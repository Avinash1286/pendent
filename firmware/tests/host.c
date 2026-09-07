/* These tests execute the same C journal, gesture and PCM mixer used on ARM. */
#include "journal.h"
#include "gestures.h"
#include "pcm.h"
#include "maintenance.h"
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <stdlib.h>
#define PAGES 256
static uint8_t memory[PAGES][AJ_PAGE];
static int writes, fail_at = -1, ecc_page = -1;
static bool bad1;
static int readp(uint32_t p, uint8_t *o)
{
    if ((int)p == ecc_page)
        return -EBADMSG;
    memcpy(o, memory[p], AJ_PAGE);
    return 0;
}
static int writep(uint32_t p, const uint8_t *d)
{
    for (unsigned n = 0; n < AJ_PAGE; n++)
        if (memory[p][n] != 255)
            return -EEXIST;
    if (writes++ == fail_at) {
        memcpy(memory[p], d, 19);
        return -EIO;
    }
    memcpy(memory[p], d, AJ_PAGE);
    return 0;
}
static bool bad(uint32_t block)
{
    return block == 1 && bad1;
}
static struct aj_io io = {readp, writep, bad, PAGES};
static struct aj_store s, t;
static bool persisted_intent;
static int fail_erase = -1;
static bool fail_intent;
static int intent(bool on)
{
    if (fail_intent)
        return -EIO;
    persisted_intent = on;
    return 0;
}
static int erase(uint32_t block)
{
    if ((int)block == fail_erase) {
        memset(memory[block * 64], 255, AJ_PAGE * 17);
        return -EIO;
    }
    memset(memory[block * 64], 255, AJ_PAGE * 64);
    return 0;
}
static void reset(void)
{
    memset(memory, 255, sizeof(memory));
    writes = 0;
    fail_at = -1;
    ecc_page = -1;
    bad1 = false;
}
#define CHECK(x)                                                                                   \
    do {                                                                                           \
        if (!(x)) {                                                                                \
            fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x);                                   \
            exit(1);                                                                               \
        }                                                                                          \
    } while (0)
static int tests;
static void pass(const char *n)
{
    printf("PASS %s\n", n);
    tests++;
}
int main(void)
{
    uint8_t data[AJ_PAYLOAD], out[AJ_PAYLOAD];
    for (unsigned i = 0; i < sizeof(data); i++)
        data[i] = i % 251;
    CHECK(aj_crc(0, "123456789", 9) == 0xcbf43926);
    CHECK(aj_crc(aj_crc(0, "1234", 4), "56789", 5) == 0xcbf43926);
    pass("CRC IEEE known vector and incremental chaining");
    reset();
    CHECK(!aj_mount(&s, io));
    CHECK(!aj_begin(&s, 1700000000));
    CHECK(!aj_append(&s, data, sizeof(data)));
    CHECK(!aj_mark(&s));
    CHECK(!aj_append(&s, data, 200));
    CHECK(!aj_end(&s, false));
    CHECK(!aj_mount(&t, io));
    CHECK(t.count == 1 && t.notes[0].bytes == AJ_PAYLOAD + 200 && !t.notes[0].recovered);
    CHECK(aj_read(&t, 1, AJ_PAYLOAD - 100, out, 200) == 200);
    CHECK(!memcmp(out, data + AJ_PAYLOAD - 100, 100) && !memcmp(out + 100, data, 100));
    pass("record, bookmark, commit, mount and cross-page read");
    CHECK(aj_read(&t, 1, t.notes[0].bytes, out, 180) == 0);
    CHECK(aj_read(&t, 1, t.notes[0].bytes + 1, out, 180) == -EINVAL);
    CHECK(aj_delete(&t, 1, t.notes[0].bytes, 123) == -EPERM);
    CHECK(!aj_delete(&t, 1, t.notes[0].bytes, t.notes[0].crc));
    CHECK(!aj_mount(&s, io));
    CHECK(!aj_find(&s, 1));
    pass("EOF and explicit size/CRC matching tombstone");
    reset();
    CHECK(!aj_mount(&s, io));
    CHECK(!aj_begin(&s, 5));
    CHECK(!aj_append(&s, data, 100));
    CHECK(!aj_mount(&t, io));
    CHECK(t.notes[0].recovered && t.notes[0].bytes == 100);
    CHECK(!aj_begin(&t, 6));
    CHECK(!aj_append(&t, data, 50));
    CHECK(!aj_end(&t, false));
    CHECK(!aj_mount(&s, io));
    CHECK(s.count == 2 && s.notes[1].id == 2);
    pass("power loss without end preserves pages and unique next ID");
    reset();
    CHECK(!aj_mount(&s, io));
    CHECK(!aj_begin(&s, 1));
    CHECK(!aj_append(&s, data, 100));
    fail_at = writes;
    CHECK(aj_append(&s, data, 100) == -EIO);
    fail_at = -1;
    CHECK(!aj_mount(&t, io));
    CHECK(t.notes[0].bytes == 100 && t.notes[0].recovered && t.next == 5);
    CHECK(!aj_begin(&t, 2));
    CHECK(t.notes[1].first == 5);
    pass("torn page is skipped and prior committed PCM recovered");
    reset();
    CHECK(!aj_mount(&s, io));
    CHECK(!aj_begin(&s, 1));
    CHECK(!aj_append(&s, data, 100));
    CHECK(!aj_end(&s, false));
    ecc_page = 3;
    CHECK(aj_mount(&t, io) == -EIO);
    CHECK(aj_read(&t, 1, 0, out, 100) == -EIO);
    pass("uncorrectable ECC cannot silently repair recording CRC");
    reset();
    bad1 = true;
    CHECK(!aj_mount(&s, io));
    CHECK(!aj_begin(&s, 1));
    for (int i = 0; i < 70; i++)
        CHECK(!aj_append(&s, data, 100));
    CHECK(s.next > 128);
    for (int p = 64; p < 128; p++)
        CHECK(memory[p][0] == 255);
    CHECK(!aj_end(&s, false));
    CHECK(!aj_mount(&t, io));
    CHECK(t.notes[0].bytes == 7000);
    CHECK(aj_read(&t, 1, 6300, out, 100) == 100);
    pass("factory bad block skipped across recording and replay");
    reset();
    CHECK(!aj_mount(&s, io));
    CHECK(!aj_begin(&s, 1));
    int r;
    while ((r = aj_append(&s, data, AJ_PAYLOAD)) == 0) {
    }
    CHECK(r == -ENOSPC);
    CHECK(!aj_end(&s, false));
    CHECK(!aj_mount(&t, io));
    CHECK(!t.notes[0].recovered);
    CHECK(aj_begin(&t, 2) == -ENOSPC);
    pass("full storage reserves END page and never overwrites audio");
    struct aura_gesture_state g = {0};
    CHECK(aura_gesture_tick(&g, 1, 0) == AG_NONE);
    CHECK(aura_gesture_tick(&g, 0, 10) == AG_NONE);
    CHECK(aura_gesture_tick(&g, 1, 20) == AG_NONE);
    CHECK(aura_gesture_tick(&g, 1, 45) == AG_NONE);
    CHECK(aura_gesture_tick(&g, 0, 100) == AG_NONE);
    CHECK(aura_gesture_tick(&g, 0, 125) == AG_NONE);
    CHECK(aura_gesture_tick(&g, 0, 425) == AG_PRESS);
    CHECK(aura_gesture_tick(&g, 0, 426) == AG_NONE);
    pass("button bounce, delayed single press and no duplicate event");
    memset(&g, 0, sizeof(g));
    aura_gesture_tick(&g, 1, 0);
    aura_gesture_tick(&g, 1, 25);
    CHECK(aura_gesture_tick(&g, 1, 3025) == AG_HOLD);
    CHECK(aura_gesture_tick(&g, 1, 6030) == AG_NONE);
    aura_gesture_tick(&g, 0, 6040);
    aura_gesture_tick(&g, 0, 6070);
    CHECK(aura_gesture_tick(&g, 0, 6500) == AG_NONE);
    pass("three second hold does not become record press on release");
    memset(&g, 0, sizeof(g));
    for (int i = 0; i < 2; i++) {
        aura_gesture_tick(&g, 1, 200 * i);
        aura_gesture_tick(&g, 1, 200 * i + 25);
        aura_gesture_tick(&g, 0, 200 * i + 80);
        aura_gesture_tick(&g, 0, 200 * i + 110);
    }
    CHECK(aura_gesture_tick(&g, 0, 610) == AG_DOUBLE);
    pass("double press emits one bookmark gesture");
    CHECK(aura_mix(32767, 32767) == 32767);
    CHECK(aura_mix(-32768, -32768) == -32768);
    CHECK(aura_mix(32767, -32768) == 0);
    CHECK(aura_mix(1000, 3000) == 2000);
    pass("dual-microphone mono mix preserves signed range without overflow");
    reset();
    CHECK(!aj_mount(&s, io));
    CHECK(!aj_begin(&s, 1));
    CHECK(!aj_append(&s, data, 100));
    CHECK(!aj_end(&s, false));
    struct aura_maintenance_io m = {intent, erase};
    CHECK(aura_erase_run(&s, m, false) < 0);
    CHECK(memory[2][0] != 255);
    CHECK(!aj_delete(&s, 1, s.notes[0].bytes, s.notes[0].crc));
    fail_intent = true;
    CHECK(aura_erase_run(&s, m, false) == -EIO);
    CHECK(memory[2][0] != 255);
    fail_intent = false;
    pass("maintenance refuses live audio and no erase before durable intent");
    fail_erase = 1;
    CHECK(aura_erase_run(&s, m, false) == -EIO);
    CHECK(persisted_intent);
    CHECK(memory[0][0] == 255);
    fail_erase = -1; /* Boot must resume erase, never expose a partial journal. */
    CHECK(!aura_erase_run(&s, m, true));
    CHECK(!persisted_intent && s.count == 0);
    CHECK(!aj_begin(&s, 99));
    CHECK(!aj_append(&s, data, 100));
    CHECK(!aj_end(&s, false));
    CHECK(!aj_mount(&t, io));
    CHECK(t.notes[0].time == 99);
    pass("interrupted erase resumes before mount and restores recording capacity");
    printf("%d tests passed\n", tests);
    return 0;
}
