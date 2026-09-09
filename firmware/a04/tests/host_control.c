/* SPDX-License-Identifier: MIT
 * Deterministic NAND operation faults, not physical power-loss qualification.
 * Uses the actual control implementation and the existing strict NAND model.
 */
#include "aura_control.h"
#include "aura_archive.h"
#include "nand_model.h"
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static struct nand_model media,alternate;
static struct aura_control control,opened,stale;
static const struct aura_control_config config={{1,6},{1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16}};
static uint8_t input[AURA_CONTROL_MAX_BYTES],second[AURA_CONTROL_MAX_BYTES],output[AURA_CONTROL_MAX_BYTES];
static uint8_t canary_hash[32];
static unsigned groups,cases,guarded_erases;
static bool exact_program_fail,dirty_erase,substitute;
static bool arm_substitute;
static uint64_t arm_after_programs;
static uint32_t substitute_page;
static uint8_t *substitute_pages[64];

static uint8_t *cell(struct nand_model *m,uint32_t page)
{
    if(!m->pages[page]){m->pages[page]=malloc(2048);assert(m->pages[page]);memset(m->pages[page],255,2048);}
    return m->pages[page];
}
static void pattern(uint8_t *p,size_t bytes,unsigned seed)
{for(size_t n=0;n<bytes;++n)p[n]=(uint8_t)(n*37+seed);}
static void page_crc(uint8_t *p)
{
    uint32_t n=aura_archive_crc32(p,2044);
    for(unsigned i=0;i<4;++i)p[2044+i]=(uint8_t)(n>>(8*i));
}
static void put(uint8_t *p,uint64_t n,unsigned bytes)
{for(unsigned i=0;i<bytes;++i)p[i]=(uint8_t)(n>>(8*i));}
static int read_control(void *user,uint32_t page,uint16_t column,uint8_t *out,size_t bytes)
{
    struct nand_model *m=user;
    if(substitute&&page==substitute_page){
        substitute=false;uint32_t first=page/64*64;
        for(unsigned n=0;n<64;++n){
            free(m->pages[first+n]);m->pages[first+n]=NULL;
            if(substitute_pages[n])memcpy(cell(m,first+n),substitute_pages[n],2048);
        }
    }
    int r=model_io(m).read(m,page,column,out,bytes);
    if(arm_substitute&&page==6*64+63&&m->programs==arm_after_programs){
        arm_substitute=false;substitute=true;
    }
    return r;
}
static int program_control(void *user,uint32_t page,const uint8_t data[2048])
{
    struct nand_model *m=user;
    assert(page/64==config.blocks[0]||page/64==config.blocks[1]);
    int r=model_io(m).program(m,page,data);
    if(!r&&exact_program_fail)return AURA_NAND_PROGRAM_FAILED;
    return r;
}
static int erase_control(void *user,uint32_t block)
{
    struct nand_model *m=user;
    /* Integration-side guard is separate from the primitive's private guard. */
    if(block!=config.blocks[0]&&block!=config.blocks[1])return AURA_CONTROL_BAD_ARGUMENT;
    ++guarded_erases;int r=model_io(m).erase(m,block);
    if(!r&&dirty_erase)cell(m,block*64+40)[31]=0;
    return r;
}
static struct aura_control_io io_for(struct nand_model *m)
{
    struct aura_nand_io io=model_io(m);io.read=read_control;io.program=program_control;
    /* Deliberately unavailable ordinary erase: rotation must use its distinct
     * privileged control interface and may never fall back to audio erase. */
    io.erase=NULL;return (struct aura_control_io){io,m,erase_control};
}
static struct aura_control_io io(void){return io_for(&media);}
static void preserve_audio(void)
{
    uint8_t digest[32];aura_archive_sha256(cell(&media,3*64+3),2048,digest);
    assert(!memcmp(digest,canary_hash,32));
    assert(media.attempts[3*64+3]==1&&media.highest[3]==3);
    for(unsigned slot=0;slot<2;++slot)for(unsigned n=0;n<2;++n){
        assert(media.attempts[config.blocks[slot]*64+n]==0);
        for(unsigned k=0;k<3;++k)assert(media.marker[config.blocks[slot]][n][k]==255);
    }
}
static void fresh(void)
{
    model_destroy(&media);model_init(&media,8);exact_program_fail=dirty_erase=substitute=arm_substitute=false;
    for(unsigned n=0;n<64;++n){free(substitute_pages[n]);substitute_pages[n]=NULL;}
    pattern(input,sizeof(input),17);pattern(second,sizeof(second),43);
    uint8_t page[2048];pattern(page,sizeof(page),123);
    assert(model_io(&media).program(&media,3*64+3,page)==0);
    aura_archive_sha256(page,sizeof(page),canary_hash);
}
static void provision(size_t bytes)
{assert(aura_control_provision(&control,io(),&config,input,bytes)==0);assert(control.generation==1);}
static void load_equal(struct aura_control *c,const uint8_t *expected,size_t bytes)
{
    size_t count=SIZE_MAX;assert(aura_control_load(c,output,sizeof(output),&count)==0);
    assert(count==bytes&&!memcmp(output,expected,bytes));
}
static void snapshot_hash(uint16_t block,uint8_t digest[32])
{
    uint8_t chain[32]={0},wire[2080];
    for(unsigned n=0;n<64;++n){
        memcpy(wire,chain,32);
        assert(model_io(&media).read(&media,block*64+n,0,wire+32,2048)>=0);
        aura_archive_sha256(wire,sizeof(wire),chain);
    }
    memcpy(digest,chain,32);
}
static void group(const char *name)
{++groups;printf("PASS %02u %s\n",groups,name);}

static void ordinary(void)
{
    fresh();uint64_t programs=media.programs,erases=media.erases;
    assert(aura_control_open(&opened,io(),&config)==AURA_CONTROL_UNPROVISIONED);
    assert(opened.reads==128&&media.programs==programs&&media.erases==erases);
    provision(4000);load_equal(&control,input,4000);
    assert(control.current==0&&media.highest[1]==63);
    assert(aura_control_store(&control,second,AURA_CONTROL_MAX_BYTES)==0);
    assert(control.generation==2&&control.current==1);
    model_power_on(&media);assert(aura_control_open(&opened,io(),&config)==0);
    assert(opened.reads==128);load_equal(&opened,second,AURA_CONTROL_MAX_BYTES);
    assert(aura_control_store(&opened,input,1)==0&&opened.generation==3&&opened.current==0);
    assert(aura_control_store(&opened,NULL,0)==0&&opened.generation==4);
    size_t bytes=1;assert(aura_control_load(&opened,NULL,0,&bytes)==0&&!bytes);
    preserve_audio();group("explicit provision, max/empty snapshots, alternating generations, bounded mount");
}
static void argument_guards(void)
{
    fresh();struct aura_control_config cfg=config;struct aura_control_io x=io();
    uint64_t erases=media.erases,programs=media.programs;
    cfg.blocks[1]=cfg.blocks[0];assert(aura_control_open(&opened,x,&cfg)==AURA_CONTROL_BAD_ARGUMENT);
    cfg=config;cfg.blocks[1]=8;assert(aura_control_open(&opened,x,&cfg)==AURA_CONTROL_BAD_ARGUMENT);
    cfg=config;memset(cfg.domain,0,16);assert(aura_control_open(&opened,x,&cfg)==AURA_CONTROL_BAD_ARGUMENT);
    cfg=config;x.nand.blocks=1025;assert(aura_control_open(&opened,x,&cfg)==AURA_CONTROL_BAD_ARGUMENT);
    x.nand.blocks=0;assert(aura_control_open(&opened,x,&cfg)==AURA_CONTROL_BAD_ARGUMENT);
    assert(media.erases==erases&&media.programs==programs);
    x=io();x.erase_control=NULL;
    assert(aura_control_provision(&control,x,&config,input,4)==AURA_CONTROL_READ_ONLY);
    assert(media.erases==erases&&media.programs==programs);
    provision(4);x.erase_control=NULL;
    assert(aura_control_open(&opened,x,&config)==0);load_equal(&opened,input,4);
    assert(aura_control_store(&opened,input,4)==AURA_CONTROL_READ_ONLY);
    uint8_t saved[sizeof(control)];memcpy(saved,&control,sizeof(control));
    assert(aura_control_load(&control,output,sizeof(output),(size_t *)&control.generation)==AURA_CONTROL_BAD_ARGUMENT);
    assert(!memcmp(saved,&control,sizeof(control)));
    union {size_t aligned;uint8_t bytes[64];} overlapping;
    memset(&overlapping,0xA5,sizeof(overlapping));
    assert(aura_control_load(&control,overlapping.bytes,sizeof(overlapping.bytes),
                            (size_t *)overlapping.bytes)==AURA_CONTROL_BAD_ARGUMENT);
    assert(aura_control_load(&control,overlapping.bytes,sizeof(overlapping.bytes),
                            (size_t *)(overlapping.bytes+sizeof(size_t)))==AURA_CONTROL_BAD_ARGUMENT);
    for(unsigned i=0;i<sizeof(overlapping.bytes);++i)assert(overlapping.bytes[i]==0xA5);
    size_t n=77;assert(aura_control_load(&control,control.page,2048,&n)==AURA_CONTROL_BAD_ARGUMENT&&n==0);
    assert(aura_control_store(&control,control.page,1)==AURA_CONTROL_BAD_ARGUMENT);
    assert(aura_control_store(&control,input,AURA_CONTROL_MAX_BYTES+1)==AURA_CONTROL_BAD_ARGUMENT);
    assert(aura_control_store(&control,NULL,1)==AURA_CONTROL_BAD_ARGUMENT);
    n=77;assert(aura_control_load(&control,output,3,&n)==AURA_CONTROL_CAPACITY&&n==0);
    control.config.blocks[1]=1024;erases=media.erases;
    assert(aura_control_store(&control,input,4)==AURA_CONTROL_BAD_ARGUMENT&&media.erases==erases);
    assert(erase_control(&media,3)==AURA_CONTROL_BAD_ARGUMENT&&media.erases==erases);
    preserve_audio();group("bounds, alias/capacity guards, read-only backend, no non-control erase");
}
static void blank_guards(void)
{
    for(unsigned page=0;page<64;++page){
        fresh();cell(&media,6*64+page)[2047]=0;
        uint64_t erases=media.erases,programs=media.programs;
        assert(aura_control_provision(&control,io(),&config,input,4)==AURA_NAND_NOT_ERASED);
        assert(media.erases==erases&&media.programs==programs);preserve_audio();++cases;
    }
    fresh();media.ecc[6*64+40]=1;
    assert(aura_control_provision(&control,io(),&config,input,4)==AURA_CONTROL_CORRUPT);
    assert(!media.erases);media.ecc[6*64+40]=2;
    assert(aura_control_provision(&control,io(),&config,input,4)==AURA_NAND_UNCORRECTABLE);
    fresh();provision(4);uint64_t erases=media.erases;
    assert(aura_control_provision(&opened,io(),&config,input,4)==AURA_NAND_NOT_ERASED&&media.erases==erases);
    group("all main pages checked before explicit provision; populated/dirty/ECC media never formatted");
}
static void program_cuts(bool initial)
{
    const size_t boundaries[]={1,4,63,123,124,127,1024,2043,2044,2047};
    for(unsigned at=1;at<=5;++at)for(unsigned phase=0;phase<12;++phase){
        fresh();uint8_t old_hash[32];
        if(!initial){provision(4000);snapshot_hash(1,old_hash);}
        media.cut_program=media.programs+at;
        media.cut=phase==0?MODEL_CUT_BEFORE:phase==11?MODEL_CUT_AFTER:MODEL_CUT_PARTIAL;
        media.cut_bytes=phase>0&&phase<11?boundaries[phase-1]:0;
        int r=initial?aura_control_provision(&control,io(),&config,input,4000):aura_control_store(&control,second,4000);
        assert(r<0&&!control.ready);model_power_on(&media);
        r=aura_control_open(&opened,io(),&config);
        if(at==5&&phase==11){assert(r==0);load_equal(&opened,initial?input:second,4000);}
        else if(at==1&&phase==0){
            assert(r==(initial?AURA_CONTROL_UNPROVISIONED:0));
            if(!initial)load_equal(&opened,input,4000);
        }else{
            assert(r==AURA_CONTROL_INCOMPLETE);size_t bytes=99;
            assert(aura_control_load(&opened,output,sizeof(output),&bytes)<0&&bytes==0);
            uint64_t erases=media.erases;assert(aura_control_store(&opened,input,4)<0&&media.erases==erases);
        }
        if(!initial){uint8_t now[32];snapshot_hash(1,now);assert(!memcmp(old_hash,now,32));}
        preserve_audio();++cases;
    }
    group(initial?"provision header/body/commit power cuts preserve blank-or-incomplete state":
                  "replacement header/body/commit power cuts preserve sole prior snapshot and fail closed");
}
static void erase_cuts(void)
{
    for(unsigned baseline=0;baseline<3;++baseline)for(unsigned phase=0;phase<66;++phase){
        fresh();uint8_t current_hash[32];uint16_t current=1;
        if(baseline){provision(4000);if(baseline==2){assert(aura_control_store(&control,second,4000)==0);current=6;}
            snapshot_hash(current,current_hash);}
        media.cut_erase=media.erases+1;
        media.cut=phase==0?MODEL_CUT_BEFORE:phase==65?MODEL_CUT_AFTER:MODEL_CUT_PARTIAL;
        media.cut_bytes=phase?phase-1:0;
        uint64_t programs=media.programs;
        int r=baseline?aura_control_store(&control,input,4000):
            aura_control_provision(&control,io(),&config,input,4000);
        assert(r==AURA_NAND_UNCERTAIN&&media.programs==programs&&!control.ready);
        model_power_on(&media);r=aura_control_open(&opened,io(),&config);
        if(!baseline)assert(r==AURA_CONTROL_UNPROVISIONED);
        else{
            /* Complete old commit remains through page-prefix partial erase;
             * it is linked by the current snapshot, so no old floor is used. */
            assert(r==0&&opened.generation==baseline);
            load_equal(&opened,baseline==1?input:second,4000);
            uint8_t now[32];snapshot_hash(current,now);assert(!memcmp(current_hash,now,32));
            uint64_t erases=media.erases;assert(aura_control_store(&opened,input,4000)==0);
            assert(media.erases==erases+1); /* Fresh erase after every cold cut. */
        }
        preserve_audio();++cases;
    }
    group("before/every partial-page boundary/after control erases preserve current; fresh erase required");
}
static void lost_and_failures(void)
{
    for(unsigned at=1;at<=5;++at){
        fresh();provision(4000);media.cut_program=media.programs+at;
        media.cut=MODEL_CUT_AFTER;media.lose_completion_only=true;
        uint64_t programs=media.programs;assert(aura_control_store(&control,second,4000)==0);
        assert(media.programs==programs+5);load_equal(&control,second,4000);preserve_audio();++cases;
    }
    fresh();provision(4000);media.cut_erase=media.erases+1;media.cut=MODEL_CUT_AFTER;media.lose_completion_only=true;
    uint64_t programs=media.programs;
    assert(aura_control_store(&control,second,4000)==AURA_NAND_UNCERTAIN&&media.programs==programs);
    model_power_on(&media);assert(aura_control_open(&opened,io(),&config)==0);load_equal(&opened,input,4000);
    fresh();provision(4000);exact_program_fail=true;
    assert(aura_control_store(&control,second,4000)==AURA_NAND_PROGRAM_FAILED&&!control.ready);
    exact_program_fail=false;assert(aura_control_open(&opened,io(),&config)==AURA_CONTROL_INCOMPLETE);
    fresh();provision(4000);media.program_failure[6]=1;
    assert(aura_control_store(&control,second,4000)==AURA_NAND_PROGRAM_FAILED);
    fresh();provision(4000);media.erase_failure[6]=1;
    assert(aura_control_store(&control,second,4000)==AURA_NAND_ERASE_FAILED);
    fresh();provision(4000);dirty_erase=true;
    assert(aura_control_store(&control,second,4000)==AURA_NAND_NOT_ERASED);
    preserve_audio();group("lost program completion resolved once; PFAIL and lost/EFAIL/dirty erase never promoted");
}
static void bad_ecc_and_hidden(void)
{
    for(unsigned slot=0;slot<2;++slot)for(unsigned page=0;page<2;++page)for(unsigned marker=0;marker<3;++marker){
        fresh();media.marker[config.blocks[slot]][page][marker]=0;
        assert(aura_control_provision(&control,io(),&config,input,4)==AURA_NAND_BAD_BLOCK);
        assert(!media.erases);++cases;
    }
    fresh();media.remapped[6]=true;
    assert(aura_control_provision(&control,io(),&config,input,4)==AURA_NAND_BAD_BLOCK);
    fresh();provision(4000);media.ecc[1*64+3]=1;
    assert(aura_control_open(&opened,io(),&config)==0&&opened.corrected_reads==1);load_equal(&opened,input,4000);
    media.ecc[1*64+3]=2;assert(aura_control_open(&opened,io(),&config)==AURA_CONTROL_INCOMPLETE);
    fresh();provision(4000);assert(aura_control_store(&control,second,4000)==0);
    media.ecc[6*64+3]=3;assert(aura_control_open(&opened,io(),&config)==AURA_CONTROL_INCOMPLETE);
    fresh();provision(4000);cell(&media,1*64+62)[100]=0;
    assert(aura_control_open(&opened,io(),&config)==AURA_CONTROL_INCOMPLETE);
    fresh();provision(4000);cell(&media,6*64+51)[100]=0;
    assert(aura_control_open(&opened,io(),&config)==AURA_CONTROL_INCOMPLETE);
    group("six marker bytes/LUT reservations, corrected/uncorrectable ECC, hidden later material");
}
static void rechain(struct nand_model *m,unsigned slot)
{
    uint32_t first=config.blocks[slot]*64;uint8_t h[32],chain[32];
    page_crc(cell(m,first+2));aura_archive_sha256(cell(m,first+2),2048,h);memcpy(chain,h,32);
    unsigned bodies=(unsigned)cell(m,first+2)[80]+256u*cell(m,first+2)[81];
    for(unsigned n=0;n<bodies;++n){
        uint8_t *p=cell(m,first+3+n);memcpy(p+48,chain,32);page_crc(p);aura_archive_sha256(p,2048,chain);
    }
    uint8_t *commit=cell(m,first+63);memcpy(commit+88,h,32);memcpy(commit+120,chain,32);page_crc(commit);
}
static void generations_and_mutations(void)
{
    const unsigned offsets[]={4,5,6,8,10,11,12,14,16,24,28,32,48,80,123,2043};
    for(unsigned which=0;which<3;++which)for(unsigned mutation=0;mutation<sizeof(offsets)/sizeof(offsets[0]);++mutation){
        fresh();provision(4000);unsigned page=which==0?2:which==1?3:63;
        uint8_t *p=cell(&media,1*64+page);p[offsets[mutation]]^=1;page_crc(p);
        assert(aura_control_open(&opened,io(),&config)==AURA_CONTROL_INCOMPLETE);++cases;
    }
    fresh();provision(4000);assert(aura_control_store(&control,second,4000)==0);
    /* Two internally valid, but unlinked snapshots cannot elect authority. */
    cell(&media,6*64+2)[48]^=1;cell(&media,6*64+63)[48]^=1;rechain(&media,1);
    assert(aura_control_open(&opened,io(),&config)==AURA_CONTROL_CONFLICT);
    fresh();provision(4000);struct aura_control_config wrong=config;wrong.domain[0]^=1;
    assert(aura_control_open(&opened,io(),&wrong)==AURA_CONTROL_INCOMPLETE);
    /* Public CRC/SHA are deliberately not anti-forgery. Construct an internally
     * valid extreme generation; API refuses rollover without an erase. */
    fresh();provision(0);
    for(unsigned p=2;p<=63;p+=61){uint8_t *v=cell(&media,1*64+p);put(v+16,UINT64_MAX,8);put(v+24,UINT64_MAX-1,8);memset(v+48,7,32);}
    rechain(&media,0);assert(aura_control_open(&opened,io(),&config)==0);
    uint64_t erases=media.erases;assert(aura_control_store(&opened,input,4)==AURA_CONTROL_EXHAUSTED&&media.erases==erases);
    group("canonical page fields, body header124, generation/domain/parent conflicts and rollover bound");
}
static void stale_and_substitution(void)
{
    fresh();provision(16);stale=control;
    assert(aura_control_store(&control,second,4)==0);
    assert(aura_control_store(&control,second,4000)==0); /* Same physical slot as stale. */
    uint8_t guarded[48];memset(guarded,0xA5,sizeof(guarded));size_t bytes=88;
    assert(aura_control_load(&stale,guarded+16,16,&bytes)==AURA_CONTROL_CONFLICT&&bytes==0);
    for(unsigned n=0;n<sizeof(guarded);++n)assert(guarded[n]==0xA5);
    fresh();provision(16);stale=control;assert(aura_control_store(&control,second,4000)==0);
    memset(output,0xA5,sizeof(output));bytes=99;
    assert(aura_control_load(&stale,output,sizeof(output),&bytes)==AURA_CONTROL_CONFLICT&&bytes==0);
    for(unsigned n=0;n<sizeof(output);++n)assert(output[n]==0xA5);
    assert(aura_control_open(&stale,io(),&config)==0);
    media.cut_program=media.programs+2;media.cut=MODEL_CUT_PARTIAL;media.cut_bytes=124;
    assert(aura_control_store(&control,input,4000)<0);model_power_on(&media);bytes=99;
    assert(aura_control_load(&stale,output,sizeof(output),&bytes)==AURA_CONTROL_INCOMPLETE&&bytes==0);
    fresh();provision(16);stale=control;assert(aura_control_store(&control,second,4000)==0);
    uint64_t erases=media.erases;assert(aura_control_store(&stale,input,16)==AURA_CONTROL_CONFLICT&&media.erases==erases);

    /* Prepare a different but valid generation2 sharing the same parent. */
    fresh();provision(4000);model_destroy(&alternate);model_init(&alternate,8);
    assert(aura_control_provision(&opened,io_for(&alternate),&config,input,4000)==0);
    uint8_t changed[4000];pattern(changed,sizeof(changed),97);
    assert(aura_control_store(&opened,changed,sizeof(changed))==0);
    for(unsigned n=0;n<64;++n)if(alternate.pages[6*64+n]){
        substitute_pages[n]=malloc(2048);assert(substitute_pages[n]);memcpy(substitute_pages[n],alternate.pages[6*64+n],2048);
    }
    /* Trigger only on the post-commit complete scan, after erase readback and
     * all exact per-page readbacks. A wrapper arms it at commit readback below. */
    substitute_page=6*64;substitute=false;
    arm_substitute=true;arm_after_programs=media.programs+5;
    assert(aura_control_store(&control,second,4000)==AURA_CONTROL_CORRUPT&&!control.ready);
    assert(!substitute);preserve_audio();
    group("stale-small load canaries, stale store, exact expected digest at final snapshot verification");
}
static void older_exception(void)
{
    for(unsigned mode=0;mode<5;++mode){
        fresh();provision(4000);assert(aura_control_store(&control,second,4000)==0);
        uint8_t before[32];snapshot_hash(6,before);
        if(mode==0){free(media.pages[1*64+2]);media.pages[1*64+2]=NULL;}
        if(mode==1){cell(&media,1*64+63)[2044]^=1;}
        if(mode==2){
            uint8_t *p=cell(&media,1*64+2);put(p+16,3,8);put(p+24,2,8);
            memcpy(p+48,control.digest,32);page_crc(p);
        }
        if(mode==3){uint8_t *p=cell(&media,1*64+3);put(p+16,3,8);page_crc(p);}
        if(mode==4){cell(&media,1*64+2)[1]^=1;}
        int r=aura_control_open(&opened,io(),&config);
        if(!mode){assert(r==0&&opened.generation==2);load_equal(&opened,second,4000);}
        else{
            assert(r==AURA_CONTROL_INCOMPLETE);uint64_t erases=media.erases;
            assert(aura_control_store(&opened,input,4)<0&&media.erases==erases);
        }
        uint8_t after[32];snapshot_hash(6,after);assert(!memcmp(before,after,32));preserve_audio();++cases;
    }
    group("older-erasure exception requires intact bound commit and no contradictory newer candidate");
}
static void cycles_and_rollback(void)
{
    fresh();provision(4000);uint8_t *old_pages[128]={0};
    for(unsigned slot=0;slot<2;++slot)for(unsigned n=0;n<64;++n)if(media.pages[config.blocks[slot]*64+n]){
        old_pages[slot*64+n]=malloc(2048);assert(old_pages[slot*64+n]);
        memcpy(old_pages[slot*64+n],media.pages[config.blocks[slot]*64+n],2048);
    }
    for(unsigned n=0;n<260;++n){
        pattern(second,4000,n);assert(aura_control_store(&control,second,4000)==0);
        model_power_on(&media);assert(aura_control_open(&control,io(),&config)==0);
        assert(control.generation==n+2);load_equal(&control,second,4000);preserve_audio();++cases;
    }
    /* Exact old raw-media backup is indistinguishable without an external
     * trusted anchor. Test the limitation instead of claiming anti-rollback. */
    for(unsigned slot=0;slot<2;++slot)for(unsigned n=0;n<64;++n){
        uint32_t page=config.blocks[slot]*64+n;free(media.pages[page]);media.pages[page]=old_pages[slot*64+n];
    }
    assert(aura_control_open(&opened,io(),&config)==0&&opened.generation==1);load_equal(&opened,input,4000);
    preserve_audio();group("260 replacements/reopens preserve unrelated source; raw-pair rollback limitation explicit");
}

static int fixture(const char *path)
{
    fresh();pattern(input,4000,11);provision(4000);
    pattern(second,AURA_CONTROL_MAX_BYTES,23);assert(aura_control_store(&control,second,AURA_CONTROL_MAX_BYTES)==0);
    pattern(input,1921,53);assert(aura_control_store(&control,input,1921)==0);
    FILE *f=fopen(path,"wb");if(!f)return 1;
    for(unsigned slot=0;slot<2;++slot)for(unsigned n=0;n<64;++n){
        assert(model_io(&media).read(&media,config.blocks[slot]*64+n,0,output,2048)==0);
        assert(fwrite(output,1,2048,f)==2048);
    }
    assert(!fclose(f));return 0;
}
int main(int argc,char **argv)
{
    ordinary();argument_guards();blank_guards();program_cuts(true);program_cuts(false);
    erase_cuts();lost_and_failures();bad_ecc_and_hidden();generations_and_mutations();
    stale_and_substitution();older_exception();cycles_and_rollback();
    if(argc>1&&fixture(argv[1]))return 1;
    printf("RESULT {\"groups\":%u,\"fault_and_rotation_cases\":%u,\"context_bytes\":%zu,\"guarded_erases\":%u}\n",
           groups,cases,sizeof(struct aura_control),guarded_erases);
    fresh();model_destroy(&media);model_destroy(&alternate);return 0;
}
