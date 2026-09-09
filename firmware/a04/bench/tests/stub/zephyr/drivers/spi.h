/* SPDX-License-Identifier: MIT */
#ifndef BENCH_STUB_SPI_H
#define BENCH_STUB_SPI_H
#include <zephyr/kernel.h>
struct spi_dt_spec { unsigned node; };
#define SPI_WORD_SET(n) (n)
#define SPI_TRANSFER_MSB 0
#define SPI_DT_SPEC_GET(n,o,d) {.node=(n)}
#endif
