/* SPDX-License-Identifier: Apache-2.0 */
#ifndef AURA_DMIC_HEALTH_H
#define AURA_DMIC_HEALTH_H

#include <stdbool.h>
#include <stdint.h>

struct device;

enum aura_dmic_fault {
	AURA_DMIC_FAULT_NONE = 0,
	AURA_DMIC_FAULT_OVERFLOW = 1u << 0,
	AURA_DMIC_FAULT_SLAB = 1u << 1,
	AURA_DMIC_FAULT_PREPARE = 1u << 2,
	AURA_DMIC_FAULT_HANDOFF = 1u << 3,
	AURA_DMIC_FAULT_RX_QUEUE = 1u << 4,
	AURA_DMIC_FAULT_OWNERSHIP = 1u << 5,
	AURA_DMIC_FAULT_RELEASE = 1u << 6,
	AURA_DMIC_FAULT_CLOCK = 1u << 7,
	AURA_DMIC_FAULT_START = 1u << 8,
	AURA_DMIC_FAULT_STOP = 1u << 9,
	AURA_DMIC_FAULT_INIT = 1u << 10,
};

struct aura_dmic_health {
	enum aura_dmic_fault faults;
	int first_error;
	uint32_t epoch;
	uint64_t completed_blocks;
	uint64_t delivered_blocks;
	uint64_t last_read_sequence;
	uint32_t queued_blocks;
	uint32_t slab_used_blocks;
	uint8_t owned_dma_buffers;
	bool configured;
	bool active;
	bool stopping;
	bool clock_pending;
	bool stopped;
	bool drained;
};

/* Only the AURA custom DMIC device is accepted (-ENOTSUP for another API).
 * One application owner serializes configure/trigger/read/reset. The dedicated
 * slab must not be shared with unrelated allocations. get() is an IRQ-safe,
 * coherent snapshot; call after every successful read to obtain that block's
 * last_read_sequence. Complete nrfx releases are numbered 1, 2, ... per epoch;
 * zero means no block has been delivered. These are observed callback counts,
 * not a hardware sample counter, measured rate, or proof of physical continuity.
 * A fault can arrive after any snapshot; check again before accepting a block.
 *
 * STOP is asynchronous: active becomes false immediately, stopping remains true
 * through pending clock startup / DMA return / clock release. Queued full blocks
 * remain readable, including after a fault, and every returned block must be
 * freed by the caller. Partial buffers returned during STOP are discarded.
 *
 * Use a bounded application deadline: STOP, read with finite/no-wait timeouts
 * and free queued blocks, then poll health until stopped && drained and both
 * owned_dma_buffers and slab_used_blocks are zero. Timeout is a failed shutdown,
 * never permission to reuse the slab, reset, configure, or restart. Independently
 * cut microphone power for privacy; a sleep alone does not establish quiescence.
 */
int aura_dmic_health_get(const struct device *dev, struct aura_dmic_health *health);

/* Explicitly clear sticky faults/counters and increment epoch, only after fully
 * stopped and drained (including caller-owned blocks). Returns -EBUSY otherwise.
 * Configuration is retained. Neither START nor configure silently clears faults.
 */
int aura_dmic_health_reset(const struct device *dev);

#endif
