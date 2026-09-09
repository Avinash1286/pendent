/* SPDX-License-Identifier: MIT */
#include "aura_storage.h"
#include <string.h>

#define PHASE_IDLE 0u
#define PHASE_GRANTED 1u
#define COUNTER_AT 64u
#define FLOOR_AT 72u
#define RELEASE_AT 80u
#define COUNT_AT 262u
#define MANIFEST_AT 264u

_Static_assert(AURA_STORAGE_STATE_BYTES <= AURA_CONTROL_MAX_BYTES, "Authority snapshot exceeds ledger");
static uint64_t get(const uint8_t *p,unsigned n)
{uint64_t v=0;for(unsigned i=0;i<n;++i)v|=(uint64_t)p[i]<<(8*i);return v;}
static void put(uint8_t *p,uint64_t v,unsigned n)
{for(unsigned i=0;i<n;++i)p[i]=(uint8_t)(v>>(8*i));}
static bool filled(const uint8_t *p,size_t n,uint8_t value)
{for(size_t i=0;i<n;++i)if(p[i]!=value)return false;return true;}
static bool overlap(const void *a,size_t an,const void *b,size_t bn)
{if(!an||!bn)return false;uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;return x<=y?y-x<an:x-y<bn;}
static bool is_control(const struct aura_storage *s,uint32_t b)
{return b==s->config.blocks[0]||b==s->config.blocks[1];}
static uint16_t count(const struct aura_storage *s)
{return (uint16_t)get(s->snapshot+COUNT_AT,2);}
static uint8_t *extent(struct aura_storage *s,unsigned i)
{return s->snapshot+AURA_STORAGE_HEADER_BYTES+i*AURA_STORAGE_EXTENT_BYTES;}
static int fail(struct aura_storage *s,int error)
{s->ready=false;return s->fault=error;}

int aura_storage_capture_id(const uint8_t device[16],const uint8_t incarnation[16],
                            uint64_t generation,uint8_t capture[16])
{
    if(!device||!incarnation||!capture||!generation||filled(device,16,0)||filled(incarnation,16,0))
        return AURA_STORAGE_ARGUMENT;
    static const uint8_t domain[]="AURA-A04-CAPTURE-v1";
    uint8_t message[sizeof(domain)+40],digest[32];
    memcpy(message,domain,sizeof(domain));memcpy(message+sizeof(domain),device,16);
    memcpy(message+sizeof(domain)+16,incarnation,16);put(message+sizeof(domain)+32,generation,8);
    aura_archive_sha256(message,sizeof(message),digest);memcpy(capture,digest,16);return 0;
}

static int validate_state(struct aura_storage *s)
{
    const uint8_t *p=s->snapshot;
    if(s->bytes<AURA_STORAGE_HEADER_BYTES||s->bytes>s->capacity||memcmp(p,"AST1",4)||p[4]!=1||
       p[5]>PHASE_GRANTED||p[6]||p[7]||!filled(p+332,20,0)||
       memcmp(p+8,s->authority.device_id,16)||memcmp(p+24,s->authority.storage_incarnation,16)||
       memcmp(p+40,s->authority.owner_id,16)||get(p+56,8)!=s->authority.owner_generation)
        return AURA_STORAGE_STATE;
    uint16_t n=count(s);uint64_t floor=get(p+FLOOR_AT,8);
    if(n>s->io.data.blocks-2||s->bytes!=AURA_STORAGE_HEADER_BYTES+(size_t)n*AURA_STORAGE_EXTENT_BYTES)
        return AURA_STORAGE_STATE;
    if(floor){
        struct aura_release_authorization authorization;
        int r=aura_release_authenticate(&s->authority,p+RELEASE_AT,182,p+RELEASE_AT+56,94,&authorization);
        if(r||authorization.release_sequence!=floor||authorization.receipt[5]!=AURA_ARCHIVE_FINALIZED)
            return AURA_STORAGE_STATE;
    }else if(!filled(p+RELEASE_AT,182,0))return AURA_STORAGE_STATE;
    if(p[5]==PHASE_IDLE)return !n&&filled(p+MANIFEST_AT,68,0)?0:AURA_STORAGE_STATE;
    if(!floor||!n)return AURA_STORAGE_STATE;
    struct aura_archive_writer view={0};
    if(aura_archive_replay(&view,p+MANIFEST_AT,68)||
       memcmp(p+MANIFEST_AT+8,p+RELEASE_AT+62,32))return AURA_STORAGE_STATE;
    uint64_t generation=get(extent(s,0)+36,8);uint8_t id[16],seen[128]={0};
    if(!generation||generation>get(p+COUNTER_AT,8)||
       aura_storage_capture_id(s->authority.device_id,s->authority.storage_incarnation,generation,id)||
       memcmp(id,p+MANIFEST_AT+24,16))return AURA_STORAGE_IDENTITY;
    for(unsigned i=0;i<n;++i){
        const uint8_t *e=extent(s,i);uint16_t b=(uint16_t)get(e,2);
        if(b>=s->io.data.blocks||is_control(s,b)||get(e+2,2)!=i||get(e+36,8)!=generation||
           filled(e+4,32,0)||(seen[b/8]&(1u<<(b%8))))return AURA_STORAGE_STATE;
        seen[b/8]|=(uint8_t)(1u<<(b%8));
    }
    return 0;
}
static int reload(struct aura_storage *s)
{
    if(!s||!s->ready)return s?(s->fault?s->fault:AURA_STORAGE_STATE):AURA_STORAGE_ARGUMENT;
    size_t bytes=0;int r=aura_control_load(s->control,s->snapshot,s->capacity,&bytes);
    if(r)return fail(s,r);s->bytes=bytes;
    r=validate_state(s);return r?fail(s,r):0;
}
static bool fenced(struct aura_storage *s,uint32_t b)
{
    if(is_control(s,b))return true;
    if(s->snapshot[5]!=PHASE_GRANTED)return false;
    for(unsigned i=0;i<count(s);++i)if(get(extent(s,i),2)==b)return true;
    return false;
}
static int data_bad(void *user,uint32_t b,bool *bad)
{
    struct aura_storage *s=user;if(!bad||b>=s->io.data.blocks)return AURA_NAND_BAD_ARGUMENT;
    if(fenced(s,b)){*bad=true;return 0;}return s->io.data.bad(s->io.data.user,b,bad);
}
static int data_read(void *user,uint32_t page,uint16_t column,uint8_t *out,size_t bytes)
{
    struct aura_storage *s=user;
    if(page>=s->io.data.blocks*64||fenced(s,page/64))return AURA_NAND_BAD_BLOCK;
    return s->io.data.read(s->io.data.user,page,column,out,bytes);
}
static int data_program(void *user,uint32_t page,const uint8_t *data)
{
    struct aura_storage *s=user;
    if(!s->ready||s->snapshot[5]!=PHASE_IDLE||page>=s->io.data.blocks*64||fenced(s,page/64))return AURA_NAND_BAD_BLOCK;
    return s->io.data.program(s->io.data.user,page,data);
}
static int data_erase(void *user,uint32_t b)
{
    struct aura_storage *s=user;
    if(!s->ready||s->snapshot[5]!=PHASE_IDLE||b>=s->io.data.blocks||fenced(s,b))return AURA_NAND_BAD_BLOCK;
    return s->io.data.erase(s->io.data.user,b);
}
static int mount_journal(struct aura_storage *s)
{
    struct aura_nand_io io={s,s->io.data.blocks,data_read,data_program,data_erase,data_bad};
    int r=aura_journal_mount(s->journal,io);
    if(!r)r=aura_journal_set_owned_profile(s->journal,s->authority.storage_incarnation);
    if(!r&&s->journal->last_bound_generation>get(s->snapshot+COUNTER_AT,8))r=AURA_STORAGE_IDENTITY;
    return r?fail(s,r):0;
}
static int initialize(struct aura_storage *s,struct aura_storage_io io,
    const struct aura_control_config *config,const struct aura_release_auth_context *authority,
    struct aura_journal *journal,struct aura_control *control,uint8_t *snapshot,size_t capacity)
{
    if(!s||!config||!authority||!journal||!control||!snapshot)return AURA_STORAGE_ARGUMENT;
    struct aura_release_auth_context trusted;struct aura_control_config selected;
    memcpy(&trusted,authority,sizeof(trusted));memcpy(&selected,config,sizeof(selected));
    if(capacity<AURA_STORAGE_STATE_BYTES||
       !io.data.read||!io.data.program||!io.data.erase||!io.data.bad||io.data.blocks<3||io.data.blocks>1024||
       io.control.nand.blocks!=io.data.blocks||selected.blocks[0]>=io.data.blocks||
       selected.blocks[1]>=io.data.blocks||selected.blocks[0]==selected.blocks[1]||
       memcmp(selected.domain,trusted.storage_incarnation,16)||!trusted.owner_generation||
       filled(trusted.device_id,16,0)||filled(trusted.storage_incarnation,16,0)||
       filled(trusted.owner_id,16,0)||filled(trusted.key,32,0)||
       overlap(s,sizeof(*s),journal,sizeof(*journal))||overlap(s,sizeof(*s),control,sizeof(*control))||
       overlap(journal,sizeof(*journal),control,sizeof(*control))||
       overlap(snapshot,capacity,s,sizeof(*s))||overlap(snapshot,capacity,journal,sizeof(*journal))||
       overlap(snapshot,capacity,control,sizeof(*control))||overlap(snapshot,capacity,authority,sizeof(*authority))||
       overlap(snapshot,capacity,config,sizeof(*config)))return AURA_STORAGE_ARGUMENT;
    memset(s,0,sizeof(*s));s->authority=trusted;s->config=selected;s->io=io;
    s->journal=journal;s->control=control;s->snapshot=snapshot;s->capacity=capacity;return 0;
}
int aura_storage_open(struct aura_storage *s,struct aura_storage_io io,
    const struct aura_control_config *config,const struct aura_release_auth_context *authority,
    struct aura_journal *journal,struct aura_control *control,uint8_t *snapshot,size_t capacity)
{
    int r=initialize(s,io,config,authority,journal,control,snapshot,capacity);if(r)return r;
    r=aura_control_open(control,io.control,&s->config);if(r)return fail(s,r);
    s->ready=true;r=reload(s);if(r)return r;return mount_journal(s);
}
int aura_storage_provision(struct aura_storage *s,struct aura_storage_io io,
    const struct aura_control_config *config,const struct aura_release_auth_context *authority,
    struct aura_journal *journal,struct aura_control *control,uint8_t *snapshot,size_t capacity)
{
    int r=initialize(s,io,config,authority,journal,control,snapshot,capacity);if(r)return r;
    /* This is a new-media operation, never a reset/migration of existing audio. */
    for(uint32_t b=0;b<io.data.blocks;++b){
        if(is_control(s,b))continue;
        bool bad=false;r=io.data.bad(io.data.user,b,&bad);if(r)return fail(s,r);if(bad)continue;
        for(unsigned page=0;page<64;++page){
            r=io.data.read(io.data.user,b*64+page,0,journal->scratch,2048);
            if(r||!filled(journal->scratch,2048,255))return fail(s,r<0?r:AURA_STORAGE_CHANGED);
        }
    }
    memset(snapshot,0,AURA_STORAGE_HEADER_BYTES);memcpy(snapshot,"AST1",4);snapshot[4]=1;
    memcpy(snapshot+8,s->authority.device_id,16);memcpy(snapshot+24,s->authority.storage_incarnation,16);
    memcpy(snapshot+40,s->authority.owner_id,16);put(snapshot+56,s->authority.owner_generation,8);
    s->bytes=AURA_STORAGE_HEADER_BYTES;
    r=aura_control_provision(control,io.control,&s->config,snapshot,s->bytes);if(r)return fail(s,r);
    s->ready=true;return mount_journal(s);
}

static int collect_manifest(void *user,uint64_t offset,const uint8_t *wire,size_t bytes)
{if(offset||bytes!=68)return AURA_STORAGE_ARGUMENT;memcpy(user,wire,68);return 0;}
int aura_storage_prepare_capture(struct aura_storage *s,
    const struct aura_archive_manifest *settings,struct aura_archive_manifest *manifest)
{
    if(!s||!settings||!manifest||overlap(manifest,sizeof(*manifest),s,sizeof(*s))||
       overlap(manifest,sizeof(*manifest),s->journal,sizeof(*s->journal))||
       overlap(manifest,sizeof(*manifest),s->control,sizeof(*s->control))||
       overlap(manifest,sizeof(*manifest),s->snapshot,s->capacity))return AURA_STORAGE_ARGUMENT;
    /* Reload overwrites caller-owned snapshot/control scratch. Copy input first;
     * the output must not overwrite any private context, even after success. */
    struct aura_archive_manifest next;memcpy(&next,settings,sizeof(next));
    int r=reload(s);if(r)return r;
    if(s->snapshot[5]!=PHASE_IDLE||s->journal->active>=0||s->journal->fault||s->journal->binding_pending)return AURA_STORAGE_BUSY;
    uint64_t generation=get(s->snapshot+COUNTER_AT,8);if(generation==UINT64_MAX)return AURA_RELEASE_EXHAUSTED;
    ++generation;uint8_t wire[68];
    memcpy(next.device_id,s->authority.device_id,16);
    r=aura_storage_capture_id(next.device_id,s->authority.storage_incarnation,generation,next.capture_id);if(r)return r;
    struct aura_archive_writer writer;
    r=aura_archive_begin(&writer,&next,collect_manifest,wire);if(r)return r;
    put(s->snapshot+COUNTER_AT,generation,8);
    r=aura_control_store(s->control,s->snapshot,s->bytes);if(r)return fail(s,r);
    r=aura_journal_bind_capture(s->journal,wire,generation);if(r)return fail(s,r);
    *manifest=next;return 0;
}
int aura_storage_cancel_prepared(struct aura_storage *s)
{
    int r=reload(s);if(r)return r;
    if(s->snapshot[5]!=PHASE_IDLE)return AURA_STORAGE_BUSY;
    return aura_journal_discard_binding(s->journal);
}

int aura_storage_request_release(struct aura_storage *s,const uint8_t *wire,size_t bytes)
{
    if(!s||!wire||bytes!=182)return AURA_STORAGE_ARGUMENT;
    uint8_t command[182];memcpy(command,wire,182);
    int r=reload(s);if(r)return r;
    struct aura_release_authorization authorization;
    r=aura_release_authenticate(&s->authority,command,182,command+56,94,&authorization);if(r)return r;
    if(authorization.receipt[5]!=AURA_ARCHIVE_FINALIZED)return AURA_STORAGE_UNSUPPORTED;
    uint64_t floor=get(s->snapshot+FLOOR_AT,8);
    if(authorization.release_sequence==floor&&!memcmp(command,s->snapshot+RELEASE_AT,182))
        return s->snapshot[5]==PHASE_GRANTED?AURA_STORAGE_PENDING:AURA_STORAGE_ALREADY_DONE;
    if(s->snapshot[5]!=PHASE_IDLE||s->journal->active>=0||s->journal->fault||s->journal->binding_pending)return AURA_STORAGE_BUSY;
    r=aura_release_validate_next(authorization.release_sequence,floor);if(r)return r;
    if(!s->io.erase_released)return AURA_STORAGE_UNSUPPORTED;
    unsigned index=0;
    for(;index<s->journal->count;++index)
        if(!memcmp(s->journal->captures[index].manifest+8,authorization.receipt+6,32))break;
    if(index==s->journal->count)return AURA_STORAGE_IDENTITY;
    struct aura_journal_allocation_identity identity;
    r=aura_journal_get_allocation_identity(s->journal,(uint16_t)index,&identity);if(r)return r;
    uint8_t expected[94],id[16];r=aura_journal_receipt(s->journal,(uint16_t)index,expected);if(r)return r;
    r=aura_release_authenticate(&s->authority,command,182,expected,94,&authorization);if(r)return r;
    if(!identity.owned||identity.version!=2||memcmp(identity.incarnation,s->authority.storage_incarnation,16)||
       !identity.allocation_generation||identity.allocation_generation>get(s->snapshot+COUNTER_AT,8))return AURA_STORAGE_IDENTITY;
    r=aura_storage_capture_id(s->authority.device_id,identity.incarnation,identity.allocation_generation,id);if(r)return r;
    if(memcmp(id,authorization.receipt+22,16))return AURA_STORAGE_IDENTITY;
    struct aura_journal_capture *capture=&s->journal->captures[index];
    if(!capture->blocks||capture->blocks>s->io.data.blocks-2||
       AURA_STORAGE_HEADER_BYTES+(size_t)capture->blocks*AURA_STORAGE_EXTENT_BYTES>s->capacity)
        return fail(s,AURA_STORAGE_CHANGED);
    uint16_t b=capture->first_block;
    for(unsigned part=0;part<capture->blocks;++part){
        if(b>=s->io.data.blocks||is_control(s,b)||s->journal->owner[b]!=index)return fail(s,AURA_STORAGE_CHANGED);
        r=s->io.data.read(s->io.data.user,b*64+2,0,s->journal->scratch,2048);if(r<0)return fail(s,r);
        const uint8_t *h=s->journal->scratch;
        uint32_t previous=part?(uint32_t)get(extent(s,part-1),2):UINT32_MAX;
        if(memcmp(h,"A4NH",4)||h[4]!=2||h[5]||get(h+6,2)!=256||get(h+8,4)!=b||
           get(h+12,4)!=previous||get(h+16,4)!=part||memcmp(h+60,capture->manifest,68)||
           memcmp(h+28,capture->manifest+8,32)||memcmp(h+222,identity.incarnation,16)||
           get(h+238,8)!=identity.allocation_generation||!filled(h+246,6,0)||
           get(h+252,4)!=aura_archive_crc32(h,252)||!filled(h+256,1792,255))return fail(s,AURA_STORAGE_CHANGED);
        uint8_t *e=extent(s,part);put(e,b,2);put(e+2,part,2);
        aura_archive_sha256(s->journal->scratch,2048,e+4);put(e+36,identity.allocation_generation,8);
        b=s->journal->next_block[b];
    }
    if(b!=AURA_JOURNAL_NONE)return fail(s,AURA_STORAGE_CHANGED);
    s->snapshot[5]=PHASE_GRANTED;put(s->snapshot+FLOOR_AT,authorization.release_sequence,8);
    memcpy(s->snapshot+RELEASE_AT,command,182);put(s->snapshot+COUNT_AT,capture->blocks,2);
    memcpy(s->snapshot+MANIFEST_AT,capture->manifest,68);
    s->bytes=AURA_STORAGE_HEADER_BYTES+(size_t)capture->blocks*AURA_STORAGE_EXTENT_BYTES;
    r=validate_state(s);if(r)return fail(s,r);
    r=aura_control_store(s->control,s->snapshot,s->bytes);if(r)return fail(s,r);
    s->progress=0;r=mount_journal(s);return r?r:AURA_STORAGE_PENDING;
}

/* A durable grant fences its original extents across reboot. Interrupted erase
 * can remove any surviving identity, but an intact conflicting identity cannot
 * be explained by that erase. Inspect every page, even past erased/torn gaps.
 * This cannot identify a wholly damaged replacement or defeat raw flash rollback;
 * exclusive serialized ownership remains a required part of the contract. */
static int check_released_extent(struct aura_storage *s,const uint8_t *e)
{
    uint16_t b=(uint16_t)get(e,2),part=(uint16_t)get(e+2,2);
    const uint8_t *ids=s->snapshot+MANIFEST_AT+8;
    uint8_t *page=s->journal->scratch;
    for(unsigned n=0;n<64;++n){
        int r=s->io.data.read(s->io.data.user,b*64+n,0,page,2048);if(r<0)return r;
        if(filled(page,2048,255))continue;
        if(n<2)return AURA_STORAGE_CHANGED; /* Main areas were never programmed. */
        if(n==2){
            uint8_t digest[32];aura_archive_sha256(page,2048,digest);
            if(memcmp(digest,e+4,32)&&get(page+252,4)==aura_archive_crc32(page,252))
                return AURA_STORAGE_CHANGED;
            if(!filled(page+256,1792,255))return AURA_STORAGE_CHANGED;
        }else if(n==63){
            if(!filled(page+256,1792,255))return AURA_STORAGE_CHANGED;
            if(get(page+252,4)!=aura_archive_crc32(page,252))continue;
            if(memcmp(page,"A4NC",4)||page[4]!=2||page[5]||get(page+6,2)!=256||
               get(page+8,4)!=b||get(page+12,4)!=part||get(page+16,2)>60||
               !filled(page+18,2,0)||memcmp(page+28,"ACK3",4)||page[32]!=3||
               page[33]!=(part+1==count(s)?AURA_ARCHIVE_FINALIZED:0)||
               memcmp(page+34,ids,32)||memcmp(page+122,s->authority.storage_incarnation,16)||
               get(page+138,8)!=get(e+36,8)||!filled(page+146,106,0))
                return AURA_STORAGE_CHANGED;
        }else{
            if(get(page+2044,4)!=aura_archive_crc32(page,2044))continue;
            size_t used=(size_t)get(page+56,2);
            if(memcmp(page,"A4ND",4)||page[4]!=1||page[5]||get(page+6,2)!=64||
               get(page+8,4)!=b||get(page+12,4)!=part||memcmp(page+24,ids,32)||
               !used||used>1980||!get(page+58,2)||get(page+60,4)||
               !filled(page+64+used,1980-used,255))return AURA_STORAGE_CHANGED;
        }
    }
    return 0;
}
int aura_storage_release_step(struct aura_storage *s)
{
    int r=reload(s);if(r)return r;
    if(s->snapshot[5]!=PHASE_GRANTED)return AURA_STORAGE_ALREADY_DONE;
    if(!s->io.erase_released)return AURA_STORAGE_UNSUPPORTED;
    if(s->journal->active>=0||s->progress>=count(s))return fail(s,AURA_STORAGE_STATE);
    const uint8_t *e=extent(s,s->progress);uint16_t b=(uint16_t)get(e,2);
    bool bad=false;r=s->io.data.bad(s->io.data.user,b,&bad);if(r||bad)return fail(s,r?r:AURA_NAND_BAD_BLOCK);
    r=check_released_extent(s,e);if(r)return fail(s,r);
    uint8_t *page=s->journal->scratch;
    r=s->io.erase_released(s->io.release_user,b);if(r)return fail(s,r);
    for(unsigned n=0;n<64;++n){
        r=s->io.data.read(s->io.data.user,b*64+n,0,page,2048);
        if(r||!filled(page,2048,255))return fail(s,r<0?r:AURA_STORAGE_CHANGED);
    }
    if(++s->progress<count(s))return AURA_STORAGE_PENDING;
    s->snapshot[5]=PHASE_IDLE;put(s->snapshot+COUNT_AT,0,2);memset(s->snapshot+MANIFEST_AT,0,68);
    s->bytes=AURA_STORAGE_HEADER_BYTES;
    r=aura_control_store(s->control,s->snapshot,s->bytes);if(r)return fail(s,r);
    s->progress=0;r=mount_journal(s);return r?r:AURA_STORAGE_ALREADY_DONE;
}
