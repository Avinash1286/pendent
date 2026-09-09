/* SPDX-License-Identifier: MIT */
#include "aura_w25n01gv_zephyr.h"
#include <string.h>

static int transaction(void *user,const uint8_t *h,size_t hn,
                       const uint8_t *out,size_t on,uint8_t *in,size_t n)
{
    struct aura_w25n01gv_zephyr *z=user;
    struct spi_buf txb[]={{.buf=(void *)h,.len=hn},{.buf=(void *)out,.len=on?on:n}};
    struct spi_buf rxb[]={{.buf=NULL,.len=hn},{.buf=in,.len=n}};
    struct spi_buf_set tx={.buffers=txb,.count=(on||n)?2:1};
    struct spi_buf_set rx={.buffers=rxb,.count=2};
    return n?spi_transceive_dt(&z->spi,&tx,&rx):spi_write_dt(&z->spi,&tx);
}
static uint64_t now(void *user){(void)user;return (uint64_t)k_uptime_get();}
static void sleep_us(void *user,uint32_t us){(void)user;k_usleep((int32_t)us);}

static int lock(struct aura_w25n01gv_zephyr *z)
{
    if(!z||!z->initialized||k_is_in_isr())return AURA_NAND_BAD_ARGUMENT;
    return k_mutex_lock(&z->mutex,K_FOREVER)?AURA_NAND_IO_ERROR:0;
}
static int zread(void *u,uint32_t p,uint16_t c,uint8_t *out,size_t n)
{
    struct aura_w25n01gv_zephyr *z=u; int r=lock(z); if(r)return r;
    struct aura_nand_io io=aura_w25n01gv_io(&z->device);
    r=io.read(io.user,p,c,out,n); k_mutex_unlock(&z->mutex); return r;
}
static int zprogram(void *u,uint32_t p,const uint8_t data[2048])
{
    struct aura_w25n01gv_zephyr *z=u; int r=lock(z); if(r)return r;
    struct aura_nand_io io=aura_w25n01gv_io(&z->device);
    r=io.program(io.user,p,data); k_mutex_unlock(&z->mutex); return r;
}
static int zerase(void *u,uint32_t b)
{
    struct aura_w25n01gv_zephyr *z=u; int r=lock(z); if(r)return r;
    struct aura_nand_io io=aura_w25n01gv_io(&z->device);
    r=io.erase(io.user,b); k_mutex_unlock(&z->mutex); return r;
}
static int zbad(void *u,uint32_t b,bool *out)
{
    struct aura_w25n01gv_zephyr *z=u; int r=lock(z); if(r)return r;
    struct aura_nand_io io=aura_w25n01gv_io(&z->device);
    r=io.bad(io.user,b,out); k_mutex_unlock(&z->mutex); return r;
}
static int zcontrol_read(void *u,uint32_t p,uint16_t c,uint8_t *out,size_t n)
{
    struct aura_w25n01gv_zephyr *z=u; int r=lock(z); if(r)return r;
    struct aura_control_io io=aura_w25n01gv_control_io(&z->device);
    r=io.nand.read(io.nand.user,p,c,out,n); k_mutex_unlock(&z->mutex); return r;
}
static int zcontrol_program(void *u,uint32_t p,const uint8_t data[2048])
{
    struct aura_w25n01gv_zephyr *z=u; int r=lock(z); if(r)return r;
    struct aura_control_io io=aura_w25n01gv_control_io(&z->device);
    r=io.nand.program(io.nand.user,p,data); k_mutex_unlock(&z->mutex); return r;
}
static int zcontrol_bad(void *u,uint32_t b,bool *out)
{
    struct aura_w25n01gv_zephyr *z=u; int r=lock(z); if(r)return r;
    struct aura_control_io io=aura_w25n01gv_control_io(&z->device);
    r=io.nand.bad(io.nand.user,b,out); k_mutex_unlock(&z->mutex); return r;
}
static int zcontrol_erase(void *u,uint32_t b)
{
    struct aura_w25n01gv_zephyr *z=u; int r=lock(z); if(r)return r;
    struct aura_control_io io=aura_w25n01gv_control_io(&z->device);
    r=io.erase_control(io.erase_user,b); k_mutex_unlock(&z->mutex); return r;
}
int aura_w25n01gv_zephyr_configure_control(struct aura_w25n01gv_zephyr *z,
                                          uint16_t first,uint16_t second)
{
    int r=lock(z); if(r)return r;
    r=aura_w25n01gv_configure_control(&z->device,first,second);
    k_mutex_unlock(&z->mutex); return r;
}
int aura_w25n01gv_zephyr_init(struct aura_w25n01gv_zephyr *z,const struct spi_dt_spec *spi)
{
    if(!z||!spi||k_is_in_isr()||!spi_is_ready_dt(spi))return AURA_NAND_BAD_ARGUMENT;
    spi_operation_t op=spi->config.operation;
    const spi_operation_t forbidden=SPI_OP_MODE_SLAVE|SPI_TRANSFER_LSB|SPI_HALF_DUPLEX|
        SPI_HOLD_ON_CS|SPI_LOCK_ON|SPI_CS_ACTIVE_HIGH;
    spi_operation_t mode=op&(SPI_MODE_CPOL|SPI_MODE_CPHA);
    if(SPI_WORD_SIZE_GET(op)!=8||(op&forbidden)||(mode&&mode!=(SPI_MODE_CPOL|SPI_MODE_CPHA))||
        !spi->config.frequency||spi->config.frequency>32000000u)return AURA_NAND_BAD_ARGUMENT;
#ifdef CONFIG_SPI_EXTENDED_MODES
    if((op&SPI_LINES_MASK)!=SPI_LINES_SINGLE)return AURA_NAND_BAD_ARGUMENT;
#endif
    struct spi_dt_spec copy=*spi;
    memset(z,0,sizeof(*z)); z->spi=copy; k_mutex_init(&z->mutex);
    struct aura_w25n01gv_bus bus={z,transaction,now,sleep_us};
    int r=aura_w25n01gv_init(&z->device,&bus);
    z->initialized=r==0; return r;
}
struct aura_nand_io aura_w25n01gv_zephyr_io(struct aura_w25n01gv_zephyr *z)
{return (struct aura_nand_io){z,z&&z->initialized?1024u:0u,zread,zprogram,zerase,zbad};}
struct aura_control_io aura_w25n01gv_zephyr_control_io(struct aura_w25n01gv_zephyr *z)
{
    struct aura_control_io io={
        .nand={z,z&&z->initialized&&z->device.control_configured?1024u:0u,
               zcontrol_read,zcontrol_program,NULL,zcontrol_bad},
        .erase_user=z,.erase_control=zcontrol_erase};
    return io;
}
