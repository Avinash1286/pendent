/* SPDX-License-Identifier: MIT */
#include "aura_storage.h"
#include "aura_journal_cursor.h"
#include "nand_model.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static struct nand_model model;
static struct aura_storage storage;
static struct aura_journal journal;
static struct aura_control control;
static struct aura_release_auth_context authority;
static struct aura_control_config config;
static _Alignas(struct aura_archive_manifest) uint8_t state[AURA_STORAGE_STATE_BYTES];
static struct aura_archive_writer writer;
static unsigned groups,cases,released;
static uint64_t get(const uint8_t *p,unsigned n)
{uint64_t v=0;for(unsigned i=0;i<n;++i)v|=(uint64_t)p[i]<<(8*i);return v;}
static void put(uint8_t *p,uint64_t v,unsigned n)
{for(unsigned i=0;i<n;++i)p[i]=(uint8_t)(v>>(8*i));}
static int control_erase(void *u,uint32_t b)
{
    assert(b==config.blocks[0]||b==config.blocks[1]);
    struct aura_nand_io io=model_io(u);return io.erase(io.user,b);
}
static struct aura_control_io control_io(void)
{return (struct aura_control_io){model_io(&model),&model,control_erase};}
static int released_erase(void *u,uint32_t b)
{
    assert(b<model.blocks&&b!=config.blocks[0]&&b!=config.blocks[1]);
    /* Independently prove the exact block was fenced in a committed authority
     * snapshot before this privileged callback was reached. */
    struct aura_control audit;uint8_t *snapshot=malloc(AURA_STORAGE_STATE_BYTES);assert(snapshot);
    assert(!aura_control_open(&audit,control_io(),&config));size_t bytes;
    assert(!aura_control_load(&audit,snapshot,AURA_STORAGE_STATE_BYTES,&bytes));
    assert(bytes>=352&&snapshot[5]==1);bool found=false;
    for(unsigned i=0;i<get(snapshot+262,2);++i)if(get(snapshot+352+44*i,2)==b)found=true;
    assert(found);free(snapshot);++released;
    struct aura_nand_io io=model_io(u);return io.erase(io.user,b);
}
static struct aura_storage_io storage_io(void)
{return (struct aura_storage_io){model_io(&model),control_io(),&model,released_erase};}
static void fresh(unsigned blocks)
{
    model_destroy(&model);model_init(&model,blocks);released=0;
    memset(&authority,0,sizeof(authority));memset(authority.device_id,0x11,16);
    memset(authority.storage_incarnation,0x33,16);memset(authority.owner_id,0x44,16);
    for(unsigned i=0;i<32;++i)authority.key[i]=(uint8_t)(i+1);authority.owner_generation=1;
    config=(struct aura_control_config){.blocks={(uint16_t)(blocks-2),(uint16_t)(blocks-1)}};
    memcpy(config.domain,authority.storage_incarnation,16);
    assert(!aura_storage_provision(&storage,storage_io(),&config,&authority,&journal,&control,state,sizeof(state)));
}
static int reopen(void)
{
    model_power_on(&model);
    return aura_storage_open(&storage,storage_io(),&config,&authority,&journal,&control,state,sizeof(state));
}
static int index_for(const uint8_t ack[94])
{
    for(unsigned i=0;i<journal.count;++i)if(!memcmp(journal.captures[i].manifest+8,ack+6,32))return (int)i;
    return -1;
}
static int start(struct aura_archive_manifest *out)
{
    struct aura_archive_manifest settings={.frame_samples=320,.pre_skip=40};
    int r=aura_storage_prepare_capture(&storage,&settings,out);if(r)return r;
    if(!journal.service_clock_started){r=aura_journal_service(&journal,0);if(r)return r;}
    return aura_archive_begin_staged(&writer,out,aura_journal_stage,&journal);
}
static int packet(unsigned bytes)
{
    struct aura_opus_packet p={.sequence=writer.audio_packets,.sample_offset=writer.encoded_samples,
        .sample_count=320,.bytes=(uint16_t)bytes};
    memset(p.data,0x33,bytes);p.data[0]=0x98;return aura_archive_opus_commit(&writer,&p);
}
static void capture(unsigned packets,bool finalized,uint8_t ack[94])
{
    struct aura_archive_manifest manifest;assert(!start(&manifest));
    for(unsigned i=0;i<packets;++i)assert(!packet(packets>60?1275:80));
    if(finalized){struct aura_opus_seal seal={.source_samples=writer.encoded_samples-40,
        .encoded_samples=writer.encoded_samples,.packets=writer.audio_packets,.pre_skip=40};
        assert(!aura_archive_finalize(&writer,&seal));}
    else assert(!aura_archive_interrupt(&writer));
    assert(!aura_journal_receipt(&journal,(uint16_t)(journal.count-1),ack));
}
static void sign(const uint8_t ack[94],uint64_t sequence,uint8_t wire[182])
{assert(!aura_release_sign(&authority,sequence,ack,94,wire,182));}
static void drain(void)
{
    int r=AURA_STORAGE_PENDING;unsigned steps=0;
    while(r==AURA_STORAGE_PENDING&&steps++<2048)r=aura_storage_release_step(&storage);
    assert(r==AURA_STORAGE_ALREADY_DONE);
}
static void group(const char *name){++groups;printf("PASS storage %u %s\n",groups,name);}
static void ordinary(void)
{
    fresh(8);assert(journal.block_state[6]==AURA_BLOCK_EXCLUDED&&journal.block_state[7]==AURA_BLOCK_EXCLUDED);
    uint8_t keep[94],ack[94],wire[182];capture(2,true,keep);capture(2,true,ack);sign(ack,1,wire);
    assert(aura_storage_request_release(&storage,wire,182)==AURA_STORAGE_PENDING);
    assert(released==0&&index_for(ack)<0&&index_for(keep)>=0);
    assert(aura_storage_request_release(&storage,wire,182)==AURA_STORAGE_PENDING);
    assert(!reopen());assert(released==0);drain();assert(released==1);
    assert(aura_storage_request_release(&storage,wire,182)==AURA_STORAGE_ALREADY_DONE);
    assert(!reopen());assert(aura_storage_request_release(&storage,wire,182)==AURA_STORAGE_ALREADY_DONE);
    int i=index_for(keep);assert(i>=0&&!aura_journal_verify(&journal,(uint16_t)i));
    uint8_t checked[94];assert(!aura_journal_receipt(&journal,(uint16_t)i,checked)&&!memcmp(checked,keep,94));
    assert(journal.count==1);group("durable grant precedes erase; exact retry and retained source survive reboot");
}
static void reservation(void)
{
    fresh(5);struct aura_archive_manifest settings={.frame_samples=320,.pre_skip=40},first,next;
    assert(!aura_storage_prepare_capture(&storage,&settings,&first));
    assert(aura_storage_prepare_capture(&storage,&settings,&next)==AURA_STORAGE_BUSY);
    assert(!aura_storage_cancel_prepared(&storage));assert(!reopen());
    assert(!aura_storage_prepare_capture(&storage,&settings,&next));assert(memcmp(first.capture_id,next.capture_id,16));
    uint8_t expected[16];assert(!aura_storage_capture_id(authority.device_id,authority.storage_incarnation,2,expected));
    assert(!memcmp(next.capture_id,expected,16));assert(!reopen());
    struct aura_archive_manifest third;assert(!aura_storage_prepare_capture(&storage,&settings,&third));
    assert(memcmp(third.capture_id,next.capture_id,16));
    assert(!aura_storage_cancel_prepared(&storage));
    uint8_t ack[94];capture(1,true,ack);uint32_t before=model.erases;
    assert(aura_storage_provision(&storage,storage_io(),&config,&authority,&journal,&control,state,sizeof(state))<0);
    assert(model.erases==before&&released==0);assert(!reopen());
    group("capture generation committed before binding; cancellation/reset never reuses IDs or formats audio");
}
static void rejected(void)
{
    fresh(8);uint8_t ack[94],wire[182],other[182];capture(1,true,ack);sign(ack,1,wire);
    uint64_t programs=model.programs,erases=model.erases;
    for(unsigned i=0;i<182;++i){memcpy(other,wire,182);other[i]^=1;assert(aura_storage_request_release(&storage,other,182)<0);++cases;}
    assert(model.programs==programs&&model.erases==erases&&!released);
    sign(ack,2,other);assert(aura_storage_request_release(&storage,other,182)==AURA_RELEASE_SEQUENCE_GAP);
    storage.io.erase_released=NULL;assert(aura_storage_request_release(&storage,wire,182)==AURA_STORAGE_UNSUPPORTED);
    assert(model.programs==programs);storage.io.erase_released=released_erase;
    uint8_t interrupted[94];capture(1,false,interrupted);sign(interrupted,1,other);
    assert(aura_storage_request_release(&storage,other,182)==AURA_STORAGE_UNSUPPORTED&&!released);
    struct aura_archive_manifest prepared,settings={.frame_samples=320,.pre_skip=40};
    assert(!aura_storage_prepare_capture(&storage,&settings,&prepared));
    assert(aura_storage_request_release(&storage,wire,182)==AURA_STORAGE_BUSY);
    assert(!aura_storage_cancel_prepared(&storage));
    assert(aura_storage_request_release(&storage,wire,182)==AURA_STORAGE_PENDING);drain();
    assert(aura_storage_request_release(&storage,other,182)<0);
    group("forged/replayed/gapped/nonfinal commands and missing erase capability cannot release");
}
static void cycling(void)
{
    fresh(7);uint8_t keep[94],ack[94],wire[182],previous[16]={0};capture(1,true,keep);
    uint32_t retained=journal.captures[0].first_block;uint8_t source_hash[32];
    aura_archive_sha256(model.pages[retained*64+3],2048,source_hash);
    for(unsigned n=1;n<=260;++n){
        capture(1,true,ack);assert(memcmp(ack+22,previous,16));memcpy(previous,ack+22,16);
        sign(ack,n,wire);assert(aura_storage_request_release(&storage,wire,182)==AURA_STORAGE_PENDING);
        if(n%2)assert(!reopen());drain();assert(!reopen());assert(journal.count==1);
        assert(aura_storage_request_release(&storage,wire,182)==AURA_STORAGE_ALREADY_DONE);
        uint8_t hash[32];aura_archive_sha256(model.pages[retained*64+3],2048,hash);assert(!memcmp(hash,source_hash,32));
        ++cases;
    }
    assert(released==260);int i=index_for(keep);assert(i>=0&&!aura_journal_verify(&journal,(uint16_t)i));
    group("260 acknowledged releases recycle bounded catalog while unacknowledged source remains unchanged");
}
static void wrapped(void)
{
    fresh(7);journal.allocation_cursor=4;uint8_t ack[94],wire[182];capture(125,true,ack);
    assert(journal.captures[0].first_block==4&&journal.captures[0].last_block==1);
    sign(ack,1,wire);assert(aura_storage_request_release(&storage,wire,182)==AURA_STORAGE_PENDING);
    assert(!reopen());assert(journal.count==0);drain();assert(released==3);
    assert(!reopen());assert(journal.count==0);
    group("wrapped multiblock grant fences every extent until durable completion");
}
static void grant_cuts(void)
{
    const size_t boundaries[]={0,1,80,255,700,2047,2048};
    for(unsigned op=1;op<=3;++op)for(unsigned k=0;k<7;++k){
        fresh(6);uint8_t ack[94],wire[182];capture(1,true,ack);sign(ack,1,wire);
        uint32_t source=journal.captures[0].first_block;uint8_t saved[2048];memcpy(saved,model.pages[source*64+3],2048);
        model.cut_program=model.programs+op;model.cut=boundaries[k]==2048?MODEL_CUT_AFTER:MODEL_CUT_PARTIAL;model.cut_bytes=boundaries[k];
        assert(aura_storage_request_release(&storage,wire,182)<0&&released==0);
        assert(!memcmp(saved,model.pages[source*64+3],2048));
        int opened=reopen();
        if(!opened&&state[5]==1){drain();assert(released==1);}
        else{assert(!released);assert(!memcmp(saved,model.pages[source*64+3],2048));}
        ++cases;
    }
    group("every grant header/body/commit program cut preserves source before committed permission");
}
static void release_cuts(void)
{
    for(unsigned cut=MODEL_CUT_BEFORE;cut<=MODEL_CUT_AFTER;++cut)for(unsigned pages=0;pages<=64;++pages){
        fresh(6);uint8_t ack[94],wire[182];capture(1,true,ack);sign(ack,1,wire);
        assert(aura_storage_request_release(&storage,wire,182)==AURA_STORAGE_PENDING);
        model.cut_erase=model.erases+1;model.cut=(enum model_cut)cut;model.cut_bytes=pages;
        assert(aura_storage_release_step(&storage)<0);assert(!reopen());
        assert(journal.count==0&&state[5]==1);drain();assert(!reopen());assert(journal.count==0);
        ++cases;
    }
    group("released-block erase cuts resume only the committed fenced set, with no early reuse");
}
static void completion_cuts(void)
{
    const size_t boundaries[]={0,1,255,700,2047,2048};
    for(unsigned op=1;op<=3;++op)for(unsigned k=0;k<6;++k){
        fresh(6);uint8_t keep[94],ack[94],wire[182];capture(1,true,keep);capture(1,true,ack);sign(ack,1,wire);
        uint16_t source=journal.captures[0].first_block;uint8_t saved[2048];memcpy(saved,model.pages[source*64+3],2048);
        assert(aura_storage_request_release(&storage,wire,182)==AURA_STORAGE_PENDING);
        model.cut_program=model.programs+op;model.cut=boundaries[k]==2048?MODEL_CUT_AFTER:MODEL_CUT_PARTIAL;model.cut_bytes=boundaries[k];
        assert(aura_storage_release_step(&storage)<0&&released==1);int opened=reopen();
        if(!opened&&state[5]==1)drain();
        assert(!memcmp(saved,model.pages[source*64+3],2048));++cases;
    }
    group("completion-write cuts preserve unrelated source and never publish an uncertain old floor");
}
static void changed_allocation(void)
{
    fresh(7);uint8_t ack[94],wire[182];capture(1,true,ack);uint16_t b=journal.captures[0].first_block;
    sign(ack,1,wire);assert(aura_storage_request_release(&storage,wire,182)==AURA_STORAGE_PENDING);
    uint8_t *h=model.pages[b*64+2];put(h+238,get(h+238,8)+1,8);put(h+252,aura_archive_crc32(h,252),4);
    uint64_t erases=model.erases;assert(aura_storage_release_step(&storage)==AURA_STORAGE_CHANGED);
    assert(model.erases==erases&&!released);assert(!reopen());
    assert(aura_storage_release_step(&storage)==AURA_STORAGE_CHANGED&&!released);
    group("a coherent newer allocation at an old grant block is never erased");
}
static void private_digest(uint8_t out[128])
{
    aura_archive_sha256((const uint8_t *)&storage,sizeof(storage),out);
    aura_archive_sha256((const uint8_t *)&journal,sizeof(journal),out+32);
    aura_archive_sha256((const uint8_t *)&control,sizeof(control),out+64);
    aura_archive_sha256(state,sizeof(state),out+96);
}
static void *aligned_within(uint8_t *area,size_t alignment)
{return area+(alignment-(uintptr_t)area%alignment)%alignment;}
static void input_output_aliases(void)
{
    fresh(5);struct aura_archive_manifest settings={.frame_samples=160,.pre_skip=40,
        .started_at_ms=1700000000000,.time_source=1};
    void *destinations[]={&storage,&storage.authority,&journal,&journal.committed.manifest,
        &control,state,state+sizeof(state)-8};
    uint8_t before[128],after[128];private_digest(before);
    uint64_t reads=model.reads,programs=model.programs,erases=model.erases,bad_queries=model.bad_queries;
    for(unsigned i=0;i<sizeof(destinations)/sizeof(destinations[0]);++i){
        assert(aura_storage_prepare_capture(&storage,&settings,destinations[i])==AURA_STORAGE_ARGUMENT);
        private_digest(after);assert(!memcmp(before,after,sizeof(before)));
        assert(model.reads==reads&&model.programs==programs&&model.erases==erases&&model.bad_queries==bad_queries);
        ++cases;
    }
    void *inputs[]={state,aligned_within(journal.scratch,_Alignof(struct aura_archive_manifest)),
        aligned_within(control.page,_Alignof(struct aura_archive_manifest))};
    for(unsigned i=0;i<sizeof(inputs)/sizeof(inputs[0]);++i){
        memcpy(inputs[i],&settings,sizeof(settings));struct aura_archive_manifest result;
        assert(!aura_storage_prepare_capture(&storage,inputs[i],&result));
        assert(result.frame_samples==160&&result.pre_skip==40&&result.started_at_ms==1700000000000&&result.time_source==1);
        uint8_t expected[16];assert(!aura_storage_capture_id(authority.device_id,authority.storage_incarnation,i+1,expected));
        assert(!memcmp(result.capture_id,expected,16));assert(!aura_storage_cancel_prepared(&storage));++cases;
    }
    assert(!aura_storage_prepare_capture(&storage,&settings,&settings));
    assert(settings.frame_samples==160&&settings.pre_skip==40&&settings.time_source==1);
    assert(!aura_storage_cancel_prepared(&storage));assert(!reopen());++cases;
    group("private output aliases fail before IO; overwritten input scratch and caller in-place manifests are copied safely");
}
static void provision_authority_alias(void)
{
    fresh(5);model_destroy(&model);model_init(&model,5);
    void *aliased=aligned_within(journal.scratch,_Alignof(struct aura_release_auth_context));
    memcpy(aliased,&authority,sizeof(authority));
    assert(!aura_storage_provision(&storage,storage_io(),&config,aliased,&journal,&control,state,sizeof(state)));
    assert(!memcmp(state+8,authority.device_id,16)&&!memcmp(state+24,authority.storage_incarnation,16));
    assert(!memcmp(state+40,authority.owner_id,16)&&get(state+56,8)==authority.owner_generation);
    assert(!memcmp(&storage.authority,&authority,sizeof(authority)));assert(!reopen());
    uint8_t ack[94],wire[182];capture(1,true,ack);sign(ack,1,wire);
    assert(aura_storage_request_release(&storage,wire,182)==AURA_STORAGE_PENDING);drain();++cases;
    group("provision copies trusted authority before blank-media scans overwrite journal scratch");
}
static void reject_changed_block(uint16_t block)
{
    uint8_t before[32],after[32];aura_archive_sha256(model.pages[block*64+3],2048,before);
    uint64_t programs=model.programs,erases=model.erases;
    assert(aura_storage_release_step(&storage)==AURA_STORAGE_CHANGED);
    assert(model.programs==programs&&model.erases==erases&&!released);assert(!reopen());
    assert(aura_storage_release_step(&storage)==AURA_STORAGE_CHANGED);
    assert(model.programs==programs&&model.erases==erases&&!released);
    aura_archive_sha256(model.pages[block*64+3],2048,after);assert(!memcmp(before,after,32));++cases;
}
static void changed_residual_identities(void)
{
    const unsigned checkpoint_fields[]={4,8,12,34,50,122,138};
    for(unsigned damaged=0;damaged<2;++damaged)for(unsigned i=0;i<7;++i){
        fresh(6);uint8_t ack[94],wire[182];capture(1,true,ack);uint16_t b=journal.captures[0].first_block;
        sign(ack,1,wire);assert(aura_storage_request_release(&storage,wire,182)==AURA_STORAGE_PENDING);
        uint8_t *h=model.pages[b*64+2],*cp=model.pages[b*64+63];
        if(damaged){put(h+238,get(h+238,8)+1,8);assert(get(h+252,4)!=aura_archive_crc32(h,252));}
        if(checkpoint_fields[i]==138)put(cp+138,get(cp+138,8)+1,8);
        else cp[checkpoint_fields[i]]^=1;
        put(cp+252,aura_archive_crc32(cp,252),4);
        reject_changed_block(b);
    }
    const unsigned data_fields[]={0,4,8,12,24,40};
    for(unsigned header=0;header<3;++header)for(unsigned late=0;late<2;++late)for(unsigned i=0;i<6;++i){
        fresh(6);uint8_t ack[94],wire[182];capture(1,true,ack);uint16_t b=journal.captures[0].first_block;
        sign(ack,1,wire);assert(aura_storage_request_release(&storage,wire,182)==AURA_STORAGE_PENDING);
        uint8_t *h=model.pages[b*64+2];
        if(header==1)memset(h,255,2048);
        if(header==2){put(h+238,get(h+238,8)+1,8);assert(get(h+252,4)!=aura_archive_crc32(h,252));}
        unsigned page=b*64+(late?62:3);
        if(late){model.pages[page]=malloc(2048);assert(model.pages[page]);memcpy(model.pages[page],model.pages[b*64+3],2048);}
        uint8_t *data=model.pages[page];data[data_fields[i]]^=1;put(data+2044,aura_archive_crc32(data,2044),4);
        memset(model.pages[b*64+63],255,2048);reject_changed_block(b);
    }
    /* Copy an actual later capture, including its valid archive payload and v2
     * allocation/checkpoint, into the old extent. Damage only the new header;
     * then repeat with both metadata pages erased so the data identity decides. */
    for(unsigned metadata_erased=0;metadata_erased<2;++metadata_erased){
        fresh(7);uint8_t ack[94],newer[94],wire[182];capture(1,true,ack);capture(1,true,newer);
        uint16_t b=journal.captures[0].first_block,new_block=journal.captures[1].first_block;
        sign(ack,1,wire);assert(aura_storage_request_release(&storage,wire,182)==AURA_STORAGE_PENDING);
        const unsigned occupied[]={2,3,63};
        for(unsigned i=0;i<3;++i){
            unsigned n=occupied[i];uint8_t *page=model.pages[b*64+n];
            memcpy(page,model.pages[new_block*64+n],2048);put(page+8,b,4);
            unsigned crc_at=n==3?2044:252;put(page+crc_at,aura_archive_crc32(page,crc_at),4);
        }
        assert(get(model.pages[b*64+63]+138,8)==2);
        if(metadata_erased){memset(model.pages[b*64+2],255,2048);memset(model.pages[b*64+63],255,2048);}
        else model.pages[b*64+2][252]^=1;
        reject_changed_block(b);
    }
    group("foreign surviving checkpoints/data defeat stale grants despite original, erased or damaged headers and page gaps");
}
static void select_buffered_cursor(struct aura_journal_cursor *cursor,const uint8_t ack[94])
{
    uint64_t reads=model.reads,programs=model.programs,erases=model.erases;
    assert(!aura_journal_cursor_open(cursor,&journal,ack+6));assert(model.reads==reads);
    int r=AURA_CURSOR_PENDING;unsigned steps=0;
    while(r==AURA_CURSOR_PENDING&&steps++<128)r=aura_journal_cursor_verify_step(cursor);
    assert(r==AURA_CURSOR_READY);
    struct aura_journal_cursor_info info;assert(!aura_journal_cursor_get_info(cursor,&info));
    assert(!memcmp(info.physical_receipt,ack,94)&&!info.derived_seal);
    assert(!aura_journal_cursor_seek(cursor,0));
    uint8_t first=0;uint64_t offset=UINT64_MAX;size_t bytes=0;r=AURA_CURSOR_PENDING;steps=0;
    while(r==AURA_CURSOR_PENDING&&steps++<128)r=aura_journal_cursor_read(cursor,&first,1,&offset,&bytes);
    assert(r==AURA_CURSOR_DATA&&offset==0&&bytes==1&&first=='A');
    /* Deliberately leave bytes buffered: invalidation must run before even a
     * NAND-free DATA response, not merely prevent the next physical read. */
    assert(cursor->buffer_at<cursor->buffer_bytes);
    assert(model.programs==programs&&model.erases==erases);
}
static void assert_cursor_stale(struct aura_journal_cursor *cursor)
{
    uint64_t reads=model.reads,programs=model.programs,erases=model.erases,bad=model.bad_queries;
    uint8_t out[16],untouched[16];memset(out,0xa5,sizeof(out));memcpy(untouched,out,sizeof(out));
    uint64_t offset=UINT64_MAX;size_t bytes=SIZE_MAX;
    assert(aura_journal_cursor_read(cursor,out,sizeof(out),&offset,&bytes)==AURA_CURSOR_STALE);
    assert(!bytes&&offset==UINT64_MAX&&!memcmp(out,untouched,sizeof(out)));
    struct aura_journal_cursor_info info;
    assert(aura_journal_cursor_get_info(cursor,&info)==AURA_CURSOR_STALE);
    assert(aura_journal_cursor_verify_step(cursor)==AURA_CURSOR_STALE);
    assert(aura_journal_cursor_seek(cursor,0)==AURA_CURSOR_STALE);
    assert(model.reads==reads&&model.programs==programs&&model.erases==erases&&model.bad_queries==bad);
}
static void cursor_owner_transitions(void)
{
    /* A host NAND model regression, not device concurrency or power evidence.
     * Every transition below runs on the same serialized storage owner. */
    for(unsigned scenario=0;scenario<5;++scenario){
        fresh(6);uint8_t ack[94];capture(2,true,ack);
        uint16_t retained=journal.captures[0].first_block;
        uint8_t original[64][32],blank[2048];memset(blank,255,sizeof(blank));
        for(unsigned i=0;i<64;++i){
            const uint8_t *page=model.pages[retained*64+i];
            aura_archive_sha256(page?page:blank,2048,original[i]);
        }
        struct aura_journal_cursor cursor;select_buffered_cursor(&cursor,ack);
        uint64_t epoch=journal.export_epoch,programs=model.programs,erases=model.erases;
        struct aura_archive_manifest settings={.frame_samples=320,.pre_skip=40},next;
        if(scenario==0){
            /* Reserving the next capture preempts export before its first
             * audio page exists, while the retained capture remains intact. */
            assert(!aura_storage_prepare_capture(&storage,&settings,&next));
            assert(journal.binding_pending&&storage.ready);
        }else if(scenario==1){
            /* The counter store reaches its first program attempt but fails
             * before any header bits change. The old authority can reopen. */
            model.cut_program=model.programs+1;model.cut=MODEL_CUT_BEFORE;model.lose_completion_only=true;
            assert(aura_storage_prepare_capture(&storage,&settings,&next)==AURA_NAND_UNCERTAIN);
            assert(model.programs==programs+1&&!storage.ready&&!journal.binding_pending);
        }else if(scenario==2||scenario==3){
            /* Test both context replacement during open and an early failed
             * control reload before prepare reaches counter reservation. */
            assert(control.current<2);unsigned page=config.blocks[control.current]*64+2;
            model.ecc[page]=2;
            int r=scenario==2?
                aura_storage_open(&storage,storage_io(),&config,&authority,&journal,&control,state,sizeof(state)):
                aura_storage_prepare_capture(&storage,&settings,&next);
            assert(r<0&&!storage.ready);model.ecc[page]=0;
            assert(model.programs==programs&&model.erases==erases);
        }else{
            assert(aura_storage_provision(&storage,storage_io(),&config,&authority,
                &journal,&control,state,sizeof(state))==AURA_STORAGE_CHANGED);
            assert(!storage.ready&&model.programs==programs&&model.erases==erases);
        }
        assert(journal.export_epoch!=epoch);assert_cursor_stale(&cursor);
        assert(!reopen());assert(journal.count==1&&!released);
        int index=index_for(ack);assert(index>=0&&!aura_journal_verify(&journal,(uint16_t)index));
        uint8_t checked[94];assert(!aura_journal_receipt(&journal,(uint16_t)index,checked));
        assert(!memcmp(checked,ack,94));
        for(unsigned i=0;i<64;++i){
            const uint8_t *page=model.pages[retained*64+i];
            uint8_t hash[32];aura_archive_sha256(page?page:blank,2048,hash);
            assert(!memcmp(hash,original[i],32));
        }
        /* Reopening never revives the old cursor or invalidates a newly
         * reverified replacement catalog entry when its stale call arrives. */
        assert_cursor_stale(&cursor);
        assert(!aura_journal_receipt(&journal,(uint16_t)index,checked)&&!memcmp(checked,ack,94));
        aura_journal_cursor_cancel(&cursor);++cases;
    }
    group("prepared capture and failed counter/reopen/reload/provision transitions invalidate buffered export without changing retained source");
}
int main(void)
{
    ordinary();reservation();rejected();cycling();wrapped();grant_cuts();release_cuts();completion_cuts();changed_allocation();
    input_output_aliases();provision_authority_alias();changed_residual_identities();cursor_owner_transitions();
    printf("RESULT storage groups=%u cases=%u owner_context=%zu journal_context=%zu snapshot_bytes=%u\n",
        groups,cases,sizeof(storage),sizeof(journal),(unsigned)sizeof(state));
    model_destroy(&model);return 0;
}
