/* Actual pairing policy source, with bounded clock/ref/callback mocks.
 * This deliberately does not simulate cryptography or claim SMP execution. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <zephyr/kernel.h>
#include <zephyr/bluetooth/conn.h>
#ifdef NDEBUG
#error "Pairing checks cannot compile with NDEBUG"
#endif
static unsigned checks,groups,cancels,disconnects;
int64_t test_now;
static int auth_register_error,info_register_error;
static const struct bt_conn_auth_cb *auth_cb;
static struct bt_conn_auth_info_cb *info_cb;
static struct bt_conn connections[4];
static bool bondable;
void check_at(int ok,const char *message,int line)
{ ++checks;if(!ok){fprintf(stderr,"FAIL %d %s\n",line,message);exit(1);} }
#define CHECK(v) check_at((v),#v,__LINE__)
#define GROUP(v) do { ++groups;printf("PASS %s\n",v); } while(0)
struct bt_conn *bt_conn_ref(struct bt_conn *conn)
{ CHECK(conn&&conn->refs);++conn->refs;return conn; }
void bt_conn_unref(struct bt_conn *conn) { CHECK(conn&&conn->refs>1);--conn->refs; }
int bt_conn_auth_cancel(struct bt_conn *conn)
{ ++cancels;if(auth_cb&&auth_cb->cancel)auth_cb->cancel(conn);return 0; }
int bt_conn_auth_cb_register(const struct bt_conn_auth_cb *cb)
{ if(cb&&auth_register_error)return auth_register_error;auth_cb=cb;return 0; }
int bt_conn_auth_info_cb_register(struct bt_conn_auth_info_cb *cb)
{ if(info_register_error)return info_register_error;info_cb=cb;return 0; }
bt_security_t bt_conn_get_security(const struct bt_conn *conn) { return conn->security; }
uint8_t bt_conn_enc_key_size(const struct bt_conn *conn) { return conn->key_bytes; }
void bt_set_bondable(bool enable) { bondable=enable; }
uint64_t aura_gatt_connection_generation(struct bt_conn *conn)
{ return conn&&conn->connected?conn->generation:0; }
void aura_gatt_disconnect(uint64_t generation)
{
    for(unsigned i=0;i<4;++i)if(connections[i].generation==generation&&generation){
        ++disconnects;connections[i].generation=0;
    }
}
#include "../../src/aura_pairing_zephyr.c"

static void reset(void)
{
    if(P.initialized)aura_pairing_close();
    for(unsigned i=0;i<4;++i)if(connections[i].refs)CHECK(connections[i].refs==1);
    memset(&pairing,0,sizeof(pairing));memset(connections,0,sizeof(connections));
    for(unsigned i=0;i<4;++i)connections[i]=(struct bt_conn){.refs=1,.generation=i+1,.connected=true};
    test_now=1000;auth_register_error=info_register_error=0;
    auth_cb=NULL;info_cb=NULL;cancels=disconnects=0;bondable=false;
}
static void ready(void) { reset();CHECK(aura_pairing_init()==0);CHECK(aura_pairing_open()==0); }
static enum bt_security_err accept_connection(unsigned i)
{
    const struct bt_conn_pairing_feat feat={.io_capability=4,.auth_req=8,.max_enc_key_size=16};
    return auth_cb->pairing_accept(&connections[i],&feat);
}
static void init_failures(void)
{
    reset();CHECK(aura_pairing_open()==-EACCES);
    auth_register_error=-7;CHECK(aura_pairing_init()==-7&&!P.initialized&&!auth_cb);
    auth_register_error=0;info_register_error=-8;
    CHECK(aura_pairing_init()==-8&&!P.initialized&&!auth_cb);
    info_register_error=0;CHECK(aura_pairing_init()==0&&auth_cb&&info_cb);
    CHECK(aura_pairing_init()==0&&!aura_pairing_window_open()&&!bondable);
    CHECK(accept_connection(0)==BT_SECURITY_ERR_PAIR_NOT_ALLOWED&&connections[0].refs==1);
    GROUP("registration_errors_fail_closed_and_boot_has_no_window");
}
static void window_lifetime(void)
{
    ready();uint64_t window=P.window;int64_t deadline=P.deadline;
    CHECK(deadline==61000&&P.expiry.scheduled&&P.expiry.deadline==deadline&&bondable);
    test_now=60000;CHECK(aura_pairing_open()==0&&P.window==window&&P.deadline==deadline);
    CHECK(accept_connection(0)==0&&connections[0].refs==2);
    test_now=61000;CHECK(!aura_pairing_window_open());
    P.expiry.work.handler(&P.expiry.work);
    CHECK(!P.window&&!P.attempt&&disconnects==1&&cancels==1&&connections[0].refs==1&&!bondable);
    struct aura_pairing_event event;CHECK(aura_pairing_take(&event)&&event.kind==AURA_PAIRING_EXPIRED&&event.passkey==0);
    GROUP("absolute_window_deadline_cancels_SMP_without_owner_tick");
}
static void budgets(void)
{
    ready();
    for(unsigned i=0;i<3;++i){
        CHECK(accept_connection(i)==0&&P.attempts==i+1);
        CHECK(accept_connection(i)==0&&P.attempts==i+1);
        CHECK(accept_connection(3)==BT_SECURITY_ERR_PAIR_NOT_ALLOWED);
        auth_cb->passkey_display(&connections[i],1234+i);
        auth_cb->cancel(&connections[i]);
        CHECK(connections[i].refs==1&&P.attempt==NULL);
        CHECK(aura_pairing_window_open()==(i<2)&&bondable==(i<2));
    }
    CHECK(accept_connection(3)==BT_SECURITY_ERR_PAIR_NOT_ALLOWED&&disconnects==3&&cancels==3);
    GROUP("one_attempt_at_a_time_and_three_attempt_window_budget");
}
static void successful_pair(void)
{
    ready();CHECK(accept_connection(0)==0);auth_cb->passkey_display(&connections[0],37);
    struct aura_pairing_event event;CHECK(aura_pairing_take(&event));
    CHECK(event.kind==AURA_PAIRING_PASSKEY&&event.passkey==37&&event.connection_generation==1&&event.window_generation==P.window);
    connections[0].security=4;connections[0].key_bytes=16;
    info_cb->pairing_complete(&connections[0],true);
    CHECK(!aura_pairing_window_open()&&!P.attempt&&connections[0].refs==1&&cancels==0&&disconnects==0&&!bondable);
    aura_pairing_close();CHECK(connections[0].connected&&connections[0].generation==1&&disconnects==0&&cancels==0);
    CHECK(aura_pairing_take(&event)&&event.kind==AURA_PAIRING_COMPLETE&&event.passkey==0);
    CHECK(accept_connection(1)==BT_SECURITY_ERR_PAIR_NOT_ALLOWED);
    GROUP("dynamic_passkey_and_real_L4_completion_consume_window");
}
static void downgrade(void)
{
    ready();struct bt_conn_pairing_feat feat={.io_capability=3,.auth_req=8,.max_enc_key_size=16};
    CHECK(auth_cb->pairing_accept(&connections[0],&feat)==BT_SECURITY_ERR_AUTH_REQUIREMENT);
    feat.io_capability=4;feat.auth_req=0;
    CHECK(auth_cb->pairing_accept(&connections[0],&feat)==BT_SECURITY_ERR_AUTH_REQUIREMENT);
    feat.auth_req=8;feat.max_enc_key_size=15;
    CHECK(auth_cb->pairing_accept(&connections[0],&feat)==BT_SECURITY_ERR_AUTH_REQUIREMENT&&P.attempts==0);
    CHECK(accept_connection(0)==0);auth_cb->pairing_confirm(&connections[0]);
    CHECK(cancels==1&&disconnects==1&&!P.attempt);
    for(unsigned kind=0;kind<2;++kind){
        ready();CHECK(accept_connection(0)==0);
        connections[0].security=kind?4:3;connections[0].key_bytes=kind?15:16;
        info_cb->pairing_complete(&connections[0],true);
        CHECK(!P.window&&!P.attempt&&cancels==1&&disconnects==1);
    }
    GROUP("SC_features_Just_Works_L3_and_short_keys_cannot_complete");
}
static void stale_callbacks(void)
{
    ready();CHECK(accept_connection(0)==0);auth_cb->passkey_display(&connections[0],123456);
    aura_pairing_close();test_now=1001;CHECK(aura_pairing_open()==0);CHECK(accept_connection(1)==0);
    uint64_t window=P.window;unsigned old_cancels=cancels,old_disconnects=disconnects;
    auth_cb->passkey_display(&connections[0],654321);auth_cb->cancel(&connections[0]);
    info_cb->pairing_failed(&connections[0],BT_SECURITY_ERR_AUTH_FAIL);
    connections[0].security=4;connections[0].key_bytes=16;info_cb->pairing_complete(&connections[0],true);
    aura_pairing_connection_callbacks.disconnected(&connections[0],0);
    CHECK(P.attempt==&connections[1]&&P.window==window&&cancels==old_cancels&&disconnects==old_disconnects);
    struct aura_pairing_event event;CHECK(!aura_pairing_take(&event));
    auth_cb->passkey_display(&connections[1],111111);CHECK(aura_pairing_take(&event)&&event.passkey==111111&&event.connection_generation==2);
    GROUP("old_connection_callbacks_cannot_relabel_or_cancel_new_attempt");
}
static void stale_events_and_overflow(void)
{
    ready();CHECK(accept_connection(0)==0);auth_cb->passkey_display(&connections[0],1);
    ++connections[0].generation;
    struct aura_pairing_event event;CHECK(!aura_pairing_take(&event));
    aura_pairing_close();CHECK(disconnects==0&&cancels==0&&connections[0].refs==1);
    ready();CHECK(accept_connection(0)==0);auth_cb->passkey_display(&connections[0],1);
    auth_cb->passkey_display(&connections[0],1);CHECK(P.event_count==1);
    auth_cb->passkey_display(&connections[0],2);CHECK(P.event_count==2);
    auth_cb->passkey_display(&connections[0],3);
    CHECK(P.event_count==1&&!P.attempt&&disconnects==1&&cancels==1);
    CHECK(aura_pairing_take(&event)&&event.kind==AURA_PAIRING_CANCELLED&&event.passkey==0);
    ready();CHECK(accept_connection(0)==0);auth_cb->passkey_display(&connections[0],1000000);
    CHECK(!P.attempt&&disconnects==1&&cancels==1);
    GROUP("stale_queued_keys_and_event_overflow_never_leak_display");
}
static void deadline_races(void)
{
    ready();CHECK(accept_connection(0)==0);auth_cb->passkey_display(&connections[0],123456);
    test_now=61000;connections[0].security=4;connections[0].key_bytes=16;
    info_cb->pairing_complete(&connections[0],true);
    CHECK(!P.attempt&&!P.window&&disconnects==1);
    struct aura_pairing_event event;CHECK(aura_pairing_take(&event)&&event.kind!=AURA_PAIRING_PASSKEY&&event.kind!=AURA_PAIRING_COMPLETE);
    ready();aura_pairing_close();test_now=2000;CHECK(aura_pairing_open()==0&&P.deadline==62000);
    test_now=61000;P.expiry.work.handler(&P.expiry.work);
    CHECK(aura_pairing_window_open()&&P.expiry.deadline==62000&&bondable);
    test_now=62000;P.expiry.work.handler(&P.expiry.work);CHECK(!aura_pairing_window_open());
    GROUP("late_completion_and_obsolete_timer_cannot_extend_or_consume_new_window");
}
static void disconnect_and_overflow(void)
{
    ready();CHECK(accept_connection(0)==0);auth_cb->passkey_display(&connections[0],222222);
    connections[0].connected=false;aura_pairing_connection_callbacks.disconnected(&connections[0],0);
    CHECK(!P.attempt&&connections[0].refs==1&&disconnects==0&&cancels==0);
    struct aura_pairing_event event;CHECK(aura_pairing_take(&event)&&event.kind==AURA_PAIRING_CANCELLED&&event.passkey==0);
    aura_pairing_close();P.counter=UINT64_MAX;CHECK(aura_pairing_open()==-EOVERFLOW);
    P.counter=1;test_now=INT64_MAX-59999;CHECK(aura_pairing_open()==-EOVERFLOW);
    test_now=-1;CHECK(aura_pairing_open()==-EOVERFLOW);
    CHECK(!aura_pairing_take(NULL));
    GROUP("disconnect_releases_only_own_reference_and_overflow_fails_closed");
}
int main(void)
{
    init_failures();window_lifetime();budgets();successful_pair();downgrade();stale_callbacks();
    stale_events_and_overflow();deadline_races();disconnect_and_overflow();reset();
    printf("PASS pairing groups=%u checks=%u mocked_callbacks=true SMP_tested=false\n",groups,checks);
    return 0;
}
