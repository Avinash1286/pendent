/* SPDX-License-Identifier: MIT */
#ifndef AURA_A04_GATT_ZEPHYR_H
#define AURA_A04_GATT_ZEPHYR_H
#include "aura_transfer.h"

#define AURA_GATT_AUTH_MAX 160u
#define AURA_GATT_FRAME_MAX 20u

/* Immutable copies, not bt_conn pointers or ownership credentials. A generation
 * changes on connection, security failure/loss, or CCC loss. Zero means no live
 * generation. A caller must not cache a trusted grant across that change. */
struct aura_gatt_link {
    uint64_t generation;
    uint16_t mtu;
    bool connected, secure_l4, subscribed, transfer_ready;
};
struct aura_gatt_auth_frame {
    uint64_t generation;
    uint8_t bytes, data[AURA_GATT_FRAME_MAX];
};
enum aura_gatt_authorization { AURA_GATT_DENIED=0, AURA_GATT_GRANTED=1 };
struct aura_gatt_owner_gate {
    uint64_t connection_generation;
    enum aura_gatt_authorization authorization;
    /* Local capture wins before transfer work. This cancels volatile transfer
     * work while retaining authenticated session/transaction high-water. */
    bool capture_preempt;
};

/* Call once before bt_enable/advertising. This registers the static service but
 * does not enable Bluetooth, advertise, pair, load keys or initialize transfer. */
void aura_gatt_init(void);
void aura_gatt_link_snapshot(struct aura_gatt_link *out);
struct bt_conn;
/* Pairing callbacks must bind their exact pointer, never another link snapshot. */
uint64_t aura_gatt_connection_generation(struct bt_conn *conn);

/* One serialized owner consumes auth writes and publishes immutable read data.
 * Auth characteristic 7f520003-1b15-4f0d-8fe5-3f942170a004 requires L4, accepts
 * only WRITE-with-response envelopes 4..20 and reads at most 160 bytes. These
 * APIs do not interpret credentials or grant access. No keys in diagnostics. */
bool aura_gatt_auth_take(struct aura_gatt_auth_frame *out);
int aura_gatt_auth_publish(uint64_t generation, const uint8_t *data, size_t bytes);
/* Absolute monotonic k_uptime_get() deadline from the TRUSTED proof provider.
 * Expiry closes the generation independently of storage-owner progress. Zero/
 * past times revoke; a positive deadline must be within INT32_MAX ms of now.
 * Only verified provider transitions may extend it; retries do not renew TTL. */
int aura_gatt_auth_deadline(uint64_t generation, int64_t absolute_ms);

/* ONLY this method calls aura_transfer APIs, all on the storage owner's thread.
 * Supply the separately verified session-provider result on EVERY tick. DENIED,
 * generation mismatch, or lost link ends the engine session before processing.
 * Drains completion, admits at most one mailbox command, steps at most once.
 * Returns 0 normally; an engine/admission error closes the link and returns that
 * exact negative result. It never manufactures a wire response. transfer must
 * be initialized by this same owner before a GRANTED tick. No NAND work occurs
 * in RX, connection, security, CCC, notification callbacks or radio workqueue. */
int aura_gatt_owner_tick(struct aura_transfer *transfer,
                         const struct aura_gatt_owner_gate *gate);

/* Owner requests, scheduled onto radio work. Disconnect invalidates admission
 * synchronously; security initiation alone never grants archive access. Pairing
 * window/passkey policy and authorization expiry belong to the application. */
void aura_gatt_disconnect(uint64_t generation);
void aura_gatt_request_security(uint64_t generation);
size_t aura_gatt_static_bytes(void);
#endif
