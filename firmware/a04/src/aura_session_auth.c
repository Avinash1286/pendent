/* SPDX-License-Identifier: MIT */
#include "aura_session_auth.h"
#include <string.h>
#include <limits.h>

static const uint8_t server_domain[]="AURA-A04-SESSION-SERVER-v1";
static const uint8_t client_domain[]="AURA-A04-SESSION-CLIENT-v1";
static const uint8_t confirm_domain[]="AURA-A04-SESSION-CONFIRM-v1";
_Static_assert(sizeof(confirm_domain)+144u+32u<=AURA_RELEASE_HMAC_MAX_BYTES,"HMAC bound");
static void wipe(void *p,size_t n) { volatile uint8_t *v=p;while(n--)*v++=0; }
static bool nonzero(const uint8_t *p,size_t n) { uint8_t v=0;while(n--)v|=*p++;return v!=0; }
static bool equal(const uint8_t *a,const uint8_t *b,size_t n)
{ volatile uint8_t v=0;while(n--)v|=*a++^*b++;return v==0; }
static void put(uint8_t *p,uint64_t v,unsigned n)
{ for(unsigned i=0;i<n;++i)p[i]=(uint8_t)(v>>(8u*i)); }
static bool overlaps(const void *a,size_t an,const void *b,size_t bn)
{
    uintptr_t av=(uintptr_t)a,bv=(uintptr_t)b;
    if(!an||!bn)return false;
    if(av>UINTPTR_MAX-an||bv>UINTPTR_MAX-bn)return true;
    return av<bv+bn&&bv<av+an;
}
void aura_session_auth_end(struct aura_session_auth *s)
{
    if(!s)return;
    wipe(s->challenge,sizeof(s->challenge));wipe(s->proof,sizeof(s->proof));
    wipe(s->confirmation,sizeof(s->confirmation));wipe(s->last_frame,sizeof(s->last_frame));
    s->phase=AURA_SESSION_CLOSED;s->connection=s->deadline=0;s->have_frame=false;
}
void aura_session_auth_forget(struct aura_session_auth *s) { if(s)wipe(s,sizeof(*s)); }
int aura_session_auth_init(struct aura_session_auth *s,const struct aura_release_auth_context *c,
                          int (*random)(void *,uint8_t *,size_t),void *user)
{
    if(!s||!c||!random||overlaps(s,sizeof(*s),c,sizeof(*c)))return AURA_SESSION_ARGUMENT;
    if(!nonzero(c->device_id,16)||!nonzero(c->storage_incarnation,16)||
       !nonzero(c->owner_id,16)||!nonzero(c->key,32)||!c->owner_generation)return AURA_SESSION_ARGUMENT;
    memset(s,0,sizeof(*s));s->context=*c;s->random=random;s->random_user=user;s->configured=true;
    return 0;
}
static int live(struct aura_session_auth *s,uint64_t generation,uint64_t now,bool l4)
{
    if(!s||!s->configured)return AURA_SESSION_DENIED;
    /* A stale callback has no authority to revoke a newer live connection. */
    if(!generation||s->connection!=generation)return AURA_SESSION_DENIED;
    if(!l4||s->phase==AURA_SESSION_CLOSED||now<s->last_now) {
        aura_session_auth_end(s);return AURA_SESSION_DENIED;
    }
    s->last_now=now;
    if(now>=s->deadline){aura_session_auth_end(s);return AURA_SESSION_EXPIRED;}
    return 0;
}
int aura_session_auth_bind(struct aura_session_auth *s,uint64_t generation,uint64_t now,bool l4)
{
    if(!s||!s->configured)return AURA_SESSION_DENIED;
    if(!generation||generation<=s->high_water)return AURA_SESSION_DENIED;
    aura_session_auth_end(s);
    if(!l4||now<s->last_now||now>UINT64_MAX-AURA_SESSION_PROOF_MS)
        return AURA_SESSION_DENIED;
    s->high_water=s->connection=generation;s->last_now=now;s->deadline=now+AURA_SESSION_PROOF_MS;
    s->phase=AURA_SESSION_BEGIN;return 0;
}
static int tag(const struct aura_session_auth *s,const uint8_t *domain,size_t domain_bytes,
               size_t challenge_bytes,bool include_proof,uint8_t out[32])
{
    uint8_t message[AURA_RELEASE_HMAC_MAX_BYTES];size_t n=domain_bytes+challenge_bytes;
    memcpy(message,domain,domain_bytes);memcpy(message+domain_bytes,s->challenge,challenge_bytes);
    if(include_proof){memcpy(message+n,s->proof,32);n+=32;}
    int rc=aura_release_hmac_sha256(s->context.key,32,message,n,out);
    wipe(message,sizeof(message));return rc;
}
int aura_session_auth_receive(struct aura_session_auth *s,uint64_t generation,uint64_t now,
                             bool l4,const uint8_t *frame,size_t bytes)
{
    int rc=live(s,generation,now,l4);if(rc)return rc;
    if(!frame||bytes!=20){aura_session_auth_end(s);return AURA_SESSION_FORMAT;}
    if(overlaps(s,sizeof(*s),frame,bytes))return AURA_SESSION_ARGUMENT;
    if(s->have_frame&&equal(s->last_frame,frame,20))return 0;
    if(frame[0]!='A'||frame[1]!='4'||frame[2]!=1){rc=AURA_SESSION_FORMAT;goto fail;}
    if(frame[3]==1&&s->phase==AURA_SESSION_BEGIN){
        if(!nonzero(frame+4,16)||now>UINT64_MAX-AURA_SESSION_PROOF_MS){rc=AURA_SESSION_FORMAT;goto fail;}
        uint8_t *c=s->challenge;
        memcpy(c,"ASC1",4);c[4]=c[5]=c[6]=1;c[7]=0;
        memcpy(c+8,s->context.device_id,16);memcpy(c+24,s->context.storage_incarnation,16);
        memcpy(c+40,s->context.owner_id,16);put(c+56,s->context.owner_generation,8);
        put(c+64,generation,8);memcpy(c+72,frame+4,16);
        if(s->random(s->random_user,c+88,16)||!nonzero(c+88,16)){rc=AURA_SESSION_RANDOM;goto fail;}
        put(c+104,AURA_SESSION_PROOF_MS,4);
        if(tag(s,server_domain,sizeof(server_domain),112,false,c+112)){rc=AURA_SESSION_PROOF;goto fail;}
        s->deadline=now+AURA_SESSION_PROOF_MS;s->phase=AURA_SESSION_CHALLENGE;
    }else if(frame[3]==2&&s->phase==AURA_SESSION_CHALLENGE){
        memcpy(s->proof,frame+4,16);s->phase=AURA_SESSION_HALF;
    }else if(frame[3]==3&&s->phase==AURA_SESSION_HALF){
        uint8_t expected[32];memcpy(s->proof+16,frame+4,16);
        rc=tag(s,client_domain,sizeof(client_domain),144,false,expected);
        bool accepted=!rc&&equal(s->proof,expected,32);wipe(expected,sizeof(expected));
        if(!accepted||now>UINT64_MAX-AURA_SESSION_GRANT_MS){rc=AURA_SESSION_PROOF;goto fail;}
        memcpy(s->confirmation,"ASOK",4);s->confirmation[4]=s->confirmation[5]=1;
        put(s->confirmation+8,generation,8);
        if(tag(s,confirm_domain,sizeof(confirm_domain),144,true,s->confirmation+16)){rc=AURA_SESSION_PROOF;goto fail;}
        s->deadline=now+AURA_SESSION_GRANT_MS;s->phase=AURA_SESSION_GRANTED;
        wipe(s->proof,sizeof(s->proof));
    }else{rc=AURA_SESSION_FORMAT;goto fail;}
    memcpy(s->last_frame,frame,20);s->have_frame=true;return 0;
fail:
    aura_session_auth_end(s);return rc;
}
int aura_session_auth_snapshot(struct aura_session_auth *s,uint64_t generation,uint64_t now,
                              bool l4,uint8_t *out,size_t capacity,size_t *bytes)
{
    if(!s||!out||!bytes||overlaps(s,sizeof(*s),out,capacity)||
       overlaps(s,sizeof(*s),bytes,sizeof(*bytes))||overlaps(out,capacity,bytes,sizeof(*bytes)))return AURA_SESSION_ARGUMENT;
    int rc=live(s,generation,now,l4);if(rc)return rc;
    size_t n=s->phase==AURA_SESSION_BEGIN?0:(s->phase==AURA_SESSION_GRANTED?48:144);
    if(capacity<n)return AURA_SESSION_ARGUMENT;
    if(n)memcpy(out,s->phase==AURA_SESSION_GRANTED?s->confirmation:s->challenge,n);
    *bytes=n;return 0;
}
bool aura_session_auth_granted(struct aura_session_auth *s,uint64_t generation,uint64_t now,bool l4)
{ return !live(s,generation,now,l4)&&s->phase==AURA_SESSION_GRANTED; }
