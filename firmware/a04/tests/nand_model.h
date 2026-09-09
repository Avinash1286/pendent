/* SPDX-License-Identifier: MIT */
#ifndef AURA_A04_NAND_MODEL_H
#define AURA_A04_NAND_MODEL_H
#include "aura_nand.h"

/* Test-only sparse chip memory. Heap is confined to the host model. Program
 * attempts, cells and bad markers survive model_power_on(); one-shot cuts do
 * not. This is an electrical/operation fault model, not physical qualification. */
enum model_cut { MODEL_NO_CUT, MODEL_CUT_BEFORE, MODEL_CUT_PARTIAL, MODEL_CUT_AFTER };
struct nand_model {
    uint8_t *pages[AURA_NAND_PAGES];
    uint8_t attempts[AURA_NAND_PAGES];
    uint8_t ecc[AURA_NAND_PAGES];
    uint8_t marker[AURA_NAND_BLOCKS][2][3];
    int16_t highest[AURA_NAND_BLOCKS];
    uint8_t erase_failure[AURA_NAND_BLOCKS];
    uint8_t program_failure[AURA_NAND_BLOCKS];
    bool remapped[AURA_NAND_BLOCKS];
    uint32_t blocks;
    uint64_t reads, read_bytes, programs, erases, bad_queries;
    uint64_t cut_program;
    uint64_t cut_erase;
    enum model_cut cut;
    size_t cut_bytes;
    bool powered;
    bool lose_completion_only;
};
void model_init(struct nand_model *model, uint32_t blocks);
void model_destroy(struct nand_model *model);
void model_power_on(struct nand_model *model);
struct aura_nand_io model_io(struct nand_model *model);
#endif
