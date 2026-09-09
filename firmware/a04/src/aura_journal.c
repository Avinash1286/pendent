/* SPDX-License-Identifier: MIT
 * Packed, once-programmed-page A04 journal. No populated-block reclamation.
 * Metadata is an index, never proof of old audio. All source export is verified.
 */
#include "aura_journal.h"
#include <string.h>

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
{return !memcmp(p,magic,4)&&p[4]==1&&!p[5]&&get(p+6,2)==256&&get(p+8,4)==block&&checked(p,256);}
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
    j->prepared=j->current_block=AURA_JOURNAL_NONE;
    for(unsigned b=0;b<1024;++b)j->owner[b]=j->next_block[b]=AURA_JOURNAL_NONE;
    for(uint16_t b=0;b<io.blocks;++b){
        bool bad=false;int r=io.bad(io.user,b,&bad);
        if(r<0)return j->fault=r;
        if(bad){j->block_state[b]=AURA_BLOCK_EXCLUDED;continue;}
        r=read_at(j,b*64+2,j->scratch,256,true);
        if(r<0){j->block_state[b]=AURA_BLOCK_QUARANTINED;continue;}
        if(erased(j->scratch,256)){j->block_state[b]=AURA_BLOCK_FREE;continue;}
        if(!meta(j->scratch,"A4NH",b)||!zero(j->scratch+222,30)||!valid_manifest(j->scratch+60)){
            j->block_state[b]=AURA_BLOCK_QUARANTINED;continue;
        }
        uint8_t *h=j->scratch;
        int index=capture_index(j,h+60);
        if(index<0){
            if(j->count==128)return j->fault=AURA_JOURNAL_FULL;
            index=j->count++;struct aura_journal_capture *c=&j->captures[index];
            memcpy(c->manifest,h+60,68);c->first_block=c->last_block=b;
        }
        struct aura_journal_capture *c=&j->captures[index];
        uint32_t part=(uint32_t)get(h+16,4),previous=(uint32_t)get(h+12,4);
        if(memcmp(c->manifest,h+60,68)||memcmp(h+28,c->manifest+8,32)||
           part!=c->blocks||(part==0?(previous!=UINT32_MAX||get(h+20,8)!=0):previous!=c->last_block))
            c->metadata_fault=true;
        if(c->blocks)j->next_block[c->last_block]=b;
        c->last_block=b;++c->blocks;j->owner[b]=(uint16_t)index;j->block_state[b]=AURA_BLOCK_OWNED;
        /* Checkpoint declarations are deliberately NOT copied into committed_receipt. */
        r=read_at(j,b*64+63,j->scratch,256,true);
        if(r<0)c->metadata_fault=true;
        else if(!erased(j->scratch,256)&&checked(j->scratch,256)&&!meta(j->scratch,"A4NC",b))c->metadata_fault=true;
    }
    /* A damaged continuation identity must not hide a valid checkpoint that
     * declares additional committed audio. Do this after building the catalog
     * so association does not depend on physical discovery order. */
    for(uint16_t b=0;b<io.blocks;++b){
        if(j->block_state[b]!=AURA_BLOCK_FREE&&j->block_state[b]!=AURA_BLOCK_QUARANTINED)continue;
        int r=read_at(j,b*64+63,j->scratch,256,true);
        if(j->block_state[b]==AURA_BLOCK_FREE&&!r&&erased(j->scratch,256))continue;
        j->block_state[b]=AURA_BLOCK_QUARANTINED;bool associated=false;
        if(!r&&meta(j->scratch,"A4NC",b)&&!memcmp(j->scratch+28,"ACK3",4)&&
           j->scratch[32]==3&&checked(j->scratch+28,94)){
            for(unsigned i=0;i<j->count;++i)if(!memcmp(j->captures[i].manifest+8,j->scratch+34,32)){
                j->captures[i].metadata_fault=true;j->owner[b]=(uint16_t)i;associated=true;break;
            }
        }
        if(!associated)++j->unassociated_blocks;
    }
    return 0;
}

int aura_journal_prepare(struct aura_journal *j)
{
    if(!j||j->fault)return j?j->fault:AURA_NAND_BAD_ARGUMENT;
    if(j->prepared!=AURA_JOURNAL_NONE)return 0;
    uint16_t b=j->allocation_cursor;
    while(b<j->io.blocks&&j->block_state[b]!=AURA_BLOCK_FREE)++b;
    j->allocation_cursor=b<j->io.blocks?(uint16_t)(b+1):b;
    if(b>=j->io.blocks)return AURA_JOURNAL_FULL;
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
    int r=j->io.program(j->io.user,at,page);
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
    if(j->active<0){
        if(bytes!=68||offset||memcmp(wire,"AUR3",4)||!valid_manifest(wire))return AURA_JOURNAL_CONFLICT;
        if(capture_index(j,wire)>=0)return AURA_JOURNAL_CONFLICT;
        if(j->count>=128)return AURA_JOURNAL_FULL;
        if(j->prepared==AURA_JOURNAL_NONE){int r=aura_journal_prepare(j);if(r)return r;}
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

/* No first-gap shortcut: remaining data slots/checkpoint/continuations are
 * inspected, even if the last valid archive record was a terminal seal. */
static int scan(struct aura_journal *j,uint16_t index,struct aura_archive_writer *view,
                 aura_archive_commit output,void *user)
{
    struct aura_journal_capture *c=&j->captures[index];
    if(c->metadata_fault)return AURA_JOURNAL_CORRUPT;
    memset(view,0,sizeof(*view));uint16_t b=c->first_block;bool hole=false;uint32_t previous=UINT32_MAX;
    for(unsigned part=0;part<c->blocks;++part){
        if(b>=j->io.blocks||j->owner[b]!=index)return AURA_JOURNAL_CORRUPT;
        uint8_t h[256];int r=read_at(j,b*64+2,h,256,true);if(r)return r;
        if(!meta(h,"A4NH",b)||!zero(h+222,30)||get(h+12,4)!=previous||get(h+16,4)!=part||
           get(h+20,8)!=view->file_offset||memcmp(h+60,c->manifest,68)||hole)return AURA_JOURNAL_CORRUPT;
        if(part){uint8_t ack[94];if(declaration(view,ack)||memcmp(ack,h+128,94))return AURA_JOURNAL_CORRUPT;}
        else if(!zero(h+128,94))return AURA_JOURNAL_CORRUPT;
        unsigned valid_pages=0;
        for(unsigned n=3;n<=62;++n){
            r=read_at(j,b*64+n,j->scratch,2048,false);
            bool blank=!r&&erased(j->scratch,2048);
            bool page_ok=!r&&!blank&&checked(j->scratch,2048);
            if(!page_ok){
                if(hole&&!blank)return AURA_JOURNAL_CORRUPT;
                hole=true;continue;
            }
            if(hole)return AURA_JOURNAL_CORRUPT;
            uint8_t *p=j->scratch;
            size_t used=(size_t)get(p+56,2),records=(size_t)get(p+58,2);
            if(memcmp(p,"A4ND",4)||p[4]!=1||p[5]||get(p+6,2)!=64||get(p+8,4)!=b||
               get(p+12,4)!=part||get(p+16,8)!=view->file_offset||memcmp(p+24,c->manifest+8,32)||
               !used||used>1980||!records||get(p+60,4)||!erased(p+64+used,1980-used))return AURA_JOURNAL_CORRUPT;
            size_t at=0,count=0;
            while(at<used){
                size_t bytes=record_size(p+64+at,used-at);if(!bytes)return AURA_JOURNAL_CORRUPT;
                uint64_t offset=view->file_offset;
                r=aura_archive_replay(view,p+64+at,bytes);if(r)return AURA_JOURNAL_CORRUPT;
                if(output&&(r=output(user,offset,p+64+at,bytes)))return r;
                at+=bytes;++count;
            }
            if(count!=records)return AURA_JOURNAL_CORRUPT;
            ++valid_pages;
        }
        r=read_at(j,b*64+63,h,256,true);if(r<0)return r;
        bool complete=meta(h,"A4NC",b);
        if(!erased(h,256)&&checked(h,256)&&!complete)return AURA_JOURNAL_CORRUPT;
        if(complete){
            uint8_t ack[94];
            if(!zero(h+18,2)||!zero(h+122,130)||get(h+12,4)!=part||get(h+16,2)!=valid_pages||get(h+20,8)!=view->file_offset||
               declaration(view,ack)||memcmp(ack,h+28,94))return AURA_JOURNAL_CORRUPT;
        }
        if(part+1<c->blocks){
            /* Continuation only follows a fully verified closed predecessor. */
            if(!complete||valid_pages!=60||view->status)return AURA_JOURNAL_CORRUPT;
            hole=false;
        }
        previous=b;b=j->next_block[b];
    }
    return view->begun?0:AURA_JOURNAL_NOT_COMMITTED;
}

int aura_journal_verify(struct aura_journal *j,uint16_t index)
{
    if(!j||index>=j->count)return AURA_NAND_BAD_ARGUMENT;
    if(j->active>=0&&!j->fault)return AURA_JOURNAL_BUSY;
    struct aura_archive_writer view;int r=scan(j,index,&view,NULL,NULL);
    struct aura_journal_capture *c=&j->captures[index];
    if(r){c->verification=AURA_JOURNAL_INVALID;return r;}
    if(declaration(&view,c->committed_receipt))return AURA_JOURNAL_NOT_COMMITTED;
    c->committed_wire_bytes=view.file_offset;
    c->verification=view.status==1?AURA_JOURNAL_VERIFIED_FINAL:
        view.status==2?AURA_JOURNAL_VERIFIED_INTERRUPTED:AURA_JOURNAL_VERIFIED_OPEN;
    return 0;
}

int aura_journal_export(struct aura_journal *j,uint16_t index,aura_archive_commit output,void *user)
{
    if(!output)return AURA_NAND_BAD_ARGUMENT;
    int r=aura_journal_verify(j,index);if(r)return r;
    struct aura_archive_writer view;r=scan(j,index,&view,output,user);
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
