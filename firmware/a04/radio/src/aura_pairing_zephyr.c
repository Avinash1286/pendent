/* SPDX-License-Identifier: MIT */
#include "aura_pairing_zephyr.h"
#include "aura_gatt_zephyr.h"
#include <zephyr/kernel.h>
#include <zephyr/bluetooth/conn.h>
#include <errno.h>
#include <limits.h>
#include <string.h>

BUILD_ASSERT(IS_ENABLED(CONFIG_BT_SMP_SC_ONLY), "Pairing must require L4");
BUILD_ASSERT(IS_ENABLED(CONFIG_BT_SMP_APP_PAIRING_ACCEPT), "Physical gate is mandatory");
BUILD_ASSERT(!IS_ENABLED(CONFIG_BT_FIXED_PASSKEY), "No fixed passkey");
BUILD_ASSERT(!IS_ENABLED(CONFIG_BT_USE_DEBUG_KEYS), "No Bluetooth debug keys");
BUILD_ASSERT(!IS_ENABLED(CONFIG_BT_STORE_DEBUG_KEYS), "No stored debug keys");

#define WINDOW_MS INT64_C(60000)
#define ATTEMPTS_MAX 3u
#define EVENTS_MAX 2u
/* Public SMP Pairing Request/Response wire values from Core Vol3 PartH3.5.1;
 * Zephyr's names live in private host/smp.h, which is deliberately not used. */
#define SMP_AUTH_SC 0x08u
#define SMP_IO_KEYBOARD_ONLY 0x02u
#define SMP_IO_KEYBOARD_DISPLAY 0x04u

static struct {
    struct k_spinlock lock;
    struct k_work_delayable expiry;
    struct bt_conn *attempt;
    uint64_t counter, window, attempt_window, connection;
    int64_t deadline;
    unsigned attempts, event_count;
    struct aura_pairing_event events[EVENTS_MAX];
    bool initialized;
} pairing;
#define P pairing

static bool open_locked(int64_t now)
{ return P.initialized && P.window && now >= 0 && now < P.deadline; }
static void close_window_locked(void)
{
    P.window=0;P.deadline=0;
    /* Pinned Zephyr 4.2 bt_set_bondable is a nonblocking bool assignment.
     * This module is its sole application writer, ordered with window state. */
    bt_set_bondable(false);
}
static struct bt_conn *detach_locked(void)
{
    struct bt_conn *conn=P.attempt;
    P.attempt=NULL;P.attempt_window=P.connection=0;
    return conn;
}
static void terminal_locked(enum aura_pairing_event_kind kind,uint64_t connection)
{
    /* State changes discard queued passkeys, so a cancelled key cannot be
     * printed ahead of its cancellation even if the UART owner was blocked. */
    memset(P.events,0,sizeof(P.events));P.event_count=1;
    P.events[0]=(struct aura_pairing_event){.kind=kind,
        .window_generation=P.counter,.connection_generation=connection};
}
static void cancel_connection(struct bt_conn *conn,uint64_t generation)
{
    if(!conn)return;
    /* No policy spinlock is held: these calls may synchronously call back. */
    if(aura_gatt_connection_generation(conn)==generation){
        aura_gatt_disconnect(generation);
        (void)bt_conn_auth_cancel(conn);
    }
    bt_conn_unref(conn);
}
static void expire_if_due(void)
{
    struct bt_conn *conn=NULL;uint64_t generation=0;
    k_spinlock_key_t key=k_spin_lock(&P.lock);
    if(P.window && (k_uptime_get()<0 || k_uptime_get()>=P.deadline)){
        generation=P.connection;terminal_locked(AURA_PAIRING_EXPIRED,generation);
        close_window_locked();conn=detach_locked();
    }
    k_spin_unlock(&P.lock,key);
    cancel_connection(conn,generation);
}
static void expiry_work(struct k_work *work)
{
    ARG_UNUSED(work);expire_if_due();
    k_spinlock_key_t key=k_spin_lock(&P.lock);
    int64_t deadline=P.window?P.deadline:0;
    k_spin_unlock(&P.lock,key);
    if(deadline)(void)k_work_reschedule(&P.expiry,K_TIMEOUT_ABS_MS(deadline));
}
bool aura_pairing_window_open(void)
{
    k_spinlock_key_t key=k_spin_lock(&P.lock);
    bool allowed=open_locked(k_uptime_get());
    k_spin_unlock(&P.lock,key);return allowed;
}
int aura_pairing_open(void)
{
    expire_if_due();
    k_spinlock_key_t key=k_spin_lock(&P.lock);
    int64_t now=k_uptime_get();
    if(!P.initialized){k_spin_unlock(&P.lock,key);return -EACCES;}
    if(open_locked(now)){k_spin_unlock(&P.lock,key);return 0;}
    if(P.counter==UINT64_MAX || now<0 || now>INT64_MAX-WINDOW_MS){
        k_spin_unlock(&P.lock,key);return -EOVERFLOW;
    }
    P.window=++P.counter;P.deadline=now+WINDOW_MS;P.attempts=0;
    bt_set_bondable(true);
    memset(P.events,0,sizeof(P.events));P.event_count=0;
    int64_t deadline=P.deadline;
    k_spin_unlock(&P.lock,key);
    (void)k_work_reschedule(&P.expiry,K_TIMEOUT_ABS_MS(deadline));
    return 0;
}
void aura_pairing_close(void)
{
    k_spinlock_key_t key=k_spin_lock(&P.lock);
    uint64_t generation=P.connection;
    if(P.window||P.attempt)terminal_locked(AURA_PAIRING_CANCELLED,generation);
    close_window_locked();
    struct bt_conn *conn=detach_locked();
    k_spin_unlock(&P.lock,key);
    /* Do not cancel delayed work: an old close must not cancel a newly opened
     * window's timer. An obsolete work item rechecks the current deadline. */
    cancel_connection(conn,generation);
}

static enum bt_security_err accept(struct bt_conn *conn,const struct bt_conn_pairing_feat *feat)
{
    uint64_t generation=aura_gatt_connection_generation(conn);
    if(!generation||!feat)return BT_SECURITY_ERR_PAIR_NOT_ALLOWED;
    if(!(feat->auth_req&SMP_AUTH_SC)||feat->max_enc_key_size!=16||
       (feat->io_capability!=SMP_IO_KEYBOARD_ONLY&&feat->io_capability!=SMP_IO_KEYBOARD_DISPLAY))
        return BT_SECURITY_ERR_AUTH_REQUIREMENT;
    k_spinlock_key_t key=k_spin_lock(&P.lock);
    bool allowed=open_locked(k_uptime_get());
    if(allowed&&P.attempt){
        allowed=P.attempt==conn&&P.connection==generation&&P.attempt_window==P.window;
    }else if(allowed&&P.attempts<ATTEMPTS_MAX){
        memset(P.events,0,sizeof(P.events));P.event_count=0;
        P.attempt=bt_conn_ref(conn);P.connection=generation;P.attempt_window=P.window;
        ++P.attempts;
    }else allowed=false;
    k_spin_unlock(&P.lock,key);
    return allowed?BT_SECURITY_ERR_SUCCESS:BT_SECURITY_ERR_PAIR_NOT_ALLOWED;
}
static void failed_attempt(struct bt_conn *conn)
{
    struct bt_conn *release=NULL;uint64_t generation=0;
    k_spinlock_key_t key=k_spin_lock(&P.lock);
    if(P.attempt==conn){
        generation=P.connection;terminal_locked(AURA_PAIRING_CANCELLED,generation);
        release=detach_locked();
        if(P.attempts>=ATTEMPTS_MAX)close_window_locked();
    }
    k_spin_unlock(&P.lock,key);
    /* Even when the window remains open, a failed attempt requires a fresh
     * connection. Old callbacks cannot become a new attempt on this link. */
    cancel_connection(release,generation);
}
static void display(struct bt_conn *conn,unsigned int passkey)
{
    uint64_t generation=aura_gatt_connection_generation(conn);
    k_spinlock_key_t key=k_spin_lock(&P.lock);
    bool current=P.attempt==conn&&generation&&P.connection==generation&&
                 P.attempt_window==P.window&&open_locked(k_uptime_get());
    bool accepted=current&&passkey<=999999u;
    if(accepted){
        bool same=P.event_count&&P.events[P.event_count-1].kind==AURA_PAIRING_PASSKEY&&
                  P.events[P.event_count-1].passkey==passkey;
        if(!same){
            if(P.event_count==EVENTS_MAX)accepted=false;
            else P.events[P.event_count++]=(struct aura_pairing_event){
                .kind=AURA_PAIRING_PASSKEY,.passkey=passkey,
                .window_generation=P.window,.connection_generation=generation};
        }
    }
    bool owns=P.attempt==conn;
    k_spin_unlock(&P.lock,key);
    if(!accepted&&owns)failed_attempt(conn);
    /* A callback for a different old connection is ignored, never relabelled. */
}
static void cancelled(struct bt_conn *conn) { failed_attempt(conn); }
static void confirm(struct bt_conn *conn)
{
    /* Never approve a Just Works fallback, even inside the physical window. */
    failed_attempt(conn);
}
static void complete(struct bt_conn *conn,bool bonded)
{
    /* Bonding is persistence, not owner authorization. Even an authenticated
     * nonbonded link still requires ASC1; it cannot reconnect without pairing. */
    ARG_UNUSED(bonded);
    uint64_t generation=aura_gatt_connection_generation(conn);
    bool secure=bt_conn_get_security(conn)==BT_SECURITY_L4&&bt_conn_enc_key_size(conn)==16;
    struct bt_conn *release=NULL;bool success=false;
    k_spinlock_key_t key=k_spin_lock(&P.lock);
    if(P.attempt==conn){
        success=generation&&P.connection==generation&&P.attempt_window==P.window&&
                open_locked(k_uptime_get())&&secure;
        terminal_locked(success?AURA_PAIRING_COMPLETE:AURA_PAIRING_CANCELLED,P.connection);
        generation=P.connection;close_window_locked();release=detach_locked();
    }
    k_spin_unlock(&P.lock,key);
    if(success)bt_conn_unref(release);
    else cancel_connection(release,generation);
}
static void failed(struct bt_conn *conn,enum bt_security_err reason)
{ ARG_UNUSED(reason);failed_attempt(conn); }
static void disconnected(struct bt_conn *conn,uint8_t reason)
{
    ARG_UNUSED(reason);
    struct bt_conn *release=NULL;
    k_spinlock_key_t key=k_spin_lock(&P.lock);
    if(P.attempt==conn){
        terminal_locked(AURA_PAIRING_CANCELLED,P.connection);release=detach_locked();
        if(P.attempts>=ATTEMPTS_MAX)close_window_locked();
    }
    k_spin_unlock(&P.lock,key);
    if(release)bt_conn_unref(release);
}
BT_CONN_CB_DEFINE(aura_pairing_connection_callbacks)={.disconnected=disconnected};
static const struct bt_conn_auth_cb callbacks={.pairing_accept=accept,
    .passkey_display=display,.cancel=cancelled,.pairing_confirm=confirm};
static struct bt_conn_auth_info_cb info_callbacks={.pairing_complete=complete,.pairing_failed=failed};
int aura_pairing_init(void)
{
    if(P.initialized)return 0;
    k_work_init_delayable(&P.expiry,expiry_work);
    int result=bt_conn_auth_cb_register(&callbacks);
    if(result)return result;
    result=bt_conn_auth_info_cb_register(&info_callbacks);
    if(result){(void)bt_conn_auth_cb_register(NULL);return result;}
    P.initialized=true;bt_set_bondable(false);return 0;
}
bool aura_pairing_take(struct aura_pairing_event *event)
{
    if(!event)return false;
    memset(event,0,sizeof(*event));expire_if_due();
    for(unsigned scanned=0;scanned<EVENTS_MAX;++scanned){
        struct bt_conn *conn=NULL;struct aura_pairing_event candidate;
        k_spinlock_key_t key=k_spin_lock(&P.lock);
        if(!P.event_count){k_spin_unlock(&P.lock,key);return false;}
        candidate=P.events[0];--P.event_count;
        if(P.event_count)P.events[0]=P.events[1];
        memset(&P.events[P.event_count],0,sizeof(P.events[0]));
        bool valid=candidate.window_generation==P.counter;
        if(candidate.kind==AURA_PAIRING_PASSKEY){
            valid=valid&&open_locked(k_uptime_get())&&P.window==candidate.window_generation&&
                  P.attempt&&P.connection==candidate.connection_generation;
            if(valid)conn=bt_conn_ref(P.attempt);
        }
        k_spin_unlock(&P.lock,key);
        if(conn){
            uint64_t generation=aura_gatt_connection_generation(conn);
            key=k_spin_lock(&P.lock);
            valid=valid&&generation==candidate.connection_generation&&P.attempt==conn&&
                  P.window==candidate.window_generation&&open_locked(k_uptime_get());
            k_spin_unlock(&P.lock,key);bt_conn_unref(conn);
        }
        if(valid){*event=candidate;return true;}
    }
    return false;
}
