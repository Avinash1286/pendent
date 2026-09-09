/* SPDX-License-Identifier: MIT */
#include "aura_journal.h"
#include "nand_model.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do{if(!(x)){fprintf(stderr,"FAIL journal line %d: %s\n",__LINE__,#x);return 1;}}while(0)
static struct nand_model model;
static struct aura_journal journal;
static struct aura_archive_writer writer;
static unsigned tests;
static const uint8_t owned_incarnation[16]={0xA4,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16};
static void put(uint8_t *p,uint64_t v,unsigned n){for(unsigned i=0;i<n;++i)p[i]=(uint8_t)(v>>(8*i));}
static void fix(uint8_t *p,size_t n){put(p+n-4,aura_archive_crc32(p,n-4),4);}
static int reset(unsigned blocks)
{model_destroy(&model);model_init(&model,blocks);return aura_journal_mount(&journal,model_io(&model));}
static int reopen(void){model_power_on(&model);return aura_journal_mount(&journal,model_io(&model));}
static int begin(unsigned id)
{
    if(!journal.service_clock_started){int r=aura_journal_service(&journal,0);if(r)return r;}
    struct aura_archive_manifest m={.frame_samples=320,.pre_skip=40};
    memset(m.device_id,17,16);memset(m.capture_id,(int)id,16);
    return aura_archive_begin_staged(&writer,&m,aura_journal_stage,&journal);
}
static int copy_manifest(void *user,uint64_t offset,const uint8_t *wire,size_t bytes)
{if(offset||bytes!=68)return -902;memcpy(user,wire,68);return 0;}
static int manifest_wire(unsigned id,uint8_t wire[68])
{
    struct aura_archive_manifest m={.frame_samples=320,.pre_skip=40};
    memset(m.device_id,17,16);memset(m.capture_id,(int)id,16);
    struct aura_archive_writer draft;
    return aura_archive_begin_staged(&draft,&m,copy_manifest,wire);
}
static int bind(unsigned id,uint64_t generation)
{uint8_t wire[68];int r=manifest_wire(id,wire);return r?r:aura_journal_bind_capture(&journal,wire,generation);}
static int packet(unsigned bytes)
{
    struct aura_opus_packet p={.sequence=writer.audio_packets,.sample_offset=writer.encoded_samples,
        .sample_count=320,.bytes=(uint16_t)bytes};
    memset(p.data,0x33,bytes);p.data[0]=0x98;
    return aura_archive_opus_commit(&writer,&p);
}
static int finish(void){return aura_archive_interrupt(&writer);}
static int blank_and_model(void)
{
    memset(&journal,0,sizeof(journal));CHECK(aura_journal_prepare(&journal)==AURA_NAND_BAD_ARGUMENT);
    CHECK(!reset(1024));CHECK(journal.metadata_reads==2048&&journal.payload_reads==0);
    CHECK(model.read_bytes==524288&&model.programs==0&&model.erases==0);
    printf("MOUNT empty blocks=1024 metadata_reads=%llu read_bytes=%llu payload_reads=0\n",
        (unsigned long long)journal.metadata_reads,(unsigned long long)model.read_bytes);
    struct aura_nand_io io=model_io(&model);io.blocks=0;CHECK(aura_journal_mount(&journal,io)==AURA_NAND_BAD_ARGUMENT);
    io.blocks=1025;CHECK(aura_journal_mount(&journal,io)==AURA_NAND_BAD_ARGUMENT);
    CHECK(!reset(1));struct aura_archive_manifest manifest={.frame_samples=320,.pre_skip=40};
    memset(manifest.device_id,17,16);memset(manifest.capture_id,18,16);
    CHECK(aura_archive_begin_staged(&writer,&manifest,aura_journal_stage,&journal)==AURA_NAND_BAD_ARGUMENT);
    CHECK(model.programs==0&&model.erases==0);
    CHECK(!reset(2));io=model_io(&model);uint8_t page[2048];memset(page,255,2048);
    CHECK(io.program(io.user,128,page)==AURA_NAND_BAD_ARGUMENT);
    CHECK(io.program(io.user,1,page)==AURA_NAND_PROGRAM_ORDER);
    CHECK(!io.program(io.user,2,page));CHECK(model.attempts[2]==1);
    model_power_on(&model);CHECK(io.program(io.user,2,page)==AURA_NAND_PROGRAM_ORDER);
    CHECK(!io.program(io.user,4,page));CHECK(io.program(io.user,3,page)==AURA_NAND_PROGRAM_ORDER);
    CHECK(!io.erase(io.user,0));CHECK(!io.program(io.user,2,page));
    /* Pre-existing programmed cells still forbid 0->1 even if cycle bookkeeping is missing. */
    model.pages[3]=malloc(2048);CHECK(model.pages[3]);memset(model.pages[3],0,2048);
    CHECK(io.program(io.user,3,page)==AURA_NAND_NOT_ERASED);
    for(unsigned p=0;p<2;++p)for(unsigned c=0;c<3;++c){
        CHECK(!reset(2));model.marker[0][p][c]=0;CHECK(!reopen());
        CHECK(journal.block_state[0]==AURA_BLOCK_EXCLUDED);CHECK(!aura_journal_prepare(&journal));
        CHECK(journal.prepared==1&&model.erases==1);
    }
    CHECK(!reset(2));model.remapped[0]=true;CHECK(!reopen());CHECK(journal.block_state[0]==AURA_BLOCK_EXCLUDED);
    CHECK(!reset(1));model.ecc[7]=2;CHECK(aura_journal_prepare(&journal)==AURA_JOURNAL_RETRY_PREPARE);CHECK(!model.erases);
    ++tests;return 0;
}
static int staging_and_replay(void)
{
    uint8_t ack[94];CHECK(!reset(4));CHECK(!aura_journal_service(&journal,1000));CHECK(!begin(1));
    CHECK(aura_archive_receipt(&writer,ack)==AURA_ARCHIVE_BUSY);
    CHECK(aura_journal_receipt(&journal,0,ack)==AURA_JOURNAL_NOT_COMMITTED);
    CHECK(model.programs==1);CHECK(!packet(80));CHECK(model.programs==2);
    CHECK(!aura_journal_receipt(&journal,0,ack));CHECK(journal.committed.audio_packets==1);
    CHECK(!packet(80));CHECK(!aura_journal_service(&journal,1399));CHECK(journal.committed.audio_packets==1);
    CHECK(!aura_journal_service(&journal,1400));CHECK(journal.committed.audio_packets==2);
    CHECK(aura_journal_service(&journal,1399)==AURA_NAND_BAD_ARGUMENT);
    for(unsigned n=0;n<19;++n)CHECK(!packet(80));
    CHECK(journal.committed.audio_packets==20&&writer.audio_packets==21);
    CHECK(!finish());CHECK(!journal.staged_bytes&&journal.active==-1);
    CHECK(!aura_journal_receipt(&journal,0,ack));uint8_t saved[94];memcpy(saved,ack,94);
    CHECK(!reopen());CHECK(journal.payload_reads==0);
    CHECK(aura_journal_receipt(&journal,0,ack)==AURA_JOURNAL_NOT_COMMITTED);
    CHECK(!aura_journal_verify(&journal,0));CHECK(!aura_journal_receipt(&journal,0,ack));CHECK(!memcmp(saved,ack,94));
    CHECK(!begin(2));CHECK(journal.current_block==1);CHECK(!finish());
    CHECK(!reopen());CHECK(begin(1)==AURA_JOURNAL_CONFLICT);
    ++tests;return 0;
}
static int program_cuts(void)
{
    /* Every Program Execute in a short capture: identity, first audio, packed
     * tail/seal and checkpoint; several partial-program boundaries. */
    const size_t cuts[]={0,1,60,255,700,2047,2048};
    for(unsigned operation=1;operation<=4;++operation)for(unsigned k=0;k<sizeof(cuts)/sizeof(cuts[0]);++k){
        CHECK(!reset(2));model.cut_program=operation;
        model.cut=cuts[k]==2048?MODEL_CUT_AFTER:MODEL_CUT_PARTIAL;model.cut_bytes=cuts[k];
        int r=begin(1);if(!r)r=packet(80);if(!r)r=packet(80);if(!r)r=finish();CHECK(r<0);
        CHECK(model.programs==operation);CHECK(!reopen());
        if(journal.count){r=aura_journal_verify(&journal,0);
            bool audio_survives=operation>2||(operation==2&&cuts[k]==2048);
            CHECK(audio_survives?r==0:r==AURA_JOURNAL_NOT_COMMITTED);
            if(audio_survives){uint8_t ack[94];CHECK(!aura_journal_receipt(&journal,0,ack));
                CHECK(journal.captures[0].committed_wire_bytes>=174);}
        }else CHECK(operation==1&&cuts[k]<2048);
    }
    for(unsigned cut=MODEL_CUT_BEFORE;cut<=MODEL_CUT_AFTER;++cut){
        CHECK(!reset(3));CHECK(!begin(1));CHECK(!packet(80));CHECK(!packet(80));
        model.cut_program=model.programs+1;model.cut=(enum model_cut)cut;model.cut_bytes=100;
        CHECK(aura_journal_flush(&journal)<0);CHECK(model.attempts[4]==1);
        uint64_t programs=model.programs;CHECK(!reopen());CHECK(!aura_journal_verify(&journal,0));
        CHECK(journal.captures[0].committed_wire_bytes==(cut==MODEL_CUT_AFTER?280:174));
        CHECK(!begin(2));CHECK(journal.current_block==1&&model.programs==programs+1);
    }
    CHECK(!reset(2));CHECK(!begin(1));CHECK(!packet(80));CHECK(!packet(80));
    model.cut_program=model.programs+1;model.cut=MODEL_CUT_AFTER;model.lose_completion_only=true;
    CHECK(!aura_journal_flush(&journal));CHECK(journal.committed.audio_packets==2&&model.attempts[4]==1);
    CHECK(!reset(2));CHECK(!begin(1));CHECK(!packet(80));CHECK(!packet(80));
    model.program_failure[0]=1;CHECK(aura_journal_flush(&journal)==AURA_NAND_PROGRAM_FAILED);
    CHECK(journal.committed.audio_packets==1);CHECK(packet(80)==AURA_NAND_PROGRAM_FAILED);
    CHECK(!reopen());CHECK(!aura_journal_verify(&journal,0));CHECK(journal.captures[0].committed_wire_bytes==174);
    /* Uncertain all-FF identity-page program cannot be programmed again before erase. */
    CHECK(!reset(2));uint8_t ff[2048];memset(ff,255,2048);struct aura_nand_io io=model_io(&model);
    model.cut_program=1;model.cut=MODEL_CUT_BEFORE;CHECK(io.program(io.user,2,ff)==AURA_NAND_UNCERTAIN);
    CHECK(!reopen());CHECK(!begin(1));CHECK(model.erases==1&&model.attempts[2]==1);
    ++tests;return 0;
}
static int erase_cuts(void)
{
    for(unsigned cut=MODEL_CUT_BEFORE;cut<=MODEL_CUT_AFTER;++cut){
        CHECK(!reset(2));model.cut_erase=1;model.cut=(enum model_cut)cut;model.cut_bytes=7;
        CHECK(aura_journal_prepare(&journal)==AURA_JOURNAL_RETRY_PREPARE);
        CHECK(!reopen());CHECK(!aura_journal_prepare(&journal));CHECK(model.erases==2);
    }
    CHECK(!reset(2));model.erase_failure[0]=1;
    CHECK(aura_journal_prepare(&journal)==AURA_JOURNAL_RETRY_PREPARE);CHECK(!aura_journal_prepare(&journal));CHECK(journal.prepared==1);
    /* Blank header with nonblank payload (including residue of partial erase) is preserved. */
    CHECK(!reset(2));uint8_t page[2048];memset(page,0,2048);struct aura_nand_io io=model_io(&model);
    CHECK(!io.program(io.user,20,page));model.cut_erase=1;model.cut=MODEL_CUT_PARTIAL;model.cut_bytes=7;
    CHECK(io.erase(io.user,0)==AURA_NAND_UNCERTAIN);CHECK(!reopen());
    CHECK(aura_journal_prepare(&journal)==AURA_JOURNAL_RETRY_PREPARE);CHECK(model.erases==1);
    CHECK(journal.block_state[0]==AURA_BLOCK_QUARANTINED&&model.pages[20][0]==0);
    ++tests;return 0;
}
static int corruption(void)
{
    /* CRC-bad page, then a valid later page: never silently truncate. */
    CHECK(!reset(3));CHECK(!begin(1));CHECK(!packet(80));CHECK(!packet(80));CHECK(!aura_journal_flush(&journal));
    CHECK(!packet(80));CHECK(!aura_journal_flush(&journal));model.pages[4][100]^=1;
    CHECK(!reopen());CHECK(aura_journal_verify(&journal,0)==AURA_JOURNAL_CORRUPT);
    /* An unreadable page and blank page still require inspecting every later slot. */
    for(unsigned mode=0;mode<3;++mode){
        CHECK(!reset(2));CHECK(!begin(1));CHECK(!packet(80));CHECK(!packet(80));CHECK(!aura_journal_flush(&journal));
        CHECK(!finish());
        if(mode==0){free(model.pages[4]);model.pages[4]=NULL;}
        if(mode==1)model.ecc[4]=2;
        if(mode==2)model.pages[4][99]^=1;
        CHECK(!reopen());CHECK(aura_journal_verify(&journal,0)==AURA_JOURNAL_CORRUPT);
    }
    /* Valid checkpoint claims a now unreadable tail; later slots are all blank. */
    CHECK(!reset(2));CHECK(!begin(1));CHECK(!packet(80));CHECK(!finish());model.ecc[4]=2;
    CHECK(!reopen());CHECK(aura_journal_verify(&journal,0)==AURA_JOURNAL_CORRUPT);
    CHECK(!reset(2));CHECK(!begin(1));CHECK(!packet(80));CHECK(!finish());model.ecc[3]=1;
    CHECK(!reopen());CHECK(!aura_journal_verify(&journal,0));CHECK(journal.corrected_reads>0);
    /* CRC-valid but wrong canonical record / padding / declaration is corruption. */
    for(unsigned mode=0;mode<3;++mode){
        CHECK(!reset(2));CHECK(!begin(1));CHECK(!packet(80));CHECK(!finish());
        if(mode==0){model.pages[3][80]^=1;fix(model.pages[3],2048);}
        if(mode==1){model.pages[3][2000]=0;fix(model.pages[3],2048);}
        if(mode==2){model.pages[63][20]^=1;fix(model.pages[63],256);}
        CHECK(!reopen());CHECK(aura_journal_verify(&journal,0)==AURA_JOURNAL_CORRUPT);
    }
    /* Torn checkpoint following a fully committed terminal page preserves seal. */
    CHECK(!reset(2));CHECK(!begin(1));CHECK(!packet(80));model.cut=MODEL_CUT_PARTIAL;
    model.cut_program=model.programs+2;model.cut_bytes=40;CHECK(finish()<0);
    CHECK(!reopen());CHECK(!aura_journal_verify(&journal,0));CHECK(journal.captures[0].verification==AURA_JOURNAL_VERIFIED_INTERRUPTED);
    /* A repeated terminal record must never replay successfully after closing. */
    struct aura_archive_writer replay=writer;replay.status=AURA_ARCHIVE_INTERRUPTED;
    CHECK(aura_archive_replay(&replay,writer.wire,120)==AURA_ARCHIVE_BAD_ARGUMENT);
    ++tests;return 0;
}
static int continuation_and_full(void)
{
    uint8_t ack[94];CHECK(!reset(3));CHECK(!begin(1));
    /* Large legal record forces one per page, stressing boundary correctness. */
    for(unsigned n=0;n<65;++n)CHECK(!packet(1275));CHECK(!finish());
    CHECK(journal.captures[0].blocks==2);CHECK(!aura_journal_receipt(&journal,0,ack));
    uint8_t saved[94];memcpy(saved,ack,94);CHECK(!reopen());CHECK(!aura_journal_verify(&journal,0));
    CHECK(!aura_journal_receipt(&journal,0,ack)&&!memcmp(saved,ack,94));
    model.pages[66][100]^=1;CHECK(!reopen());CHECK(journal.captures[0].metadata_fault);
    CHECK(aura_journal_verify(&journal,0)==AURA_JOURNAL_CORRUPT);
    model.pages[66][100]^=1;
    model.pages[3][100]^=1;CHECK(!reopen());CHECK(aura_journal_verify(&journal,0)==AURA_JOURNAL_CORRUPT);
    /* Unidentifiable torn next header has no checkpoint; preserve it and make
     * the orphan count visible beside an explicitly interrupted prefix. */
    CHECK(!reset(3));CHECK(!begin(1));for(unsigned k=0;k<61;++k)CHECK(!packet(1275));
    model.cut_program=model.programs+1;model.cut=MODEL_CUT_PARTIAL;model.cut_bytes=40;
    CHECK(aura_journal_flush(&journal)<0);CHECK(!reopen());
    CHECK(journal.unassociated_blocks==1&&journal.block_state[1]==AURA_BLOCK_QUARANTINED);
    CHECK(!aura_journal_verify(&journal,0));CHECK(journal.captures[0].verification==AURA_JOURNAL_VERIFIED_OPEN);
    CHECK(!reset(1));CHECK(!begin(1));unsigned n=0;int r=0;
    while(!r&&n<100){r=packet(1275);++n;}CHECK(r==AURA_JOURNAL_FULL&&n<100);
    CHECK(!aura_journal_receipt(&journal,0,ack));CHECK(!aura_journal_verify(&journal,0));
    CHECK(model.erases==1&&model.programs==62);CHECK(!reopen());CHECK(!aura_journal_verify(&journal,0));
    CHECK(journal.captures[0].committed_wire_bytes==68+60*1301);CHECK(begin(2)==AURA_JOURNAL_FULL);
    CHECK(model.erases==1&&model.programs==62);
    CHECK(!reset(129));
    for(unsigned id=1;id<=128;++id){CHECK(!begin(id));CHECK(!packet(80));CHECK(!finish());}
    CHECK(begin(129)==AURA_JOURNAL_FULL);CHECK(model.erases==128);
    uint64_t reads_before=model.read_bytes;CHECK(!reopen());CHECK(journal.count==128);
    CHECK(journal.metadata_reads==386&&journal.payload_reads==0&&model.read_bytes-reads_before==98816);
    printf("MOUNT 128_short_captures blocks=129 metadata_reads=%llu payload_reads=%llu reads_bytes=%llu\n",
        (unsigned long long)journal.metadata_reads,(unsigned long long)journal.payload_reads,
        (unsigned long long)(model.read_bytes-reads_before));
    ++tests;return 0;
}
/* Use the real writer and NAND programming rules to fill 2, then create a
 * three-block capture in 3 -> 0 -> 1. No successful-layout bytes are patched. */
static int wrapped_layout(void)
{
    CHECK(!reset(4));journal.allocation_cursor=2;
    CHECK(!begin(9));CHECK(!packet(80));CHECK(!finish());
    CHECK(!begin(1));for(unsigned n=0;n<125;++n)CHECK(!packet(1275));CHECK(!finish());
    CHECK(journal.captures[1].first_block==3&&journal.captures[1].last_block==1);
    CHECK(journal.captures[1].blocks==3&&journal.next_block[3]==0&&journal.next_block[0]==1);
    CHECK(journal.next_block[1]==AURA_JOURNAL_NONE&&model.erases==4);return 0;
}
static int catalog_id(unsigned id)
{
    for(unsigned i=0;i<journal.count;++i)if(journal.captures[i].manifest[24]==id)return (int)i;
    return -1;
}
struct byte_digest{uint64_t bytes;uint8_t *data;size_t capacity;};
static int digest_output(void *user,uint64_t offset,const uint8_t *p,size_t n)
{
    struct byte_digest *sink=user;
    if(offset!=sink->bytes||n>sink->capacity-sink->bytes)return -901;
    memcpy(sink->data+sink->bytes,p,n);sink->bytes+=n;return 0;
}
static int wrapped_recovery(void)
{
    CHECK(!wrapped_layout());uint8_t saved[94],ack[94],original_hash[32],recovered_hash[32];
    CHECK(!aura_journal_receipt(&journal,1,saved));
    struct byte_digest original={.data=malloc(200000),.capacity=200000};CHECK(original.data);
    CHECK(!aura_journal_export(&journal,1,digest_output,&original));
    aura_archive_sha256(original.data,(size_t)original.bytes,original_hash);
    uint64_t reads_before=model.read_bytes,erases=model.erases,programs=model.programs;
    CHECK(!reopen());CHECK(journal.count==2&&journal.metadata_reads==12&&journal.payload_reads==0);
    CHECK(model.read_bytes-reads_before==3072&&model.erases==erases&&model.programs==programs);
    int index=catalog_id(1);CHECK(index>=0&&!journal.captures[index].metadata_fault);
    CHECK(journal.captures[index].first_block==3&&journal.captures[index].last_block==1);
    CHECK(aura_journal_receipt(&journal,(uint16_t)index,ack)==AURA_JOURNAL_NOT_COMMITTED);
    CHECK(!aura_journal_verify(&journal,(uint16_t)index));
    CHECK(!aura_journal_receipt(&journal,(uint16_t)index,ack)&&!memcmp(saved,ack,94));
    struct byte_digest recovered={.data=malloc(200000),.capacity=200000};CHECK(recovered.data);
    CHECK(!aura_journal_export(&journal,(uint16_t)index,digest_output,&recovered));
    aura_archive_sha256(recovered.data,(size_t)recovered.bytes,recovered_hash);
    CHECK(original.bytes==recovered.bytes&&!memcmp(original_hash,recovered_hash,32));
    CHECK(!aura_journal_verify(&journal,(uint16_t)catalog_id(9)));
    CHECK(aura_journal_prepare(&journal)==AURA_JOURNAL_FULL);
    CHECK(model.erases==erases&&model.programs==programs);
    printf("PASS wrapped_chain 3->0->1 captures=2 metadata_reads=12 payload_reads_at_mount=0 export_bytes=%llu exact_digest_and_receipt=true\n",
        (unsigned long long)recovered.bytes);
    free(original.data);free(recovered.data);++tests;return 0;
}
static int conflicting_chains(void)
{
    for(unsigned mode=0;mode<12;++mode){
        CHECK(!wrapped_layout());uint8_t *h=model.pages[2];
        switch(mode){
        case 0:put(h+16,2,4);break; /* missing part 1 */
        case 1:h=model.pages[66];put(h+12,3,4);break; /* two successors of head */
        case 2:put(h+12,2,4);break; /* predecessor belongs to capture 9 */
        case 3:h=model.pages[194];put(h+12,0,4);break; /* noncanonical head */
        case 4:put(h+12,0,4);break; /* self link */
        case 5:h=model.pages[66];put(h+12,17,4);break; /* out of bounds */
        case 6:put(h+16,0,4);put(h+12,UINT32_MAX,4);put(h+20,0,8);break; /* duplicate head */
        case 7:h=model.pages[194];put(h+16,1,4);put(h+12,1,4);break; /* cycle / no head */
        case 8:h=model.pages[66];put(h+16,1,4);break; /* duplicate part */
        case 9:h[100]^=1;break; /* damaged header, valid identifying checkpoint */
        case 10:h=model.pages[66];h[28]^=1;break; /* conflicting duplicate identity */
        default:h=model.pages[66];put(h+12,UINT32_MAX,4);break;
        }
        if(mode!=9)fix(h,256);
        uint64_t erases=model.erases,programs=model.programs;CHECK(!reopen());
        int index=catalog_id(1);CHECK(index>=0&&journal.captures[index].metadata_fault);
        CHECK(aura_journal_verify(&journal,(uint16_t)index)==AURA_JOURNAL_CORRUPT);
        uint8_t ack[94];CHECK(aura_journal_receipt(&journal,(uint16_t)index,ack)==AURA_JOURNAL_NOT_COMMITTED);
        int other=catalog_id(9);CHECK(other>=0);
        CHECK(aura_journal_verify(&journal,(uint16_t)other)==(mode==2?AURA_JOURNAL_CORRUPT:0));
        CHECK(aura_journal_prepare(&journal)==AURA_JOURNAL_FULL);
        CHECK(model.erases==erases&&model.programs==programs);
    }
    printf("PASS conflicting_chains cases=12 no_source_erase=true\n");++tests;return 0;
}
static int reclassified_continuation(void)
{
    for(unsigned wrapped=0;wrapped<2;++wrapped){
        CHECK(!reset(3));journal.allocation_cursor=wrapped?2:0;
        CHECK(!begin(1));for(unsigned n=0;n<65;++n)CHECK(!packet(1275));CHECK(!finish());
        uint16_t tail=wrapped?0:1;CHECK(journal.captures[0].last_block==tail);
        /* The continuation now has a fully canonical head for another capture,
         * but its unchanged checkpoint still identifies committed capture 1. */
        uint8_t *h=model.pages[tail*64+2];
        put(h+12,UINT32_MAX,4);put(h+16,0,4);put(h+20,0,8);
        memset(h+44,2,16);memset(h+84,2,16);fix(h+60,68);
        memset(h+128,0,94);fix(h,256);
        uint64_t programs=model.programs,erases=model.erases;CHECK(!reopen());
        CHECK(journal.count==2&&journal.unassociated_blocks==0&&journal.payload_reads==0);
        for(unsigned id=1;id<=2;++id){
            int index=catalog_id(id);CHECK(index>=0&&journal.captures[index].metadata_fault);
            CHECK(aura_journal_verify(&journal,(uint16_t)index)==AURA_JOURNAL_CORRUPT);
            uint8_t ack[94];CHECK(aura_journal_receipt(&journal,(uint16_t)index,ack)==AURA_JOURNAL_NOT_COMMITTED);
        }
        CHECK(model.programs==programs&&model.erases==erases);
    }
    CHECK(!reset(2));CHECK(!begin(1));CHECK(!packet(80));CHECK(!finish());
    uint8_t *checkpoint=model.pages[63];memset(checkpoint+50,9,16);
    fix(checkpoint+28,94);fix(checkpoint,256);
    CHECK(!reopen());CHECK(journal.count==1&&journal.unassociated_blocks==1);
    CHECK(journal.captures[0].metadata_fault&&aura_journal_verify(&journal,0)==AURA_JOURNAL_CORRUPT);
    printf("PASS reclassified_continuation physical_orders=2 both_owners_faulted=true no_source_erase=true\n");
    ++tests;return 0;
}
struct export_sink{FILE *file;uint64_t bytes;};
static int export_file(void *user,uint64_t offset,const uint8_t *p,size_t n)
{struct export_sink *s=user;if(offset!=s->bytes||fwrite(p,1,n,s->file)!=n)return -900;s->bytes+=n;return 0;}
static int changing_output(void *user,uint64_t offset,const uint8_t *p,size_t n)
{
    (void)p;size_t *bytes=user;*bytes+=n;
    if(!offset)model.pages[4][100]^=1;
    return 0;
}
static int export_changes(void)
{
    CHECK(!reset(2));CHECK(!begin(1));CHECK(!packet(80));CHECK(!finish());CHECK(!reopen());
    size_t bytes=0;CHECK(aura_journal_export(&journal,0,changing_output,&bytes)==AURA_JOURNAL_CORRUPT);
    CHECK(bytes>0&&journal.captures[0].verification==AURA_JOURNAL_INVALID);
    uint8_t ack[94];CHECK(aura_journal_receipt(&journal,0,ack)==AURA_JOURNAL_NOT_COMMITTED);
    ++tests;return 0;
}
static int owned_bindings(void)
{
    CHECK(!reset(8));CHECK(!begin(1));CHECK(!packet(80));CHECK(!finish());
    struct aura_journal_allocation_identity id;
    CHECK(!aura_journal_get_allocation_identity(&journal,0,&id));
    CHECK(id.version==1&&!id.owned&&!id.allocation_generation);
    CHECK(!aura_journal_set_owned_profile(&journal,owned_incarnation));
    uint64_t erases=model.erases,programs=model.programs;
    CHECK(begin(2)==AURA_JOURNAL_CONFLICT&&model.erases==erases&&model.programs==programs);
    uint8_t wire[68];CHECK(!manifest_wire(2,wire));
    CHECK(aura_journal_bind_capture(&journal,wire,0)==AURA_NAND_BAD_ARGUMENT);
    CHECK(!aura_journal_bind_capture(&journal,wire,10));
    CHECK(bind(3,11)==AURA_JOURNAL_BUSY);
    /* The same IDs with a different canonical frame profile are still a
     * different manifest. Caller edits cannot change the retained binding. */
    put(wire+44,160,2);fix(wire,68);CHECK(memcmp(wire,journal.bound_manifest,68));
    CHECK(aura_journal_stage(&journal,0,wire,68)==AURA_JOURNAL_CONFLICT&&!journal.binding_pending);
    CHECK(bind(2,10)==AURA_JOURNAL_CONFLICT&&model.erases==erases&&model.programs==programs);
    CHECK(!bind(2,11));CHECK(!aura_journal_discard_binding(&journal));
    CHECK(bind(2,11)==AURA_JOURNAL_CONFLICT);CHECK(!bind(2,12));CHECK(!begin(2));
    CHECK(!journal.binding_pending&&journal.capture_generation==12);
    CHECK(bind(3,13)==AURA_JOURNAL_BUSY&&aura_journal_discard_binding(&journal)==AURA_JOURNAL_BUSY);
    CHECK(aura_journal_set_owned_profile(&journal,owned_incarnation)==AURA_JOURNAL_BUSY);
    CHECK(!packet(80));CHECK(!finish());
    CHECK(!aura_journal_get_allocation_identity(&journal,1,&id));
    CHECK(id.owned&&id.version==2&&id.allocation_generation==12&&!memcmp(id.incarnation,owned_incarnation,16));
    CHECK(model.pages[66][4]==2&&!memcmp(model.pages[66]+222,owned_incarnation,16));
    CHECK(model.pages[127][4]==2&&!memcmp(model.pages[127]+122,owned_incarnation,16));
    CHECK(begin(3)==AURA_JOURNAL_CONFLICT);
    uint8_t other[16];memcpy(other,owned_incarnation,16);other[0]^=1;
    CHECK(aura_journal_set_owned_profile(&journal,other)==AURA_JOURNAL_CONFLICT);
    CHECK(!aura_journal_set_owned_profile(&journal,owned_incarnation)&&journal.last_bound_generation==12);
    CHECK(!reopen()&&journal.count==2&&journal.payload_reads==0);
    CHECK(!aura_journal_get_allocation_identity(&journal,0,&id)&&!id.owned&&id.version==1);
    CHECK(!aura_journal_get_allocation_identity(&journal,1,&id)&&id.owned&&id.allocation_generation==12);
    CHECK(!aura_journal_set_owned_profile(&journal,owned_incarnation)&&journal.last_bound_generation==12);
    CHECK(bind(3,12)==AURA_JOURNAL_CONFLICT&&bind(2,13)==AURA_JOURNAL_CONFLICT);
    CHECK(!bind(3,13));CHECK(!begin(3));CHECK(!finish());
    /* Preparation may advance past a newly excluded candidate without burning
     * the binding a second time or requiring a replacement reservation. */
    CHECK(!reset(3));CHECK(!aura_journal_set_owned_profile(&journal,owned_incarnation));CHECK(!bind(1,1));
    model.remapped[0]=true;CHECK(begin(1)==AURA_JOURNAL_RETRY_PREPARE&&journal.binding_pending);
    CHECK(!begin(1)&&!journal.binding_pending&&journal.current_block==1);CHECK(!finish());
    printf("PASS owned_bindings exact_manifest=true one_use=true legacy_preserved=true durable_reservation_external=true\n");
    ++tests;return 0;
}
static int owned_wrapped_layout(void)
{
    CHECK(!reset(4));journal.allocation_cursor=2;
    CHECK(!begin(9));CHECK(!packet(80));CHECK(!finish());
    CHECK(!aura_journal_set_owned_profile(&journal,owned_incarnation));CHECK(!bind(1,25));
    CHECK(!begin(1));for(unsigned n=0;n<125;++n)CHECK(!packet(1275));CHECK(!finish());
    CHECK(journal.captures[1].first_block==3&&journal.captures[1].last_block==1);
    CHECK(journal.captures[1].blocks==3);return 0;
}
static int owned_chain_identity(void)
{
    CHECK(!owned_wrapped_layout());struct aura_journal_allocation_identity identity;
    CHECK(!aura_journal_get_allocation_identity(&journal,1,&identity)&&identity.owned&&identity.allocation_generation==25);
    uint64_t programs=model.programs,erases=model.erases;CHECK(!reopen());
    CHECK(journal.metadata_reads==18&&journal.payload_reads==0);
    CHECK(!aura_journal_get_allocation_identity(&journal,(uint16_t)catalog_id(1),&identity));
    CHECK(identity.version==2&&identity.allocation_generation==25&&!memcmp(identity.incarnation,owned_incarnation,16));
    CHECK(model.programs==programs&&model.erases==erases);
    for(unsigned mode=0;mode<12;++mode){
        CHECK(!owned_wrapped_layout());uint8_t *p=model.pages[66];
        switch(mode){
        case 0:p[238]^=1;break;
        case 1:p[222]^=1;break;
        case 2:p[4]=1;memset(p+222,0,30);break;
        case 3:p=model.pages[194];p[4]=1;memset(p+222,0,30);break;
        case 4:p=model.pages[127];p[138]^=1;break;
        case 5:p=model.pages[127];p[122]^=1;break;
        case 6:p=model.pages[127];p[4]=1;memset(p+122,0,130);break;
        case 7:p=model.pages[255];p[4]=1;memset(p+122,0,130);break;
        case 8:p[246]=1;break;
        case 9:p=model.pages[127];p[146]=1;break;
        case 10:{
            uint8_t wire[68];CHECK(!manifest_wire(9,wire));memcpy(p+60,wire,68);memcpy(p+28,wire+8,32);
            put(p+12,UINT32_MAX,4);put(p+16,0,4);put(p+20,0,8);memset(p+128,0,94);break;
        }
        default:memset(p+222,0,16);break;
        }
        fix(p,256);programs=model.programs;erases=model.erases;CHECK(!reopen());
        int index=catalog_id(1);CHECK(index>=0&&journal.captures[index].metadata_fault);
        CHECK(aura_journal_get_allocation_identity(&journal,(uint16_t)index,&identity)==AURA_JOURNAL_CORRUPT);
        uint8_t ack[94];CHECK(aura_journal_receipt(&journal,(uint16_t)index,ack)==AURA_JOURNAL_NOT_COMMITTED);
        int legacy=catalog_id(9);CHECK(legacy>=0);
        CHECK(aura_journal_verify(&journal,(uint16_t)legacy)==(mode==10?AURA_JOURNAL_CORRUPT:0));
        CHECK(model.programs==programs&&model.erases==erases);
    }
    /* Getter cannot rely on a previous cached verification after metadata
     * changes. A single-block header/checkpoint identity disagreement fails. */
    CHECK(!reset(2));CHECK(!aura_journal_set_owned_profile(&journal,owned_incarnation));
    CHECK(!bind(1,1));CHECK(!begin(1));CHECK(!packet(80));CHECK(!finish());
    CHECK(!aura_journal_get_allocation_identity(&journal,0,&identity));model.pages[63][138]^=1;fix(model.pages[63],256);
    CHECK(aura_journal_get_allocation_identity(&journal,0,&identity)==AURA_JOURNAL_CORRUPT);
    printf("PASS owned_chain_identity corruption_cases=13 wrapped_order=3->0->1 metadata_reads=18 legacy_crossowners_preserved=true\n");
    ++tests;return 0;
}
static int owned_power_cuts(void)
{
    const size_t cuts[]={0,1,121,137,145,221,237,245,251,255,700,2047,2048};
    for(unsigned operation=1;operation<=4;++operation)for(unsigned k=0;k<sizeof(cuts)/sizeof(cuts[0]);++k){
        CHECK(!reset(3));CHECK(!aura_journal_set_owned_profile(&journal,owned_incarnation));CHECK(!bind(1,100));
        model.cut_program=operation;model.cut=cuts[k]==2048?MODEL_CUT_AFTER:MODEL_CUT_PARTIAL;model.cut_bytes=cuts[k];
        int r=begin(1);if(!r)r=packet(80);if(!r)r=packet(80);if(!r)r=finish();
        CHECK(r<0&&!journal.binding_pending&&journal.last_bound_generation==100);
        CHECK(model.programs==operation);uint64_t programs=model.programs,erases=model.erases;
        CHECK(!reopen()&&journal.payload_reads==0);
        if(journal.count){
            struct aura_journal_allocation_identity id;
            r=aura_journal_get_allocation_identity(&journal,0,&id);
            bool audio_survives=operation>2||(operation==2&&cuts[k]==2048);
            CHECK(audio_survives?r==0:r==AURA_JOURNAL_NOT_COMMITTED);
            if(!r)CHECK(id.owned&&id.version==2&&id.allocation_generation==100&&!memcmp(id.incarnation,owned_incarnation,16));
        }else CHECK(operation==1&&cuts[k]<2048);
        CHECK(model.programs==programs&&model.erases==erases);
    }
    CHECK(!reset(2));CHECK(!aura_journal_set_owned_profile(&journal,owned_incarnation));CHECK(!bind(1,100));
    model.cut_program=1;model.cut=MODEL_CUT_AFTER;model.lose_completion_only=true;
    CHECK(!begin(1)&&!journal.binding_pending&&model.attempts[2]==1);CHECK(!packet(80));CHECK(!finish());
    CHECK(!reopen());CHECK(!aura_journal_set_owned_profile(&journal,owned_incarnation));
    CHECK(bind(2,100)==AURA_JOURNAL_CONFLICT&&journal.last_bound_generation==100);
    printf("PASS owned_power_cuts cases=52 header_checkpoint_identity=true no_binding_reuse=true\n");
    ++tests;return 0;
}
static int fixture(const char *input_path,const char *prefix,unsigned mode)
{
    FILE *f=fopen(input_path,"rb");CHECK(f);CHECK(!fseek(f,0,SEEK_END));long bytes=ftell(f);rewind(f);
    CHECK(bytes>0&&bytes<2000000&&!(bytes%2));int16_t *pcm=malloc((size_t)bytes);CHECK(pcm);
    CHECK(fread(pcm,1,(size_t)bytes,f)==(size_t)bytes);fclose(f);CHECK(!reset(8));
    if(mode==4||mode==5){
        int16_t *long_pcm=realloc(pcm,(size_t)bytes*4);CHECK(long_pcm);pcm=long_pcm;
        for(unsigned repeat=1;repeat<4;++repeat)memcpy((uint8_t *)pcm+(size_t)bytes*repeat,pcm,(size_t)bytes);
        bytes*=4;journal.allocation_cursor=7;
    }
    struct aura_opus_capture capture;void *state=malloc(aura_opus_state_bytes());CHECK(state);
    CHECK(!aura_opus_init_staged(&capture,state,aura_opus_state_bytes(),20,aura_archive_opus_commit,&writer));
    CHECK(capture.staging);CHECK(!aura_journal_service(&journal,0));
    if(mode==5){CHECK(!aura_journal_set_owned_profile(&journal,owned_incarnation));CHECK(!bind(50+mode,UINT64_C(0x100000002)));}
    CHECK(!begin(50+mode));
    size_t samples=(size_t)bytes/2,at=0;uint64_t ms=0;
    while(at<samples){size_t chunk=1280;if(chunk>samples-at)chunk=samples-at;size_t consumed;
        CHECK(!aura_opus_push(&capture,pcm+at,chunk,&consumed));CHECK(consumed==chunk);at+=consumed;ms+=80;
        CHECK(!aura_journal_service(&journal,ms));
        if(at==32000)CHECK(!aura_archive_bookmark(&writer,at));
    }
    if(mode==0||mode==4||mode==5){struct aura_opus_seal seal;CHECK(!aura_opus_finish(&capture,&seal));CHECK(!aura_archive_finalize(&writer,&seal));}
    else if(mode==2||mode==3){model.cut_program=model.programs+1;model.cut=mode==2?MODEL_CUT_PARTIAL:MODEL_CUT_AFTER;model.cut_bytes=700;CHECK(aura_journal_flush(&journal)<0);}
    if(mode==4||mode==5)CHECK(journal.captures[0].first_block==7&&journal.captures[0].last_block==0&&journal.captures[0].blocks==2);
    uint64_t programmed=model.programs;CHECK(!reopen());CHECK(journal.payload_reads==0);CHECK(!aura_journal_verify(&journal,0));
    char name[1024];CHECK(snprintf(name,sizeof(name),"%s-%u.aura",prefix,mode)>0);
    struct export_sink sink={.file=fopen(name,"wb")};CHECK(sink.file);CHECK(!aura_journal_export(&journal,0,export_file,&sink));CHECK(!fclose(sink.file));
    uint8_t ack[94];CHECK(!aura_journal_receipt(&journal,0,ack));CHECK(snprintf(name,sizeof(name),"%s-%u.receipt",prefix,mode)>0);
    f=fopen(name,"wb");CHECK(f&&fwrite(ack,1,94,f)==94&&!fclose(f));
    if(mode==5){
        struct aura_journal_allocation_identity identity;CHECK(!aura_journal_get_allocation_identity(&journal,0,&identity));
        CHECK(identity.owned&&identity.version==2&&identity.allocation_generation==UINT64_C(0x100000002));
        CHECK(!memcmp(identity.incarnation,owned_incarnation,16));
        CHECK(snprintf(name,sizeof(name),"%s-%u.allocation",prefix,mode)>0);f=fopen(name,"wb");CHECK(f);
        const unsigned blocks[]={7,0};
        for(unsigned part=0;part<2;++part){CHECK(fwrite(model.pages[blocks[part]*64+2],1,256,f)==256);
            CHECK(fwrite(model.pages[blocks[part]*64+63],1,256,f)==256);}
        CHECK(!fclose(f));
    }
    printf("PASS real_opus_journal mode=%u physical_programs=%llu wire_bytes=%llu committed_bytes=%llu source_input_samples=%llu metadata_reads=%llu payload_reads=%llu\n",
        mode,(unsigned long long)programmed,(unsigned long long)sink.bytes,
        (unsigned long long)journal.captures[0].committed_wire_bytes,(unsigned long long)samples,
        (unsigned long long)journal.metadata_reads,(unsigned long long)journal.payload_reads);
    free(state);free(pcm);++tests;return 0;
}
int main(int argc,char **argv)
{
    CHECK(argc==3);CHECK(!blank_and_model());CHECK(!staging_and_replay());CHECK(!program_cuts());
    CHECK(!erase_cuts());CHECK(!corruption());CHECK(!continuation_and_full());
    CHECK(!wrapped_recovery());CHECK(!conflicting_chains());CHECK(!reclassified_continuation());CHECK(!export_changes());
    CHECK(!owned_bindings());CHECK(!owned_chain_identity());CHECK(!owned_power_cuts());
    for(unsigned mode=0;mode<6;++mode)CHECK(!fixture(argv[1],argv[2],mode));
    printf("PASS journal groups=%u journal_context=%u model_is_host_only=%u\n",tests,(unsigned)sizeof(journal),(unsigned)sizeof(model));
    model_destroy(&model);return 0;
}
