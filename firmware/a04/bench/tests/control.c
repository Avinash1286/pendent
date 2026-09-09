/* SPDX-License-Identifier: MIT
 * Actual bench orchestration + actual audio adapter; deterministic doubles for
 * OS, devices, recorder, storage and journal export. No hardware evidence.
 */
#include <assert.h>
#include <setjmp.h>
#define main aura_bench_application_main
#include "../src/main.c"
#undef main
#include "aura_dmic_health.h"
#include <zephyr/audio/dmic.h>

#define REQUIRE(x) do{if(!(x)){fprintf(stderr,"bench control assertion %d: %s\n",__LINE__,#x);exit(2);}}while(0)
struct device bench_devices[6];
static struct {
    char output[32768]; size_t used;
    const uint8_t *input; size_t input_bytes,input_offset;
    int uart_error,privacy,power,led,prepare_error,recorder_retries,seal_error,export_error,receipt_error;
    unsigned powerups,prepare_calls,cancel_calls,start_calls,stop_calls,interrupt_calls;
    unsigned provision_calls,open_calls,export_calls,receipt_calls,init_calls;
    unsigned raw_count,raw_head,irq_depth,groups,cases;
    uint64_t ms,sequence;
    struct {void *data;uint64_t sequence;} raw[8];
    struct k_mem_slab *slab;
    struct aura_dmic_health health;
    struct aura_release_auth_context authority;
    struct aura_archive_manifest prepared,started;
    uint64_t started_epoch;
    bool exported,owner_running,auto_quiesce;
    int owner_iterations;
    void (*prepare_hook)(void),(*reset_hook)(void),(*sleep_hook)(void);
} sim;
static jmp_buf owner_exit;

int k_mem_slab_init(struct k_mem_slab *s,void *p,size_t n,uint32_t count)
{*s=(struct k_mem_slab){p,n,count,0,0};return 0;}
void k_mem_slab_free(struct k_mem_slab *s,void *p)
{size_t at=(size_t)((char *)p-s->buffer);REQUIRE(at<s->block_size*s->blocks&&at%s->block_size==0);
 unsigned bit=1u<<(at/s->block_size);REQUIRE(s->mask&bit);s->mask&=~bit;--s->used;}
uint32_t k_mem_slab_num_used_get(struct k_mem_slab *s){return s->used;}
void k_msgq_init(struct k_msgq *q,char *p,size_t n,uint32_t count)
{*q=(struct k_msgq){p,n,count,0,0};}
int k_msgq_put(struct k_msgq *q,const void *p,int timeout)
{REQUIRE(timeout==K_NO_WAIT);if(q->used==q->capacity)return -ENOMSG;
 memcpy(q->buffer+((q->head+q->used)%q->capacity)*q->msg_size,p,q->msg_size);++q->used;return 0;}
int k_msgq_get(struct k_msgq *q,void *p,int timeout)
{REQUIRE(timeout==K_NO_WAIT);if(!q->used)return -ENOMSG;
 memcpy(p,q->buffer+q->head*q->msg_size,q->msg_size);q->head=(q->head+1)%q->capacity;--q->used;return 0;}
uint32_t k_msgq_num_used_get(struct k_msgq *q){return q->used;}
int64_t k_uptime_get(void){return (int64_t)sim.ms;}
void k_msleep(int32_t ms)
{REQUIRE(ms>=0);sim.ms+=(unsigned)ms;
 if(sim.sleep_hook){void (*f)(void)=sim.sleep_hook;sim.sleep_hook=NULL;f();}
 if(sim.owner_running&&!--sim.owner_iterations)longjmp(owner_exit,1);}
uint32_t k_cycle_get_32(void){return (uint32_t)(sim.ms*1000);}
uint32_t k_cyc_to_us_floor32(uint32_t n){return n;}
struct k_thread *k_thread_create(struct k_thread *t,char *stack,size_t n,k_thread_entry_t fn,
    void *a,void *b,void *c,int priority,unsigned options,int delay)
{(void)stack;(void)n;(void)fn;(void)a;(void)b;(void)c;(void)priority;(void)options;(void)delay;return t;}
int k_thread_stack_space_get(const struct k_thread *t,size_t *out){(void)t;*out=1024;return 0;}
unsigned irq_lock(void){return sim.irq_depth++;}
void irq_unlock(unsigned key){REQUIRE(sim.irq_depth==key+1);--sim.irq_depth;}
k_spinlock_key_t k_spin_lock(struct k_spinlock *s){(void)s;return irq_lock();}
void k_spin_unlock(struct k_spinlock *s,k_spinlock_key_t key){(void)s;irq_unlock(key);}

int gpio_pin_configure_dt(const struct gpio_dt_spec *p,int flags)
{if(p->pin==mic.pin&&flags==GPIO_OUTPUT_INACTIVE)sim.power=0;return 0;}
int gpio_pin_get_dt(const struct gpio_dt_spec *p){REQUIRE(p->pin==privacy.pin);return sim.privacy;}
int gpio_pin_set_dt(const struct gpio_dt_spec *p,int value)
{if(p->pin==mic.pin){sim.power=value;if(value)++sim.powerups;}else if(p->pin==led.pin)sim.led=value;return 0;}
void gpio_init_callback(struct gpio_callback *c,
    void (*fn)(const struct device *,struct gpio_callback *,gpio_port_pins_t),uint32_t pins)
{(void)pins;c->handler=fn;}
int gpio_add_callback(const struct device *p,struct gpio_callback *c){(void)p;(void)c;return 0;}
int gpio_pin_interrupt_configure_dt(const struct gpio_dt_spec *p,int flags){(void)p;(void)flags;return 0;}
void uart_poll_out(const struct device *p,unsigned char ch)
{(void)p;REQUIRE(sim.used+1<sizeof(sim.output));sim.output[sim.used++]=(char)ch;sim.output[sim.used]=0;}
int uart_err_check(const struct device *p){(void)p;int r=sim.uart_error;sim.uart_error=0;return r;}
int uart_irq_update(const struct device *p){(void)p;return sim.input_offset<sim.input_bytes;}
int uart_irq_rx_ready(const struct device *p){return uart_irq_update(p);}
int uart_fifo_read(const struct device *p,uint8_t *out,int count)
{(void)p;size_t n=MIN((size_t)count,sim.input_bytes-sim.input_offset);
 memcpy(out,sim.input+sim.input_offset,n);sim.input_offset+=n;return (int)n;}
int uart_irq_callback_user_data_set(const struct device *p,void (*fn)(const struct device *,void *),void *u)
{(void)p;(void)fn;(void)u;return 0;}
void uart_irq_rx_enable(const struct device *p){(void)p;}
ssize_t hwinfo_get_device_id(uint8_t *p,size_t n){memset(p,0x42,n);return (ssize_t)n;}
int printk(const char *format,...){(void)format;return 0;}

int aura_dmic_health_get(const struct device *d,struct aura_dmic_health *h)
{(void)d;sim.health.queued_blocks=sim.raw_count;sim.health.slab_used_blocks=sim.slab?sim.slab->used:0;
 sim.health.drained=sim.health.stopped&&!sim.raw_count;*h=sim.health;return 0;}
int aura_dmic_health_reset(const struct device *d)
{(void)d;if(sim.reset_hook){void (*f)(void)=sim.reset_hook;sim.reset_hook=NULL;f();}
 if(!sim.health.stopped||sim.raw_count||(sim.slab&&sim.slab->used))return -EBUSY;
 memset(&sim.health,0,sizeof(sim.health));sim.health.stopped=sim.health.drained=true;sim.sequence=0;return 0;}
int dmic_configure(const struct device *d,struct dmic_cfg *c)
{(void)d;sim.slab=c->streams->mem_slab;c->channel.act_num_chan=2;c->channel.act_num_streams=1;
 c->channel.act_chan_map_lo=c->channel.req_chan_map_lo;return 0;}
int dmic_trigger(const struct device *d,enum dmic_trigger trigger)
{(void)d;if(trigger==DMIC_TRIGGER_START){REQUIRE(sim.power==1);sim.health.stopped=false;sim.health.active=true;}
 else{sim.health.active=false;if(sim.auto_quiesce)sim.health.stopped=true;}return 0;}
int dmic_read(const struct device *d,uint8_t stream,void **out,size_t *bytes,int32_t timeout)
{(void)d;REQUIRE(stream==0&&(timeout==0||timeout==100));
 if(!sim.raw_count){sim.ms+=(unsigned)timeout;return -EAGAIN;}
 *out=sim.raw[sim.raw_head].data;*bytes=AURA_AUDIO_RAW_BYTES;
 sim.health.last_read_sequence=sim.raw[sim.raw_head].sequence;
 sim.raw_head=(sim.raw_head+1)%8;--sim.raw_count;return 0;}

/* Recorder/storage/export doubles intentionally do not encode or touch NAND. */
int aura_recorder_init(struct aura_recorder *r,struct aura_journal *j,void *p,size_t n)
{memset(r,0,sizeof(*r));r->journal=j;r->encoder_state=p;r->encoder_bytes=n;return 0;}
int aura_recorder_start(struct aura_recorder *r,const struct aura_archive_manifest *m,uint64_t e,uint64_t now)
{(void)now;++sim.start_calls;if(sim.recorder_retries){--sim.recorder_retries;return AURA_JOURNAL_RETRY_PREPARE;}
 REQUIRE(e>r->last_epoch);r->epoch=r->last_epoch=e;r->state=AURA_RECORDER_RECORDING;r->source_samples=0;
 r->journal->active=0;r->journal->binding_pending=false;sim.started=*m;sim.started_epoch=e;return 0;}
int aura_recorder_consume(struct aura_recorder *r,const struct aura_recorder_block *b,uint64_t now,size_t *n)
{(void)now;REQUIRE(b->source_offset==r->source_samples&&b->epoch==r->epoch);*n=b->samples;r->source_samples+=*n;return 0;}
int aura_recorder_service(struct aura_recorder *r,uint64_t now){(void)r;(void)now;return 0;}
int aura_recorder_stop(struct aura_recorder *r,uint64_t e,uint64_t end,uint64_t now)
{(void)now;REQUIRE(e==r->epoch&&end==r->source_samples);++sim.stop_calls;
 if(sim.seal_error){r->state=AURA_RECORDER_FAILED;r->journal->fault=sim.seal_error;r->close_error=sim.seal_error;return sim.seal_error;}
 r->state=AURA_RECORDER_FINALIZED;r->journal->active=-1;return 0;}
int aura_recorder_interrupt(struct aura_recorder *r,uint64_t e,int reason,uint64_t now)
{(void)now;REQUIRE(e==r->epoch&&reason);++sim.interrupt_calls;r->state=AURA_RECORDER_INTERRUPTED;r->journal->active=-1;return 0;}
int aura_w25n01gv_zephyr_init(struct aura_w25n01gv_zephyr *d,const struct spi_dt_spec *s)
{(void)s;++sim.init_calls;d->initialized=true;return 0;}
int aura_w25n01gv_zephyr_configure_control(struct aura_w25n01gv_zephyr *d,uint16_t a,uint16_t b)
{(void)d;REQUIRE(a==1022&&b==1023);return 0;}
struct aura_nand_io aura_w25n01gv_zephyr_io(struct aura_w25n01gv_zephyr *d)
{return (struct aura_nand_io){.user=d,.blocks=1024};}
struct aura_control_io aura_w25n01gv_zephyr_control_io(struct aura_w25n01gv_zephyr *d)
{return (struct aura_control_io){.nand={.user=d,.blocks=1024}};}
static int accept_enrollment(struct aura_storage *s,struct aura_storage_io io,const struct aura_control_config *c,
 const struct aura_release_auth_context *a,struct aura_journal *j,struct aura_control *ctl,uint8_t *snap,size_t n)
{REQUIRE(!io.erase_released&&c->blocks[0]==1022&&c->blocks[1]==1023&&n==AURA_STORAGE_STATE_BYTES);
 REQUIRE(!memcmp(c->domain,a->storage_incarnation,16));sim.authority=*a;s->ready=true;s->journal=j;s->control=ctl;s->snapshot=snap;return 0;}
int aura_storage_provision(struct aura_storage *s,struct aura_storage_io io,const struct aura_control_config *c,
 const struct aura_release_auth_context *a,struct aura_journal *j,struct aura_control *ctl,uint8_t *snap,size_t n)
{++sim.provision_calls;return accept_enrollment(s,io,c,a,j,ctl,snap,n);}
int aura_storage_open(struct aura_storage *s,struct aura_storage_io io,const struct aura_control_config *c,
 const struct aura_release_auth_context *a,struct aura_journal *j,struct aura_control *ctl,uint8_t *snap,size_t n)
{++sim.open_calls;return accept_enrollment(s,io,c,a,j,ctl,snap,n);}
int aura_storage_prepare_capture(struct aura_storage *s,const struct aura_archive_manifest *in,struct aura_archive_manifest *out)
{(void)s;++sim.prepare_calls;if(sim.prepare_hook){void (*f)(void)=sim.prepare_hook;sim.prepare_hook=NULL;f();}
 if(sim.prepare_error)return sim.prepare_error;*out=*in;memcpy(out->device_id,device_id,16);
 memset(out->capture_id,0x23,16);journal.binding_pending=true;sim.prepared=*out;return 0;}
int aura_storage_cancel_prepared(struct aura_storage *s)
{(void)s;REQUIRE(journal.active<0&&journal.binding_pending);journal.binding_pending=false;++sim.cancel_calls;return 0;}
int aura_journal_verify(struct aura_journal *j,uint16_t index)
{REQUIRE(index<j->count);j->captures[index].verification=AURA_JOURNAL_VERIFIED_FINAL;return 0;}
int aura_journal_export(struct aura_journal *j,uint16_t index,aura_archive_commit output,void *user)
{REQUIRE(index<j->count);++sim.export_calls;uint8_t bytes[300];for(unsigned i=0;i<sizeof(bytes);++i)bytes[i]=(uint8_t)i;
 int r=output(user,0,bytes,68);if(r)return r;r=output(user,68,bytes+68,232);if(r)return r;
 if(sim.export_error)return sim.export_error;sim.exported=true;return 0;}
int aura_journal_receipt(const struct aura_journal *j,uint16_t index,uint8_t out[94])
{(void)j;(void)index;++sim.receipt_calls;REQUIRE(sim.exported);if(sim.receipt_error)return sim.receipt_error;
 memset(out,0x51,94);return 0;}

static void reset_sim(void)
{
    unsigned groups=sim.groups,cases=sim.cases;memset(&sim,0,sizeof(sim));sim.groups=groups;sim.cases=cases;
    sim.privacy=1;sim.auto_quiesce=true;sim.health.stopped=sim.health.drained=true;
    for(unsigned i=0;i<6;++i)bench_devices[i].ready=true;
    memset(&nand,0,sizeof(nand));memset(&storage,0,sizeof(storage));memset(&control,0,sizeof(control));
    memset(&journal,0,sizeof(journal));journal.active=-1;storage.ready=true;journal.io.blocks=1024;
    memset(snapshot,0,sizeof(snapshot));memset(device_id,0x17,16);memset(capture_id,0,16);
    k_msgq_init(&requests,requests_memory,sizeof(struct request),2);memset(&rx,0,sizeof(rx));
    rx_size=0;discard_line=false;cancellation=session_generation=startup_pending=capture_gate=initialized=rx_fault=0;
    boot_fault=0;epoch=started_ms=0;service_max_us=late_services=fifo_high_water=0;have_stop_reply=false;stop_reply_id=0;
    REQUIRE(!aura_recorder_init(&recorder,&journal,encoder.bytes,sizeof(encoder.bytes)));
    REQUIRE(!aura_audio_zephyr_init(&audio,&bench_devices[3],mic,permitted,NULL,&recorder,AURA_AUDIO_MEAN));
    atomic_set(&initialized,1);
}
static void receive(const char *line)
{sim.input=(const uint8_t *)line;sim.input_bytes=strlen(line);sim.input_offset=0;uart_input(uart,NULL);}
static void command(const char *line)
{receive(line);struct request request;REQUIRE(!k_msgq_get(&requests,&request,K_NO_WAIT));dispatch(&request);}
static void stop_event(void){receive("A04B 00000002 STOP\n");}
static void run_owner(unsigned count)
{sim.owner_running=true;sim.owner_iterations=(int)count;
 if(!setjmp(owner_exit))owner(NULL,NULL,NULL);sim.owner_running=false;}
static void supply_raw(void)
{REQUIRE(sim.slab&&sim.raw_count<8);unsigned slot=0;while(slot<sim.slab->blocks&&(sim.slab->mask&(1u<<slot)))++slot;
 REQUIRE(slot<sim.slab->blocks);sim.slab->mask|=1u<<slot;++sim.slab->used;
 int16_t *p=(int16_t *)(sim.slab->buffer+slot*sim.slab->block_size);
 for(unsigned i=0;i<AURA_AUDIO_FRAMES*2;++i)p[i]=(int16_t)(i%17);
 unsigned at=(sim.raw_head+sim.raw_count)%8;sim.raw[at].data=p;sim.raw[at].sequence=++sim.sequence;++sim.raw_count;}
static void start_running(void)
{command("A04B 00000001 START\n");REQUIRE(strstr(sim.output,"OK START"));
 for(unsigned i=0;i<5;++i){supply_raw();REQUIRE(!aura_audio_zephyr_reader_step(&audio));REQUIRE(!aura_audio_zephyr_service(&audio));}
 REQUIRE(atomic_get(&audio.state)==AURA_AUDIO_CAPTURING&&recorder.source_samples==320);}
static void drain_audio(void)
{for(unsigned i=0;i<24;++i){(void)aura_audio_zephyr_reader_step(&audio);(void)aura_audio_zephyr_service(&audio);
 if(!audio_pending())return;sim.ms+=20;}REQUIRE(false);}
static void pass_group(const char *name,unsigned cases)
{++sim.groups;sim.cases+=cases;printf("PASS %s (%u cases)\n",name,cases);}

static void normal_and_physical_stop(void)
{
    reset_sim();start_running();supply_raw();stop_event();
    REQUIRE(permitted(NULL)&&atomic_get(&audio.stop_kind)==1&&!atomic_get(&audio.fault));
    drain_audio();REQUIRE(atomic_get(&audio.state)==AURA_AUDIO_FINALIZED&&sim.stop_calls==1&&!sim.interrupt_calls);
    run_owner(2);REQUIRE(strstr(sim.output,"A04B 00000002 OK STOP 4 0 "));
    reset_sim();start_running();sim.privacy=0;privacy_changed(privacy.port,&privacy_callback,1u<<privacy.pin);
    REQUIRE(!sim.power&&atomic_get(&audio.stop_kind)==2&&atomic_get(&audio.fault)==AURA_AUDIO_PRIVACY);
    drain_audio();REQUIRE(atomic_get(&audio.state)==AURA_AUDIO_INTERRUPTED&&sim.interrupt_calls==1&&!sim.stop_calls);
    pass_group("actual adapter ordinary STOP finalizes; physical cutoff interrupts",2);
}
static void startup_cancellation(void)
{
    reset_sim();sim.prepare_hook=stop_event;command("A04B 00000001 START\n");
    REQUIRE(strstr(sim.output,"A04B 00000001 ERROR")&&!sim.powerups&&!sim.start_calls&&sim.cancel_calls==1);
    REQUIRE(!atomic_get(&startup_pending)&&!journal.binding_pending);run_owner(2);
    REQUIRE(strstr(sim.output,"A04B 00000002 OK STOP"));
    reset_sim();sim.reset_hook=stop_event;command("A04B 00000001 START\n");
    REQUIRE(strstr(sim.output,"A04B 00000001 ERROR")&&!sim.powerups&&sim.start_calls==1);
    drain_audio();REQUIRE(!audio_pending()&&!sim.power);run_owner(2);
    REQUIRE(strstr(sim.output,"A04B 00000002 OK STOP"));
    reset_sim();sim.recorder_retries=2;command("A04B 00000001 START\n");
    REQUIRE(sim.prepare_calls==1&&sim.start_calls==3&&epoch==1&&sim.started_epoch==1);
    REQUIRE(!memcmp(&sim.prepared,&sim.started,sizeof(sim.prepared))&&strstr(sim.output,"OK START"));
    reset_sim();sim.recorder_retries=1;sim.sleep_hook=stop_event;command("A04B 00000001 START\n");
    REQUIRE(sim.prepare_calls==1&&sim.start_calls==1&&sim.cancel_calls==1&&!sim.powerups);
    pass_group("cancellation across prepare/begin/reset and exact preparation retries",4);
}
static void failed_seal_and_quarantine(void)
{
    reset_sim();start_running();supply_raw();sim.seal_error=-901;stop_event();drain_audio();
    REQUIRE(atomic_get(&audio.state)==AURA_AUDIO_FAILED&&journal.active==0&&busy()&&!audio_pending());
    run_owner(2);REQUIRE(strstr(sim.output,"A04B 00000002 OK STOP 6 -901 ")&&!have_stop_reply);
    command("A04B 00000003 START\n");REQUIRE(strstr(sim.output,"A04B 00000003 ERROR"));
    command("A04B 00000004 STATS\n");REQUIRE(strstr(sim.output,"A04B 00000004 OK STATS"));
    command("A04B 00000007 INFO\n");REQUIRE(strstr(sim.output," 1 6 -901 "));
    reset_sim();start_running();sim.auto_quiesce=false;sim.privacy=0;privacy_changed(privacy.port,&privacy_callback,1);
    drain_audio();REQUIRE(atomic_get(&audio.state)==AURA_AUDIO_QUARANTINED&&!atomic_get(&audio.driver_quiescent));
    command("A04B 00000005 STOP\n");run_owner(1);REQUIRE(strstr(sim.output,"A04B 00000005 OK STOP 7 "));
    unsigned started=sim.start_calls;command("A04B 00000006 START\n");REQUIRE(sim.start_calls==started);
    pass_group("terminal seal failure replies while journal locked; quarantine stays locked",2);
}
static void framing_and_enrollment(void)
{
    reset_sim();const char *bad[]={"A04B 123 STOP\n","A04B z0000000 STOP\n","A04B 00000000 \n","NOT A REQUEST\n"};
    for(unsigned i=0;i<4;++i){receive(bad[i]);REQUIRE(!requests.used&&atomic_get(&rx_fault));atomic_clear(&rx_fault);}
    const uint8_t invalid_bytes[]={0,1,127,255};
    for(unsigned i=0;i<sizeof(invalid_bytes);++i){
        uint8_t malformed[]="A04B 00000008 INFO!\n";malformed[18]=invalid_bytes[i];
        sim.input=malformed;sim.input_bytes=sizeof(malformed)-1;sim.input_offset=0;uart_input(uart,NULL);
        REQUIRE(!requests.used&&atomic_get(&rx_fault));atomic_clear(&rx_fault);
    }
    char boundary[258];memset(boundary,'a',sizeof(boundary));memcpy(boundary,"A04B 00000008 ",14);
    boundary[255]='\n';boundary[256]=0;receive(boundary);REQUIRE(requests.used==1);
    struct request accepted;REQUIRE(!k_msgq_get(&requests,&accepted,K_NO_WAIT)&&strlen(accepted.line)==255);
    boundary[255]='a';boundary[256]='\n';boundary[257]=0;receive(boundary);REQUIRE(!requests.used&&atomic_get(&rx_fault));
    char oversized[400];memset(oversized,'a',sizeof(oversized));memcpy(oversized,"A04B 00000009 OPEN ",19);
    oversized[sizeof(oversized)-2]='\n';oversized[sizeof(oversized)-1]=0;receive(oversized);
    REQUIRE(!requests.used&&atomic_get(&rx_fault));run_owner(1);REQUIRE(!strstr(sim.output,"aaaa"));
    receive("A04B 0000000a INFO\n");REQUIRE(requests.used==1);run_owner(1);REQUIRE(strstr(sim.output,"0000000a OK INFO"));
    reset_sim();uint8_t bytes[88];memset(bytes,0x9b,sizeof(bytes));memcpy(bytes,device_id,16);
    memset(bytes+48,0,8);bytes[48]=7;char encoded[177],line[256];hex(bytes,88,encoded);
    snprintf(line,sizeof(line),"A04B 0000000b PROVISION %s\n",encoded);command(line);
    REQUIRE(sim.provision_calls==1&&sim.authority.owner_generation==7&&!memcmp(sim.authority.key,bytes+56,32));
    REQUIRE(strstr(sim.output,"OK PROVISION")&&!strstr(sim.output,encoded)&&!strstr(sim.output,"9b9b9b9b"));
    snprintf(line,sizeof(line),"A04B 0000000c OPEN %s\n",encoded);command(line);REQUIRE(sim.open_calls==1);
    encoded[0]='0';snprintf(line,sizeof(line),"A04B 0000000d OPEN %s\n",encoded);command(line);
    REQUIRE(sim.open_calls==1&&strstr(sim.output,"0000000d ERROR"));
    reset_sim();sim.uart_error=1;receive("A04B 0000000e STOP\n");REQUIRE(!requests.used&&!atomic_get(&cancellation));
    receive("A04B 0000000f INFO\n");REQUIRE(requests.used==1);
    reset_sim();receive("A04B 00000010 INFO\nA04B 00000011 INFO\nA04B 00000012 STOP\n");
    REQUIRE(requests.used==2&&atomic_get(&rx_fault)&&atomic_get(&audio.stop_kind)==1);
    pass_group("bounded RX framing, recovery, queue overflow and no enrollment key echo",17);
}
static void export_ordering(void)
{
    for(unsigned failure=0;failure<3;++failure){
        reset_sim();journal.count=1;memset(journal.captures[0].manifest+24,0x31,16);
        if(failure==1)sim.export_error=-902;if(failure==2)sim.receipt_error=-903;
        command("A04B 00000020 EXPORT 31313131313131313131313131313131\n");
        REQUIRE(sim.export_calls==1&&strstr(sim.output,"DATA 0000000000000000 "));
        REQUIRE(strstr(sim.output,"DATA 0000000000000044 ")&&strstr(sim.output,"DATA 00000000000000c4 "));
        if(!failure)REQUIRE(sim.receipt_calls==1&&strstr(sim.output,"END EXPORT 000000000000012c "));
        else REQUIRE(!strstr(sim.output,"END EXPORT")&&strstr(sim.output,"ERROR")&&sim.receipt_calls==(failure==2));
        size_t length=0;for(size_t i=0;i<sim.used;++i){++length;if(sim.output[i]=='\n'){REQUIRE(length<=384);length=0;}}
    }
    reset_sim();struct export state={.request_id=3};uint8_t byte=7;
    REQUIRE(send_data(&state,1,&byte,1)==-EIO&&!sim.used&&state.offset==0);
    pass_group("export chunks and receipt only after success; no END after failures",4);
}
int main(void)
{
    REQUIRE(journal.active==-1);
    normal_and_physical_stop();startup_cancellation();failed_seal_and_quarantine();framing_and_enrollment();export_ordering();
    printf("BENCH_CONTROL_OK groups=%u cases=%u hardware_tested=false\n",sim.groups,sim.cases);return 0;
}
