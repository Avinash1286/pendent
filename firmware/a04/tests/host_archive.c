/* SPDX-License-Identifier: MIT */
#include "aura_archive.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <io.h>
#else
#include <unistd.h>
#endif
#define CHECK(x) do { if(!(x)){fprintf(stderr,"FAIL archive line %d: %s\n",__LINE__,#x);return 1;} } while(0)

struct file_sink {
    FILE *file;
    unsigned failures[5];
    uint8_t pending[AURA_ARCHIVE_RECORD_BYTES];
    size_t pending_bytes;
    uint64_t pending_offset;
    unsigned retries;
};
static int durable_file(void *user,uint64_t offset,const uint8_t *wire,size_t bytes)
{
    struct file_sink *s=user;
    if(offset>0x7fffffff||fseek(s->file,(long)offset,SEEK_SET))return -102;
    if(s->pending_bytes){
        if(s->pending_bytes!=bytes||s->pending_offset!=offset||memcmp(s->pending,wire,bytes))return -103;
        ++s->retries;
    }
    unsigned kind=!memcmp(wire,"AUR3",4)?3:!memcmp(wire,"ASE3",4)?4:wire[5];
    if(s->failures[kind]){
        --s->failures[kind];memcpy(s->pending,wire,bytes);s->pending_bytes=bytes;s->pending_offset=offset;
        /* An uncertain partial write: exact same offset/data must be retried. */
        if(fwrite(wire,1,bytes/2,s->file)!=bytes/2||fflush(s->file))return -104;
        return -100;
    }
    if(fwrite(wire,1,bytes,s->file)!=bytes||fflush(s->file))return -105;
#ifdef _WIN32
    if(_commit(_fileno(s->file)))return -106;
#else
    if(fsync(fileno(s->file)))return -106;
#endif
    s->pending_bytes=0;
    return 0;
}
static int fixture(const char *input_path,const char *prefix,unsigned ms,unsigned ending)
{
    FILE *input=fopen(input_path,"rb");CHECK(input);
    CHECK(!fseek(input,0,SEEK_END));long bytes=ftell(input);CHECK(bytes>0&&bytes%2==0&&bytes<2000000);rewind(input);
    int16_t *pcm=malloc((size_t)bytes);CHECK(pcm&&fread(pcm,1,(size_t)bytes,input)==(size_t)bytes);fclose(input);
    char name[1024];const char *suffix=ending==1?"":ending==2?"-interrupted":"-open";
    CHECK(snprintf(name,sizeof(name),"%s-%ums%s.aura",prefix,ms,suffix)>0);
    struct file_sink sink={.file=fopen(name,"w+b"),.failures={0,2,1,1,1}};CHECK(sink.file);
    struct aura_archive_writer writer;
    struct aura_opus_capture capture;
    void *state=malloc(aura_opus_state_bytes());CHECK(state);
    CHECK(aura_opus_init(&capture,state,aura_opus_state_bytes(),ms,aura_archive_opus_commit,&writer)==0);
    struct aura_archive_manifest manifest={.frame_samples=(uint16_t)(ms*16),.pre_skip=capture.lookahead};
    memset(manifest.device_id,0x11,16);memset(manifest.capture_id,(int)(ms+ending*32),16);
    int result=aura_archive_begin(&writer,&manifest,durable_file,&sink);
    CHECK(result==-100&&!writer.begun&&writer.file_offset==0);
    CHECK(aura_archive_retry(&writer)==0&&writer.begun);
    uint8_t ack[94];CHECK(aura_archive_receipt(&writer,ack)==0);
    size_t samples=(size_t)bytes/2,offset=0;
    while(offset<samples){
        size_t chunk=manifest.frame_samples;if(chunk>samples-offset)chunk=samples-offset;
        size_t consumed=0;result=aura_opus_push(&capture,pcm+offset,chunk,&consumed);offset+=consumed;
        if(result==-100)CHECK(aura_archive_retry(&writer)==AURA_ARCHIVE_BUSY);
        while(result==-100)result=aura_opus_retry(&capture);
        CHECK(result==0&&consumed==chunk);
        if(offset==8000||offset==32000){
            result=aura_archive_bookmark(&writer,offset);
            while(result==-100)result=aura_archive_retry(&writer);
            CHECK(result==0);
        }
    }
    struct aura_opus_seal seal={0};
    if(ending==1){
        result=aura_opus_finish(&capture,&seal);
        while(result==-100)result=aura_opus_finish(&capture,&seal);
        CHECK(result==0);
        result=aura_archive_finalize(&writer,&seal);
        while(result==-100)result=aura_archive_retry(&writer);
        CHECK(result==0&&writer.status==AURA_ARCHIVE_FINALIZED);
        CHECK(aura_archive_finalize(&writer,&seal)==0);
        struct aura_opus_seal bad=seal;--bad.source_samples;++bad.end_trim;
        CHECK(aura_archive_finalize(&writer,&bad)==AURA_ARCHIVE_CONFLICT);
    }else if(ending==2){
        /* Preserve a bookmark in the last 40 source samples lost to lookahead. */
        CHECK(aura_archive_bookmark(&writer,writer.encoded_samples)==0);
        result=aura_archive_interrupt(&writer);
        while(result==-100)result=aura_archive_retry(&writer);
        CHECK(result==0&&writer.status==AURA_ARCHIVE_INTERRUPTED);
    }
    CHECK(aura_archive_receipt(&writer,ack)==0);
    CHECK(fclose(sink.file)==0);
    CHECK(snprintf(name,sizeof(name),"%s-%ums%s.receipt",prefix,ms,suffix)>0);
    FILE *receipt=fopen(name,"wb");CHECK(receipt&&fwrite(ack,1,94,receipt)==94&&fclose(receipt)==0);
    printf("PASS archive %ums status=%u packets=%u audio=%u bytes=%llu samples=%llu retries=%u writer_context=%u\n",
        ms,ending,writer.next_sequence,writer.audio_packets,(unsigned long long)writer.encoded_bytes,
        (unsigned long long)writer.encoded_samples,sink.retries,(unsigned)sizeof(writer));
    free(pcm);free(state);return 0;
}
int main(int argc,char **argv)
{
    static const uint8_t abc[32]={0xba,0x78,0x16,0xbf,0x8f,0x01,0xcf,0xea,0x41,0x41,0x40,0xde,0x5d,0xae,0x22,0x23,
        0xb0,0x03,0x61,0xa3,0x96,0x17,0x7a,0x9c,0xb4,0x10,0xff,0x61,0xf2,0x00,0x15,0xad};
    uint8_t hash[32];aura_archive_sha256((const uint8_t*)"abc",3,hash);CHECK(!memcmp(hash,abc,32));
    CHECK(argc==3);
    return fixture(argv[1],argv[2],10,1)||fixture(argv[1],argv[2],20,1)||
        fixture(argv[1],argv[2],20,2)||fixture(argv[1],argv[2],20,0);
}
