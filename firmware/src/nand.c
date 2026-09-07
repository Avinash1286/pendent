/* SPDX-License-Identifier: MIT
 * W25N01GV Rev R command set. Internal ECC, buffer mode; single page programs.
 * Factory bad marks are read with ECC disabled before use. No block erase API.
 */
#include "nand.h"
#include <zephyr/kernel.h>
#include <zephyr/drivers/spi.h>
#include <errno.h>
#include <string.h>
static const struct spi_dt_spec flash =
    SPI_DT_SPEC_GET(DT_NODELABEL(nand0), SPI_WORD_SET(8) | SPI_TRANSFER_MSB, 0);
static uint8_t bad_blocks[128];
static uint8_t check[AJ_PAGE];
static int command(const uint8_t *header, size_t n, const uint8_t *out, size_t olen, uint8_t *in,
                   size_t ilen)
{
    struct spi_buf txb[2] = {{.buf = (void *)header, .len = n},
                             {.buf = (void *)out, .len = olen ? olen : ilen}};
    struct spi_buf rxb[2] = {{.buf = NULL, .len = n}, {.buf = in, .len = ilen}};
    struct spi_buf_set tx = {.buffers = txb, .count = (olen || ilen) ? 2 : 1},
                       rx = {.buffers = rxb, .count = 2};
    return ilen ? spi_transceive_dt(&flash, &tx, &rx) : spi_write_dt(&flash, &tx);
}
static int feature(uint8_t reg, uint8_t *v)
{
    uint8_t h[] = {0x0f, reg};
    return command(h, 2, NULL, 0, v, 1);
}
static int set_feature(uint8_t reg, uint8_t v)
{
    uint8_t enable = 0x06;
    int r = command(&enable, 1, NULL, 0, NULL, 0);
    if (r)
        return r;
    uint8_t h[] = {0x1f, reg, v};
    return command(h, 3, NULL, 0, NULL, 0);
}
static int wait_ready(uint8_t *status)
{
    int64_t until = k_uptime_get() + 30;
    do {
        int r = feature(0xc0, status);
        if (r)
            return r;
        if (!(*status & 1))
            return 0;
        k_usleep(100);
    } while (k_uptime_get() < until);
    return -ETIMEDOUT;
}
static int cache_page(uint32_t page, bool ecc)
{
    uint8_t h[] = {0x13, (uint8_t)(page >> 16), (uint8_t)(page >> 8), (uint8_t)page}, s;
    int r = command(h, 4, NULL, 0, NULL, 0);
    if (r)
        return r;
    r = wait_ready(&s);
    if (r)
        return r;
    return ecc && ((s >> 4) & 3) >= 2 ? -EBADMSG : 0;
}
static int cache_read(uint16_t column, uint8_t *out, size_t n)
{
    uint8_t h[] = {0x03, (uint8_t)(column >> 8), (uint8_t)column, 0};
    return command(h, 4, NULL, 0, out, n);
}
static int read_page(uint32_t page, uint8_t *out)
{
    int r = cache_page(page, true);
    if (r)
        return r;
    return cache_read(0, out, AJ_PAGE);
}
static bool is_bad(uint32_t block)
{
    return block >= 1024 || (bad_blocks[block / 8] & (1u << (block % 8)));
}
static int program_page(uint32_t page, const uint8_t *data)
{
    if (page >= 65536 || is_bad(page / 64))
        return -EINVAL;
    /* Never rely on software high water alone when writing unique audio. */
    int r = read_page(page, check);
    if (r)
        return r;
    for (unsigned i = 0; i < AJ_PAGE; i++)
        if (check[i] != 255)
            return -EEXIST;
    uint8_t en = 0x06, status;
    r = command(&en, 1, NULL, 0, NULL, 0);
    if (r)
        return r;
    r = feature(0xc0, &status);
    if (r || !(status & 2))
        return r ? r : -EACCES;
    uint8_t load[] = {0x02, 0, 0};
    r = command(load, 3, data, AJ_PAGE, NULL, 0);
    if (r)
        return r;
    uint8_t exec[] = {0x10, (uint8_t)(page >> 16), (uint8_t)(page >> 8), (uint8_t)page};
    r = command(exec, 4, NULL, 0, NULL, 0);
    if (r)
        return r;
    r = wait_ready(&status);
    if (r || status & 8)
        return r ? r : -EIO;
    r = read_page(page, check);
    if (r)
        return r;
    return memcmp(data, check, AJ_PAGE) ? -EBADMSG : 0;
}
int aura_nand_init(void)
{
    if (!spi_is_ready_dt(&flash))
        return -ENODEV;
    uint8_t reset = 0xff, id[3], status;
    int r = command(&reset, 1, NULL, 0, NULL, 0);
    if (r)
        return r;
    k_msleep(2);
    r = wait_ready(&status);
    if (r)
        return r;
    uint8_t h[] = {0x9f, 0};
    r = command(h, 2, NULL, 0, id, 3);
    if (r)
        return r;
    if (id[0] != 0xef || id[1] != 0xaa || id[2] != 0x21)
        return -ENODEV;
    r = set_feature(0xb0, 0x08);
    if (r)
        return r; /* BUF=1, ECC=0 for manufacturer markers */
    memset(bad_blocks, 0, sizeof(bad_blocks));
    for (uint32_t b = 0; b < 1024; b++) {
        for (uint32_t p = 0; p < 2; p++) {
            uint8_t m, main_marker;
            int e = cache_page(b * 64 + p, false);
            if (!e)
                e = cache_read(2048, &m, 1);
            if (!e)
                e = cache_read(0, &main_marker, 1);
            if (e || m != 255 || main_marker != 255) {
                bad_blocks[b / 8] |= 1u << (b % 8);
                break;
            }
        }
    }
    r = set_feature(0xa0, 0);
    if (r)
        return r;
    r = set_feature(0xb0, 0x18);
    if (r)
        return r;
    r = feature(0xb0, &status);
    if (r || ((status & 0x18) != 0x18))
        return r ? r : -EIO;
    return 0;
}
struct aj_io aura_nand_io(void)
{
    return (struct aj_io){read_page, program_page, is_bad, 65536};
}
int aura_nand_erase_block(uint32_t block)
{
    if (block >= 1024 || is_bad(block))
        return -EINVAL;
    uint8_t en = 0x06, status;
    int r = command(&en, 1, NULL, 0, NULL, 0);
    if (r)
        return r;
    r = feature(0xc0, &status);
    if (r || !(status & 2))
        return r ? r : -EACCES;
    uint32_t page = block * 64;
    uint8_t h[] = {0xd8, (uint8_t)(page >> 16), (uint8_t)(page >> 8), (uint8_t)page};
    r = command(h, 4, NULL, 0, NULL, 0);
    if (r)
        return r;
    r = wait_ready(&status);
    if (r || status & 4)
        return r ? r : -EIO;
    /* Verify complete erased main area. Factory bad blocks were skipped. */
    for (unsigned n = 0; n < 64; n++) {
        r = read_page(page + n, check);
        if (r)
            return r;
        for (unsigned j = 0; j < AJ_PAGE; j++)
            if (check[j] != 255)
                return -EIO;
    }
    return 0;
}
