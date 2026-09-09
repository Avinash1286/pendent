/* SPDX-License-Identifier: MIT */
#include "aura_recorder.h"
#include "nand_model.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do{if(!(x)){fprintf(stderr,"FAIL recorder line %d: %s\n",__LINE__,#x);return 1;}}while(0)
static struct nand_model model;
static struct aura_journal journal;
static struct aura_recorder recorder;
static union{max_align_t align;uint8_t bytes[AURA_OPUS_STATE_LIMIT];} arena;
static int16_t synthetic[320];
static unsigned groups;

static struct aura_archive_manifest manifest(unsigned id)
{
    struct aura_archive_manifest m={.frame_samples=320,.pre_skip=40};
    memset(m.device_id,17,16);memset(m.capture_id,(int)id,16);return m;
}
static int reset(unsigned blocks)
{
    model_destroy(&model);model_init(&model,blocks);
    int r=aura_journal_mount(&journal,model_io(&model));
    return r?r:aura_recorder_init(&recorder,&journal,arena.bytes,sizeof(arena.bytes));
}
static int start(unsigned id,uint64_t epoch,uint64_t now)
{struct aura_archive_manifest m=manifest(id);return aura_recorder_start(&recorder,&m,epoch,now);}
static int feed(const int16_t *pcm,size_t count,uint64_t now,size_t *used)
{
    struct aura_recorder_block b={recorder.epoch,recorder.next_sequence,recorder.source_samples,pcm,count};
    return aura_recorder_consume(&recorder,&b,now,used);
}
static int reopen(void){model_power_on(&model);return aura_journal_mount(&journal,model_io(&model));}

static int lifecycle(void)
{
    CHECK(!reset(4));struct aura_recorder invalid;
    CHECK(aura_recorder_init(&invalid,&journal,arena.bytes+1,sizeof(arena.bytes)-1)==AURA_RECORDER_BAD_ARGUMENT);
    CHECK(aura_recorder_init(&invalid,&journal,arena.bytes,1)==AURA_RECORDER_BAD_ARGUMENT);
    struct aura_archive_manifest timestamped=manifest(1);timestamped.time_source=1;timestamped.started_at_ms=1000;
    CHECK(aura_recorder_start(&recorder,&timestamped,1,0)==AURA_RECORDER_BAD_ARGUMENT);
    CHECK(start(1,0,0)==AURA_RECORDER_STALE_EPOCH);CHECK(!model.programs&&!model.erases);
    CHECK(!start(1,1,1000));CHECK(journal.service_clock_started&&model.programs==1&&model.erases==1);
    CHECK(start(2,2,1000)==AURA_RECORDER_STATE);size_t used;
    CHECK(!feed(synthetic,17,1001,&used)&&used==17);CHECK(journal.committed.audio_packets==0);
    CHECK(!feed(synthetic,303,1020,&used)&&used==303);CHECK(journal.committed.audio_packets==1);
    CHECK(!feed(synthetic,17,1030,&used));CHECK(recorder.source_samples==337);
    CHECK(!aura_recorder_stop(&recorder,1,337,1100));CHECK(recorder.state==AURA_RECORDER_FINALIZED);
    CHECK(recorder.seal.source_samples==337&&recorder.seal.encoded_samples==640);
    CHECK(recorder.seal.pre_skip==40&&recorder.seal.end_trim==263);
    uint64_t programs=model.programs;CHECK(!aura_recorder_stop(&recorder,1,337,1101));CHECK(programs==model.programs);
    CHECK(start(2,1,1102)==AURA_RECORDER_STALE_EPOCH);CHECK(!start(2,2,1200));
    struct aura_recorder_block stale={1,0,0,synthetic,320};used=99;
    CHECK(aura_recorder_consume(&recorder,&stale,1201,&used)==AURA_RECORDER_STALE_EPOCH&&used==0);
    CHECK(aura_recorder_stop(&recorder,1,0,1201)==AURA_RECORDER_STALE_EPOCH);
    CHECK(aura_recorder_interrupt(&recorder,1,AURA_RECORDER_OVERFLOW,1201)==AURA_RECORDER_STALE_EPOCH);
    CHECK(recorder.state==AURA_RECORDER_RECORDING&&recorder.source_samples==0);
    CHECK(!aura_recorder_stop(&recorder,2,0,1202));CHECK(recorder.seal.source_samples==0);
    CHECK(!reopen());CHECK(journal.count==2);CHECK(!aura_journal_verify(&journal,0));CHECK(!aura_journal_verify(&journal,1));
    ++groups;return 0;
}

static int start_preparation(void)
{
    CHECK(!reset(3));uint8_t bytes[2048];memset(bytes,0,2048);struct aura_nand_io io=model_io(&model);
    CHECK(!io.program(io.user,20,bytes));CHECK(!reopen());
    CHECK(start(1,1,0)==AURA_JOURNAL_RETRY_PREPARE);
    CHECK(recorder.state==AURA_RECORDER_IDLE&&recorder.last_epoch==0&&model.erases==0);
    CHECK(!start(1,1,0));CHECK(journal.current_block==1);CHECK(!aura_recorder_stop(&recorder,1,0,0));
    CHECK(start(1,2,0)==AURA_JOURNAL_CONFLICT);CHECK(recorder.state==AURA_RECORDER_FAILED);
    CHECK(!start(2,3,0));CHECK(!aura_recorder_stop(&recorder,3,0,0));
    ++groups;return 0;
}

static int startup_cancellation(void)
{
    const int reasons[]={AURA_RECORDER_SOURCE_FAILED,AURA_RECORDER_CANCELLED};
    for(unsigned n=0;n<2;++n){
        CHECK(!reset(2));CHECK(!start(1,1,0));CHECK(recorder.source_samples==0);
        CHECK(!aura_recorder_interrupt(&recorder,1,reasons[n],1));
        CHECK(recorder.state==AURA_RECORDER_INTERRUPTED&&recorder.fault_reason==reasons[n]);
        CHECK(recorder.close_error==0&&!recorder.codec.finished&&journal.active==-1);
        CHECK(!aura_recorder_interrupt(&recorder,1,reasons[n],2));
        CHECK(!reopen());CHECK(!aura_journal_verify(&journal,0));
        CHECK(journal.captures[0].verification==AURA_JOURNAL_VERIFIED_INTERRUPTED);
    }
    ++groups;return 0;
}

static int source_faults(void)
{
    for(unsigned mode=0;mode<6;++mode){
        CHECK(!reset(3));CHECK(!start(1,1,0));size_t used;
        CHECK(!feed(synthetic,320,20,&used));CHECK(!feed(synthetic,17,21,&used));
        int r;
        if(mode<2){struct aura_recorder_block b={1,mode==0?3u:0u,337,synthetic,320};
            r=aura_recorder_consume(&recorder,&b,22,&used);CHECK(r==AURA_RECORDER_GAP&&used==0);
        }else if(mode==2){struct aura_recorder_block b={1,2,338,synthetic,320};
            r=aura_recorder_consume(&recorder,&b,22,&used);CHECK(r==AURA_RECORDER_GAP&&used==0);
        }else if(mode==3){r=aura_recorder_stop(&recorder,1,657,22);CHECK(r==AURA_RECORDER_GAP);
        }else{r=aura_recorder_interrupt(&recorder,1,mode==4?AURA_RECORDER_OVERFLOW:AURA_RECORDER_SOURCE_FAILED,22);CHECK(!r);}
        CHECK(recorder.state==AURA_RECORDER_INTERRUPTED&&recorder.close_error==0);
        CHECK(recorder.archive.status==AURA_ARCHIVE_INTERRUPTED&&!recorder.codec.finished);
        CHECK(recorder.source_samples==337&&recorder.archive.encoded_samples==320);
        uint64_t programs=model.programs;CHECK(feed(synthetic,320,23,&used)==AURA_RECORDER_STATE&&used==0);
        CHECK(model.programs==programs);CHECK(!reopen());CHECK(!aura_journal_verify(&journal,0));
        CHECK(journal.captures[0].verification==AURA_JOURNAL_VERIFIED_INTERRUPTED);
    }
    CHECK(!reset(2));CHECK(!start(1,1,0));size_t used;
    CHECK(!feed(synthetic,320,20,&used));CHECK(!feed(synthetic,320,21,&used));
    CHECK(journal.committed.audio_packets==1);CHECK(!aura_recorder_service(&recorder,420));
    CHECK(journal.committed.audio_packets==1);CHECK(!aura_recorder_service(&recorder,421));
    CHECK(journal.committed.audio_packets==2);CHECK(!aura_recorder_interrupt(&recorder,1,AURA_RECORDER_SOURCE_FAILED,422));
    ++groups;return 0;
}

static int partial_consumption(void)
{
    CHECK(!reset(3));CHECK(!start(1,1,0));size_t used;
    CHECK(!feed(synthetic,318,0,&used)&&used==318);
    CHECK(!feed(synthetic,320,0,&used)&&used==320);CHECK(journal.committed.audio_packets==1);
    model.program_failure[0]=1;int r=0;unsigned blocks=0;uint64_t before=0;
    while(!r&&blocks++<100){before=recorder.source_samples;r=feed(synthetic,320,0,&used);}
    CHECK(r==AURA_NAND_PROGRAM_FAILED&&blocks<100);CHECK(used==2&&recorder.source_samples==before+2);
    CHECK(recorder.state==AURA_RECORDER_FAILED&&recorder.fault_reason==r&&recorder.close_error==r);
    uint64_t programs=model.programs,samples=recorder.source_samples;
    CHECK(feed(synthetic,320,0,&used)==AURA_RECORDER_STATE&&used==0);
    CHECK(model.programs==programs&&recorder.source_samples==samples);
    CHECK(!reopen());CHECK(!aura_journal_verify(&journal,0));
    CHECK(journal.captures[0].verification==AURA_JOURNAL_VERIFIED_OPEN);
    CHECK(journal.captures[0].committed_wire_bytes>68);
    ++groups;return 0;
}

struct sink{FILE *file;uint64_t bytes;};
static int output(void *user,uint64_t offset,const uint8_t *wire,size_t bytes)
{struct sink *s=user;if(offset!=s->bytes||fwrite(wire,1,bytes,s->file)!=bytes)return -900;s->bytes+=bytes;return 0;}
static int fixture(const char *input_path,const char *prefix,unsigned mode)
{
    FILE *f=fopen(input_path,"rb");CHECK(f);CHECK(!fseek(f,0,SEEK_END));long bytes=ftell(f);rewind(f);
    CHECK(bytes>0&&bytes<2000000&&bytes%2==0);int16_t *pcm=malloc((size_t)bytes);CHECK(pcm);
    CHECK(fread(pcm,1,(size_t)bytes,f)==(size_t)bytes);fclose(f);
    CHECK(!reset(8));CHECK(!start(40+mode,1,0));size_t samples=mode?48017:(size_t)bytes/2,at=0;
    const size_t chunks[]={17,320,83,219,303,1};unsigned chunk=0;
    while(at<samples){size_t take=chunks[chunk++%6];if(take>samples-at)take=samples-at;
        size_t used;CHECK(!feed(pcm+at,take,at/16,&used));CHECK(used==take);at+=used;
    }
    uint64_t now=(at+15)/16;int r;
    if(mode==0){CHECK(!aura_recorder_stop(&recorder,1,at,now));CHECK(recorder.state==AURA_RECORDER_FINALIZED);}
    if(mode==1){CHECK(!aura_recorder_interrupt(&recorder,1,AURA_RECORDER_OVERFLOW,now));}
    if(mode==2){struct aura_recorder_block b={1,recorder.next_sequence+1,at+320,pcm,320};size_t used=99;
        CHECK(aura_recorder_consume(&recorder,&b,now,&used)==AURA_RECORDER_GAP&&used==0);}
    if(mode==3){CHECK(journal.staged_bytes>0);model.cut_program=model.programs+1;model.cut=MODEL_CUT_PARTIAL;model.cut_bytes=700;
        r=aura_recorder_interrupt(&recorder,1,AURA_RECORDER_SOURCE_FAILED,now);CHECK(r==AURA_NAND_UNCERTAIN);
        CHECK(recorder.fault_reason==AURA_RECORDER_SOURCE_FAILED&&recorder.close_error==AURA_NAND_UNCERTAIN);}
    if(mode==4){CHECK(aura_recorder_stop(&recorder,1,at+320,now)==AURA_RECORDER_GAP);}
    CHECK(!reopen());CHECK(!aura_journal_verify(&journal,0));
    char name[1024];CHECK(snprintf(name,sizeof(name),"%s-%u.aura",prefix,mode)>0);
    struct sink s={.file=fopen(name,"wb")};CHECK(s.file);CHECK(!aura_journal_export(&journal,0,output,&s));CHECK(!fclose(s.file));
    uint8_t ack[94];CHECK(!aura_journal_receipt(&journal,0,ack));CHECK(snprintf(name,sizeof(name),"%s-%u.receipt",prefix,mode)>0);
    f=fopen(name,"wb");CHECK(f&&fwrite(ack,1,94,f)==94&&!fclose(f));
    printf("PASS real_recorder mode=%u accepted_source_samples=%llu wire_bytes=%llu state=%u reason=%d close_error=%d\n",
        mode,(unsigned long long)recorder.source_samples,(unsigned long long)s.bytes,recorder.state,recorder.fault_reason,recorder.close_error);
    free(pcm);++groups;return 0;
}
int main(int argc,char **argv)
{
    CHECK(argc==3);for(unsigned n=0;n<320;++n)synthetic[n]=(int16_t)((int)(n%80)*250-10000);
    CHECK(!lifecycle());CHECK(!start_preparation());CHECK(!startup_cancellation());CHECK(!source_faults());CHECK(!partial_consumption());
    for(unsigned mode=0;mode<5;++mode)CHECK(!fixture(argv[1],argv[2],mode));
    printf("PASS recorder groups=%u recorder_context=%u external_encoder_arena=%u\n",groups,(unsigned)sizeof(recorder),(unsigned)sizeof(arena));
    model_destroy(&model);return 0;
}
