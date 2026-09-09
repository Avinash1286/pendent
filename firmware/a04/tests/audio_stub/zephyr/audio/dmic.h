/* SPDX-License-Identifier: MIT */
#ifndef AUDIO_STUB_DMIC_H
#define AUDIO_STUB_DMIC_H
#include <zephyr/kernel.h>
enum dmic_trigger { DMIC_TRIGGER_START, DMIC_TRIGGER_STOP };
enum pdm_lr { PDM_CHAN_LEFT, PDM_CHAN_RIGHT };
struct pcm_stream_cfg { uint32_t pcm_rate; uint8_t pcm_width; uint32_t block_size; struct k_mem_slab *mem_slab; };
struct dmic_cfg {
    struct { uint32_t min_pdm_clk_freq,max_pdm_clk_freq; uint8_t min_pdm_clk_dc,max_pdm_clk_dc; } io;
    struct pcm_stream_cfg *streams;
    struct { uint8_t req_num_streams,req_num_chan,act_num_streams,act_num_chan;
        uint32_t req_chan_map_lo,req_chan_map_hi,act_chan_map_lo,act_chan_map_hi; } channel;
};
static inline uint32_t dmic_build_channel_map(unsigned slot,unsigned pdm,enum pdm_lr lr)
{return (uint32_t)((pdm<<1)|(unsigned)lr)<<(slot*4);}
int dmic_configure(const struct device *,struct dmic_cfg *);
int dmic_trigger(const struct device *,enum dmic_trigger);
int dmic_read(const struct device *,uint8_t,void **,size_t *,int32_t);
#endif
