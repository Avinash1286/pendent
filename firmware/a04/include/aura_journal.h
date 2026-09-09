/* SPDX-License-Identifier: MIT */
#ifndef AURA_A04_JOURNAL_H
#define AURA_A04_JOURNAL_H
#include "aura_archive.h"
#include "aura_nand.h"

#define AURA_JOURNAL_MAX_CAPTURES 128u
#define AURA_JOURNAL_META_BYTES 256u
#define AURA_JOURNAL_DATA_HEADER 64u
#define AURA_JOURNAL_DATA_BYTES 1980u
#define AURA_JOURNAL_NONE UINT16_MAX
#define AURA_JOURNAL_FULL (-400)
#define AURA_JOURNAL_CONFLICT (-401)
#define AURA_JOURNAL_CORRUPT (-402)
#define AURA_JOURNAL_NOT_COMMITTED (-403)
#define AURA_JOURNAL_BUSY (-404)
#define AURA_JOURNAL_RETRY_PREPARE (-405)

enum aura_journal_verification { AURA_JOURNAL_UNVERIFIED, AURA_JOURNAL_VERIFIED_OPEN,
    AURA_JOURNAL_VERIFIED_FINAL, AURA_JOURNAL_VERIFIED_INTERRUPTED, AURA_JOURNAL_INVALID };
enum aura_journal_block { AURA_BLOCK_FREE, AURA_BLOCK_OWNED, AURA_BLOCK_QUARANTINED,
    AURA_BLOCK_EXCLUDED, AURA_BLOCK_PREPARED };

struct aura_journal_capture {
    uint8_t manifest[68];
    /* Only valid if verification is VERIFIED_*; no checkpoint-only ACK. */
    uint8_t committed_receipt[94];
    uint16_t first_block, last_block, blocks;
    uint8_t verification;
    bool metadata_fault;
    uint64_t committed_wire_bytes;
};

struct aura_journal {
    struct aura_nand_io io;
    struct aura_journal_capture captures[AURA_JOURNAL_MAX_CAPTURES];
    uint8_t block_state[AURA_NAND_BLOCKS];
    uint16_t owner[AURA_NAND_BLOCKS], next_block[AURA_NAND_BLOCKS];
    uint16_t count, allocation_cursor, prepared, current_block;
    /* Quarantined metadata/candidates with no provable capture association.
     * Such material is preserved; an interrupted prefix does not prove that
     * this material contains no additional source audio. */
    uint16_t unassociated_blocks;
    int active, fault;
    uint16_t current_part, data_pages, staged_bytes, staged_records;
    uint64_t page_start_offset, staged_since_ms, last_service_ms;
    bool service_clock_started;
    uint64_t metadata_reads, payload_reads, corrected_reads, committed_pages;
    /* Staged validator is updated for EVERY accepted record, independent of
     * the outer producer callback's timing. committed advances after readback. */
    struct aura_archive_writer staged, committed;
    uint8_t page[2048], scratch[2048];
};

int aura_journal_mount(struct aura_journal *journal, struct aura_nand_io io);
/* Inspect/erase/verify at most one blank candidate per call. Retry-preparation
 * can be scheduled before capture; never erase a populated/unknown block. */
int aura_journal_prepare(struct aura_journal *journal);
/* Use ONLY with aura_archive_begin_staged. Zero means buffered acceptance. */
int aura_journal_stage(void *journal, uint64_t offset, const uint8_t *wire, size_t bytes);
int aura_journal_flush(struct aura_journal *journal);
/* Call once before starting a producer (stage rejects an uninitialized clock).
 * Caller supplies monotonic wall milliseconds and must service while paused
 * too. Flushes an outstanding partial page after at most400ms between service
 * calls; it cannot enforce scheduling while the caller is blocked/asleep. */
int aura_journal_service(struct aura_journal *journal, uint64_t now_ms);
int aura_journal_receipt(const struct aura_journal *journal, uint16_t capture, uint8_t out[94]);
/* Full payload validation is lazy. Verify/export never resumes an encoder. */
int aura_journal_verify(struct aura_journal *journal, uint16_t capture);
/* Destination MUST be temporary until this returns0. Interrupted export adds
 * an explicit synthesized seal; that seal NEVER becomes a local NAND receipt. */
int aura_journal_export(struct aura_journal *journal, uint16_t capture,
                         aura_archive_commit output, void *user);
#endif
