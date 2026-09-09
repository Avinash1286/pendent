/* SPDX-License-Identifier: MIT
 * Actual portable ASC1 provider tests. All identities, keys and random bytes
 * are public synthetic inputs. This harness supplies no BLE/SMP/hardware proof. */
#include "aura_session_auth.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stddef.h>
#ifdef NDEBUG
#error "Session authentication checks must not disable assertions"
#endif

static unsigned checks, groups;
#define CHECK(v) do { ++checks; if (!(v)) { \
    fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#v); exit(1); } } while (0)
#define GROUP(name) do { ++groups; printf("PASS %s\n",name); } while (0)

struct random_state { unsigned calls; int fail, zero; uint8_t seed; };
static int random_bytes(void *user,uint8_t *out,size_t n)
{
    struct random_state *r=user; ++r->calls;
    CHECK(n==16);
    for(size_t i=0;i<n;++i)out[i]=r->zero?0:(uint8_t)(r->seed+i);
    return r->fail;
}
static struct aura_release_auth_context context(void)
{
    struct aura_release_auth_context c={0};
    memset(c.device_id,0x11,16);memset(c.storage_incarnation,0x33,16);
    memset(c.owner_id,0x44,16);c.owner_generation=UINT64_C(0x0102030405060708);
    for(unsigned i=0;i<32;++i)c.key[i]=(uint8_t)(i+1);
    return c;
}
static void frame(uint8_t out[20],uint8_t opcode,const uint8_t bytes[16])
{ out[0]='A';out[1]='4';out[2]=1;out[3]=opcode;memcpy(out+4,bytes,16); }
static void begin_frame(uint8_t out[20])
{ uint8_t nonce[16];for(unsigned i=0;i<16;++i)nonce[i]=(uint8_t)(0x60+i);frame(out,1,nonce); }
static void init(struct aura_session_auth *s,struct random_state *r,uint64_t generation)
{
    struct aura_release_auth_context c=context();
    memset(r,0,sizeof(*r));r->seed=0x80;
    CHECK(aura_session_auth_init(s,&c,random_bytes,r)==0);
    CHECK(aura_session_auth_bind(s,generation,1000,true)==0);
}
static void challenge(struct aura_session_auth *s,struct random_state *r,uint8_t out[144])
{
    uint8_t f[20];size_t n=99;init(s,r,9);begin_frame(f);
    CHECK(aura_session_auth_receive(s,9,1001,true,f,20)==0);
    CHECK(aura_session_auth_snapshot(s,9,1001,true,out,144,&n)==0&&n==144);
}
static void make_proof(const uint8_t c[144],const uint8_t key[32],uint8_t out[32])
{
    static const uint8_t domain[]="AURA-A04-SESSION-CLIENT-v1";
    uint8_t bytes[sizeof(domain)+144];memcpy(bytes,domain,sizeof(domain));
    memcpy(bytes+sizeof(domain),c,144);
    CHECK(aura_release_hmac_sha256(key,32,bytes,sizeof(bytes),out)==0);
}
static void base_proof(const uint8_t c[144],uint8_t out[32])
{ struct aura_release_auth_context ctx=context();make_proof(c,ctx.key,out); }
static int send_proof(struct aura_session_auth *s,uint64_t generation,uint64_t now,const uint8_t tag[32])
{
    uint8_t f[20];frame(f,2,tag);
    int rc=aura_session_auth_receive(s,generation,now,true,f,20);
    if(rc)return rc;
    frame(f,3,tag+16);return aura_session_auth_receive(s,generation,now+1,true,f,20);
}
static void grant(struct aura_session_auth *s,struct random_state *r)
{ uint8_t c[144],p[32];challenge(s,r,c);base_proof(c,p);CHECK(send_proof(s,9,1002,p)==0); }
static int zero(const void *p,size_t n)
{ const uint8_t *b=p;while(n--)if(*b++)return 0;return 1; }
static void closed(const struct aura_session_auth *s)
{
    CHECK(s->phase==AURA_SESSION_CLOSED&&s->connection==0&&s->deadline==0&&!s->have_frame);
    CHECK(zero(s->challenge,sizeof(s->challenge))&&zero(s->proof,sizeof(s->proof))&&
          zero(s->confirmation,sizeof(s->confirmation))&&zero(s->last_frame,sizeof(s->last_frame)));
}
static void hex(const char *name,const uint8_t *p,size_t n)
{ printf("%s ",name);for(size_t i=0;i<n;++i)printf("%02x",p[i]);putchar('\n'); }

static void canonical(void)
{
    struct aura_session_auth s;struct random_state r;uint8_t c[144],p[32],out[160];size_t n=0;
    challenge(&s,&r,c);CHECK(!memcmp(c,"ASC1\1\1\1\0",8));
    CHECK(c[64]==9&&zero(c+65,7)&&zero(c+108,4));
    CHECK(c[104]==0x30&&c[105]==0x75&&zero(c+106,2));
    CHECK(r.calls==1&&!aura_session_auth_granted(&s,9,1001,true));
    base_proof(c,p);CHECK(send_proof(&s,9,1002,p)==0);
    CHECK(aura_session_auth_granted(&s,9,1003,true));
    CHECK(aura_session_auth_snapshot(&s,9,1003,true,out,sizeof(out),&n)==0&&n==48);
    CHECK(!memcmp(out,"ASOK\1\1\0\0",8)&&out[8]==9&&zero(out+9,7));
    CHECK(zero(s.proof,32));hex("ASC1",c,144);hex("CLIENT_PROOF",p,32);hex("ASOK",out,n);
    GROUP("canonical_mutual_transcript_and_full_grant");
}
static void proof_bits(void)
{
    for(unsigned bit=0;bit<256;++bit){
        struct aura_session_auth s;struct random_state r;uint8_t c[144],p[32];
        challenge(&s,&r,c);base_proof(c,p);p[bit/8]^=(uint8_t)(1u<<(bit%8));
        CHECK(send_proof(&s,9,1002,p)==AURA_SESSION_PROOF);closed(&s);
    }
    GROUP("every_client_tag_bit_rejects_without_partial_grant");
}
static void transcript_bits(void)
{
    for(unsigned bit=0;bit<144*8;++bit){
        struct aura_session_auth s;struct random_state r;uint8_t c[144],p[32];
        challenge(&s,&r,c);c[bit/8]^=(uint8_t)(1u<<(bit%8));base_proof(c,p);
        CHECK(send_proof(&s,9,1002,p)==AURA_SESSION_PROOF);closed(&s);
    }
    GROUP("every_challenge_byte_is_bound_by_client_proof");
}
static void context_substitution(void)
{
    struct aura_session_auth first;struct random_state r;uint8_t c[144],p[32],f[20];
    challenge(&first,&r,c);base_proof(c,p);begin_frame(f);
    for(unsigned field=0;field<5;++field){
        struct aura_release_auth_context ctx=context();
        uint8_t *fields[]={ctx.device_id,ctx.storage_incarnation,ctx.owner_id,ctx.key,(uint8_t *)&ctx.owner_generation};
        size_t sizes[]={16,16,16,32,8};
        for(size_t byte=0;byte<sizes[field];++byte){
            struct aura_session_auth s;struct random_state rng={.seed=0x80};
            fields[field][byte]^=1;
            CHECK(aura_session_auth_init(&s,&ctx,random_bytes,&rng)==0);
            CHECK(aura_session_auth_bind(&s,9,1000,true)==0);
            CHECK(aura_session_auth_receive(&s,9,1001,true,f,20)==0);
            CHECK(send_proof(&s,9,1002,p)==AURA_SESSION_PROOF);closed(&s);
            fields[field][byte]^=1;
        }
    }
    GROUP("trusted_context_and_key_substitution_rejects_old_proof");
}
static void replay(void)
{
    struct aura_session_auth s;struct random_state r;uint8_t c[144],p[32],f[20];
    challenge(&s,&r,c);base_proof(c,p);begin_frame(f);
    for(unsigned kind=0;kind<3;++kind){
        init(&s,&r,kind==2?10:9);if(kind==0)f[4]^=1;if(kind==1)r.seed=0xa0;
        CHECK(aura_session_auth_receive(&s,kind==2?10:9,1001,true,f,20)==0);
        CHECK(send_proof(&s,kind==2?10:9,1002,p)==AURA_SESSION_PROOF);closed(&s);
        if(kind==0)f[4]^=1;
    }
    init(&s,&r,9);aura_session_auth_end(&s);
    CHECK(aura_session_auth_bind(&s,9,1001,true)==AURA_SESSION_DENIED);
    CHECK(aura_session_auth_bind(&s,8,1001,true)==AURA_SESSION_DENIED);
    CHECK(aura_session_auth_bind(&s,10,1001,true)==0);
    CHECK(aura_session_auth_bind(&s,UINT64_MAX,1002,true)==0);
    aura_session_auth_end(&s);CHECK(aura_session_auth_bind(&s,1,1003,true)==AURA_SESSION_DENIED);
    GROUP("nonce_reboot_and_generation_replay_fails");
}
static void retries(void)
{
    struct aura_session_auth s;struct random_state r;uint8_t c[144],p[32],f[20];
    challenge(&s,&r,c);base_proof(c,p);uint64_t deadline=s.deadline;begin_frame(f);
    CHECK(aura_session_auth_receive(&s,9,1100,true,f,20)==0&&s.deadline==deadline&&r.calls==1);
    frame(f,2,p);CHECK(aura_session_auth_receive(&s,9,1200,true,f,20)==0);
    CHECK(aura_session_auth_receive(&s,9,1300,true,f,20)==0&&s.deadline==deadline);
    frame(f,3,p+16);CHECK(aura_session_auth_receive(&s,9,1400,true,f,20)==0);
    deadline=s.deadline;CHECK(aura_session_auth_receive(&s,9,1500,true,f,20)==0&&s.deadline==deadline);
    CHECK(aura_session_auth_receive(&s,9,deadline,true,f,20)==AURA_SESSION_EXPIRED);closed(&s);
    challenge(&s,&r,c);base_proof(c,p);frame(f,2,p);CHECK(aura_session_auth_receive(&s,9,1002,true,f,20)==0);
    begin_frame(f);CHECK(aura_session_auth_receive(&s,9,1003,true,f,20)==AURA_SESSION_FORMAT);closed(&s);
    GROUP("only_exact_last_retry_is_idempotent_without_deadline_renewal");
}
static void framing(void)
{
    for(unsigned byte=0;byte<4;++byte)for(unsigned bit=0;bit<8;++bit){
        struct aura_session_auth s;struct random_state r;uint8_t f[20];init(&s,&r,9);begin_frame(f);
        f[byte]^=(uint8_t)(1u<<bit);CHECK(aura_session_auth_receive(&s,9,1001,true,f,20)==AURA_SESSION_FORMAT);closed(&s);
    }
    struct aura_session_auth s;struct random_state r;uint8_t c[144],p[32],f[20];
    init(&s,&r,9);begin_frame(f);memset(f+4,0,16);
    CHECK(aura_session_auth_receive(&s,9,1001,true,f,20)==AURA_SESSION_FORMAT);closed(&s);
    challenge(&s,&r,c);base_proof(c,p);frame(f,3,p+16);
    CHECK(aura_session_auth_receive(&s,9,1002,true,f,20)==AURA_SESSION_FORMAT);closed(&s);
    challenge(&s,&r,c);base_proof(c,p);frame(f,2,p);CHECK(aura_session_auth_receive(&s,9,1002,true,f,20)==0);
    f[4]^=1;CHECK(aura_session_auth_receive(&s,9,1003,true,f,20)==AURA_SESSION_FORMAT);closed(&s);
    challenge(&s,&r,c);begin_frame(f);f[4]^=1;
    CHECK(aura_session_auth_receive(&s,9,1002,true,f,20)==AURA_SESSION_FORMAT);closed(&s);
    GROUP("canonical_headers_zero_nonce_order_and_conflicting_halves");
}
static void deadlines(void)
{
    struct aura_session_auth s;struct random_state r;uint8_t c[144],p[32],f[20];
    challenge(&s,&r,c);base_proof(c,p);frame(f,2,p);
    CHECK(aura_session_auth_receive(&s,9,31000,true,f,20)==0);frame(f,3,p+16);
    CHECK(aura_session_auth_receive(&s,9,31001,true,f,20)==AURA_SESSION_EXPIRED);closed(&s);
    grant(&s,&r);CHECK(aura_session_auth_granted(&s,9,601002,true));
    CHECK(!aura_session_auth_granted(&s,9,601003,true));closed(&s);
    challenge(&s,&r,c);CHECK(!aura_session_auth_granted(&s,9,1000,true));closed(&s);
    init(&s,&r,9);aura_session_auth_end(&s);
    CHECK(aura_session_auth_bind(&s,10,UINT64_MAX-29999,true)==AURA_SESSION_DENIED);
    CHECK(aura_session_auth_bind(&s,10,UINT64_MAX-30000,true)==0);
    begin_frame(f);CHECK(aura_session_auth_receive(&s,10,UINT64_MAX-30000,true,f,20)==0);
    memcpy(c,s.challenge,144);base_proof(c,p);
    CHECK(send_proof(&s,10,UINT64_MAX-29999,p)==AURA_SESSION_PROOF);closed(&s);
    GROUP("absolute_proof_grant_deadlines_clock_rollback_and_overflow");
}
static void revoke(void)
{
    for(unsigned phase=0;phase<4;++phase){
        struct aura_session_auth s;struct random_state r;uint8_t c[144],p[32],f[20];init(&s,&r,9);
        if(phase){begin_frame(f);CHECK(aura_session_auth_receive(&s,9,1001,true,f,20)==0);memcpy(c,s.challenge,144);base_proof(c,p);}
        if(phase>=2){frame(f,2,p);CHECK(aura_session_auth_receive(&s,9,1002,true,f,20)==0);}
        if(phase==3){frame(f,3,p+16);CHECK(aura_session_auth_receive(&s,9,1003,true,f,20)==0);}
        CHECK(!aura_session_auth_granted(&s,9,1004,false));closed(&s);
        CHECK(aura_session_auth_bind(&s,10,1005,true)==0);aura_session_auth_end(&s);closed(&s);
        aura_session_auth_forget(&s);CHECK(zero(&s,sizeof(s)));
        CHECK(aura_session_auth_bind(&s,11,1006,true)==AURA_SESSION_DENIED);
    }
    struct aura_session_auth s;struct random_state r;init(&s,&r,9);
    CHECK(aura_session_auth_bind(&s,10,1001,false)==AURA_SESSION_DENIED);closed(&s);
    GROUP("L4_loss_end_and_forget_revoke_every_phase");
}
static void random_failures(void)
{
    for(unsigned mode=0;mode<2;++mode){
        struct aura_session_auth s;struct random_state r;uint8_t f[20];init(&s,&r,9);begin_frame(f);
        if(mode)r.zero=1;else r.fail=-1;
        CHECK(aura_session_auth_receive(&s,9,1001,true,f,20)==AURA_SESSION_RANDOM);
        CHECK(r.calls==1);closed(&s);
    }
    GROUP("entropy_failure_and_all_zero_randomness_leave_no_challenge");
}
static void arguments_and_aliases(void)
{
    struct aura_session_auth s,before;struct random_state r;struct aura_release_auth_context ctx=context();
    memset(&s,0x55,sizeof(s));before=s;
    CHECK(aura_session_auth_init(&s,NULL,random_bytes,&r)==AURA_SESSION_ARGUMENT);
    CHECK(!memcmp(&s,&before,sizeof(s)));
    CHECK(aura_session_auth_init(&s,&ctx,NULL,&r)==AURA_SESSION_ARGUMENT);
    CHECK(aura_session_auth_init(&s,&s.context,random_bytes,&r)==AURA_SESSION_ARGUMENT);
    for(unsigned field=0;field<5;++field){
        ctx=context();if(field==0)memset(ctx.device_id,0,16);if(field==1)memset(ctx.storage_incarnation,0,16);
        if(field==2)memset(ctx.owner_id,0,16);if(field==3)memset(ctx.key,0,32);if(field==4)ctx.owner_generation=0;
        CHECK(aura_session_auth_init(&s,&ctx,random_bytes,&r)==AURA_SESSION_ARGUMENT);
    }
    uint8_t c[144],out[160];size_t n=999;challenge(&s,&r,c);memset(out,0xa5,sizeof(out));
    CHECK(aura_session_auth_snapshot(&s,9,1001,true,out,143,&n)==AURA_SESSION_ARGUMENT&&n==999);
    CHECK(out[0]==0xa5&&out[159]==0xa5);before=s;
    CHECK(aura_session_auth_snapshot(&s,9,1001,true,s.challenge,144,&n)==AURA_SESSION_ARGUMENT);
    CHECK(aura_session_auth_snapshot(&s,9,1001,true,out,160,(size_t *)&s.connection)==AURA_SESSION_ARGUMENT);
    union { max_align_t alignment; uint8_t bytes[160]; } aliased;
    memset(&aliased,0xa5,sizeof(aliased));
    CHECK(aura_session_auth_snapshot(&s,9,1001,true,aliased.bytes,144,(size_t *)aliased.bytes)==AURA_SESSION_ARGUMENT);
    CHECK(aura_session_auth_snapshot(&s,9,1001,true,out,SIZE_MAX,&n)==AURA_SESSION_ARGUMENT);
    CHECK(aura_session_auth_snapshot(&s,9,1001,true,(uint8_t *)(UINTPTR_MAX-1u),4,&n)==AURA_SESSION_ARGUMENT);
    CHECK(aura_session_auth_receive(&s,9,1001,true,s.last_frame,20)==AURA_SESSION_ARGUMENT);
    CHECK(!memcmp(&s,&before,sizeof(s))&&n==999&&out[0]==0xa5);
    CHECK(aura_session_auth_receive(&s,9,1001,true,NULL,20)==AURA_SESSION_FORMAT);closed(&s);
    init(&s,&r,9);uint8_t invalid[21];begin_frame(invalid);
    CHECK(aura_session_auth_receive(&s,9,1001,true,invalid,19)==AURA_SESSION_FORMAT);closed(&s);
    init(&s,&r,9);
    CHECK(aura_session_auth_receive(&s,9,1001,true,invalid,21)==AURA_SESSION_FORMAT);closed(&s);
    init(&s,&r,9);n=99;CHECK(aura_session_auth_snapshot(&s,9,1000,true,out,160,&n)==0&&n==0);
    CHECK(out[0]==0xa5);
    GROUP("invalid_context_arguments_snapshot_bounds_and_output_aliases");
}
static void stale_generation(void)
{
    struct aura_session_auth s;struct random_state r;grant(&s,&r);
    CHECK(aura_session_auth_bind(&s,8,1004,false)==AURA_SESSION_DENIED);
    CHECK(aura_session_auth_bind(&s,9,1004,true)==AURA_SESSION_DENIED);
    CHECK(aura_session_auth_granted(&s,9,1004,true));
    CHECK(!aura_session_auth_granted(&s,8,1004,true));
    CHECK(aura_session_auth_granted(&s,9,1004,true));
    uint8_t out[160],f[20];size_t n=999;memset(out,0xa5,sizeof(out));begin_frame(f);
    CHECK(aura_session_auth_snapshot(&s,8,1005,true,out,sizeof(out),&n)==AURA_SESSION_DENIED);
    CHECK(n==999&&out[0]==0xa5&&aura_session_auth_granted(&s,9,1005,true));
    CHECK(aura_session_auth_receive(&s,8,1006,false,f,sizeof(f))==AURA_SESSION_DENIED);
    CHECK(aura_session_auth_granted(&s,9,1006,true));
    GROUP("stale_generation_callbacks_cannot_revoke_newer_grant");
}
static int parse_hex(const char *hexstr,uint8_t *out,size_t n)
{
    if(strlen(hexstr)!=n*2)return 0;
    for(size_t i=0;i<n;++i){unsigned v;if(sscanf(hexstr+i*2,"%2x",&v)!=1)return 0;out[i]=(uint8_t)v;}
    return 1;
}
int main(int argc,char **argv)
{
    if(argc==3&&!strcmp(argv[1],"--proof")){
        uint8_t p[32],c[144],out[48];size_t n=0;struct aura_session_auth s;struct random_state r;
        if(!parse_hex(argv[2],p,32))return 2;
        challenge(&s,&r,c);int rc=send_proof(&s,9,1002,p);
        if(rc){printf("PYTHON_PROOF_REJECTED %d\n",rc);return 0;}
        CHECK(aura_session_auth_snapshot(&s,9,1003,true,out,48,&n)==0&&n==48);
        hex("PYTHON_PROOF_ACCEPTED",out,48);return 0;
    }
    CHECK(argc==1);canonical();proof_bits();transcript_bits();context_substitution();replay();retries();
    framing();deadlines();revoke();random_failures();arguments_and_aliases();stale_generation();
    printf("PASS session_auth groups=%u checks=%u physical_hardware=false SMP_tested=false\n",groups,checks);
    return 0;
}
