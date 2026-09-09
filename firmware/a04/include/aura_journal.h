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

/* Physical allocation identity, not a release policy or deletion authority.
 * Legacy v1 returns version1, owned=false, and zero incarnation/generation. */
struct aura_journal_allocation_identity {
    uint8_t incarnation[16];
    uint64_t allocation_generation;
    uint8_t version;
    bool owned;
};

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
    /* One namespace and one next-capture binding, never per-block/capture RAM.
     * Durable reservation/nonreuse remains the external owner's obligation. */
    uint8_t owned_incarnation[16], bound_manifest[68];
    uint64_t bound_generation, capture_generation, last_bound_generation;
    bool owned_profile, binding_pending;
    /* Staged validator is updated for EVERY accepted record, independent of
     * the outer producer callback's timing. committed advances after readback. */
    struct aura_archive_writer staged, committed;
    uint8_t page[2048], scratch[2048];
};

int aura_journal_mount(struct aura_journal *journal, struct aura_nand_io io);
/* Opt into v2 writes after mount. Nonzero incarnation; cannot switch or disable
 * it without remounting. Conservatively observes existing matching v2 metadata
 * to raise the volatile generation floor. This does not replace a durable ID
 * reservation ledger, especially after erased allocations leave no metadata. */
int aura_journal_set_owned_profile(struct aura_journal *journal, const uint8_t incarnation[16]);
/* Bind BEFORE recorder_start. Exact canonical manifest and fresh nonzero
 * generation; one pending binding at a time, idle owned journal only. The
 * binding survives blank-block preparation retries, but a different valid
 * manifest rejects/discards it. It is consumed before the first header program
 * attempt, including uncertain/failed attempts. No old generation is unburned. */
int aura_journal_bind_capture(struct aura_journal *journal, const uint8_t manifest[68], uint64_t generation);
int aura_journal_discard_binding(struct aura_journal *journal);
/* Repeats full source+metadata validation before returning identity. A v2
 * identity also applies to an interrupted/open prefix; it does NOT authorize
 * reclaiming that prefix or any unassociated material. Output only on zero. */
int aura_journal_get_allocation_identity(struct aura_journal *journal, uint16_t capture,
                                        struct aura_journal_allocation_identity *identity);
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
