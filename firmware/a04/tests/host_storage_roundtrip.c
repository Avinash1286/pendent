/* SPDX-License-Identifier: MIT */
/* Real encoder/recorder -> owned journal -> Python durable receiver/outbox ->
 * authenticated C release. NAND, known test enrollment, synthetic speech and
 * logical timing are host substitutes; PDM/Zephyr/BLE do not run here. */
#include "aura_storage.h"
#include "aura_recorder.h"
#include "nand_model.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static struct nand_model medium;
static struct aura_storage storage;
static struct aura_journal journal;
static struct aura_control control;
static struct aura_recorder recorder;
static struct aura_release_auth_context authority;
static struct aura_control_config config = {.blocks={6,7}};
static uint8_t snapshot[AURA_STORAGE_STATE_BYTES];
static union { max_align_t alignment; uint8_t bytes[AURA_OPUS_STATE_LIMIT]; } encoder;
static unsigned erased;

static int erase_control(void *user,uint32_t block)
{
    assert(block==6||block==7);
    struct aura_nand_io io=model_io(user);return io.erase(user,block);
}
static struct aura_control_io ledger_io(void)
{return (struct aura_control_io){model_io(&medium),&medium,erase_control};}
static int erase_released(void *user,uint32_t block)
{
    assert(block<6);
    struct aura_control audit;uint8_t bytes[AURA_STORAGE_HEADER_BYTES+6*AURA_STORAGE_EXTENT_BYTES];
    size_t size=0;assert(!aura_control_open(&audit,ledger_io(),&config));
    assert(!aura_control_load(&audit,bytes,sizeof(bytes),&size));
    assert(size>=352&&bytes[5]==1);bool fenced=false;
    unsigned count=bytes[262]|(unsigned)bytes[263]<<8;
    for(unsigned i=0;i<count;++i){unsigned at=352+i*44;
        if((bytes[at]|(unsigned)bytes[at+1]<<8)==block)fenced=true;}
    assert(fenced);++erased;
    struct aura_nand_io io=model_io(user);return io.erase(user,block);
}
static struct aura_storage_io io(void)
{return (struct aura_storage_io){model_io(&medium),ledger_io(),&medium,erase_released};}
static void reopen(void)
{
    model_power_on(&medium);
    assert(!aura_storage_open(&storage,io(),&config,&authority,&journal,&control,snapshot,sizeof(snapshot)));
}
struct sink { FILE *file; uint64_t offset; };
static int output(void *user,uint64_t offset,const uint8_t *bytes,size_t size)
{
    struct sink *sink=user;
    if(offset!=sink->offset||fwrite(bytes,1,size,sink->file)!=size)return -900;
    sink->offset+=size;return 0;
}
static int find(const uint8_t receipt[94])
{
    for(unsigned i=0;i<journal.count;++i)
        if(!memcmp(journal.captures[i].manifest+8,receipt+6,32))return (int)i;
    return -1;
}
static void export_capture(const char *prefix,const char *label,const uint8_t receipt[94])
{
    int index=find(receipt);assert(index>=0);uint8_t actual[94];
    assert(!aura_journal_verify(&journal,(uint16_t)index));
    int result=aura_journal_receipt(&journal,(uint16_t)index,actual);
    if(result||memcmp(actual,receipt,94)){
        fprintf(stderr,"receipt mismatch label=%s index=%d verify=%d\n",label,index,result);
        if(!result)for(unsigned i=0;i<94;++i)if(actual[i]!=receipt[i])
            fprintf(stderr,"byte %u actual=%u expected=%u\n",i,actual[i],receipt[i]);
        abort();
    }
    char path[2048];int n=snprintf(path,sizeof(path),"%s-%s.aura",prefix,label);
    assert(n>0&&(size_t)n<sizeof(path));struct sink sink={.file=fopen(path,"wb")};assert(sink.file);
    assert(!aura_journal_export(&journal,(uint16_t)index,output,&sink));assert(!fclose(sink.file));
    n=snprintf(path,sizeof(path),"%s-%s.receipt",prefix,label);assert(n>0&&(size_t)n<sizeof(path));
    FILE *file=fopen(path,"wb");assert(file&&fwrite(receipt,1,94,file)==94&&!fclose(file));
}
static void record(const int16_t *pcm,size_t samples,uint64_t epoch,uint8_t receipt[94])
{
    struct aura_archive_manifest settings={.frame_samples=320,.pre_skip=40},manifest;
    assert(!aura_storage_prepare_capture(&storage,&settings,&manifest));
    assert(!aura_recorder_init(&recorder,&journal,encoder.bytes,sizeof(encoder.bytes)));
    assert(!aura_recorder_start(&recorder,&manifest,epoch,0));
    size_t offset=0;
    while(offset<samples){size_t size=samples-offset;if(size>320)size=320;size_t used=0;
        struct aura_recorder_block block={epoch,recorder.next_sequence,offset,pcm+offset,size};
        assert(!aura_recorder_consume(&recorder,&block,offset/16,&used)&&used==size);offset+=used;
    }
    assert(!aura_recorder_stop(&recorder,epoch,samples,(samples+15)/16));
    assert(!aura_journal_receipt(&journal,journal.count-1,receipt));
}
int main(int argc,char **argv)
{
    assert(argc==3);FILE *file=fopen(argv[1],"rb");assert(file);
    assert(!fseek(file,0,SEEK_END));long size=ftell(file);rewind(file);
    assert(size>0&&size<2000000&&size%2==0);int16_t *pcm=malloc((size_t)size);assert(pcm);
    assert(fread(pcm,1,(size_t)size,file)==(size_t)size&&!fclose(file));
    model_init(&medium,8);memset(authority.device_id,0x11,16);
    memset(authority.storage_incarnation,0x33,16);memset(authority.owner_id,0x44,16);
    authority.owner_generation=1;for(unsigned i=0;i<32;++i)authority.key[i]=(uint8_t)(i+1);
    memcpy(config.domain,authority.storage_incarnation,16);
    assert(!aura_storage_provision(&storage,io(),&config,&authority,&journal,&control,snapshot,sizeof(snapshot)));
    uint8_t keep[94],release[94],replacement[94];
    record(pcm,(size_t)size/2,1,keep);reopen();record(pcm,(size_t)size/2,2,release);reopen();
    int release_index=find(release);assert(release_index>=0);
    assert(journal.captures[release_index].blocks==1);
    uint16_t released_block=journal.captures[release_index].first_block;
    export_capture(argv[2],"retained",keep);export_capture(argv[2],"release",release);
    puts("READY durable receiver authorization required");fflush(stdout);
    char line[368];assert(fgets(line,sizeof(line),stdin)&&strlen(line)==365&&line[364]=='\n');
    uint8_t command[182];
    for(unsigned i=0;i<182;++i){char byte[3]={line[i*2],line[i*2+1],0};char *end=NULL;
        unsigned long value=strtoul(byte,&end,16);assert(end==byte+2&&value<=255);command[i]=(uint8_t)value;}
    assert(aura_storage_request_release(&storage,command,182)==AURA_STORAGE_PENDING&&erased==0);
    reopen();assert(find(release)<0&&find(keep)>=0);
    int result=AURA_STORAGE_PENDING;unsigned steps=0;
    while(result==AURA_STORAGE_PENDING&&steps++<6)result=aura_storage_release_step(&storage);
    assert(result==AURA_STORAGE_ALREADY_DONE&&erased>0);reopen();
    assert(aura_storage_request_release(&storage,command,182)==AURA_STORAGE_ALREADY_DONE);
    export_capture(argv[2],"retained-after",keep);
    record(pcm,(size_t)size/2,3,replacement);reopen();
    assert(memcmp(replacement+22,release+22,16)&&memcmp(replacement+22,keep+22,16));
    int replacement_index=find(replacement);
    assert(journal.count==2&&find(release)<0&&find(keep)>=0&&replacement_index>=0);
    assert(journal.captures[replacement_index].first_block==released_block);
    export_capture(argv[2],"retained-after-reuse",keep);
    export_capture(argv[2],"replacement",replacement);
    printf("PASS real storage roundtrip samples=%lu erased_blocks=%u reused_block=%u retained_catalog=%u\n",
           (unsigned long)size/2,erased,released_block,journal.count);
    free(pcm);model_destroy(&medium);return 0;
}
