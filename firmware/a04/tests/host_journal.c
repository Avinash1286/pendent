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
    CHECK(begin(129)==AURA_JOURNAL_FULL);CHECK(model.erases==128);CHECK(!reopen());CHECK(journal.count==128);
    printf("MOUNT 128_short_captures blocks=129 metadata_reads=%llu payload_reads=%llu reads_bytes=%llu\n",
        (unsigned long long)journal.metadata_reads,(unsigned long long)journal.payload_reads,(unsigned long long)129*512);
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
static int fixture(const char *input_path,const char *prefix,unsigned mode)
{
    FILE *f=fopen(input_path,"rb");CHECK(f);CHECK(!fseek(f,0,SEEK_END));long bytes=ftell(f);rewind(f);
    CHECK(bytes>0&&bytes<2000000&&!(bytes%2));int16_t *pcm=malloc((size_t)bytes);CHECK(pcm);
    CHECK(fread(pcm,1,(size_t)bytes,f)==(size_t)bytes);fclose(f);CHECK(!reset(8));
    struct aura_opus_capture capture;void *state=malloc(aura_opus_state_bytes());CHECK(state);
    CHECK(!aura_opus_init_staged(&capture,state,aura_opus_state_bytes(),20,aura_archive_opus_commit,&writer));
    CHECK(capture.staging);CHECK(!aura_journal_service(&journal,0));CHECK(!begin(50+mode));
    size_t samples=(size_t)bytes/2,at=0;uint64_t ms=0;
    while(at<samples){size_t chunk=1280;if(chunk>samples-at)chunk=samples-at;size_t consumed;
        CHECK(!aura_opus_push(&capture,pcm+at,chunk,&consumed));CHECK(consumed==chunk);at+=consumed;ms+=80;
        CHECK(!aura_journal_service(&journal,ms));
        if(at==32000)CHECK(!aura_archive_bookmark(&writer,at));
    }
    if(mode==0){struct aura_opus_seal seal;CHECK(!aura_opus_finish(&capture,&seal));CHECK(!aura_archive_finalize(&writer,&seal));}
    else if(mode==2||mode==3){model.cut_program=model.programs+1;model.cut=mode==2?MODEL_CUT_PARTIAL:MODEL_CUT_AFTER;model.cut_bytes=700;CHECK(aura_journal_flush(&journal)<0);}
    uint64_t programmed=model.programs;CHECK(!reopen());CHECK(journal.payload_reads==0);CHECK(!aura_journal_verify(&journal,0));
    char name[1024];CHECK(snprintf(name,sizeof(name),"%s-%u.aura",prefix,mode)>0);
    struct export_sink sink={.file=fopen(name,"wb")};CHECK(sink.file);CHECK(!aura_journal_export(&journal,0,export_file,&sink));CHECK(!fclose(sink.file));
    uint8_t ack[94];CHECK(!aura_journal_receipt(&journal,0,ack));CHECK(snprintf(name,sizeof(name),"%s-%u.receipt",prefix,mode)>0);
    f=fopen(name,"wb");CHECK(f&&fwrite(ack,1,94,f)==94&&!fclose(f));
    printf("PASS real_opus_journal mode=%u physical_programs=%llu wire_bytes=%llu committed_bytes=%llu source_input_samples=%llu metadata_reads=%llu payload_reads=%llu\n",
        mode,(unsigned long long)programmed,(unsigned long long)sink.bytes,
        (unsigned long long)journal.captures[0].committed_wire_bytes,(unsigned long long)samples,
        (unsigned long long)journal.metadata_reads,(unsigned long long)journal.payload_reads);
    free(state);free(pcm);++tests;return 0;
}
int main(int argc,char **argv)
{
    CHECK(argc==3);CHECK(!blank_and_model());CHECK(!staging_and_replay());CHECK(!program_cuts());
    CHECK(!erase_cuts());CHECK(!corruption());CHECK(!continuation_and_full());CHECK(!export_changes());
    for(unsigned mode=0;mode<4;++mode)CHECK(!fixture(argv[1],argv[2],mode));
    printf("PASS journal groups=%u journal_context=%u model_is_host_only=%u\n",tests,(unsigned)sizeof(journal),(unsigned)sizeof(model));
    model_destroy(&model);return 0;
}
