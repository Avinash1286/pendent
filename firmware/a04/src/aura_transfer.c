/* SPDX-License-Identifier: MIT */
#include "aura_transfer.h"
#include "aura_storage.h"
#include <string.h>

/* One global storage owner serializes all contexts; not a thread-safe counter. */
static uint64_t connection_counter;
static uint64_t get(const uint8_t *p,unsigned n)
{uint64_t v=0;for(unsigned i=0;i<n;++i)v|=(uint64_t)p[i]<<(8*i);return v;}
static void put(uint8_t *p,uint64_t v,unsigned n)
{for(unsigned i=0;i<n;++i)p[i]=(uint8_t)(v>>(8*i));}
static bool zero(const uint8_t *p,size_t n)
{for(size_t i=0;i<n;++i)if(p[i])return false;return true;}
static bool overlap(const void *a,size_t an,const void *b,size_t bn)
{
    if(!a||!b||!an||!bn)return false;
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;return x<=y?y-x<an:x-y<bn;
}
static bool private_output(const struct aura_transfer *t,const void *p,size_t bytes)
{
    return t&&(overlap(t,sizeof(*t),p,bytes)||
        (t->initialized&&t->journal&&overlap(t->journal,sizeof(*t->journal),p,bytes)));
}

static void clear_selection(struct aura_transfer *t)
{
    aura_journal_cursor_cancel(&t->cursor);
    t->handle=0;t->next_offset=0;t->selected=t->seeked=t->finished=false;
}
static void clear_work(struct aura_transfer *t)
{
    clear_selection(t);t->pending=t->response_pending=t->cache_valid=t->operation_started=false;
    t->response_bytes=0;t->delivery=0;memset(t->response,0,sizeof(t->response));
}
static int connection_guard(struct aura_transfer *t,uint64_t generation)
{
    if(!t||!t->initialized)return AURA_TRANSFER_STATE;
    if(!generation||generation!=t->connection)return AURA_TRANSFER_STALE;
    return 0;
}
static int guard(struct aura_transfer *t,uint64_t generation)
{
    int r=connection_guard(t,generation);if(r)return r;
    if(!t->authorized)return AURA_TRANSFER_FORBIDDEN;
    struct aura_journal *j=t->journal;
    if(j->export_epoch!=t->observed_epoch){
        clear_work(t);t->observed_epoch=j->export_epoch;
        if(t->revision==UINT32_MAX){t->connection=0;t->authorized=false;return AURA_TRANSFER_EXHAUSTED;}
        ++t->revision;return AURA_TRANSFER_SOURCE_CHANGED;
    }
    if(!j->export_epoch||!j->owned_profile||memcmp(j->owned_incarnation,t->incarnation,16)){
        clear_work(t);return AURA_TRANSFER_FORBIDDEN;
    }
    if(j->count>AURA_JOURNAL_MAX_CAPTURES){clear_work(t);return AURA_TRANSFER_STATE;}
    return 0;
}
int aura_transfer_init(struct aura_transfer *t,struct aura_journal *j,
    const uint8_t device[16],const uint8_t incarnation[16])
{
    if(!t||!j||!device||!incarnation||overlap(t,sizeof(*t),j,sizeof(*j))||
       zero(device,16)||zero(incarnation,16))return AURA_TRANSFER_INVALID;
    uint8_t ids[32];memcpy(ids,device,16);memcpy(ids+16,incarnation,16);
    memset(t,0,sizeof(*t));t->journal=j;memcpy(t->device_id,ids,16);memcpy(t->incarnation,ids+16,16);
    t->initialized=true;return 0;
}
int aura_transfer_session_begin(struct aura_transfer *t,bool authorized,uint64_t *generation)
{
    if(!t||!t->initialized||!generation||private_output(t,generation,sizeof(*generation)))return AURA_TRANSFER_INVALID;
    *generation=0;
    clear_work(t);t->connection=0;t->authorized=false;t->last_transaction=0;t->command_bytes=0;
    memset(t->command,0,sizeof(t->command));
    if(connection_counter==UINT64_MAX)return AURA_TRANSFER_EXHAUSTED;
    if(!t->journal->export_epoch)return AURA_TRANSFER_STATE;
    t->connection=++connection_counter;t->authorized=authorized;
    t->observed_epoch=t->journal->export_epoch;t->revision=1;t->next_delivery=0;
    *generation=t->connection;return 0;
}
int aura_transfer_session_end(struct aura_transfer *t,uint64_t generation)
{
    int r=connection_guard(t,generation);if(r)return r;
    clear_work(t);t->connection=0;t->authorized=false;t->command_bytes=0;
    memset(t->command,0,sizeof(t->command));return 0;
}
int aura_transfer_cancel_work(struct aura_transfer *t,uint64_t generation)
{
    int r=connection_guard(t,generation);if(r)return r;
    clear_work(t);return 0;
}
static int new_delivery(struct aura_transfer *t)
{
    if(t->next_delivery==UINT64_MAX){
        clear_work(t);t->connection=0;t->authorized=false;return AURA_TRANSFER_EXHAUSTED;
    }
    t->delivery=++t->next_delivery;t->response_pending=true;return 0;
}

static bool valid_command(const uint8_t *p,size_t n)
{
    if(n<4||n>20||p[0]!=1||!get(p+2,2))return false;
    switch(p[1]){
    case AURA_TRANSFER_HELLO:return n==4;
    case AURA_TRANSFER_LIST:return n==10&&get(p+4,4)!=0;
    case AURA_TRANSFER_SELECT:return n==20&&!zero(p+4,16);
    case AURA_TRANSFER_READ:return n==18&&get(p+4,4)&&get(p+8,8)<=AURA_TRANSFER_FILE_MAX&&get(p+16,2)&&get(p+16,2)<=256;
    case AURA_TRANSFER_FINISH:return n==16&&get(p+4,4)&&get(p+8,8)<=AURA_TRANSFER_FILE_MAX;
    case AURA_TRANSFER_CANCEL:return n==8&&get(p+4,4);
    default:return false;
    }
}
int aura_transfer_submit(struct aura_transfer *t,uint64_t generation,const uint8_t *command,size_t bytes)
{
    if(!command||bytes<4||bytes>20)return AURA_TRANSFER_INVALID;
    uint8_t copy[20];memcpy(copy,command,bytes);
    int r=guard(t,generation);if(r)return r;
    uint16_t transaction=(uint16_t)get(copy+2,2);
    if(!transaction)return AURA_TRANSFER_INVALID;
    if(transaction==t->last_transaction){
        if(bytes!=t->command_bytes||memcmp(copy,t->command,bytes))return AURA_TRANSFER_CONFLICT;
        if(t->pending)return AURA_TRANSFER_JOINED;
        if(t->cache_valid){
            if(t->response_pending)return AURA_TRANSFER_JOINED;
            r=new_delivery(t);return r?r:AURA_TRANSFER_CACHED;
        }
        return AURA_TRANSFER_STALE;
    }
    if(!valid_command(copy,bytes))return AURA_TRANSFER_INVALID;
    if(transaction<t->last_transaction)return AURA_TRANSFER_STALE;
    if(t->pending||t->response_pending)return AURA_TRANSFER_BUSY;
    memcpy(t->command,copy,bytes);t->command_bytes=(uint8_t)bytes;t->last_transaction=transaction;
    memset(t->response,0,sizeof(t->response));t->response_bytes=0;t->cache_valid=false;
    t->pending=true;t->operation_started=false;return AURA_TRANSFER_ACCEPTED;
}

static int response(struct aura_transfer *t,uint8_t status,uint16_t bytes)
{
    int r=new_delivery(t);if(r)return r;
    t->response[0]=status;t->response[1]=t->command[1];put(t->response+2,t->last_transaction,2);
    t->response_bytes=status?4:bytes;t->pending=false;t->cache_valid=t->response_pending=true;
    t->operation_started=false;return AURA_TRANSFER_RESPONSE;
}
static uint8_t cursor_status(int r)
{
    if(r==AURA_JOURNAL_BUSY||r==AURA_CURSOR_STATE)return AURA_TRANSFER_STATUS_BUSY;
    if(r==AURA_CURSOR_BOUNDARY||r==AURA_NAND_BAD_ARGUMENT)return AURA_TRANSFER_STATUS_INVALID;
    if(r==AURA_JOURNAL_NOT_COMMITTED)return AURA_TRANSFER_NOT_FOUND;
    if(r==AURA_CURSOR_STALE)return AURA_TRANSFER_STATUS_STALE;
    return AURA_TRANSFER_IO_ERROR;
}
static int cursor_error(struct aura_transfer *t,int r)
{clear_selection(t);return response(t,cursor_status(r),4);}
static int selected_info(struct aura_transfer *t,struct aura_journal_cursor_info *info)
{
    int r=aura_journal_cursor_get_info(&t->cursor,info);if(r)return r;
    uint8_t capture[16];
    if(!info->allocation.owned||info->allocation.version!=2||
       memcmp(info->allocation.incarnation,t->incarnation,16)||
       memcmp(info->manifest+8,t->device_id,16)||
       aura_storage_capture_id(t->device_id,t->incarnation,info->allocation.allocation_generation,capture)||
       memcmp(capture,info->manifest+24,16))return AURA_TRANSFER_FORBIDDEN;
    if(info->export_bytes>AURA_TRANSFER_FILE_MAX)return AURA_TRANSFER_INVALID;
    return 0;
}
static int select_step(struct aura_transfer *t)
{
    if(!t->operation_started){
        clear_selection(t);
        if(t->next_handle==UINT32_MAX)return response(t,AURA_TRANSFER_STATUS_CONFLICT,4);
        uint8_t identity[32];memcpy(identity,t->device_id,16);memcpy(identity+16,t->command+4,16);
        int r=aura_journal_cursor_open(&t->cursor,t->journal,identity);
        if(r)return cursor_error(t,r);
        t->operation_started=true;
    }
    int r=aura_journal_cursor_verify_step(&t->cursor);
    if(r==AURA_CURSOR_PENDING)return AURA_TRANSFER_WAIT;
    if(r!=AURA_CURSOR_READY)return cursor_error(t,r);
    struct aura_journal_cursor_info info;r=selected_info(t,&info);
    if(r){clear_selection(t);return response(t,r==AURA_TRANSFER_FORBIDDEN?AURA_TRANSFER_STATUS_FORBIDDEN:AURA_TRANSFER_IO_ERROR,4);}
    t->handle=++t->next_handle;t->selected=true;
    put(t->response+4,t->handle,4);memcpy(t->response+8,info.manifest,68);
    memcpy(t->response+76,info.physical_receipt,94);put(t->response+170,info.physical_bytes,8);
    put(t->response+178,info.export_bytes,8);t->response[186]=info.derived_seal?1:0;
    put(t->response+187,info.allocation.allocation_generation,8);
    return response(t,AURA_TRANSFER_OK,195);
}
static bool matching_handle(const struct aura_transfer *t)
{return t->selected&&t->handle&&get(t->command+4,4)==t->handle;}
static int read_step(struct aura_transfer *t)
{
    if(!matching_handle(t))return response(t,AURA_TRANSFER_NOT_FOUND,4);
    uint64_t requested_offset=get(t->command+8,8);size_t requested=(size_t)get(t->command+16,2);
    if(!t->operation_started){
        if(!t->seeked){
            int r=aura_journal_cursor_seek(&t->cursor,requested_offset);if(r)return cursor_error(t,r);
            t->next_offset=requested_offset;t->seeked=true;
        }else if(requested_offset!=t->next_offset)return response(t,AURA_TRANSFER_STATUS_CONFLICT,4);
        t->operation_started=true;
    }
    size_t bytes=0;uint64_t offset=0;
    int r=aura_journal_cursor_read(&t->cursor,t->response+18,requested,&offset,&bytes);
    if(r==AURA_CURSOR_PENDING)return AURA_TRANSFER_WAIT;
    if(r==AURA_CURSOR_DATA){
        if(!bytes||bytes>requested||offset!=t->next_offset||bytes>AURA_TRANSFER_FILE_MAX-t->next_offset)
            return cursor_error(t,AURA_JOURNAL_CORRUPT);
        t->next_offset+=bytes;
    }else if(!r){
        if(bytes||t->next_offset!=t->cursor.selected.export_bytes)return cursor_error(t,AURA_JOURNAL_CORRUPT);
        t->finished=true;offset=t->next_offset;
    }else return cursor_error(t,r);
    put(t->response+4,t->handle,4);put(t->response+8,offset,8);put(t->response+16,bytes,2);
    put(t->response+18+bytes,aura_archive_crc32(t->response+18,bytes),4);
    return response(t,AURA_TRANSFER_OK,(uint16_t)(22+bytes));
}
static int finish_step(struct aura_transfer *t)
{
    if(!matching_handle(t))return response(t,AURA_TRANSFER_NOT_FOUND,4);
    uint64_t expected=get(t->command+8,8);
    if(!t->seeked||expected!=t->cursor.selected.export_bytes||t->next_offset!=expected)
        return response(t,AURA_TRANSFER_STATUS_INVALID,4);
    if(!t->finished){
        uint8_t unexpected;size_t bytes=0;uint64_t offset=0;
        int r=aura_journal_cursor_read(&t->cursor,&unexpected,1,&offset,&bytes);
        if(r==AURA_CURSOR_PENDING)return AURA_TRANSFER_WAIT;
        if(r||bytes)return cursor_error(t,r<0?r:AURA_JOURNAL_CORRUPT);
        t->finished=true;
    }
    struct aura_journal_cursor_info info;int r=selected_info(t,&info);
    if(r)return cursor_error(t,r);
    put(t->response+4,t->handle,4);memcpy(t->response+8,info.physical_receipt,94);
    put(t->response+102,info.export_bytes,8);t->response[110]=info.derived_seal?1:0;
    put(t->response+111,info.allocation.allocation_generation,8);
    return response(t,AURA_TRANSFER_OK,119);
}
int aura_transfer_step(struct aura_transfer *t,uint64_t generation)
{
    int r=guard(t,generation);if(r)return r;
    if(!t->pending)return t->response_pending?AURA_TRANSFER_RESPONSE:AURA_TRANSFER_IDLE;
    struct aura_journal *j=t->journal;
    switch(t->command[1]){
    case AURA_TRANSFER_HELLO:
        memcpy(t->response+4,t->device_id,16);memcpy(t->response+20,t->incarnation,16);
        put(t->response+36,t->revision,4);put(t->response+40,j->count,2);
        put(t->response+42,512,2);put(t->response+44,256,2);return response(t,AURA_TRANSFER_OK,46);
    case AURA_TRANSFER_LIST:{
        if(get(t->command+4,4)!=t->revision)return response(t,AURA_TRANSFER_STATUS_STALE,4);
        uint16_t index=(uint16_t)get(t->command+8,2);
        if(index>=j->count)return response(t,AURA_TRANSFER_END_OF_LIST,4);
        const struct aura_journal_capture *c=&j->captures[index];
        if(c->verification>AURA_JOURNAL_INVALID)return response(t,AURA_TRANSFER_IO_ERROR,4);
        put(t->response+4,t->revision,4);put(t->response+8,index,2);memcpy(t->response+10,c->manifest,68);
        t->response[78]=c->verification;
        t->response[79]=(c->metadata_fault?1:0)|(j->unassociated_blocks?2:0)|(j->fault?4:0)|
            (memcmp(c->manifest+8,t->device_id,16)?8:0);
        return response(t,AURA_TRANSFER_OK,80);
    }
    case AURA_TRANSFER_SELECT:return select_step(t);
    case AURA_TRANSFER_READ:return read_step(t);
    case AURA_TRANSFER_FINISH:return finish_step(t);
    case AURA_TRANSFER_CANCEL:
        if(!matching_handle(t))return response(t,AURA_TRANSFER_NOT_FOUND,4);
        put(t->response+4,t->handle,4);clear_selection(t);return response(t,AURA_TRANSFER_OK,8);
    default:return response(t,AURA_TRANSFER_STATUS_INVALID,4);
    }
}
int aura_transfer_copy_response(struct aura_transfer *t,uint64_t generation,uint8_t *out,size_t capacity,
    size_t *bytes,uint64_t *delivery)
{
    if(!out||!bytes||!delivery||private_output(t,out,capacity)||private_output(t,bytes,sizeof(*bytes))||
       private_output(t,delivery,sizeof(*delivery))||overlap(out,capacity,bytes,sizeof(*bytes))||
       overlap(out,capacity,delivery,sizeof(*delivery))||overlap(bytes,sizeof(*bytes),delivery,sizeof(*delivery)))
        return AURA_TRANSFER_INVALID;
    *bytes=0;*delivery=0;
    int r=guard(t,generation);if(r)return r;
    if(!t->cache_valid||t->pending||!t->response_pending)return AURA_TRANSFER_BUSY;
    if(capacity<t->response_bytes)return AURA_TRANSFER_BUFFER_SMALL;
    memcpy(out,t->response,t->response_bytes);*bytes=t->response_bytes;*delivery=t->delivery;return 0;
}
int aura_transfer_copy_fragment(struct aura_transfer *t,uint64_t generation,uint16_t transaction,
    uint64_t delivery,uint16_t mtu,uint16_t offset,uint8_t *out,size_t capacity,size_t *bytes)
{
    if(!out||!bytes||private_output(t,out,capacity)||private_output(t,bytes,sizeof(*bytes))||
       overlap(out,capacity,bytes,sizeof(*bytes)))return AURA_TRANSFER_INVALID;
    *bytes=0;if(mtu<23||mtu>517||!transaction||!delivery)return AURA_TRANSFER_INVALID;
    int r=guard(t,generation);if(r)return r;
    if(!t->cache_valid||t->pending||!t->response_pending)return AURA_TRANSFER_BUSY;
    if(transaction!=t->last_transaction||delivery!=t->delivery)return AURA_TRANSFER_STALE;
    if(offset>=t->response_bytes)return AURA_TRANSFER_INVALID;
    size_t n=t->response_bytes-offset;if(n>(size_t)mtu-11)n=(size_t)mtu-11;
    if(capacity<n+8)return AURA_TRANSFER_BUFFER_SMALL;
    out[0]=1;out[1]=0;put(out+2,transaction,2);put(out+4,offset,2);put(out+6,t->response_bytes,2);
    memcpy(out+8,t->response+offset,n);*bytes=n+8;return 0;
}
int aura_transfer_response_sent(struct aura_transfer *t,uint64_t generation,uint16_t transaction,uint64_t delivery)
{
    int r=guard(t,generation);if(r)return r;
    if(!transaction||transaction!=t->last_transaction||!delivery||delivery!=t->delivery)return AURA_TRANSFER_STALE;
    if(!t->cache_valid||t->pending)return AURA_TRANSFER_BUSY;
    t->response_pending=false;return 0;
}
