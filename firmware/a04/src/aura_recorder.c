/* SPDX-License-Identifier: MIT */
#include "aura_recorder.h"
#include <string.h>

static bool valid(const struct aura_recorder *r)
{
    return r&&r->journal&&r->encoder_state&&r->encoder_bytes;
}

int aura_recorder_init(struct aura_recorder *r,struct aura_journal *j,
                       void *arena,size_t bytes)
{
    if(!r)return AURA_RECORDER_BAD_ARGUMENT;
    memset(r,0,sizeof(*r));
    size_t required=aura_opus_state_bytes();
    if(!j||!arena||(uintptr_t)arena%_Alignof(max_align_t)||!required||
       required>AURA_OPUS_STATE_LIMIT||bytes<required)return AURA_RECORDER_BAD_ARGUMENT;
    r->journal=j;r->encoder_state=arena;r->encoder_bytes=bytes;
    r->capture_index=AURA_JOURNAL_NONE;
    return 0;
}

int aura_recorder_start(struct aura_recorder *r,const struct aura_archive_manifest *m,
                        uint64_t epoch,uint64_t now)
{
    if(!valid(r)||!m||m->frame_samples!=320||m->pre_skip!=40||m->time_source||m->started_at_ms)
        return AURA_RECORDER_BAD_ARGUMENT;
    if(!epoch||epoch<=r->last_epoch)return AURA_RECORDER_STALE_EPOCH;
    if(r->state==AURA_RECORDER_RECORDING||r->journal->active>=0)return AURA_RECORDER_STATE;
    if(r->journal->fault)return r->journal->fault;
    int status=aura_journal_prepare(r->journal);
    if(status)return status;
    status=aura_journal_service(r->journal,now);
    if(status)return status;
    status=aura_opus_init_staged(&r->codec,r->encoder_state,r->encoder_bytes,20,
                                 aura_archive_opus_commit,&r->archive);
    if(status)return status;
    if(r->codec.lookahead!=m->pre_skip)return AURA_RECORDER_BAD_ARGUMENT;
    r->epoch=r->last_epoch=epoch;r->source_samples=0;r->next_sequence=0;
    r->fault_reason=r->close_error=0;memset(&r->seal,0,sizeof(r->seal));
    r->capture_index=AURA_JOURNAL_NONE;
    status=aura_archive_begin_staged(&r->archive,m,aura_journal_stage,r->journal);
    if(status){r->state=AURA_RECORDER_FAILED;r->fault_reason=r->close_error=status;return status;}
    r->capture_index=(uint16_t)r->journal->active;r->state=AURA_RECORDER_RECORDING;
    return 0;
}

int aura_recorder_interrupt(struct aura_recorder *r,uint64_t epoch,int reason,uint64_t now)
{
    if(!valid(r)||!reason)return AURA_RECORDER_BAD_ARGUMENT;
    if(epoch!=r->epoch)return AURA_RECORDER_STALE_EPOCH;
    if(r->state==AURA_RECORDER_INTERRUPTED)return 0;
    if(r->state==AURA_RECORDER_FAILED)return r->close_error?r->close_error:AURA_RECORDER_STATE;
    if(r->state!=AURA_RECORDER_RECORDING)return AURA_RECORDER_STATE;
    /* Synchronous owner: publish the terminal state before attempting storage,
     * so callers never consider failure an invitation to accept more PCM. */
    r->state=AURA_RECORDER_FAILED;r->fault_reason=reason;
    int status=aura_journal_service(r->journal,now);
    if(!status)status=aura_archive_interrupt(&r->archive);
    r->close_error=status;
    if(!status)r->state=AURA_RECORDER_INTERRUPTED;
    return status;
}

static int fail(struct aura_recorder *r,int reason,uint64_t now)
{
    (void)aura_recorder_interrupt(r,r->epoch,reason,now);
    return reason;
}

int aura_recorder_service(struct aura_recorder *r,uint64_t now)
{
    if(!valid(r))return AURA_RECORDER_BAD_ARGUMENT;
    if(r->state!=AURA_RECORDER_RECORDING)return 0;
    int status=aura_journal_service(r->journal,now);
    return status?fail(r,status,now):0;
}

int aura_recorder_consume(struct aura_recorder *r,const struct aura_recorder_block *b,
                          uint64_t now,size_t *consumed)
{
    if(!consumed)return AURA_RECORDER_BAD_ARGUMENT;
    *consumed=0;
    if(!valid(r)||!b)return AURA_RECORDER_BAD_ARGUMENT;
    if(b->epoch!=r->epoch)return AURA_RECORDER_STALE_EPOCH;
    if(r->state!=AURA_RECORDER_RECORDING)return AURA_RECORDER_STATE;
    if(!b->pcm||!b->samples||b->samples>AURA_RECORDER_BLOCK_SAMPLES)
        return fail(r,AURA_RECORDER_BAD_ARGUMENT,now);
    if(b->sequence!=r->next_sequence||b->source_offset!=r->source_samples||
       r->next_sequence==UINT32_MAX||b->samples>UINT64_MAX-r->source_samples)
        return fail(r,AURA_RECORDER_GAP,now);
    int status=aura_recorder_service(r,now);
    if(status)return status;
    status=aura_opus_push(&r->codec,b->pcm,b->samples,consumed);
    r->source_samples=r->codec.source_samples;
    if(status)return fail(r,status,now);
    if(*consumed!=b->samples)return fail(r,AURA_RECORDER_SOURCE_FAILED,now);
    ++r->next_sequence;
    return 0;
}

int aura_recorder_stop(struct aura_recorder *r,uint64_t epoch,uint64_t end,uint64_t now)
{
    if(!valid(r))return AURA_RECORDER_BAD_ARGUMENT;
    if(epoch!=r->epoch)return AURA_RECORDER_STALE_EPOCH;
    if(r->state==AURA_RECORDER_FINALIZED)
        return end==r->source_samples?0:AURA_RECORDER_GAP;
    if(r->state!=AURA_RECORDER_RECORDING)return AURA_RECORDER_STATE;
    if(end!=r->source_samples)return fail(r,AURA_RECORDER_GAP,now);
    int status=aura_recorder_service(r,now);
    if(status)return status;
    status=aura_opus_finish(&r->codec,&r->seal);
    if(!status)status=aura_archive_finalize(&r->archive,&r->seal);
    if(status)return fail(r,status,now);
    r->state=AURA_RECORDER_FINALIZED;
    return 0;
}
