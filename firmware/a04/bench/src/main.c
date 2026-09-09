/* SPDX-License-Identifier: MIT */
/* nRF52840 DK wired bench application. Cold boot initializes/reads real NAND;
 * PDM and array writes require explicit local commands. Never flash AURA.
 * No radio, battery, charger, automatic format or audio-release capability. */
#include <zephyr/kernel.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/drivers/hwinfo.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/byteorder.h>
#include "aura_audio_zephyr.h"
#include "aura_w25n01gv_zephyr.h"
#include "aura_storage.h"
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define REQUEST_BYTES 256u
#define MAX_CAPTURE_MS 60000u
static const struct device *const uart = DEVICE_DT_GET(DT_CHOSEN(zephyr_console));
static const struct gpio_dt_spec mic = GPIO_DT_SPEC_GET(DT_NODELABEL(bench_controls), mic_enable_gpios);
static const struct gpio_dt_spec privacy = GPIO_DT_SPEC_GET(DT_NODELABEL(bench_controls), privacy_gpios);
static const struct gpio_dt_spec led = GPIO_DT_SPEC_GET(DT_ALIAS(led0), gpios);
static const struct spi_dt_spec spi = SPI_DT_SPEC_GET(DT_NODELABEL(bench_nand),
                                                     SPI_WORD_SET(8) | SPI_TRANSFER_MSB, 0);
static struct aura_w25n01gv_zephyr nand;
static struct aura_storage storage;
static struct aura_control control;
static struct aura_journal journal = {.active=-1};
static struct aura_recorder recorder;
static struct aura_audio_zephyr audio;
static uint8_t snapshot[AURA_STORAGE_STATE_BYTES], device_id[16], capture_id[16];
static union { max_align_t alignment; uint8_t bytes[AURA_OPUS_STATE_LIMIT]; } encoder;
static struct gpio_callback privacy_callback;
static struct k_thread reader_thread, storage_thread;
K_THREAD_STACK_DEFINE(reader_stack, 4096);
K_THREAD_STACK_DEFINE(storage_stack, 49152);
struct request { char line[REQUEST_BYTES]; atomic_val_t stop_generation; };
K_MSGQ_DEFINE(requests, sizeof(struct request), 2, 4);
static struct request rx;
static size_t rx_size;
static bool discard_line;
static atomic_t cancellation, session_generation, startup_pending, capture_gate, initialized, rx_fault;
static int boot_fault;
static uint64_t epoch, started_ms;
static uint32_t service_max_us, late_services, fifo_high_water;
static bool have_stop_reply;
static uint32_t stop_reply_id;

/* Exactly one storage owner writes complete protocol lines. ISR/reader never
 * format or transmit; they only publish atomic state or bounded commands. */
static void reply(uint32_t id, const char *format, ...)
{
    char line[384];
    int prefix = snprintf(line, sizeof(line), "A04B %08x ", id);
    va_list arguments; va_start(arguments, format);
    int length = vsnprintf(line + prefix, sizeof(line) - (size_t)prefix - 1, format, arguments);
    va_end(arguments);
    if (length < 0 || (size_t)length >= sizeof(line) - (size_t)prefix - 1) {
        length = snprintf(line + prefix, sizeof(line) - (size_t)prefix, "ERROR %d", -EMSGSIZE);
    }
    size_t used = (size_t)prefix + (size_t)length;
    line[used++] = '\n';
    for (size_t i = 0; i < used; ++i) uart_poll_out(uart, line[i]);
}
static int nibble(char value)
{
    if (value >= '0' && value <= '9') return value - '0';
    if (value >= 'a' && value <= 'f') return value - 'a' + 10;
    if (value >= 'A' && value <= 'F') return value - 'A' + 10;
    return -1;
}
static int unhex(const char *text, uint8_t *bytes, size_t count)
{
    if (!text || strlen(text) != count * 2) return -EINVAL;
    for (size_t i = 0; i < count; ++i) {
        int high = nibble(text[2*i]), low = nibble(text[2*i+1]);
        if (high < 0 || low < 0) return -EINVAL;
        bytes[i] = (uint8_t)(high * 16 + low);
    }
    return 0;
}
static void hex(const uint8_t *bytes, size_t count, char *out)
{
    const char digits[] = "0123456789abcdef";
    for (size_t i = 0; i < count; ++i) { out[i*2] = digits[bytes[i] >> 4]; out[i*2+1] = digits[bytes[i] & 15]; }
    out[count*2] = 0;
}
static bool valid_prefix(const char *line)
{
    if (strlen(line) < 15 || memcmp(line, "A04B ", 5) || line[13] != ' ') return false;
    for (unsigned i = 5; i < 13; ++i) if (nibble(line[i]) < 0) return false;
    return true;
}
static void cancel_capture(bool physical)
{
    atomic_inc(&cancellation);
    if (atomic_get(&initialized)) {
        if (physical) aura_audio_zephyr_privacy_cutoff(&audio);
        else aura_audio_zephyr_request_stop(&audio);
    }
}
static void receive_byte(uint8_t value)
{
    if (value == '\r') return;
    if (value == '\n') {
        if (!discard_line) {
            rx.line[rx_size] = 0;
            if (valid_prefix(rx.line)) {
                if (!strcmp(rx.line + 14, "STOP")) cancel_capture(false);
                rx.stop_generation = atomic_get(&cancellation);
                if (k_msgq_put(&requests, &rx, K_NO_WAIT)) atomic_set(&rx_fault, 1);
            } else atomic_set(&rx_fault, 1);
        }
        memset(&rx, 0, sizeof(rx)); rx_size = 0; discard_line = false;
    } else if (value < 32 || value > 126 || rx_size >= sizeof(rx.line) - 1) {
        discard_line = true; atomic_set(&rx_fault, 1);
    } else if (!discard_line) rx.line[rx_size++] = (char)value;
}
static void uart_input(const struct device *port, void *user)
{
    ARG_UNUSED(user);
    if (uart_err_check(port)) { discard_line = true; atomic_set(&rx_fault, 1); }
    while (uart_irq_update(port) && uart_irq_rx_ready(port)) {
        uint8_t bytes[16]; int count = uart_fifo_read(port, bytes, sizeof(bytes));
        if (count <= 0) break;
        for (int i = 0; i < count; ++i) receive_byte(bytes[i]);
    }
}
static bool permitted(void *user)
{
    ARG_UNUSED(user);
    return atomic_get(&capture_gate) &&
           (!atomic_get(&startup_pending) || atomic_get(&session_generation) == atomic_get(&cancellation)) &&
           gpio_pin_get_dt(&privacy) == 1;
}
static void privacy_changed(const struct device *port, struct gpio_callback *callback, gpio_port_pins_t pins)
{
    ARG_UNUSED(port); ARG_UNUSED(callback); ARG_UNUSED(pins);
    if (gpio_pin_get_dt(&privacy) != 1) cancel_capture(true);
}
static bool audio_pending(void)
{
    atomic_val_t state = atomic_get(&audio.state);
    return state == AURA_AUDIO_STARTING || state == AURA_AUDIO_CAPTURING || state == AURA_AUDIO_STOPPING ||
        !atomic_get(&audio.reader_done) || k_msgq_num_used_get(&audio.queue) ||
        recorder.state == AURA_RECORDER_RECORDING;
}
static bool busy(void) { return audio_pending() || journal.active >= 0; }
static void reader(void *one, void *two, void *three)
{
    ARG_UNUSED(one); ARG_UNUSED(two); ARG_UNUSED(three);
    for (;;) {
        if (atomic_get(&audio.reader_enabled)) {
            (void)aura_audio_zephyr_reader_step(&audio);
            if (atomic_get(&audio.state) == AURA_AUDIO_STOPPING) k_msleep(1);
        } else k_msleep(1);
    }
}
static unsigned free_blocks(void)
{
    unsigned count = 0;
    if (storage.ready) for (unsigned i=0; i<journal.io.blocks; ++i)
        count += journal.block_state[i] == AURA_BLOCK_FREE || journal.block_state[i] == AURA_BLOCK_PREPARED;
    return count;
}
static int owner_fault(void)
{
    /* The recorder may fail while sealing after the producer has stopped.
     * The audio adapter's producer fault alone cannot describe that failure. */
    int audio_fault = (int)atomic_get(&audio.fault);
    if (boot_fault) return boot_fault;
    if (storage.fault) return storage.fault;
    if (audio_fault) return audio_fault;
    if (recorder.close_error) return recorder.close_error;
    if (recorder.fault_reason) return recorder.fault_reason;
    return journal.fault;
}
static void info(uint32_t id)
{
    char identity[33]; hex(device_id, 16, identity);
    reply(id, "OK INFO %s %u %d %d %u %u", identity, storage.ready, (int)atomic_get(&audio.state),
          owner_fault(), storage.ready ? journal.count : 0, free_blocks());
}
static void stats(uint32_t id)
{
    size_t reader_free=0, storage_free=0;
    (void)k_thread_stack_space_get(&reader_thread, &reader_free);
    (void)k_thread_stack_space_get(&storage_thread, &storage_free);
    reply(id, "OK STATS %u %u %u %u %u %llu %u %u %u %u %u %u", service_max_us, late_services,
        fifo_high_water, (unsigned)reader_free, (unsigned)storage_free,
        (unsigned long long)(journal.metadata_reads+journal.payload_reads+control.reads),
        nand.device.program_attempts, nand.device.erase_attempts,
        audio.peak[0], audio.peak[1], audio.clipped[0], audio.clipped[1]);
}
static int enroll(const char *argument, bool provision)
{
    uint8_t bytes[88]; int result = unhex(argument, bytes, sizeof(bytes));
    if (result) { memset(bytes, 0, sizeof(bytes)); return result; }
    struct aura_release_auth_context context;
    memcpy(context.device_id, bytes, 16); memcpy(context.storage_incarnation, bytes+16, 16);
    memcpy(context.owner_id, bytes+32, 16); context.owner_generation=sys_get_le64(bytes+48);
    memcpy(context.key, bytes+56, 32); memset(bytes, 0, sizeof(bytes));
    if (memcmp(context.device_id, device_id, 16)) result=-EACCES;
    else {
        struct aura_control_config config = {.blocks={1022,1023}};
        memcpy(config.domain, context.storage_incarnation, 16);
        struct aura_storage_io io = {.data=aura_w25n01gv_zephyr_io(&nand),
            .control=aura_w25n01gv_zephyr_control_io(&nand), .erase_released=NULL};
        if (provision) result=aura_storage_provision(&storage, io, &config, &context,
            &journal, &control, snapshot, sizeof(snapshot));
        else result=aura_storage_open(&storage, io, &config, &context,
            &journal, &control, snapshot, sizeof(snapshot));
    }
    memset(&context, 0, sizeof(context)); return result;
}
static int begin(const struct request *request)
{
    if (epoch==UINT64_MAX || atomic_get(&audio.state)==AURA_AUDIO_QUARANTINED) return -EOVERFLOW;
    atomic_set(&session_generation, request->stop_generation); atomic_set(&startup_pending, 1);
    atomic_set(&capture_gate, 1);
    if (!permitted(NULL)) { atomic_clear(&capture_gate); atomic_clear(&startup_pending); return -EACCES; }
    struct aura_archive_manifest settings={.frame_samples=320,.pre_skip=40}, manifest;
    int result=aura_storage_prepare_capture(&storage, &settings, &manifest);
    if (result) { atomic_clear(&capture_gate); atomic_clear(&startup_pending); return result; }
    memcpy(capture_id, manifest.capture_id, 16); ++epoch;
    service_max_us=late_services=fifo_high_water=0;
    /* Retry only the same reserved manifest. Cancellation remains visible in
     * permitted() across all storage preparation and microphone-start races. */
    do {
        if (!permitted(NULL)) { result=-ECANCELED; break; }
        result=aura_audio_zephyr_begin(&audio, &manifest, epoch);
        if (result==AURA_JOURNAL_RETRY_PREPARE) k_msleep(1);
    } while (result==AURA_JOURNAL_RETRY_PREPARE);
    if (result && journal.active < 0 && journal.binding_pending)
        (void)aura_storage_cancel_prepared(&storage);
    if (result) atomic_clear(&capture_gate);
    else started_ms=(uint64_t)k_uptime_get();
    atomic_clear(&startup_pending);
    return result;
}
struct export { uint32_t request_id; uint64_t offset; };
static int send_data(void *user, uint64_t offset, const uint8_t *bytes, size_t size)
{
    struct export *state=user;
    if (offset!=state->offset) return -EIO;
    while (size) {
        size_t take=MIN(size,128u); char payload[257]; hex(bytes,take,payload);
        reply(state->request_id,"DATA %016llx %s %08x",(unsigned long long)state->offset,
              payload,aura_archive_crc32(bytes,take));
        state->offset+=take; bytes+=take; size-=take;
    }
    return 0;
}
static int export_capture(uint32_t id, const char *argument)
{
    uint8_t selected[16]; int result=unhex(argument,selected,16); if(result)return result;
    unsigned index=0;
    for(;index<journal.count;++index)if(!memcmp(journal.captures[index].manifest+24,selected,16))break;
    if(index==journal.count)return -ENOENT;
    struct export state={.request_id=id};
    result=aura_journal_export(&journal,(uint16_t)index,send_data,&state);
    uint8_t receipt[94];
    if(!result)result=aura_journal_receipt(&journal,(uint16_t)index,receipt);
    if(!result){char encoded[189];hex(receipt,94,encoded);
        reply(id,"END EXPORT %016llx %s",(unsigned long long)state.offset,encoded);}
    return result;
}
static void dispatch(struct request *request)
{
    char id_text[9];memcpy(id_text,request->line+5,8);id_text[8]=0;
    uint32_t id=(uint32_t)strtoul(id_text,NULL,16);
    char *verb=request->line+14,*argument=strchr(verb,' ');
    if(argument){*argument++=0;if(!*argument||strchr(argument,' ')){reply(id,"ERROR %d",-EINVAL);return;}}
    if(!strcmp(verb,"INFO")&&!argument){info(id);return;}
    if(!strcmp(verb,"STOP")&&!argument){
        if(have_stop_reply){reply(id,"ERROR %d",-EBUSY);return;}
        aura_audio_zephyr_request_stop(&audio); have_stop_reply=true;stop_reply_id=id;return;
    }
    if(!strcmp(verb,"STATS")&&!argument&&!audio_pending()){stats(id);return;}
    if(busy()||have_stop_reply){reply(id,"ERROR %d",-EBUSY);return;}
    if(boot_fault){reply(id,"ERROR %d",boot_fault);return;}
    int result;
    if((!strcmp(verb,"PROVISION")||!strcmp(verb,"OPEN"))&&argument){
        result=enroll(argument,!strcmp(verb,"PROVISION"));
        if(!result)reply(id,"OK %s",verb);
    }else if(!storage.ready){result=-EACCES;
    }else if(!strcmp(verb,"LIST")&&!argument){
        for(unsigned i=0;i<journal.count;++i){
            (void)aura_journal_verify(&journal,(uint16_t)i);
            char manifest[137];hex(journal.captures[i].manifest,68,manifest);
            reply(id,"ITEM %s %u %u",manifest,journal.captures[i].verification,journal.captures[i].blocks);
        }
        reply(id,"END LIST %u",journal.count);return;
    }else if(!strcmp(verb,"START")&&!argument){
        result=begin(request);
        if(!result){char identity[33];hex(capture_id,16,identity);reply(id,"OK START %s",identity);}
    }else if(!strcmp(verb,"EXPORT")&&argument){result=export_capture(id,argument);
    }else result=-EINVAL;
    if(result)reply(id,"ERROR %d",result);
}
static void owner(void *one,void *two,void *three)
{
    ARG_UNUSED(one);ARG_UNUSED(two);ARG_UNUSED(three);
    boot_fault=aura_w25n01gv_zephyr_init(&nand,&spi);
    if(!boot_fault)boot_fault=aura_w25n01gv_zephyr_configure_control(&nand,1022,1023);
    for(;;){
        atomic_val_t current=atomic_get(&audio.state);
        if(current==AURA_AUDIO_CAPTURING&&(uint64_t)k_uptime_get()-started_ms>=MAX_CAPTURE_MS)
            aura_audio_zephyr_request_stop(&audio);
        if(audio_pending()){
            unsigned queued=k_msgq_num_used_get(&audio.queue);if(queued>fifo_high_water)fifo_high_water=queued;
            uint32_t started=k_cycle_get_32();(void)aura_audio_zephyr_service(&audio);
            uint32_t duration=k_cyc_to_us_floor32(k_cycle_get_32()-started);
            if(duration>service_max_us)service_max_us=duration;
            if(duration>20000)++late_services;
        }
        bool active=audio_pending();
        (void)gpio_pin_set_dt(&led,active&&atomic_get(&capture_gate));
        if(!active){
            atomic_clear(&capture_gate);
            if(have_stop_reply){char identity[33];hex(capture_id,16,identity);
                reply(stop_reply_id,"OK STOP %d %d %s",(int)atomic_get(&audio.state),
                      owner_fault(),identity);have_stop_reply=false;}
        }
        struct request request;
        if(!k_msgq_get(&requests,&request,K_NO_WAIT)){dispatch(&request);memset(&request,0,sizeof(request));}
        if(atomic_cas(&rx_fault,1,0))reply(0,"ERROR %d",-EMSGSIZE);
        k_msleep(1);
    }
}
int main(void)
{
    if(!device_is_ready(uart)||!gpio_is_ready_dt(&privacy)||!gpio_is_ready_dt(&led))return -ENODEV;
    uint8_t uid[8],message[32]={0},digest[32];
    if(hwinfo_get_device_id(uid,sizeof(uid))!=sizeof(uid))return -ENODEV;
    memcpy(message,"AURA-A04-BENCH-DEVICE-v1",24);memcpy(message+24,uid,8);
    aura_archive_sha256(message,sizeof(message),digest);memcpy(device_id,digest,16);
    int result=gpio_pin_configure_dt(&privacy,GPIO_INPUT);
    if(!result)result=gpio_pin_configure_dt(&led,GPIO_OUTPUT_INACTIVE);
    if(!result)result=aura_recorder_init(&recorder,&journal,encoder.bytes,sizeof(encoder.bytes));
    if(!result)result=aura_audio_zephyr_init(&audio,DEVICE_DT_GET(DT_NODELABEL(pdm0)),mic,
                                          permitted,NULL,&recorder,AURA_AUDIO_MEAN);
    if(result)return result;
    atomic_set(&initialized,1);
    gpio_init_callback(&privacy_callback,privacy_changed,BIT(privacy.pin));
    result=gpio_add_callback(privacy.port,&privacy_callback);
    if(!result)result=gpio_pin_interrupt_configure_dt(&privacy,GPIO_INT_EDGE_BOTH);
    if(result)return result;
    result=uart_irq_callback_user_data_set(uart,uart_input,NULL);if(result)return result;
    printk("AURA wired bench only; microphone off; explicit host OPEN/PROVISION and START required.\n");
    uart_irq_rx_enable(uart);
    k_thread_create(&reader_thread,reader_stack,K_THREAD_STACK_SIZEOF(reader_stack),
                    reader,NULL,NULL,NULL,K_PRIO_PREEMPT(4),0,K_NO_WAIT);
    k_thread_create(&storage_thread,storage_stack,K_THREAD_STACK_SIZEOF(storage_stack),
                    owner,NULL,NULL,NULL,K_PRIO_PREEMPT(7),0,K_NO_WAIT);
    return 0;
}
