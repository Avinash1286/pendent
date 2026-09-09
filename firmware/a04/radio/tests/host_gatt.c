/* SPDX-License-Identifier: MIT
 * Actual adapter + actual transfer/journal/archive engine. Only Zephyr, radio
 * callbacks and clock are deterministic doubles; no RF/security proof claim.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "aura_transfer.h"
#include "zephyr_stubs.h"
#define REQUIRE(x) do { if (!(x)) { fprintf(stderr, "GATT assertion %d: %s\n", __LINE__, #x); exit(2); } } while (0)
enum execution { TEST, OWNER, RX, WORK };
static struct {
    enum execution context;
    unsigned locked, calls, steps, sent, begins, ends, cancels, notifications, groups;
    unsigned attempts, disconnects, security_requests;
    int64_t now;
    int notify_error, disconnect_error, security_error;
    struct bt_gatt_cb *gatt;
    struct bt_conn *pending_conn;
    void (*pending_callback)(struct bt_conn *, void *);
    void *pending_user;
    bool inline_callback, owner_inside_notify, preempt_inside_notify;
    uint8_t wire[2048]; size_t wire_bytes;
} sim;
static void owner_api(void) { REQUIRE(sim.context == OWNER); REQUIRE(!sim.locked); ++sim.calls; }
static int checked_begin(struct aura_transfer *t, bool a, uint64_t *g)
{ owner_api(); ++sim.begins; return aura_transfer_session_begin(t,a,g); }
static int checked_end(struct aura_transfer *t, uint64_t g)
{ owner_api(); ++sim.ends; return aura_transfer_session_end(t,g); }
static int checked_cancel(struct aura_transfer *t, uint64_t g)
{ owner_api(); ++sim.cancels; return aura_transfer_cancel_work(t,g); }
static int checked_submit(struct aura_transfer *t, uint64_t g, const uint8_t *p, size_t n)
{ owner_api(); return aura_transfer_submit(t,g,p,n); }
static int checked_step(struct aura_transfer *t, uint64_t g)
{ owner_api(); ++sim.steps; return aura_transfer_step(t,g); }
static int checked_response(struct aura_transfer *t,uint64_t g,uint8_t *p,size_t c,size_t *n,uint64_t *d)
{ owner_api(); return aura_transfer_copy_response(t,g,p,c,n,d); }
static int checked_fragment(struct aura_transfer *t,uint64_t g,uint16_t x,uint64_t d,uint16_t m,uint16_t o,uint8_t *p,size_t c,size_t *n)
{ owner_api(); return aura_transfer_copy_fragment(t,g,x,d,m,o,p,c,n); }
static int checked_sent(struct aura_transfer *t,uint64_t g,uint16_t x,uint64_t d)
{ owner_api(); ++sim.sent; return aura_transfer_response_sent(t,g,x,d); }
#define aura_transfer_session_begin checked_begin
#define aura_transfer_session_end checked_end
#define aura_transfer_cancel_work checked_cancel
#define aura_transfer_submit checked_submit
#define aura_transfer_step checked_step
#define aura_transfer_copy_response checked_response
#define aura_transfer_copy_fragment checked_fragment
#define aura_transfer_response_sent checked_sent
#include "../src/aura_gatt_zephyr.c"
#undef aura_transfer_session_begin
#undef aura_transfer_session_end
#undef aura_transfer_cancel_work
#undef aura_transfer_submit
#undef aura_transfer_step
#undef aura_transfer_copy_response
#undef aura_transfer_copy_fragment
#undef aura_transfer_response_sent

static struct aura_journal journal;
static struct aura_transfer transfer;
static struct bt_conn first, second;
static int tick(bool grant, bool preempt);

k_spinlock_key_t k_spin_lock(struct k_spinlock *lock)
{ (void)lock; REQUIRE(!sim.locked); return sim.locked++; }
void k_spin_unlock(struct k_spinlock *lock, k_spinlock_key_t key)
{ (void)lock; REQUIRE(sim.locked == key+1); sim.locked = key; }
int64_t k_uptime_get(void) { return sim.now; }
void k_work_init_delayable(struct k_work_delayable *w, void (*fn)(struct k_work *))
{ memset(w,0,sizeof(*w)); w->work.handler=fn; }
int k_work_reschedule(struct k_work_delayable *w,int delay)
{ REQUIRE(!sim.locked); w->due=sim.now+delay; w->pending=true; return 1; }
struct bt_conn *bt_conn_ref(struct bt_conn *c) { REQUIRE(c && c->refs); ++c->refs; return c; }
void bt_conn_unref(struct bt_conn *c) { REQUIRE(c && c->refs>1); --c->refs; }
bt_security_t bt_conn_get_security(const struct bt_conn *c) { return c->security; }
uint8_t bt_conn_enc_key_size(const struct bt_conn *c) { return c->key_bytes; }
int bt_conn_disconnect(struct bt_conn *c,uint8_t reason)
{ REQUIRE(!sim.locked); REQUIRE(c); (void)reason; ++sim.disconnects; return sim.disconnect_error; }
int bt_conn_set_security(struct bt_conn *c,bt_security_t level)
{ REQUIRE(!sim.locked && sim.context==WORK && c && level==4); ++sim.security_requests; return sim.security_error; }
void bt_gatt_cb_register(struct bt_gatt_cb *cb) { REQUIRE(!sim.gatt); sim.gatt=cb; }
bool bt_gatt_is_subscribed(struct bt_conn *c,const struct bt_gatt_attr *attr,uint16_t type)
{ REQUIRE(!sim.locked && attr==RESPONSE_ATTR && type==1); return c->subscribed; }
uint16_t bt_gatt_get_mtu(struct bt_conn *c) { return c->mtu; }
int bt_gatt_notify_cb(struct bt_conn *c,struct bt_gatt_notify_params *p)
{
    REQUIRE(!sim.locked && sim.context==WORK); ++sim.attempts;
    REQUIRE(p->attr==RESPONSE_ATTR && p->data==S.tx.data && p->user_data==&S.tx);
    REQUIRE(p->len>=9 && p->len<=c->mtu-3 && S.tx.state==TX_SENDING);
    if(sim.preempt_inside_notify) REQUIRE(!tick(true,true));
    if (sim.notify_error) return sim.notify_error;
    REQUIRE(!sim.pending_callback && sim.wire_bytes+p->len+2<=sizeof(sim.wire));
    sim.wire[sim.wire_bytes++]=(uint8_t)p->len;
    sim.wire[sim.wire_bytes++]=(uint8_t)(p->len>>8);
    memcpy(sim.wire+sim.wire_bytes,p->data,p->len); sim.wire_bytes+=p->len;
    ++sim.notifications;
    if (sim.inline_callback) {
        uint64_t delivery=S.tx.delivery;
        uint8_t copy[TX_MAX]; memcpy(copy,S.tx.data,S.tx.bytes);
        p->func(c,p->user_data);
        REQUIRE(S.tx.state==TX_SENDING && S.tx.completion_seen);
        if (sim.owner_inside_notify) REQUIRE(tick(true,false)==0);
        REQUIRE(S.tx.state==TX_SENDING && S.tx.delivery==delivery);
        REQUIRE(!memcmp(copy,S.tx.data,S.tx.bytes));
    } else {
        sim.pending_conn=c; sim.pending_callback=p->func; sim.pending_user=p->user_data;
    }
    return 0;
}
static void run_work(struct k_work_delayable *w)
{
    REQUIRE(w->pending); if(sim.now<w->due) sim.now=w->due;
    w->pending=false; enum execution old=sim.context; sim.context=WORK;
    w->work.handler(&w->work); sim.context=old;
}
static void complete(void)
{
    REQUIRE(sim.pending_callback);
    void (*fn)(struct bt_conn *,void *)=sim.pending_callback;
    struct bt_conn *c=sim.pending_conn; void *u=sim.pending_user;
    sim.pending_callback=NULL; sim.pending_conn=NULL; sim.pending_user=NULL;
    enum execution old=sim.context; sim.context=WORK; fn(c,u); sim.context=old;
}
static void connection(struct bt_conn *c)
{ enum execution old=sim.context; sim.context=RX; aura_radio_callbacks.connected(c,0); sim.context=old; }
static void disconnection(struct bt_conn *c)
{ enum execution old=sim.context; sim.context=RX; aura_radio_callbacks.disconnected(c,19); sim.context=old; }
static void secure(struct bt_conn *c)
{
    c->security=4; c->key_bytes=16;
    enum execution old=sim.context; sim.context=RX;
    aura_radio_callbacks.security_changed(c,4,BT_SECURITY_ERR_SUCCESS); sim.context=old;
}
static void subscribe(struct bt_conn *c,bool enabled)
{
    enum execution old=sim.context; sim.context=RX;
    REQUIRE(ccc_write(c,NULL,enabled?1:0)==2);
    c->subscribed=enabled; ccc_changed(NULL,enabled?1:0); sim.context=old;
}
static struct aura_gatt_link link(void) { struct aura_gatt_link l; aura_gatt_link_snapshot(&l); return l; }
static int tick(bool grant,bool preempt)
{
    enum execution old=sim.context; sim.context=OWNER;
    struct aura_gatt_owner_gate gate={link().generation,grant?AURA_GATT_GRANTED:AURA_GATT_DENIED,preempt};
    unsigned before=sim.steps; int r=aura_gatt_owner_tick(&transfer,&gate);
    REQUIRE(sim.steps-before<=1); sim.context=old; return r;
}
static ssize_t write_command(struct bt_conn *c,uint16_t transaction)
{
    uint8_t command[4]={1,1,(uint8_t)transaction,(uint8_t)(transaction>>8)};
    enum execution old=sim.context; sim.context=RX;
    unsigned before=sim.calls;
    ssize_t r=command_write(c,NULL,command,sizeof(command),0,0);
    REQUIRE(sim.calls==before); sim.context=old; return r;
}
static void reset(void)
{
    unsigned groups=sim.groups;
    REQUIRE(!sim.pending_callback);
    memset(&sim,0,sizeof(sim)); sim.groups=groups;
    memset(&S,0,sizeof(S)); memset(&journal,0,sizeof(journal));
    first=(struct bt_conn){.refs=1,.security=1,.mtu=23}; second=first;
    journal.export_epoch=1; journal.owned_profile=true;
    memset(journal.owned_incarnation,0x22,16);
    uint8_t device[16]; memset(device,0x11,16);
    REQUIRE(!aura_transfer_init(&transfer,&journal,device,journal.owned_incarnation));
    aura_gatt_init(); aura_gatt_init();
    REQUIRE(sim.gatt && aura_gatt_static_bytes()==sizeof(S));
    connection(&first);
}
static void ready(uint16_t mtu)
{
    secure(&first); subscribe(&first,true);
    REQUIRE(!aura_gatt_auth_deadline(link().generation,sim.now+600000));
    first.mtu=mtu; sim.gatt->att_mtu_updated(&first,mtu,mtu);
    REQUIRE(!tick(true,false)); REQUIRE(link().transfer_ready);
}
static void cleanup(void)
{
    if(sim.pending_callback) complete();
    if(S.conn) disconnection(S.conn);
    REQUIRE(!tick(false,false));
    if(S.tx.state==TX_READY) { run_work(&S.tx_work); REQUIRE(!tick(false,false)); }
    REQUIRE(S.tx.state==TX_FREE && first.refs==1 && second.refs==1);
}
static void pass(const char *name) { cleanup(); ++sim.groups; printf("PASS %s\n",name); }
static void deliver(void)
{
    unsigned guard=0;
    while(transfer.response_pending) {
        REQUIRE(++guard<50);
        if(S.tx.state==TX_READY) run_work(&S.tx_work);
        if(sim.pending_callback) complete();
        REQUIRE(!tick(true,false));
    }
}
static void exact_hello(uint16_t transaction,uint16_t mtu)
{
    uint8_t assembled[46]; size_t pos=0,at=0;
    while(at<sim.wire_bytes) {
        size_t n=sys_get_le16(sim.wire+at); at+=2;
        REQUIRE(n<=mtu-3 && n>=9 && at+n<=sim.wire_bytes);
        const uint8_t *p=sim.wire+at;
        REQUIRE(p[0]==1 && p[1]==0 && sys_get_le16(p+2)==transaction);
        REQUIRE(sys_get_le16(p+4)==pos && sys_get_le16(p+6)==46 && pos+n-8<=46);
        memcpy(assembled+pos,p+8,n-8); pos+=n-8; at+=n;
    }
    REQUIRE(pos==46 && assembled[0]==0 && assembled[1]==1);
    REQUIRE(sys_get_le16(assembled+2)==transaction);
    REQUIRE(!memcmp(assembled+4,transfer.device_id,16));
    REQUIRE(!memcmp(assembled+20,transfer.incarnation,16));
    REQUIRE(sys_get_le16(assembled+42)==512 && sys_get_le16(assembled+44)==256);
}
int main(void)
{
    reset();
    REQUIRE(write_command(&first,1)==-BT_ATT_ERR_AUTHORIZATION);
    REQUIRE(!tick(false,false) && !sim.calls);
    secure(&first); REQUIRE(write_command(&first,1)==-BT_ATT_ERR_AUTHORIZATION);
    subscribe(&first,true); REQUIRE(!tick(false,false) && !sim.calls);
    REQUIRE(write_command(&first,1)==-BT_ATT_ERR_AUTHORIZATION);
    ready(23); REQUIRE(sim.begins==1 && write_command(&first,1)==4);
    uint8_t bad[21]={1};
    REQUIRE(command_write(&first,NULL,bad,3,0,0)==-BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
    REQUIRE(command_write(&first,NULL,bad,21,0,0)==-BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
    REQUIRE(command_write(&first,NULL,bad,4,1,0)==-BT_ATT_ERR_INVALID_OFFSET);
    for(unsigned f=1;f<=7;++f) REQUIRE(command_write(&first,NULL,bad,4,0,(uint8_t)f)==-BT_ATT_ERR_NOT_SUPPORTED);
    REQUIRE(write_command(&first,1)==4);
    REQUIRE(write_command(&first,2)==-BT_ATT_ERR_INSUFFICIENT_RESOURCES);
    REQUIRE(!tick(true,false)); deliver(); REQUIRE(sim.sent==1);
    exact_hello(1,23); pass("encrypted authorization, bounded mailbox, envelopes and real HELLO");

    reset(); secure(&first);
    uint8_t read[160],challenge[144],grant[48];
    for(unsigned i=0;i<sizeof(challenge);++i) challenge[i]=(uint8_t)i;
    memset(grant,0xab,sizeof(grant));
    REQUIRE(auth_read(&first,NULL,read,22,0)==4 && !memcmp(read,"ASNO",4));
    uint64_t original=link().generation;
    REQUIRE(!aura_gatt_auth_publish(original,challenge,sizeof(challenge)));
    REQUIRE(auth_read(&first,NULL,read,22,0)==22 && !memcmp(read,challenge,22));
    REQUIRE(!aura_gatt_auth_publish(original,grant,sizeof(grant)));
    REQUIRE(auth_read(&first,NULL,read,160,22)==122 && !memcmp(read,challenge+22,122));
    REQUIRE(auth_read(&first,NULL,read,160,0)==48 && !memcmp(read,grant,48));
    REQUIRE(auth_read(&first,NULL,read,160,49)==-BT_ATT_ERR_INVALID_OFFSET);
    REQUIRE(aura_gatt_auth_publish(original,challenge,161)==-EINVAL);
    uint8_t frame[20]={0x41,0x34,1,1};
    REQUIRE(auth_write(&first,NULL,frame,20,0,0)==20);
    REQUIRE(auth_write(&first,NULL,frame,20,0,0)==20);
    frame[4]=1; REQUIRE(auth_write(&first,NULL,frame,20,0,0)==-BT_ATT_ERR_INSUFFICIENT_RESOURCES);
    struct aura_gatt_auth_frame got; REQUIRE(aura_gatt_auth_take(&got));
    REQUIRE(got.generation==original && got.bytes==20 && !got.data[4]);
    REQUIRE(!aura_gatt_auth_take(&got));
    subscribe(&first,true); subscribe(&first,false);
    REQUIRE(link().generation!=original && aura_gatt_auth_publish(original,grant,48)==-ESTALE);
    REQUIRE(auth_read(&first,NULL,read,160,22)==-BT_ATT_ERR_INVALID_OFFSET);
    REQUIRE(auth_read(&first,NULL,read,160,0)==4 && !memcmp(read,"ASNO",4));
    pass("immutable long auth read, one auth inbox, CCC revokes exact generation");

    for(unsigned mode=0;mode<3;++mode) {
        uint16_t mtu=mode==0?23:mode==1?247:517;
        reset(); ready(mtu); REQUIRE(write_command(&first,1)==4 && !tick(true,false));
        unsigned before=sim.sent;
        run_work(&S.tx_work); REQUIRE(S.tx.state==TX_SUBMITTED && sim.sent==before);
        uint8_t retained[TX_MAX]; memcpy(retained,S.tx.data,S.tx.bytes);
        REQUIRE(write_command(&first,1)==4 && !tick(true,false));
        REQUIRE(!memcmp(retained,S.tx.data,S.tx.bytes) && sim.sent==before);
        complete(); REQUIRE(!tick(true,false)); deliver(); exact_hello(1,mtu);
        REQUIRE(sim.sent==1);
        uint64_t token=transfer.delivery;
        sim.wire_bytes=0; REQUIRE(write_command(&first,1)==4 && !tick(true,false));
        REQUIRE(transfer.delivery!=token); deliver(); exact_hello(1,mtu);
        REQUIRE(sim.sent==2);
        pass(mode==0?"MTU23 retained fragments and fresh retry token":mode==1?"MTU247 actual negotiated fragment sizing":"MTU517 actual negotiated fragment sizing");
    }

    reset(); ready(23); REQUIRE(write_command(&first,1)==4 && !tick(true,false));
    sim.inline_callback=true; sim.owner_inside_notify=true;
    deliver(); REQUIRE(sim.sent==1); exact_hello(1,23);
    pass("inline completion cannot reclaim slot before notify call returns");

    reset(); ready(23); REQUIRE(write_command(&first,1)==4 && !tick(true,false));
    uint8_t retained[TX_MAX]; memcpy(retained,S.tx.data,S.tx.bytes);
    sim.notify_error=-ENOMEM;
    for(unsigned i=0;i<TX_RETRIES+1;++i) {
        run_work(&S.tx_work); REQUIRE(!memcmp(retained,S.tx.data,S.tx.bytes));
    }
    REQUIRE(sim.attempts==TX_RETRIES+1 && S.tx.state==TX_DONE && !sim.sent && !link().generation);
    REQUIRE(!tick(false,false)); run_work(&S.control_work); REQUIRE(sim.disconnects==1);
    pass("notification resource exhaustion is bounded and closes without fabricated response");

    reset(); ready(23); REQUIRE(write_command(&first,1)==4 && !tick(true,false));
    run_work(&S.tx_work); unsigned refs=first.refs;
    sim.now+=TX_TIMEOUT_MS; run_work(&S.tx_work);
    REQUIRE(S.tx.state==TX_SUBMITTED && first.refs==refs && !link().generation);
    REQUIRE(!tick(false,false) && !sim.sent && S.tx.state==TX_SUBMITTED);
    complete(); REQUIRE(!tick(false,false)); REQUIRE(S.tx.state==TX_FREE && first.refs==refs-1);
    pass("timeout quarantines callback slot and ref until actual completion");

    reset(); ready(23); REQUIRE(write_command(&first,1)==4 && !tick(true,false));
    REQUIRE(!tick(true,true) && sim.cancels==1 && !link().transfer_ready);
    run_work(&S.tx_work); REQUIRE(!tick(true,true) && !sim.sent && !sim.notifications);
    REQUIRE(!tick(true,false) && link().transfer_ready && transfer.last_transaction==1);
    REQUIRE(write_command(&first,2)==4 && !tick(true,false)); deliver(); REQUIRE(sim.sent==1);
    pass("capture preemption cancels unsent copies and retains transaction high-water");

    reset(); ready(23); REQUIRE(write_command(&first,1)==4 && !tick(true,false));
    run_work(&S.tx_work); uint64_t generation=link().generation;
    disconnection(&first); REQUIRE(!tick(false,false) && !sim.sent);
    connection(&second); secure(&second); subscribe(&second,true);
    REQUIRE(!aura_gatt_auth_deadline(link().generation,sim.now+600000));
    REQUIRE(link().generation!=generation && !tick(true,false));
    REQUIRE(write_command(&second,1)==4 && !tick(true,false));
    REQUIRE(S.tx.state==TX_SUBMITTED); complete(); REQUIRE(!tick(true,false));
    REQUIRE(!sim.sent && S.tx.connection==link().generation);
    sim.wire_bytes=0; deliver(); REQUIRE(sim.sent==1); exact_hello(1,23);
    pass("stale connection completion cannot clear a new delivery");

    reset(); ready(23); REQUIRE(write_command(&first,1)==4 && !tick(true,false));
    REQUIRE(write_command(&first,2)==4);
    REQUIRE(tick(true,false)==AURA_TRANSFER_BUSY && !link().generation && !sim.notifications);
    pass("real engine admission rejection disconnects without competing logical response");

    reset(); ready(23); REQUIRE(write_command(&first,1)==4 && !tick(true,false));
    ++journal.export_epoch;
    REQUIRE(tick(true,false)==AURA_TRANSFER_SOURCE_CHANGED && !link().generation);
    pass("source epoch change propagates real engine rejection");

    reset(); ready(23);
    first.key_bytes=15;
    REQUIRE(write_command(&first,1)==-BT_ATT_ERR_AUTHORIZATION);
    uint8_t readbuf[4]; REQUIRE(auth_read(&first,NULL,readbuf,4,0)==-BT_ATT_ERR_AUTHORIZATION);
    aura_radio_callbacks.security_changed(&first,4,BT_SECURITY_ERR_SUCCESS);
    REQUIRE(!link().generation && !link().secure_l4 && !tick(false,false));
    pass("L4 without 128-bit key is denied and invalidates generation");

    reset(); aura_gatt_request_security(link().generation);
    REQUIRE(!sim.security_requests); run_work(&S.control_work); REQUIRE(sim.security_requests==1);
    ready(23); uint64_t old_generation=link().generation;
    sim.gatt->att_mtu_updated(&first,518,518);
    REQUIRE(!link().generation && !link().transfer_ready && !tick(false,false));
    aura_gatt_request_security(old_generation);
    run_work(&S.control_work); REQUIRE(sim.security_requests==1 && sim.disconnects==1);
    pass("owner security request uses workqueue and invalid MTU revokes readiness");

    reset(); ready(23); generation=link().generation;
    REQUIRE(aura_gatt_connection_generation(&first)==generation);
    REQUIRE(!aura_gatt_connection_generation(&second));
    REQUIRE(!aura_gatt_auth_deadline(generation,sim.now+30));
    REQUIRE(write_command(&first,1)==4 && !tick(true,false));
    run_work(&S.tx_work); refs=first.refs;
    unsigned owner_calls=sim.calls;
    sim.now+=30; run_work(&S.deadline_work);
    REQUIRE(!link().generation && !link().transfer_ready && sim.calls==owner_calls);
    REQUIRE(write_command(&first,2)==-BT_ATT_ERR_AUTHORIZATION);
    REQUIRE(auth_read(&first,NULL,readbuf,4,0)==-BT_ATT_ERR_AUTHORIZATION);
    REQUIRE(aura_gatt_auth_deadline(generation,sim.now+30000)==-ESTALE);
    REQUIRE(first.refs==refs && S.tx.state==TX_SUBMITTED);
    REQUIRE(!tick(false,false)); complete(); REQUIRE(!tick(false,false) && !sim.sent);
    pass("auth watchdog expires without owner ticks and rejects late credential renewal");

    reset(); ready(23); generation=link().generation;
    REQUIRE(!aura_gatt_auth_deadline(generation,sim.now+5));
    sim.now+=5; owner_calls=sim.calls;
    REQUIRE(write_command(&first,1)==-BT_ATT_ERR_AUTHORIZATION);
    REQUIRE(!link().generation && sim.calls==owner_calls);
    REQUIRE(!aura_gatt_connection_generation(&first));
    pass("RX independently revokes an expired generation before watchdog dispatch");

    reset(); ready(23); REQUIRE(write_command(&first,1)==4 && !tick(true,false));
    generation=link().generation; run_work(&S.tx_work);
    subscribe(&first,false);
    REQUIRE(link().generation!=generation && !link().transfer_ready);
    REQUIRE(!tick(false,false)); complete(); REQUIRE(!tick(false,false) && !sim.sent);
    subscribe(&first,true);
    REQUIRE(!aura_gatt_auth_deadline(link().generation,sim.now+600000));
    REQUIRE(!tick(true,false)); sim.wire_bytes=0;
    REQUIRE(write_command(&first,1)==4 && !tick(true,false)); deliver();
    REQUIRE(sim.sent==1); exact_hello(1,23);
    pass("CCC loss retains submitted slot while revoking grant and stale completion");

    reset(); ready(23); REQUIRE(write_command(&first,1)==4 && !tick(true,false));
    generation=link().generation; sim.preempt_inside_notify=true; sim.notify_error=-ENOMEM;
    run_work(&S.tx_work);
    REQUIRE(link().generation==generation && S.tx.state==TX_DONE && !sim.sent);
    REQUIRE(!tick(true,true)); sim.preempt_inside_notify=false; sim.notify_error=0;
    REQUIRE(!tick(true,false)); REQUIRE(write_command(&first,2)==4 && !tick(true,false));
    deliver(); REQUIRE(sim.sent==1);
    pass("preemption during notification call failure retains authenticated session");

    printf("%u production GATT adapter / real transfer groups passed\n",sim.groups);
    return 0;
}
