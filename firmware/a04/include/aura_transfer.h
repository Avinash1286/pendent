/* SPDX-License-Identifier: MIT */
#ifndef AURA_A04_TRANSFER_H
#define AURA_A04_TRANSFER_H
#include "aura_journal_cursor.h"

#define AURA_TRANSFER_COMMAND_MAX 20u
#define AURA_TRANSFER_RESPONSE_MAX 512u
#define AURA_TRANSFER_FILE_MAX (320u * 1024u * 1024u)
enum aura_transfer_opcode { AURA_TRANSFER_HELLO=1, AURA_TRANSFER_LIST,
    AURA_TRANSFER_SELECT, AURA_TRANSFER_READ, AURA_TRANSFER_FINISH, AURA_TRANSFER_CANCEL };
enum aura_transfer_status { AURA_TRANSFER_OK=0, AURA_TRANSFER_STATUS_BUSY,
    AURA_TRANSFER_STATUS_INVALID, AURA_TRANSFER_NOT_FOUND, AURA_TRANSFER_IO_ERROR,
    AURA_TRANSFER_STATUS_FORBIDDEN, AURA_TRANSFER_END_OF_LIST, AURA_TRANSFER_STATUS_STALE,
    AURA_TRANSFER_STATUS_CONFLICT };
enum aura_transfer_result { AURA_TRANSFER_ACCEPTED=0, AURA_TRANSFER_JOINED=1,
    AURA_TRANSFER_CACHED=2, AURA_TRANSFER_INVALID=-700, AURA_TRANSFER_BUSY=-701,
    AURA_TRANSFER_STALE=-702, AURA_TRANSFER_FORBIDDEN=-703, AURA_TRANSFER_SOURCE_CHANGED=-704,
    AURA_TRANSFER_STATE=-705, AURA_TRANSFER_EXHAUSTED=-706, AURA_TRANSFER_CONFLICT=-707,
    AURA_TRANSFER_BUFFER_SMALL=-708 };
#define AURA_TRANSFER_IDLE 0
#define AURA_TRANSFER_WAIT 1
#define AURA_TRANSFER_RESPONSE 2

/* Static allocation only. Private implementation state; do not copy/mutate a
 * live context. ONE global serialized storage owner owns every API call. */
struct aura_transfer {
    struct aura_journal *journal;
    struct aura_journal_cursor cursor;
    uint8_t device_id[16], incarnation[16];
    uint64_t connection, observed_epoch, next_offset, delivery, next_delivery;
    uint32_t revision, next_handle, handle;
    uint16_t last_transaction, response_bytes;
    uint8_t command[AURA_TRANSFER_COMMAND_MAX], command_bytes;
    uint8_t response[AURA_TRANSFER_RESPONSE_MAX];
    bool initialized, authorized, pending, response_pending, cache_valid;
    bool selected, seeked, finished, operation_started;
};

/* IDs come from the trusted storage owner; this API does not enroll/authenticate
 * a device or verify an owner proof. No key is copied into this context. */
int aura_transfer_init(struct aura_transfer *transfer, struct aura_journal *journal,
    const uint8_t device_id[16], const uint8_t incarnation[16]);
/* authorized is a TRUSTED caller result, never a wire field or BLE bond test.
 * Returns a fresh nonzero process generation; old callbacks cannot reopen it.
 * False can be used to test denial, but no response/catalog access is allowed.
 * No NAND IO in begin/end/cancel/submit/copy/fragment/sent. */
int aura_transfer_session_begin(struct aura_transfer *transfer, bool authorized, uint64_t *generation);
int aura_transfer_session_end(struct aura_transfer *transfer, uint64_t generation);
/* Local preemption/transfer timeout, separate from ordered wire CANCEL. Clears handle,
 * work and cache, retains transaction high-water. Caller cancels queued radio
 * copies too. Ownership loss / authorization expiry must END the session.
 * No source mutation or release authorization. */
int aura_transfer_cancel_work(struct aura_transfer *transfer, uint64_t generation);
/* ACCEPTED / JOINED / CACHED or negative admission result. Admission errors do
 * not overwrite pending work/cache or consume a transaction. A source epoch
 * transition clears obsolete volatile work and returns SOURCE_CHANGED; retry
 * reconciliation under a NEW transaction if the old one was already accepted. */
int aura_transfer_submit(struct aura_transfer *transfer, uint64_t generation,
    const uint8_t *command, size_t bytes);
/* IDLE / WAIT / RESPONSE or negative state transition. Each call performs at
 * most one NAND read through the cursor. Wire contextual failures are cached
 * four-byte logical error responses, never source repairs or erase commands. */
int aura_transfer_step(struct aura_transfer *transfer, uint64_t generation);
/* Caller-owned nonoverlapping copies/count/token. Private-context aliases and
 * output-output aliases reject before writes. No pointer into response/cursor/
 * NAND storage escapes. Rechecks session/source and delivery generation before
 * publication. A retry during transmission JOINs the current delivery; a retry
 * after response_sent obtains a fresh token, rejecting old completion callbacks. */
int aura_transfer_copy_response(struct aura_transfer *transfer, uint64_t generation,
    uint8_t *out, size_t capacity, size_t *bytes, uint64_t *delivery);
int aura_transfer_copy_fragment(struct aura_transfer *transfer, uint64_t generation,
    uint16_t transaction, uint64_t delivery, uint16_t actual_att_mtu, uint16_t offset,
    uint8_t *out, size_t capacity, size_t *bytes);
/* Notification-chain completion only; permits a new command while retaining
 * the immutable last reply for retry. Never a durable phone acknowledgement. */
int aura_transfer_response_sent(struct aura_transfer *transfer, uint64_t generation,
    uint16_t transaction, uint64_t delivery);
#endif
