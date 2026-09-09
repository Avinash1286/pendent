/* SPDX-License-Identifier: MIT
 * RFC4231 HMAC-SHA256 vectors: https://www.rfc-editor.org/rfc/rfc4231
 * All RLS1 identities/keys below are PUBLIC SYNTHETIC TEST DATA. */
#include "aura_release_auth.h"
#include "aura_archive.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(value) do { if (!(value)) { \
    fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #value); exit(1); \
} } while (0)
static unsigned groups;
static void passed(const char *name) { ++groups; printf("PASS %s\n", name); }
static void put(uint8_t *p, uint64_t value, unsigned bytes)
{ for (unsigned i = 0; i < bytes; ++i) p[i] = (uint8_t)(value >> (8u * i)); }
static void crc(uint8_t *ack) { put(ack + 90, aura_archive_crc32(ack, 90), 4); }
static unsigned nibble(char c)
{
    if (c >= '0' && c <= '9') return (unsigned)(c - '0');
    if (c >= 'a' && c <= 'f') return (unsigned)(c - 'a' + 10);
    CHECK(0); return 0;
}
static void unhex(const char *hex, uint8_t *out, size_t bytes)
{
    CHECK(strlen(hex) == 2 * bytes);
    for (size_t i = 0; i < bytes; ++i)
        out[i] = (uint8_t)((nibble(hex[2 * i]) << 4) | nibble(hex[2 * i + 1]));
}
static void hex_print(const char *name, const uint8_t *data, size_t bytes)
{
    printf("%s ", name);
    for (size_t i = 0; i < bytes; ++i) printf("%02x", data[i]);
    puts("");
}
static struct aura_release_auth_context context(void)
{
    struct aura_release_auth_context c = {0};
    memset(c.device_id, 0x11, 16); memset(c.storage_incarnation, 0x33, 16);
    memset(c.owner_id, 0x44, 16);
    for (unsigned i = 0; i < 32; ++i) c.key[i] = (uint8_t)(i + 1);
    c.owner_generation = UINT64_C(0x0102030405060708);
    return c;
}
static void receipt(uint8_t ack[94], unsigned status)
{
    memset(ack, 0, 94); memcpy(ack, "ACK3", 4); ack[4] = 3; ack[5] = (uint8_t)status;
    memset(ack + 6, 0x11, 16); memset(ack + 22, 0x22, 16);
    put(ack + 38, 7, 4); put(ack + 42, 80, 8); put(ack + 50, 320, 8);
    for (unsigned i = 0; i < 32; ++i) ack[58 + i] = (uint8_t)(0x60 + i);
    crc(ack);
}
static void sign_wire(uint8_t wire[182], const uint8_t ack[94])
{
    struct aura_release_auth_context c = context();
    CHECK(!aura_release_sign(&c, 9, ack, 94, wire, 182));
}
static void retag(uint8_t wire[182])
{
    static const uint8_t domain[] = "AURA-A04-OWNER-RELEASE-v1";
    uint8_t message[sizeof(domain) + 150];
    struct aura_release_auth_context c = context();
    memcpy(message, domain, sizeof(domain)); memcpy(message + sizeof(domain), wire, 150);
    CHECK(!aura_release_hmac_sha256(c.key, 32, message, sizeof(message), wire + 150));
}
static int authenticate(const uint8_t *wire, size_t bytes, const uint8_t *ack)
{
    struct aura_release_auth_context c = context();
    struct aura_release_authorization out, before;
    memset(&out, 0xa5, sizeof(out)); memcpy(&before, &out, sizeof(out));
    int result = aura_release_authenticate(&c, wire, bytes, ack, 94, &out);
    if (result) CHECK(!memcmp(&out, &before, sizeof(out)));
    return result;
}
static void vector(const uint8_t *key, size_t kn, const uint8_t *message, size_t mn,
                   const char *expected)
{
    uint8_t tag[32], want[32]; size_t n = strlen(expected) / 2;
    CHECK(n == 16 || n == 32); unhex(expected, want, n);
    CHECK(!aura_release_hmac_sha256(key, kn, message, mn, tag));
    CHECK(!memcmp(tag, want, n));
}
static void rfc4231(void)
{
    uint8_t key[131], message[50];
    memset(key, 0x0b, 20);
    vector(key, 20, (const uint8_t *)"Hi There", 8,
           "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7");
    vector((const uint8_t *)"Jefe", 4, (const uint8_t *)"what do ya want for nothing?", 28,
           "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843");
    memset(key, 0xaa, 20); memset(message, 0xdd, 50);
    vector(key, 20, message, 50,
           "773ea91e36800e46854db8ebd09181a72959098b3ef8c122d9635514ced565fe");
    for (unsigned i = 0; i < 25; ++i) key[i] = (uint8_t)(i + 1);
    memset(message, 0xcd, 50);
    vector(key, 25, message, 50,
           "82558a389a443c0ea4cc819899f2083a85f0faa3e578f8077a2e3ff46729665b");
    passed("rfc4231_cases_1_to_4");
    memset(key, 0x0c, 20);
    /* RFC case5 specifies only a128-bit prefix. RLS1 still requires all32B. */
    vector(key, 20, (const uint8_t *)"Test With Truncation", 20,
           "a3b6167473100ee06e0c796c2955552b");
    memset(key, 0xaa, sizeof(key));
    static const uint8_t m6[] = "Test Using Larger Than Block-Size Key - Hash Key First";
    static const uint8_t m7[] = "This is a test using a larger than block-size key and a larger "
        "than block-size data. The key needs to be hashed before being used by the HMAC algorithm.";
    vector(key, sizeof(key), m6, sizeof(m6) - 1,
           "60e431591ee0b67f0d8a26aacbf5b77f8e0bc6213728c5140546040f0ee37f54");
    vector(key, sizeof(key), m7, sizeof(m7) - 1,
           "9b09ffa71b942fcb27635fbcd5b0e944bfdc63644f0713938a7f51535c3a35e2");
    passed("rfc4231_cases_5_to_7");
}
static void hmac_bounds(void)
{
    uint8_t key[257] = {0}, message[257] = {0}, tag[32], before[32];
    memset(tag, 0xa5, 32); memcpy(before, tag, 32);
    CHECK(aura_release_hmac_sha256(key, 257, message, 256, tag) == AURA_RELEASE_ARGUMENT);
    CHECK(!memcmp(before, tag, 32));
    CHECK(aura_release_hmac_sha256(key, 256, message, 257, tag) == AURA_RELEASE_ARGUMENT);
    CHECK(!memcmp(before, tag, 32));
    CHECK(aura_release_hmac_sha256(NULL, 1, message, 1, tag) == AURA_RELEASE_ARGUMENT);
    CHECK(aura_release_hmac_sha256(key, 1, NULL, 1, tag) == AURA_RELEASE_ARGUMENT);
    CHECK(aura_release_hmac_sha256(key, 1, message, 1, NULL) == AURA_RELEASE_ARGUMENT);
    CHECK(aura_release_hmac_sha256(key, SIZE_MAX, message, 1, tag) == AURA_RELEASE_ARGUMENT);
    CHECK(!aura_release_hmac_sha256(NULL, 0, NULL, 0, tag)); hex_print("EMPTY_HMAC", tag, 32);
    CHECK(!aura_release_hmac_sha256(key, 256, message, 256, tag));
    hex_print("MAX_HMAC", tag, 32);
    passed("hmac_bounds_empty_and_maximum");
}
static void roundtrip(void)
{
    struct aura_release_auth_context c = context();
    struct aura_release_authorization out;
    uint8_t ack[94], unaligned[183], repeated[182]; receipt(ack, 1);
    CHECK(!aura_release_sign(&c, 9, ack, 94, unaligned + 1, 182));
    CHECK(!aura_release_authenticate(&c, unaligned + 1, 182, ack, 94, &out));
    CHECK(out.release_sequence == 9 && !memcmp(out.receipt, ack, 94));
    CHECK(!aura_release_sign(&c, out.release_sequence, out.receipt, 94, repeated, 182));
    CHECK(!memcmp(repeated, unaligned + 1, 182));
    hex_print("INTEROP_RLS1", repeated, 182);
    receipt(ack, 2); sign_wire(repeated, ack); CHECK(!authenticate(repeated, 182, ack));
    /* This confirms syntax only, not whether an interrupted ACK was durable. */
    passed("terminal_roundtrip_unaligned_and_exact_bytes");
}
static void tamper(void)
{
    uint8_t ack[94], wire[182], changed[182]; receipt(ack, 1); sign_wire(wire, ack);
    for (unsigned i = 0; i < 182; ++i) for (unsigned bit = 0; bit < 8; ++bit) {
        memcpy(changed, wire, 182); changed[i] ^= (uint8_t)(1u << bit);
        CHECK(authenticate(changed, 182, ack) != AURA_RELEASE_OK);
    }
    passed("every_wire_bit_and_full_tag_rejected_after_tampering");
}
static void canonical_header(void)
{
    uint8_t ack[94], wire[182], changed[182]; receipt(ack, 1); sign_wire(wire, ack);
    for (unsigned i = 0; i < 8; ++i) {
        memcpy(changed, wire, 182); changed[i] ^= 0x80; retag(changed);
        CHECK(authenticate(changed, 182, ack) == AURA_RELEASE_FORMAT);
    }
    memcpy(changed, wire, 182); memset(changed + 48, 0, 8); retag(changed);
    CHECK(authenticate(changed, 182, ack) == AURA_RELEASE_FORMAT);
    passed("authenticated_noncanonical_headers_and_zero_sequence");
}
static void trusted_context(void)
{
    struct aura_release_auth_context c = context(), changed;
    struct aura_release_authorization out;
    uint8_t ack[94], wire[182]; receipt(ack, 1); sign_wire(wire, ack);
    for (unsigned i = 0; i < 32; ++i) {
        changed = c; changed.key[i] ^= 1;
        CHECK(aura_release_authenticate(&changed, wire, 182, ack, 94, &out) == AURA_RELEASE_TAG);
    }
    changed = c; changed.device_id[0] ^= 1;
    CHECK(aura_release_authenticate(&changed, wire, 182, ack, 94, &out) == AURA_RELEASE_CONTEXT);
    changed = c; changed.storage_incarnation[0] ^= 1;
    CHECK(aura_release_authenticate(&changed, wire, 182, ack, 94, &out) == AURA_RELEASE_CONTEXT);
    changed = c; changed.owner_id[0] ^= 1;
    CHECK(aura_release_authenticate(&changed, wire, 182, ack, 94, &out) == AURA_RELEASE_CONTEXT);
    changed = c; ++changed.owner_generation;
    CHECK(aura_release_authenticate(&changed, wire, 182, ack, 94, &out) == AURA_RELEASE_CONTEXT);
    /* A different valid context can sign its own wire, but not authorize ours. */
    CHECK(!aura_release_sign(&changed, 9, ack, 94, wire, 182));
    CHECK(aura_release_authenticate(&c, wire, 182, ack, 94, &out) == AURA_RELEASE_CONTEXT);
    passed("wrong_key_device_incarnation_owner_and_generation");
}
static void context_initialization(void)
{
    struct aura_release_auth_context c = context(), changed;
    uint8_t ack[94], wire[182]; receipt(ack, 1);
    changed = c; memset(changed.device_id, 0, 16);
    CHECK(aura_release_sign(&changed, 1, ack, 94, wire, 182) == AURA_RELEASE_CONTEXT);
    changed = c; memset(changed.storage_incarnation, 0, 16);
    CHECK(aura_release_sign(&changed, 1, ack, 94, wire, 182) == AURA_RELEASE_CONTEXT);
    changed = c; memset(changed.owner_id, 0, 16);
    CHECK(aura_release_sign(&changed, 1, ack, 94, wire, 182) == AURA_RELEASE_CONTEXT);
    changed = c; memset(changed.key, 0, 32);
    CHECK(aura_release_sign(&changed, 1, ack, 94, wire, 182) == AURA_RELEASE_CONTEXT);
    changed = c; changed.owner_generation = 0;
    CHECK(aura_release_sign(&changed, 1, ack, 94, wire, 182) == AURA_RELEASE_CONTEXT);
    passed("uninitialized_trusted_context_refused");
}
static void receipt_canonicality(void)
{
    struct aura_release_auth_context c = context();
    uint8_t ack[94], wire[182], changed[94], signed_bad[182];
    receipt(ack, 1); sign_wire(wire, ack);
    for (unsigned test = 0; test < 11; ++test) {
        memcpy(changed, ack, 94);
        switch (test) {
        case 0: changed[0] ^= 1; break;
        case 1: changed[4] = 2; break;
        case 2: changed[5] = 0; break;
        case 3: changed[5] = 3; break;
        case 4: memset(changed + 6, 0, 16); break;
        case 5: memset(changed + 22, 0, 16); break;
        case 6: put(changed + 38, 1000001, 4); break;
        case 7: put(changed + 42, (UINT64_C(1) << 40) + 1, 8); break;
        case 8: put(changed + 50, UINT64_C(1) << 63, 8); break;
        case 9: changed[6] ^= 1; break;
        case 10: changed[90] ^= 1; break;
        }
        if (test != 10) crc(changed);
        CHECK(aura_release_sign(&c, 9, changed, 94, signed_bad, 182) != AURA_RELEASE_OK);
        memcpy(signed_bad, wire, 182); memcpy(signed_bad + 56, changed, 94); retag(signed_bad);
        CHECK(authenticate(signed_bad, 182, ack) != AURA_RELEASE_OK);
        CHECK(authenticate(wire, 182, changed) != AURA_RELEASE_OK);
    }
    /* Inclusive ACK3 scalar wire bounds are syntax, not full archive validity. */
    memcpy(changed, ack, 94); put(changed + 38, 1000000, 4);
    put(changed + 42, UINT64_C(1) << 40, 8); put(changed + 50, INT64_MAX, 8); crc(changed);
    sign_wire(wire, changed); CHECK(!authenticate(wire, 182, changed));
    passed("terminal_ack_crc_identity_status_and_scalar_bounds");
}
static void exact_receipt(void)
{
    uint8_t ack[94], wire[182], changed[94], signed_changed[182]; receipt(ack, 1); sign_wire(wire, ack);
    const unsigned offsets[] = {22, 38, 42, 50, 58};
    for (unsigned i = 0; i < sizeof(offsets) / sizeof(offsets[0]); ++i) {
        memcpy(changed, ack, 94); changed[offsets[i]] ^= 1; crc(changed); sign_wire(signed_changed, changed);
        CHECK(authenticate(signed_changed, 182, ack) == AURA_RELEASE_RECEIPT);
        CHECK(authenticate(wire, 182, changed) == AURA_RELEASE_RECEIPT);
    }
    receipt(changed, 2); sign_wire(signed_changed, changed);
    CHECK(authenticate(signed_changed, 182, ack) == AURA_RELEASE_RECEIPT);
    passed("exact_committed_receipt_fields_and_terminal_status_match");
}
static void api_bounds(void)
{
    struct aura_release_auth_context c = context(); struct aura_release_authorization out;
    uint8_t ack[94], wire[183], original[182]; receipt(ack, 1); sign_wire(wire, ack);
    for (size_t n = 0; n < 182; ++n) CHECK(authenticate(wire, n, ack) == AURA_RELEASE_ARGUMENT);
    CHECK(authenticate(wire, 183, ack) == AURA_RELEASE_ARGUMENT);
    CHECK(authenticate(wire, SIZE_MAX, ack) == AURA_RELEASE_ARGUMENT);
    CHECK(aura_release_authenticate(NULL, wire, 182, ack, 94, &out) == AURA_RELEASE_ARGUMENT);
    CHECK(aura_release_authenticate(&c, NULL, 182, ack, 94, &out) == AURA_RELEASE_ARGUMENT);
    CHECK(aura_release_authenticate(&c, wire, 182, NULL, 94, &out) == AURA_RELEASE_ARGUMENT);
    CHECK(aura_release_authenticate(&c, wire, 182, ack, 93, &out) == AURA_RELEASE_ARGUMENT);
    CHECK(aura_release_authenticate(&c, wire, 182, ack, 95, &out) == AURA_RELEASE_ARGUMENT);
    CHECK(aura_release_authenticate(&c, wire, 182, ack, 94, NULL) == AURA_RELEASE_ARGUMENT);
    memcpy(original, wire, 182);
    CHECK(aura_release_sign(&c, 0, ack, 94, wire, 182) == AURA_RELEASE_ARGUMENT);
    CHECK(aura_release_sign(&c, 1, ack, 94, wire, 181) == AURA_RELEASE_ARGUMENT);
    CHECK(aura_release_sign(&c, 1, ack, 94, wire, 183) == AURA_RELEASE_ARGUMENT);
    CHECK(aura_release_sign(&c, 1, ack, 93, wire, 182) == AURA_RELEASE_ARGUMENT);
    CHECK(aura_release_sign(&c, 1, ack, 94, NULL, 182) == AURA_RELEASE_ARGUMENT);
    CHECK(!memcmp(original, wire, 182));
    passed("null_lengths_truncation_extension_and_unchanged_outputs");
}
static void sequences(void)
{
    struct aura_release_auth_context c = context(); struct aura_release_authorization out;
    uint8_t ack[94], wire[182]; receipt(ack, 1);
    CHECK(!aura_release_validate_next(1, 0));
    CHECK(!aura_release_validate_next(9, 8));
    CHECK(aura_release_validate_next(9, 9) == AURA_RELEASE_REPLAY);
    CHECK(aura_release_validate_next(8, 9) == AURA_RELEASE_REPLAY);
    CHECK(aura_release_validate_next(10, 8) == AURA_RELEASE_SEQUENCE_GAP);
    CHECK(aura_release_validate_next(0, 0) == AURA_RELEASE_ARGUMENT);
    CHECK(!aura_release_validate_next(UINT64_MAX, UINT64_MAX - 1));
    CHECK(aura_release_validate_next(UINT64_MAX, UINT64_MAX) == AURA_RELEASE_EXHAUSTED);
    CHECK(!aura_release_sign(&c, UINT64_MAX, ack, 94, wire, 182));
    CHECK(!aura_release_authenticate(&c, wire, 182, ack, 94, &out));
    CHECK(out.release_sequence == UINT64_MAX);
    sign_wire(wire, ack);
    CHECK(!aura_release_authenticate(&c, wire, 182, ack, 94, &out));
    CHECK(!aura_release_authenticate(&c, wire, 182, ack, 94, &out));
    CHECK(aura_release_validate_next(out.release_sequence, 9) == AURA_RELEASE_REPLAY);
    passed("freshness_replay_gap_overflow_and_no_implicit_persistence");
}
static void domain_separation(void)
{
    struct aura_release_auth_context c = context();
    const uint8_t domain[] = "AURA-A04-OWNER-RELEASE-v1";
    uint8_t ack[94], wire[182], message[256]; receipt(ack, 1); sign_wire(wire, ack);
    memcpy(message, domain, sizeof(domain) - 1); memcpy(message + sizeof(domain) - 1, wire, 150);
    CHECK(!aura_release_hmac_sha256(c.key, 32, message, sizeof(domain) - 1 + 150, wire + 150));
    CHECK(authenticate(wire, 182, ack) == AURA_RELEASE_TAG);
    memcpy(message, domain, sizeof(domain)); message[9] ^= 1;
    memcpy(message + sizeof(domain), wire, 150);
    CHECK(!aura_release_hmac_sha256(c.key, 32, message, sizeof(domain) + 150, wire + 150));
    CHECK(authenticate(wire, 182, ack) == AURA_RELEASE_TAG);
    CHECK(!aura_release_hmac_sha256(c.key, 32, wire, 150, wire + 150));
    CHECK(authenticate(wire, 182, ack) == AURA_RELEASE_TAG);
    passed("domain_purpose_and_included_nul_required");
}
int main(int argc, char **argv)
{
    if (argc == 3 && !strcmp(argv[1], "--authenticate")) {
        uint8_t wire[182], ack[94]; unhex(argv[2], wire, 182); receipt(ack, 1);
        CHECK(!authenticate(wire, 182, ack));
        puts("PYTHON_RLS1_ACCEPTED"); return 0;
    }
    CHECK(argc == 1);
    rfc4231(); hmac_bounds(); roundtrip(); tamper(); canonical_header();
    trusted_context(); context_initialization(); receipt_canonicality();
    exact_receipt(); api_bounds(); sequences(); domain_separation();
    printf("%u release-auth test groups passed\n", groups);
    return 0;
}
