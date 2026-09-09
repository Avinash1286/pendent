/* SPDX-License-Identifier: MIT */
#ifndef AURA_A04_RECORDER_H
#define AURA_A04_RECORDER_H
#include "aura_journal.h"

#define AURA_RECORDER_BLOCK_SAMPLES 320u
#define AURA_RECORDER_BAD_ARGUMENT (-500)
#define AURA_RECORDER_STATE (-501)
#define AURA_RECORDER_STALE_EPOCH (-502)
#define AURA_RECORDER_GAP (-503)
#define AURA_RECORDER_OVERFLOW (-504)
#define AURA_RECORDER_SOURCE_FAILED (-505)
#define AURA_RECORDER_CANCELLED (-506)

enum aura_recorder_state {
    AURA_RECORDER_IDLE, AURA_RECORDER_RECORDING, AURA_RECORDER_FINALIZED,
    AURA_RECORDER_INTERRUPTED, AURA_RECORDER_FAILED
};

/* Immutable mono PCM16 message owned by the upstream bounded queue/slab until
 * consume returns. Epoch/sequence/offset describe delivered source continuity;
 * they cannot establish physical microphone continuity without driver health. */
struct aura_recorder_block {
    uint64_t epoch;
    uint32_t sequence;
    uint64_t source_offset;
    const int16_t *pcm;
    size_t samples;
};

/* One storage-thread owner. No internal queue, locks, allocation or atomics.
 * The adapter owns producer concurrency, fixed PCM slots and overflow signals.
 * Hardware privacy/stop acts upstream immediately; it never waits for this
 * synchronous encoding/storage owner. Never reinitialize a live recorder. */
struct aura_recorder {
    struct aura_journal *journal;
    void *encoder_state;
    size_t encoder_bytes;
    struct aura_opus_capture codec;
    struct aura_archive_writer archive;
    struct aura_opus_seal seal;
    uint64_t epoch, last_epoch, source_samples;
    uint32_t next_sequence;
    uint16_t capture_index;
    enum aura_recorder_state state;
    int fault_reason, close_error;
};

int aura_recorder_init(struct aura_recorder *recorder, struct aura_journal *journal,
                       void *aligned_encoder_state, size_t encoder_bytes);
/* 20 ms / 16 kHz mono profile. Startup time must be UNKNOWN (time_source and
 * started_at_ms zero): a request timestamp cannot bind the first usable sample
 * across asynchronous microphone startup/warmup. Every archive attempt consumes
 * a strictly increasing nonzero epoch; the manifest must use a fresh ID.
 * Zero is the permission to start the microphone. RETRY_PREPARE means retry
 * start before enabling it. Journal is already mounted by the storage owner. */
int aura_recorder_start(struct aura_recorder *recorder,
                        const struct aura_archive_manifest *manifest,
                        uint64_t epoch, uint64_t now_ms);
/* Synchronous storage-owner call, not a producer/ISR function. Exact consumed
 * is returned on all paths. Release this message after return; NEVER resubmit
 * its consumed prefix. Any current-epoch gap/encode/storage fault ends capture.
 * A stale epoch returns STALE_EPOCH without changing the current capture. */
int aura_recorder_consume(struct aura_recorder *recorder,
                          const struct aura_recorder_block *block,
                          uint64_t now_ms, size_t *consumed);
int aura_recorder_service(struct aura_recorder *recorder, uint64_t now_ms);
/* Clean stop is legal only after upstream reports healthy quiescence and its
 * FIFO has drained. source_end is the producer's final mono-sample watermark.
 * A missing final block is therefore a GAP, not an apparently clean ending. */
int aura_recorder_stop(struct aura_recorder *recorder, uint64_t epoch,
                       uint64_t source_end, uint64_t now_ms);
/* Upstream overflow, driver fault or explicit aborted capture: no encoder tail
 * flush. Preserve an explicitly interrupted complete-packet prefix. The reason
 * remains observable separately from close_error; if I/O prevents sealing,
 * reopen/export later must recover the verified physical prefix. */
int aura_recorder_interrupt(struct aura_recorder *recorder, uint64_t epoch,
                            int reason, uint64_t now_ms);
#endif
