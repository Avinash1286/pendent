/* SPDX-License-Identifier: MIT */
#include "aura_audio_zephyr.h"
#include "aura_dmic_health.h"
#include <zephyr/audio/dmic.h>
#include <zephyr/irq.h>
#include <errno.h>
#include <limits.h>
#include <string.h>

static uint64_t now_ms(void) { return (uint64_t)k_uptime_get(); }

static void latch_fault(struct aura_audio_zephyr *a, int reason)
{
    (void)atomic_cas(&a->fault, 0, reason ? reason : AURA_AUDIO_DRIVER);
    atomic_set(&a->stop_kind, 2);
}

static void power_off(struct aura_audio_zephyr *a)
{
    if (gpio_pin_set_dt(&a->mic_enable, 0)) latch_fault(a, AURA_AUDIO_POWER);
}

static bool allowed(struct aura_audio_zephyr *a)
{
    return !atomic_get(&a->fault) && a->permitted(a->permission_user);
}

static int guarded_power_on(struct aura_audio_zephyr *a)
{
    /* Permission may block, so check it outside the short native-GPIO section.
     * A concurrent cutoff latches stop before/after this section and remains
     * the last writer. This single-core adapter must not use an expander. */
    if (!a->permitted(a->permission_user)) return -EACCES;
    unsigned int key = irq_lock();
    int r = atomic_get(&a->stop_kind) || atomic_get(&a->fault) ? -ECANCELED :
        gpio_pin_set_dt(&a->mic_enable, 1);
    irq_unlock(key);
    return r;
}

static bool terminal_state(atomic_val_t state)
{
    return state == AURA_AUDIO_IDLE || state == AURA_AUDIO_FINALIZED ||
        state == AURA_AUDIO_INTERRUPTED || state == AURA_AUDIO_FAILED;
}

int aura_audio_zephyr_init(struct aura_audio_zephyr *a,
    const struct device *dmic, struct gpio_dt_spec mic,
    bool (*permitted)(void *), void *user, struct aura_recorder *recorder,
    enum aura_audio_mix mix)
{
    if (!a || !dmic || !permitted || !recorder || mix > AURA_AUDIO_MEAN ||
        mix < AURA_AUDIO_FIRST || !device_is_ready(dmic) || !gpio_is_ready_dt(&mic))
        return -EINVAL;
    struct aura_dmic_health health;
    int r = aura_dmic_health_get(dmic, &health);
    if (r) return r; /* A stock driver cannot prove the required health contract. */
    if (!health.stopped || !health.drained || health.owned_dma_buffers ||
        health.slab_used_blocks) return -EBUSY;
    memset(a, 0, sizeof(*a));
    a->dmic = dmic; a->mic_enable = mic; a->permitted = permitted;
    a->permission_user = user; a->recorder = recorder; a->mix = mix;
    r = k_mem_slab_init(&a->slab, a->dma_memory, AURA_AUDIO_RAW_BYTES, AURA_AUDIO_DMA_BLOCKS);
    if (r) return r;
    k_msgq_init(&a->queue, a->queue_memory, sizeof(struct aura_audio_message),
        AURA_AUDIO_QUEUE_BLOCKS);
    r = gpio_pin_configure_dt(&a->mic_enable, GPIO_OUTPUT_INACTIVE);
    if (r) return r;
    atomic_set(&a->reader_done, 1);
    atomic_set(&a->driver_quiescent, 1);
    a->initialized = true;
    return 0;
}

int aura_audio_zephyr_begin(struct aura_audio_zephyr *a,
    const struct aura_archive_manifest *manifest, uint64_t epoch)
{
    if (!a || !a->initialized || !manifest || manifest->time_source ||
        manifest->started_at_ms) return -EINVAL;
    atomic_val_t stop_generation = atomic_get(&a->stop_generation);
    atomic_val_t privacy_generation = atomic_get(&a->privacy_generation);
    if (!terminal_state(atomic_get(&a->state)) || !atomic_get(&a->reader_done) ||
        !atomic_get(&a->driver_quiescent) || k_msgq_num_used_get(&a->queue) ||
        k_mem_slab_num_used_get(&a->slab)) return -EBUSY;
    if (!a->permitted(a->permission_user)) return -EACCES;
    int r = aura_dmic_health_reset(a->dmic);
    if (r) return r;
    atomic_clear(&a->fault); atomic_clear(&a->stop_kind);
    if (privacy_generation != atomic_get(&a->privacy_generation)) latch_fault(a, AURA_AUDIO_PRIVACY);
    else if (stop_generation != atomic_get(&a->stop_generation))
        (void)atomic_cas(&a->stop_kind, 0, 1);
    atomic_set(&a->state, AURA_AUDIO_STARTING);
    a->epoch = epoch; a->expected_driver_sequence = 0;
    a->published_samples = 0; a->published_blocks = 0;
    a->warmup_remaining = AURA_AUDIO_WARMUP_BLOCKS; a->ending = false;
    memset(a->peak, 0, sizeof(a->peak)); memset(a->clipped, 0, sizeof(a->clipped));
    r = aura_recorder_start(a->recorder, manifest, epoch, now_ms());
    if (r) { atomic_set(&a->state, AURA_AUDIO_FAILED); return r; }
    struct pcm_stream_cfg stream = {
        .pcm_rate = 16000, .pcm_width = 16, .block_size = AURA_AUDIO_RAW_BYTES,
        .mem_slab = &a->slab };
    struct dmic_cfg cfg = {
        .io = { .min_pdm_clk_freq = 1280000, .max_pdm_clk_freq = 1280000,
            .min_pdm_clk_dc = 40, .max_pdm_clk_dc = 60 },
        .streams = &stream,
        .channel = { .req_num_streams = 1, .req_num_chan = 2,
            .req_chan_map_lo = dmic_build_channel_map(0, 0, PDM_CHAN_LEFT) |
                dmic_build_channel_map(1, 0, PDM_CHAN_RIGHT) } };
    r = dmic_configure(a->dmic, &cfg);
    if (!r && (cfg.channel.act_num_chan != 2 || cfg.channel.act_num_streams != 1 ||
        cfg.channel.act_chan_map_hi || cfg.channel.act_chan_map_lo != cfg.channel.req_chan_map_lo))
        r = -ENOTSUP;
    if (!r && !allowed(a)) r = -EACCES;
    if (!r) r = guarded_power_on(a);
    if (!r) {
        k_msleep(50); /* Power settling is separate from clocked audio warmup. */
        if (!allowed(a) || atomic_get(&a->stop_kind)) r = -ECANCELED;
    }
    if (!r) r = dmic_trigger(a->dmic, DMIC_TRIGGER_START);
    if (r) {
        latch_fault(a, r); power_off(a);
        /* A failed start may still have an asynchronous clock request/stop. */
        a->ending = true; a->stop_started_ms = now_ms();
        (void)dmic_trigger(a->dmic, DMIC_TRIGGER_STOP);
        atomic_set(&a->state, AURA_AUDIO_STOPPING);
    }
    atomic_clear(&a->reader_done); atomic_clear(&a->driver_quiescent);
    atomic_set(&a->reader_enabled, 1);
    return r;
}

void aura_audio_zephyr_request_stop(struct aura_audio_zephyr *a)
{
    if (a && a->initialized) {
        atomic_inc(&a->stop_generation);
        (void)atomic_cas(&a->stop_kind, 0, 1);
    }
}

void aura_audio_zephyr_privacy_cutoff(struct aura_audio_zephyr *a)
{
    if (!a || !a->initialized) return;
    unsigned int key = irq_lock();
    atomic_inc(&a->privacy_generation);
    atomic_inc(&a->stop_generation);
    latch_fault(a, AURA_AUDIO_PRIVACY);
    power_off(a);
    irq_unlock(key);
}

static void begin_stop(struct aura_audio_zephyr *a)
{
    if (a->ending) return;
    a->ending = true; a->stop_started_ms = now_ms();
    atomic_set(&a->state, AURA_AUDIO_STOPPING);
    if (dmic_trigger(a->dmic, DMIC_TRIGGER_STOP)) latch_fault(a, AURA_AUDIO_DRIVER);
    power_off(a);
}

static bool owns_buffer(struct aura_audio_zephyr *a, void *p)
{
    uintptr_t base = (uintptr_t)a->dma_memory, value = (uintptr_t)p;
    return value >= base && value < base + sizeof(a->dma_memory) &&
        (value - base) % AURA_AUDIO_RAW_BYTES == 0;
}

static int accept_buffer(struct aura_audio_zephyr *a, void *raw, size_t bytes,
    const struct aura_dmic_health *health)
{
    if (!owns_buffer(a, raw)) { latch_fault(a, AURA_AUDIO_BAD_BUFFER); return -EINVAL; }
    int r = 0;
    if (bytes != AURA_AUDIO_RAW_BYTES) { r = AURA_AUDIO_BAD_BUFFER; goto release; }
    if (health->faults) { r = AURA_AUDIO_DRIVER; goto release; }
    if (health->last_read_sequence != a->expected_driver_sequence + 1) {
        r = AURA_AUDIO_SEQUENCE; goto release;
    }
    a->expected_driver_sequence = health->last_read_sequence;
    if (atomic_get(&a->stop_kind) == 2 || !a->permitted(a->permission_user)) {
        r = AURA_AUDIO_PRIVACY; goto release;
    }
    if (a->warmup_remaining) { --a->warmup_remaining; goto release; }
    struct aura_audio_message msg = { .epoch = a->epoch,
        .source_offset = a->published_samples, .sequence = a->published_blocks };
    const int16_t *pcm = raw;
    for (size_t i = 0; i < AURA_AUDIO_FRAMES; ++i) {
        int32_t first = pcm[2 * i], second = pcm[2 * i + 1];
        int32_t values[2] = { first, second };
        for (unsigned ch = 0; ch < 2; ++ch) {
            uint32_t peak = (uint32_t)(values[ch] < 0 ? -values[ch] : values[ch]);
            if (peak > a->peak[ch]) a->peak[ch] = peak;
            if ((values[ch] == INT16_MIN || values[ch] == INT16_MAX) && a->clipped[ch] < UINT32_MAX)
                ++a->clipped[ch];
        }
        msg.pcm[i] = (int16_t)(a->mix == AURA_AUDIO_FIRST ? first :
            a->mix == AURA_AUDIO_SECOND ? second : (first + second) / 2);
    }
    if (!a->permitted(a->permission_user)) { r = AURA_AUDIO_PRIVACY; goto release; }
    if (a->published_blocks == UINT32_MAX ||
        a->published_samples > UINT64_MAX - AURA_AUDIO_FRAMES) {
        r = AURA_AUDIO_SEQUENCE; goto release;
    }
    /* Publishing defines the privacy cutoff boundary. Keep the final health /
     * cutoff check, nonblocking copy, and watermark together on this single
     * core. A cutoff delivered after unlock can only retain this earlier block.
     * Neither the permission callback nor PCM conversion runs with IRQs locked. */
    unsigned int key = irq_lock();
    struct aura_dmic_health current;
    if (atomic_get(&a->stop_kind) == 2 || atomic_get(&a->fault))
        r = AURA_AUDIO_PRIVACY;
    else if (aura_dmic_health_get(a->dmic, &current) || current.faults)
        r = AURA_AUDIO_DRIVER;
    else if (k_msgq_put(&a->queue, &msg, K_NO_WAIT))
        r = AURA_AUDIO_QUEUE_FULL;
    else {
        ++a->published_blocks; a->published_samples += AURA_AUDIO_FRAMES;
        if (!a->ending) atomic_set(&a->state, AURA_AUDIO_CAPTURING);
    }
    irq_unlock(key);
release:
    k_mem_slab_free(&a->slab, raw);
    if (r) latch_fault(a, r);
    return r;
}

static int drain_stop(struct aura_audio_zephyr *a)
{
    struct aura_dmic_health h;
    for (unsigned i = 0; i < AURA_AUDIO_DMA_BLOCKS; ++i) {
        void *buffer = NULL; size_t bytes = 0;
        int r = dmic_read(a->dmic, 0, &buffer, &bytes, 0);
        if (r) break;
        if (aura_dmic_health_get(a->dmic, &h)) { latch_fault(a, AURA_AUDIO_DRIVER); memset(&h, 0, sizeof(h)); h.faults = 1; }
        (void)accept_buffer(a, buffer, bytes, &h);
    }
    int r = aura_dmic_health_get(a->dmic, &h);
    if (r || h.faults) latch_fault(a, AURA_AUDIO_DRIVER);
    if (!r && h.stopped && h.drained && !h.owned_dma_buffers &&
        !k_mem_slab_num_used_get(&a->slab)) {
        atomic_set(&a->driver_quiescent, 1);
        atomic_clear(&a->reader_enabled); atomic_set(&a->reader_done, 1);
        return 0;
    }
    if (now_ms() - a->stop_started_ms >= 250) {
        latch_fault(a, AURA_AUDIO_TIMEOUT); power_off(a);
        atomic_set(&a->state, AURA_AUDIO_QUARANTINED);
        atomic_clear(&a->reader_enabled); atomic_set(&a->reader_done, 1);
        /* Keep the object/slab alive; never recycle memory still owned by DMA. */
        return AURA_AUDIO_TIMEOUT;
    }
    return -EINPROGRESS;
}

int aura_audio_zephyr_reader_step(struct aura_audio_zephyr *a)
{
    if (!a || !a->initialized) return -EINVAL;
    if (!atomic_get(&a->reader_enabled)) return 0;
    if (a->ending) return drain_stop(a);
    if (!allowed(a)) latch_fault(a, AURA_AUDIO_PRIVACY);
    if (atomic_get(&a->stop_kind) == 2 ||
        (atomic_get(&a->stop_kind) == 1 && a->warmup_remaining)) {
        begin_stop(a); return drain_stop(a);
    }
    struct aura_dmic_health h;
    if (aura_dmic_health_get(a->dmic, &h) || h.faults) {
        latch_fault(a, AURA_AUDIO_DRIVER); begin_stop(a); return drain_stop(a);
    }
    void *buffer = NULL; size_t bytes = 0;
    int r = dmic_read(a->dmic, 0, &buffer, &bytes, 100);
    if (r) latch_fault(a, AURA_AUDIO_TIMEOUT);
    else {
        if (aura_dmic_health_get(a->dmic, &h)) { memset(&h, 0, sizeof(h)); h.faults = 1; }
        r = accept_buffer(a, buffer, bytes, &h);
    }
    if (atomic_get(&a->stop_kind)) begin_stop(a);
    return r;
}

int aura_audio_zephyr_service(struct aura_audio_zephyr *a)
{
    if (!a || !a->initialized) return -EINVAL;
    atomic_val_t state = atomic_get(&a->state);
    if (terminal_state(state)) return 0;
    struct aura_audio_message msg;
    int r = 0;
    if (k_msgq_get(&a->queue, &msg, K_NO_WAIT) == 0 &&
        a->recorder->state == AURA_RECORDER_RECORDING) {
        struct aura_recorder_block block = { .epoch = msg.epoch, .sequence = msg.sequence,
            .source_offset = msg.source_offset, .pcm = msg.pcm, .samples = AURA_AUDIO_FRAMES };
        size_t consumed = 0;
        r = aura_recorder_consume(a->recorder, &block, now_ms(), &consumed);
        if (!r && consumed != AURA_AUDIO_FRAMES) r = AURA_RECORDER_GAP;
        if (r) { latch_fault(a, r); power_off(a); }
    }
    if (!r && a->recorder->state == AURA_RECORDER_RECORDING)
        r = aura_recorder_service(a->recorder, now_ms());
    if (r) { latch_fault(a, r); power_off(a); }
    if (!atomic_get(&a->reader_done) || k_msgq_num_used_get(&a->queue)) return r;
    int fault = (int)atomic_get(&a->fault);
    bool quiescent = atomic_get(&a->driver_quiescent) != 0;
    if (a->recorder->state == AURA_RECORDER_RECORDING) {
        r = fault || !quiescent ? aura_recorder_interrupt(a->recorder, a->epoch,
            fault ? fault : AURA_AUDIO_DRIVER, now_ms()) :
            aura_recorder_stop(a->recorder, a->epoch, a->published_samples, now_ms());
    }
    atomic_set(&a->state, !quiescent ? AURA_AUDIO_QUARANTINED :
        a->recorder->state == AURA_RECORDER_FINALIZED ? AURA_AUDIO_FINALIZED :
        a->recorder->state == AURA_RECORDER_INTERRUPTED ? AURA_AUDIO_INTERRUPTED : AURA_AUDIO_FAILED);
    return r;
}
