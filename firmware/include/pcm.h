#ifndef AURA_PCM_H
#define AURA_PCM_H
#include <stdint.h>
/* A wide accumulator prevents overflow when both channels approach full scale. */
static inline int16_t aura_mix(int16_t left, int16_t right)
{
    return (int16_t)(((int32_t)left + right) / 2);
}
#endif
