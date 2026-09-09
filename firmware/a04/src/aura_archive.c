/* SPDX-License-Identifier: MIT
 * Authored portable SHA-256, CRC32 and AURA revision-3 serialization. All fields
 * are written explicitly; C structure layout is never used as a wire format. */
#include "aura_archive.h"
#include <string.h>

struct hash_state { uint32_t h[8]; uint64_t count; uint8_t block[64]; size_t used; };
static uint32_t rotr(uint32_t x, unsigned n) { return (x >> n) | (x << (32 - n)); }
static uint32_t be32(const uint8_t *p) { return (uint32_t)p[0]<<24 | (uint32_t)p[1]<<16 | (uint32_t)p[2]<<8 | p[3]; }
static void transform(struct hash_state *s, const uint8_t block[64])
{
    static const uint32_t k[64] = {
        0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
        0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
        0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
        0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
        0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
        0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
        0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
        0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
    uint32_t w[64];
    for (unsigned i=0;i<16;++i) w[i]=be32(block+4*i);
    for (unsigned i=16;i<64;++i) {
        uint32_t x=w[i-15], y=w[i-2];
        w[i]=w[i-16]+(rotr(x,7)^rotr(x,18)^(x>>3))+w[i-7]+(rotr(y,17)^rotr(y,19)^(y>>10));
    }
    uint32_t a=s->h[0],b=s->h[1],c=s->h[2],d=s->h[3],e=s->h[4],f=s->h[5],g=s->h[6],h=s->h[7];
    for (unsigned i=0;i<64;++i) {
        uint32_t t1=h+(rotr(e,6)^rotr(e,11)^rotr(e,25))+((e&f)^(~e&g))+k[i]+w[i];
        uint32_t t2=(rotr(a,2)^rotr(a,13)^rotr(a,22))+((a&b)^(a&c)^(b&c));
        h=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;
    }
    s->h[0]+=a;s->h[1]+=b;s->h[2]+=c;s->h[3]+=d;s->h[4]+=e;s->h[5]+=f;s->h[6]+=g;s->h[7]+=h;
}
static void hash_init(struct hash_state *s)
{
    *s=(struct hash_state){.h={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19}};
}
static void hash_update(struct hash_state *s, const uint8_t *data, size_t n)
{
    s->count+=n;
    while (n) {
        size_t take=64-s->used; if(take>n)take=n;
        memcpy(s->block+s->used,data,take); s->used+=take;data+=take;n-=take;
        if(s->used==64){transform(s,s->block);s->used=0;}
    }
}
static void hash_finish(struct hash_state *s,uint8_t out[32])
{
    uint64_t bits=s->count*8;
    s->block[s->used++]=0x80;
    if(s->used>56){memset(s->block+s->used,0,64-s->used);transform(s,s->block);s->used=0;}
    memset(s->block+s->used,0,56-s->used);
    for(unsigned i=0;i<8;++i)s->block[63-i]=(uint8_t)(bits>>(8*i));
    transform(s,s->block);
    for(unsigned i=0;i<32;++i)out[i]=(uint8_t)(s->h[i/4]>>(24-8*(i%4)));
}
void aura_archive_sha256(const uint8_t *data,size_t n,uint8_t out[32])
{
    struct hash_state s;hash_init(&s);hash_update(&s,data,n);hash_finish(&s,out);
}
static void chained(const uint8_t before[32],const uint8_t *wire,size_t n,uint8_t out[32])
{
    struct hash_state s;hash_init(&s);hash_update(&s,before,32);hash_update(&s,wire,n);hash_finish(&s,out);
}
static void put(uint8_t *p,uint64_t v,unsigned n){for(unsigned i=0;i<n;++i)p[i]=(uint8_t)(v>>(8*i));}
uint32_t aura_archive_crc32(const uint8_t *wire,size_t n)
{
    uint32_t v=0xffffffff;
    for(size_t i=0;i<n;++i){v^=wire[i];for(unsigned b=0;b<8;++b)v=(v>>1)^(0xedb88320u & (0u-(v&1)));}
    return v^0xffffffff;
}
static void crc(uint8_t *wire,size_t n){put(wire+n,aura_archive_crc32(wire,n),4);}
static bool nonzero(const uint8_t *p){uint8_t v=0;for(unsigned i=0;i<16;++i)v|=p[i];return v!=0;}

/* pending_kind: 1 audio, 2 bookmark, 3 manifest, 4 seal */
static int commit_pending(struct aura_archive_writer *w)
{
    if(!w->pending_bytes)return 0;
    int result=w->commit(w->user,w->file_offset,w->wire,w->pending_bytes);
    if(result)return result;
    w->file_offset+=w->pending_bytes;
    memcpy(w->chain,w->pending_chain,32);
    if(w->pending_kind==1){++w->next_sequence;++w->audio_packets;w->encoded_samples+=w->manifest.frame_samples;w->encoded_bytes+=w->pending_payload;}
    if(w->pending_kind==2){++w->next_sequence;if(w->pending_bookmark>w->max_bookmark)w->max_bookmark=w->pending_bookmark;}
    if(w->pending_kind==3)w->begun=true;
    if(w->pending_kind==4)w->status=w->wire[5];
    w->pending_bytes=0;w->pending_kind=0;
    return 0;
}
int aura_archive_retry(struct aura_archive_writer *w)
{
    if(!w||!w->commit)return AURA_ARCHIVE_BAD_ARGUMENT;
    if(w->pending_kind==1)return AURA_ARCHIVE_BUSY;
    return commit_pending(w);
}
static int begin(struct aura_archive_writer *w,const struct aura_archive_manifest *m,aura_archive_commit cb,void *user,bool staging)
{
    if(!w)return AURA_ARCHIVE_BAD_ARGUMENT;
    memset(w,0,sizeof(*w));
    if(!m||!cb||!nonzero(m->device_id)||!nonzero(m->capture_id)||m->pre_skip!=40||
       (m->frame_samples!=160&&m->frame_samples!=320)||m->started_at_ms>UINT64_C(4102444800000)||
       m->time_source>1||((m->started_at_ms==0)!=(m->time_source==0)))return AURA_ARCHIVE_BAD_ARGUMENT;
    w->manifest=*m;w->commit=cb;w->user=user;w->staging=staging;
    uint8_t *p=w->wire;memcpy(p,"AUR3",4);p[4]=3;p[5]=2;p[6]=1;
    memcpy(p+8,m->device_id,16);memcpy(p+24,m->capture_id,16);
    put(p+40,16000,4);put(p+44,m->frame_samples,2);put(p+46,m->pre_skip,2);put(p+48,32000,4);
    p[52]=1;p[53]=3;p[54]=m->time_source;put(p+56,m->started_at_ms,8);crc(p,64);
    aura_archive_sha256(p,68,w->pending_chain);w->pending_kind=3;w->pending_bytes=68;
    return commit_pending(w);
}
int aura_archive_begin(struct aura_archive_writer *w,const struct aura_archive_manifest *m,aura_archive_commit cb,void *user)
{return begin(w,m,cb,user,false);}
int aura_archive_begin_staged(struct aura_archive_writer *w,const struct aura_archive_manifest *m,aura_archive_commit cb,void *user)
{return begin(w,m,cb,user,true);}
static int ready(const struct aura_archive_writer *w)
{
    if(!w||!w->commit||!w->begun)return AURA_ARCHIVE_BAD_ARGUMENT;
    if(w->closing||w->status)return AURA_ARCHIVE_CONFLICT;
    if(w->next_sequence>=AURA_ARCHIVE_MAX_RECORDS)return AURA_ARCHIVE_LIMIT;
    return 0;
}
static void header(uint8_t *p,uint8_t kind,uint32_t sequence,uint64_t offset,uint16_t samples,uint16_t bytes)
{
    memcpy(p,"AFR3",4);p[4]=3;p[5]=kind;put(p+6,sequence,4);put(p+10,offset,8);put(p+18,samples,2);put(p+20,bytes,2);
}
int aura_archive_opus_commit(void *context,const struct aura_opus_packet *packet)
{
    struct aura_archive_writer *w=context;
    int result=ready(w);if(result)return result;
    if(!packet||packet->sequence!=w->audio_packets||packet->sample_offset!=w->encoded_samples||
       packet->sample_count!=w->manifest.frame_samples||packet->bytes<2||packet->bytes>1275)return AURA_ARCHIVE_BAD_ARGUMENT;
    unsigned toc=packet->data[0],config=toc>>3;
    if((toc&7)||config<16||config>23||(40u<<(config&3))!=packet->sample_count)return AURA_ARCHIVE_BAD_ARGUMENT;
    if(w->encoded_bytes+packet->bytes>AURA_ARCHIVE_MAX_PAYLOAD_BYTES)return AURA_ARCHIVE_LIMIT;
    if(w->pending_bytes){
        if(w->pending_kind!=1||w->pending_payload!=packet->bytes||memcmp(w->wire+22,packet->data,packet->bytes))return AURA_ARCHIVE_CONFLICT;
        return commit_pending(w);
    }
    header(w->wire,1,w->next_sequence,packet->sample_offset,packet->sample_count,packet->bytes);
    memcpy(w->wire+22,packet->data,packet->bytes);crc(w->wire,22+packet->bytes);
    w->pending_bytes=26+packet->bytes;w->pending_payload=packet->bytes;w->pending_kind=1;
    chained(w->chain,w->wire,w->pending_bytes,w->pending_chain);
    return commit_pending(w);
}
int aura_archive_bookmark(struct aura_archive_writer *w,uint64_t offset)
{
    int result=ready(w);if(result)return result;
    if(offset>w->encoded_samples)return AURA_ARCHIVE_BAD_ARGUMENT;
    if(w->pending_bytes){
        if(w->pending_kind!=2||w->pending_bookmark!=offset)return AURA_ARCHIVE_BUSY;
        return commit_pending(w);
    }
    header(w->wire,2,w->next_sequence,offset,0,0);crc(w->wire,22);
    w->pending_bytes=26;w->pending_kind=2;w->pending_bookmark=offset;
    chained(w->chain,w->wire,26,w->pending_chain);return commit_pending(w);
}
static int terminate(struct aura_archive_writer *w,uint8_t status,uint64_t source,uint16_t skip,uint16_t tail)
{
    if(!w||!w->begun)return AURA_ARCHIVE_BAD_ARGUMENT;
    if(w->pending_bytes&&w->pending_kind!=4)return AURA_ARCHIVE_BUSY;
    uint8_t p[120]={0};memcpy(p,"ASE3",4);p[4]=3;p[5]=status;
    memcpy(p+8,w->manifest.device_id,16);memcpy(p+24,w->manifest.capture_id,16);
    put(p+40,w->next_sequence,4);put(p+44,w->audio_packets,4);put(p+48,w->encoded_bytes,8);put(p+56,w->encoded_samples,8);
    put(p+64,source,8);put(p+72,status==AURA_ARCHIVE_INTERRUPTED?UINT64_MAX:source,8);put(p+80,skip,2);put(p+82,tail,2);
    /* A terminal retry compares the saved prefix digest in the held seal. */
    memcpy(p+84,w->closing?w->wire+84:w->chain,32);crc(p,116);
    if(w->closing){if(memcmp(p,w->wire,120))return AURA_ARCHIVE_CONFLICT;return commit_pending(w);}
    w->closing=true;memcpy(w->wire,p,120);w->pending_bytes=120;w->pending_kind=4;
    chained(w->chain,w->wire,120,w->pending_chain);return commit_pending(w);
}
int aura_archive_finalize(struct aura_archive_writer *w,const struct aura_opus_seal *s)
{
    if(!w||!s||s->packets!=w->audio_packets||s->encoded_samples!=w->encoded_samples||
       s->pre_skip!=(w->encoded_samples?w->manifest.pre_skip:0)||s->end_trim>=w->manifest.frame_samples||
       s->source_samples>w->encoded_samples||s->source_samples+s->pre_skip+s->end_trim!=w->encoded_samples||
       w->max_bookmark>s->source_samples)return AURA_ARCHIVE_BAD_ARGUMENT;
    return terminate(w,AURA_ARCHIVE_FINALIZED,s->source_samples,s->pre_skip,s->end_trim);
}
int aura_archive_interrupt(struct aura_archive_writer *w)
{
    if(!w||!w->begun)return AURA_ARCHIVE_BAD_ARGUMENT;
    uint16_t skip=w->encoded_samples?w->manifest.pre_skip:0;
    return terminate(w,AURA_ARCHIVE_INTERRUPTED,w->encoded_samples-skip,skip,0);
}
int aura_archive_receipt(const struct aura_archive_writer *w,uint8_t p[94])
{
    if(!w||!p||!w->begun||w->pending_bytes||w->staging)return AURA_ARCHIVE_BUSY;
    memcpy(p,"ACK3",4);p[4]=3;p[5]=w->status;memcpy(p+6,w->manifest.device_id,16);memcpy(p+22,w->manifest.capture_id,16);
    put(p+38,w->next_sequence,4);put(p+42,w->encoded_bytes,8);put(p+50,w->encoded_samples,8);memcpy(p+58,w->chain,32);crc(p,90);
    return 0;
}

static uint64_t get(const uint8_t *p,unsigned n)
{uint64_t v=0;for(unsigned i=0;i<n;++i)v|=(uint64_t)p[i]<<(8*i);return v;}
struct match_record { const uint8_t *wire; size_t bytes; uint64_t offset; };
static int match(void *user,uint64_t offset,const uint8_t *wire,size_t bytes)
{
    const struct match_record *m=user;
    return offset!=m->offset||bytes!=m->bytes||memcmp(wire,m->wire,bytes)?AURA_ARCHIVE_CONFLICT:0;
}
int aura_archive_replay(struct aura_archive_writer *view,const uint8_t *wire,size_t bytes)
{
    if(!view||!wire||view->status||bytes<26||bytes>1301||get(wire+bytes-4,4)!=aura_archive_crc32(wire,bytes-4))
        return AURA_ARCHIVE_BAD_ARGUMENT;
    struct aura_archive_writer next=*view;
    struct match_record expected={wire,bytes,view->file_offset};
    next.commit=match;next.user=&expected;next.staging=true;
    int result=AURA_ARCHIVE_BAD_ARGUMENT;
    if(!view->begun){
        if(bytes!=68||memcmp(wire,"AUR3",4))return result;
        struct aura_archive_manifest m={.frame_samples=(uint16_t)get(wire+44,2),
            .pre_skip=(uint16_t)get(wire+46,2),.started_at_ms=get(wire+56,8),.time_source=wire[54]};
        memcpy(m.device_id,wire+8,16);memcpy(m.capture_id,wire+24,16);
        result=aura_archive_begin_staged(&next,&m,match,&expected);
    }else if(!memcmp(wire,"AFR3",4)){
        if(get(wire+6,4)!=view->next_sequence||get(wire+10,8)>INT64_MAX||get(wire+20,2)+26!=bytes)return result;
        if(wire[5]==1){
            struct aura_opus_packet packet={.sequence=view->audio_packets,.sample_offset=get(wire+10,8),
                .sample_count=(uint16_t)get(wire+18,2),.bytes=(uint16_t)get(wire+20,2)};
            memcpy(packet.data,wire+22,packet.bytes);
            result=aura_archive_opus_commit(&next,&packet);
        }else if(wire[5]==2)result=aura_archive_bookmark(&next,get(wire+10,8));
    }else if(!memcmp(wire,"ASE3",4)&&bytes==120){
        if(wire[5]==AURA_ARCHIVE_FINALIZED){
            struct aura_opus_seal seal={.packets=(uint32_t)get(wire+44,4),.encoded_samples=get(wire+56,8),
                .source_samples=get(wire+64,8),.pre_skip=(uint16_t)get(wire+80,2),.end_trim=(uint16_t)get(wire+82,2)};
            result=aura_archive_finalize(&next,&seal);
        }else if(wire[5]==AURA_ARCHIVE_INTERRUPTED)result=aura_archive_interrupt(&next);
    }
    if(!result){next.commit=NULL;next.user=NULL;*view=next;}
    return result;
}
