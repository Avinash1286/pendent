/* SPDX-License-Identifier: MIT */
/* Cursor scheduling/integrity tests use the real journal/archive parser and
 * host NAND fault model. Synthetic packet bytes are not an audio quality test. */
#include "aura_journal_cursor.h"
#include "nand_model.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static struct nand_model medium;
static struct aura_journal journal;
static struct aura_archive_writer writer;
static struct aura_journal_cursor cursor;
static const char *case_name;
static unsigned checks, cases, maximum_reads;
static uint64_t verify_calls, read_calls;
static const uint8_t incarnation[16]={0xA4,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16};
#define CHECK(x) do { ++checks; if(!(x)) { fprintf(stderr,"FAIL cursor %s line=%d: %s\n",case_name,__LINE__,#x); exit(1); } } while(0)
#define START(name) do { case_name=(name); } while(0)
#define PASS() do { ++cases; printf("CASE %s PASS\n",case_name); } while(0)
#define SINK_LIMIT 200000u
struct sink { uint8_t data[SINK_LIMIT]; uint64_t bytes, boundary[1024]; size_t boundaries; };
static struct sink expected, actual;
static uint8_t fixture_data[SINK_LIMIT];

static void put(uint8_t *p,uint64_t value,unsigned bytes)
{for(unsigned i=0;i<bytes;++i)p[i]=(uint8_t)(value>>(8*i));}
static void fix_crc(uint8_t *p,size_t bytes)
{put(p+bytes-4,aura_archive_crc32(p,bytes-4),4);}
static void reset(unsigned blocks)
{model_destroy(&medium);model_init(&medium,blocks);CHECK(!aura_journal_mount(&journal,model_io(&medium)));}
static void remount(void)
{model_power_on(&medium);CHECK(!aura_journal_mount(&journal,model_io(&medium)));}
static struct aura_archive_manifest manifest(unsigned device,unsigned capture)
{
    struct aura_archive_manifest m={.frame_samples=320,.pre_skip=40};
    memset(m.device_id,(int)device,16);memset(m.capture_id,(int)capture,16);return m;
}
static int copy_manifest(void *user,uint64_t offset,const uint8_t *wire,size_t bytes)
{if(offset||bytes!=68)return -901;memcpy(user,wire,bytes);return 0;}
static void bind(unsigned device,unsigned capture,uint64_t generation)
{
    uint8_t wire[68];struct aura_archive_writer draft;struct aura_archive_manifest m=manifest(device,capture);
    CHECK(!aura_archive_begin_staged(&draft,&m,copy_manifest,wire));
    CHECK(!aura_journal_bind_capture(&journal,wire,generation));
}
static void begin(unsigned device,unsigned capture)
{
    if(!journal.service_clock_started)CHECK(!aura_journal_service(&journal,0));
    struct aura_archive_manifest m=manifest(device,capture);
    CHECK(!aura_archive_begin_staged(&writer,&m,aura_journal_stage,&journal));
}
static void packet(unsigned bytes)
{
    struct aura_opus_packet p={.sequence=writer.audio_packets,.sample_offset=writer.encoded_samples,
        .sample_count=320,.bytes=(uint16_t)bytes};
    memset(p.data,0x33,bytes);p.data[0]=0x98;CHECK(!aura_archive_opus_commit(&writer,&p));
}
static void close_capture(unsigned mode)
{
    if(mode==0){
        struct aura_opus_seal seal={.source_samples=writer.encoded_samples-40-17,
            .encoded_samples=writer.encoded_samples,.packets=writer.audio_packets,.pre_skip=40,.end_trim=17};
        CHECK(!aura_archive_finalize(&writer,&seal));
    }else if(mode==1)CHECK(!aura_archive_interrupt(&writer));
    else CHECK(!aura_journal_flush(&journal));
}
static void fixture(unsigned mode,bool owned)
{
    reset(6);
    if(owned){CHECK(!aura_journal_set_owned_profile(&journal,incarnation));bind(17,1,42);}
    begin(17,1);packet(80);packet(80);CHECK(!aura_archive_bookmark(&writer,160));
    packet(80);close_capture(mode);remount();CHECK(journal.count==1&&journal.active==-1);
}
static int collect(void *user,uint64_t offset,const uint8_t *wire,size_t bytes)
{
    struct sink *s=user;
    if(offset!=s->bytes||bytes>SINK_LIMIT-s->bytes||s->boundaries>=1024)return -902;
    memcpy(s->data+s->bytes,wire,bytes);s->bytes+=bytes;s->boundary[s->boundaries++]=s->bytes;return 0;
}
static void reference(unsigned index)
{
    memset(&expected,0,sizeof(expected));expected.boundary[expected.boundaries++]=0;
    uint64_t programs=medium.programs,erases=medium.erases;
    CHECK(!aura_journal_export(&journal,(uint16_t)index,collect,&expected));
    CHECK(medium.programs==programs&&medium.erases==erases);
}
static void unchanged_writes(uint64_t programs,uint64_t erases)
{CHECK(medium.programs==programs&&medium.erases==erases);}
static void bounded_reads(uint64_t before)
{
    uint64_t used=medium.reads-before;CHECK(used<=1);
    if(used>maximum_reads)maximum_reads=(unsigned)used;
}
static int open_identity(const uint8_t identity[32])
{
    uint64_t reads=medium.reads,programs=medium.programs,erases=medium.erases;
    int result=aura_journal_cursor_open(&cursor,&journal,identity);
    CHECK(medium.reads==reads);unchanged_writes(programs,erases);return result;
}
static int step(void)
{
    uint64_t reads=medium.reads,programs=medium.programs,erases=medium.erases;
    int result=aura_journal_cursor_verify_step(&cursor);++verify_calls;
    bounded_reads(reads);unchanged_writes(programs,erases);return result;
}
static int read_chunk(uint8_t *out,size_t capacity,uint64_t *offset,size_t *bytes)
{
    uint64_t reads=medium.reads,programs=medium.programs,erases=medium.erases;
    int result=aura_journal_cursor_read(&cursor,out,capacity,offset,bytes);++read_calls;
    bounded_reads(reads);unchanged_writes(programs,erases);return result;
}
static struct aura_journal_cursor_info ready(unsigned index)
{
    uint8_t identity[32];memcpy(identity,journal.captures[index].manifest+8,32);
    CHECK(!open_identity(identity));memset(identity,0x91,sizeof(identity));
    struct aura_journal_cursor_info info;CHECK(aura_journal_cursor_get_info(&cursor,&info)<0);
    int result=AURA_CURSOR_PENDING;unsigned iterations=0;
    while(result==AURA_CURSOR_PENDING){CHECK(++iterations<10000);result=step();}
    CHECK(result==AURA_CURSOR_READY);
    uint64_t reads=medium.reads;CHECK(!aura_journal_cursor_get_info(&cursor,&info));CHECK(medium.reads==reads);
    CHECK(!memcmp(info.manifest,journal.captures[index].manifest,68));
    CHECK(!memcmp(info.physical_receipt,journal.captures[index].committed_receipt,94));
    CHECK(info.physical_bytes==journal.captures[index].committed_wire_bytes);
    CHECK(info.export_bytes==expected.bytes);
    struct aura_journal_cursor_info again;memset(journal.scratch,0xE3,sizeof(journal.scratch));
    CHECK(!aura_journal_cursor_get_info(&cursor,&again));CHECK(!memcmp(&info,&again,sizeof(info)));
    return info;
}
static int drain(uint64_t resume,size_t capacity,bool compare)
{
    uint8_t buffers[2][AURA_CURSOR_CHUNK_MAX],saved[AURA_CURSOR_CHUNK_MAX];
    size_t previous_size=0;unsigned previous=0,turn=0,iterations=0;
    memset(&actual,0,sizeof(actual));uint64_t reads=medium.reads;
    for(;;){
        CHECK(++iterations<250000);unsigned slot=turn++%2;CHECK(slot!=previous||!previous_size);
        memset(buffers[slot],0xA5,sizeof(buffers[slot]));
        memset(journal.scratch,0x7D,sizeof(journal.scratch));
        uint64_t offset=UINT64_MAX;size_t bytes=999;
        int result=read_chunk(buffers[slot],capacity,&offset,&bytes);
        if(previous_size)CHECK(!memcmp(buffers[previous],saved,previous_size));
        previous_size=0;
        if(result==AURA_CURSOR_DATA){
            CHECK(bytes>0&&bytes<=capacity&&offset==resume+actual.bytes);
            CHECK(bytes<=SINK_LIMIT-actual.bytes);
            if(compare){CHECK(offset+bytes<=expected.bytes);CHECK(!memcmp(buffers[slot],expected.data+offset,bytes));}
            memcpy(actual.data+actual.bytes,buffers[slot],bytes);actual.bytes+=bytes;
            memcpy(saved,buffers[slot],bytes);previous=slot;previous_size=bytes;
        }else{
            CHECK(bytes==0);
            for(size_t n=0;n<sizeof(buffers[slot]);++n)CHECK(buffers[slot][n]==0xA5);
            if(result==AURA_CURSOR_PENDING)continue;
            CHECK(medium.reads-reads<=2u*62u*journal.captures[0].blocks+8u);
            if(result==0&&compare)CHECK(actual.bytes==expected.bytes-resume);
            return result;
        }
    }
}
static void seek_to(uint64_t offset)
{
    uint64_t reads=medium.reads,programs=medium.programs,erases=medium.erases;
    CHECK(!aura_journal_cursor_seek(&cursor,offset));CHECK(medium.reads==reads);unchanged_writes(programs,erases);
}
static void cancel(void)
{
    uint64_t reads=medium.reads,programs=medium.programs,erases=medium.erases;
    aura_journal_cursor_cancel(&cursor);CHECK(medium.reads==reads);unchanged_writes(programs,erases);
}
static void receipt_cached(bool valid)
{
    uint8_t receipt[94];uint64_t reads=medium.reads;
    int result=aura_journal_receipt(&journal,0,receipt);
    CHECK(result==(valid?0:AURA_JOURNAL_NOT_COMMITTED));CHECK(medium.reads==reads);
    if(valid)CHECK(!memcmp(receipt,journal.captures[0].committed_receipt,94));
}

static void exports_and_capacities(void)
{
    START("all_chunk_capacities_final_interrupted_open");
    for(unsigned mode=0;mode<3;++mode){
        fixture(mode,mode==0);reference(0);
        for(size_t capacity=1;capacity<=AURA_CURSOR_CHUNK_MAX;++capacity){
            struct aura_journal_cursor_info info=ready(0);
            CHECK(info.derived_seal==(mode==2));CHECK(info.allocation.owned==(mode==0));
            CHECK(info.allocation.version==(mode==0?2:1));
            if(mode==0){CHECK(info.allocation.allocation_generation==42);CHECK(!memcmp(info.allocation.incarnation,incarnation,16));}
            CHECK(info.export_bytes==info.physical_bytes+(mode==2?120u:0u));
            seek_to(0);CHECK(drain(0,capacity,true)==0);cancel();
        }
    }
    PASS();
}
static void resume_boundaries(void)
{
    START("record_boundary_resume_and_single_linear_replay");
    for(unsigned mode=0;mode<3;++mode){
        fixture(mode,false);reference(0);
        bool saw_manifest=false,saw_physical=false,saw_export=false;
        for(size_t n=0;n<expected.boundaries;++n){
            struct aura_journal_cursor_info info=ready(0);uint64_t offset=expected.boundary[n];
            saw_manifest|=offset==68;saw_physical|=offset==info.physical_bytes;saw_export|=offset==info.export_bytes;
            seek_to(offset);uint64_t reads=medium.reads;
            CHECK(drain(offset,7,true)==0);CHECK(medium.reads-reads>=120u*journal.captures[0].blocks);
            if(offset==info.export_bytes)CHECK(actual.bytes==0);
        }
        CHECK(saw_manifest&&saw_physical&&saw_export);
        const uint64_t invalid[]={1,67,69,173,expected.bytes-119,expected.bytes-1};
        for(size_t n=0;n<sizeof(invalid)/sizeof(invalid[0]);++n){
            (void)ready(0);seek_to(invalid[n]);CHECK(drain(invalid[n],13,false)==AURA_CURSOR_BOUNDARY);CHECK(!actual.bytes);
            receipt_cached(true);
        }
        (void)ready(0);int result=aura_journal_cursor_seek(&cursor,expected.bytes+1);
        if(!result)result=drain(expected.bytes+1,13,false);CHECK(result<0);
        (void)ready(0);CHECK(aura_journal_cursor_seek(&cursor,UINT64_MAX)<0);receipt_cached(true);
        (void)ready(0);seek_to(0);CHECK(aura_journal_cursor_seek(&cursor,68)<0);
    }
    PASS();
}
static void wrapped_maximum_records(void)
{
    START("wrapped_three_block_chain_maximum_AFR_and_bookmark");reset(4);journal.allocation_cursor=2;
    begin(17,9);packet(80);close_capture(1);
    begin(17,1);for(unsigned n=0;n<125;++n)packet(1275);
    CHECK(!aura_archive_bookmark(&writer,160));close_capture(0);remount();
    unsigned index=0;while(index<journal.count&&journal.captures[index].manifest[24]!=1)++index;
    CHECK(index<journal.count);CHECK(journal.captures[index].first_block==3&&journal.captures[index].last_block==1);
    CHECK(journal.captures[index].blocks==3);reference(index);
    /* Keep catalog indices intact. This loop checks the selected three-block
     * chain's bound instead of drain's single-capture fixture bound. */
    struct aura_journal_cursor_info info=ready(index);seek_to(68);
    uint64_t reads=medium.reads;uint8_t out[256];uint64_t offset;size_t bytes,total=0;int result;
    do{memset(journal.scratch,0xAD,sizeof(journal.scratch));bytes=0;result=read_chunk(out,sizeof(out),&offset,&bytes);
        if(result==AURA_CURSOR_DATA){CHECK(offset==68+total&&bytes>0&&bytes<=256);CHECK(!memcmp(out,expected.data+offset,bytes));total+=bytes;}
        else CHECK(!bytes);
    }while(result==AURA_CURSOR_PENDING||result==AURA_CURSOR_DATA);
    CHECK(result==0&&total==info.export_bytes-68);CHECK(medium.reads-reads<=2u*62u*3u+8u);PASS();
}
static void exact_identity(void)
{
    START("exact_device_and_capture_identity_copied_at_open");reset(4);
    begin(17,1);packet(80);close_capture(1);begin(18,1);packet(80);close_capture(1);remount();
    CHECK(journal.count==2);
    for(unsigned index=0;index<2;++index){reference(index);(void)ready(index);seek_to(0);CHECK(drain(0,31,true)==0);}
    /* Reopen may use the cursor's own copied identity as its input. */
    CHECK(!open_identity(cursor.selected.manifest+8));
    int result;do{result=step();}while(result==AURA_CURSOR_PENDING);CHECK(result==AURA_CURSOR_READY);
    uint8_t id[32];memcpy(id,journal.captures[0].manifest+8,32);id[0]^=1;CHECK(open_identity(id)<0);
    memcpy(id,journal.captures[0].manifest+8,32);id[31]^=1;CHECK(open_identity(id)<0);PASS();
}
static int verify_failure(void)
{
    CHECK(!open_identity(journal.captures[0].manifest+8));int result=AURA_CURSOR_PENDING;unsigned calls=0;
    while(result==AURA_CURSOR_PENDING){CHECK(++calls<1000);result=step();}
    CHECK(result<0);struct aura_journal_cursor_info info;CHECK(aura_journal_cursor_get_info(&cursor,&info)<0);return result;
}
static void ecc_and_torn_tail(void)
{
    START("corrected_ECC_and_every_selected_unreadable_slot");fixture(0,false);reference(0);
    medium.ecc[2]=medium.ecc[3]=medium.ecc[62]=medium.ecc[63]=1;
    uint64_t corrected=journal.corrected_reads;(void)ready(0);seek_to(0);CHECK(!drain(0,37,true));CHECK(journal.corrected_reads>corrected);
    const unsigned slots[]={2,3,4,62,63};
    for(size_t n=0;n<sizeof(slots)/sizeof(slots[0]);++n){fixture(0,false);medium.ecc[slots[n]]=2;CHECK(verify_failure()<0);}
    PASS();
    START("torn_tail_prefix_and_torn_checkpoint_policy");
    reset(3);begin(17,1);packet(80);packet(80);CHECK(!aura_journal_flush(&journal));
    CHECK(medium.pages[4]);medium.pages[4][90]^=1;remount();reference(0);
    struct aura_journal_cursor_info info=ready(0);CHECK(info.derived_seal&&info.physical_bytes==174);
    seek_to(0);CHECK(!drain(0,19,true));
    fixture(1,false);CHECK(medium.pages[63]);medium.pages[63][20]^=1;remount();reference(0);
    info=ready(0);CHECK(!info.derived_seal);seek_to(0);CHECK(!drain(0,19,true));PASS();
}
static void framing_holes_and_unassociated(void)
{
    START("valid_CRC_bad_framing_padding_and_holes");
    for(unsigned kind=0;kind<3;++kind){
        fixture(1,false);uint8_t *page=medium.pages[3];CHECK(page);
        if(kind==0){page[132]='X';fix_crc(page+132,106);}
        if(kind==1)page[2000]=0;
        if(kind==2)put(page+58,0,2);
        fix_crc(page,2048);CHECK(verify_failure()<0);
    }
    for(unsigned kind=0;kind<3;++kind){
        reset(3);begin(17,1);packet(80);packet(80);CHECK(!aura_journal_flush(&journal));
        packet(80);CHECK(!aura_journal_flush(&journal));CHECK(medium.pages[4]&&medium.pages[5]);
        if(kind==0){free(medium.pages[4]);medium.pages[4]=NULL;}
        if(kind==1)medium.pages[4][100]^=1;
        if(kind==2)medium.ecc[4]=2;
        remount();CHECK(verify_failure()<0);
    }
    PASS();
    START("global_unassociated_source_denies_selection_without_read");fixture(1,false);
    uint8_t junk[2048];memset(junk,0,sizeof(junk));struct aura_nand_io io=model_io(&medium);
    CHECK(!io.program(io.user,2*64+2,junk));remount();CHECK(journal.unassociated_blocks>0);
    CHECK(open_identity(journal.captures[0].manifest+8)<0);PASS();
}
static void mutate_first_packet(void)
{
    uint8_t *page=medium.pages[3];CHECK(page);page[155]^=1;
    fix_crc(page+132,106);fix_crc(page,2048);
}
static void changed_source(void)
{
    START("source_mutation_between_verify_and_export_rejected");fixture(0,false);reference(0);(void)ready(0);
    receipt_cached(true);mutate_first_packet();seek_to(0);CHECK(drain(0,31,false)<0);receipt_cached(false);PASS();
    START("third_verify_detects_mutation_of_already_emitted_source");
    for(unsigned when=0;when<2;++when){
        fixture(0,false);reference(0);(void)ready(0);seek_to(0);
        uint8_t out[31];uint64_t offset;size_t bytes;uint64_t total=0;bool changed=false;int result;
        unsigned calls=0;
        do{
            CHECK(++calls<3000);bytes=0;result=read_chunk(out,sizeof(out),&offset,&bytes);
            if(result==AURA_CURSOR_DATA){
                CHECK(offset==total&&bytes>0&&total+bytes<=expected.bytes);
                CHECK(!memcmp(out,expected.data+offset,bytes));total+=bytes;
                if(!changed&&total>=(when?expected.bytes:174)){mutate_first_packet();changed=true;}
            }
        }while(result==AURA_CURSOR_PENDING||result==AURA_CURSOR_DATA);
        CHECK(changed&&result<0&&total==expected.bytes);
        receipt_cached(false);
    }
    PASS();
}
static void mutate_allocation(unsigned kind)
{
    uint8_t *header=medium.pages[2],*checkpoint=medium.pages[63];CHECK(header&&checkpoint);
    CHECK(header[4]==2&&checkpoint[4]==2);
    /* Coherent new identity with intact archive bytes and valid metadata CRCs. */
    if(kind==0){header[222]^=1;checkpoint[122]^=1;}
    else{header[238]^=1;checkpoint[138]^=1;}
    fix_crc(header,256);fix_crc(checkpoint,256);
}
static void changed_allocation(void)
{
    START("coherent_v2_allocation_mutation_before_replay_and_after_DATA");
    for(unsigned kind=0;kind<2;++kind)for(unsigned when=0;when<2;++when){
        fixture(0,true);reference(0);(void)ready(0);seek_to(0);receipt_cached(true);
        if(!when){mutate_allocation(kind);CHECK(drain(0,31,false)<0);}
        else{
            uint8_t out[31];uint64_t offset,total=0;size_t bytes;int result;bool changed=false;unsigned calls=0;
            do{
                CHECK(++calls<1000);result=read_chunk(out,sizeof(out),&offset,&bytes);
                if(result==AURA_CURSOR_DATA){
                    CHECK(bytes&&offset==total&&total+bytes<=expected.bytes);
                    CHECK(!memcmp(out,expected.data+offset,bytes));total+=bytes;
                    if(total==expected.bytes){CHECK(!changed);mutate_allocation(kind);changed=true;}
                }
            }while(result==AURA_CURSOR_PENDING||result==AURA_CURSOR_DATA);
            CHECK(changed&&result<0&&total==expected.bytes);
        }
        receipt_cached(false);
    }
    PASS();
}
static void stop_after_data_or_done(bool done)
{
    uint8_t out[31];uint64_t offset,total=0;size_t bytes;unsigned calls=0;int result;
    do{
        CHECK(++calls<2000);result=read_chunk(out,sizeof(out),&offset,&bytes);
        if(result==AURA_CURSOR_DATA){
            CHECK(bytes&&offset==total&&total+bytes<=expected.bytes);
            CHECK(!memcmp(out,expected.data+offset,bytes));total+=bytes;
        }else CHECK(result==AURA_CURSOR_PENDING||result==0);
    }while((done&&result!=0)||(!done&&total<expected.bytes));
    CHECK(total==expected.bytes);
    if(!done){
        /* After every DATA byte, enter the third walk and inspect its first
         * source page. Interrupt that walk before it can establish FINISHED. */
        uint64_t reads=medium.reads;
        do{CHECK(++calls<2100);result=read_chunk(out,sizeof(out),&offset,&bytes);CHECK(result==AURA_CURSOR_PENDING&&!bytes);}
        while(medium.reads==reads);
    }else CHECK(result==0);
}
static void late_lifecycle(void)
{
    START("cancel_and_epoch_preempt_during_third_verify_and_after_DONE");
    for(unsigned done=0;done<2;++done)for(unsigned preempt=0;preempt<2;++preempt){
        fixture(1,false);reference(0);(void)ready(0);seek_to(0);stop_after_data_or_done(done!=0);
        if(preempt){uint64_t reads=medium.reads,programs=medium.programs,erases=medium.erases;
            CHECK(!aura_journal_invalidate_exports(&journal));CHECK(medium.reads==reads);unchanged_writes(programs,erases);
        }else cancel();
        uint8_t out[31];uint64_t offset;size_t bytes;struct aura_journal_cursor_info info;
        CHECK(read_chunk(out,sizeof(out),&offset,&bytes)<0&&bytes==0);CHECK(step()<0);
        CHECK(aura_journal_cursor_get_info(&cursor,&info)<0);CHECK(aura_journal_cursor_seek(&cursor,0)<0);
        receipt_cached(true);
    }
    PASS();
}
static void empty_archives(void)
{
    START("empty_interrupted_and_manifest_only_derived_archives");
    for(unsigned mode=1;mode<=2;++mode){
        reset(3);begin(17,1);close_capture(mode);remount();reference(0);CHECK(expected.bytes==188);
        const uint64_t boundaries[]={0,68,188};
        for(size_t n=0;n<sizeof(boundaries)/sizeof(boundaries[0]);++n){
            struct aura_journal_cursor_info info=ready(0);
            CHECK(info.derived_seal==(mode==2)&&info.physical_bytes==(mode==2?68u:188u));
            seek_to(boundaries[n]);CHECK(!drain(boundaries[n],n==0?1:256,true));
        }
        (void)ready(0);seek_to(80);CHECK(drain(80,31,false)==AURA_CURSOR_BOUNDARY);receipt_cached(true);
        (void)ready(0);CHECK(aura_journal_cursor_seek(&cursor,UINT64_MAX)<0);receipt_cached(true);
    }
    PASS();
}
static void first_manifest_binding(void)
{
    START("OPEN_physical_manifest_bound_to_full_header_catalog_manifest");
    for(unsigned kind=0;kind<3;++kind){
        reset(3);begin(17,1);close_capture(2);remount();reference(0);
        CHECK(medium.pages[3]&&!medium.pages[63]);uint8_t changed[68];
        memcpy(changed,journal.captures[0].manifest,68);
        if(kind==1)changed[8]^=1;
        else{changed[54]=1;put(changed+56,1,8);}
        fix_crc(changed,sizeof(changed));
        struct aura_archive_writer canonical={0};CHECK(!aura_archive_replay(&canonical,changed,sizeof(changed)));
        if(kind<2){memcpy(medium.pages[3]+64,changed,68);fix_crc(medium.pages[3],2048);}
        else{memcpy(medium.pages[2]+60,changed,68);fix_crc(medium.pages[2],256);memcpy(journal.captures[0].manifest,changed,68);}
        CHECK(aura_journal_verify(&journal,0)<0);receipt_cached(false);
        CHECK(verify_failure()<0);receipt_cached(false);
    }
    PASS();
}
static void lifecycle_and_arguments(void)
{
    START("active_capture_epoch_remount_profile_and_binding_preempt");
    for(unsigned kind=0;kind<5;++kind){
        fixture(1,kind==4);
        if(kind==4)CHECK(!aura_journal_set_owned_profile(&journal,incarnation));
        reference(0);(void)ready(0);seek_to(0);uint64_t epoch=journal.export_epoch;
        if(kind==0)CHECK(!aura_journal_invalidate_exports(&journal));
        if(kind==1)remount();
        if(kind==2)begin(17,2);
        if(kind==3)CHECK(!aura_journal_set_owned_profile(&journal,incarnation));
        if(kind==4)bind(17,2,43);
        CHECK(journal.export_epoch!=epoch);
        uint8_t out[17];uint64_t offset;size_t bytes;CHECK(read_chunk(out,sizeof(out),&offset,&bytes)<0);
        CHECK(step()<0);
        if(kind==2||kind==4)CHECK(open_identity(journal.captures[0].manifest+8)<0);
    }
    PASS();
    START("cancel_all_phases_and_argument_bounds_no_NAND_writes");
    for(unsigned phase=0;phase<3;++phase){
        fixture(1,false);reference(0);
        if(phase==0)CHECK(!open_identity(journal.captures[0].manifest+8));
        else (void)ready(0);
        uint8_t out[257];uint64_t offset;size_t bytes;
        if(phase==2){seek_to(0);int result;unsigned tries=0;do{CHECK(++tries<1000);result=read_chunk(out,1,&offset,&bytes);}while(result==AURA_CURSOR_PENDING);CHECK(result==AURA_CURSOR_DATA);}
        cancel();CHECK(step()<0);CHECK(read_chunk(out,1,&offset,&bytes)<0);
        struct aura_journal_cursor_info info;CHECK(aura_journal_cursor_get_info(&cursor,&info)<0);CHECK(aura_journal_cursor_seek(&cursor,0)<0);
        receipt_cached(true);
    }
    fixture(1,false);reference(0);
    for(unsigned kind=0;kind<5;++kind){
        (void)ready(0);seek_to(0);uint8_t out[257];uint64_t offset;size_t bytes;
        int result=read_chunk(kind==2?NULL:out,kind==0?0:kind==1?257:1,kind==3?NULL:&offset,kind==4?NULL:&bytes);
        CHECK(result<0);
    }
    PASS();
}
static size_t read_file(const char *path,uint8_t *out,size_t capacity)
{
    FILE *file=fopen(path,"rb");CHECK(file);size_t bytes=fread(out,1,capacity,file);
    CHECK(!ferror(file));CHECK(fgetc(file)==EOF);CHECK(!ferror(file));CHECK(!fclose(file));return bytes;
}
static void real_opus_fixture(const char *path,const char *receipt_path,bool physical_open)
{
    START(physical_open?"real_Opus_fixture_physical_OPEN_derived_export":"real_Opus_fixture_finalized_export");
    size_t length=read_file(path,fixture_data,sizeof(fixture_data));uint8_t receipt[94];
    CHECK(read_file(receipt_path,receipt,sizeof(receipt))==sizeof(receipt));
    CHECK(length>188&&!memcmp(fixture_data,"AUR3",4)&&!memcmp(receipt,"ACK3",4));
    CHECK(receipt[5]==(physical_open?0:AURA_ARCHIVE_FINALIZED));
    CHECK(!memcmp(fixture_data+length-120,"ASE3",4));
    CHECK(fixture_data[length-115]==(physical_open?AURA_ARCHIVE_INTERRUPTED:AURA_ARCHIVE_FINALIZED));
    size_t physical=length-(physical_open?120:0),offset=0;unsigned packets=0;
    reset(6);CHECK(!aura_journal_service(&journal,0));
    while(offset<physical){
        const uint8_t *record=fixture_data+offset;size_t bytes;
        if(!offset)bytes=68;
        else if(physical-offset>=26&&!memcmp(record,"AFR3",4)){
            bytes=26u+record[20]+((size_t)record[21]<<8);if(record[5]==1)++packets;
        }else{CHECK(physical-offset==120&&!memcmp(record,"ASE3",4));bytes=120;}
        CHECK(bytes<=AURA_ARCHIVE_RECORD_BYTES&&bytes<=physical-offset);
        CHECK(!aura_journal_stage(&journal,offset,record,bytes));offset+=bytes;
    }
    CHECK(offset==physical&&packets>0);CHECK(!aura_journal_flush(&journal));remount();
    CHECK(journal.count==1&&journal.active==-1);reference(0);
    CHECK(expected.bytes==length&&!memcmp(expected.data,fixture_data,length));
    CHECK(!memcmp(journal.captures[0].committed_receipt,receipt,sizeof(receipt)));
    const size_t capacities[]={1,128,256};
    for(size_t n=0;n<sizeof(capacities)/sizeof(capacities[0]);++n){
        struct aura_journal_cursor_info info=ready(0);
        CHECK(info.derived_seal==physical_open&&info.physical_bytes==physical&&info.export_bytes==length);
        CHECK(!memcmp(info.physical_receipt,receipt,sizeof(receipt)));
        seek_to(0);CHECK(!drain(0,capacities[n],true));cancel();receipt_cached(true);
    }
    printf("FIXTURE physical_open=%u export_bytes=%zu physical_bytes=%zu Opus_packets=%u exact_file_and_receipt=true\n",
        physical_open?1u:0u,length,physical,packets);PASS();
}
int main(int argc,char **argv)
{
    exports_and_capacities();resume_boundaries();wrapped_maximum_records();exact_identity();
    ecc_and_torn_tail();framing_holes_and_unassociated();changed_source();lifecycle_and_arguments();
    changed_allocation();late_lifecycle();empty_archives();
    first_manifest_binding();
    START("fixture_arguments");CHECK(argc==1||argc==5);
    if(argc==5){real_opus_fixture(argv[1],argv[2],false);real_opus_fixture(argv[3],argv[4],true);}
    model_destroy(&medium);
    printf("PASS cursor cases=%u checks=%u verify_calls=%llu read_calls=%llu max_reads_per_call=%u cursor_bytes=%zu host_model_only=true\n",
        cases,checks,(unsigned long long)verify_calls,(unsigned long long)read_calls,maximum_reads,sizeof(cursor));
    return 0;
}
