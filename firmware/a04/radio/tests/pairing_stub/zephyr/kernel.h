#ifndef AURA_PAIRING_TEST_KERNEL_H
#define AURA_PAIRING_TEST_KERNEL_H
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#define CONFIG_BT_SMP_SC_ONLY 1
#define CONFIG_BT_SMP_APP_PAIRING_ACCEPT 1
#define CONFIG_BT_FIXED_PASSKEY 0
#define CONFIG_BT_USE_DEBUG_KEYS 0
#define CONFIG_BT_STORE_DEBUG_KEYS 0
#define IS_ENABLED(v) (v)
#define BUILD_ASSERT(v,m) _Static_assert(v,m)
#define ARG_UNUSED(v) (void)(v)
#define K_TIMEOUT_ABS_MS(v) ((int64_t)(v))
struct k_spinlock { bool held; };
typedef unsigned k_spinlock_key_t;
struct k_work { void (*handler)(struct k_work *); };
struct k_work_delayable { struct k_work work; int64_t deadline; bool scheduled; };
void check_at(int ok,const char *message,int line);
#define STUB_CHECK(v) check_at((v),#v,__LINE__)
extern int64_t test_now;
static inline int64_t k_uptime_get(void) { return test_now; }
static inline k_spinlock_key_t k_spin_lock(struct k_spinlock *s)
{ STUB_CHECK(!s->held);s->held=true;return 0; }
static inline void k_spin_unlock(struct k_spinlock *s,k_spinlock_key_t key)
{ (void)key;STUB_CHECK(s->held);s->held=false; }
static inline void k_work_init_delayable(struct k_work_delayable *w,void (*fn)(struct k_work *))
{ w->work.handler=fn;w->scheduled=false;w->deadline=0; }
static inline int k_work_reschedule(struct k_work_delayable *w,int64_t deadline)
{ w->scheduled=true;w->deadline=deadline;return 1; }
#endif
