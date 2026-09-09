/* SPDX-License-Identifier: MIT */
#include "nand_model.h"
#include <stdlib.h>
#include <string.h>

void model_init(struct nand_model *m, uint32_t blocks)
{
    memset(m, 0, sizeof(*m));
    m->blocks = blocks;
    memset(m->marker, 255, sizeof(m->marker));
    for (unsigned b = 0; b < AURA_NAND_BLOCKS; ++b) m->highest[b] = -1;
    m->powered = true;
}

void model_destroy(struct nand_model *m)
{
    for (unsigned p = 0; p < AURA_NAND_PAGES; ++p) free(m->pages[p]);
    memset(m, 0, sizeof(*m));
}

void model_power_on(struct nand_model *m)
{
    m->powered = true;
    m->cut = MODEL_NO_CUT;
    m->cut_program = 0;
    m->cut_erase = 0;
    m->lose_completion_only = false;
}

static int bad(void *user, uint32_t block, bool *result)
{
    struct nand_model *m = user;
    if (!m->powered) return AURA_NAND_IO_ERROR;
    if (!m->blocks || m->blocks > 1024 || block >= m->blocks || !result) return AURA_NAND_BAD_ARGUMENT;
    ++m->bad_queries;
    *result = m->remapped[block];
    for (unsigned p = 0; p < 2; ++p)
        for (unsigned n = 0; n < 3; ++n)
            if (m->marker[block][p][n] != 255) *result = true;
    return 0;
}

static int read_page(void *user, uint32_t page, uint16_t column, uint8_t *out, size_t bytes)
{
    struct nand_model *m = user;
    if (!m->powered) return AURA_NAND_IO_ERROR;
    if (!m->blocks || m->blocks > 1024 || page >= m->blocks * 64 || !out || column > 2112 || bytes > 2112u - column)
        return AURA_NAND_BAD_ARGUMENT;
    ++m->reads;
    m->read_bytes += bytes;
    if (m->ecc[page] >= 2) return AURA_NAND_UNCORRECTABLE;
    memset(out, 255, bytes);
    for(size_t n=0;n<bytes;++n){
        size_t c=column+n;
        if(c<2048&&m->pages[page])out[n]=m->pages[page][c];
        if(page%64<2&&(c==0||c==2048||c==2049))
            out[n]=m->marker[page/64][page%64][c==0?0:c-2047];
    }
    return m->ecc[page] ? AURA_NAND_CORRECTED : 0;
}

static int program_page(void *user, uint32_t page, const uint8_t data[2048])
{
    struct nand_model *m = user;
    if (!m->powered) return AURA_NAND_IO_ERROR;
    if (!m->blocks || m->blocks > 1024 || page >= m->blocks * 64 || !data) return AURA_NAND_BAD_ARGUMENT;
    uint32_t block = page / 64, within = page % 64;
    bool unavailable;
    int status = bad(m, block, &unavailable);
    if (status || unavailable) return status ? status : AURA_NAND_BAD_BLOCK;
    /* A04 is stricter than the chip's four partial-program allowance: one
     * attempt per page. Interrupted all-FF attempts are still attempts. */
    if (within < 2 || (int)within <= m->highest[block] || m->attempts[page])
        return AURA_NAND_PROGRAM_ORDER;
    if (!m->pages[page]) {
        m->pages[page] = malloc(2048);
        if (!m->pages[page]) return AURA_NAND_IO_ERROR;
        memset(m->pages[page], 255, 2048);
    }
    for (unsigned i = 0; i < 2048; ++i)
        if ((m->pages[page][i] & data[i]) != data[i]) return AURA_NAND_NOT_ERASED;
    ++m->programs;
    ++m->attempts[page];
    m->highest[block] = (int16_t)within;
    size_t take = 2048;
    bool cut = m->cut_program == m->programs && m->cut != MODEL_NO_CUT;
    if (cut && m->cut == MODEL_CUT_BEFORE) take = 0;
    if (cut && m->cut == MODEL_CUT_PARTIAL) take = m->cut_bytes < 2048 ? m->cut_bytes : 2047;
    if (m->program_failure[block]) take = 11;
    for (size_t i = 0; i < take; ++i) m->pages[page][i] &= data[i];
    if (cut) { if(!m->lose_completion_only)m->powered = false; return AURA_NAND_UNCERTAIN; }
    return m->program_failure[block] ? AURA_NAND_PROGRAM_FAILED : 0;
}

static int erase_block(void *user, uint32_t block)
{
    struct nand_model *m = user;
    if (!m->powered) return AURA_NAND_IO_ERROR;
    if (!m->blocks || m->blocks > 1024 || block >= m->blocks) return AURA_NAND_BAD_ARGUMENT;
    bool unavailable;
    int status = bad(m, block, &unavailable);
    if (status || unavailable) return status ? status : AURA_NAND_BAD_BLOCK;
    ++m->erases;
    bool cut=m->cut_erase==m->erases&&m->cut!=MODEL_NO_CUT;
    unsigned count = m->erase_failure[block] ? 7 : 64;
    if(cut&&m->cut==MODEL_CUT_BEFORE)count=0;
    if(cut&&m->cut==MODEL_CUT_PARTIAL)count=(unsigned)(m->cut_bytes<64?m->cut_bytes:63);
    for (unsigned n = 0; n < count; ++n) {
        unsigned page = block * 64 + n;
        free(m->pages[page]); m->pages[page] = NULL;
        m->attempts[page] = m->ecc[page] = 0;
    }
    if(count==64)m->highest[block] = -1;
    if(cut){if(!m->lose_completion_only)m->powered=false;return AURA_NAND_UNCERTAIN;}
    if (m->erase_failure[block]) return AURA_NAND_ERASE_FAILED;
    return 0;
}

struct aura_nand_io model_io(struct nand_model *m)
{
    return (struct aura_nand_io){m, m->blocks, read_page, program_page, erase_block, bad};
}
