/* SPDX-License-Identifier: MIT */
/* DK-only ABI/resource integration probe: synthetic PCM and volatile RAM NAND.
 * The custom DMIC device binds DK test pins at boot, but no PDM stream,
 * microphone power, physical NAND, radio or charger is started by this probe.
 * Cross-built, not executed on AURA; never flash this image onto the wearable. */
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>
#include "aura_opus.h"
#include "aura_archive.h"
#include "aura_journal.h"
#include "aura_w25n01gv_zephyr.h"
#include "aura_audio_zephyr.h"
#include "aura_dmic_health.h"
#include <string.h>

#define CODEC_STACK_BYTES 49152
static union {
    max_align_t alignment;
    uint8_t bytes[AURA_OPUS_STATE_LIMIT];
} encoder_state;
static struct aura_recorder recorder;
static struct aura_journal journal;
static struct aura_w25n01gv_zephyr nand_adapter;
static struct aura_audio_zephyr audio_adapter;
/* Eight sparse pages suffice for this short synthetic capture. */
static uint8_t probe_pages[8][2048], probe_map[64], probe_used;
static int probe_highest;
K_THREAD_STACK_DEFINE(codec_stack, CODEC_STACK_BYTES);
static struct k_thread codec_thread;
static uint64_t sink_bytes;
static int16_t input[AURA_OPUS_MAX_SAMPLES];

static int probe_sink(void *user, uint64_t offset, const uint8_t *wire, size_t bytes)
{
    ARG_UNUSED(user);
    /* This export sink deliberately discards SYNTHETIC probe output. */
    ARG_UNUSED(wire);
    if (offset != sink_bytes) return -1;
    sink_bytes += bytes;
    return 0;
}
static int ram_read(void *u,uint32_t page,uint16_t col,uint8_t *out,size_t bytes)
{
    ARG_UNUSED(u);
    if(page>=64||col>2048||bytes>2048u-col)return AURA_NAND_BAD_ARGUMENT;
    if(probe_map[page]==255)memset(out,255,bytes);
    else memcpy(out,probe_pages[probe_map[page]]+col,bytes);
    return 0;
}
static int ram_program(void *u,uint32_t page,const uint8_t *data)
{
    ARG_UNUSED(u);
    if(page<2||page>=64||(int)page<=probe_highest||probe_used==8)return AURA_NAND_PROGRAM_ORDER;
    probe_highest=(int)page;probe_map[page]=probe_used;memcpy(probe_pages[probe_used++],data,2048);return 0;
}
static int ram_erase(void *u,uint32_t block)
{ARG_UNUSED(u);return block||probe_used?AURA_NAND_BAD_ARGUMENT:0;}
static int ram_bad(void *u,uint32_t block,bool *out)
{ARG_UNUSED(u);if(block||!out)return AURA_NAND_BAD_ARGUMENT;*out=false;return 0;}

static void probe(void *one, void *two, void *three)
{
    ARG_UNUSED(one); ARG_UNUSED(two); ARG_UNUSED(three);
    memset(probe_map,255,sizeof(probe_map));probe_highest=-1;
    struct aura_nand_io ram={NULL,1,ram_read,ram_program,ram_erase,ram_bad};
    int status=aura_journal_mount(&journal,ram);
    if(!status)status=aura_recorder_init(&recorder,&journal,encoder_state.bytes,sizeof(encoder_state.bytes));
    struct aura_archive_manifest manifest = {.frame_samples = 320, .pre_skip = 40};
    memset(manifest.device_id, 0x11, 16);
    memset(manifest.capture_id, 0x22, 16);
    if (!status) status = aura_recorder_start(&recorder, &manifest, 1, (uint64_t)k_uptime_get());
    /* Retain the real adapter and its RAM footprint in the linked image without
     * choosing a devicetree node or invoking any physical SPI operation. */
    struct aura_nand_io physical=aura_w25n01gv_zephyr_io(&nand_adapter);
    printk("A04 EXPERIMENTAL codec=%s state=%u reserved=%u recorder=%u journal=%u init=%d "
           "uninitialized_spi_blocks=%u spi_init_symbol=%p\n",
           opus_get_version_string(), (unsigned)aura_opus_state_bytes(),
           (unsigned)sizeof(encoder_state.bytes), (unsigned)sizeof(recorder),
           (unsigned)sizeof(journal), status,physical.blocks,(void *)aura_w25n01gv_zephyr_init);
    struct aura_dmic_health health;
    int health_status=aura_dmic_health_get(DEVICE_DT_GET(DT_NODELABEL(pdm0)),&health);
    printk("DK PIN BINDING ONLY audio_context=%u health=%d begin=%p read=%p service=%p init=%p "
           "privacy=%p stop=%p context_address=%p; no physical audio stream started\n",
           (unsigned)sizeof(audio_adapter),health_status,(void *)aura_audio_zephyr_begin,
           (void *)aura_audio_zephyr_reader_step,(void *)aura_audio_zephyr_service,
           (void *)aura_audio_zephyr_init,(void *)aura_audio_zephyr_privacy_cutoff,
           (void *)aura_audio_zephyr_request_stop,(void *)&audio_adapter);
    uint32_t worst_us = 0, late_frames = 0;
    for (unsigned frame = 0; !status && frame < 50; ++frame) {
        for (unsigned i = 0; i < ARRAY_SIZE(input); ++i)
            input[i] = (int16_t)((int)((i + frame * 320) % 80) * 250 - 10000);
        size_t consumed = 0;
        uint32_t begin = k_cycle_get_32();
        struct aura_recorder_block block={.epoch=1,.sequence=frame,.source_offset=frame*320u,
            .pcm=input,.samples=ARRAY_SIZE(input)};
        status = aura_recorder_consume(&recorder, &block, (uint64_t)k_uptime_get(), &consumed);
        uint32_t usec = k_cyc_to_us_floor32(k_cycle_get_32() - begin);
        if (usec > worst_us) worst_us = usec;
        if (usec > 20000) ++late_frames;
        if (!status && consumed != ARRAY_SIZE(input)) status = -1;
        if (!status && frame == 24) status = aura_archive_bookmark(&recorder.archive, 8000);
        if (!status) status = aura_recorder_service(&recorder,(uint64_t)k_uptime_get());
        k_yield();
    }
    if (!status) status = aura_recorder_stop(&recorder,1,16000,(uint64_t)k_uptime_get());
    struct aura_opus_seal seal = recorder.seal;
    uint8_t receipt[AURA_ARCHIVE_ACK_BYTES];
    if (!status) status = aura_journal_receipt(&journal, 0, receipt);
    if (!status) status = aura_journal_mount(&journal,ram);
    if (!status) status = aura_journal_export(&journal,0,probe_sink,NULL);
    size_t free_stack = 0;
    int stack_status = k_thread_stack_space_get(k_current_get(), &free_stack);
    printk("A04 VOLATILE RAM PROBE ONLY result=%d packets=%u wire_bytes=%u source=%u preskip=%u tail=%u "
           "worst_encode_us=%u late_frames=%u stack_free=%u stack_check=%d\n",
           status, recorder.archive.audio_packets, (unsigned)sink_bytes, (unsigned)seal.source_samples,
           seal.pre_skip, seal.end_trim, worst_us, late_frames,
           (unsigned)free_stack, stack_status);
}

int main(void)
{
    k_thread_create(&codec_thread, codec_stack, K_THREAD_STACK_SIZEOF(codec_stack),
                    probe, NULL, NULL, NULL, K_PRIO_PREEMPT(5), 0, K_NO_WAIT);
    return 0;
}
