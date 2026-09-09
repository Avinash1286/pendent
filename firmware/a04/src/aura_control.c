/* SPDX-License-Identifier: MIT */
#include "aura_control.h"
#include "aura_archive.h"
#include <string.h>

#define NONE UINT16_MAX
#define BODY_OFFSET 124u
#define CRC_OFFSET 2044u

enum slot_state { SLOT_BLANK, SLOT_VALID, SLOT_PARTIAL };
struct slot_info {
    enum slot_state state;
    uint64_t generation, parent;
    uint32_t bytes;
    uint16_t bodies;
    uint8_t digest[32], parent_digest[32];
    bool commit_valid, header_valid, header_blank, header_matches_commit;
    bool read_failed, corrected, mixed_generation;
};

static uint64_t get(const uint8_t *p, unsigned n)
{ uint64_t v=0; for(unsigned i=0;i<n;++i)v|=(uint64_t)p[i]<<(8*i); return v; }
static void put(uint8_t *p, uint64_t v, unsigned n)
{ for(unsigned i=0;i<n;++i)p[i]=(uint8_t)(v>>(8*i)); }
static bool same(const uint8_t *p, size_t n, uint8_t value)
{ for(size_t i=0;i<n;++i)if(p[i]!=value)return false; return true; }
static void crc(uint8_t *p)
{ put(p+CRC_OFFSET,aura_archive_crc32(p,CRC_OFFSET),4); }
static bool checked(const uint8_t *p)
{ return get(p+CRC_OFFSET,4)==aura_archive_crc32(p,CRC_OFFSET); }
static void hash(const uint8_t *p,uint8_t out[32])
{ aura_archive_sha256(p,2048,out); }
static bool overlaps(const void *left,size_t left_bytes,const void *right,size_t right_bytes)
{
    if(!left_bytes||!right_bytes)return false;
    uintptr_t a=(uintptr_t)left,b=(uintptr_t)right;
    return b>=a ? b-a<left_bytes : a-b<right_bytes;
}
static bool aliases(const struct aura_control *c,const void *p,size_t bytes)
{return overlaps(c,sizeof(*c),p,bytes);}
static int arguments(struct aura_control *c,struct aura_control_io io,
                     const struct aura_control_config *config)
{
    if(!c||!config||!io.nand.read||!io.nand.bad||!io.nand.blocks||io.nand.blocks>1024||
       config->blocks[0]>=io.nand.blocks||config->blocks[1]>=io.nand.blocks||
       config->blocks[0]==config->blocks[1]||same(config->domain,16,0))
        return AURA_CONTROL_BAD_ARGUMENT;
    return 0;
}
static void initialize(struct aura_control *c,struct aura_control_io io,
                       const struct aura_control_config *config)
{
    struct aura_control_config copy=*config;
    memset(c,0,sizeof(*c));c->io=io;c->config=copy;c->current=NONE;
}
static int fail(struct aura_control *c,int error)
{ c->ready=false;return c->fault=error; }
static int read_page(struct aura_control *c,uint16_t block,unsigned n,uint8_t *out)
{
    ++c->reads;
    int r=c->io.nand.read(c->io.nand.user,(uint32_t)block*64+n,0,out,2048);
    if(r==AURA_NAND_CORRECTED)++c->corrected_reads;
    return r;
}
static bool prefix(const struct aura_control *c,const uint8_t *p,
                   unsigned slot,const char *magic,unsigned type)
{
    return !memcmp(p,magic,4)&&p[4]==1&&p[5]==type&&get(p+6,2)==(type==2?BODY_OFFSET:128)&&
        get(p+8,2)==c->config.blocks[slot]&&p[10]==slot&&!p[11]&&
        !memcmp(p+32,c->config.domain,16)&&checked(p);
}
static bool declaration(const struct aura_control *c,const uint8_t *p,
                        unsigned slot,bool commit)
{
    uint64_t generation=get(p+16,8),parent=get(p+24,8);
    uint32_t bytes=(uint32_t)get(p+12,4);
    return prefix(c,p,slot,commit?"A4CC":"A4CH",commit?3:1)&&generation&&
        parent==generation-1&&bytes<=AURA_CONTROL_MAX_BYTES&&
        get(p+80,2)==(bytes+AURA_CONTROL_BODY_BYTES-1)/AURA_CONTROL_BODY_BYTES&&
        (parent?!same(p+48,32,0):same(p+48,32,0))&&
        (commit?(same(p+82,6,0)&&same(p+152,CRC_OFFSET-152,0)):
                 same(p+82,CRC_OFFSET-82,0));
}
static bool body(const struct aura_control *c,const uint8_t *p,unsigned slot,
                 uint64_t generation,uint32_t bytes,unsigned index,
                 const uint8_t previous[32])
{
    uint32_t at=index*AURA_CONTROL_BODY_BYTES;
    size_t take=bytes-at;if(take>AURA_CONTROL_BODY_BYTES)take=AURA_CONTROL_BODY_BYTES;
    return prefix(c,p,slot,"A4CB",2)&&get(p+12,2)==index&&get(p+14,2)==take&&
        get(p+16,8)==generation&&get(p+24,4)==at&&get(p+28,4)==bytes&&
        !memcmp(p+48,previous,32)&&same(p+80,BODY_OFFSET-80,0)&&
        same(p+BODY_OFFSET+take,AURA_CONTROL_BODY_BYTES-take,255);
}

/* Always inspect the entire control block, including unused pages. An intact
 * commit can identify a partially erased OLD block, but cannot make an invalid
 * body into usable authority. It is compared to the newer snapshot's parent. */
static int scan(struct aura_control *c,unsigned slot,struct slot_info *info,uint8_t *out,size_t capacity)
{
    memset(info,0,sizeof(*info));info->state=SLOT_PARTIAL;
    bool bad=false;uint16_t block=c->config.blocks[slot];
    int r=c->io.nand.bad(c->io.nand.user,block,&bad);
    if(r)return r;if(bad)return AURA_NAND_BAD_BLOCK;
    bool blank=true,valid=true;
    uint64_t gen=0,parent=0;uint32_t bytes=0;unsigned count=0;
    uint64_t observed_generation=0;bool observed=false;
    uint8_t header_hash[32]={0},chain[32]={0},parent_hash[32]={0};
    for(unsigned n=0;n<64;++n){
        r=read_page(c,block,n,c->page);
        if(r<0){info->read_failed=true;blank=valid=false;continue;}
        if(r==AURA_NAND_CORRECTED)info->corrected=true;
        bool ff=same(c->page,2048,255);if(!ff)blank=false;
        if(prefix(c,c->page,slot,"A4CH",1)||prefix(c,c->page,slot,"A4CB",2)||prefix(c,c->page,slot,"A4CC",3)){
            uint64_t value=get(c->page+16,8);
            if(observed&&observed_generation!=value)info->mixed_generation=true;
            observed_generation=value;observed=true;
        }
        if(n==2){
            info->header_blank=ff;
            info->header_valid=declaration(c,c->page,slot,false);
            if(!info->header_valid){valid=false;continue;}
            gen=get(c->page+16,8);parent=get(c->page+24,8);
            bytes=(uint32_t)get(c->page+12,4);count=(unsigned)get(c->page+80,2);
            if(out&&bytes>capacity)return AURA_CONTROL_CAPACITY;
            memcpy(parent_hash,c->page+48,32);hash(c->page,header_hash);memcpy(chain,header_hash,32);
        }else if(n>=3&&n<3+count&&info->header_valid){
            if(!body(c,c->page,slot,gen,bytes,n-3,chain)){valid=false;continue;}
            if(out){
                size_t at=(n-3)*AURA_CONTROL_BODY_BYTES,take=(size_t)get(c->page+14,2);
                if(at>capacity||take>capacity-at)return AURA_CONTROL_CAPACITY;
                memcpy(out+at,c->page+BODY_OFFSET,take);
            }
            hash(c->page,chain);
        }else if(n==63){
            info->commit_valid=declaration(c,c->page,slot,true);
            if(!info->commit_valid){valid=false;continue;}
            info->generation=get(c->page+16,8);info->parent=get(c->page+24,8);
            info->bytes=(uint32_t)get(c->page+12,4);info->bodies=(uint16_t)get(c->page+80,2);
            memcpy(info->parent_digest,c->page+48,32);hash(c->page,info->digest);
            info->header_matches_commit=info->header_valid&&info->generation==gen&&info->parent==parent&&
                info->bytes==bytes&&info->bodies==count&&!memcmp(info->parent_digest,parent_hash,32)&&
                !memcmp(c->page+88,header_hash,32);
            if(!info->header_matches_commit||memcmp(c->page+120,chain,32))valid=false;
        }else if(!ff)valid=false;
    }
    if(blank&&!info->corrected)info->state=SLOT_BLANK;
    else if(valid&&info->commit_valid&&!info->read_failed)info->state=SLOT_VALID;
    return 0;
}
static void select_slot(struct aura_control *c,unsigned slot,const struct slot_info *info)
{
    c->current=(uint16_t)slot;c->generation=info->generation;c->bytes=info->bytes;
    memcpy(c->digest,info->digest,32);c->ready=true;c->fault=0;
}
int aura_control_open(struct aura_control *c,struct aura_control_io io,
                      const struct aura_control_config *config)
{
    int r=arguments(c,io,config);if(r)return r;
    initialize(c,io,config);struct slot_info slots[2];
    for(unsigned s=0;s<2;++s){r=scan(c,s,&slots[s],NULL,0);if(r)return fail(c,r);}
    if(slots[0].state==SLOT_BLANK&&slots[1].state==SLOT_BLANK)
        return fail(c,AURA_CONTROL_UNPROVISIONED);
    int current=-1;
    for(unsigned s=0;s<2;++s)if(slots[s].state==SLOT_VALID){
        if(current<0)current=(int)s;
        else{
            unsigned newer=slots[s].generation>slots[current].generation?s:(unsigned)current;
            unsigned older=1-newer;
            if(slots[newer].parent!=slots[older].generation||
               memcmp(slots[newer].parent_digest,slots[older].digest,32))
                return fail(c,AURA_CONTROL_CONFLICT);
            current=(int)newer;
        }
    }
    if(current<0)return fail(c,AURA_CONTROL_INCOMPLETE);
    unsigned other=1-(unsigned)current;
    if(slots[other].state==SLOT_PARTIAL){
        /* A retained OLD commit proves which snapshot an interrupted erase was
         * destroying. Any newer/torn/unknown commit, or unreadable media, blocks
         * authority. No inference from an intact old header alone is allowed. */
        if(!slots[other].commit_valid||slots[other].read_failed||slots[other].mixed_generation||
           (!slots[other].header_blank&&!slots[other].header_matches_commit)||
           slots[current].parent!=slots[other].generation||
           memcmp(slots[current].parent_digest,slots[other].digest,32))
            return fail(c,AURA_CONTROL_INCOMPLETE);
    }
    select_slot(c,(unsigned)current,&slots[current]);return 0;
}
static int blank_block(struct aura_control *c,unsigned slot)
{
    bool bad=false;uint16_t block=c->config.blocks[slot];
    int r=c->io.nand.bad(c->io.nand.user,block,&bad);if(r)return r;if(bad)return AURA_NAND_BAD_BLOCK;
    for(unsigned n=0;n<64;++n){
        r=read_page(c,block,n,c->verify);
        if(r)return r<0?r:AURA_CONTROL_CORRUPT;
        if(!same(c->verify,2048,255))return AURA_NAND_NOT_ERASED;
    }
    return 0;
}
static int erase_inactive(struct aura_control *c,uint32_t block)
{
    if(block>=c->io.nand.blocks||
       (block!=c->config.blocks[0]&&block!=c->config.blocks[1]))return AURA_CONTROL_BAD_ARGUMENT;
    unsigned slot=block==c->config.blocks[0]?0:1;
    if(c->ready&&slot==c->current)return AURA_CONTROL_CONFLICT;
    if(!c->io.erase_control)return AURA_CONTROL_READ_ONLY;
    bool bad=false;int r=c->io.nand.bad(c->io.nand.user,block,&bad);
    if(r)return r;if(bad)return AURA_NAND_BAD_BLOCK;
    ++c->erases;r=c->io.erase_control(c->io.erase_user,block);
    if(r)return r; /* FF cannot prove a lost erase completed. */
    return blank_block(c,slot);
}
static int program(struct aura_control *c,unsigned slot,unsigned n)
{
    ++c->programs;
    int r=c->io.nand.program(c->io.nand.user,(uint32_t)c->config.blocks[slot]*64+n,c->page);
    if(r!=0&&r!=AURA_NAND_UNCERTAIN)return r;
    int check=read_page(c,c->config.blocks[slot],n,c->verify);
    if(check>=0&&!memcmp(c->page,c->verify,2048))return 0;
    return r?r:(check<0?check:AURA_CONTROL_CORRUPT);
}
static void common(struct aura_control *c,unsigned slot,const char *magic,unsigned type,
                   uint64_t generation)
{
    memset(c->page,0,2048);memcpy(c->page,magic,4);c->page[4]=1;c->page[5]=(uint8_t)type;
    put(c->page+6,type==2?BODY_OFFSET:128,2);put(c->page+8,c->config.blocks[slot],2);c->page[10]=(uint8_t)slot;
    put(c->page+16,generation,8);memcpy(c->page+32,c->config.domain,16);
}
static int write_snapshot(struct aura_control *c,unsigned slot,const uint8_t *snapshot,size_t bytes,
                          uint64_t generation,uint64_t parent,const uint8_t parent_hash[32])
{
    unsigned bodies=(unsigned)((bytes+AURA_CONTROL_BODY_BYTES-1)/AURA_CONTROL_BODY_BYTES);
    uint8_t header_hash[32],chain[32];
    common(c,slot,"A4CH",1,generation);put(c->page+12,bytes,4);put(c->page+24,parent,8);
    memcpy(c->page+48,parent_hash,32);put(c->page+80,bodies,2);crc(c->page);hash(c->page,header_hash);
    memcpy(chain,header_hash,32);int r=program(c,slot,2);if(r)return r;
    for(unsigned n=0;n<bodies;++n){
        size_t at=n*AURA_CONTROL_BODY_BYTES,take=bytes-at;if(take>AURA_CONTROL_BODY_BYTES)take=AURA_CONTROL_BODY_BYTES;
        common(c,slot,"A4CB",2,generation);put(c->page+12,n,2);put(c->page+14,take,2);
        put(c->page+24,at,4);put(c->page+28,bytes,4);memcpy(c->page+48,chain,32);
        memcpy(c->page+BODY_OFFSET,snapshot+at,take);
        memset(c->page+BODY_OFFSET+take,255,AURA_CONTROL_BODY_BYTES-take);crc(c->page);
        r=program(c,slot,3+n);if(r)return r;hash(c->page,chain);
    }
    common(c,slot,"A4CC",3,generation);put(c->page+12,bytes,4);put(c->page+24,parent,8);
    memcpy(c->page+48,parent_hash,32);put(c->page+80,bodies,2);
    memcpy(c->page+88,header_hash,32);memcpy(c->page+120,chain,32);crc(c->page);
    uint8_t expected_digest[32];hash(c->page,expected_digest);
    r=program(c,slot,63);if(r)return r;
    struct slot_info info;r=scan(c,slot,&info,NULL,0);if(r)return r;
    if(info.state!=SLOT_VALID||info.generation!=generation||info.parent!=parent||info.bytes!=bytes||
       memcmp(info.parent_digest,parent_hash,32)||memcmp(info.digest,expected_digest,32))return AURA_CONTROL_CORRUPT;
    select_slot(c,slot,&info);return 0;
}
int aura_control_provision(struct aura_control *c,struct aura_control_io io,
                           const struct aura_control_config *config,const uint8_t *snapshot,size_t bytes)
{
    int r=arguments(c,io,config);if(r)return r;
    if(bytes>AURA_CONTROL_MAX_BYTES||(!snapshot&&bytes)||aliases(c,snapshot,bytes))return AURA_CONTROL_BAD_ARGUMENT;
    initialize(c,io,config);
    if(!io.nand.program||!io.erase_control)return fail(c,AURA_CONTROL_READ_ONLY);
    for(unsigned slot=0;slot<2;++slot){r=blank_block(c,slot);if(r)return fail(c,r);}
    r=erase_inactive(c,c->config.blocks[0]);if(r)return fail(c,r);
    uint8_t parent[32]={0};r=write_snapshot(c,0,snapshot,bytes,1,0,parent);
    return r?fail(c,r):0;
}
static int refresh_current(struct aura_control *c)
{
    uint64_t generation=c->generation;uint8_t digest[32];memcpy(digest,c->digest,32);
    struct aura_control_io io=c->io;struct aura_control_config config=c->config;
    uint64_t reads=c->reads,corrected=c->corrected_reads,programs=c->programs,erases=c->erases;
    int r=aura_control_open(c,io,&config);
    c->reads+=reads;c->corrected_reads+=corrected;c->programs+=programs;c->erases+=erases;
    if(r)return r;
    if(c->generation!=generation||memcmp(c->digest,digest,32))return fail(c,AURA_CONTROL_CONFLICT);
    return 0;
}
int aura_control_load(struct aura_control *c,uint8_t *out,size_t capacity,size_t *bytes)
{
    if(!c||!bytes||aliases(c,bytes,sizeof(*bytes))||overlaps(out,capacity,bytes,sizeof(*bytes)))
        return AURA_CONTROL_BAD_ARGUMENT;
    *bytes=0;
    if((!out&&c->bytes)||aliases(c,out,capacity))return AURA_CONTROL_BAD_ARGUMENT;
    if(!c->ready)return c->fault?c->fault:AURA_CONTROL_INCOMPLETE;
    if(capacity<c->bytes)return AURA_CONTROL_CAPACITY;
    int r=refresh_current(c);if(r)return r;
    struct slot_info info;r=scan(c,c->current,&info,out,capacity);
    if(r)return fail(c,r);
    if(info.state!=SLOT_VALID||info.generation!=c->generation||memcmp(info.digest,c->digest,32))
        return fail(c,AURA_CONTROL_CORRUPT);
    *bytes=info.bytes;return 0;
}
int aura_control_store(struct aura_control *c,const uint8_t *snapshot,size_t bytes)
{
    if(!c||bytes>AURA_CONTROL_MAX_BYTES||(!snapshot&&bytes)||aliases(c,snapshot,bytes))return AURA_CONTROL_BAD_ARGUMENT;
    if(!c->ready)return c->fault?c->fault:AURA_CONTROL_INCOMPLETE;
    if(!c->io.nand.program||!c->io.erase_control)return AURA_CONTROL_READ_ONLY;
    if(c->generation==UINT64_MAX)return AURA_CONTROL_EXHAUSTED;
    /* Recheck BOTH slots before erasing anything; the owner must not keep using
     * a stale context after another serialized owner changed the media. */
    uint64_t generation=c->generation;uint8_t parent[32];memcpy(parent,c->digest,32);
    int r=refresh_current(c);if(r)return r;
    unsigned slot=1-c->current;
    r=erase_inactive(c,c->config.blocks[slot]);if(r)return fail(c,r);
    r=write_snapshot(c,slot,snapshot,bytes,generation+1,generation,parent);
    return r?fail(c,r):0;
}
