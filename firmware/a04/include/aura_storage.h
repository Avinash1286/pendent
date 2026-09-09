/* SPDX-License-Identifier: MIT */
#ifndef AURA_A04_STORAGE_H
#define AURA_A04_STORAGE_H
#include "aura_control.h"
#include "aura_journal.h"
#include "aura_release_auth.h"

#define AURA_STORAGE_HEADER_BYTES 352u
#define AURA_STORAGE_EXTENT_BYTES 44u
#define AURA_STORAGE_STATE_BYTES (AURA_STORAGE_HEADER_BYTES + AURA_NAND_BLOCKS * AURA_STORAGE_EXTENT_BYTES)
#define AURA_STORAGE_ALREADY_DONE 1
#define AURA_STORAGE_PENDING 2
#define AURA_STORAGE_ARGUMENT (-800)
#define AURA_STORAGE_STATE (-801)
#define AURA_STORAGE_BUSY (-802)
#define AURA_STORAGE_IDENTITY (-803)
#define AURA_STORAGE_UNSUPPORTED (-804)
#define AURA_STORAGE_CHANGED (-805)

struct aura_storage_io {
    struct aura_nand_io data;
    struct aura_control_io control;
    void *release_user;
    /* Privileged capability owned by this serialized storage owner. It must
     * independently exclude the control pair and factory/LUT-reserved blocks,
     * establish a fresh successful erase and preserve program-order guards.
     * It is invoked ONLY for a durably committed, authenticated, fenced grant.
     * There is no production audio-erase adapter yet; NULL keeps release inert. */
    int (*erase_released)(void *user, uint32_t block);
};

/* Caller-owned, single-threaded storage owner. All dependencies, the journal,
 * control context and buffer are private to this owner. Do not call low-level
 * writers concurrently or bypass its partitioned journal IO. This is not a
 * memory-protection boundary against malicious firmware or raw flash rollback.
 * Caller snapshot memory must remain alive and not alias any context/IO/key. */
struct aura_storage {
    struct aura_storage_io io;
    struct aura_control_config config;
    struct aura_release_auth_context authority;
    struct aura_journal *journal;
    struct aura_control *control;
    uint8_t *snapshot;
    size_t capacity, bytes;
    uint16_t progress;
    bool ready;
    int fault;
};

/* Both operations require explicitly trusted enrollment/context. Provision
 * additionally requires entirely blank readable data/control main areas; it
 * cannot reset existing authority, identities, audio or damaged source. */
int aura_storage_provision(struct aura_storage *storage, struct aura_storage_io io,
    const struct aura_control_config *config, const struct aura_release_auth_context *authority,
    struct aura_journal *journal, struct aura_control *control, uint8_t *snapshot, size_t capacity);
int aura_storage_open(struct aura_storage *storage, struct aura_storage_io io,
    const struct aura_control_config *config, const struct aura_release_auth_context *authority,
    struct aura_journal *journal, struct aura_control *control, uint8_t *snapshot, size_t capacity);

/* Durably reserve a never-reused generation, derive device/capture IDs, and
 * bind exactly that manifest to the next journal capture. Input IDs are ignored
 * in favor of trusted device identity and the reserved generation. Output is
 * unchanged on failure. It cannot overlap storage, journal, control or snapshot;
 * these aliases are rejected before IO. Input is copied before reload, and an
 * external caller may use the same object for settings and output.
 * Start the existing recorder with the returned manifest.
 * An unused reservation is burned, including after reboot/cancellation. */
int aura_storage_prepare_capture(struct aura_storage *storage,
    const struct aura_archive_manifest *settings, struct aura_archive_manifest *manifest);
int aura_storage_cancel_prepared(struct aura_storage *storage);

/* FINALIZED-only initial policy. Authenticate exact RLS1, independently verify
 * source and identity, and commit exact original extents before any erase.
 * Identical pending/done retries are idempotent; other replay/gaps are rejected.
 * A NULL erase capability refuses a new release without changing state. */
int aura_storage_request_release(struct aura_storage *storage, const uint8_t *wire, size_t bytes);
/* At most one released block erased per call. All grant extents remain fenced
 * until durable completion. A failure locks this context until cold open.
 * Reboot may repeat erasure of already-blank still-fenced released blocks.
 * Every surviving main page is checked for a contradictory intact identity
 * before erase, even past erased/torn gaps. This is not protection against raw
 * rollback or a replacement whose identities are all unrecognizably damaged. */
int aura_storage_release_step(struct aura_storage *storage);
int aura_storage_capture_id(const uint8_t device[16], const uint8_t incarnation[16],
                            uint64_t generation, uint8_t capture[16]);
#endif
