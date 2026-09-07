#ifndef AURA_NAND_H
#define AURA_NAND_H
#include "journal.h"
int aura_nand_init(void);
struct aj_io aura_nand_io(void);
int aura_nand_erase_block(uint32_t block);
#endif
