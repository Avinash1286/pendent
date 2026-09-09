/* SPDX-License-Identifier: Apache-2.0
 * Host-only substitutes for the external kernel/HAL boundaries. The test
 * translation unit includes the production driver callback/lifecycle code.
 */
#ifndef AURA_DRIVER_SHIM_H
#define AURA_DRIVER_SHIM_H
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <errno.h>
#define CONFIG_CLOCK_CONTROL_NRF 1
#define CONFIG_AUDIO_DMIC_LOG_LEVEL 0
#define LOG_MODULE_REGISTER(...)
#define LOG_DBG(...)
#define LOG_INF(...)
#define LOG_ERR(...)
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define CONTAINER_OF(p, t, m) ((t *)((char *)(p) - offsetof(t, m)))
#define ARG_UNUSED(x) ((void)(x))
#define K_NO_WAIT 0
#define SYS_TIMEOUT_MS(x) (x)
#define NRFX_SUCCESS 0
#define NRFX_ERROR_BUSY 1
#define NRFX_PDM_NO_ERROR 0
#define NRFX_PDM_ERROR_OVERFLOW 1

enum dmic_trigger { DMIC_TRIGGER_STOP, DMIC_TRIGGER_START,
	DMIC_TRIGGER_PAUSE, DMIC_TRIGGER_RELEASE };
struct device { void *data; const void *config; const void *api; bool ready; };
struct _dmic_ops {
	int (*trigger)(const struct device *, enum dmic_trigger);
	int (*read)(const struct device *, uint8_t, void **, size_t *, int32_t);
};
static bool device_is_ready(const struct device *dev) { return dev->ready; }
static unsigned int irq_lock(void) { return 0; }
static void irq_unlock(unsigned int key) { (void)key; }

struct k_mem_slab { uint32_t used; bool allocated[8]; uint32_t blocks[8][320]; };
struct k_msgq { unsigned int used, capacity; unsigned char messages[4][32]; };
static int slab_error, prepare_error, release_error, handoff_error;
static int start_error, stop_error, clock_request_error, clock_release_error;
static bool clock_sync;
static int clock_result, start_calls, stop_calls, clock_releases;
static size_t message_size;

static int k_mem_slab_alloc(struct k_mem_slab *s, void **p, int timeout)
{
	(void)timeout;
	if (slab_error) { return slab_error; }
	for (unsigned int i = 0; i < 8; ++i) {
		if (!s->allocated[i]) {
			s->allocated[i] = true; ++s->used; *p = s->blocks[i]; return 0;
		}
	}
	return -ENOMEM;
}
static void k_mem_slab_free(struct k_mem_slab *s, void *p)
{
	for (unsigned int i = 0; i < 8; ++i) {
		if (p == s->blocks[i]) {
			assert(s->allocated[i]); s->allocated[i] = false; --s->used; return;
		}
	}
	assert(!"free of foreign pointer");
}
static uint32_t k_mem_slab_num_used_get(struct k_mem_slab *s) { return s->used; }
static unsigned int k_msgq_num_used_get(struct k_msgq *q) { return q->used; }
static int k_msgq_put(struct k_msgq *q, const void *p, int timeout)
{
	(void)timeout;
	if (q->used >= q->capacity) { return -ENOMSG; }
	memcpy(q->messages[q->used++], p, message_size); return 0;
}
static int k_msgq_get(struct k_msgq *q, void *p, int timeout)
{
	(void)timeout;
	if (!q->used) { return -ENOMSG; }
	memcpy(p, q->messages[0], message_size); --q->used;
	memmove(q->messages[0], q->messages[1], q->used * sizeof(q->messages[0]));
	return 0;
}
static int dmm_buffer_in_prepare(void *region, void *p, size_t size, void **dma)
{
	(void)region; (void)size;
	if (prepare_error) { return prepare_error; }
	*dma = p; return 0;
}
static int dmm_buffer_in_release(void *region, void *p, size_t size, void *dma)
{
	(void)region; (void)size; assert(p == dma); return release_error;
}

typedef int nrfx_err_t;
typedef struct { bool enabled; int state; } nrfx_pdm_t;
enum { MOCK_IDLE, MOCK_STARTING, MOCK_RUNNING, MOCK_STOPPING };
typedef struct { bool buffer_requested; void *buffer_released; int error; } nrfx_pdm_evt_t;
typedef void (*nrfx_pdm_event_handler_t)(const nrfx_pdm_evt_t *);
typedef struct { int unused; } nrfx_pdm_config_t;
struct pinctrl_dev_config { int unused; };
static bool nrfx_pdm_enable_check(const nrfx_pdm_t *p) { return p->enabled; }
static int nrfx_pdm_start(const nrfx_pdm_t *p)
{
	++start_calls;
	if (!start_error) { ((nrfx_pdm_t *)p)->state = MOCK_STARTING; }
	return start_error;
}
static int nrfx_pdm_buffer_set(const nrfx_pdm_t *p, void *buffer, size_t samples)
{
	assert(buffer != NULL && samples == 640);
	if (!handoff_error) { ((nrfx_pdm_t *)p)->enabled = true; }
	return handoff_error;
}
static int nrfx_pdm_stop(const nrfx_pdm_t *p)
{
	++stop_calls;
	if (stop_error) { return stop_error; }
	nrfx_pdm_t *m = (nrfx_pdm_t *)p;
	if (m->state == MOCK_STOPPING) { return NRFX_ERROR_BUSY; }
	if (m->state == MOCK_RUNNING) { m->state = MOCK_STOPPING; }
	else { m->state = MOCK_IDLE; m->enabled = false; }
	return NRFX_SUCCESS;
}

struct onoff_manager { int unused; };
struct onoff_client;
typedef void (*clock_cb_t)(struct onoff_manager *, struct onoff_client *, uint32_t, int);
struct sys_notify { clock_cb_t cb; };
struct onoff_client { struct sys_notify notify; };
static struct onoff_client *pending_clock;
static void sys_notify_init_callback(struct sys_notify *n, clock_cb_t cb) { n->cb = cb; }
static int onoff_request(struct onoff_manager *m, struct onoff_client *c)
{
	if (clock_request_error) { return clock_request_error; }
	if (clock_sync) { c->notify.cb(m, c, 0, clock_result); }
	else { pending_clock = c; }
	return 0;
}
static int onoff_release(struct onoff_manager *m)
{
	(void)m; ++clock_releases; return clock_release_error;
}
#endif
