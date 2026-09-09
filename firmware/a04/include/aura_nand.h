/* SPDX-License-Identifier: MIT */
#ifndef AURA_A04_NAND_H
#define AURA_A04_NAND_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define AURA_NAND_PAGE_BYTES 2048u
#define AURA_NAND_SPARE_BYTES 64u
#define AURA_NAND_PAGES_PER_BLOCK 64u
#define AURA_NAND_BLOCKS 1024u
#define AURA_NAND_PAGES (AURA_NAND_BLOCKS * AURA_NAND_PAGES_PER_BLOCK)
#define AURA_NAND_CORRECTED 1
#define AURA_NAND_BAD_ARGUMENT (-300)
#define AURA_NAND_IO_ERROR (-301)
#define AURA_NAND_UNCORRECTABLE (-302)
#define AURA_NAND_PROGRAM_FAILED (-303)
#define AURA_NAND_ERASE_FAILED (-304)
#define AURA_NAND_UNCERTAIN (-305)
#define AURA_NAND_NOT_ERASED (-306)
#define AURA_NAND_BAD_BLOCK (-307)
#define AURA_NAND_PROGRAM_ORDER (-308)

/* An initialized W25N01GV-compatible backend, with buffer mode/internal ECC.
 * read() returns 0 or CORRECTED only for usable bytes, negative otherwise.
 * program() is one full main-page program, never a partial-page update.
 * A nonzero write result can mean physical bytes changed: never retry that page.
 * bad() includes factory markers and excluded hardware-remapping endpoints.
 * No journal is permitted to erase a populated source block through this API.
 * Backend/owner must serialize all operations. No GPIO assignments live here. */
struct aura_nand_io {
    void *user;
    uint32_t blocks;
    int (*read)(void *user, uint32_t page, uint16_t column, uint8_t *out, size_t bytes);
    int (*program)(void *user, uint32_t page, const uint8_t data[AURA_NAND_PAGE_BYTES]);
    int (*erase)(void *user, uint32_t block);
    int (*bad)(void *user, uint32_t block, bool *bad);
};
#endif
