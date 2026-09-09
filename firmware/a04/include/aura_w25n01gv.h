/* SPDX-License-Identifier: MIT */
#ifndef AURA_A04_W25N01GV_H
#define AURA_A04_W25N01GV_H
#include "aura_nand.h"

/* One transfer is one complete CS assertion: header then optional TX or RX.
 * RX clocks send don't-care bytes; return zero only when all bytes transferred.
 * All callbacks are synchronous. Caller serializes complete NAND operations,
 * including initialization, because the chip has one shared page cache.
 * A command transport must itself have a bounded hardware timeout. */
struct aura_w25n01gv_bus {
    void *user;
    int (*transfer)(void *user, const uint8_t *header, size_t header_bytes,
                    const uint8_t *out, size_t out_bytes, uint8_t *in, size_t in_bytes);
    uint64_t (*now_ms)(void *user);
    void (*sleep_us)(void *user, uint32_t microseconds);
};

struct aura_w25n01gv {
    struct aura_w25n01gv_bus bus;
    uint8_t excluded[AURA_NAND_BLOCKS / 8];
    uint8_t writable[AURA_NAND_BLOCKS / 8];
    int8_t highest[AURA_NAND_BLOCKS];
    /* One failed/uncertain program per retired block: page+1, bit7 uncertain.
     * 255 records an erase fault. Prior pages remain readable. Cold recovery
     * reinitializes this volatile guard and must fully validate the archive. */
    uint8_t failed_page[AURA_NAND_BLOCKS];
    uint8_t verify[AURA_NAND_PAGE_BYTES];
    uint32_t corrected_reads, failed_reads, excluded_blocks;
    uint32_t program_attempts, erase_attempts;
    uint32_t resolved_execute_errors;
    uint64_t transfers, received_bytes;
    bool ready;
};

/* Cold startup only, after the owner has ensured stable power and no live flash
 * operation. Issues RESET and volatile config writes; never OTP/LUT changes.
 * Scans only factory marker locations, not user audio. No array erase here.
 * The backend deliberately cannot resume writing a block from a previous boot.
 * It permits erasing only completely FF, ECC-clean main areas, then authorizes
 * increasing single-program pages 2..63 for that block in the current boot.
 * Populated reclamation/migration requires a separately designed API. */
int aura_w25n01gv_init(struct aura_w25n01gv *device, const struct aura_w25n01gv_bus *bus);
struct aura_nand_io aura_w25n01gv_io(struct aura_w25n01gv *device);
#endif
