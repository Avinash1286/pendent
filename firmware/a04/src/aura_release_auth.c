/* SPDX-License-Identifier: MIT
 * RLS1 uses RFC2104 HMAC-SHA256 and the existing portable archive SHA256.
 * Authentication only: this file has no storage, erase or provisioning API. */
#include "aura_release_auth.h"
#include "aura_archive.h"
#include <string.h>

/* sizeof includes exactly one terminal NUL in the authenticated domain. */
static const uint8_t release_domain[] = "AURA-A04-OWNER-RELEASE-v1";
_Static_assert(sizeof(release_domain) + AURA_RELEASE_BODY_BYTES <=
               AURA_RELEASE_HMAC_MAX_BYTES, "RLS1 HMAC input exceeds bound");
_Static_assert(AURA_RELEASE_ACK_BYTES == AURA_ARCHIVE_ACK_BYTES, "ACK3 size changed");

static uint64_t get_le(const uint8_t *p, unsigned bytes)
{
    uint64_t value = 0;
    for (unsigned i = 0; i < bytes; ++i) value |= (uint64_t)p[i] << (8u * i);
    return value;
}

static void put_le(uint8_t *p, uint64_t value, unsigned bytes)
{
    for (unsigned i = 0; i < bytes; ++i) p[i] = (uint8_t)(value >> (8u * i));
}

static int nonzero(const uint8_t *p, size_t bytes)
{
    uint8_t value = 0;
    for (size_t i = 0; i < bytes; ++i) value |= p[i];
    return value != 0;
}

static void wipe(void *p, size_t bytes)
{
    volatile uint8_t *out = p;
    while (bytes--) *out++ = 0;
}

static int equal_tag(const uint8_t a[32], const uint8_t b[32])
{
    /* No memcmp and no data-dependent early exit in the full32-byte comparison.
     * This is a source-level guarantee, not a measured side-channel result. */
    volatile uint8_t difference = 0;
    for (unsigned i = 0; i < 32; ++i) difference |= (uint8_t)(a[i] ^ b[i]);
    return difference == 0;
}

int aura_release_hmac_sha256(const uint8_t *key, size_t key_bytes,
                            const uint8_t *message, size_t message_bytes,
                            uint8_t tag[32])
{
    if (!tag || (!key && key_bytes) || (!message && message_bytes) ||
        key_bytes > AURA_RELEASE_HMAC_MAX_BYTES ||
        message_bytes > AURA_RELEASE_HMAC_MAX_BYTES) return AURA_RELEASE_ARGUMENT;
    uint8_t block[64] = {0};
    uint8_t input[64 + AURA_RELEASE_HMAC_MAX_BYTES];
    uint8_t inner[32], result[32];
    if (key_bytes > sizeof(block)) aura_archive_sha256(key, key_bytes, block);
    else if (key_bytes) memcpy(block, key, key_bytes);
    for (unsigned i = 0; i < 64; ++i) input[i] = (uint8_t)(block[i] ^ 0x36u);
    if (message_bytes) memcpy(input + 64, message, message_bytes);
    aura_archive_sha256(input, 64 + message_bytes, inner);
    for (unsigned i = 0; i < 64; ++i) input[i] = (uint8_t)(block[i] ^ 0x5cu);
    memcpy(input + 64, inner, sizeof(inner));
    aura_archive_sha256(input, 64 + sizeof(inner), result);
    memcpy(tag, result, sizeof(result));
    wipe(block, sizeof(block)); wipe(input, sizeof(input));
    wipe(inner, sizeof(inner)); wipe(result, sizeof(result));
    return AURA_RELEASE_OK;
}

static int context_valid(const struct aura_release_auth_context *context)
{
    if (!context) return AURA_RELEASE_ARGUMENT;
    if (!context->owner_generation || !nonzero(context->device_id, 16) ||
        !nonzero(context->storage_incarnation, 16) || !nonzero(context->owner_id, 16) ||
        !nonzero(context->key, AURA_RELEASE_KEY_BYTES)) return AURA_RELEASE_CONTEXT;
    return AURA_RELEASE_OK;
}

static int receipt_valid(const struct aura_release_auth_context *context,
                         const uint8_t *receipt, size_t bytes)
{
    if (!receipt || bytes != AURA_RELEASE_ACK_BYTES) return AURA_RELEASE_ARGUMENT;
    if (memcmp(receipt, "ACK3", 4) || receipt[4] != 3 ||
        (receipt[5] != AURA_ARCHIVE_FINALIZED && receipt[5] != AURA_ARCHIVE_INTERRUPTED) ||
        !nonzero(receipt + 6, 16) || !nonzero(receipt + 22, 16) ||
        get_le(receipt + 38, 4) > AURA_ARCHIVE_MAX_RECORDS ||
        get_le(receipt + 42, 8) > (UINT64_C(1) << 40) ||
        get_le(receipt + 50, 8) > INT64_MAX ||
        get_le(receipt + 90, 4) != aura_archive_crc32(receipt, 90))
        return AURA_RELEASE_FORMAT;
    if (memcmp(receipt + 6, context->device_id, 16)) return AURA_RELEASE_CONTEXT;
    return AURA_RELEASE_OK;
}

static int release_tag(const struct aura_release_auth_context *context,
                       const uint8_t *body, uint8_t tag[32])
{
    uint8_t message[sizeof(release_domain) + AURA_RELEASE_BODY_BYTES];
    memcpy(message, release_domain, sizeof(release_domain));
    memcpy(message + sizeof(release_domain), body, AURA_RELEASE_BODY_BYTES);
    return aura_release_hmac_sha256(context->key, AURA_RELEASE_KEY_BYTES,
                                   message, sizeof(message), tag);
}

int aura_release_sign(const struct aura_release_auth_context *context,
                      uint64_t sequence, const uint8_t *receipt,
                      size_t receipt_bytes, uint8_t *wire, size_t wire_bytes)
{
    if (!wire || wire_bytes != AURA_RELEASE_WIRE_BYTES || !sequence)
        return AURA_RELEASE_ARGUMENT;
    int result = context_valid(context);
    if (result) return result;
    result = receipt_valid(context, receipt, receipt_bytes);
    if (result) return result;
    uint8_t encoded[AURA_RELEASE_WIRE_BYTES];
    memcpy(encoded, "RLS1", 4);
    encoded[4] = 1; encoded[5] = 1; encoded[6] = 1; encoded[7] = 0;
    memcpy(encoded + 8, context->storage_incarnation, 16);
    memcpy(encoded + 24, context->owner_id, 16);
    put_le(encoded + 40, context->owner_generation, 8);
    put_le(encoded + 48, sequence, 8);
    memcpy(encoded + 56, receipt, AURA_RELEASE_ACK_BYTES);
    result = release_tag(context, encoded, encoded + AURA_RELEASE_BODY_BYTES);
    if (!result) memcpy(wire, encoded, sizeof(encoded));
    wipe(encoded, sizeof(encoded));
    return result;
}

int aura_release_authenticate(const struct aura_release_auth_context *context,
                              const uint8_t *wire, size_t wire_bytes,
                              const uint8_t *expected_receipt, size_t receipt_bytes,
                              struct aura_release_authorization *authorization)
{
    if (!wire || wire_bytes != AURA_RELEASE_WIRE_BYTES || !authorization)
        return AURA_RELEASE_ARGUMENT;
    int result = context_valid(context);
    if (result) return result;
    result = receipt_valid(context, expected_receipt, receipt_bytes);
    if (result) return result;
    if (memcmp(wire, "RLS1", 4) || wire[4] != 1 || wire[5] != 1 ||
        wire[6] != 1 || wire[7] != 0 || !get_le(wire + 48, 8))
        return AURA_RELEASE_FORMAT;
    uint8_t tag[32];
    result = release_tag(context, wire, tag);
    int valid = !result && equal_tag(tag, wire + AURA_RELEASE_BODY_BYTES);
    wipe(tag, sizeof(tag));
    if (!valid) return AURA_RELEASE_TAG;
    if (memcmp(wire + 8, context->storage_incarnation, 16) ||
        memcmp(wire + 24, context->owner_id, 16) ||
        get_le(wire + 40, 8) != context->owner_generation) return AURA_RELEASE_CONTEXT;
    result = receipt_valid(context, wire + 56, AURA_RELEASE_ACK_BYTES);
    if (result) return result;
    if (memcmp(wire + 56, expected_receipt, AURA_RELEASE_ACK_BYTES))
        return AURA_RELEASE_RECEIPT;
    authorization->release_sequence = get_le(wire + 48, 8);
    memcpy(authorization->receipt, wire + 56, AURA_RELEASE_ACK_BYTES);
    return AURA_RELEASE_OK;
}

int aura_release_validate_next(uint64_t sequence, uint64_t persisted_floor)
{
    if (!sequence) return AURA_RELEASE_ARGUMENT;
    if (persisted_floor == UINT64_MAX) return AURA_RELEASE_EXHAUSTED;
    if (sequence <= persisted_floor) return AURA_RELEASE_REPLAY;
    if (sequence != persisted_floor + 1) return AURA_RELEASE_SEQUENCE_GAP;
    return AURA_RELEASE_OK;
}
