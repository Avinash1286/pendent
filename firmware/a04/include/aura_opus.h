/* SPDX-License-Identifier: MIT */
#ifndef AURA_A04_OPUS_H
#define AURA_A04_OPUS_H
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include <opus.h>

#define AURA_OPUS_RATE 16000
#define AURA_OPUS_BITRATE 32000
#define AURA_OPUS_STATE_LIMIT 32768
#define AURA_OPUS_PACKET_LIMIT 1275
#define AURA_OPUS_MAX_SAMPLES 320

struct aura_opus_packet {
    uint32_t sequence;
    uint64_t sample_offset;
    uint16_t sample_count;
    uint16_t bytes;
    uint8_t data[AURA_OPUS_PACKET_LIMIT];
};

/* Return zero ONLY after the packet is durably committed. A failed commit
 * retains the exact packet for retry; it must be idempotent by sequence/hash. */
typedef int (*aura_opus_commit)(void *user, const struct aura_opus_packet *packet);

struct aura_opus_seal {
    uint64_t source_samples;
    uint64_t encoded_samples;
    uint32_t packets;
    uint16_t pre_skip;
    uint16_t end_trim;
};

struct aura_opus_capture {
    OpusEncoder *encoder;
    aura_opus_commit commit;
    void *user;
    uint64_t source_samples;
    uint64_t encoded_samples;
    uint32_t accepted_packets;
    uint16_t frame_samples;
    uint16_t buffered_samples;
    uint16_t lookahead;
    bool pending;
    bool closing;
    bool finished;
    bool staging;
    int fault;
    int16_t pcm[AURA_OPUS_MAX_SAMPLES];
    struct aura_opus_packet packet;
};

size_t aura_opus_state_bytes(void);
/* Initialization always invalidates the previous capture, including on failure.
 * The caller must finish/persist a live recording before reinitializing it. */
int aura_opus_init(struct aura_opus_capture *capture, void *state, size_t state_bytes,
                   unsigned frame_ms, aura_opus_commit commit, void *user);
/* Explicit speculative producer: callback zero means copied into a bounded
 * staging owner, NOT durable. accepted_packets/finish seal are declarations;
 * only the journal's independently committed snapshot can issue receipts. */
int aura_opus_init_staged(struct aura_opus_capture *capture, void *state, size_t state_bytes,
                          unsigned frame_ms, aura_opus_commit stage, void *user);
/* *consumed counts samples copied into the protected capture buffer, even when
 * a later commit fails. Retry that pending commit, then submit only the remainder. */
int aura_opus_push(struct aura_opus_capture *capture, const int16_t *pcm,
                  size_t count, size_t *consumed);
int aura_opus_retry(struct aura_opus_capture *capture);
/* Pads the encoder tail and returns exact pre-skip/end-trim metadata. Repeat
 * after failed commit; no new source samples are accepted once closing starts. */
int aura_opus_finish(struct aura_opus_capture *capture, struct aura_opus_seal *seal);
#endif
