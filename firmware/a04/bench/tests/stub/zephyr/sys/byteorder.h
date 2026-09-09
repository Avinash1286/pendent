/* SPDX-License-Identifier: MIT */
#include <stdint.h>
static inline uint64_t sys_get_le64(const uint8_t *p)
{uint64_t n=0;for(unsigned i=0;i<8;++i)n|=(uint64_t)p[i]<<(8*i);return n;}
