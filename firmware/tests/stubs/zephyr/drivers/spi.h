#ifndef AURA_TEST_SPI
#define AURA_TEST_SPI
#include <stddef.h>
#include <stdbool.h>
#define SPI_WORD_SET(x) (x)
#define SPI_TRANSFER_MSB 0
#define DT_NODELABEL(x) 0
#define SPI_DT_SPEC_GET(a, b, c) {0}
struct spi_dt_spec {
    int ignored;
};
struct spi_buf {
    void *buf;
    size_t len;
};
struct spi_buf_set {
    const struct spi_buf *buffers;
    size_t count;
};
static inline bool spi_is_ready_dt(const struct spi_dt_spec *s)
{
    (void)s;
    return true;
}
int spi_transceive_dt(const struct spi_dt_spec *, const struct spi_buf_set *,
                      const struct spi_buf_set *);
int spi_write_dt(const struct spi_dt_spec *, const struct spi_buf_set *);
#endif
