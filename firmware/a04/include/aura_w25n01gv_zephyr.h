/* SPDX-License-Identifier: MIT */
#ifndef AURA_A04_W25N01GV_ZEPHYR_H
#define AURA_A04_W25N01GV_ZEPHYR_H
#include "aura_w25n01gv.h"
#include <zephyr/drivers/spi.h>
#include <zephyr/kernel.h>

struct aura_w25n01gv_zephyr {
    struct aura_w25n01gv device;
    struct spi_dt_spec spi;
    struct k_mutex mutex;
    bool initialized;
};
/* Caller supplies the reviewed devicetree SPI/CS pins. Cold startup only.
 * No devicetree node, GPIO or physical device is implicitly selected. */
int aura_w25n01gv_zephyr_init(struct aura_w25n01gv_zephyr *context,
                             const struct spi_dt_spec *spi);
struct aura_nand_io aura_w25n01gv_zephyr_io(struct aura_w25n01gv_zephyr *context);
/* Configure immediately after cold init, before ordinary NAND callbacks. The
 * same operation mutex protects configuration and both restricted IO views. */
int aura_w25n01gv_zephyr_configure_control(struct aura_w25n01gv_zephyr *context,
                                          uint16_t first, uint16_t second);
struct aura_control_io aura_w25n01gv_zephyr_control_io(struct aura_w25n01gv_zephyr *context);
#endif
