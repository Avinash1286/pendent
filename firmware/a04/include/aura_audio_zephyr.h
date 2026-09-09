/* SPDX-License-Identifier: MIT */
#ifndef AURA_A04_AUDIO_ZEPHYR_H
#define AURA_A04_AUDIO_ZEPHYR_H
#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/sys/atomic.h>
#include "aura_recorder.h"

#define AURA_AUDIO_FRAMES 320u
#define AURA_AUDIO_RAW_BYTES (AURA_AUDIO_FRAMES * 2u * sizeof(int16_t))
#define AURA_AUDIO_DMA_BLOCKS 8u
#define AURA_AUDIO_QUEUE_BLOCKS 16u
#define AURA_AUDIO_WARMUP_BLOCKS 4u

enum aura_audio_mix { AURA_AUDIO_FIRST, AURA_AUDIO_SECOND, AURA_AUDIO_MEAN };
enum aura_audio_state { AURA_AUDIO_IDLE, AURA_AUDIO_STARTING, AURA_AUDIO_CAPTURING,
    AURA_AUDIO_STOPPING, AURA_AUDIO_FINALIZED, AURA_AUDIO_INTERRUPTED,
    AURA_AUDIO_FAILED, AURA_AUDIO_QUARANTINED };
enum aura_audio_fault { AURA_AUDIO_DRIVER = -600, AURA_AUDIO_PRIVACY = -601,
    AURA_AUDIO_QUEUE_FULL = -602, AURA_AUDIO_TIMEOUT = -603,
    AURA_AUDIO_BAD_BUFFER = -604, AURA_AUDIO_SEQUENCE = -605,
    AURA_AUDIO_POWER = -606 };

struct aura_audio_message {
    uint64_t epoch, source_offset;
    uint32_t sequence;
    int16_t pcm[AURA_AUDIO_FRAMES];
};

/* Two explicit owners, no hidden threads:
 * - one high-priority reader task repeatedly calls reader_step;
 * - one storage task owns begin/service and the recorder/journal/encoder.
 * Both tasks and this object must remain alive until driver quiescence.
 * Request-stop and privacy-cutoff may run concurrently. The permission callback
 * runs in thread context and must be bounded; the mic GPIO must be a native,
 * IRQ-safe GPIO if privacy_cutoff is called from an ISR. Never use an expander.
 * All other initialization/session transitions are externally serialized. */
struct aura_audio_zephyr {
    const struct device *dmic;
    struct gpio_dt_spec mic_enable;
    bool (*permitted)(void *);
    void *permission_user;
    struct aura_recorder *recorder;
    enum aura_audio_mix mix;
    struct k_mem_slab slab;
    struct k_msgq queue;
    uint8_t dma_memory[AURA_AUDIO_DMA_BLOCKS * AURA_AUDIO_RAW_BYTES] __aligned(4);
    char queue_memory[AURA_AUDIO_QUEUE_BLOCKS * sizeof(struct aura_audio_message)] __aligned(4);
    atomic_t state, stop_kind, fault, reader_enabled, reader_done, driver_quiescent;
    atomic_t stop_generation, privacy_generation;
    uint64_t epoch, expected_driver_sequence, published_samples, stop_started_ms;
    uint32_t published_blocks, warmup_remaining;
    uint32_t peak[2], clipped[2];
    bool initialized, ending;
};

int aura_audio_zephyr_init(struct aura_audio_zephyr *audio,
    const struct device *dmic, struct gpio_dt_spec mic_enable,
    bool (*permitted)(void *), void *permission_user,
    struct aura_recorder *recorder, enum aura_audio_mix mix);
/* Prepares storage before enabling power. No AURA pin assignment is implicit.
 * Currently requires unknown wall time (time_source=0, started_at_ms=0): a
 * request timestamp must not be presented as the first post-warmup sample.
 * External reader task must already exist and service reader_step promptly. */
int aura_audio_zephyr_begin(struct aura_audio_zephyr *audio,
    const struct aura_archive_manifest *manifest, uint64_t epoch);
/* Reader only. At most one blocking read (100ms bound) per call; stop cleanup
 * is nonblocking and polled until quiescent, with a 250ms quarantine deadline.
 * Call promptly again while active. It never encodes or touches NAND. */
int aura_audio_zephyr_reader_step(struct aura_audio_zephyr *audio);
/* Storage owner only. Consumes at most one FIFO message and services the
 * journal even without audio. Call while starting/recording/stopping, with
 * the codec's required stack. Physical/storage deadlines need measurement. */
int aura_audio_zephyr_service(struct aura_audio_zephyr *audio);
void aura_audio_zephyr_request_stop(struct aura_audio_zephyr *audio);
/* Immediate software power cut and sticky interrupted-capture request. The
 * separate physical switch must also disconnect the microphone rail itself. */
void aura_audio_zephyr_privacy_cutoff(struct aura_audio_zephyr *audio);
#endif
