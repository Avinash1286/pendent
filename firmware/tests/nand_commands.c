/* Exercise the production NAND command serializer against a strict simulated chip. */
#include "nand.h"
#include <zephyr/drivers/spi.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <stdlib.h>
static uint8_t pages[4][2048], cache[2048], status, config, protection;
static uint32_t row;
static int bad_main = -1, bad_spare = -1, ecc = -1;
static bool wrong_id, program_fail;
#define CHECK(x)                                                                                   \
    do {                                                                                           \
        if (!(x)) {                                                                                \
            fprintf(stderr, "NAND FAIL line %d: %s\n", __LINE__, #x);                              \
            exit(1);                                                                               \
        }                                                                                          \
    } while (0)
static uint32_t addr(const uint8_t *h)
{
    return (uint32_t)h[1] << 16 | (uint32_t)h[2] << 8 | h[3];
}
int spi_write_dt(const struct spi_dt_spec *s, const struct spi_buf_set *tx)
{
    (void)s;
    const uint8_t *h = tx->buffers[0].buf;
    switch (h[0]) {
    case 0xff:
        status = 0;
        config = 0x10;
        return 0;
    case 0x06:
        status |= 2;
        return 0;
    case 0x1f:
        CHECK(status & 2);
        if (h[1] == 0xb0)
            config = h[2];
        else if (h[1] == 0xa0)
            protection = h[2];
        else
            CHECK(false);
        status &= ~2;
        return 0;
    case 0x13:
        row = addr(h);
        status &= 2;
        if ((int)row == ecc)
            status |= 0x20;
        return 0;
    case 0x02:
        CHECK(status & 2);
        CHECK(tx->buffers[1].len == 2048);
        memcpy(cache, tx->buffers[1].buf, 2048);
        return 0;
    case 0x10:
        CHECK(status & 2);
        row = addr(h);
        CHECK(row < 4);
        if (program_fail) {
            status = 8;
            return 0;
        }
        memcpy(pages[row], cache, 2048);
        status = 0;
        return 0;
    case 0xd8:
        CHECK(status & 2);
        row = addr(h);
        CHECK(row % 64 == 0);
        memset(pages, 255, sizeof(pages));
        status = 0;
        return 0;
    default:
        CHECK(false);
        return -EIO;
    }
}
int spi_transceive_dt(const struct spi_dt_spec *s, const struct spi_buf_set *tx,
                      const struct spi_buf_set *rx)
{
    (void)s;
    const uint8_t *h = tx->buffers[0].buf;
    uint8_t *out = rx->buffers[1].buf;
    size_t len = rx->buffers[1].len;
    CHECK(rx->buffers[0].buf == NULL);
    CHECK(rx->buffers[0].len == tx->buffers[0].len);
    switch (h[0]) {
    case 0x9f:
        CHECK(tx->buffers[0].len == 2 && h[1] == 0 && len == 3);
        out[0] = wrong_id ? 0 : 0xef;
        out[1] = 0xaa;
        out[2] = 0x21;
        return 0;
    case 0x0f:
        CHECK(len == 1);
        *out = h[1] == 0xc0 ? status : (h[1] == 0xb0 ? config : protection);
        return 0;
    case 0x03: {
        CHECK(tx->buffers[0].len == 4 && h[3] == 0);
        uint16_t col = (uint16_t)h[1] << 8 | h[2];
        memset(out, 255, len);
        if (col == 2048) {
            CHECK(len == 1);
            if ((int)(row / 64) == bad_spare)
                *out = 0;
        } else {
            CHECK(col == 0);
            if (row < 4)
                memcpy(out, pages[row], len);
            if ((int)(row / 64) == bad_main && row % 64 < 2)
                *out = 0;
        }
        return 0;
    }
    default:
        CHECK(false);
        return -EIO;
    }
}
int main(void)
{
    memset(pages, 255, sizeof(pages));
    wrong_id = true;
    CHECK(aura_nand_init() == -ENODEV);
    wrong_id = false;
    bad_main = 2;
    bad_spare = 3;
    CHECK(!aura_nand_init());
    struct aj_io io = aura_nand_io();
    CHECK(io.bad(2) && io.bad(3) && !io.bad(0));
    CHECK(config == 0x18 && protection == 0);
    puts("PASS exact NAND JEDEC, WREN features and both manufacturer markers");
    uint8_t data[2048], out[2048];
    memset(data, 0x5a, sizeof(data));
    CHECK(!io.write(2, data));
    CHECK(!io.read(2, out) && !memcmp(data, out, 2048));
    CHECK(io.write(2, data) == -EEXIST);
    puts("PASS NAND program command ordering, readback and overwrite refusal");
    ecc = 2;
    CHECK(io.read(2, out) == -EBADMSG);
    ecc = -1;
    program_fail = true;
    CHECK(io.write(3, data) == -EIO);
    program_fail = false;
    puts("PASS ECC and hardware program-failure propagation");
    CHECK(aura_nand_erase_block(2) == -EINVAL);
    CHECK(!aura_nand_erase_block(0));
    CHECK(!io.read(2, out));
    for (unsigned i = 0; i < sizeof(out); i++)
        CHECK(out[i] == 255);
    puts("PASS erase refuses bad blocks and verifies full main area");
    return 0;
}
