/* SPDX-License-Identifier: MIT -- deterministic host doubles, no scheduler. */
#ifndef BENCH_STUB_KERNEL_H
#define BENCH_STUB_KERNEL_H
#include "../../../../tests/audio_stub/zephyr/kernel.h"
#define ARG_UNUSED(x) ((void)(x))
#define MIN(a,b) ((a)<(b)?(a):(b))
#define BIT(n) (1u<<(n))
#define K_PRIO_PREEMPT(n) (n)
#define K_THREAD_STACK_DEFINE(n,s) char n[s]
#define K_THREAD_STACK_SIZEOF(n) sizeof(n)
#define K_MSGQ_DEFINE(n,s,c,a) static char n##_memory[(s)*(c)] __aligned(a); \
    struct k_msgq n={.buffer=n##_memory,.msg_size=(s),.capacity=(c)}
#define DT_CHOSEN(n) 0
#define DT_ALIAS(n) 5
#define DT_NODELABEL(n) BENCH_NODE_##n
#define BENCH_NODE_bench_mic_enable 1
#define BENCH_NODE_bench_privacy 2
#define BENCH_NODE_pdm0 3
#define BENCH_NODE_bench_nand 4
#define BENCH_NODE_bench_controls 1
extern struct device bench_devices[6];
#define DEVICE_DT_GET(n) (&bench_devices[n])
struct k_thread { unsigned unused; };
struct k_mutex { unsigned unused; };
typedef void (*k_thread_entry_t)(void *,void *,void *);
struct k_thread *k_thread_create(struct k_thread *,char *,size_t,k_thread_entry_t,
    void *,void *,void *,int,unsigned,int);
int k_thread_stack_space_get(const struct k_thread *,size_t *);
uint32_t k_cycle_get_32(void);
uint32_t k_cyc_to_us_floor32(uint32_t);
void k_yield(void);
#endif
