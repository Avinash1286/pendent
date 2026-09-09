/* SPDX-License-Identifier: Apache-2.0 */
#define AURA_DMIC_HOST_TEST 1
#include "../aura_dmic_nrfx_pdm.c"
#include <stdio.h>

static struct dmic_nrfx_pdm_drv_data data;
static struct dmic_nrfx_pdm_drv_cfg cfg;
static struct k_mem_slab slab;
static nrfx_pdm_t pdm;
static struct device dev = { .data = &data, .config = &cfg, .api = &dmic_ops, .ready = true };
static unsigned int groups;

static void setup(void)
{
	memset(&data, 0, sizeof(data)); memset(&cfg, 0, sizeof(cfg));
	memset(&slab, 0, sizeof(slab)); memset(&pdm, 0, sizeof(pdm));
	slab_error = prepare_error = release_error = handoff_error = 0;
	start_error = stop_error = clock_request_error = clock_release_error = 0;
	clock_sync = false; clock_result = 0;
	start_calls = stop_calls = clock_releases = 0; pending_clock = NULL;
	data.pdm = &pdm; data.mem_slab = &slab; data.block_size = 1280;
	data.rx_queue.capacity = 4; data.configured = true;
	message_size = sizeof(struct aura_rx_block);
	assert(message_size <= sizeof(data.rx_queue.messages[0]));
}

static struct aura_dmic_health health(void)
{
	struct aura_dmic_health h;
	assert(aura_dmic_health_get(&dev, &h) == 0); return h;
}
static void emit(bool request, void *release, int error)
{
	nrfx_pdm_evt_t evt = { request, release, error }; event_handler(&dev, &evt);
}
static void running(void)
{
	assert(dmic_nrfx_pdm_trigger(&dev, DMIC_TRIGGER_START) == 0);
	emit(true, NULL, 0); /* software request of initial DMA buffer */
	pdm.state = MOCK_RUNNING;
	emit(true, NULL, 0); /* hardware STARTED requests second buffer */
	assert(health().owned_dma_buffers == 2);
}
static void stopped_event(void)
{
	pdm.enabled = false; pdm.state = MOCK_IDLE;
	void *first = data.dma[0].dma, *second = data.dma[1].dma;
	if (first) { emit(false, first, 0); }
	if (second) { emit(false, second, 0); }
}
static void drain(void)
{
	void *p; size_t size;
	while (dmic_nrfx_pdm_read(&dev, 0, &p, &size, 0) == 0) {
		assert(size == 1280); k_mem_slab_free(&slab, p);
	}
}
static void check_fault(enum aura_dmic_fault fault)
{
	assert((health().faults & fault) != 0);
	assert(dmic_nrfx_pdm_trigger(&dev, DMIC_TRIGGER_START) == -EIO);
}
static void pass(const char *name) { ++groups; printf("PASS %s\n", name); }

int main(void)
{
	struct aura_dmic_health h;
	void *p; size_t size;
	setup();
	struct device stock = { .ready = true, .data = (void *)1, .api = (void *)2 };
	assert(aura_dmic_health_get(&stock, &h) == -ENOTSUP);
	assert(aura_dmic_health_reset(&stock) == -ENOTSUP);
	assert(aura_dmic_health_get(NULL, &h) == -EINVAL);
	assert(aura_dmic_health_get(&dev, NULL) == -EINVAL);
	pass("reject foreign API before data access");

	setup(); running();
	assert(aura_dmic_health_reset(&dev) == -EBUSY);
	emit(true, data.dma[0].dma, 0);
	assert(dmic_nrfx_pdm_read(&dev, 0, &p, &size, 0) == 0);
	h = health(); assert(h.completed_blocks == 1 && h.delivered_blocks == 1);
	assert(h.last_read_sequence == 1 && size == 1280);
	assert(dmic_nrfx_pdm_trigger(&dev, DMIC_TRIGGER_STOP) == 0);
	h = health(); assert(!h.active && h.stopping && !h.stopped);
	stopped_event();
	h = health(); assert(h.stopped && !h.drained && h.slab_used_blocks == 1);
	assert(aura_dmic_health_reset(&dev) == -EBUSY);
	assert(dmic_nrfx_pdm_trigger(&dev, DMIC_TRIGGER_START) == -EBUSY);
	k_mem_slab_free(&slab, p);
	assert(health().drained && aura_dmic_health_reset(&dev) == 0);
	h = health(); assert(h.epoch == 1 && h.last_read_sequence == 0 && h.completed_blocks == 0);
	pass("normal sequence and caller-owned buffer reset/restart guard");

	setup(); running();
	emit(true, data.dma[0].dma, 0); emit(true, data.dma[1].dma, 0);
	dmic_nrfx_pdm_trigger(&dev, DMIC_TRIGGER_STOP); stopped_event();
	assert(health().completed_blocks == 2 && !health().drained);
	for (uint64_t seq = 1; seq <= 2; ++seq) {
		assert(dmic_nrfx_pdm_read(&dev, 0, &p, &size, 0) == 0);
		assert(health().last_read_sequence == seq); k_mem_slab_free(&slab, p);
	}
	assert(health().drained); pass("queued full blocks survive STOP; partial returns excluded");

	setup(); running(); emit(true, data.dma[0].dma, 0);
	emit(false, NULL, NRFX_PDM_ERROR_OVERFLOW); check_fault(AURA_DMIC_FAULT_OVERFLOW);
	assert(health().completed_blocks == 1 && health().stopping);
	stopped_event(); drain(); assert(health().drained);
	assert(dmic_nrfx_pdm_read(&dev, 0, &p, &size, 0) == -EIO);
	assert(aura_dmic_health_reset(&dev) == 0 && health().faults == 0);
	pass("standalone nrfx overflow latched; preceding queue remains drainable");

	setup(); running(); slab_error = -ENOMEM;
	emit(true, data.dma[0].dma, 0); check_fault(AURA_DMIC_FAULT_SLAB);
	stopped_event(); drain(); assert(health().drained);
	pass("slab exhaustion is a terminal transfer fault");

	setup(); running(); prepare_error = -EIO;
	emit(true, data.dma[0].dma, 0); check_fault(AURA_DMIC_FAULT_PREPARE);
	stopped_event(); drain(); assert(health().drained);
	pass("prepare failure releases unowned slab allocation");

	setup(); running(); handoff_error = NRFX_ERROR_BUSY;
	emit(true, data.dma[0].dma, 0); check_fault(AURA_DMIC_FAULT_HANDOFF);
	assert(health().owned_dma_buffers == 1);
	stopped_event(); drain(); assert(health().drained);
	pass("buffer_set failure returns prepared but unsubmitted allocation");

	setup(); running(); data.rx_queue.capacity = 1;
	emit(true, data.dma[0].dma, 0); emit(true, data.dma[1].dma, 0);
	check_fault(AURA_DMIC_FAULT_RX_QUEUE);
	assert(health().completed_blocks == 2 && health().queued_blocks == 1);
	stopped_event(); drain(); assert(health().drained);
	pass("RX overflow counts observed completion and stops without leaking it");

	setup(); running(); emit(false, (void *)42, 0);
	check_fault(AURA_DMIC_FAULT_OWNERSHIP);
	assert(health().owned_dma_buffers == 2);
	stopped_event(); assert(health().drained);
	pass("foreign release never frees or steals a registered allocation");

	setup(); running(); release_error = -EIO;
	emit(true, data.dma[0].dma, 0); check_fault(AURA_DMIC_FAULT_RELEASE);
	stopped_event(); assert(!health().drained && health().owned_dma_buffers == 2);
	assert(aura_dmic_health_reset(&dev) == -EBUSY);
	pass("uncertain DMM release preserves ownership and blocks reset");

	setup(); data.request_clock = true;
	assert(dmic_nrfx_pdm_trigger(&dev, DMIC_TRIGGER_START) == 0);
	assert(health().clock_pending && health().active);
	dmic_nrfx_pdm_trigger(&dev, DMIC_TRIGGER_STOP);
	assert(!health().active && health().stopping && !health().stopped);
	pending_clock->notify.cb(NULL, pending_clock, 0, 0);
	assert(start_calls == 0 && clock_releases == 1 && health().drained);
	emit(true, NULL, 0); assert(health().slab_used_blocks == 0);
	pass("STOP while clock starts cannot start late or allocate from late IRQ");

	setup(); data.request_clock = true; clock_request_error = -EAGAIN;
	assert(dmic_nrfx_pdm_trigger(&dev, DMIC_TRIGGER_START) == -EIO);
	check_fault(AURA_DMIC_FAULT_CLOCK);
	assert(health().drained && clock_releases == 0);
	pass("clock request rejection has no owned reference");

	setup(); data.request_clock = true;
	dmic_nrfx_pdm_trigger(&dev, DMIC_TRIGGER_START);
	pending_clock->notify.cb(NULL, pending_clock, 0, -EIO);
	check_fault(AURA_DMIC_FAULT_CLOCK);
	assert(start_calls == 0 && clock_releases == 0 && health().drained);
	pass("asynchronous clock failure prevents start");

	setup(); data.request_clock = true; clock_sync = true; start_error = 2;
	assert(dmic_nrfx_pdm_trigger(&dev, DMIC_TRIGGER_START) == -EIO);
	check_fault(AURA_DMIC_FAULT_START);
	assert(clock_releases == 1 && health().drained);
	pass("synchronous clock callback preserves nrfx start failure");

	setup(); data.request_clock = true; clock_sync = true;
	assert(dmic_nrfx_pdm_trigger(&dev, DMIC_TRIGGER_START) == 0);
	clock_release_error = -EIO; dmic_nrfx_pdm_trigger(&dev, DMIC_TRIGGER_STOP);
	check_fault(AURA_DMIC_FAULT_CLOCK);
	assert(!health().stopped && aura_dmic_health_reset(&dev) == -EBUSY);
	pass("clock release failure cannot claim quiescence");

	setup(); dmic_nrfx_pdm_trigger(&dev, DMIC_TRIGGER_START);
	dmic_nrfx_pdm_trigger(&dev, DMIC_TRIGGER_STOP);
	assert(health().drained); emit(true, NULL, 0);
	assert(health().slab_used_blocks == 0);
	pass("STOP before first software buffer request ignores late request");

	setup(); dmic_nrfx_pdm_trigger(&dev, DMIC_TRIGGER_START); emit(true, NULL, 0);
	assert(pdm.state == MOCK_STARTING && health().owned_dma_buffers == 1);
	dmic_nrfx_pdm_trigger(&dev, DMIC_TRIGGER_STOP);
	assert(stop_calls == 0 && !health().stopped && health().stopping);
	pdm.state = MOCK_RUNNING; emit(true, NULL, 0);
	assert(pdm.state == MOCK_STOPPING && health().owned_dma_buffers == 1);
	stopped_event(); assert(health().drained && health().completed_blocks == 0);
	pass("STOP after DMA arm waits STARTED before nrfx stop and returns partial buffer");

	setup(); running(); stop_error = 3;
	dmic_nrfx_pdm_trigger(&dev, DMIC_TRIGGER_STOP); check_fault(AURA_DMIC_FAULT_STOP);
	assert(!health().stopped); stop_error = 0;
	dmic_nrfx_pdm_trigger(&dev, DMIC_TRIGGER_STOP); stopped_event();
	assert(health().drained); pass("stop error remains latched after a later successful shutdown");

	setup(); running(); emit(false, NULL, NRFX_PDM_ERROR_OVERFLOW);
	int first = health().first_error; emit(false, (void *)42, 0);
	assert(health().first_error == first);
	assert(health().faults == (AURA_DMIC_FAULT_OVERFLOW | AURA_DMIC_FAULT_OWNERSHIP));
	stopped_event(); pass("sticky faults accumulate while preserving first error");

	setup(); p = (void *)42; size = 42;
	assert(dmic_nrfx_pdm_read(&dev, 1, &p, &size, 0) == -EINVAL);
	assert(dmic_nrfx_pdm_read(&dev, 0, NULL, &size, 0) == -EINVAL);
	assert(dmic_nrfx_pdm_read(&dev, 0, &p, &size, 0) == -ENOMSG);
	assert(p == NULL && size == 0);
	pass("read validates stream/output pointers and clears outputs on empty queue");
	printf("%u production-driver callback/lifecycle test groups passed\n", groups);
	return 0;
}
