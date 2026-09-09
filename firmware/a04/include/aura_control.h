/* SPDX-License-Identifier: MIT */
#ifndef AURA_A04_CONTROL_H
#define AURA_A04_CONTROL_H
#include "aura_nand.h"

#define AURA_CONTROL_MAX_BYTES 49152u
#define AURA_CONTROL_BODY_BYTES 1920u
#define AURA_CONTROL_BAD_ARGUMENT (-600)
#define AURA_CONTROL_UNPROVISIONED (-601)
#define AURA_CONTROL_CORRUPT (-602)
#define AURA_CONTROL_INCOMPLETE (-603)
#define AURA_CONTROL_CONFLICT (-604)
#define AURA_CONTROL_CAPACITY (-605)
#define AURA_CONTROL_READ_ONLY (-606)
#define AURA_CONTROL_EXHAUSTED (-607)

struct aura_control_config {
    uint16_t blocks[2];
    uint8_t domain[16]; /* Explicit nonzero storage incarnation, not a secret. */
};

struct aura_control_io {
    struct aura_nand_io nand;
    void *erase_user;
    /* Separately privileged CONTROL-block erase, never an audio erase API.
     * Integration must independently restrict this to config.blocks, serialize
     * the whole NAND operation, check status/full ECC-clean FF readback, and
     * establish the backend's fresh-erase program permission. This primitive
     * also checks the target and readback. The W25N adapter supplies a separate
     * configured-pair capability; its ordinary audio erase remains blank-only.
     * A nonzero result remains failure even if all bytes read FF afterward. */
    int (*erase_control)(void *user, uint32_t block);
};

/* One serialized owner, no heap or concurrency machinery. Config/context must
 * remain private to that owner. Public hashes detect accidental damage and
 * establish snapshot linkage; they are NOT authentication or anti-rollback. */
struct aura_control {
    struct aura_control_io io;
    struct aura_control_config config;
    uint64_t generation, reads, corrected_reads, programs, erases;
    uint32_t bytes;
    uint16_t current;
    uint8_t digest[32];
    bool ready;
    int fault;
    uint8_t page[2048], verify[2048];
};

/* Read-only open: scan only the two explicitly configured blocks. A torn or
 * ambiguous newer candidate fails closed: no old authority/floor is returned.
 * No automatic format, repair, or fallback to generation zero. */
int aura_control_open(struct aura_control *control, struct aura_control_io io,
                      const struct aura_control_config *config);
/* Explicit initial provisioning, only if BOTH complete main areas are readable
 * ECC-clean FF. Requires erase_control; does not repair damaged authority. */
int aura_control_provision(struct aura_control *control, struct aura_control_io io,
                           const struct aura_control_config *config,
                           const uint8_t *snapshot, size_t bytes);
/* Output is usable only on zero return; *bytes is zero on failure except when
 * the count pointer itself is invalid/aliased (then nothing is written there).
 * Caller output and count storage must not overlap each other or control.
 * Both slots are rechecked before output; a stale context must reopen. */
int aura_control_load(struct aura_control *control, uint8_t *out, size_t capacity,
                      size_t *bytes);
/* Atomic whole-snapshot replacement. Input must remain stable for this call and
 * must not alias control. Nonzero may mean a new snapshot reached media; reopen
 * to establish the state. Never retry programming an uncertain page. */
int aura_control_store(struct aura_control *control, const uint8_t *snapshot,
                       size_t bytes);
#endif
