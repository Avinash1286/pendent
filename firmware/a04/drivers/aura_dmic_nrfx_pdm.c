/*
 * Copyright (c) 2021 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: Apache-2.0
 */

/* Vendored from Zephyr v4.2.0; see README.md for provenance and changes. */
#ifdef AURA_DMIC_HOST_TEST
#include "tests/driver_shim.h"
#else
#include <zephyr/audio/dmic.h>
#include <zephyr/drivers/clock_control/nrf_clock_control.h>
#include <zephyr/drivers/pinctrl.h>
#include <soc.h>
#include <dmm.h>
#include <nrfx_pdm.h>

#include <zephyr/logging/log.h>
#include <zephyr/irq.h>
#endif
#include <aura_dmic_health.h>
LOG_MODULE_REGISTER(aura_dmic_nrfx_pdm, CONFIG_AUDIO_DMIC_LOG_LEVEL);

struct aura_rx_block {
	void *buffer;
	uint64_t sequence;
};

struct aura_dma_buffer {
	void *slab;
	void *dma;
};

#if CONFIG_SOC_SERIES_NRF54HX
#define DMIC_NRFX_CLOCK_FREQ MHZ(16)
#define DMIC_NRFX_CLOCK_FACTOR 8192
#define DMIC_NRFX_AUDIO_CLOCK_FREQ DT_PROP_OR(DT_NODELABEL(audiopll), frequency, 0)
#else
#define DMIC_NRFX_CLOCK_FREQ MHZ(32)
#define DMIC_NRFX_CLOCK_FACTOR 4096
#define DMIC_NRFX_AUDIO_CLOCK_FREQ DT_PROP_OR(DT_NODELABEL(aclk), clock_frequency, \
				   DT_PROP_OR(DT_NODELABEL(clock), hfclkaudio_frequency, 0))
#endif

struct dmic_nrfx_pdm_drv_data {
	const nrfx_pdm_t *pdm;
#if CONFIG_CLOCK_CONTROL_NRF
	struct onoff_manager *clk_mgr;
#elif CONFIG_CLOCK_CONTROL_NRFS_AUDIOPLL
	const struct device *audiopll_dev;
#endif
	struct onoff_client clk_cli;
	struct k_mem_slab *mem_slab;
	uint32_t block_size;
	struct k_msgq rx_queue;
	struct aura_dma_buffer dma[2];
	enum aura_dmic_fault faults;
	int first_error;
	uint32_t epoch;
	uint64_t completed_blocks;
	uint64_t delivered_blocks;
	uint64_t last_read_sequence;
	bool clock_pending;
	bool clock_owned;
	bool hw_started;
	bool request_clock : 1;
	bool configured    : 1;
	volatile bool active;
	volatile bool stopping;
};

static const struct _dmic_ops dmic_ops;

struct dmic_nrfx_pdm_drv_cfg {
	nrfx_pdm_event_handler_t event_handler;
	nrfx_pdm_config_t nrfx_def_cfg;
	const struct pinctrl_dev_config *pcfg;
	enum clock_source {
		PCLK32M,
		PCLK32M_HFXO,
		ACLK
	} clk_src;
	void *mem_reg;
};

/* All mutable state is serialized by irq_lock on this nRF52840-only driver.
 * The application must serialize its DMIC calls; read may block outside the lock.
 */
static uint8_t owned_buffers(const struct dmic_nrfx_pdm_drv_data *data)
{
	return (data->dma[0].slab != NULL) + (data->dma[1].slab != NULL);
}

static void latch_fault(struct dmic_nrfx_pdm_drv_data *data,
			enum aura_dmic_fault fault, int error)
{
	if (data->faults == AURA_DMIC_FAULT_NONE) {
		data->first_error = error < 0 ? error : -EIO;
	}
	data->faults = (enum aura_dmic_fault)(data->faults | fault);
}

static int request_clock(struct dmic_nrfx_pdm_drv_data *data)
{
#if CONFIG_CLOCK_CONTROL_NRF
	return onoff_request(data->clk_mgr, &data->clk_cli);
#else
	return -ENOTSUP;
#endif
}

static int release_clock(struct dmic_nrfx_pdm_drv_data *data)
{
#if CONFIG_CLOCK_CONTROL_NRF
	return onoff_release(data->clk_mgr);
#else
	return -ENOTSUP;
#endif
}

static bool peripheral_enabled(const struct dmic_nrfx_pdm_drv_data *data)
{
	return nrfx_pdm_enable_check(data->pdm);
}

/* nrfx disables the peripheral before emitting its STOPPED buffer releases.
 * IDLE/STARTING stops need not emit a release callback. Never release the HF
 * clock until both its asynchronous request and all DMA ownership are settled.
 */
static void finish_stop(struct dmic_nrfx_pdm_drv_data *data)
{
	if (data->active || data->clock_pending || owned_buffers(data) != 0 ||
	    peripheral_enabled(data)) {
		return;
	}
	if (data->clock_owned) {
		int ret = release_clock(data);

		if (ret < 0) {
			latch_fault(data, AURA_DMIC_FAULT_CLOCK, ret);
			data->stopping = true;
			return;
		}
		data->clock_owned = false;
	}
	data->stopping = false;
}

static void stop_pdm(struct dmic_nrfx_pdm_drv_data *data)
{
	bool was_stopping = data->stopping;
	nrfx_err_t err;

	data->active = false;
	data->stopping = true;
	/* nrfx STOP during STARTING disables without returning its DMA buffers.
	 * If the first DMA buffer was armed, wait for the STARTED callback first;
	 * then nrfx is RUNNING and STOP guarantees asynchronous buffer returns.
	 */
	if (!data->hw_started && owned_buffers(data) != 0 && peripheral_enabled(data)) {
		return;
	}
	if (data->configured) {
		err = nrfx_pdm_stop(data->pdm);
		if (err != NRFX_SUCCESS && !(was_stopping && err == NRFX_ERROR_BUSY)) {
			latch_fault(data, AURA_DMIC_FAULT_STOP, -EIO);
		}
	}
	finish_stop(data);
}

static bool fully_stopped(const struct dmic_nrfx_pdm_drv_data *data)
{
	return !data->active && !data->stopping && !data->clock_pending &&
	       !data->clock_owned && owned_buffers(data) == 0 && !peripheral_enabled(data);
}

static bool fully_drained(struct dmic_nrfx_pdm_drv_data *data)
{
	return fully_stopped(data) && k_msgq_num_used_get(&data->rx_queue) == 0 &&
	       (data->mem_slab == NULL || k_mem_slab_num_used_get(data->mem_slab) == 0);
}

static bool release_buffer(const struct device *dev, unsigned int slot, bool complete)
{
	struct dmic_nrfx_pdm_drv_data *data = dev->data;
	const struct dmic_nrfx_pdm_drv_cfg *cfg = dev->config;
	struct aura_dma_buffer *entry = &data->dma[slot];
	struct aura_rx_block block = { .buffer = entry->slab };
	int ret;

	/* Count the observed full release even if the following handoff fails. */
	if (complete) {
		block.sequence = ++data->completed_blocks;
	}
	ret = dmm_buffer_in_release(cfg->mem_reg, entry->slab,
				    data->block_size, entry->dma);
	if (ret < 0) {
		/* Retain uncertain ownership. Reset/reconfigure must remain blocked. */
		latch_fault(data, AURA_DMIC_FAULT_RELEASE, ret);
		return false;
	}
	entry->slab = NULL;
	entry->dma = NULL;
	if (complete) {
		ret = k_msgq_put(&data->rx_queue, &block, K_NO_WAIT);
		if (ret == 0) {
			return true;
		}
		latch_fault(data, AURA_DMIC_FAULT_RX_QUEUE, ret);
	}
	k_mem_slab_free(data->mem_slab, block.buffer);
	return !complete;
}

static void event_handler(const struct device *dev, const nrfx_pdm_evt_t *evt)
{
	struct dmic_nrfx_pdm_drv_data *data = dev->data;
	const struct dmic_nrfx_pdm_drv_cfg *cfg = dev->config;
	unsigned int key = irq_lock();
	int ret;

	if (evt->buffer_requested && owned_buffers(data) != 0) {
		data->hw_started = true;
	}
	if (evt->error != NRFX_PDM_NO_ERROR) {
		latch_fault(data, AURA_DMIC_FAULT_OVERFLOW, -EOVERFLOW);
		stop_pdm(data);
	}

	/* Reclaim by the actual DMA pointer, before supplying the next buffer.
	 * A STOPPED callback may contain a partial block; never count it as full.
	 */
	if (evt->buffer_released != NULL) {
		unsigned int slot;

		for (slot = 0; slot < ARRAY_SIZE(data->dma); ++slot) {
			if (data->dma[slot].slab != NULL &&
			    data->dma[slot].dma == evt->buffer_released) {
				break;
			}
		}
		if (slot == ARRAY_SIZE(data->dma)) {
			latch_fault(data, AURA_DMIC_FAULT_OWNERSHIP, -EIO);
			stop_pdm(data);
		} else if (!release_buffer(dev, slot,
					data->active && !data->stopping &&
					data->faults == AURA_DMIC_FAULT_NONE)) {
			stop_pdm(data);
		}
	}

	if (evt->buffer_requested && data->active && !data->stopping &&
	    data->faults == AURA_DMIC_FAULT_NONE) {
		unsigned int slot;
		void *slab_buffer;
		void *dma_buffer;

		for (slot = 0; slot < ARRAY_SIZE(data->dma); ++slot) {
			if (data->dma[slot].slab == NULL) {
				break;
			}
		}
		if (slot == ARRAY_SIZE(data->dma)) {
			latch_fault(data, AURA_DMIC_FAULT_OWNERSHIP, -ENOSPC);
			stop_pdm(data);
			goto done;
		}
		ret = k_mem_slab_alloc(data->mem_slab, &slab_buffer, K_NO_WAIT);
		if (ret < 0) {
			latch_fault(data, AURA_DMIC_FAULT_SLAB, ret);
			stop_pdm(data);
			goto done;
		}
		ret = dmm_buffer_in_prepare(cfg->mem_reg, slab_buffer,
					    data->block_size, &dma_buffer);
		if (ret < 0) {
			k_mem_slab_free(data->mem_slab, slab_buffer);
			latch_fault(data, AURA_DMIC_FAULT_PREPARE, ret);
			stop_pdm(data);
			goto done;
		}
		data->dma[slot].slab = slab_buffer;
		data->dma[slot].dma = dma_buffer;
		if (nrfx_pdm_buffer_set(data->pdm, dma_buffer,
					data->block_size / 2) != NRFX_SUCCESS) {
			latch_fault(data, AURA_DMIC_FAULT_HANDOFF, -EIO);
			(void)release_buffer(dev, slot, false);
			stop_pdm(data);
		}
	}

done:
	if (!data->active) {
		stop_pdm(data);
	}
	irq_unlock(key);
}

#ifndef AURA_DMIC_HOST_TEST
static bool is_in_freq_range(uint32_t freq, const struct dmic_cfg *pdm_cfg)
{
	return freq >= pdm_cfg->io.min_pdm_clk_freq && freq <= pdm_cfg->io.max_pdm_clk_freq;
}

static bool is_better(uint32_t freq,
		      uint8_t ratio,
		      uint32_t req_rate,
		      uint32_t *best_diff,
		      uint32_t *best_rate,
		      uint32_t *best_freq)
{
	uint32_t act_rate = freq / ratio;
	uint32_t diff = act_rate >= req_rate ? (act_rate - req_rate)
					     : (req_rate - act_rate);

	LOG_DBG("Freq %u, ratio %u, act_rate %u", freq, ratio, act_rate);

	if (diff < *best_diff) {
		*best_diff = diff;
		*best_rate = act_rate;
		*best_freq = freq;
		return true;
	}

	return false;
}

static bool check_pdm_frequencies(const struct dmic_nrfx_pdm_drv_cfg *drv_cfg,
				  nrfx_pdm_config_t *config,
				  const struct dmic_cfg *pdm_cfg,
				  uint8_t ratio,
				  uint32_t *best_diff,
				  uint32_t *best_rate,
				  uint32_t *best_freq)
{
	uint32_t req_rate = pdm_cfg->streams[0].pcm_rate;
	bool better_found = false;
	const uint32_t src_freq =
		(NRF_PDM_HAS_SELECTABLE_CLOCK && drv_cfg->clk_src == ACLK)
		? DMIC_NRFX_AUDIO_CLOCK_FREQ
		: DMIC_NRFX_CLOCK_FREQ;
#if NRF_PDM_HAS_PRESCALER
	uint32_t req_freq = req_rate * ratio;
	uint32_t prescaler = src_freq / req_freq;
	uint32_t act_freq = src_freq / prescaler;

	if (is_in_freq_range(act_freq, pdm_cfg) &&
	    is_better(act_freq, ratio, req_rate, best_diff, best_rate, best_freq)) {
		config->prescaler = prescaler;

		better_found = true;
	}

	/* Stop if an exact rate match is found. */
	if (*best_diff == 0) {
		return true;
	}

	/* Prescaler value is rounded down by default,
	 * thus value rounded up should be checked as well.
	 */
	prescaler += 1;
	act_freq  = src_freq / prescaler;

	if (is_in_freq_range(act_freq, pdm_cfg) &&
	    is_better(act_freq, ratio, req_rate, best_diff, best_rate, best_freq)) {
		config->prescaler = prescaler;

		better_found = true;
	}
#else
	if (IS_ENABLED(CONFIG_SOC_SERIES_NRF53X) || IS_ENABLED(CONFIG_SOC_SERIES_NRF54HX)) {
		uint32_t req_freq = req_rate * ratio;
		/* As specified in the nRF5340 PS:
		 *
		 * PDMCLKCTRL = 4096 * floor(f_pdm * 1048576 /
		 *                           (f_source + f_pdm / 2))
		 * f_actual = f_source / floor(1048576 * 4096 / PDMCLKCTRL)
		 */
		uint32_t clk_factor = (uint32_t)((req_freq * 1048576ULL) /
						 (src_freq + req_freq / 2));
		uint32_t act_freq = src_freq / (1048576 / clk_factor);

		if (is_in_freq_range(act_freq, pdm_cfg) &&
		    is_better(act_freq, ratio, req_rate, best_diff, best_rate, best_freq)) {
			config->clock_freq = clk_factor * DMIC_NRFX_CLOCK_FACTOR;

			better_found = true;
		}
	} else { /* -> !IS_ENABLED(CONFIG_SOC_SERIES_NRF53X)) */
		static const struct {
			uint32_t       freq_val;
			nrf_pdm_freq_t freq_enum;
		} freqs[] = {
			{ 1000000, NRF_PDM_FREQ_1000K },
			{ 1032000, NRF_PDM_FREQ_1032K },
			{ 1067000, NRF_PDM_FREQ_1067K },
#if defined(PDM_PDMCLKCTRL_FREQ_1231K)
			{ 1231000, NRF_PDM_FREQ_1231K },
#endif
#if defined(PDM_PDMCLKCTRL_FREQ_1280K)
			{ 1280000, NRF_PDM_FREQ_1280K },
#endif
#if defined(PDM_PDMCLKCTRL_FREQ_1333K)
			{ 1333000, NRF_PDM_FREQ_1333K }
#endif
		};

		for (int i = 0; i < ARRAY_SIZE(freqs); ++i) {
			uint32_t freq_val = freqs[i].freq_val;

			if (freq_val < pdm_cfg->io.min_pdm_clk_freq) {
				continue;
			}
			if (freq_val > pdm_cfg->io.max_pdm_clk_freq) {
				break;
			}

			if (is_better(freq_val, ratio, req_rate,
				      best_diff, best_rate, best_freq)) {
				config->clock_freq = freqs[i].freq_enum;

				/* Stop if an exact rate match is found. */
				if (*best_diff == 0) {
					return true;
				}

				better_found = true;
			}

			/* Since frequencies are in ascending order, stop
			 * checking next ones for the current ratio after
			 * resulting PCM rate goes above the one requested.
			 */
			if ((freq_val / ratio) > req_rate) {
				break;
			}
		}
	}
#endif /* NRF_PDM_HAS_PRESCALER */

	return better_found;
}

/* Finds clock settings that give the PCM output rate closest to that requested,
 * taking into account the hardware limitations.
 */
static bool find_suitable_clock(const struct dmic_nrfx_pdm_drv_cfg *drv_cfg,
				nrfx_pdm_config_t *config,
				const struct dmic_cfg *pdm_cfg)
{
	uint32_t best_diff = UINT32_MAX;
	uint32_t best_rate;
	uint32_t best_freq;

#if NRF_PDM_HAS_RATIO_CONFIG
	static const struct {
		uint8_t         ratio_val;
		nrf_pdm_ratio_t ratio_enum;
	} ratios[] = {
#if defined(PDM_RATIO_RATIO_Ratio32)
		{ 32, NRF_PDM_RATIO_32X },
#endif
#if defined(PDM_RATIO_RATIO_Ratio48)
		{ 48, NRF_PDM_RATIO_48X },
#endif
#if defined(PDM_RATIO_RATIO_Ratio50)
		{ 50, NRF_PDM_RATIO_50X },
#endif
		{ 64, NRF_PDM_RATIO_64X },
		{ 80, NRF_PDM_RATIO_80X },
#if defined(PDM_RATIO_RATIO_Ratio96)
		{ 96, NRF_PDM_RATIO_96X },
#endif
#if defined(PDM_RATIO_RATIO_Ratio100)
		{ 100, NRF_PDM_RATIO_100X },
#endif
#if defined(PDM_RATIO_RATIO_Ratio128)
		{ 128, NRF_PDM_RATIO_128X }
#endif
	};

	for (int r = 0; best_diff != 0 && r < ARRAY_SIZE(ratios); ++r) {
		uint8_t ratio = ratios[r].ratio_val;

		if (check_pdm_frequencies(drv_cfg, config, pdm_cfg, ratio,
					  &best_diff, &best_rate, &best_freq)) {
			config->ratio = ratios[r].ratio_enum;

			/* Look no further if a configuration giving the exact
			 * PCM rate is found.
			 */
			if (best_diff == 0) {
				break;
			}
		}
	}
#else
	uint8_t ratio = 64;

	(void)check_pdm_frequencies(drv_cfg, config, pdm_cfg, ratio,
				    &best_diff, &best_rate, &best_freq);
#endif

	if (best_diff == UINT32_MAX) {
		return false;
	}

	LOG_INF("PDM clock frequency: %u, actual PCM rate: %u",
		best_freq, best_rate);
	return true;
}

static int dmic_nrfx_pdm_configure(const struct device *dev,
				   struct dmic_cfg *config)
{
	struct dmic_nrfx_pdm_drv_data *drv_data = dev->data;
	const struct dmic_nrfx_pdm_drv_cfg *drv_cfg = dev->config;
	struct pdm_chan_cfg *channel;
	struct pcm_stream_cfg *stream;
	unsigned int key;
	uint32_t def_map, alt_map;
	nrfx_pdm_config_t nrfx_cfg;
	nrfx_err_t err;

	if (config == NULL || config->streams == NULL) {
		return -EINVAL;
	}
	channel = &config->channel;
	stream = &config->streams[0];
	key = irq_lock();
	if (!fully_drained(drv_data)) {
		irq_unlock(key);
		return -EBUSY;
	}
	if (drv_data->faults != AURA_DMIC_FAULT_NONE) {
		irq_unlock(key);
		return -EIO;
	}
	irq_unlock(key);

	/*
	 * This device supports only one stream and can be configured to return
	 * 16-bit samples for two channels (Left+Right samples) or one channel
	 * (only Left samples). Left and Right samples can be optionally swapped
	 * by changing the PDM_CLK edge on which the sampling is done
	 * Provide the valid channel maps for both the above configurations
	 * (to inform the requester what is available) and check if what is
	 * requested can be actually configured.
	 */
	if (channel->req_num_chan == 1) {
		def_map = dmic_build_channel_map(0, 0, PDM_CHAN_LEFT);
		alt_map = dmic_build_channel_map(0, 0, PDM_CHAN_RIGHT);

		channel->act_num_chan = 1;
	} else {
		def_map = dmic_build_channel_map(0, 0, PDM_CHAN_LEFT)
			| dmic_build_channel_map(1, 0, PDM_CHAN_RIGHT);
		alt_map = dmic_build_channel_map(0, 0, PDM_CHAN_RIGHT)
			| dmic_build_channel_map(1, 0, PDM_CHAN_LEFT);

		channel->act_num_chan = 2;
	}

	channel->act_num_streams = 1;
	channel->act_chan_map_hi = 0;

	if (channel->req_num_streams != 1 ||
	    channel->req_num_chan > 2 ||
	    channel->req_num_chan < 1 ||
	    (channel->req_chan_map_lo != def_map &&
	     channel->req_chan_map_lo != alt_map) ||
	    channel->req_chan_map_hi != channel->act_chan_map_hi) {
		LOG_ERR("Requested configuration is not supported");
		return -EINVAL;
	}

	/* If either rate or width is 0, the stream is to be disabled. */
	if (stream->pcm_rate == 0 || stream->pcm_width == 0) {
		if (drv_data->configured) {
			nrfx_pdm_uninit(drv_data->pdm);
			drv_data->configured = false;
		}

		return 0;
	}

	if (stream->pcm_width != 16) {
		LOG_ERR("Only 16-bit samples are supported");
		return -EINVAL;
	}
	if (stream->mem_slab == NULL || stream->block_size == 0 ||
	    stream->block_size % (2 * channel->req_num_chan) != 0 ||
	    stream->block_size % 4 != 0 || stream->block_size / 2 > 32767 ||
	    stream->block_size > stream->mem_slab->info.block_size ||
	    stream->mem_slab->info.block_size % 4 != 0 ||
	    ((uintptr_t)stream->mem_slab->buffer % 4) != 0 ||
	    k_mem_slab_num_used_get(stream->mem_slab) != 0) {
		return -EINVAL;
	}

	nrfx_cfg = drv_cfg->nrfx_def_cfg;
	nrfx_cfg.mode = channel->req_num_chan == 1
		      ? NRF_PDM_MODE_MONO
		      : NRF_PDM_MODE_STEREO;
	if (channel->req_chan_map_lo == def_map) {
		nrfx_cfg.edge = NRF_PDM_EDGE_LEFTFALLING;
		channel->act_chan_map_lo = def_map;
	} else {
		nrfx_cfg.edge = NRF_PDM_EDGE_LEFTRISING;
		channel->act_chan_map_lo = alt_map;
	}
#if NRF_PDM_HAS_SELECTABLE_CLOCK
	nrfx_cfg.mclksrc = drv_cfg->clk_src == ACLK
			 ? NRF_PDM_MCLKSRC_ACLK
			 : NRF_PDM_MCLKSRC_PCLK32M;
#endif
	if (!find_suitable_clock(drv_cfg, &nrfx_cfg, config)) {
		LOG_ERR("Cannot find suitable PDM clock configuration.");
		return -EINVAL;
	}

	if (drv_data->configured) {
		nrfx_pdm_uninit(drv_data->pdm);
		drv_data->configured = false;
	}

	err = nrfx_pdm_init(drv_data->pdm, &nrfx_cfg, drv_cfg->event_handler);
	if (err != NRFX_SUCCESS) {
		LOG_ERR("Failed to initialize PDM: 0x%08x", err);
		latch_fault(drv_data, AURA_DMIC_FAULT_INIT, -EIO);
		return -EIO;
	}

	drv_data->block_size = stream->block_size;
	drv_data->mem_slab   = stream->mem_slab;

	/* Unless the PCLK32M source is used with the HFINT oscillator
	 * (which is always available without any additional actions),
	 * it is required to request the proper clock to be running
	 * before starting the transfer itself.
	 * Targets using CLKSELECT register to select clock source
	 * do not need to request audio clock.
	 */
	drv_data->request_clock = (drv_cfg->clk_src != PCLK32M && !NRF_PDM_HAS_CLKSELECT);
	drv_data->configured = true;
	return 0;
}

#endif /* !AURA_DMIC_HOST_TEST */

static int start_transfer(struct dmic_nrfx_pdm_drv_data *data)
{
	if (!data->active || data->stopping || data->faults != AURA_DMIC_FAULT_NONE) {
		finish_stop(data);
		return -ECANCELED;
	}
	if (nrfx_pdm_start(data->pdm) != NRFX_SUCCESS) {
		latch_fault(data, AURA_DMIC_FAULT_START, -EIO);
		stop_pdm(data);
		return -EIO;
	}
	return 0;
}

static void clock_started_callback(struct onoff_manager *mgr,
				   struct onoff_client *cli,
				   uint32_t state, int res)
{
	struct dmic_nrfx_pdm_drv_data *data =
		CONTAINER_OF(cli, struct dmic_nrfx_pdm_drv_data, clk_cli);
	unsigned int key = irq_lock();

	ARG_UNUSED(mgr);
	ARG_UNUSED(state);
	data->clock_pending = false;
	if (res < 0) {
		/* onoff failed transitions do not grant a reference to this client. */
		data->clock_owned = false;
		latch_fault(data, AURA_DMIC_FAULT_CLOCK, res);
		stop_pdm(data);
	} else if (!data->active || data->stopping) {
		finish_stop(data);
	} else {
		(void)start_transfer(data);
	}
	irq_unlock(key);
}

static int trigger_start(const struct device *dev)
{
	struct dmic_nrfx_pdm_drv_data *data = dev->data;
	int ret;

	data->active = true;
	data->hw_started = false;
	if (data->request_clock) {
		/* onoff_request may invoke its callback synchronously. */
		data->clock_pending = true;
		data->clock_owned = true;
		sys_notify_init_callback(&data->clk_cli.notify, clock_started_callback);
		ret = request_clock(data);
		if (ret < 0) {
			data->clock_pending = false;
			data->clock_owned = false;
			latch_fault(data, AURA_DMIC_FAULT_CLOCK, ret);
			stop_pdm(data);
			return -EIO;
		}
		return data->faults == AURA_DMIC_FAULT_NONE ? 0 : -EIO;
	}
	return start_transfer(data);
}

static int dmic_nrfx_pdm_trigger(const struct device *dev, enum dmic_trigger cmd)
{
	struct dmic_nrfx_pdm_drv_data *data = dev->data;
	unsigned int key = irq_lock();
	int ret = 0;

	switch (cmd) {
	case DMIC_TRIGGER_PAUSE:
	case DMIC_TRIGGER_STOP:
		stop_pdm(data);
		break;
	case DMIC_TRIGGER_RELEASE:
	case DMIC_TRIGGER_START:
		if (!data->configured || data->faults != AURA_DMIC_FAULT_NONE) {
			ret = -EIO;
		} else if (data->active) {
			ret = 0;
		} else if (!fully_drained(data)) {
			ret = -EBUSY;
		} else {
			ret = trigger_start(dev);
		}
		break;
	default:
		ret = -EINVAL;
		break;
	}
	irq_unlock(key);
	return ret;
}

static int dmic_nrfx_pdm_read(const struct device *dev, uint8_t stream,
			      void **buffer, size_t *size, int32_t timeout)
{
	struct dmic_nrfx_pdm_drv_data *data = dev->data;
	struct aura_rx_block block;
	unsigned int key;
	int ret;

	if (stream != 0 || buffer == NULL || size == NULL) {
		return -EINVAL;
	}
	*buffer = NULL;
	*size = 0;
	key = irq_lock();
	if (!data->configured) {
		irq_unlock(key);
		return -EIO;
	}
	/* Faulted/stopped queue draining must never block waiting for new data. */
	if (data->faults != AURA_DMIC_FAULT_NONE || !data->active) {
		timeout = 0;
	}
	irq_unlock(key);
	ret = k_msgq_get(&data->rx_queue, &block, SYS_TIMEOUT_MS(timeout));
	key = irq_lock();
	if (ret == 0) {
		*buffer = block.buffer;
		*size = data->block_size;
		data->last_read_sequence = block.sequence;
		++data->delivered_blocks;
	} else if (data->faults != AURA_DMIC_FAULT_NONE) {
		ret = -EIO;
	}
	irq_unlock(key);
	return ret;
}

int aura_dmic_health_get(const struct device *dev, struct aura_dmic_health *health)
{
	struct dmic_nrfx_pdm_drv_data *data;
	unsigned int key;

	if (dev == NULL || health == NULL) {
		return -EINVAL;
	}
	if (dev->api != &dmic_ops || dev->data == NULL || !device_is_ready(dev)) {
		return -ENOTSUP;
	}
	data = dev->data;
	key = irq_lock();
	*health = (struct aura_dmic_health) {
		.faults = data->faults,
		.first_error = data->first_error,
		.epoch = data->epoch,
		.completed_blocks = data->completed_blocks,
		.delivered_blocks = data->delivered_blocks,
		.last_read_sequence = data->last_read_sequence,
		.queued_blocks = k_msgq_num_used_get(&data->rx_queue),
		.slab_used_blocks = data->mem_slab == NULL ? 0 :
			k_mem_slab_num_used_get(data->mem_slab),
		.owned_dma_buffers = owned_buffers(data),
		.configured = data->configured,
		.active = data->active,
		.stopping = data->stopping,
		.clock_pending = data->clock_pending,
		.stopped = fully_stopped(data),
		.drained = fully_drained(data),
	};
	irq_unlock(key);
	return 0;
}

int aura_dmic_health_reset(const struct device *dev)
{
	struct dmic_nrfx_pdm_drv_data *data;
	unsigned int key;

	if (dev == NULL) {
		return -EINVAL;
	}
	if (dev->api != &dmic_ops || dev->data == NULL || !device_is_ready(dev)) {
		return -ENOTSUP;
	}
	data = dev->data;
	key = irq_lock();
	if (!fully_drained(data)) {
		irq_unlock(key);
		return -EBUSY;
	}
	data->faults = AURA_DMIC_FAULT_NONE;
	data->first_error = 0;
	data->completed_blocks = 0;
	data->delivered_blocks = 0;
	data->last_read_sequence = 0;
	++data->epoch;
	irq_unlock(key);
	return 0;
}

#ifndef AURA_DMIC_HOST_TEST
static void init_clock_manager(const struct device *dev)
{
#if CONFIG_CLOCK_CONTROL_NRF
	clock_control_subsys_t subsys;
	struct dmic_nrfx_pdm_drv_data *drv_data = dev->data;
#if NRF_CLOCK_HAS_HFCLKAUDIO
	const struct dmic_nrfx_pdm_drv_cfg *drv_cfg = dev->config;

	if (drv_cfg->clk_src == ACLK) {
		subsys = CLOCK_CONTROL_NRF_SUBSYS_HFAUDIO;
	} else
#endif
	{
		subsys = CLOCK_CONTROL_NRF_SUBSYS_HF;
	}

	drv_data->clk_mgr = z_nrf_clock_control_get_onoff(subsys);
	__ASSERT_NO_MSG(drv_data->clk_mgr != NULL);
#elif CONFIG_CLOCK_CONTROL_NRFS_AUDIOPLL
	struct dmic_nrfx_pdm_drv_data *drv_data = dev->data;

	drv_data->audiopll_dev = DEVICE_DT_GET(DT_NODELABEL(audiopll));
#endif
}

static const struct _dmic_ops dmic_ops = {
	.configure = dmic_nrfx_pdm_configure,
	.trigger = dmic_nrfx_pdm_trigger,
	.read = dmic_nrfx_pdm_read,
};

#define PDM(idx) DT_NODELABEL(pdm##idx)
#define PDM_CLK_SRC(idx) DT_STRING_TOKEN(PDM(idx), clock_source)

#define PDM_NRFX_DEVICE(idx)						     \
	static struct aura_rx_block rx_msgs##idx[DT_PROP(PDM(idx), queue_size)];	     \
	static struct dmic_nrfx_pdm_drv_data dmic_nrfx_pdm_data##idx;	     \
	static const nrfx_pdm_t dmic_nrfx_pdm##idx = NRFX_PDM_INSTANCE(idx); \
	static int pdm_nrfx_init##idx(const struct device *dev)		     \
	{								     \
		IRQ_CONNECT(DT_IRQN(PDM(idx)), DT_IRQ(PDM(idx), priority),   \
			    nrfx_isr, nrfx_pdm_##idx##_irq_handler, 0);      \
		const struct dmic_nrfx_pdm_drv_cfg *drv_cfg = dev->config;   \
		int err = pinctrl_apply_state(drv_cfg->pcfg,		     \
					      PINCTRL_STATE_DEFAULT);	     \
		if (err < 0) {						     \
			return err;					     \
		}							     \
		dmic_nrfx_pdm_data##idx.pdm = &dmic_nrfx_pdm##idx;	     \
		k_msgq_init(&dmic_nrfx_pdm_data##idx.rx_queue,		     \
			    (char *)rx_msgs##idx, sizeof(struct aura_rx_block),	     \
			    ARRAY_SIZE(rx_msgs##idx));			     \
		init_clock_manager(dev);				     \
		return 0;						     \
	}								     \
	static void event_handler##idx(const nrfx_pdm_evt_t *evt)	     \
	{								     \
		event_handler(DEVICE_DT_GET(PDM(idx)), evt);		     \
	}								     \
	PINCTRL_DT_DEFINE(PDM(idx));					     \
	static const struct dmic_nrfx_pdm_drv_cfg dmic_nrfx_pdm_cfg##idx = { \
		.event_handler = event_handler##idx,			     \
		.nrfx_def_cfg =	NRFX_PDM_DEFAULT_CONFIG(0, 0),		     \
		.nrfx_def_cfg.skip_gpio_cfg = true,			     \
		.nrfx_def_cfg.skip_psel_cfg = true,			     \
		.pcfg = PINCTRL_DT_DEV_CONFIG_GET(PDM(idx)),		     \
		.clk_src = PDM_CLK_SRC(idx),				     \
		.mem_reg = DMM_DEV_TO_REG(PDM(idx)),			     \
	};								     \
	BUILD_ASSERT(PDM_CLK_SRC(idx) != ACLK ||			     \
		     NRF_PDM_HAS_SELECTABLE_CLOCK,			     \
		"Clock source ACLK is not available.");			     \
	BUILD_ASSERT(PDM_CLK_SRC(idx) != ACLK ||			     \
		     DT_NODE_HAS_PROP(DT_NODELABEL(clock),		     \
				      hfclkaudio_frequency) ||		     \
		     DT_NODE_HAS_PROP(DT_NODELABEL(aclk),		     \
				      clock_frequency) ||		     \
		     DT_NODE_HAS_PROP(DT_NODELABEL(audiopll),		     \
				      frequency),			     \
		"Clock source ACLK requires the hfclkaudio-frequency "	     \
		"property to be defined in the nordic,nrf-clock node "	     \
		"or clock-frequency property to be defined in aclk node"     \
		"or frequency property to be defined in audiopll node");     \
	DEVICE_DT_DEFINE(PDM(idx), pdm_nrfx_init##idx, NULL,		     \
			 &dmic_nrfx_pdm_data##idx, &dmic_nrfx_pdm_cfg##idx,  \
			 POST_KERNEL, CONFIG_AUDIO_DMIC_INIT_PRIORITY,	     \
			 &dmic_ops);

BUILD_ASSERT(DT_NODE_HAS_COMPAT(PDM(0), aura_nrf_pdm),
	"AURA DMIC requires the aura,nrf-pdm compatible on pdm0");
BUILD_ASSERT(!IS_ENABLED(CONFIG_AUDIO_DMIC_NRFX_PDM),
	"Stock and AURA DMIC drivers cannot own the same peripheral");
PDM_NRFX_DEVICE(0);
#else
static const struct _dmic_ops dmic_ops = {
	.trigger = dmic_nrfx_pdm_trigger,
	.read = dmic_nrfx_pdm_read,
};
#endif /* !AURA_DMIC_HOST_TEST */
