/* SPDX-License-Identifier: MIT */
#include "aura_opus.h"
#include <string.h>
#include <limits.h>

size_t aura_opus_state_bytes(void)
{
    int size = opus_encoder_get_size(1);
    return size > 0 ? (size_t)size : 0;
}

static int init(struct aura_opus_capture *c, void *state, size_t bytes,
                unsigned frame_ms, aura_opus_commit commit, void *user, bool staging)
{
    if (!c) return OPUS_BAD_ARG;
    memset(c, 0, sizeof(*c));
    if (!state || !commit || (frame_ms != 10 && frame_ms != 20) ||
        (uintptr_t)state % _Alignof(max_align_t))
        return OPUS_BAD_ARG;
    size_t required = aura_opus_state_bytes();
    if (!required || required > AURA_OPUS_STATE_LIMIT || bytes < required)
        return OPUS_ALLOC_FAIL;
    c->encoder = state;
    c->frame_samples = (uint16_t)(frame_ms * 16);
    c->commit = commit;
    c->user = user;
    c->staging = staging;
    int result = opus_encoder_init(c->encoder, AURA_OPUS_RATE, 1,
                                   OPUS_APPLICATION_RESTRICTED_LOWDELAY);
    if (result) return c->fault = result;
#define CONFIGURE(request) do { result = opus_encoder_ctl(c->encoder, request); \
                               if (result) return c->fault = result; } while (0)
    CONFIGURE(OPUS_SET_BITRATE(AURA_OPUS_BITRATE));
    CONFIGURE(OPUS_SET_VBR(1));
    CONFIGURE(OPUS_SET_VBR_CONSTRAINT(1));
    CONFIGURE(OPUS_SET_COMPLEXITY(3));
    CONFIGURE(OPUS_SET_SIGNAL(OPUS_SIGNAL_VOICE));
    CONFIGURE(OPUS_SET_MAX_BANDWIDTH(OPUS_BANDWIDTH_WIDEBAND));
    CONFIGURE(OPUS_SET_LSB_DEPTH(16));
    CONFIGURE(OPUS_SET_DTX(0));
    CONFIGURE(OPUS_SET_INBAND_FEC(0));
    CONFIGURE(OPUS_SET_PACKET_LOSS_PERC(0));
    opus_int32 lookahead = 0;
    CONFIGURE(OPUS_GET_LOOKAHEAD(&lookahead));
#undef CONFIGURE
    if (lookahead < 0 || lookahead > AURA_OPUS_MAX_SAMPLES)
        return c->fault = OPUS_INTERNAL_ERROR;
    c->lookahead = (uint16_t)lookahead;
    return OPUS_OK;
}

int aura_opus_init(struct aura_opus_capture *c, void *state, size_t bytes,
                   unsigned frame_ms, aura_opus_commit commit, void *user)
{
    return init(c, state, bytes, frame_ms, commit, user, false);
}

int aura_opus_init_staged(struct aura_opus_capture *c, void *state, size_t bytes,
                          unsigned frame_ms, aura_opus_commit stage, void *user)
{
    return init(c, state, bytes, frame_ms, stage, user, true);
}

int aura_opus_retry(struct aura_opus_capture *c)
{
    if (!c || !c->encoder || !c->commit) return OPUS_BAD_ARG;
    if (c->fault) return c->fault;
    if (!c->pending) return OPUS_OK;
    int result = c->commit(c->user, &c->packet);
    if (result) return result;
    c->pending = false;
    ++c->accepted_packets;
    return OPUS_OK;
}

static int encode_buffer(struct aura_opus_capture *c)
{
    if (c->pending || c->buffered_samples != c->frame_samples ||
        c->accepted_packets == UINT32_MAX)
        return c->fault = OPUS_INTERNAL_ERROR;
    int result = opus_encode(c->encoder, c->pcm, c->frame_samples,
                             c->packet.data, sizeof(c->packet.data));
    if (result <= 0) return c->fault = (result ? result : OPUS_INTERNAL_ERROR);
    c->packet.sequence = c->accepted_packets;
    c->packet.sample_offset = c->encoded_samples;
    c->packet.sample_count = c->frame_samples;
    c->packet.bytes = (uint16_t)result;
    c->encoded_samples += c->frame_samples;
    c->buffered_samples = 0;
    c->pending = true;
    return aura_opus_retry(c);
}

int aura_opus_push(struct aura_opus_capture *c, const int16_t *pcm,
                  size_t count, size_t *consumed)
{
    if (!consumed) return OPUS_BAD_ARG;
    *consumed = 0;
    if (!c || !c->encoder || (count && !pcm) || c->closing || c->finished)
        return OPUS_BAD_ARG;
    int result = aura_opus_retry(c);
    if (result) return result;
    if (count > UINT64_MAX - c->source_samples - AURA_OPUS_MAX_SAMPLES)
        return OPUS_BAD_ARG;
    while (*consumed < count) {
        size_t remaining = count - *consumed;
        size_t take = c->frame_samples - c->buffered_samples;
        if (take > remaining) take = remaining;
        memcpy(c->pcm + c->buffered_samples, pcm + *consumed, take * sizeof(*pcm));
        c->buffered_samples += (uint16_t)take;
        c->source_samples += take;
        *consumed += take;
        if (c->buffered_samples == c->frame_samples) {
            result = encode_buffer(c);
            if (result) return result;
        }
    }
    return OPUS_OK;
}

int aura_opus_finish(struct aura_opus_capture *c, struct aura_opus_seal *seal)
{
    if (!c || !c->encoder || !seal) return OPUS_BAD_ARG;
    c->closing = true;
    int result = aura_opus_retry(c);
    if (result) return result;
    uint64_t target = c->source_samples ? c->source_samples + c->lookahead : 0;
    while (c->encoded_samples < target) {
        memset(c->pcm + c->buffered_samples, 0,
               (c->frame_samples - c->buffered_samples) * sizeof(c->pcm[0]));
        c->buffered_samples = c->frame_samples;
        result = encode_buffer(c);
        if (result) return result;
    }
    *seal = (struct aura_opus_seal){
        .source_samples = c->source_samples,
        .encoded_samples = c->encoded_samples,
        .packets = c->accepted_packets,
        .pre_skip = c->source_samples ? c->lookahead : 0,
        .end_trim = (uint16_t)(c->encoded_samples - target),
    };
    c->finished = true;
    return OPUS_OK;
}
