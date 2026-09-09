/* SPDX-License-Identifier: MIT
 * Packed, once-programmed-page A04 journal. No populated-block reclamation.
 * Metadata is an index, never proof of old audio. All source export is verified.
 */
#include "aura_journal.h"
#include "aura_journal_cursor.h"
#include <string.h>

/* All journal/storage operations are serialized by their owner. A process-wide
 * counter avoids same-address remount ABA without reading uninitialized RAM. */
static uint64_t export_epoch_counter;
int aura_journal_invalidate_exports(struct aura_journal *j)
{
    if(!j)return AURA_NAND_BAD_ARGUMENT;
    j->export_epoch=0;
    if(export_epoch_counter==UINT64_MAX)return j->fault=AURA_CURSOR_STALE;
    j->export_epoch=++export_epoch_counter;return 0;
}

static uint64_t get(const uint8_t *p,unsigned n)
{uint64_t v=0;for(unsigned i=0;i<n;++i)v|=(uint64_t)p[i]<<(8*i);return v;}
static void put(uint8_t *p,uint64_t v,unsigned n)
{for(unsigned i=0;i<n;++i)p[i]=(uint8_t)(v>>(8*i));}
static bool erased(const uint8_t *p,size_t bytes)
{for(size_t i=0;i<bytes;++i)if(p[i]!=255)return false;return true;}
static bool zero(const uint8_t *p,size_t bytes)
{for(size_t i=0;i<bytes;++i)if(p[i])return false;return true;}
static void checksum(uint8_t *p,size_t bytes)
{put(p+bytes-4,aura_archive_crc32(p,bytes-4),4);}
static bool checked(const uint8_t *p,size_t bytes)
{return get(p+bytes-4,4)==aura_archive_crc32(p,bytes-4);}
static bool meta(const uint8_t *p,const char *magic,uint16_t block)
{return !memcmp(p,magic,4)&&(p[4]==1||p[4]==2)&&!p[5]&&get(p+6,2)==256&&get(p+8,4)==block&&checked(p,256);}
static bool allocation(const uint8_t *p,bool checkpoint,struct aura_journal_allocation_identity *out)
{
    struct aura_journal_allocation_identity id={0};id.version=p[4];
    unsigned at=checkpoint?122:222;
    if(p[4]==1){if(!zero(p+at,252-at))return false;}
    else if(p[4]==2){
        if(zero(p+at,16)||!get(p+at+16,8)||!zero(p+at+24,252-at-24))return false;
        memcpy(id.incarnation,p+at,16);id.allocation_generation=get(p+at+16,8);id.owned=true;
    }else return false;
    if(out)*out=id;return true;
}
static bool same_allocation(const struct aura_journal_allocation_identity *a,
                            const struct aura_journal_allocation_identity *b)
{
    return a->version==b->version&&a->allocation_generation==b->allocation_generation&&
        !memcmp(a->incarnation,b->incarnation,16);
}
static void write_allocation(struct aura_journal *j,uint8_t *p,bool checkpoint)
{
    if(!j->owned_profile)return;
    unsigned at=checkpoint?122:222;p[4]=2;
    memcpy(p+at,j->owned_incarnation,16);put(p+at+16,j->capture_generation,8);
}
static int declaration(const struct aura_archive_writer *view,uint8_t out[94])
{
    /* Private serialization of a state declaration; call sites decide whether
     * it is metadata, a read-verified prefix, or a freshly durable page end. */
    struct aura_archive_writer copy=*view;copy.staging=false;
    return aura_archive_receipt(&copy,out);
}
static int read_at(struct aura_journal *j,uint32_t page,uint8_t *out,size_t bytes,bool metadata)
{
    int r=j->io.read(j->io.user,page,0,out,bytes);
    if(metadata)++j->metadata_reads;else ++j->payload_reads;
    if(r==AURA_NAND_CORRECTED){++j->corrected_reads;return 0;}
    return r;
}
static int capture_index(const struct aura_journal *j,const uint8_t manifest[68])
{
    for(unsigned i=0;i<j->count;++i)
        if(!memcmp(j->captures[i].manifest+8,manifest+8,32))return (int)i;
    return -1;
}
static bool valid_manifest(const uint8_t *wire)
{
    struct aura_archive_writer view={0};
    return aura_archive_replay(&view,wire,68)==0;
}

int aura_journal_mount(struct aura_journal *j,struct aura_nand_io io)
{
    if(!j||!io.read||!io.program||!io.erase||!io.bad||!io.blocks||io.blocks>1024)return AURA_NAND_BAD_ARGUMENT;
    memset(j,0,sizeof(*j));j->io=io;j->active=-1;
    int epoch_result=aura_journal_invalidate_exports(j);if(epoch_result)return epoch_result;
    j->prepared=j->current_block=AURA_JOURNAL_NONE;
    for(unsigned b=0;b<1024;++b)j->owner[b]=j->next_block[b]=AURA_JOURNAL_NONE;
    for(uint16_t b=0;b<io.blocks;++b){
        bool bad=false;int r=io.bad(io.user,b,&bad);
        if(r<0)return j->fault=r;
        if(bad){j->block_state[b]=AURA_BLOCK_EXCLUDED;continue;}
        r=read_at(j,b*64+2,j->scratch,256,true);
        if(r<0){j->block_state[b]=AURA_BLOCK_QUARANTINED;continue;}
        if(erased(j->scratch,256)){j->block_state[b]=AURA_BLOCK_FREE;continue;}
        if(!meta(j->scratch,"A4NH",b)||!allocation(j->scratch,false,NULL)||!valid_manifest(j->scratch+60)){
            j->block_state[b]=AURA_BLOCK_QUARANTINED;continue;
        }
        uint8_t *h=j->scratch;
        int index=capture_index(j,h+60);
        if(index<0){
            if(j->count==128)return j->fault=AURA_JOURNAL_FULL;
            index=j->count++;struct aura_journal_capture *c=&j->captures[index];
            memcpy(c->manifest,h+60,68);c->first_block=c->last_block=AURA_JOURNAL_NONE;
        }
        struct aura_journal_capture *c=&j->captures[index];
        uint32_t part=(uint32_t)get(h+16,4),previous=(uint32_t)get(h+12,4);
        if(memcmp(c->manifest,h+60,68)||memcmp(h+28,c->manifest+8,32)||part>=io.blocks)
            c->metadata_fault=true;
        /* Physical discovery order is unrelated to archive order after the
         * allocator wraps. Collect predecessor claims without sorting parts
         * or allocating another per-block table. Conflicting claims invalidate
         * both captures; no claimant can silently replace an existing link. */
        if(!part){
            if(previous!=UINT32_MAX||get(h+20,8)||c->first_block!=AURA_JOURNAL_NONE)
                c->metadata_fault=true;
            else c->first_block=b;
        }else if(previous>=io.blocks||previous==b)c->metadata_fault=true;
        else if(j->next_block[previous]!=AURA_JOURNAL_NONE){
            c->metadata_fault=true;
            uint16_t other=j->owner[j->next_block[previous]];
            if(other<j->count)j->captures[other].metadata_fault=true;
        }else j->next_block[previous]=b;
        ++c->blocks;j->owner[b]=(uint16_t)index;j->block_state[b]=AURA_BLOCK_OWNED;
    }
    /* A bounded second metadata walk establishes a unique contiguous chain.
     * Count equality plus part/previous checks reject missing heads, orphan
     * parts, branches, cycles and links into another capture. No payload or
     * checkpoint declaration is accepted as a receipt during mount. */
    for(unsigned index=0;index<j->count;++index){
        struct aura_journal_capture *c=&j->captures[index];
        if(c->metadata_fault)continue;
        uint16_t b=c->first_block;uint32_t previous=UINT32_MAX;
        struct aura_journal_allocation_identity expected={0};
        for(unsigned part=0;part<c->blocks;++part){
            if(b>=io.blocks||j->owner[b]!=index){c->metadata_fault=true;break;}
            int r=read_at(j,b*64+2,j->scratch,256,true);
            const uint8_t *h=j->scratch;
            struct aura_journal_allocation_identity id;
            if(r||!meta(h,"A4NH",b)||!allocation(h,false,&id)||get(h+12,4)!=previous||
               get(h+16,4)!=part||memcmp(h+60,c->manifest,68)||memcmp(h+28,c->manifest+8,32)){
                c->metadata_fault=true;break;
            }
            if(!part)expected=id;
            else if(!same_allocation(&expected,&id)){c->metadata_fault=true;break;}
            if(id.owned){
                struct aura_journal_allocation_identity cp;
                r=read_at(j,b*64+63,j->scratch,256,true);
                if(r||(!erased(j->scratch,256)&&checked(j->scratch,256)&&
                   (!meta(j->scratch,"A4NC",b)||!allocation(j->scratch,true,&cp)||!same_allocation(&id,&cp)))){
                    c->metadata_fault=true;break;
                }
            }
            c->last_block=b;previous=b;b=j->next_block[b];
        }
        if(b!=AURA_JOURNAL_NONE)c->metadata_fault=true;
    }
    /* Reconcile every checkpoint after catalog discovery. Even an OWNED block
     * can carry a conflicting checkpoint: a damaged/reclassified identity must
     * not hide evidence of additional committed audio for another capture.
     * Checkpoint declarations are never copied into committed_receipt. */
    for(uint16_t b=0;b<io.blocks;++b){
        if(j->block_state[b]==AURA_BLOCK_EXCLUDED)continue;
        bool owned=j->block_state[b]==AURA_BLOCK_OWNED;
        int r=read_at(j,b*64+63,j->scratch,256,true);
        if(owned&&(r<0||(!erased(j->scratch,256)&&checked(j->scratch,256)&&!meta(j->scratch,"A4NC",b))))
            j->captures[j->owner[b]].metadata_fault=true;
        if(owned&&r<0)continue;
        if(j->block_state[b]==AURA_BLOCK_FREE&&!r&&erased(j->scratch,256))continue;
        if(!owned)j->block_state[b]=AURA_BLOCK_QUARANTINED;
        bool associated=false;
        if(!r&&meta(j->scratch,"A4NC",b)&&!memcmp(j->scratch+28,"ACK3",4)&&
           j->scratch[32]==3&&checked(j->scratch+28,94)){
            for(unsigned i=0;i<j->count;++i)if(!memcmp(j->captures[i].manifest+8,j->scratch+34,32)){
                if(!owned||j->owner[b]!=i){
                    j->captures[i].metadata_fault=true;
                    if(owned)j->captures[j->owner[b]].metadata_fault=true;
                    else j->owner[b]=(uint16_t)i;
                }
                associated=true;break;
            }
            if(owned&&!associated){j->captures[j->owner[b]].metadata_fault=true;++j->unassociated_blocks;}
        }
        /* Check allocation metadata separately from ACK ownership, so an
         * invalid v2 identity cannot hide the other capture's checkpoint. */
        if(owned&&!r&&meta(j->scratch,"A4NC",b)){
            struct aura_journal_allocation_identity cp,head;
            bool valid=allocation(j->scratch,true,&cp);
            if(valid&&cp.version==2){
                r=read_at(j,b*64+2,j->scratch,256,true);
                valid=!r&&meta(j->scratch,"A4NH",b)&&allocation(j->scratch,false,&head)&&same_allocation(&head,&cp);
            }
            if(!valid)j->captures[j->owner[b]].metadata_fault=true;
        }
        if(!owned&&!associated)++j->unassociated_blocks;
    }
    return 0;
}

int aura_journal_set_owned_profile(struct aura_journal *j,const uint8_t incarnation[16])
{
    if(!j||!incarnation||zero(incarnation,16)||!j->io.read||!j->io.blocks||j->io.blocks>1024)
        return AURA_NAND_BAD_ARGUMENT;
    if(j->fault)return j->fault;
    if(j->active>=0||j->binding_pending)return AURA_JOURNAL_BUSY;
    if(j->owned_profile)return memcmp(j->owned_incarnation,incarnation,16)?AURA_JOURNAL_CONFLICT:0;
    uint64_t floor=0;
    for(uint16_t b=0;b<j->io.blocks;++b){
        if(j->block_state[b]==AURA_BLOCK_EXCLUDED)continue;
        for(unsigned cp=0;cp<2;++cp){
            int r=read_at(j,b*64+(cp?63:2),j->scratch,256,true);if(r)return r;
            struct aura_journal_allocation_identity id;
            if(meta(j->scratch,cp?"A4NC":"A4NH",b)&&allocation(j->scratch,cp!=0,&id)&&
               id.owned&&!memcmp(id.incarnation,incarnation,16)&&id.allocation_generation>floor)
                floor=id.allocation_generation;
        }
    }
    int epoch_result=aura_journal_invalidate_exports(j);if(epoch_result)return epoch_result;
    memcpy(j->owned_incarnation,incarnation,16);j->owned_profile=true;j->last_bound_generation=floor;
    return 0;
}
int aura_journal_bind_capture(struct aura_journal *j,const uint8_t manifest[68],uint64_t generation)
{
    if(!j||!manifest||!generation||!valid_manifest(manifest))return AURA_NAND_BAD_ARGUMENT;
    if(j->fault)return j->fault;
    if(!j->owned_profile)return AURA_JOURNAL_CONFLICT;
    if(j->active>=0||j->binding_pending)return AURA_JOURNAL_BUSY;
    if(generation<=j->last_bound_generation||capture_index(j,manifest)>=0)return AURA_JOURNAL_CONFLICT;
    int epoch_result=aura_journal_invalidate_exports(j);if(epoch_result)return epoch_result;
    memcpy(j->bound_manifest,manifest,68);j->bound_generation=j->last_bound_generation=generation;
    j->binding_pending=true;return 0;
}
int aura_journal_discard_binding(struct aura_journal *j)
{
    if(!j)return AURA_NAND_BAD_ARGUMENT;
    if(j->active>=0)return AURA_JOURNAL_BUSY;
    if(j->binding_pending){int r=aura_journal_invalidate_exports(j);if(r)return r;}
    j->binding_pending=false;j->bound_generation=0;memset(j->bound_manifest,0,68);return 0;
}

int aura_journal_prepare(struct aura_journal *j)
{
    if(!j||j->fault)return j?j->fault:AURA_NAND_BAD_ARGUMENT;
    if(!j->io.blocks||j->io.blocks>1024||!j->io.read||!j->io.erase||!j->io.bad)
        return AURA_NAND_BAD_ARGUMENT;
    if(j->prepared!=AURA_JOURNAL_NONE)return 0;
    int epoch_result=aura_journal_invalidate_exports(j);if(epoch_result)return epoch_result;
    uint16_t b=(uint16_t)(j->allocation_cursor%j->io.blocks);
    unsigned visited=0;
    while(visited<j->io.blocks&&j->block_state[b]!=AURA_BLOCK_FREE){
        b=(uint16_t)((b+1)%j->io.blocks);++visited;
    }
    if(visited==j->io.blocks)return AURA_JOURNAL_FULL;
    j->allocation_cursor=(uint16_t)((b+1)%j->io.blocks);
    bool bad=false;int r=j->io.bad(j->io.user,b,&bad);
    if(r<0)return j->fault=r;
    if(bad){j->block_state[b]=AURA_BLOCK_EXCLUDED;return AURA_JOURNAL_RETRY_PREPARE;}
    for(unsigned n=0;n<64;++n){
        r=read_at(j,b*64+n,j->scratch,2048,false);
        if(r<0||!erased(j->scratch,2048)){
            j->block_state[b]=AURA_BLOCK_QUARANTINED;
            ++j->unassociated_blocks;
            return AURA_JOURNAL_RETRY_PREPARE;
        }
    }
    /* All source bytes were checked FF, but a previous interrupted program
     * attempt may still have used a programming cycle. A successful erase is
     * mandatory before reusing this otherwise-blank candidate. */
    r=j->io.erase(j->io.user,b);
    if(r<0){j->block_state[b]=AURA_BLOCK_QUARANTINED;++j->unassociated_blocks;return AURA_JOURNAL_RETRY_PREPARE;}
    for(unsigned n=0;n<64;++n){
        r=read_at(j,b*64+n,j->scratch,2048,false);
        if(r<0||!erased(j->scratch,2048)){
            j->block_state[b]=AURA_BLOCK_QUARANTINED;
            ++j->unassociated_blocks;
            return AURA_JOURNAL_RETRY_PREPARE;
        }
    }
    j->prepared=b;j->block_state[b]=AURA_BLOCK_PREPARED;return 0;
}

static int program(struct aura_journal *j,uint32_t at,const uint8_t *page)
{
    int r=aura_journal_invalidate_exports(j);if(r)return r;
    r=j->io.program(j->io.user,at,page);
    /* Lost completion can be resolved without a second Program Execute. A
     * reported P-FAIL is not converted to success merely because bytes match. */
    if(r==0||r==AURA_NAND_UNCERTAIN){
        int verify=read_at(j,at,j->scratch,2048,false);
        if(!verify&&!memcmp(page,j->scratch,2048))return 0;
        if(!r)r=verify?verify:AURA_JOURNAL_CORRUPT;
    }
    j->block_state[at/64]=AURA_BLOCK_QUARANTINED;
    return j->fault=r;
}

static int open_block(struct aura_journal *j,const uint8_t manifest[68],bool first)
{
    if(j->prepared==AURA_JOURNAL_NONE){int r=aura_journal_prepare(j);if(r)return r==AURA_JOURNAL_FULL?(j->fault=r):r;}
    uint16_t b=j->prepared;uint8_t header[2048];
    memset(header,255,sizeof(header));memset(header,0,256);
    memcpy(header,"A4NH",4);header[4]=1;put(header+6,256,2);put(header+8,b,4);
    struct aura_journal_capture *c=&j->captures[j->active];
    put(header+12,first?UINT32_MAX:c->last_block,4);put(header+16,first?0:c->blocks,4);
    put(header+20,j->page_start_offset,8);memcpy(header+28,manifest+8,32);memcpy(header+60,manifest,68);
    if(!first&&declaration(&j->committed,header+128))return AURA_JOURNAL_NOT_COMMITTED;
    write_allocation(j,header,false);
    checksum(header,256);
    int r=program(j,b*64+2,header);j->prepared=AURA_JOURNAL_NONE;if(r)return r;
    if(first)c->first_block=b;else j->next_block[c->last_block]=b;
    c->last_block=b;j->current_part=c->blocks++;j->owner[b]=(uint16_t)j->active;
    j->block_state[b]=AURA_BLOCK_OWNED;j->current_block=b;j->data_pages=0;
    return 0;
}

static int checkpoint(struct aura_journal *j)
{
    if(j->current_block==AURA_JOURNAL_NONE)return 0;
    uint8_t page[2048];memset(page,255,sizeof(page));memset(page,0,256);
    memcpy(page,"A4NC",4);page[4]=1;put(page+6,256,2);put(page+8,j->current_block,4);
    put(page+12,j->current_part,4);put(page+16,j->data_pages,2);put(page+20,j->committed.file_offset,8);
    if(declaration(&j->committed,page+28))return AURA_JOURNAL_NOT_COMMITTED;
    write_allocation(j,page,true);
    checksum(page,256);int r=program(j,j->current_block*64+63,page);
    if(!r)j->current_block=AURA_JOURNAL_NONE;
    return r;
}

int aura_journal_flush(struct aura_journal *j)
{
    if(!j||j->fault)return j?j->fault:AURA_NAND_BAD_ARGUMENT;
    if(!j->staged_bytes)return 0;
    if(j->active<0)return AURA_JOURNAL_CONFLICT;
    struct aura_journal_capture *c=&j->captures[j->active];
    if(j->current_block==AURA_JOURNAL_NONE){int r=open_block(j,c->manifest,false);if(r)return r;}
    uint8_t *p=j->page;memset(p,0,64);
    memcpy(p,"A4ND",4);p[4]=1;put(p+6,64,2);put(p+8,j->current_block,4);put(p+12,j->current_part,4);
    put(p+16,j->page_start_offset,8);memcpy(p+24,c->manifest+8,32);
    put(p+56,j->staged_bytes,2);put(p+58,j->staged_records,2);
    memset(p+64+j->staged_bytes,255,1980-j->staged_bytes);checksum(p,2048);
    int r=program(j,j->current_block*64+3+j->data_pages,p);if(r)return r;
    /* This view was replayed after EACH complete staged record, including any
     * records produced in the middle of one multi-frame aura_opus_push call. */
    j->committed=j->staged;j->committed.staging=false;
    if(aura_archive_receipt(&j->committed,c->committed_receipt))return j->fault=AURA_JOURNAL_CORRUPT;
    c->committed_wire_bytes=j->committed.file_offset;
    c->verification=j->committed.status==1?AURA_JOURNAL_VERIFIED_FINAL:
        j->committed.status==2?AURA_JOURNAL_VERIFIED_INTERRUPTED:AURA_JOURNAL_VERIFIED_OPEN;
    ++j->committed_pages;++j->data_pages;j->staged_bytes=j->staged_records=0;
    j->page_start_offset=j->staged.file_offset;j->staged_since_ms=j->last_service_ms;
    if(j->data_pages==60||j->committed.status){r=checkpoint(j);if(r)return r;}
    if(j->committed.status)j->active=-1;
    return 0;
}

int aura_journal_stage(void *context,uint64_t offset,const uint8_t *wire,size_t bytes)
{
    struct aura_journal *j=context;
    if(!j||!wire||bytes>1301||bytes<26)return AURA_NAND_BAD_ARGUMENT;
    if(j->fault)return j->fault;
    if(!j->service_clock_started)return AURA_NAND_BAD_ARGUMENT;
    int epoch_result=aura_journal_invalidate_exports(j);if(epoch_result)return epoch_result;
    if(j->active<0){
        if(bytes!=68||offset||memcmp(wire,"AUR3",4)||!valid_manifest(wire))return AURA_JOURNAL_CONFLICT;
        if(j->owned_profile&&(!j->binding_pending||memcmp(j->bound_manifest,wire,68))){
            (void)aura_journal_discard_binding(j);return AURA_JOURNAL_CONFLICT;
        }
        if(capture_index(j,wire)>=0)return AURA_JOURNAL_CONFLICT;
        if(j->count>=128)return AURA_JOURNAL_FULL;
        if(j->prepared==AURA_JOURNAL_NONE){int r=aura_journal_prepare(j);if(r)return r;}
        j->capture_generation=j->owned_profile?j->bound_generation:0;
        (void)aura_journal_discard_binding(j);
        memset(&j->staged,0,sizeof(j->staged));memset(&j->committed,0,sizeof(j->committed));
        j->active=j->count++;struct aura_journal_capture *c=&j->captures[j->active];
        memcpy(c->manifest,wire,68);j->staged_bytes=j->staged_records=0;j->page_start_offset=0;
        int r=open_block(j,wire,true);if(r)return r;
    }
    if(offset!=j->staged.file_offset)return AURA_JOURNAL_CONFLICT;
    if(j->staged_bytes+bytes>1980){int r=aura_journal_flush(j);if(r)return r;}
    struct aura_archive_writer candidate=j->staged;
    int r=aura_archive_replay(&candidate,wire,bytes);if(r)return r;
    if(!j->staged_bytes){j->page_start_offset=offset;j->staged_since_ms=j->last_service_ms;}
    memcpy(j->page+64+j->staged_bytes,wire,bytes);j->staged_bytes+=(uint16_t)bytes;++j->staged_records;
    j->staged=candidate;
    /* Apply the current record before deriving a page-end snapshot. The outer
     * producer has not applied its callback result yet, so it is never used as
     * the source of a committed declaration. */
    if((!j->committed.audio_packets&&candidate.audio_packets)||candidate.status||j->staged_bytes==1980)
        return aura_journal_flush(j);
    return 0;
}

int aura_journal_service(struct aura_journal *j,uint64_t now)
{
    if(!j||j->fault)return j?j->fault:AURA_NAND_BAD_ARGUMENT;
    if(j->service_clock_started&&now<j->last_service_ms)return AURA_NAND_BAD_ARGUMENT;
    if(!j->service_clock_started){j->service_clock_started=true;j->staged_since_ms=now;}
    j->last_service_ms=now;
    if(j->staged_bytes&&now-j->staged_since_ms>=400)return aura_journal_flush(j);
    return 0;
}

int aura_journal_receipt(const struct aura_journal *j,uint16_t index,uint8_t out[94])
{
    if(!j||!out||index>=j->count)return AURA_NAND_BAD_ARGUMENT;
    if(j->fault&&j->fault!=AURA_JOURNAL_FULL)return j->fault;
    const struct aura_journal_capture *c=&j->captures[index];
    if(c->verification==AURA_JOURNAL_UNVERIFIED||c->verification==AURA_JOURNAL_INVALID)
        return AURA_JOURNAL_NOT_COMMITTED;
    memcpy(out,c->committed_receipt,94);return 0;
}

static size_t record_size(const uint8_t *p,size_t available)
{
    if(available<4)return 0;
    if(!memcmp(p,"AUR3",4))return available>=68?68:0;
    if(!memcmp(p,"ASE3",4))return available>=120?120:0;
    if(memcmp(p,"AFR3",4)||available<26)return 0;
    size_t size=(size_t)get(p+20,2)+26;return size<=1301&&size<=available?size:0;
}

static void walk_begin(struct aura_journal *j,uint16_t index,
    struct aura_journal_walk *w,struct aura_archive_writer *view)
{
    memset(w,0,sizeof(*w));memset(view,0,sizeof(*view));
    w->block=j->captures[index].first_block;w->previous=UINT32_MAX;w->page=2;
}

/* Shared legacy/cursor validator: one NAND read per call, never a first-gap
 * shortcut. strict_read rejects even the first unreadable data slot; legacy
 * recovery keeps its explicitly tested single-tail-hole semantics. */
static int walk_step(struct aura_journal *j,uint16_t index,struct aura_journal_walk *w,
    struct aura_archive_writer *view,bool strict_read,aura_archive_commit output,void *user)
{
    const struct aura_journal_capture *c=&j->captures[index];
    if(c->metadata_fault)return AURA_JOURNAL_CORRUPT;
    if(w->part==c->blocks){
        if(w->block!=AURA_JOURNAL_NONE||w->previous!=c->last_block)return AURA_JOURNAL_CORRUPT;
        return view->begun?0:AURA_JOURNAL_NOT_COMMITTED;
    }
    uint16_t b=w->block;
    if(w->part>c->blocks||b>=j->io.blocks||j->owner[b]!=index)return AURA_JOURNAL_CORRUPT;
    uint8_t *p=j->scratch;struct aura_journal_allocation_identity id;
    if(w->page==2){
        int r=read_at(j,b*64+2,p,256,true);if(r)return r;
        if(!meta(p,"A4NH",b)||!allocation(p,false,&id)||get(p+12,4)!=w->previous||get(p+16,4)!=w->part||
           get(p+20,8)!=view->file_offset||memcmp(p+60,c->manifest,68)||
           memcmp(p+28,c->manifest+8,32)||w->hole)return AURA_JOURNAL_CORRUPT;
        if(!w->part)w->identity=id;
        else if(!same_allocation(&w->identity,&id))return AURA_JOURNAL_CORRUPT;
        if(w->part){uint8_t ack[94];if(declaration(view,ack)||memcmp(ack,p+128,94))return AURA_JOURNAL_CORRUPT;}
        else if(!zero(p+128,94))return AURA_JOURNAL_CORRUPT;
        w->valid_pages=0;w->page=3;return AURA_CURSOR_PENDING;
    }
    if(w->page<=62){
        int r=read_at(j,b*64+w->page,p,2048,false);
        if(r&&strict_read)return r;
        bool blank=!r&&erased(p,2048);
        bool page_ok=!r&&!blank&&checked(p,2048);
        ++w->page;
        if(!page_ok){
            if(w->hole&&!blank)return AURA_JOURNAL_CORRUPT;
            w->hole=true;return AURA_CURSOR_PENDING;
        }
        if(w->hole)return AURA_JOURNAL_CORRUPT;
        size_t used=(size_t)get(p+56,2),records=(size_t)get(p+58,2);
        if(memcmp(p,"A4ND",4)||p[4]!=1||p[5]||get(p+6,2)!=64||get(p+8,4)!=b||
           get(p+12,4)!=w->part||get(p+16,8)!=view->file_offset||memcmp(p+24,c->manifest+8,32)||
           !used||used>1980||!records||get(p+60,4)||!erased(p+64+used,1980-used))return AURA_JOURNAL_CORRUPT;
        size_t at=0,count=0;
        while(at<used){
            size_t bytes=record_size(p+64+at,used-at);if(!bytes)return AURA_JOURNAL_CORRUPT;
            if(!view->begun&&(bytes!=68||memcmp(p+64+at,c->manifest,68)))return AURA_JOURNAL_CORRUPT;
            uint64_t offset=view->file_offset;
            r=aura_archive_replay(view,p+64+at,bytes);if(r)return AURA_JOURNAL_CORRUPT;
            if(output&&(r=output(user,offset,p+64+at,bytes))){w->callback_failed=true;return r;}
            at+=bytes;++count;
        }
        if(count!=records)return AURA_JOURNAL_CORRUPT;
        ++w->valid_pages;return AURA_CURSOR_PENDING;
    }
    if(w->page!=63)return AURA_JOURNAL_CORRUPT;
    int r=read_at(j,b*64+63,p,256,true);if(r)return r;
    bool complete=meta(p,"A4NC",b);
    if(!erased(p,256)&&checked(p,256)&&!complete)return AURA_JOURNAL_CORRUPT;
    if(complete){
        uint8_t ack[94];
        if(!zero(p+18,2)||!allocation(p,true,&id)||!same_allocation(&w->identity,&id)||
           get(p+12,4)!=w->part||get(p+16,2)!=w->valid_pages||get(p+20,8)!=view->file_offset||
           declaration(view,ack)||memcmp(ack,p+28,94))return AURA_JOURNAL_CORRUPT;
    }
    if(w->part+1<c->blocks){
        if(!complete||w->valid_pages!=60||view->status)return AURA_JOURNAL_CORRUPT;
        w->hole=false;
    }
    w->previous=b;w->block=j->next_block[b];++w->part;w->page=2;
    return AURA_CURSOR_PENDING;
}

static int scan(struct aura_journal *j,uint16_t index,struct aura_archive_writer *view,
    aura_archive_commit output,void *user,struct aura_journal_allocation_identity *identity)
{
    struct aura_journal_walk walk;walk_begin(j,index,&walk,view);
    int r;do{r=walk_step(j,index,&walk,view,false,output,user);}while(r==AURA_CURSOR_PENDING&&!walk.callback_failed);
    if(!r&&identity)*identity=walk.identity;return r;
}

static int verify_capture(struct aura_journal *j,uint16_t index,struct aura_journal_allocation_identity *identity)
{
    if(!j||index>=j->count)return AURA_NAND_BAD_ARGUMENT;
    if(j->active>=0&&!j->fault)return AURA_JOURNAL_BUSY;
    struct aura_journal_allocation_identity id;
    struct aura_archive_writer view;int r=scan(j,index,&view,NULL,NULL,&id);
    struct aura_journal_capture *c=&j->captures[index];
    if(r){c->verification=AURA_JOURNAL_INVALID;return r;}
    if(declaration(&view,c->committed_receipt))return AURA_JOURNAL_NOT_COMMITTED;
    c->committed_wire_bytes=view.file_offset;
    c->verification=view.status==1?AURA_JOURNAL_VERIFIED_FINAL:
        view.status==2?AURA_JOURNAL_VERIFIED_INTERRUPTED:AURA_JOURNAL_VERIFIED_OPEN;
    if(identity)*identity=id;
    return 0;
}
int aura_journal_verify(struct aura_journal *j,uint16_t index)
{return verify_capture(j,index,NULL);}
int aura_journal_get_allocation_identity(struct aura_journal *j,uint16_t index,
                                        struct aura_journal_allocation_identity *identity)
{
    if(!identity)return AURA_NAND_BAD_ARGUMENT;
    return verify_capture(j,index,identity);
}

int aura_journal_export(struct aura_journal *j,uint16_t index,aura_archive_commit output,void *user)
{
    if(!output)return AURA_NAND_BAD_ARGUMENT;
    int r=aura_journal_verify(j,index);if(r)return r;
    struct aura_archive_writer view;r=scan(j,index,&view,output,user,NULL);
    if(r){j->captures[index].verification=AURA_JOURNAL_INVALID;return r;}
    uint8_t ack[94];if(declaration(&view,ack)||memcmp(ack,j->captures[index].committed_receipt,94)){
        j->captures[index].verification=AURA_JOURNAL_INVALID;return AURA_JOURNAL_CORRUPT;
    }
    if(!view.status){
        /* Export-only derived seal. Keep the local physical-prefix receipt OPEN. */
        view.commit=output;view.user=user;view.staging=true;
        r=aura_archive_interrupt(&view);
    }
    return r;
}

enum cursor_phase { CURSOR_EMPTY, CURSOR_VERIFY, CURSOR_READY, CURSOR_REPLAY,
    CURSOR_DRAIN, CURSOR_RECHECK, CURSOR_DONE, CURSOR_FAILED };

static int cursor_fail(struct aura_journal_cursor *c,int error)
{
    c->phase=CURSOR_FAILED;c->error=error;c->buffer_at=c->buffer_bytes=0;
    memset(c->buffer,0,sizeof(c->buffer));return error;
}
static int cursor_source_fail(struct aura_journal_cursor *c,int error)
{
    /* Never damage a replacement capture after remount/preemption. An actual
     * failed source check must not leave a previously cached receipt usable. */
    struct aura_journal *j=c->journal;
    if(j&&c->epoch==j->export_epoch&&c->index<j->count&&
       !memcmp(j->captures[c->index].manifest,c->selected.manifest,68))
        j->captures[c->index].verification=AURA_JOURNAL_INVALID;
    return cursor_fail(c,error);
}
static int cursor_guard(struct aura_journal_cursor *c)
{
    if(!c||!c->journal||c->phase==CURSOR_EMPTY)return AURA_CURSOR_STATE;
    if(c->phase==CURSOR_FAILED)return c->error;
    struct aura_journal *j=c->journal;
    if(!c->epoch||c->epoch!=j->export_epoch)return cursor_fail(c,AURA_CURSOR_STALE);
    if(j->active>=0||j->binding_pending)return cursor_fail(c,AURA_JOURNAL_BUSY);
    if(j->fault)return cursor_fail(c,j->fault);
    if(j->unassociated_blocks||j->count!=c->catalog_count||c->index>=j->count)
        return cursor_source_fail(c,AURA_JOURNAL_CORRUPT);
    const struct aura_journal_capture *source=&j->captures[c->index];
    if(source->metadata_fault||source->first_block!=c->first_block||source->last_block!=c->last_block||
       source->blocks!=c->blocks||memcmp(source->manifest,c->selected.manifest,68))
        return cursor_source_fail(c,AURA_JOURNAL_CORRUPT);
    return 0;
}

int aura_journal_cursor_open(struct aura_journal_cursor *c,struct aura_journal *j,const uint8_t identity[32])
{
    if(!c)return AURA_NAND_BAD_ARGUMENT;
    uint8_t selected_identity[32];if(identity)memcpy(selected_identity,identity,32);
    /* Open replaces only this volatile object, even when selection fails. */
    memset(c,0,sizeof(*c));
    if(!j||!identity||!j->io.read||!j->io.blocks||!j->export_epoch)return AURA_NAND_BAD_ARGUMENT;
    if(j->active>=0||j->binding_pending)return AURA_JOURNAL_BUSY;
    if(j->fault)return j->fault;
    if(j->unassociated_blocks)return AURA_JOURNAL_CORRUPT;
    uint16_t index=0;for(;index<j->count;++index)
        if(!memcmp(j->captures[index].manifest+8,selected_identity,32))break;
    if(index==j->count)return AURA_JOURNAL_NOT_COMMITTED;
    const struct aura_journal_capture *source=&j->captures[index];
    if(source->metadata_fault||!source->blocks)return AURA_JOURNAL_CORRUPT;
    c->journal=j;c->index=index;c->epoch=j->export_epoch;c->catalog_count=j->count;
    c->first_block=source->first_block;c->last_block=source->last_block;c->blocks=source->blocks;
    memcpy(c->selected.manifest,source->manifest,68);c->phase=CURSOR_VERIFY;
    walk_begin(j,index,&c->walk,&c->view);return 0;
}

int aura_journal_cursor_verify_step(struct aura_journal_cursor *c)
{
    int r=cursor_guard(c);if(r)return r;
    if(c->phase==CURSOR_READY)return AURA_CURSOR_READY;
    if(c->phase!=CURSOR_VERIFY)return AURA_CURSOR_STATE;
    r=walk_step(c->journal,c->index,&c->walk,&c->view,true,NULL,NULL);
    if(r==AURA_CURSOR_PENDING)return r;
    if(r)return cursor_source_fail(c,r);
    if(declaration(&c->view,c->selected.physical_receipt))return cursor_source_fail(c,AURA_JOURNAL_NOT_COMMITTED);
    c->selected.physical_bytes=c->view.file_offset;c->selected.derived_seal=!c->view.status;
    c->selected.export_bytes=c->view.file_offset+(c->selected.derived_seal?120u:0u);
    c->selected.allocation=c->walk.identity;c->phase=CURSOR_READY;
    return AURA_CURSOR_READY;
}

int aura_journal_cursor_get_info(struct aura_journal_cursor *c,struct aura_journal_cursor_info *out)
{
    if(!out)return AURA_NAND_BAD_ARGUMENT;
    int r=cursor_guard(c);if(r)return r;
    if(c->phase<CURSOR_READY)return AURA_CURSOR_STATE;
    *out=c->selected;return 0;
}

int aura_journal_cursor_seek(struct aura_journal_cursor *c,uint64_t offset)
{
    int r=cursor_guard(c);if(r)return r;
    if(c->phase!=CURSOR_READY)return AURA_CURSOR_STATE;
    if(offset>c->selected.export_bytes)return AURA_CURSOR_BOUNDARY;
    c->resume_offset=offset;c->phase=CURSOR_REPLAY;
    walk_begin(c->journal,c->index,&c->walk,&c->view);return 0;
}

static int cursor_collect(void *user,uint64_t offset,const uint8_t *wire,size_t bytes)
{
    struct aura_journal_cursor *c=user;
    if(offset>UINT64_MAX-bytes)return AURA_JOURNAL_CORRUPT;
    if(offset<c->resume_offset){
        if(offset+bytes>c->resume_offset)return AURA_CURSOR_BOUNDARY;
        return 0;
    }
    if(bytes>sizeof(c->buffer)-c->buffer_bytes)return AURA_JOURNAL_CORRUPT;
    if(!c->buffer_bytes)c->buffer_offset=offset;
    else if(offset!=c->buffer_offset+c->buffer_bytes)return AURA_JOURNAL_CORRUPT;
    memcpy(c->buffer+c->buffer_bytes,wire,bytes);c->buffer_bytes+=(uint16_t)bytes;
    return 0;
}

static int cursor_matches(const struct aura_journal_cursor *c)
{
    uint8_t ack[94];
    if(declaration(&c->view,ack)||memcmp(ack,c->selected.physical_receipt,94)||
       c->view.file_offset!=c->selected.physical_bytes||
       !same_allocation(&c->walk.identity,&c->selected.allocation))return AURA_JOURNAL_CORRUPT;
    return 0;
}

int aura_journal_cursor_read(struct aura_journal_cursor *c,uint8_t *out,size_t capacity,
    uint64_t *offset,size_t *bytes)
{
    if(bytes)*bytes=0;
    if(!out||!offset||!bytes||!capacity||capacity>AURA_CURSOR_CHUNK_MAX)return AURA_NAND_BAD_ARGUMENT;
    int r=cursor_guard(c);if(r)return r;
    if(c->phase==CURSOR_DONE)return 0;
    if(c->phase<CURSOR_REPLAY)return AURA_CURSOR_STATE;
    if(c->buffer_at==c->buffer_bytes){
        c->buffer_at=c->buffer_bytes=0;
        if(c->phase==CURSOR_DRAIN){
            c->phase=CURSOR_RECHECK;walk_begin(c->journal,c->index,&c->walk,&c->view);
        }
        bool replay=c->phase==CURSOR_REPLAY;
        r=walk_step(c->journal,c->index,&c->walk,&c->view,true,replay?cursor_collect:NULL,c);
        if(r!=AURA_CURSOR_PENDING){
            if(r)return r==AURA_CURSOR_BOUNDARY?cursor_fail(c,r):cursor_source_fail(c,r);
            r=cursor_matches(c);if(r)return cursor_source_fail(c,r);
            if(!replay){c->phase=CURSOR_DONE;return 0;}
            if(c->selected.derived_seal){
                c->view.commit=cursor_collect;c->view.user=c;c->view.staging=true;
                r=aura_archive_interrupt(&c->view);if(r)return r==AURA_CURSOR_BOUNDARY?cursor_fail(c,r):cursor_source_fail(c,r);
            }
            if(c->view.file_offset!=c->selected.export_bytes)return cursor_source_fail(c,AURA_JOURNAL_CORRUPT);
            c->phase=CURSOR_DRAIN;
        }
    }
    if(c->buffer_at==c->buffer_bytes)return AURA_CURSOR_PENDING;
    size_t n=c->buffer_bytes-c->buffer_at;if(n>capacity)n=capacity;
    *offset=c->buffer_offset+c->buffer_at;memcpy(out,c->buffer+c->buffer_at,n);
    c->buffer_at+=(uint16_t)n;*bytes=n;return AURA_CURSOR_DATA;
}

void aura_journal_cursor_cancel(struct aura_journal_cursor *c)
{if(c)memset(c,0,sizeof(*c));}
