/* SPDX-License-Identifier: MIT -- deterministic host stub, not a scheduler. */
#ifndef AUDIO_STUB_KERNEL_H
#define AUDIO_STUB_KERNEL_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define __aligned(n) __attribute__((aligned(n)))
#define K_NO_WAIT 0
struct device { bool ready; };
static inline bool device_is_ready(const struct device *d){return d&&d->ready;}
struct k_mem_slab { char *buffer; size_t block_size; uint32_t blocks, used, mask; };
struct k_msgq { char *buffer; size_t msg_size; uint32_t capacity, head, used; };
struct k_spinlock { unsigned unused; };
typedef unsigned k_spinlock_key_t;
k_spinlock_key_t k_spin_lock(struct k_spinlock *);
void k_spin_unlock(struct k_spinlock *,k_spinlock_key_t);
int k_mem_slab_init(struct k_mem_slab *,void *,size_t,uint32_t);
void k_mem_slab_free(struct k_mem_slab *,void *);
uint32_t k_mem_slab_num_used_get(struct k_mem_slab *);
void k_msgq_init(struct k_msgq *,char *,size_t,uint32_t);
int k_msgq_put(struct k_msgq *,const void *,int);
int k_msgq_get(struct k_msgq *,void *,int);
uint32_t k_msgq_num_used_get(struct k_msgq *);
int64_t k_uptime_get(void);
void k_msleep(int32_t);
#endif
