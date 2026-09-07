/* SPDX-License-Identifier: MIT */
#include "aura.h"
#include "nand.h"
#include "gestures.h"
#include "pcm.h"
#include "maintenance.h"
#include <zephyr/settings/settings.h>
#include <zephyr/audio/dmic.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/drivers/watchdog.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/reboot.h>
#include <zephyr/fatal.h>
#include <errno.h>
#include <string.h>
struct aj_store aura_store;
K_MUTEX_DEFINE(aura_store_lock);
volatile uint8_t aura_state;
volatile bool aura_privacy = true, aura_charge_allowed;
volatile uint16_t aura_battery_mv;
static const struct gpio_dt_spec mic = GPIO_DT_SPEC_GET(DT_PATH(zephyr_user), mic_enable_gpios),
                                 record = GPIO_DT_SPEC_GET(DT_PATH(zephyr_user), record_gpios),
                                 privacy =
                                     GPIO_DT_SPEC_GET(DT_PATH(zephyr_user), privacy_off_gpios),
                                 charge =
                                     GPIO_DT_SPEC_GET(DT_PATH(zephyr_user), charge_allow_gpios),
                                 haptic =
                                     GPIO_DT_SPEC_GET(DT_PATH(zephyr_user), haptic_enable_gpios);
static const struct device *pdm = DEVICE_DT_GET(DT_NODELABEL(pdm0)),
                           *i2c = DEVICE_DT_GET(DT_NODELABEL(i2c0)),
                           *wdt = DEVICE_DT_GET(DT_NODELABEL(wdt0));
static uint64_t unix_anchor;
static int64_t uptime_anchor;
static struct k_spinlock time_lock;
static atomic_t wanted, storage_ready, mark_pending;
static bool format_intent;
static uint32_t id_floor = 1;
static int64_t maintenance_until;
static bool haptic_ready;
static int watchdog_channel = -1;
static atomic_t audio_heartbeat;
static struct gpio_callback privacy_cb;
K_MEM_SLAB_DEFINE_STATIC(audio_slab, 2560, 8, 4);
K_THREAD_STACK_DEFINE(audio_stack, 4096);
static struct k_thread audio_thread;
bool aura_capture_pending(void)
{
    return atomic_get(&wanted) != 0;
}
static int load_maintenance(const char *key, size_t len, settings_read_cb read, void *arg)
{
    if (!strcmp(key, "nextid") && len == 4) {
        uint8_t bytes[4];
        if (read(arg, bytes, 4) != 4)
            return -EIO;
        id_floor = sys_get_le32(bytes);
        return id_floor ? 0 : -EINVAL;
    }
    if (strcmp(key, "erase") || len != 1)
        return -ENOENT;
    uint8_t value = 0;
    int r = read(arg, &value, 1);
    if (r != 1)
        return -EIO;
    format_intent = value != 0;
    return 0;
}
SETTINGS_STATIC_HANDLER_DEFINE(aura_persistence, "aura", NULL, load_maintenance, NULL, NULL);
static int save_intent(bool enabled)
{
    if (aura_store.next_id > id_floor)
        id_floor = aura_store.next_id;
    if (aura_store.next_id < id_floor)
        aura_store.next_id = id_floor;
    uint8_t id[4];
    sys_put_le32(id_floor, id);
    int r = settings_save_one("aura/nextid", id, 4);
    if (r)
        return r;
    uint8_t v = enabled ? 1 : 0;
    r = settings_save_one("aura/erase", &v, 1);
    if (!r)
        format_intent = enabled;
    return r;
}
int aura_format(void)
{
    /* Called with the storage mutex held; a new physical gesture is required per attempt. */
    if (!atomic_get(&storage_ready) || aura_store.fault || aura_state == 1 || aura_state == 2 ||
        atomic_get(&wanted) || k_uptime_get() >= maintenance_until ||
        !aura_all_deleted(&aura_store))
        return -EPERM;
    maintenance_until = 0;
    atomic_clear(&storage_ready);
    aura_state = 2;
    gpio_pin_set_dt(&charge, 0);
    aura_charge_allowed = false;
    int r = aura_erase_run(&aura_store,
                           (struct aura_maintenance_io){save_intent, aura_nand_erase_block}, false);
    if (r) {
        aura_store.fault = true;
        aura_state = 4;
    } else {
        atomic_set(&storage_ready, 1);
        aura_state = aura_privacy ? 3 : 0;
    }
    return r;
}
uint64_t aura_time(void)
{
    k_spinlock_key_t k = k_spin_lock(&time_lock);
    uint64_t t = unix_anchor ? unix_anchor + (k_uptime_get() - uptime_anchor) / 1000 : 0;
    k_spin_unlock(&time_lock, k);
    return t;
}
void aura_set_time(uint64_t time)
{
    k_spinlock_key_t k = k_spin_lock(&time_lock);
    unix_anchor = time;
    uptime_anchor = k_uptime_get();
    k_spin_unlock(&time_lock, k);
}
static void fail_off(void)
{
    gpio_pin_set_dt(&mic, 0);
    gpio_pin_set_dt(&charge, 0);
    aura_charge_allowed = false;
    atomic_clear(&wanted);
}
void k_sys_fatal_error_handler(unsigned int reason, const struct arch_esf *esf)
{
    ARG_UNUSED(reason);
    ARG_UNUSED(esf);
    if (gpio_is_ready_dt(&mic))
        gpio_pin_set_dt(&mic, 0);
    if (gpio_is_ready_dt(&charge))
        gpio_pin_set_dt(&charge, 0);
    if (gpio_is_ready_dt(&haptic))
        gpio_pin_set_dt(&haptic, 0);
    sys_reboot(SYS_REBOOT_COLD);
}
static void privacy_interrupt(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
{
    ARG_UNUSED(dev);
    ARG_UNUSED(cb);
    ARG_UNUSED(pins);
    if (gpio_pin_get_dt(&privacy) != 0) {
        gpio_pin_set_dt(&mic, 0);
        atomic_clear(&wanted);
        aura_privacy = true;
    }
}
static int gauge_read(void)
{
    uint8_t bytes[2];
    int r = i2c_burst_read(i2c, 0x36, 0x02, bytes, 2);
    if (r) {
        aura_battery_mv = 0;
        return r;
    }
    aura_battery_mv = ((uint32_t)sys_get_be16(bytes) * 625) / 8000;
    return 0;
}
static int haptic_init(void)
{
    if (!IS_ENABLED(CONFIG_AURA_HAPTIC_QUALIFIED))
        return 0;
    /* Conservative engineering target only. C08-00A: 0.84 Vrms, 240 Hz.
     * DRV2605L datasheet equations: sample_time=300us, DRIVE_TIME=2.1ms.
     * Rated register round(0.84*sqrt(1-(4*.0003+.0003)*240)/.02058)=33.
     * Clamp round(1.20/.02133)=56, below candidate 1.25V maximum.
     * Scope RMS/peaks and verify resonant behavior before qualifying this option. */
    gpio_pin_set_dt(&haptic, 1);
    k_msleep(2);
    uint8_t status;
    int r = i2c_reg_read_byte(i2c, 0x5a, 0, &status);
    if (r || (status >> 5) != 7)
        goto fail;
    const uint8_t regs[][2] = {{1, 0},       {0x16, 33},   {0x17, 56},   {0x1a, 0xb6}, {0x1b, 0x14},
                               {0x1c, 0xf5}, {0x1d, 0x80}, {0x1e, 0x30}, {1, 7},       {0x0c, 1}};
    for (unsigned n = 0; n < ARRAY_SIZE(regs); n++)
        if (i2c_reg_write_byte(i2c, 0x5a, regs[n][0], regs[n][1]))
            goto fail;
    for (int n = 0; n < 100; n++) {
        uint8_t go;
        if (i2c_reg_read_byte(i2c, 0x5a, 0x0c, &go))
            goto fail;
        if (!go) {
            if (i2c_reg_read_byte(i2c, 0x5a, 0, &status) || status & 0x08)
                goto fail;
            haptic_ready = true;
            gpio_pin_set_dt(&haptic, 0);
            return 0;
        }
        k_msleep(10);
    }
fail:
    gpio_pin_set_dt(&haptic, 0);
    return -EIO;
}
static void feedback(void)
{
    if (!haptic_ready)
        return;
    gpio_pin_set_dt(&haptic, 1);
    k_msleep(2);
    if (i2c_reg_write_byte(i2c, 0x5a, 1, 5) || i2c_reg_write_byte(i2c, 0x5a, 2, 35)) {
        haptic_ready = false;
        gpio_pin_set_dt(&haptic, 0);
        return;
    }
    k_msleep(30);
    i2c_reg_write_byte(i2c, 0x5a, 2, 0);
    gpio_pin_set_dt(&haptic, 0);
}
static void capture(void *a, void *b, void *c)
{
    ARG_UNUSED(a);
    ARG_UNUSED(b);
    ARG_UNUSED(c);
    bool running = false;
    uint8_t payload[AJ_PAYLOAD];
    unsigned used = 0;
    unsigned warmup = 0;
    struct pcm_stream_cfg stream = {
        .pcm_rate = 16000, .pcm_width = 16, .block_size = 2560, .mem_slab = &audio_slab};
    struct dmic_cfg cfg = {
        .io = {.min_pdm_clk_freq = 1280000,
               .max_pdm_clk_freq = 1280000,
               .min_pdm_clk_dc = 40,
               .max_pdm_clk_dc = 60},
        .streams = &stream,
        .channel = {.req_num_streams = 1, .req_num_chan = 2, .req_chan_map_lo = 0}};
    cfg.channel.req_chan_map_lo =
        dmic_build_channel_map(0, 0, PDM_CHAN_LEFT) | dmic_build_channel_map(1, 0, PDM_CHAN_RIGHT);
    while (1) {
        atomic_inc(&audio_heartbeat);
        if (!running) {
            if (!atomic_get(&wanted)) {
                k_msleep(10);
                continue;
            }
            if (aura_privacy || !atomic_get(&storage_ready) || aura_battery_mv < 3400) {
                atomic_clear(&wanted);
                continue;
            }
            k_mutex_lock(&aura_store_lock, K_FOREVER);
            int r = aj_begin(&aura_store, aura_time());
            k_mutex_unlock(&aura_store_lock);
            if (r) {
                aura_state = 4;
                atomic_clear(&wanted);
                continue;
            }
            used = 0;
            warmup = 2;
            r = dmic_configure(pdm, &cfg);
            if (!r && !aura_privacy && atomic_get(&wanted)) {
                gpio_pin_set_dt(&mic, 1);
                k_msleep(50);
                if (aura_privacy || !atomic_get(&wanted))
                    r = -ECANCELED;
                else
                    r = dmic_trigger(pdm, DMIC_TRIGGER_START);
            } else if (!r)
                r = -ECANCELED;
            if (r) {
                gpio_pin_set_dt(&mic, 0);
                k_mutex_lock(&aura_store_lock, K_FOREVER);
                aj_end(&aura_store, true);
                k_mutex_unlock(&aura_store_lock);
                atomic_clear(&wanted);
                aura_state = 4;
                continue;
            }
            running = true;
            aura_state = 1;
        }
        int r = 0;
        if (atomic_get(&wanted) && !aura_privacy) {
            void *buffer = NULL;
            uint32_t size = 0;
            r = dmic_read(pdm, 0, &buffer, &size, 250);
            if (!r) {
                /* Two 40 ms blocks with clocks present cover microphone power-up,
                 * wake and the PDM decimator's startup delay. Do not save transients. */
                if (warmup) {
                    warmup--;
                    k_mem_slab_free(&audio_slab, buffer);
                    continue;
                }
                if (size % 4)
                    r = -EBADMSG;
                int16_t *samples = buffer;
                for (unsigned i = 0; !r && i < size / 2; i += 2) {
                    /* Zephyr selects RATIO80 with the constrained 1.280 MHz clock:
                     * 32 MHz /25 /80 = exact 16000 Hz, within Knowles standard mode. */
                    sys_put_le16((uint16_t)aura_mix(samples[i], samples[i + 1]), payload + used);
                    used += 2;
                    if (used == AJ_PAYLOAD) {
                        k_mutex_lock(&aura_store_lock, K_FOREVER);
                        r = aj_append(&aura_store, payload, used);
                        k_mutex_unlock(&aura_store_lock);
                        used = 0;
                        if (r)
                            break;
                    }
                }
                k_mem_slab_free(&audio_slab, buffer);
            }
            if (atomic_cas(&mark_pending, 1, 0) && !r) {
                k_mutex_lock(&aura_store_lock, K_FOREVER);
                if (used) {
                    r = aj_append(&aura_store, payload, used);
                    used = 0;
                }
                if (!r)
                    r = aj_mark(&aura_store);
                k_mutex_unlock(&aura_store_lock);
            }
        }
        if (r || !atomic_get(&wanted) || aura_privacy) {
            gpio_pin_set_dt(&mic, 0);
            aura_state = 2;
            dmic_trigger(pdm, DMIC_TRIGGER_STOP);
            void *left;
            uint32_t left_size;
            while (dmic_read(pdm, 0, &left, &left_size, 0) == 0)
                k_mem_slab_free(&audio_slab, left);
            k_mutex_lock(&aura_store_lock, K_FOREVER);
            if (used && !r)
                r = aj_append(&aura_store, payload, used);
            int end = aj_end(&aura_store, r != 0);
            k_mutex_unlock(&aura_store_lock);
            atomic_clear(&wanted);
            running = false;
            atomic_clear(&mark_pending);
            aura_state = (r || end) ? 4 : (aura_privacy ? 3 : 0);
            if (r && r != -ENOSPC)
                fail_off();
        }
    }
}
int main(void)
{
    /* Hardware pulldowns enforce these levels before Zephyr reaches main. */
    if (!gpio_is_ready_dt(&mic) || !gpio_is_ready_dt(&charge) || !gpio_is_ready_dt(&privacy) ||
        !gpio_is_ready_dt(&haptic) || !gpio_is_ready_dt(&record))
        return -ENODEV;
    gpio_pin_configure_dt(&charge, GPIO_OUTPUT_INACTIVE);
    gpio_pin_configure_dt(&mic, GPIO_OUTPUT_INACTIVE);
    gpio_pin_configure_dt(&haptic, GPIO_OUTPUT_INACTIVE);
    gpio_pin_configure_dt(&privacy, GPIO_INPUT);
    gpio_pin_configure_dt(&record, GPIO_INPUT);
    gpio_init_callback(&privacy_cb, privacy_interrupt, BIT(privacy.pin));
    gpio_add_callback(privacy.port, &privacy_cb);
    gpio_pin_interrupt_configure_dt(&privacy, GPIO_INT_EDGE_BOTH);
    aura_privacy = gpio_pin_get_dt(&privacy) != 0;
    aura_state = aura_privacy ? 3 : 0;
    k_msleep(2);
    if (!device_is_ready(pdm) || !device_is_ready(i2c)) {
        aura_state = 4;
        return -ENODEV;
    }
    aura_state = 2;
    if (aura_bluetooth_init()) {
        fail_off();
        aura_state = 4;
        return -EIO;
    }
    k_mutex_lock(&aura_store_lock, K_FOREVER);
    int r = aura_nand_init();
    if (!r) {
        aura_store.io = aura_nand_io();
        aura_store.active = -1;
        if (format_intent)
            r = aura_erase_run(&aura_store,
                               (struct aura_maintenance_io){save_intent, aura_nand_erase_block},
                               true);
        else
            r = aj_mount(&aura_store, aura_nand_io());
    }
    if (r) {
        aura_store.fault = true;
        aura_state = 4;
    } else {
        atomic_set(&storage_ready, 1);
        aura_state = aura_privacy ? 3 : 0;
    }
    k_mutex_unlock(&aura_store_lock);
    if (aura_store.next_id < id_floor)
        aura_store.next_id = id_floor;
    gauge_read();
    haptic_init();
    if (IS_ENABLED(CONFIG_AURA_CHARGE_QUALIFIED) && !r && aura_battery_mv >= 2500 &&
        aura_battery_mv <= 4250) {
        gpio_pin_set_dt(&charge, 1);
        aura_charge_allowed = true;
    }
    k_thread_create(&audio_thread, audio_stack, K_THREAD_STACK_SIZEOF(audio_stack), capture, NULL,
                    NULL, NULL, 5, 0, K_NO_WAIT);
    if (device_is_ready(wdt)) {
        struct wdt_timeout_cfg w = {
            .window = {.min = 0, .max = 8000}, .callback = NULL, .flags = WDT_FLAG_RESET_SOC};
        watchdog_channel = wdt_install_timeout(wdt, &w);
        if (watchdog_channel >= 0 && wdt_setup(wdt, WDT_OPT_PAUSE_HALTED_BY_DBG))
            watchdog_channel = -1;
    }
    struct aura_gesture_state gestures = {0};
    int64_t next_gauge = 0;
    atomic_val_t prior_audio = 0;
    int64_t audio_changed = k_uptime_get();
    while (1) {
        int64_t now = k_uptime_get();
        int raw = gpio_pin_get_dt(&record);
        bool off = gpio_pin_get_dt(&privacy) != 0;
        aura_privacy = off;
        if (off) {
            gpio_pin_set_dt(&mic, 0);
            atomic_clear(&wanted);
            if (aura_state == 0)
                aura_state = 3;
        } else if (aura_state == 3)
            aura_state = 0;
        if (raw < 0) {
            fail_off();
            aura_state = 4;
            raw = 0;
        }
        enum aura_gesture gesture = aura_gesture_tick(&gestures, raw, now);
        if (gesture == AG_HOLD && (aura_state == 0 || aura_state == 3 || aura_state == 4)) {
            aura_pairing_window();
            feedback();
        }
        if (gesture == AG_MAINTENANCE && (aura_state == 0 || aura_state == 3 || aura_state == 4))
            maintenance_until = now + 30000;
        if (gesture == AG_DOUBLE && aura_state == 1) {
            atomic_set(&mark_pending, 1);
            feedback();
        }
        if (gesture == AG_PRESS) {
            if (aura_state == 1)
                atomic_clear(&wanted);
            else if (aura_state == 0 && !off && aura_battery_mv >= 3500 &&
                     atomic_get(&storage_ready)) {
                if (k_mutex_lock(&aura_store_lock, K_NO_WAIT) == 0) {
                    if (aura_state == 0)
                        atomic_set(&wanted, 1);
                    k_mutex_unlock(&aura_store_lock);
                    feedback();
                }
            }
        }
        if (now >= next_gauge) {
            next_gauge = now + 2000;
            int gauge = gauge_read();
            if (gauge || aura_battery_mv < 3300)
                atomic_clear(&wanted);
            if (IS_ENABLED(CONFIG_AURA_CHARGE_QUALIFIED) && !gauge && aura_battery_mv >= 2000 &&
                aura_battery_mv <= 4250 && !aura_store.fault && aura_state != 4 &&
                atomic_get(&storage_ready)) {
                gpio_pin_set_dt(&charge, 1);
                aura_charge_allowed = true;
            } else {
                gpio_pin_set_dt(&charge, 0);
                aura_charge_allowed = false;
            }
            if (aura_battery_mv > 4250)
                fail_off();
        }
        atomic_val_t beat = atomic_get(&audio_heartbeat);
        if (beat != prior_audio) {
            prior_audio = beat;
            audio_changed = now;
        }
        if (now - audio_changed < 3000 && watchdog_channel >= 0)
            wdt_feed(wdt, watchdog_channel);
        else if (now - audio_changed >= 3000) {
            fail_off();
            aura_state = 4;
        }
        k_msleep(10);
    }
    return 0;
}
