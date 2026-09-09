/* SPDX-License-Identifier: MIT */
#ifndef AURA_A04_PAIRING_ZEPHYR_H
#define AURA_A04_PAIRING_ZEPHYR_H
#include <stdbool.h>
#include <stdint.h>

enum aura_pairing_event_kind {
    AURA_PAIRING_PASSKEY=0,
    AURA_PAIRING_CANCELLED,
    AURA_PAIRING_COMPLETE,
    AURA_PAIRING_EXPIRED
};
struct aura_pairing_event {
    enum aura_pairing_event_kind kind;
    uint32_t passkey;
    uint64_t window_generation, connection_generation;
};

/* Register dynamic passkey/auth-info callbacks once, before bt_enable. No
 * pairing window, radio, keys, ownership enrollment or automatic acceptance.
 * This module is the sole application writer of bt_set_bondable. */
int aura_pairing_init(void);
/* Caller must separately require trusted context and inactive capture. An
 * already-open window is idempotent and its absolute 60-second deadline does
 * not move. At most three accepted attempts; one exact connection at a time. */
int aura_pairing_open(void);
/* Invalidate display/window immediately and cancel/disconnect pending SMP.
 * Successfully completed bonds and owner keys are never deleted here. */
void aura_pairing_close(void);
bool aura_pairing_window_open(void);
/* Bounded owner-only drain. PASSKEY is returned only after current connection,
 * physical window and deadline revalidation. Print it only on trusted UART,
 * with exactly six digits. Other events never carry a passkey. */
bool aura_pairing_take(struct aura_pairing_event *event);
#endif
