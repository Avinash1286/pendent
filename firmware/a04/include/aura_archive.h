/* SPDX-License-Identifier: MIT */
#ifndef AURA_A04_ARCHIVE_H
#define AURA_A04_ARCHIVE_H
#include "aura_opus.h"

#define AURA_ARCHIVE_MANIFEST_BYTES 68u
#define AURA_ARCHIVE_HEADER_BYTES 22u
#define AURA_ARCHIVE_SEAL_BYTES 120u
#define AURA_ARCHIVE_ACK_BYTES 94u
#define AURA_ARCHIVE_RECORD_BYTES 1301u
#define AURA_ARCHIVE_MAX_RECORDS 1000000u
#define AURA_ARCHIVE_MAX_PAYLOAD_BYTES (256u * 1024u * 1024u)
#define AURA_ARCHIVE_FINALIZED 1u
#define AURA_ARCHIVE_INTERRUPTED 2u
#define AURA_ARCHIVE_BAD_ARGUMENT (-200)
#define AURA_ARCHIVE_BUSY (-201)
#define AURA_ARCHIVE_CONFLICT (-202)
#define AURA_ARCHIVE_LIMIT (-203)

struct aura_archive_manifest {
    uint8_t device_id[16], capture_id[16];
    uint16_t frame_samples, pre_skip;
    uint64_t started_at_ms;
    uint8_t time_source;
};

/* A real sink returns zero only after exact bytes are durable at file_offset.
 * A retry may repeat bytes after an uncertain write/flush; it must not append a
 * second copy. No radio notification callback can provide this guarantee. */
typedef int (*aura_archive_commit)(void *user, uint64_t file_offset,
                                  const uint8_t *wire, size_t bytes);

struct aura_archive_writer {
    struct aura_archive_manifest manifest;
    aura_archive_commit commit;
    void *user;
    uint64_t file_offset, encoded_bytes, encoded_samples, max_bookmark;
    uint32_t next_sequence, audio_packets;
    uint8_t chain[32], pending_chain[32];
    uint8_t wire[AURA_ARCHIVE_RECORD_BYTES];
    uint16_t pending_bytes, pending_payload;
    uint64_t pending_bookmark;
    uint8_t pending_kind, status;
    bool begun, closing, staging;
};

void aura_archive_sha256(const uint8_t *data, size_t bytes, uint8_t digest[32]);
uint32_t aura_archive_crc32(const uint8_t *data, size_t bytes);
int aura_archive_begin(struct aura_archive_writer *writer,
                        const struct aura_archive_manifest *manifest,
                        aura_archive_commit commit, void *user);
/* Callback zero is explicitly RAM acceptance here. This writer cannot issue
 * receipts; a journal must independently verify and promote a committed view. */
int aura_archive_begin_staged(struct aura_archive_writer *writer,
                              const struct aura_archive_manifest *manifest,
                              aura_archive_commit stage, void *user);
/* Validate/replay one exact canonical record into an independent staged view.
 * Start with a zero-initialized view. Failure leaves the previous view intact.
 * Useful for journal page-end snapshots and recovery; never a durable ACK. */
int aura_archive_replay(struct aura_archive_writer *view, const uint8_t *wire, size_t bytes);
/* Attach directly as aura_opus_init's sink. Its retries MUST go through
 * aura_opus_retry, so both state machines observe the same completed packet. */
int aura_archive_opus_commit(void *writer, const struct aura_opus_packet *packet);
int aura_archive_bookmark(struct aura_archive_writer *writer, uint64_t source_offset);
int aura_archive_finalize(struct aura_archive_writer *writer, const struct aura_opus_seal *seal);
/* Close a preserved, unflushed prefix: original source duration is unknown.
 * This does not reconstruct writer state from NAND after a physical reboot. */
int aura_archive_interrupt(struct aura_archive_writer *writer);
/* Manifest/bookmark/seal retry only. Pending AUDIO must use aura_opus_retry. */
int aura_archive_retry(struct aura_archive_writer *writer);
int aura_archive_receipt(const struct aura_archive_writer *writer,
                          uint8_t wire[AURA_ARCHIVE_ACK_BYTES]);
#endif
