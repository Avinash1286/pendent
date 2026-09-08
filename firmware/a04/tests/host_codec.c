/* SPDX-License-Identifier: MIT */
#include "aura_opus.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAILED line %d: %s\n", __LINE__, #x); return 1; } } while (0)
#define PACKETS 2048

struct memory_sink {
    struct aura_opus_packet *packets;
    unsigned count;
    unsigned fail_at;
    unsigned failures;
    struct aura_opus_packet failed;
    bool verify_retry;
};

static int store(void *user, const struct aura_opus_packet *packet)
{
    struct memory_sink *sink = user;
    if (packet->sequence != sink->count || sink->count == PACKETS) return -101;
    if (sink->verify_retry) {
        if (packet->sequence != sink->failed.sequence || packet->bytes != sink->failed.bytes ||
            memcmp(packet->data, sink->failed.data, packet->bytes)) return -102;
        sink->verify_retry = false;
    }
    if (sink->failures && packet->sequence == sink->fail_at) {
        --sink->failures;
        sink->failed = *packet;
        sink->verify_retry = true;
        return -100;
    }
    sink->packets[sink->count++] = *packet;
    return 0;
}

static void little(FILE *f, uint64_t value, unsigned bytes)
{
    for (unsigned i = 0; i < bytes; ++i) fputc((unsigned char)(value >> (8 * i)), f);
}

static int fixture(const char *input_path, const char *output_prefix, unsigned frame_ms)
{
    FILE *f = fopen(input_path, "rb");
    CHECK(f);
    CHECK(fseek(f, 0, SEEK_END) == 0);
    long size = ftell(f);
    CHECK(size > 0 && size % 2 == 0 && size < 2000000);
    rewind(f);
    int16_t *input = malloc((size_t)size);
    CHECK(input && fread(input, 1, (size_t)size, f) == (size_t)size);
    fclose(f);
    size_t samples = (size_t)size / 2;
    void *state = malloc(aura_opus_state_bytes());
    struct memory_sink sink = {0};
    sink.packets = calloc(PACKETS, sizeof(*sink.packets));
    CHECK(state && sink.packets);
    struct aura_opus_capture capture;
    CHECK(aura_opus_init(&capture, state, aura_opus_state_bytes(), frame_ms, store, &sink) == 0);
    size_t offset = 0;
    const size_t blocks[] = {1, 17, 640, 39, 1000, 7, 320};
    unsigned block = 0;
    while (offset < samples) {
        size_t chunk = blocks[block++ % (sizeof(blocks) / sizeof(blocks[0]))];
        if (chunk > samples - offset) chunk = samples - offset;
        size_t consumed = 0;
        CHECK(aura_opus_push(&capture, input + offset, chunk, &consumed) == 0);
        CHECK(consumed == chunk);
        offset += consumed;
    }
    struct aura_opus_seal seal;
    CHECK(aura_opus_finish(&capture, &seal) == 0);
    CHECK(seal.source_samples == samples && seal.packets == sink.count);
    CHECK(seal.encoded_samples - seal.pre_skip - seal.end_trim == samples);
    char name[1024];
    CHECK(snprintf(name, sizeof(name), "%s-%ums.aoc", output_prefix, frame_ms) > 0);
    f = fopen(name, "wb");
    CHECK(f);
    CHECK(fwrite("AOC1", 1, 4, f) == 4);
    little(f, 1, 2); little(f, frame_ms, 2); little(f, AURA_OPUS_RATE, 4);
    little(f, seal.source_samples, 8); little(f, seal.encoded_samples, 8);
    little(f, seal.packets, 4); little(f, seal.pre_skip, 2); little(f, seal.end_trim, 2);
    unsigned encoded_bytes = 0, max_packet = 0;
    int error = 0;
    OpusDecoder *decoder = opus_decoder_create(AURA_OPUS_RATE, 1, &error);
    CHECK(decoder && error == 0);
    int16_t *decoded = calloc((size_t)seal.encoded_samples, sizeof(*decoded));
    CHECK(decoded);
    size_t decoded_count = 0;
    for (unsigned i = 0; i < sink.count; ++i) {
        struct aura_opus_packet *packet = &sink.packets[i];
        CHECK(packet->sequence == i && packet->sample_offset == decoded_count);
        CHECK(opus_packet_get_nb_samples(packet->data, packet->bytes, AURA_OPUS_RATE) == (int)packet->sample_count);
        int count = opus_decode(decoder, packet->data, packet->bytes,
                                decoded + decoded_count, packet->sample_count, 0);
        CHECK(count == packet->sample_count);
        decoded_count += (size_t)count;
        encoded_bytes += packet->bytes;
        if (packet->bytes > max_packet) max_packet = packet->bytes;
        little(f, packet->sequence, 4); little(f, packet->sample_offset, 8);
        little(f, packet->sample_count, 2); little(f, packet->bytes, 2);
        CHECK(fwrite(packet->data, 1, packet->bytes, f) == packet->bytes);
    }
    CHECK(fclose(f) == 0);
    CHECK(snprintf(name, sizeof(name), "%s-%ums-decoded.pcm", output_prefix, frame_ms) > 0);
    f = fopen(name, "wb");
    CHECK(f && fwrite(decoded + seal.pre_skip, 2, samples, f) == samples && fclose(f) == 0);
    printf("{\"frame_ms\":%u,\"source_samples\":%llu,\"encoded_samples\":%llu,\"packets\":%u,"
           "\"pre_skip\":%u,\"end_trim\":%u,\"encoded_bytes\":%u,\"max_packet_bytes\":%u,\"state_bytes\":%u}\n",
           frame_ms, (unsigned long long)seal.source_samples, (unsigned long long)seal.encoded_samples,
           seal.packets, seal.pre_skip, seal.end_trim, encoded_bytes, max_packet, (unsigned)aura_opus_state_bytes());
    opus_decoder_destroy(decoder);
    free(input); free(state); free(sink.packets); free(decoded);
    return 0;
}

static int tests(void)
{
    size_t state_size = aura_opus_state_bytes();
    CHECK(state_size > 0 && state_size <= AURA_OPUS_STATE_LIMIT);
    void *state = malloc(state_size);
    CHECK(state);
    struct memory_sink sink = {0};
    sink.packets = calloc(PACKETS, sizeof(*sink.packets));
    CHECK(sink.packets);
    struct aura_opus_capture capture;
    CHECK(aura_opus_init(&capture, state, state_size - 1, 20, store, &sink) == OPUS_ALLOC_FAIL);
    CHECK(aura_opus_init(&capture, (char *)state + 1, state_size, 20, store, &sink) == OPUS_BAD_ARG);
    CHECK(aura_opus_init(&capture, state, state_size, 30, store, &sink) == OPUS_BAD_ARG);
    CHECK(aura_opus_init(&capture, state, state_size, 20, NULL, &sink) == OPUS_BAD_ARG);
    CHECK(aura_opus_retry(&capture) == OPUS_BAD_ARG);
    CHECK(aura_opus_init(&capture, state, state_size, 20, store, &sink) == 0);
    /* A rejected reinitialization must not leave the previous stream usable. */
    CHECK(aura_opus_init(&capture, state, state_size, 30, store, &sink) == OPUS_BAD_ARG);
    CHECK(aura_opus_retry(&capture) == OPUS_BAD_ARG);
    CHECK(aura_opus_init(&capture, state, state_size, 20, store, &sink) == 0);
    struct aura_opus_seal empty;
    CHECK(aura_opus_finish(&capture, &empty) == 0 && empty.packets == 0 && empty.pre_skip == 0);
    int16_t pcm[1000];
    for (unsigned i = 0; i < 1000; ++i) pcm[i] = (int16_t)((int)(i % 80) * 200 - 8000);
    size_t consumed = 99;
    CHECK(aura_opus_push(&capture, pcm, 1, &consumed) == OPUS_BAD_ARG && consumed == 0);
    for (unsigned frame_ms = 10; frame_ms <= 20; frame_ms += 10) {
        memset(&sink.failed, 0, sizeof(sink.failed));
        sink.count = 0; sink.fail_at = 1; sink.failures = 2; sink.verify_retry = false;
        CHECK(aura_opus_init(&capture, state, state_size, frame_ms, store, &sink) == 0);
        CHECK(aura_opus_push(&capture, pcm, 1000, &consumed) == -100);
        CHECK(consumed == frame_ms * 16 * 2 && capture.pending);
        size_t accepted = consumed;
        CHECK(aura_opus_retry(&capture) == -100 && capture.pending);
        CHECK(aura_opus_retry(&capture) == 0 && !capture.pending);
        CHECK(aura_opus_push(&capture, pcm + accepted, 1000 - accepted, &consumed) == 0);
        CHECK(consumed == 1000 - accepted);
        /* Fail the final partial-frame commit, retry finish without re-encoding. */
        sink.fail_at = sink.count; sink.failures = 1;
        struct aura_opus_seal seal, again;
        CHECK(aura_opus_finish(&capture, &seal) == -100);
        CHECK(aura_opus_push(&capture, pcm, 1, &consumed) == OPUS_BAD_ARG && consumed == 0);
        CHECK(aura_opus_finish(&capture, &seal) == 0);
        CHECK(aura_opus_finish(&capture, &again) == 0);
        CHECK(seal.packets == again.packets && seal.source_samples == 1000);
        CHECK(seal.encoded_samples - seal.pre_skip - seal.end_trim == 1000);
        CHECK(seal.end_trim < frame_ms * 16);
        CHECK(!sink.verify_retry && !capture.pending && capture.finished);
    }
    free(state); free(sink.packets);
    printf("PASS state size/alignment, bad profile/reinit invalidation, empty capture, 10/20ms chunking, repeated commit failure, exact retry, final-tail retry, trim and closed-input tests; opus=%s state=%u\n",
           opus_get_version_string(), (unsigned)state_size);
    return 0;
}

int main(int argc, char **argv)
{
    if (tests()) return 1;
    if (argc == 3) return fixture(argv[1], argv[2], 10) || fixture(argv[1], argv[2], 20);
    return argc == 1 ? 0 : 2;
}
