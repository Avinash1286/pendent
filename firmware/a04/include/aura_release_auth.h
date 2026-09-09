/* SPDX-License-Identifier: MIT */
#ifndef AURA_A04_RELEASE_AUTH_H
#define AURA_A04_RELEASE_AUTH_H
#include <stddef.h>
#include <stdint.h>

#define AURA_RELEASE_WIRE_BYTES 182u
#define AURA_RELEASE_BODY_BYTES 150u
#define AURA_RELEASE_ACK_BYTES 94u
#define AURA_RELEASE_KEY_BYTES 32u
#define AURA_RELEASE_HMAC_MAX_BYTES 256u

enum aura_release_result {
    AURA_RELEASE_OK = 0,
    AURA_RELEASE_ARGUMENT = -720,
    AURA_RELEASE_FORMAT = -721,
    AURA_RELEASE_CONTEXT = -722,
    AURA_RELEASE_TAG = -723,
    AURA_RELEASE_RECEIPT = -724,
    AURA_RELEASE_REPLAY = -725,
    AURA_RELEASE_SEQUENCE_GAP = -726,
    AURA_RELEASE_EXHAUSTED = -727
};

/* Trusted, caller-owned provisioned values, NOT fields loaded from the command.
 * IDs, generation and key must be nonzero. A nonzero-key check is only an
 * initialization guard; it does not establish randomness or protected storage.
 * One independent random 32-byte key is required per device/owner generation.
 * No function retains this object, provisions ownership, or stores any state. */
struct aura_release_auth_context {
    uint8_t device_id[16], storage_incarnation[16], owner_id[16];
    uint8_t key[AURA_RELEASE_KEY_BYTES];
    uint64_t owner_generation;
};

struct aura_release_authorization {
    uint64_t release_sequence;
    uint8_t receipt[AURA_RELEASE_ACK_BYTES];
};

/* Standard full-tag HMAC-SHA256. Each input is bounded to256 bytes; empty
 * inputs are allowed with NULL pointers. All other NULL pointers are invalid.
 * This bound includes RFC4231 long-key/message cases and the RLS1 domain/body.
 * Output is unchanged on error. This helper neither derives nor stores keys. */
int aura_release_hmac_sha256(const uint8_t *key, size_t key_bytes,
                            const uint8_t *message, size_t message_bytes,
                            uint8_t tag[32]);

/* Canonical RLS1 signing helper for interoperability/tests. It accepts a
 * syntactically valid terminal ACK3; it DOES NOT establish that it is durable,
 * authorized by a user, or returned by an actual device. Such checks belong
 * to the trusted issuer before signing. Output is unchanged on error. */
int aura_release_sign(const struct aura_release_auth_context *context,
                      uint64_t sequence, const uint8_t *receipt,
                      size_t receipt_bytes, uint8_t *wire, size_t wire_bytes);

/* Authenticate/decode exactly182 bytes and match the exact expected94-byte
 * terminal ACK3 supplied by trusted independent storage verification. Full
 * tags are compared without early exit. Output is unchanged on error.
 * An interrupted ACK is accepted syntactically; caller must refuse synthesized
 * export seals, ambiguous extents or any other non-durable expected receipt.
 * SUCCESS IS NOT DELETION AUTHORITY: no replay floor, persistence, erase,
 * ownership provisioning, physical device attestation or storage checks occur.
 * A controller must also validate freshness OR match an exact durably committed
 * retry, then durably commit its grant/target extents before destructive work. */
int aura_release_authenticate(const struct aura_release_auth_context *context,
                              const uint8_t *wire, size_t wire_bytes,
                              const uint8_t *expected_receipt, size_t receipt_bytes,
                              struct aura_release_authorization *authorization);

/* Read-only freshness check: accept exactly floor+1, with nonzero sequence.
 * A persisted floor never resets on rekey within a storage incarnation.
 * This rejects even an identical old command; ONLY the storage controller can
 * identify a committed idempotent retry by comparing its stored exact envelope.
 * It does not reserve, advance, load or persist the caller's replay floor. */
int aura_release_validate_next(uint64_t sequence, uint64_t persisted_floor);
#endif
