/* SPDX-License-Identifier: MIT
 * Actual adapter/recorder/codec/archive/journal; fake deterministic OS+DMIC.
 * This does not simulate real threads, DMA timing or physical audio continuity.
 */
#include "aura_audio_zephyr.h"
#include "aura_dmic_health.h"
#include "nand_model.h"
#include <zephyr/audio/dmic.h>
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do{if(!(x)){fprintf(stderr,"FAIL audio line %d: %s\n",__LINE__,#x);return 1;}}while(0)
#define REQUIRE(x) do{if(!(x)){fprintf(stderr,"INVALID audio stub line %d: %s\n",__LINE__,#x);exit(2);}}while(0)
static struct aura_audio_zephyr audio;
static struct aura_recorder recorder;
static struct aura_journal journal;
static struct nand_model nand;
static union{max_align_t align;uint8_t bytes[AURA_OPUS_STATE_LIMIT];} arena;
static struct device dmic_device={true},gpio_device={true};
static unsigned groups;
struct queued_raw {void *p;size_t bytes;uint64_t sequence;};
static struct {
    uint64_t ms,next_sequence;
    struct aura_dmic_health health;
    struct k_mem_slab *slab;
    struct queued_raw raw[8];unsigned raw_head,raw_count;
    unsigned starts,stops,allocations,frees,high_events,unsafe_powerups,irq_depth,locked_health_reads;
    int config_error,start_error,stop_error,health_error,read_error,gpio_error;
    int power;bool permitted,auto_quiesce,wrong_map,privacy_latched;
    void (*sleep_hook)(void),(*read_hook)(void),(*reset_hook)(void),(*enable_hook)(void),(*deferred_hook)(void);
    void (*before_lock_hook)(void),(*copy_hook)(void);
} sim;

int k_mem_slab_init(struct k_mem_slab *s,void *p,size_t n,uint32_t blocks)
{*s=(struct k_mem_slab){p,n,blocks,0,0};return 0;}
static void *allocate(struct k_mem_slab *s)
{
    for(uint32_t n=0;n<s->blocks;++n)if(!(s->mask&(1u<<n))){
        s->mask|=1u<<n;++s->used;++sim.allocations;return s->buffer+n*s->block_size;}
    return NULL;
}
void k_mem_slab_free(struct k_mem_slab *s,void *p)
{
    uintptr_t at=(uintptr_t)p-(uintptr_t)s->buffer;
    REQUIRE(at<s->blocks*s->block_size&&at%s->block_size==0);
    uint32_t n=(uint32_t)(at/s->block_size);REQUIRE(s->mask&(1u<<n));
    s->mask&=~(1u<<n);--s->used;++sim.frees;
}
uint32_t k_mem_slab_num_used_get(struct k_mem_slab *s){return s->used;}
void k_msgq_init(struct k_msgq *q,char *p,size_t n,uint32_t count){*q=(struct k_msgq){p,n,count,0,0};}
int k_msgq_put(struct k_msgq *q,const void *p,int timeout)
{REQUIRE(timeout==K_NO_WAIT);if(q->used==q->capacity)return -ENOMSG;
 if(sim.copy_hook){void (*h)(void)=sim.copy_hook;sim.copy_hook=NULL;
     if(sim.irq_depth){REQUIRE(!sim.deferred_hook);sim.deferred_hook=h;}else h();}
 memcpy(q->buffer+((q->head+q->used)%q->capacity)*q->msg_size,p,q->msg_size);++q->used;return 0;}
int k_msgq_get(struct k_msgq *q,void *p,int timeout)
{REQUIRE(timeout==K_NO_WAIT);if(!q->used)return -ENOMSG;
 memcpy(p,q->buffer+q->head*q->msg_size,q->msg_size);q->head=(q->head+1)%q->capacity;--q->used;return 0;}
uint32_t k_msgq_num_used_get(struct k_msgq *q){return q->used;}
int64_t k_uptime_get(void){return (int64_t)sim.ms;}
void k_msleep(int32_t ms){REQUIRE(ms>=0);sim.ms+=(unsigned)ms;if(sim.sleep_hook){void (*h)(void)=sim.sleep_hook;sim.sleep_hook=NULL;h();}}
k_spinlock_key_t k_spin_lock(struct k_spinlock *s){(void)s;return sim.irq_depth++;}
void k_spin_unlock(struct k_spinlock *s,k_spinlock_key_t key)
{
    (void)s;REQUIRE(sim.irq_depth==key+1);--sim.irq_depth;
    if(!sim.irq_depth&&sim.deferred_hook){void (*h)(void)=sim.deferred_hook;sim.deferred_hook=NULL;h();}
}
unsigned int irq_lock(void)
{
    if(!sim.irq_depth&&sim.before_lock_hook){void (*h)(void)=sim.before_lock_hook;sim.before_lock_hook=NULL;h();}
    return sim.irq_depth++;
}
void irq_unlock(unsigned int key){k_spin_unlock(NULL,key);}
int gpio_pin_configure_dt(const struct gpio_dt_spec *g,int flags){(void)g;REQUIRE(flags==GPIO_OUTPUT_INACTIVE);sim.power=0;return sim.gpio_error;}
int gpio_pin_set_dt(const struct gpio_dt_spec *g,int value)
{
    (void)g;if(sim.gpio_error)return sim.gpio_error;
    if(value&&sim.enable_hook){void (*h)(void)=sim.enable_hook;sim.enable_hook=NULL;
        if(sim.irq_depth)sim.deferred_hook=h;else h();}
    sim.power=value;if(value){++sim.high_events;if(sim.privacy_latched)++sim.unsafe_powerups;}return 0;
}
int dmic_configure(const struct device *d,struct dmic_cfg *c)
{
    REQUIRE(d==&dmic_device);if(sim.config_error)return sim.config_error;
    REQUIRE(c->streams->pcm_rate==16000&&c->streams->pcm_width==16&&c->streams->block_size==1280);
    REQUIRE(c->channel.req_num_chan==2&&c->channel.req_num_streams==1);
    sim.slab=c->streams->mem_slab;sim.health.configured=true;
    c->channel.act_num_chan=2;c->channel.act_num_streams=1;
    c->channel.act_chan_map_lo=sim.wrong_map?UINT32_MAX:c->channel.req_chan_map_lo;return 0;
}
int dmic_trigger(const struct device *d,enum dmic_trigger trigger)
{
    REQUIRE(d==&dmic_device);
    if(trigger==DMIC_TRIGGER_START){++sim.starts;if(sim.start_error)return sim.start_error;
        REQUIRE(sim.power==1);sim.health.active=true;sim.health.stopped=false;sim.health.drained=false;return 0;}
    ++sim.stops;sim.health.active=false;sim.health.stopping=true;
    if(sim.auto_quiesce&&!sim.stop_error){sim.health.stopped=true;sim.health.stopping=false;}
    return sim.stop_error;
}
int dmic_read(const struct device *d,uint8_t stream,void **out,size_t *bytes,int32_t timeout)
{
    REQUIRE(d==&dmic_device&&stream==0&&(timeout==0||timeout==100));
    if(sim.read_hook){void (*h)(void)=sim.read_hook;sim.read_hook=NULL;h();}
    if(sim.read_error)return sim.read_error;
    if(!sim.raw_count){if(timeout)sim.ms+=(unsigned)timeout;return -EAGAIN;}
    struct queued_raw *r=&sim.raw[sim.raw_head];*out=r->p;*bytes=r->bytes;
    sim.health.last_read_sequence=r->sequence;++sim.health.delivered_blocks;
    sim.raw_head=(sim.raw_head+1)%8;--sim.raw_count;return 0;
}
int aura_dmic_health_get(const struct device *d,struct aura_dmic_health *h)
{
    REQUIRE(d==&dmic_device);if(sim.health_error)return sim.health_error;
    if(sim.irq_depth)++sim.locked_health_reads;
    sim.health.queued_blocks=sim.raw_count;sim.health.slab_used_blocks=sim.slab?sim.slab->used:0;
    sim.health.drained=sim.health.stopped&&!sim.raw_count;
    *h=sim.health;return 0;
}
int aura_dmic_health_reset(const struct device *d)
{
    REQUIRE(d==&dmic_device);if(sim.health_error)return sim.health_error;
    if(sim.reset_hook){void (*h)(void)=sim.reset_hook;sim.reset_hook=NULL;h();}
    if(!sim.health.stopped||sim.raw_count||(sim.slab&&sim.slab->used)||sim.health.owned_dma_buffers)return -EBUSY;
    uint32_t epoch=sim.health.epoch+1;memset(&sim.health,0,sizeof(sim.health));sim.health.epoch=epoch;
    sim.health.stopped=sim.health.drained=true;sim.next_sequence=0;return 0;
}
static bool permitted(void *user){REQUIRE(user==&sim);return sim.permitted;}
static int reset(enum aura_audio_mix mix)
{
    model_destroy(&nand);model_init(&nand,8);memset(&sim,0,sizeof(sim));
    sim.permitted=sim.auto_quiesce=true;sim.health.stopped=sim.health.drained=true;
    int r=aura_journal_mount(&journal,model_io(&nand));if(r)return r;
    r=aura_recorder_init(&recorder,&journal,arena.bytes,sizeof(arena.bytes));if(r)return r;
    struct gpio_dt_spec gpio={&gpio_device,0,0};
    return aura_audio_zephyr_init(&audio,&dmic_device,gpio,permitted,&sim,&recorder,mix);
}
static int begin(unsigned id,uint64_t epoch)
{
    struct aura_archive_manifest m={.frame_samples=320,.pre_skip=40};
    memset(m.device_id,17,16);memset(m.capture_id,(int)id,16);
    return aura_audio_zephyr_begin(&audio,&m,epoch);
}
static int raw(int16_t first,int16_t second)
{
    CHECK(sim.slab&&sim.raw_count<8);int16_t *p=allocate(sim.slab);CHECK(p);
    for(unsigned n=0;n<320;++n){p[2*n]=first;p[2*n+1]=second;}
    unsigned at=(sim.raw_head+sim.raw_count)%8;
    sim.raw[at]=(struct queued_raw){p,1280,++sim.next_sequence};++sim.raw_count;++sim.health.completed_blocks;return 0;
}
static int warmup(void)
{
    for(unsigned n=0;n<4;++n){CHECK(!raw(111,222));CHECK(!aura_audio_zephyr_reader_step(&audio));
        CHECK(audio.published_samples==0&&audio.queue.used==0&&audio.slab.used==0);}
    CHECK(!audio.warmup_remaining);return 0;
}
static int finish(void)
{
    for(unsigned n=0;n<40;++n){(void)aura_audio_zephyr_reader_step(&audio);(void)aura_audio_zephyr_service(&audio);
        if(atomic_get(&audio.reader_done)&&!audio.queue.used)return 0;sim.ms+=10;}
    return 1;
}
static int mixing(void)
{
    const int16_t pairs[][2]={{32767,32767},{-32768,-32768},{-32768,32767},{20000,-10000}};
    for(unsigned mix=0;mix<3;++mix){CHECK(!reset((enum aura_audio_mix)mix));CHECK(!begin(1,1));
        CHECK(nand.programs==1&&sim.power==1&&sim.starts==1);CHECK(!warmup());
        for(unsigned k=0;k<4;++k){CHECK(!raw(pairs[k][0],pairs[k][1]));CHECK(!aura_audio_zephyr_reader_step(&audio));
            struct aura_audio_message msg;CHECK(!k_msgq_get(&audio.queue,&msg,K_NO_WAIT));
            int32_t expected=mix==0?pairs[k][0]:mix==1?pairs[k][1]:((int32_t)pairs[k][0]+pairs[k][1])/2;
            CHECK(msg.epoch==1&&msg.sequence==k&&msg.source_offset==k*320);
            for(unsigned n=0;n<320;++n)CHECK(msg.pcm[n]==expected);
            CHECK(!k_msgq_put(&audio.queue,&msg,K_NO_WAIT));CHECK(!aura_audio_zephyr_service(&audio));
        }
        CHECK(audio.peak[0]==32768&&audio.peak[1]==32768);CHECK(audio.clipped[0]==960&&audio.clipped[1]==960);
        aura_audio_zephyr_request_stop(&audio);CHECK(!raw(11,22));CHECK(!aura_audio_zephyr_reader_step(&audio));CHECK(!finish());
        CHECK(audio.state==AURA_AUDIO_FINALIZED&&recorder.seal.source_samples==1600);
        CHECK(sim.power==0&&sim.allocations==sim.frees&&audio.slab.used==0&&audio.queue.used==0);
    }
    ++groups;return 0;
}
static int fifo_stop(void)
{
    CHECK(!reset(AURA_AUDIO_MEAN));CHECK(!begin(1,1));CHECK(!warmup());
    for(unsigned n=0;n<5;++n){CHECK(!raw(1000,-200));CHECK(!aura_audio_zephyr_reader_step(&audio));}
    CHECK(audio.queue.used==5&&recorder.source_samples==0);
    aura_audio_zephyr_request_stop(&audio);CHECK(!raw(300,400));CHECK(!raw(500,600));
    CHECK(!aura_audio_zephyr_reader_step(&audio));CHECK(!finish());
    CHECK(audio.state==AURA_AUDIO_FINALIZED&&recorder.source_samples==2240&&recorder.seal.source_samples==2240);
    CHECK(sim.allocations==sim.frees&&!audio.slab.used&&!audio.queue.used);
    model_power_on(&nand);CHECK(!aura_journal_mount(&journal,model_io(&nand)));CHECK(!aura_journal_verify(&journal,0));
    CHECK(journal.captures[0].verification==AURA_JOURNAL_VERIFIED_FINAL);
    ++groups;return 0;
}
static int overflow_and_driver(void)
{
    CHECK(!reset(AURA_AUDIO_FIRST));CHECK(!begin(1,1));CHECK(!warmup());
    for(unsigned n=0;n<16;++n){CHECK(!raw(100,200));CHECK(!aura_audio_zephyr_reader_step(&audio));}
    CHECK(!raw(300,400));CHECK(aura_audio_zephyr_reader_step(&audio)==AURA_AUDIO_QUEUE_FULL);
    CHECK(audio.published_samples==5120&&audio.queue.used==16);CHECK(!finish());
    CHECK(audio.state==AURA_AUDIO_INTERRUPTED&&recorder.fault_reason==AURA_AUDIO_QUEUE_FULL);
    CHECK(recorder.source_samples==5120&&recorder.archive.status==AURA_ARCHIVE_INTERRUPTED);
    CHECK(sim.allocations==sim.frees&&!audio.slab.used&&!audio.queue.used);
    for(unsigned mode=0;mode<2;++mode){
        CHECK(!reset(AURA_AUDIO_FIRST));CHECK(!begin(1,1));CHECK(!warmup());
        CHECK(!raw(100,200));CHECK(!aura_audio_zephyr_reader_step(&audio));CHECK(!aura_audio_zephyr_service(&audio));
        CHECK(!raw(300,400));if(mode==0)sim.health.faults=AURA_DMIC_FAULT_OVERFLOW;
        else sim.raw[sim.raw_head].sequence++;
        (void)aura_audio_zephyr_reader_step(&audio);CHECK(!finish());
        CHECK(audio.state==AURA_AUDIO_INTERRUPTED&&recorder.source_samples==320);
        CHECK(recorder.fault_reason==(mode==0?AURA_AUDIO_DRIVER:AURA_AUDIO_SEQUENCE));
        CHECK(sim.allocations==sim.frees&&!audio.slab.used&&!audio.queue.used);
    }
    ++groups;return 0;
}
static void privacy_software_hook(void){aura_audio_zephyr_privacy_cutoff(&audio);REQUIRE(sim.power==0);sim.privacy_latched=true;}
static void stop_hook(void){aura_audio_zephyr_request_stop(&audio);}
static void privacy_hook(void){privacy_software_hook();sim.permitted=false;}
static int privacy_and_start_failure(void)
{
    CHECK(!reset(AURA_AUDIO_FIRST));sim.sleep_hook=privacy_hook;
    CHECK(begin(1,1)==-ECANCELED);CHECK(sim.power==0&&sim.starts==0);CHECK(!finish());
    CHECK(audio.state==AURA_AUDIO_INTERRUPTED&&recorder.source_samples==0&&recorder.fault_reason==AURA_AUDIO_PRIVACY);
    CHECK(sim.allocations==sim.frees&&!audio.slab.used);
    CHECK(!reset(AURA_AUDIO_SECOND));CHECK(!begin(1,1));CHECK(!warmup());CHECK(!raw(100,200));
    sim.read_hook=privacy_hook;CHECK(aura_audio_zephyr_reader_step(&audio)==AURA_AUDIO_PRIVACY);CHECK(!finish());
    CHECK(audio.state==AURA_AUDIO_INTERRUPTED&&audio.published_samples==0&&sim.power==0);
    CHECK(sim.allocations==sim.frees&&!audio.slab.used);
    CHECK(!reset(AURA_AUDIO_FIRST));sim.start_error=-EIO;CHECK(begin(1,1)==-EIO);CHECK(!finish());
    CHECK(audio.state==AURA_AUDIO_INTERRUPTED&&recorder.source_samples==0&&sim.power==0);
    ++groups;return 0;
}
static int quarantine_and_restart(void)
{
    CHECK(!reset(AURA_AUDIO_FIRST));CHECK(!begin(1,1));CHECK(!warmup());
    sim.auto_quiesce=false;sim.health.owned_dma_buffers=1;void *dma=allocate(sim.slab);CHECK(dma);
    aura_audio_zephyr_request_stop(&audio);CHECK(!raw(1,2));CHECK(!aura_audio_zephyr_reader_step(&audio));
    CHECK(!finish());CHECK(audio.state==AURA_AUDIO_QUARANTINED&&!audio.driver_quiescent&&sim.power==0);
    CHECK(audio.slab.used==1&&sim.allocations==sim.frees+1);CHECK(begin(2,2)==-EBUSY);
    /* Explicit simulated cold DMA shutdown after assertions; this is not an
     * application permission to free a buffer which real DMA still owns. */
    sim.health.owned_dma_buffers=0;k_mem_slab_free(sim.slab,dma);
    CHECK(!reset(AURA_AUDIO_FIRST));CHECK(!begin(1,1));aura_audio_zephyr_request_stop(&audio);CHECK(!finish());
    CHECK(audio.state==AURA_AUDIO_FINALIZED&&recorder.source_samples==0);
    CHECK(!begin(2,2));CHECK(!warmup());CHECK(!raw(5,6));CHECK(!aura_audio_zephyr_reader_step(&audio));
    struct aura_audio_message msg;CHECK(!k_msgq_get(&audio.queue,&msg,0));CHECK(msg.epoch==2&&msg.sequence==0&&msg.source_offset==0);
    CHECK(!k_msgq_put(&audio.queue,&msg,0));CHECK(!aura_audio_zephyr_service(&audio));
    CHECK(recorder.epoch==2&&recorder.source_samples==320);aura_audio_zephyr_privacy_cutoff(&audio);CHECK(!finish());
    CHECK(sim.allocations==sim.frees&&!audio.slab.used&&!audio.queue.used);
    ++groups;return 0;
}
static int storage_failure(void)
{
    CHECK(!reset(AURA_AUDIO_FIRST));CHECK(!begin(1,1));CHECK(!warmup());
    nand.program_failure[0]=1;CHECK(!raw(100,200));CHECK(!aura_audio_zephyr_reader_step(&audio));
    CHECK(aura_audio_zephyr_service(&audio)==AURA_NAND_PROGRAM_FAILED);
    CHECK(recorder.source_samples==320&&recorder.state==AURA_RECORDER_FAILED);
    uint64_t programs=nand.programs;CHECK(!finish());
    CHECK(audio.state==AURA_AUDIO_FAILED&&recorder.source_samples==320&&nand.programs==programs&&sim.power==0);
    CHECK(sim.allocations==sim.frees&&!audio.slab.used&&!audio.queue.used);
    ++groups;return 0;
}
static int startup_races(void)
{
    for(unsigned mode=0;mode<2;++mode){
        CHECK(!reset(AURA_AUDIO_FIRST));sim.reset_hook=mode?stop_hook:privacy_software_hook;
        CHECK(begin(1,1)<0);CHECK(sim.power==0&&sim.high_events==0&&sim.starts==0);
        CHECK(!finish());CHECK(audio.state==AURA_AUDIO_INTERRUPTED||audio.state==AURA_AUDIO_FAILED);
        CHECK(!recorder.source_samples&&!audio.slab.used&&!audio.queue.used);
    }
    CHECK(!reset(AURA_AUDIO_FIRST));sim.enable_hook=privacy_software_hook;
    CHECK(begin(1,1)<0);CHECK(!finish());
    CHECK(sim.unsafe_powerups==0&&sim.power==0&&sim.starts==0);
    CHECK(audio.state==AURA_AUDIO_INTERRUPTED||audio.state==AURA_AUDIO_FAILED);
    ++groups;return 0;
}
static int negative_driver_results(void)
{
    CHECK(!reset(AURA_AUDIO_FIRST));sim.wrong_map=true;CHECK(begin(1,1)==-ENOTSUP);CHECK(!finish());
    CHECK(sim.starts==0&&sim.power==0&&audio.state==AURA_AUDIO_INTERRUPTED);
    CHECK(!reset(AURA_AUDIO_FIRST));CHECK(!begin(1,1));CHECK(!raw(1,2));sim.raw[sim.raw_head].bytes=1000;
    CHECK(aura_audio_zephyr_reader_step(&audio)==AURA_AUDIO_BAD_BUFFER);CHECK(!finish());
    CHECK(audio.state==AURA_AUDIO_INTERRUPTED&&sim.allocations==sim.frees&&!audio.slab.used);
    CHECK(!reset(AURA_AUDIO_FIRST));CHECK(!begin(1,1));CHECK(!warmup());
    CHECK(!raw(100,200));CHECK(!aura_audio_zephyr_reader_step(&audio));
    /* Deliberately drop the final queued message: published end must prevent
     * the drained queue from being mislabeled a zero-source clean stop. */
    struct aura_audio_message lost;CHECK(!k_msgq_get(&audio.queue,&lost,0));
    aura_audio_zephyr_request_stop(&audio);CHECK(!raw(300,400));
    CHECK(!aura_audio_zephyr_reader_step(&audio));CHECK(!finish());
    CHECK(audio.state==AURA_AUDIO_INTERRUPTED&&recorder.fault_reason==AURA_RECORDER_GAP);
    CHECK(sim.allocations==sim.frees&&!audio.slab.used&&!audio.queue.used);
    ++groups;return 0;
}
static void known_driver_fault(void){sim.health.faults=AURA_DMIC_FAULT_OVERFLOW;}
static int publication_interleavings(void)
{
    /* A cutoff immediately before the publication critical section sees all
     * earlier permission checks pass, but must discard this raw block. */
    CHECK(!reset(AURA_AUDIO_FIRST));CHECK(!begin(1,1));CHECK(!warmup());CHECK(!raw(100,200));
    sim.before_lock_hook=privacy_software_hook;
    CHECK(aura_audio_zephyr_reader_step(&audio)==AURA_AUDIO_PRIVACY);CHECK(!sim.before_lock_hook);
    CHECK(!audio.queue.used&&audio.published_samples==0&&audio.published_blocks==0);
    CHECK(!finish());CHECK(audio.state==AURA_AUDIO_INTERRUPTED&&recorder.source_samples==0);
    CHECK(sim.power==0&&!audio.slab.used&&sim.allocations==sim.frees);

    /* A pending ISR during K_NO_WAIT copy cannot run through the lock. This
     * already-publishing block is retained; a second queued DMA block is not. */
    CHECK(!reset(AURA_AUDIO_MEAN));CHECK(!begin(1,1));CHECK(!warmup());
    CHECK(!raw(32767,-32768));CHECK(!raw(20000,10000));sim.copy_hook=privacy_software_hook;
    CHECK(!aura_audio_zephyr_reader_step(&audio));CHECK(!sim.copy_hook&&!sim.deferred_hook);
    CHECK(sim.privacy_latched&&sim.power==0&&sim.irq_depth==0);
    CHECK(audio.queue.used==1&&audio.published_samples==320&&audio.published_blocks==1);
    CHECK(!finish());CHECK(audio.state==AURA_AUDIO_INTERRUPTED&&recorder.source_samples==320);
    CHECK(recorder.fault_reason==AURA_AUDIO_PRIVACY&&audio.published_samples==320);
    CHECK(!audio.queue.used&&!audio.slab.used&&sim.allocations==sim.frees);

    /* The earlier post-read health snapshot was healthy; a newly known fault
     * must be observed again at the final guarded publication check. */
    CHECK(!reset(AURA_AUDIO_SECOND));CHECK(!begin(1,1));CHECK(!warmup());CHECK(!raw(100,200));
    unsigned before=sim.locked_health_reads;sim.before_lock_hook=known_driver_fault;
    CHECK(aura_audio_zephyr_reader_step(&audio)==AURA_AUDIO_DRIVER);CHECK(!sim.before_lock_hook);
    CHECK(sim.locked_health_reads==before+1&&audio.published_samples==0&&!audio.queue.used);
    CHECK(!finish());CHECK(audio.state==AURA_AUDIO_INTERRUPTED&&recorder.source_samples==0);
    CHECK(recorder.fault_reason==AURA_AUDIO_DRIVER&&!audio.slab.used&&sim.allocations==sim.frees);
    ++groups;return 0;
}
static int init_live_ownership(void)
{
    for(unsigned mode=0;mode<3;++mode){
        CHECK(!reset(AURA_AUDIO_FIRST));void *owned=NULL;audio.epoch=777;
        if(mode==0)sim.health.owned_dma_buffers=1;
        if(mode==1){sim.slab=&audio.slab;owned=allocate(sim.slab);CHECK(owned);}
        if(mode==2)sim.health.stopped=false;
        uint8_t before[sizeof(audio)];memcpy(before,&audio,sizeof(audio));
        struct gpio_dt_spec gpio={&gpio_device,0,0};
        CHECK(aura_audio_zephyr_init(&audio,&dmic_device,gpio,permitted,&sim,&recorder,AURA_AUDIO_MEAN)==-EBUSY);
        CHECK(!memcmp(before,&audio,sizeof(audio)));CHECK(!sim.high_events&&!sim.starts&&!sim.stops);
        if(owned){CHECK(audio.slab.used==1);k_mem_slab_free(sim.slab,owned);}
    }
    ++groups;return 0;
}
int main(void)
{
    int failures=0;failures+=mixing();failures+=fifo_stop();failures+=overflow_and_driver();
    failures+=privacy_and_start_failure();failures+=quarantine_and_restart();failures+=storage_failure();
    failures+=startup_races();failures+=negative_driver_results();
    failures+=publication_interleavings();failures+=init_live_ownership();
    printf("Audio adapter deterministic host interleavings: %u groups PASS, %d failed; context=%u bytes\n",
        groups,failures,(unsigned)sizeof(audio));
    printf("Actual adapter/recorder/Opus/journal code; no physical PDM, DMA or concurrent-thread proof\n");
    model_destroy(&nand);return failures?1:0;
}
