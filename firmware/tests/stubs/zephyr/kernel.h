#ifndef AURA_TEST_KERNEL
#define AURA_TEST_KERNEL
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
static int64_t test_clock;
static inline int64_t k_uptime_get(void)
{
    return test_clock++;
}
static inline void k_msleep(int ms)
{
    test_clock += ms;
}
static inline void k_usleep(int us)
{
    (void)us;
}
#endif
