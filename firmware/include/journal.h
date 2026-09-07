/* SPDX-License-Identifier: MIT */
#ifndef AURA_JOURNAL_H
#define AURA_JOURNAL_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#define AJ_PAGE 2048u
#define AJ_HEADER 40u
#define AJ_PAYLOAD (AJ_PAGE - AJ_HEADER)
#define AJ_MAX_NOTES 128
enum { AJ_START = 1, AJ_DATA = 2, AJ_END = 3, AJ_DELETE = 4, AJ_MARK = 5 };
/* Backend returns -EBADMSG for uncorrectable ECC; erased pages are 0xff. */
struct aj_io {
    int (*read)(uint32_t page, uint8_t *out);
    int (*write)(uint32_t page, const uint8_t *in);
    bool (*bad)(uint32_t block);
    uint32_t pages;
};
struct aj_note {
    uint32_t id, first, last, bytes, crc;
    uint64_t time;
    bool deleted, recovered, fault;
};
struct aj_store {
    struct aj_io io;
    struct aj_note notes[AJ_MAX_NOTES];
    uint16_t count;
    int active;
    uint32_t next, next_id;
    uint32_t cursor_id, cursor_page, cursor_offset;
    bool fault;
    uint8_t page[AJ_PAGE];
};
uint32_t aj_crc(uint32_t prior, const void *data, size_t len);
int aj_mount(struct aj_store *s, struct aj_io io);
int aj_begin(struct aj_store *s, uint64_t time);
int aj_append(struct aj_store *s, const uint8_t *pcm, uint16_t size);
int aj_end(struct aj_store *s, bool interrupted);
int aj_mark(struct aj_store *s);
int aj_delete(struct aj_store *s, uint32_t id, uint32_t size, uint32_t crc);
struct aj_note *aj_find(struct aj_store *s, uint32_t id);
int aj_read(struct aj_store *s, uint32_t id, uint32_t offset, uint8_t *out, uint16_t size);
uint32_t aj_free(const struct aj_store *s);
#endif
