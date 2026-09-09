/* SPDX-License-Identifier: MIT */
/* Real serialized journal/cursor and host NAND model, never a GATT or phone test. */
#include "aura_transfer.h"
#include "aura_storage.h"
#include "nand_model.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static struct nand_model medium;
static struct aura_journal journal;
static struct aura_transfer transfer;
static struct aura_archive_writer writer;
static const uint8_t device[16]={17,17,17,17,17,17,17,17,17,17,17,17,17,17,17,17};
static const uint8_t incarnation[16]={0xA4,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16};
static uint8_t capture_id[16],receipt[94],expected[200000],input[200000];
static size_t expected_bytes,physical_bytes;
static uint64_t session,delivery,step_calls,noio_calls;
static uint32_t revision,handle;
static unsigned checks,cases,max_reads;
static const char *case_name;
static FILE *golden;
static const char *final_fixture,*open_fixture,*fixture_output;
#define CHECK(x) do{++checks;if(!(x)){fprintf(stderr,"FAIL transfer %s line=%d: %s\n",case_name,__LINE__,#x);exit(1);}}while(0)
#define START(x) do{case_name=(x);}while(0)
#define PASS() do{++cases;printf("CASE %s PASS\n",case_name);}while(0)
static uint64_t get(const uint8_t *p,unsigned n)
{uint64_t v=0;for(unsigned i=0;i<n;++i)v|=(uint64_t)p[i]<<(8*i);return v;}
static void put(uint8_t *p,uint64_t v,unsigned n)
{for(unsigned i=0;i<n;++i)p[i]=(uint8_t)(v>>(8*i));}
static void fix_crc(uint8_t *p,size_t bytes)
{put(p+bytes-4,aura_archive_crc32(p,bytes-4),4);}
struct counters{uint64_t reads,programs,erases;};
static struct counters before(void)
{return (struct counters){medium.reads,medium.programs,medium.erases};}
static void after(struct counters b,bool bounded_step)
{
    CHECK(medium.programs==b.programs&&medium.erases==b.erases);
    uint64_t reads=medium.reads-b.reads;CHECK(reads<=(bounded_step?1u:0u));
    if(bounded_step){++step_calls;if(reads>max_reads)max_reads=(unsigned)reads;}else ++noio_calls;
}
static int submit_at(uint64_t generation,const uint8_t *command,size_t bytes)
{struct counters b=before();int r=aura_transfer_submit(&transfer,generation,command,bytes);after(b,false);return r;}
static int submit(const uint8_t *command,size_t bytes)
{return submit_at(session,command,bytes);}
static int step_at(uint64_t generation)
{struct counters b=before();int r=aura_transfer_step(&transfer,generation);after(b,true);return r;}
static int copy_at(uint64_t generation,uint8_t *out,size_t capacity,size_t *bytes)
{struct counters b=before();uint64_t token=0;int r=aura_transfer_copy_response(&transfer,generation,out,capacity,bytes,&token);after(b,false);if(!r){CHECK(token!=0);delivery=token;}return r;}
static int fragment_token_at(uint64_t generation,uint16_t txn,uint64_t token,uint16_t mtu,uint16_t offset,uint8_t *out,size_t cap,size_t *bytes)
{struct counters b=before();int r=aura_transfer_copy_fragment(&transfer,generation,txn,token,mtu,offset,out,cap,bytes);after(b,false);return r;}
static int fragment_at(uint64_t generation,uint16_t txn,uint16_t mtu,uint16_t offset,uint8_t *out,size_t cap,size_t *bytes)
{return fragment_token_at(generation,txn,delivery,mtu,offset,out,cap,bytes);}
static int sent_token_at(uint64_t generation,uint16_t txn,uint64_t token)
{struct counters b=before();int r=aura_transfer_response_sent(&transfer,generation,txn,token);after(b,false);return r;}
static int sent_at(uint64_t generation,uint16_t txn)
{return sent_token_at(generation,txn,delivery);}
static int session_begin(bool authorized,uint64_t *generation)
{struct counters b=before();int r=aura_transfer_session_begin(&transfer,authorized,generation);after(b,false);return r;}
static int session_end(uint64_t generation)
{struct counters b=before();int r=aura_transfer_session_end(&transfer,generation);after(b,false);return r;}
static int cancel_work(uint64_t generation)
{struct counters b=before();int r=aura_transfer_cancel_work(&transfer,generation);after(b,false);return r;}
static size_t command(uint8_t *out,unsigned op,uint16_t txn,uint64_t value,uint64_t offset,unsigned requested)
{
    memset(out,0,20);out[0]=1;out[1]=(uint8_t)op;put(out+2,txn,2);
    switch(op){
    case AURA_TRANSFER_HELLO:return 4;
    case AURA_TRANSFER_LIST:put(out+4,value,4);put(out+8,offset,2);return 10;
    case AURA_TRANSFER_SELECT:memcpy(out+4,capture_id,16);return 20;
    case AURA_TRANSFER_READ:put(out+4,value,4);put(out+8,offset,8);put(out+16,requested,2);return 18;
    case AURA_TRANSFER_FINISH:put(out+4,value,4);put(out+8,offset,8);return 16;
    case AURA_TRANSFER_CANCEL:put(out+4,value,4);return 8;
    default:CHECK(false);return 0;
    }
}
static void response_header(uint8_t *out,unsigned status,unsigned op,uint16_t txn)
{out[0]=(uint8_t)status;out[1]=(uint8_t)op;put(out+2,txn,2);}
static size_t completed(uint8_t out[512])
{
    int result;unsigned calls=0;
    do{CHECK(++calls<3000);result=step_at(session);}while(result==AURA_TRANSFER_WAIT);
    CHECK(result==AURA_TRANSFER_RESPONSE);size_t bytes=0;
    CHECK(!copy_at(session,out,512,&bytes));CHECK(bytes>=4&&bytes<=512);return bytes;
}
static size_t exchange(const uint8_t *cmd,size_t command_bytes,uint8_t out[512])
{CHECK(submit(cmd,command_bytes)==AURA_TRANSFER_ACCEPTED);return completed(out);}
static void golden_row(const char *name,const char *kind,const uint8_t *data,size_t bytes)
{
    if(!golden)return;CHECK(fprintf(golden,"%s\t%s\t",name,kind)>0);
    for(size_t n=0;n<bytes;++n)CHECK(fprintf(golden,"%02x",data[n])==2);CHECK(fputc('\n',golden)!=EOF);
}
static void golden_pair(const char *name,const uint8_t *cmd,size_t cmdbytes,const uint8_t *response,size_t bytes)
{golden_row(name,"command",cmd,cmdbytes);golden_row(name,"response",response,bytes);}
static int collect(void *user,uint64_t offset,const uint8_t *wire,size_t bytes)
{
    (void)user;if(offset!=expected_bytes||bytes>sizeof(expected)-expected_bytes)return -901;
    memcpy(expected+expected_bytes,wire,bytes);expected_bytes+=bytes;return 0;
}
static int manifest_copy(void *user,uint64_t offset,const uint8_t *wire,size_t bytes)
{if(offset||bytes!=68)return -902;memcpy(user,wire,bytes);return 0;}
static void reset(void)
{
    model_destroy(&medium);model_init(&medium,6);CHECK(!aura_journal_mount(&journal,model_io(&medium)));
    expected_bytes=0;physical_bytes=0;handle=revision=0;
}
static void start_capture(bool owned,unsigned identity_kind,uint64_t generation,const uint8_t *source)
{
    uint8_t owner_device[16],owner_incarnation[16];memcpy(owner_device,device,16);memcpy(owner_incarnation,incarnation,16);
    if(identity_kind==1)owner_device[0]^=1;if(identity_kind==2)owner_incarnation[0]^=1;
    CHECK(!aura_storage_capture_id(owner_device,owner_incarnation,generation,capture_id));
    if(identity_kind==3)capture_id[0]^=1;
    struct aura_archive_manifest m={.frame_samples=320,.pre_skip=40};
    if(source){m.frame_samples=(uint16_t)get(source+44,2);m.pre_skip=(uint16_t)get(source+46,2);
        m.started_at_ms=get(source+56,8);m.time_source=source[54];}
    memcpy(m.device_id,owner_device,16);memcpy(m.capture_id,capture_id,16);
    if(owned){uint8_t wire[68];struct aura_archive_writer draft;
        CHECK(!aura_journal_set_owned_profile(&journal,owner_incarnation));
        CHECK(!aura_archive_begin_staged(&draft,&m,manifest_copy,wire));CHECK(!aura_journal_bind_capture(&journal,wire,generation));}
    CHECK(!aura_journal_service(&journal,0));CHECK(!aura_archive_begin_staged(&writer,&m,aura_journal_stage,&journal));
}
static void remount_and_reference(void)
{
    model_power_on(&medium);CHECK(!aura_journal_mount(&journal,model_io(&medium)));CHECK(journal.count==1&&journal.active==-1);
    CHECK(!aura_journal_export(&journal,0,collect,NULL));CHECK(!aura_journal_receipt(&journal,0,receipt));
    physical_bytes=(size_t)journal.captures[0].committed_wire_bytes;
    CHECK(!aura_journal_set_owned_profile(&journal,incarnation));
}
static void quick_fixture(bool opened,bool owned,unsigned identity_kind)
{
    reset();start_capture(owned,identity_kind,42,NULL);
    for(unsigned n=0;n<3;++n){struct aura_opus_packet p={.sequence=n,.sample_offset=320u*n,.sample_count=320,.bytes=80};
        memset(p.data,0x33,p.bytes);p.data[0]=0x98;CHECK(!aura_archive_opus_commit(&writer,&p));}
    CHECK(!aura_archive_bookmark(&writer,160));
    if(opened)CHECK(!aura_journal_flush(&journal));
    else{struct aura_opus_seal seal={.source_samples=903,.encoded_samples=960,.packets=3,.pre_skip=40,.end_trim=17};
        CHECK(!aura_archive_finalize(&writer,&seal));}
    remount_and_reference();
}
static void real_fixture(bool opened)
{
    FILE *file=fopen(opened?open_fixture:final_fixture,"rb");CHECK(file);
    size_t bytes=fread(input,1,sizeof(input),file);CHECK(!ferror(file)&&fgetc(file)==EOF);CHECK(!fclose(file));
    CHECK(bytes>188&&!memcmp(input,"AUR3",4));reset();start_capture(true,0,opened?43:42,input);
    size_t offset=68;unsigned packets=0;
    while(offset<bytes){const uint8_t *record=input+offset;
        if(!memcmp(record,"AFR3",4)){size_t payload=(size_t)get(record+20,2);CHECK(payload<=1275&&offset+26+payload<=bytes);
            if(record[5]==1){struct aura_opus_packet p={.sequence=writer.audio_packets,.sample_offset=get(record+10,8),
                .sample_count=(uint16_t)get(record+18,2),.bytes=(uint16_t)payload};
                memcpy(p.data,record+22,payload);CHECK(!aura_archive_opus_commit(&writer,&p));++packets;
            }else{CHECK(record[5]==2);CHECK(!aura_archive_bookmark(&writer,get(record+10,8)));}
            offset+=26+payload;
        }else{CHECK(bytes-offset==120&&!memcmp(record,"ASE3",4));
            if(!opened){CHECK(record[5]==AURA_ARCHIVE_FINALIZED);struct aura_opus_seal seal={
                .packets=(uint32_t)get(record+44,4),.encoded_samples=get(record+56,8),.source_samples=get(record+64,8),
                .pre_skip=(uint16_t)get(record+80,2),.end_trim=(uint16_t)get(record+82,2)};
                CHECK(!aura_archive_finalize(&writer,&seal));}
            offset+=120;
        }
    }
    CHECK(offset==bytes&&packets>0);CHECK(!aura_journal_flush(&journal));remount_and_reference();CHECK(expected_bytes==bytes);
    /* Independently compare every original audio/bookmark record: only manifest
     * identity and seal digest change when binding this fixture to our owner. */
    offset=68;while(offset<bytes-120){size_t recordbytes=26+(size_t)get(input+offset+20,2);
        CHECK(!memcmp(input+offset,expected+offset,recordbytes));offset+=recordbytes;}
}
static void connect_authorized(void)
{
    struct counters b=before();CHECK(!aura_transfer_init(&transfer,&journal,device,incarnation));after(b,false);
    CHECK(!session_begin(true,&session));CHECK(session!=0);
}
static void hello(uint16_t txn,const char *name)
{
    uint8_t cmd[20],out[512],want[46]={0};size_t cmdbytes=command(cmd,AURA_TRANSFER_HELLO,txn,0,0,0);
    size_t bytes=exchange(cmd,cmdbytes,out);CHECK(bytes==46);revision=(uint32_t)get(out+36,4);CHECK(revision!=0);
    response_header(want,0,AURA_TRANSFER_HELLO,txn);memcpy(want+4,device,16);memcpy(want+20,incarnation,16);
    put(want+36,revision,4);put(want+40,journal.count,2);put(want+42,512,2);put(want+44,256,2);
    CHECK(!memcmp(out,want,sizeof(want)));if(name)golden_pair(name,cmd,cmdbytes,out,bytes);CHECK(!sent_at(session,txn));
}
static void select_capture(uint16_t txn,bool opened,const char *name)
{
    uint8_t cmd[20],out[512],want[195]={0};size_t cmdbytes=command(cmd,AURA_TRANSFER_SELECT,txn,0,0,0);
    uint64_t reads=medium.reads;size_t bytes=exchange(cmd,cmdbytes,out);CHECK(bytes==195);CHECK(medium.reads-reads>=62);
    handle=(uint32_t)get(out+4,4);CHECK(handle!=0);response_header(want,0,AURA_TRANSFER_SELECT,txn);put(want+4,handle,4);
    memcpy(want+8,expected,68);memcpy(want+76,receipt,94);put(want+170,physical_bytes,8);put(want+178,expected_bytes,8);
    want[186]=opened?1:0;put(want+187,opened&&expected_bytes>1000?43:42,8);
    CHECK(!memcmp(out,want,sizeof(want)));if(name)golden_pair(name,cmd,cmdbytes,out,bytes);CHECK(!sent_at(session,txn));
}
static void error_reply(const uint8_t *cmd,size_t cmdbytes,unsigned status)
{
    uint8_t out[512],want[4];size_t bytes=exchange(cmd,cmdbytes,out);response_header(want,status,cmd[1],(uint16_t)get(cmd+2,2));
    CHECK(bytes==4&&!memcmp(out,want,4));CHECK(!sent_at(session,(uint16_t)get(cmd+2,2)));
}
static size_t read_response(uint16_t txn,uint64_t offset,unsigned requested,const char *name)
{
    uint8_t cmd[20],out[512],want[278]={0};size_t cmdbytes=command(cmd,AURA_TRANSFER_READ,txn,handle,offset,requested);
    size_t bytes=exchange(cmd,cmdbytes,out);CHECK(bytes>=22&&bytes<=22+requested);size_t count=(size_t)get(out+16,2);
    CHECK(count<=requested&&count<=256&&bytes==22+count&&offset+count<=expected_bytes);
    if(!count)CHECK(offset==expected_bytes);
    response_header(want,0,AURA_TRANSFER_READ,txn);put(want+4,handle,4);put(want+8,offset,8);put(want+16,count,2);
    memcpy(want+18,expected+offset,count);put(want+18+count,aura_archive_crc32(expected+offset,count),4);
    CHECK(!memcmp(out,want,bytes));if(name)golden_pair(name,cmd,cmdbytes,out,bytes);CHECK(!sent_at(session,txn));return count;
}
static void finish_response(uint16_t txn,bool opened,const char *name)
{
    uint8_t cmd[20],out[512],want[119]={0};size_t cmdbytes=command(cmd,AURA_TRANSFER_FINISH,txn,handle,expected_bytes,0);
    size_t bytes=exchange(cmd,cmdbytes,out);response_header(want,0,AURA_TRANSFER_FINISH,txn);put(want+4,handle,4);
    memcpy(want+8,receipt,94);put(want+102,expected_bytes,8);want[110]=opened?1:0;put(want+111,opened&&expected_bytes>1000?43:42,8);
    CHECK(bytes==sizeof(want)&&!memcmp(out,want,bytes));if(name)golden_pair(name,cmd,cmdbytes,out,bytes);CHECK(!sent_at(session,txn));
}
static void fragments(uint16_t txn,const char *prefix)
{
    uint8_t logical[512],assembled[512],part[514],saved[514];size_t logical_bytes=0;
    CHECK(!copy_at(session,logical,sizeof(logical),&logical_bytes));
    const uint16_t mtus[]={23,517};
    for(unsigned m=0;m<2;++m){
        size_t offset=0;memset(assembled,0,sizeof(assembled));
        while(offset<logical_bytes){
            size_t bytes=0;CHECK(!fragment_at(session,txn,mtus[m],(uint16_t)offset,part,sizeof(part),&bytes));
            size_t count=logical_bytes-offset;if(count>mtus[m]-11u)count=mtus[m]-11u;
            CHECK(bytes==8+count&&bytes<=mtus[m]-3u);CHECK(part[0]==1&&part[1]==0);
            CHECK(get(part+2,2)==txn&&get(part+4,2)==offset&&get(part+6,2)==logical_bytes);
            CHECK(!memcmp(part+8,logical+offset,count));memcpy(saved,part,bytes);memcpy(assembled+offset,part+8,count);
            memset(journal.scratch,0xAD,sizeof(journal.scratch));size_t repeat=0;
            CHECK(!fragment_at(session,txn,mtus[m],(uint16_t)offset,part,sizeof(part),&repeat));
            CHECK(repeat==bytes&&!memcmp(part,saved,bytes));
            if(prefix)golden_row(prefix,mtus[m]==23?"fragment23":"fragment517",part,bytes);
            offset+=count;
        }
        CHECK(!memcmp(logical,assembled,logical_bytes));
    }
    size_t bytes;CHECK(fragment_at(session,txn,22,0,part,sizeof(part),&bytes)==AURA_TRANSFER_INVALID&&bytes==0);
    CHECK(fragment_at(session,txn,518,0,part,sizeof(part),&bytes)==AURA_TRANSFER_INVALID&&bytes==0);
    CHECK(fragment_at(session,txn,23,(uint16_t)logical_bytes,part,sizeof(part),&bytes)==AURA_TRANSFER_INVALID&&bytes==0);
    CHECK(fragment_at(session,(uint16_t)(txn+1),23,0,part,sizeof(part),&bytes)==AURA_TRANSFER_STALE&&bytes==0);
    memset(part,0xA5,sizeof(part));CHECK(fragment_at(session,txn,23,0,part,19,&bytes)==AURA_TRANSFER_BUFFER_SMALL&&bytes==0);
    for(size_t n=0;n<sizeof(part);++n)CHECK(part[n]==0xA5);
    CHECK(copy_at(session,part,logical_bytes-1,&bytes)==AURA_TRANSFER_BUFFER_SMALL&&bytes==0);
}
static void save_fixture_file(const char *name,const uint8_t *data,size_t bytes)
{
    char path[1024];int length=snprintf(path,sizeof(path),"%s/%s",fixture_output,name);
    CHECK(length>0&&(size_t)length<sizeof(path));FILE *file=fopen(path,"wb");CHECK(file);
    CHECK(fwrite(data,1,bytes,file)==bytes);CHECK(!fclose(file));
}
static void save_receiver_fixture(bool opened)
{
    if(!fixture_output)return;
    /* These bytes were just compared against every successful READ and the
     * final physical FINISH receipt. Do not turn OPEN into a terminal ACK. */
    CHECK(expected_bytes==physical_bytes+(opened?120u:0u));
    CHECK(receipt[5]==(opened?0:AURA_ARCHIVE_FINALIZED));
    save_fixture_file(opened?"open.aura":"finalized.aura",expected,expected_bytes);
    save_fixture_file(opened?"open.physical.ack3":"finalized.physical.ack3",receipt,sizeof(receipt));
    printf("FIXTURE %s generation=%u export_bytes=%zu physical_bytes=%zu physical_status=%u export_status=%u\n",
        opened?"open":"finalized",opened?43u:42u,expected_bytes,physical_bytes,receipt[5],expected[expected_bytes-115]);
}
static void real_roundtrips(void)
{
    START("real_owned_Opus_finalized_and_OPEN_full_wire_roundtrip");
    golden_row("device_id","context",device,16);golden_row("incarnation","context",incarnation,16);
    for(unsigned mode=0;mode<2;++mode){
        real_fixture(mode!=0);connect_authorized();hello(1,mode?"open.hello":"final.hello");
        uint8_t cmd[20],out[512],want[80]={0};size_t cmdbytes=command(cmd,AURA_TRANSFER_LIST,2,revision,0,0);
        size_t bytes=exchange(cmd,cmdbytes,out);response_header(want,0,AURA_TRANSFER_LIST,2);put(want+4,revision,4);
        memcpy(want+10,expected,68);want[78]=journal.captures[0].verification;
        CHECK(bytes==80&&!memcmp(out,want,80));golden_pair(mode?"open.list":"final.list",cmd,cmdbytes,out,bytes);CHECK(!sent_at(session,2));
        select_capture(3,mode!=0,mode?"open.select":"final.select");
        cmdbytes=command(cmd,AURA_TRANSFER_SELECT,3,0,0,0);CHECK(submit(cmd,cmdbytes)==AURA_TRANSFER_CACHED);CHECK(completed(out)==195);
        fragments(3,mode?"open.select":"final.select");CHECK(!sent_at(session,3));
        uint64_t offset=0,reads=medium.reads;uint16_t txn=4;
        while(offset<expected_bytes){size_t count=read_response(txn,offset,128,txn==4?(mode?"open.read":"final.read"):NULL);
            CHECK(count>0);offset+=count;CHECK(++txn<2000);}
        finish_response(txn++,mode!=0,mode?"open.finish":"final.finish");
        CHECK(medium.reads-reads<=2u*62u*journal.captures[0].blocks+8u);
        save_receiver_fixture(mode!=0);
        CHECK(!read_response(txn++,offset,256,mode?"open.read-eof":"final.read-eof"));
        cmdbytes=command(cmd,AURA_TRANSFER_CANCEL,txn,handle,0,0);bytes=exchange(cmd,cmdbytes,out);
        CHECK(bytes==8&&out[0]==0&&get(out+4,4)==handle);golden_pair(mode?"open.cancel":"final.cancel",cmd,cmdbytes,out,bytes);
        CHECK(!sent_at(session,txn));CHECK(!session_end(session));
    }
    PASS();
}
static void retries_and_gate(void)
{
    START("pending_join_immutable_cached_retry_and_response_sent_gate");quick_fixture(false,true,0);connect_authorized();hello(1,NULL);
    uint8_t cmd[20],changed[20],next[20],out[512],saved[512],canary[512];
    size_t cmdbytes=command(cmd,AURA_TRANSFER_SELECT,2,0,0,0);memcpy(changed,cmd,20);changed[4]^=1;
    size_t nextbytes=command(next,AURA_TRANSFER_HELLO,3,0,0,0);CHECK(submit(cmd,cmdbytes)==AURA_TRANSFER_ACCEPTED);
    CHECK(submit(cmd,cmdbytes)==AURA_TRANSFER_JOINED);CHECK(submit(changed,20)==AURA_TRANSFER_CONFLICT);
    changed[0]=2;CHECK(submit(changed,20)==AURA_TRANSFER_CONFLICT);
    uint8_t cancelcmd[20];size_t cancelbytes=command(cancelcmd,AURA_TRANSFER_CANCEL,3,1,0,0);
    CHECK(submit(cancelcmd,cancelbytes)==AURA_TRANSFER_BUSY);
    CHECK(submit(next,nextbytes)==AURA_TRANSFER_BUSY);CHECK(sent_at(session,2)<0);
    size_t bytes=0;memset(canary,0xA5,sizeof(canary));CHECK(copy_at(session,canary,512,&bytes)==AURA_TRANSFER_BUSY&&bytes==0);
    CHECK(step_at(session)==AURA_TRANSFER_WAIT);CHECK(submit(cmd,cmdbytes)==AURA_TRANSFER_JOINED);
    size_t count=completed(out);CHECK(count==195);memcpy(saved,out,count);
    CHECK(submit(next,nextbytes)==AURA_TRANSFER_BUSY);uint64_t first_delivery=delivery;
    CHECK(submit(cmd,cmdbytes)==AURA_TRANSFER_JOINED);
    CHECK(step_at(session)==AURA_TRANSFER_RESPONSE);CHECK(!copy_at(session,out,512,&bytes));CHECK(delivery==first_delivery&&bytes==count&&!memcmp(out,saved,count));
    CHECK(sent_at(session,3)==AURA_TRANSFER_STALE);fragments(2,NULL);CHECK(!sent_at(session,2));
    CHECK(submit(cmd,cmdbytes)==AURA_TRANSFER_CACHED);CHECK(submit(next,nextbytes)==AURA_TRANSFER_BUSY);
    CHECK(!copy_at(session,out,512,&bytes));CHECK(delivery!=first_delivery&&bytes==count&&!memcmp(out,saved,count));
    CHECK(sent_token_at(session,2,first_delivery)==AURA_TRANSFER_STALE);
    CHECK(fragment_token_at(session,2,first_delivery,23,0,canary,512,&bytes)==AURA_TRANSFER_STALE&&bytes==0);
    CHECK(submit(next,nextbytes)==AURA_TRANSFER_BUSY);CHECK(!sent_at(session,2));
    uint8_t nextout[512];CHECK(submit(next,nextbytes)==AURA_TRANSFER_ACCEPTED);CHECK(completed(nextout)==46);CHECK(!sent_at(session,3));
    CHECK(submit(cmd,cmdbytes)==AURA_TRANSFER_STALE);CHECK(!memcmp(out,saved,count));
    for(size_t n=0;n<sizeof(canary);++n)CHECK(canary[n]==0xA5);
    PASS();
}
static void malformed_and_contextual(void)
{
    START("malformed_admission_does_not_consume_transaction_or_replace_cache");quick_fixture(false,true,0);connect_authorized();hello(1,NULL);
    uint8_t repeat[20],cached[512];size_t repeatbytes=command(repeat,AURA_TRANSFER_HELLO,1,0,0,0);
    CHECK(submit(repeat,repeatbytes)==AURA_TRANSFER_CACHED);CHECK(completed(cached)==46);
    for(unsigned kind=0;kind<15;++kind){uint8_t cmd[20],out[512];size_t bytes=command(cmd,AURA_TRANSFER_READ,2,1,0,1);
        switch(kind){
        case 0:cmd[0]=2;break;case 1:put(cmd+2,0,2);break;case 2:cmd[1]=99;break;
        case 3:bytes=17;break;case 4:bytes=19;break;case 5:put(cmd+4,0,4);break;
        case 6:put(cmd+8,AURA_TRANSFER_FILE_MAX+1ull,8);break;case 7:put(cmd+16,0,2);break;case 8:put(cmd+16,257,2);break;
        case 9:bytes=command(cmd,AURA_TRANSFER_LIST,2,0,0,0);break;
        case 10:bytes=command(cmd,AURA_TRANSFER_SELECT,2,0,0,0);memset(cmd+4,0,16);break;
        case 11:bytes=command(cmd,AURA_TRANSFER_FINISH,2,1,AURA_TRANSFER_FILE_MAX+1ull,0);break;
        case 12:bytes=command(cmd,AURA_TRANSFER_CANCEL,2,0,0,0);break;
        case 13:bytes=3;break;case 14:bytes=0;break;
        }
        CHECK(submit(cmd,bytes)==AURA_TRANSFER_INVALID);size_t copied;CHECK(!copy_at(session,out,512,&copied));CHECK(copied==46&&get(out+2,2)==1);
    }
    CHECK(submit(NULL,4)==AURA_TRANSFER_INVALID);uint8_t cmd[21]={0};CHECK(submit(cmd,sizeof(cmd))==AURA_TRANSFER_INVALID);CHECK(!sent_at(session,1));hello(2,NULL);PASS();
    START("immediate_and_late_contextual_errors_are_exact_cached_four_bytes");
    size_t bytes=command(cmd,AURA_TRANSFER_LIST,3,revision+1,0,0);error_reply(cmd,bytes,AURA_TRANSFER_STATUS_STALE);
    bytes=command(cmd,AURA_TRANSFER_LIST,4,revision,1,0);error_reply(cmd,bytes,AURA_TRANSFER_END_OF_LIST);
    bytes=command(cmd,AURA_TRANSFER_SELECT,5,0,0,0);cmd[4]^=1;error_reply(cmd,bytes,AURA_TRANSFER_NOT_FOUND);
    bytes=command(cmd,AURA_TRANSFER_READ,6,77,0,1);error_reply(cmd,bytes,AURA_TRANSFER_NOT_FOUND);
    select_capture(7,false,NULL);
    bytes=command(cmd,AURA_TRANSFER_FINISH,8,handle,expected_bytes,0);error_reply(cmd,bytes,AURA_TRANSFER_STATUS_INVALID);
    bytes=command(cmd,AURA_TRANSFER_READ,9,handle,1,1);error_reply(cmd,bytes,AURA_TRANSFER_STATUS_INVALID);
    uint8_t out[512],saved[4];size_t copied;uint64_t reads=medium.reads;
    CHECK(submit(cmd,bytes)==AURA_TRANSFER_CACHED);CHECK(completed(out)==4);CHECK(!copy_at(session,saved,4,&copied)&&copied==4);
    CHECK(submit(cmd,bytes)==AURA_TRANSFER_JOINED);CHECK(completed(out)==4&&!memcmp(out,saved,4));CHECK(medium.reads==reads);CHECK(!sent_at(session,9));
    select_capture(10,false,NULL);size_t count=read_response(11,68,1,NULL);CHECK(count==1);
    bytes=command(cmd,AURA_TRANSFER_READ,12,handle,68,1);error_reply(cmd,bytes,AURA_TRANSFER_STATUS_CONFLICT);
    CHECK(read_response(13,69,1,NULL)==1);PASS();
}
static void boundary_resume(void)
{
    START("first_READ_boundary_resume_followed_by_arbitrary_chunk_offsets_and_EOF");
    const uint64_t starts[]={0,68,174};
    for(unsigned opened=0;opened<2;++opened)for(unsigned n=0;n<5;++n){
        quick_fixture(opened!=0,true,0);connect_authorized();select_capture(1,opened!=0,NULL);
        uint64_t offset=n<3?starts[n]:n==3?physical_bytes:expected_bytes,reads=medium.reads;uint16_t txn=2;
        do{size_t count=read_response(txn++,offset,7,NULL);offset+=count;if(!count)break;CHECK(txn<1000);}while(offset<expected_bytes);
        CHECK(offset==expected_bytes);finish_response(txn++,opened!=0,NULL);
        CHECK(medium.reads-reads>=120u*journal.captures[0].blocks&&medium.reads-reads<=2u*62u*journal.captures[0].blocks+8u);
        CHECK(!read_response(txn,offset,1,NULL));
    }
    PASS();
}
static void ownership_and_catalog(void)
{
    START("privileged_catalog_flags_and_owned_generation_identity_enforcement");
    for(unsigned kind=0;kind<4;++kind){
        quick_fixture(false,kind!=0,kind==0?0:kind);connect_authorized();hello(1,NULL);
        uint8_t cmd[20];size_t bytes=command(cmd,AURA_TRANSFER_SELECT,2,0,0,0);
        error_reply(cmd,bytes,kind==1?AURA_TRANSFER_NOT_FOUND:AURA_TRANSFER_STATUS_FORBIDDEN);
    }
    for(unsigned bits=0;bits<16;++bits){
        quick_fixture(false,true,0);connect_authorized();hello(1,NULL);
        /* Test-only catalog fault injection: listing must expose these flags,
         * without interpreting this metadata-only snapshot as an export ACK. */
        journal.captures[0].metadata_fault=(bits&1)!=0;journal.unassociated_blocks=(bits&2)?1:0;
        journal.fault=(bits&4)?AURA_JOURNAL_CORRUPT:0;if(bits&8)journal.captures[0].manifest[8]^=1;
        journal.captures[0].verification=AURA_JOURNAL_UNVERIFIED;
        uint8_t cmd[20],out[512];size_t bytes=command(cmd,AURA_TRANSFER_LIST,2,revision,0,0);
        uint64_t reads=medium.reads;CHECK(exchange(cmd,bytes,out)==80);CHECK(medium.reads==reads);
        CHECK(out[78]==0&&out[79]==bits&&!memcmp(out+10,journal.captures[0].manifest,68));CHECK(!sent_at(session,2));
        uint8_t ack[94];CHECK(aura_journal_receipt(&journal,0,ack)<0);
    }
    PASS();
}
static void mutate_packet(void)
{
    uint8_t *page=medium.pages[3];CHECK(page);page[155]^=1;fix_crc(page+132,106);fix_crc(page,2048);
}
static void source_failure(void)
{
    START("source_corruption_fails_SELECT_READ_and_final_third_verification");
    for(unsigned when=0;when<3;++when){
        quick_fixture(false,true,0);connect_authorized();uint8_t cmd[20],out[512];size_t bytes;
        if(when==0){medium.ecc[3]=2;bytes=command(cmd,AURA_TRANSFER_SELECT,1,0,0,0);error_reply(cmd,bytes,AURA_TRANSFER_IO_ERROR);}
        else{
            select_capture(1,false,NULL);
            if(when==1){mutate_packet();bytes=command(cmd,AURA_TRANSFER_READ,2,handle,0,256);
                /* A prefix can be returned before the conflicting receipt is
                 * discovered. Keep reading until the logical error arrives. */
                uint64_t offset=0;uint16_t txn=2;bool failed=false;
                while(!failed){bytes=command(cmd,AURA_TRANSFER_READ,txn,handle,offset,256);size_t count=exchange(cmd,bytes,out);
                    if(out[0]){CHECK(count==4&&out[0]==AURA_TRANSFER_IO_ERROR);failed=true;}
                    else{CHECK(count>=22);size_t payload=(size_t)get(out+16,2);CHECK(payload>0);offset+=payload;}
                    CHECK(!sent_at(session,txn));CHECK(++txn<50);
                }
            }else{
                uint64_t offset=0;uint16_t txn=2;
                while(offset<expected_bytes){size_t count=read_response(txn++,offset,31,NULL);CHECK(count>0);offset+=count;}
                mutate_packet();bytes=command(cmd,AURA_TRANSFER_FINISH,txn,handle,expected_bytes,0);error_reply(cmd,bytes,AURA_TRANSFER_IO_ERROR);
            }
        }
        uint8_t ack[94];CHECK(aura_journal_receipt(&journal,0,ack)==AURA_JOURNAL_NOT_COMMITTED);
        uint64_t reads=medium.reads;CHECK(submit(cmd,bytes)==AURA_TRANSFER_CACHED);CHECK(completed(out)==4&&out[0]==AURA_TRANSFER_IO_ERROR);
        CHECK(medium.reads==reads);CHECK(!sent_at(session,(uint16_t)get(cmd+2,2)));
    }
    PASS();
}
static void lifecycle(void)
{
    START("epoch_change_invalidates_pending_work_cached_response_and_handle");
    for(unsigned phase=0;phase<3;++phase){
        quick_fixture(false,true,0);connect_authorized();uint8_t cmd[20],out[512];size_t cmdbytes=command(cmd,AURA_TRANSFER_SELECT,1,0,0,0);
        CHECK(submit(cmd,cmdbytes)==AURA_TRANSFER_ACCEPTED);
        if(phase==0)CHECK(step_at(session)==AURA_TRANSFER_WAIT);
        else{CHECK(completed(out)==195);if(phase==2)CHECK(!sent_at(session,1));}
        uint32_t old_revision=transfer.revision;CHECK(!aura_journal_invalidate_exports(&journal));size_t bytes=999;
        memset(out,0xA5,sizeof(out));
        if(phase==0)CHECK(step_at(session)==AURA_TRANSFER_SOURCE_CHANGED);
        else CHECK(copy_at(session,out,sizeof(out),&bytes)==AURA_TRANSFER_SOURCE_CHANGED&&bytes==0);
        for(size_t n=0;n<sizeof(out);++n)CHECK(out[n]==0xA5);
        CHECK(submit(cmd,cmdbytes)==AURA_TRANSFER_STALE);CHECK(!transfer.selected);hello(2,NULL);CHECK(revision==old_revision+1);
    }
    PASS();
    START("local_cancel_disconnect_reconnect_and_authorization_loss_drop_old_callbacks");
    for(unsigned phase=0;phase<2;++phase){
        quick_fixture(false,true,0);connect_authorized();uint8_t cmd[20],out[512];size_t cmdbytes=command(cmd,AURA_TRANSFER_SELECT,1,0,0,0);
        CHECK(submit(cmd,cmdbytes)==AURA_TRANSFER_ACCEPTED);if(phase)CHECK(completed(out)==195);else CHECK(step_at(session)==AURA_TRANSFER_WAIT);
        CHECK(!cancel_work(session));CHECK(submit(cmd,cmdbytes)==AURA_TRANSFER_STALE);hello(2,NULL);
        uint64_t old=session;CHECK(!session_end(old));CHECK(!session_begin(true,&session));CHECK(session!=old);
        cmdbytes=command(cmd,AURA_TRANSFER_HELLO,1,0,0,0);size_t bytes;
        CHECK(submit_at(old,cmd,cmdbytes)==AURA_TRANSFER_STALE);CHECK(step_at(old)==AURA_TRANSFER_STALE);
        CHECK(copy_at(old,out,512,&bytes)==AURA_TRANSFER_STALE&&bytes==0);CHECK(sent_at(old,2)==AURA_TRANSFER_STALE);
        CHECK(cancel_work(old)==AURA_TRANSFER_STALE&&session_end(old)==AURA_TRANSFER_STALE);hello(1,NULL);
        old=session;CHECK(!session_begin(false,&session));CHECK(session!=old);
        CHECK(submit(cmd,cmdbytes)==AURA_TRANSFER_FORBIDDEN);CHECK(step_at(session)==AURA_TRANSFER_FORBIDDEN);
        CHECK(copy_at(session,out,512,&bytes)==AURA_TRANSFER_FORBIDDEN&&bytes==0);
        CHECK(fragment_at(session,1,23,0,out,512,&bytes)==AURA_TRANSFER_FORBIDDEN&&bytes==0);
        CHECK(sent_at(session,1)==AURA_TRANSFER_FORBIDDEN);CHECK(!session_begin(true,&session));hello(1,NULL);
        /* Simulate trusted owner profile becoming unavailable before callbacks. */
        journal.owned_profile=false;CHECK(copy_at(session,out,512,&bytes)==AURA_TRANSFER_FORBIDDEN&&bytes==0);
        CHECK(!transfer.cache_valid&&!transfer.selected);
    }
    PASS();
}
static void counter_limits(void)
{
    START("checked_transaction_handle_and_revision_limits_test_only_injection");
    quick_fixture(false,true,0);connect_authorized();
    /* Direct near-limit setup is confined to this host test; no live context
     * field mutation is a supported public caller operation. */
    transfer.last_transaction=UINT16_MAX-1;hello(UINT16_MAX,NULL);
    uint8_t cmd[20],out[512];size_t bytes=command(cmd,AURA_TRANSFER_HELLO,UINT16_MAX,0,0,0);
    CHECK(submit(cmd,bytes)==AURA_TRANSFER_CACHED);CHECK(completed(out)==46);CHECK(!sent_at(session,UINT16_MAX));
    bytes=command(cmd,AURA_TRANSFER_HELLO,1,0,0,0);CHECK(submit(cmd,bytes)==AURA_TRANSFER_STALE);
    put(cmd+2,0,2);CHECK(submit(cmd,bytes)==AURA_TRANSFER_INVALID);CHECK(!session_begin(true,&session));hello(1,NULL);
    transfer.next_handle=UINT32_MAX-1;select_capture(2,false,NULL);CHECK(handle==UINT32_MAX);
    bytes=command(cmd,AURA_TRANSFER_SELECT,3,0,0,0);uint64_t reads=medium.reads;error_reply(cmd,bytes,AURA_TRANSFER_STATUS_CONFLICT);CHECK(medium.reads==reads);
    transfer.revision=UINT32_MAX;CHECK(!aura_journal_invalidate_exports(&journal));
    CHECK(step_at(session)==AURA_TRANSFER_EXHAUSTED);CHECK(!transfer.authorized&&transfer.connection==0);
    CHECK(!session_begin(true,&session));hello(1,NULL);CHECK(revision==1);
    transfer.next_delivery=UINT64_MAX-1;hello(2,NULL);CHECK(delivery==UINT64_MAX);
    bytes=command(cmd,AURA_TRANSFER_HELLO,2,0,0,0);CHECK(submit(cmd,bytes)==AURA_TRANSFER_EXHAUSTED);
    CHECK(!transfer.authorized&&!transfer.connection);PASS();
}
static void output_aliases(void)
{
    START("private_and_overlapping_output_aliases_reject_before_any_write");
    quick_fixture(false,true,0);connect_authorized();uint8_t cmd[20],response[512];
    size_t command_bytes=command(cmd,AURA_TRANSFER_HELLO,1,0,0,0);CHECK(exchange(cmd,command_bytes,response)==46);
    union aligned_buffer{uint64_t u64;size_t size;uint8_t data[1024];} buffer,saved;
    static struct aura_transfer saved_transfer;static struct aura_journal saved_journal;
    for(unsigned kind=0;kind<12;++kind){
        memset(&buffer,0xA5,sizeof(buffer));saved=buffer;saved_transfer=transfer;saved_journal=journal;
        size_t bytes=999;uint64_t token=888;uint8_t *out=buffer.data;size_t *count=&bytes;uint64_t *delivery_out=&token;
        if(kind==0)out=transfer.response;
        if(kind==1)out=journal.scratch;
        if(kind==2)count=(size_t *)(void *)buffer.data;
        if(kind==3)delivery_out=(uint64_t *)(void *)(buffer.data+8);
        if(kind==4){count=(size_t *)(void *)(buffer.data+600);delivery_out=(uint64_t *)(void *)(buffer.data+600);}
        if(kind==5)count=(size_t *)(void *)&transfer.next_offset;
        if(kind==6)delivery_out=&transfer.connection;
        if(kind==7)count=(size_t *)(void *)&journal.metadata_reads;
        if(kind==8)delivery_out=&journal.export_epoch;
        if(kind==9)out=NULL;if(kind==10)count=NULL;if(kind==11)delivery_out=NULL;
        struct counters b=before();CHECK(aura_transfer_copy_response(&transfer,session,out,512,count,delivery_out)==AURA_TRANSFER_INVALID);after(b,false);
        CHECK(bytes==999&&token==888);CHECK(!memcmp(&buffer,&saved,sizeof(buffer)));
        CHECK(!memcmp(&transfer,&saved_transfer,sizeof(transfer)));CHECK(!memcmp(&journal,&saved_journal,sizeof(journal)));
    }
    for(unsigned kind=0;kind<5;++kind){
        memset(&buffer,0xA5,sizeof(buffer));saved=buffer;saved_transfer=transfer;saved_journal=journal;
        size_t bytes=999;uint8_t *out=buffer.data;size_t *count=&bytes;
        if(kind==0)out=transfer.response;if(kind==1)out=journal.scratch;
        if(kind==2)count=(size_t *)(void *)buffer.data;if(kind==3)count=(size_t *)(void *)&transfer.next_offset;
        if(kind==4)count=(size_t *)(void *)&journal.metadata_reads;
        struct counters b=before();CHECK(aura_transfer_copy_fragment(&transfer,session,1,delivery,23,0,out,512,count)==AURA_TRANSFER_INVALID);after(b,false);
        CHECK(bytes==999&&!memcmp(&buffer,&saved,sizeof(buffer)));
        CHECK(!memcmp(&transfer,&saved_transfer,sizeof(transfer)));CHECK(!memcmp(&journal,&saved_journal,sizeof(journal)));
    }
    saved_transfer=transfer;saved_journal=journal;
    CHECK(session_begin(true,&transfer.connection)==AURA_TRANSFER_INVALID);CHECK(session_begin(true,&journal.export_epoch)==AURA_TRANSFER_INVALID);
    struct counters b=before();CHECK(aura_transfer_init((struct aura_transfer *)(void *)&journal,&journal,device,incarnation)==AURA_TRANSFER_INVALID);after(b,false);
    CHECK(!memcmp(&transfer,&saved_transfer,sizeof(transfer)));CHECK(!memcmp(&journal,&saved_journal,sizeof(journal)));
    CHECK(!sent_at(session,1));PASS();
}
static void empty_and_cancelled(void)
{
    START("empty_catalog_empty_archives_and_ordered_CANCEL_preserve_source");
    reset();CHECK(!aura_journal_set_owned_profile(&journal,incarnation));connect_authorized();hello(1,NULL);
    uint8_t cmd[20],out[512];size_t cmdbytes=command(cmd,AURA_TRANSFER_LIST,2,revision,0,0);error_reply(cmd,cmdbytes,AURA_TRANSFER_END_OF_LIST);
    for(unsigned opened=0;opened<2;++opened){
        reset();start_capture(true,0,42,NULL);if(opened)CHECK(!aura_journal_flush(&journal));else CHECK(!aura_archive_interrupt(&writer));
        remount_and_reference();CHECK(expected_bytes==188);connect_authorized();select_capture(1,opened!=0,NULL);
        uint64_t offset=0;uint16_t txn=2;while(offset<expected_bytes){size_t bytes=read_response(txn++,offset,1,NULL);CHECK(bytes==1);offset+=bytes;}
        finish_response(txn++,opened!=0,NULL);
        cmdbytes=command(cmd,AURA_TRANSFER_CANCEL,txn,handle,0,0);CHECK(exchange(cmd,cmdbytes,out)==8);CHECK(get(out+4,4)==handle);CHECK(!sent_at(session,txn++));
        cmdbytes=command(cmd,AURA_TRANSFER_READ,txn,handle,0,1);error_reply(cmd,cmdbytes,AURA_TRANSFER_NOT_FOUND);
        uint8_t ack[94];CHECK(!aura_journal_receipt(&journal,0,ack)&&!memcmp(ack,receipt,94));
    }
    PASS();
}
int main(int argc,char **argv)
{
    START("arguments");CHECK(argc==4||argc==5);final_fixture=argv[1];open_fixture=argv[2];
    /* Optional directory is explicit and must already exist; no implicit
     * fixtures/ root writes or directory creation by the portable C harness. */
    fixture_output=argc==5?argv[4]:NULL;golden=fopen(argv[3],"wb");CHECK(golden);
    CHECK(fprintf(golden,"# name\tkind\thex\n")>0);
    real_roundtrips();retries_and_gate();malformed_and_contextual();boundary_resume();ownership_and_catalog();
    source_failure();lifecycle();counter_limits();output_aliases();empty_and_cancelled();
    CHECK(!fclose(golden));model_destroy(&medium);
    printf("PASS transfer cases=%u checks=%u step_calls=%llu no_io_calls=%llu max_reads_per_step=%u transfer_bytes=%zu host_model_only=true\n",
        cases,checks,(unsigned long long)step_calls,(unsigned long long)noio_calls,max_reads,sizeof(transfer));return 0;
}
