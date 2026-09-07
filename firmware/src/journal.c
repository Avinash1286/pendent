/* SPDX-License-Identifier: MIT
 * An append-only, once-programmed-page NAND journal. No audio is overwritten.
 * Each page has a CRC over its header and payload. Erase/reclamation is deliberately
 * absent: deleting a note records a tombstone but never risks a live erase block.
 */
#include "journal.h"
#include <string.h>
#include <errno.h>
#define MAGIC 0x33415241u
static uint32_t get32(const uint8_t *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static void put32(uint8_t *p, uint32_t v)
{
    for (int i = 0; i < 4; i++)
        p[i] = (uint8_t)(v >> (8 * i));
}
uint32_t aj_crc(uint32_t prior, const void *data, size_t len)
{
    uint32_t c = ~prior;
    const uint8_t *p = data;
    while (len--) {
        c ^= *p++;
        for (int i = 0; i < 8; i++)
            c = (c >> 1) ^ (0xedb88320u & (0u - (c & 1)));
    }
    return ~c;
}
static uint32_t page_crc(const uint8_t *p)
{
    uint32_t c = aj_crc(0, p, 36);
    return aj_crc(c, p + AJ_HEADER, get32(p + 16));
}
static int valid(const uint8_t *p)
{
    return get32(p) == MAGIC && p[4] == 1 && get32(p + 16) <= AJ_PAYLOAD &&
           get32(p + 36) == page_crc(p);
}
static bool empty(const uint8_t *p)
{
    for (unsigned i = 0; i < AJ_PAGE; i++)
        if (p[i] != 255)
            return false;
    return true;
}
static uint32_t next_good(struct aj_store *s, uint32_t p)
{
    while (p < s->io.pages && s->io.bad(p / 64))
        p = (p / 64 + 1) * 64;
    /* Preserve both manufacturer-marker pages in every erase block. */
    if (p < s->io.pages && p % 64 < 2)
        p += 2 - p % 64;
    return p;
}
struct aj_note *aj_find(struct aj_store *s, uint32_t id)
{
    for (int i = 0; i < s->count; i++)
        if (s->notes[i].id == id && !s->notes[i].deleted)
            return &s->notes[i];
    return NULL;
}
static int emit(struct aj_store *s, int type, uint32_t id, uint32_t offset, const uint8_t *data,
                uint32_t n, uint64_t time, uint32_t crc, uint8_t flags)
{
    s->next = next_good(s, s->next);
    if (s->next >= s->io.pages)
        return -ENOSPC;
    uint8_t *p = s->page;
    memset(p, 255, AJ_PAGE);
    put32(p, MAGIC);
    p[4] = 1;
    p[5] = type;
    p[6] = flags;
    p[7] = 0;
    put32(p + 8, id);
    put32(p + 12, offset);
    put32(p + 16, n);
    put32(p + 20, (uint32_t)time);
    put32(p + 24, (uint32_t)(time >> 32));
    put32(p + 28, crc);
    put32(p + 32, 0);
    if (n)
        memcpy(p + AJ_HEADER, data, n);
    put32(p + 36, page_crc(p));
    uint32_t at = s->next++;
    int r = s->io.write(at, p);
    if (r) {
        s->fault = true;
        return r;
    }
    return 0;
}
int aj_mount(struct aj_store *s, struct aj_io io)
{
    memset(s, 0, sizeof(*s));
    s->io = io;
    s->active = -1;
    s->next_id = 1;
    int current = -1;
    bool closed = false;
    /* Scan all pages: a torn/erased page is not a trustworthy high-water mark. */
    for (uint32_t at = 0; at < io.pages; at = next_good(s, at + 1)) {
        at = next_good(s, at);
        if (at >= io.pages)
            break;
        int r = io.read(at, s->page);
        if (r) {
            s->fault = true;
            s->next = at + 1;
            if (current >= 0)
                s->notes[current].fault = true;
            continue;
        }
        if (empty(s->page))
            continue;
        s->next = at + 1;
        if (!valid(s->page)) {
            if (current >= 0 && !closed) {
                s->notes[current].recovered = true;
                closed = true;
            }
            continue;
        }
        uint8_t *p = s->page;
        uint32_t id = get32(p + 8), off = get32(p + 12), n = get32(p + 16);
        if (id >= s->next_id)
            s->next_id = id + 1;
        if (p[5] == AJ_START) {
            if (s->count >= AJ_MAX_NOTES) {
                s->fault = true;
                continue;
            }
            current = s->count++;
            closed = false;
            s->notes[current] =
                (struct aj_note){.id = id,
                                 .first = at,
                                 .last = at,
                                 .time = (uint64_t)get32(p + 20) | ((uint64_t)get32(p + 24) << 32),
                                 .recovered = true};
        } else if (p[5] == AJ_DELETE) {
            struct aj_note *note = aj_find(s, id);
            if (note && note->bytes == off && note->crc == get32(p + 28))
                note->deleted = true;
        } else if (current >= 0 && s->notes[current].id == id && !closed) {
            struct aj_note *note = &s->notes[current];
            if (p[5] == AJ_DATA) {
                if (off != note->bytes || n % 2) {
                    note->fault = true;
                    closed = true;
                    continue;
                }
                note->crc = aj_crc(note->crc, p + AJ_HEADER, n);
                note->bytes += n;
                note->last = at;
            } else if (p[5] == AJ_END) {
                if (off != note->bytes || get32(p + 28) != note->crc)
                    note->fault = true;
                else
                    note->recovered = (p[6] & 1) != 0;
                closed = true;
            }
        }
    }
    s->next = next_good(s, s->next);
    return s->fault ? -EIO : 0;
}
uint32_t aj_free(const struct aj_store *s)
{
    uint32_t pages = 0;
    for (uint32_t p = s->next; p < s->io.pages; p++)
        if (!s->io.bad(p / 64) && p % 64 >= 2)
            pages++;
    return pages > 2 ? (pages - 2) * AJ_PAYLOAD : 0;
}
int aj_begin(struct aj_store *s, uint64_t time)
{
    if (s->fault)
        return -EIO;
    if (s->active >= 0)
        return -EBUSY;
    if (s->count >= AJ_MAX_NOTES || aj_free(s) < AJ_PAYLOAD * 3)
        return -ENOSPC;
    if (s->next_id == 0)
        return -EOVERFLOW;
    uint32_t id = s->next_id++, first = next_good(s, s->next);
    int r = emit(s, AJ_START, id, 0, NULL, 0, time, 0, 0);
    if (r)
        return r;
    s->active = s->count++;
    s->notes[s->active] =
        (struct aj_note){.id = id, .first = first, .last = first, .time = time, .recovered = true};
    return 0;
}
int aj_append(struct aj_store *s, const uint8_t *pcm, uint16_t size)
{
    if (s->active < 0)
        return -EINVAL;
    if (size > AJ_PAYLOAD || size % 2)
        return -EINVAL;
    if (aj_free(s) < AJ_PAYLOAD)
        return -ENOSPC;
    struct aj_note *n = &s->notes[s->active];
    uint32_t at = next_good(s, s->next);
    int r = emit(s, AJ_DATA, n->id, n->bytes, pcm, size, 0, 0, 0);
    if (r)
        return r;
    n->crc = aj_crc(n->crc, pcm, size);
    n->bytes += size;
    n->last = at;
    return 0;
}
int aj_end(struct aj_store *s, bool interrupted)
{
    if (s->active < 0)
        return -EINVAL;
    struct aj_note *n = &s->notes[s->active];
    int r = emit(s, AJ_END, n->id, n->bytes, NULL, 0, 0, n->crc, interrupted ? 1 : 0);
    n->recovered = interrupted || r;
    s->active = -1;
    return r;
}
int aj_mark(struct aj_store *s)
{
    if (s->active < 0)
        return -EINVAL;
    struct aj_note *n = &s->notes[s->active];
    return emit(s, AJ_MARK, n->id, n->bytes, NULL, 0, 0, 0, 0);
}
int aj_delete(struct aj_store *s, uint32_t id, uint32_t size, uint32_t crc)
{
    if (s->active >= 0)
        return -EBUSY;
    struct aj_note *n = aj_find(s, id);
    if (!n)
        return -ENOENT;
    if (n->fault || n->bytes != size || n->crc != crc)
        return -EPERM;
    int r = emit(s, AJ_DELETE, id, size, NULL, 0, 0, crc, 0);
    if (!r)
        n->deleted = true;
    return r;
}
int aj_read(struct aj_store *s, uint32_t id, uint32_t offset, uint8_t *out, uint16_t size)
{
    struct aj_note *n = aj_find(s, id);
    if (!n)
        return -ENOENT;
    if (n->fault)
        return -EIO;
    if (s->active >= 0 && &s->notes[s->active] == n)
        return -EBUSY;
    if (offset > n->bytes)
        return -EINVAL;
    if (size > n->bytes - offset)
        size = n->bytes - offset;
    uint16_t copied = 0;
    uint32_t first =
        (s->cursor_id == id && offset >= s->cursor_offset) ? s->cursor_page : n->first + 1;
    for (uint32_t at = first; at <= n->last && copied < size; at = next_good(s, at + 1)) {
        int r = s->io.read(at, s->page);
        if (r)
            return r;
        if (!valid(s->page))
            return -EBADMSG;
        uint8_t *p = s->page;
        if (get32(p + 8) != id || p[5] != AJ_DATA)
            continue;
        uint32_t start = get32(p + 12), len = get32(p + 16);
        if (offset >= start + len)
            continue;
        if (offset < start)
            return -EBADMSG;
        s->cursor_id = id;
        s->cursor_page = at;
        s->cursor_offset = start;
        uint32_t skip = offset - start, take = len - skip;
        if (take > size - copied)
            take = size - copied;
        memcpy(out + copied, p + AJ_HEADER + skip, take);
        copied += take;
        offset += take;
    }
    return copied == size ? copied : -EIO;
}
