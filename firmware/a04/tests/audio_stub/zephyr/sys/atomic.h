/* SPDX-License-Identifier: MIT -- serialized deterministic host interleavings. */
#ifndef AUDIO_STUB_ATOMIC_H
#define AUDIO_STUB_ATOMIC_H
#include <stdbool.h>
typedef long atomic_t;
typedef long atomic_val_t;
static inline atomic_val_t atomic_get(const atomic_t *a){return *a;}
static inline atomic_val_t atomic_set(atomic_t *a,atomic_val_t v){atomic_val_t old=*a;*a=v;return old;}
static inline atomic_val_t atomic_clear(atomic_t *a){return atomic_set(a,0);}
static inline atomic_val_t atomic_inc(atomic_t *a){return (*a)++;}
static inline bool atomic_cas(atomic_t *a,atomic_val_t old,atomic_val_t v){if(*a!=old)return false;*a=v;return true;}
#endif
