/* SPDX-License-Identifier: MIT */
#ifndef AURA_A04_JOURNAL_CURSOR_H
#define AURA_A04_JOURNAL_CURSOR_H
#include "aura_journal.h"

#define AURA_CURSOR_PENDING 1
#define AURA_CURSOR_READY 2
#define AURA_CURSOR_DATA 3
#define AURA_CURSOR_STALE (-406)
#define AURA_CURSOR_STATE (-407)
#define AURA_CURSOR_BOUNDARY (-408)
#define AURA_CURSOR_CHUNK_MAX 256u

struct aura_journal_cursor_info {
    uint8_t manifest[68], physical_receipt[94];
    uint64_t physical_bytes, export_bytes;
    struct aura_journal_allocation_identity allocation;
    bool derived_seal;
};

/* Internal state, exposed only for static allocation. Do not modify/copy an
 * active cursor. No heap and no retained pointers into journal scratch. */
struct aura_journal_walk {
    struct aura_journal_allocation_identity identity;
    uint32_t previous;
    uint16_t block, part, page, valid_pages;
    bool hole, callback_failed;
};
struct aura_journal_cursor {
    struct aura_journal *journal;
    struct aura_journal_cursor_info selected;
    struct aura_journal_walk walk;
    struct aura_archive_writer view;
    uint64_t epoch, resume_offset, buffer_offset;
    uint16_t index, first_block, last_block, blocks, catalog_count;
    uint16_t buffer_bytes, buffer_at;
    uint8_t phase;
    int error;
    uint8_t buffer[AURA_JOURNAL_DATA_BYTES];
};

/* All calls belong to ONE serialized storage owner. No concurrent journal,
 * storage, callback or raw-media access. Capture requests cancel the cursor
 * before beginning other work. External media operations must invalidate it.
 * IDs are the exact 16-byte device + 16-byte capture identity, not catalog IDs.
 * Open performs no NAND reads. Unassociated source and pending/active capture
 * deny selection. A faulted active capture must first be remounted by its owner. */
int aura_journal_cursor_open(struct aura_journal_cursor *cursor,
    struct aura_journal *journal, const uint8_t identity[32]);
/* At most ONE NAND read and one bounded 1980-byte page replay per call.
 * Returns PENDING, READY, or negative. READY means the complete physical source
 * was independently verified, not that the phone has saved anything. */
int aura_journal_cursor_verify_step(struct aura_journal_cursor *cursor);
int aura_journal_cursor_get_info(struct aura_journal_cursor *cursor,
    struct aura_journal_cursor_info *out);
/* Exactly once after READY. Offset zero or a complete canonical record boundary,
 * including physical EOF / export EOF. A non-boundary is rejected during the
 * subsequent SINGLE linear replay, not rounded or silently overwritten. */
int aura_journal_cursor_seek(struct aura_journal_cursor *cursor, uint64_t offset);
/* capacity 1..256; caller-owned output is copied and never retained. DATA gives
 * exact absolute offset + length. PENDING gives zero length and no output data.
 * Zero is FINISHED, only after complete replay AND a third, bounded physical
 * verification against the selection's receipt, length and allocation identity.
 * Destination remains TEMPORARY until zero. Earlier DATA is not a receipt.
 * READ retries/cached logical responses are the future transport owner's duty;
 * this sequential cursor does not implement BLE transaction semantics. */
int aura_journal_cursor_read(struct aura_journal_cursor *cursor,
    uint8_t *out, size_t capacity, uint64_t *offset, size_t *bytes);
/* Volatile only; no NAND writes, release authorization, or source deletion. */
void aura_journal_cursor_cancel(struct aura_journal_cursor *cursor);
#endif
