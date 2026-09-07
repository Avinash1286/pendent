#ifndef AURA_H
#define AURA_H
#include <stdint.h>
#include <stdbool.h>
#include <zephyr/kernel.h>
#include "journal.h"
extern struct aj_store aura_store;
extern struct k_mutex aura_store_lock;
extern volatile uint8_t aura_state;
extern volatile bool aura_privacy, aura_charge_allowed;
extern volatile uint16_t aura_battery_mv;
uint64_t aura_time(void);
void aura_set_time(uint64_t unix_seconds);
int aura_bluetooth_init(void);
void aura_pairing_window(void);
int aura_format(void);
bool aura_capture_pending(void);
#endif
