/* SPDX-License-Identifier: MIT
 * W25N01GV Rev.R (2023-07-03), buffer mode, internal ECC, standard SPI.
 * See W25N-ADAPTER.md for the command-source and verification scope.
 */
#include "aura_w25n01gv.h"
#include <string.h>

enum { REG_PROTECT=0xa0, REG_CONFIG=0xb0, REG_STATUS=0xc0 };
enum { BUSY=1, WEL=2, EFAIL=4, PFAIL=8, BUF=8, ECC=16 };

static bool bit(const uint8_t *map, uint32_t b) { return (map[b/8] & (1u<<(b%8))) != 0; }
static void mark(uint8_t *map, uint32_t b) { map[b/8] |= (uint8_t)(1u<<(b%8)); }
static void disarm(struct aura_w25n01gv *d, uint32_t b) { d->writable[b/8] &= (uint8_t)~(1u<<(b%8)); }
static int transfer(struct aura_w25n01gv *d, const uint8_t *h, size_t hn,
                    const uint8_t *out, size_t on, uint8_t *in, size_t n)
{
    ++d->transfers;
    int r=d->bus.transfer(d->bus.user,h,hn,out,on,in,n);
    if (!r) d->received_bytes+=n;
    return r ? AURA_NAND_IO_ERROR : 0;
}
static int get_reg(struct aura_w25n01gv *d, uint8_t reg, uint8_t *v)
{ const uint8_t h[]={0x0f,reg}; return transfer(d,h,sizeof(h),NULL,0,v,1); }
static int ready(struct aura_w25n01gv *d, uint8_t *status)
{
    uint64_t start=d->bus.now_ms(d->bus.user);
    /* Poll count is a second bound if the injected/platform clock stalls. */
    for (unsigned poll=0;poll<301;++poll) {
        int r=get_reg(d,REG_STATUS,status);
        if (r || !(*status&BUSY)) return r;
        if (d->bus.now_ms(d->bus.user)-start>=30) break;
        d->bus.sleep_us(d->bus.user,100);
    }
    return AURA_NAND_IO_ERROR;
}
static int set_reg(struct aura_w25n01gv *d, uint8_t reg, uint8_t v, uint8_t mask)
{
    uint8_t status;
    int r=ready(d,&status); if(r)return r;
    const uint8_t h[]={0x1f,reg,v};
    r=transfer(d,h,sizeof(h),NULL,0,NULL,0); if(r)return r;
    r=ready(d,&status); if(r)return r;
    r=get_reg(d,reg,&status);
    return r ? r : ((status&mask)==(v&mask) ? 0 : AURA_NAND_IO_ERROR);
}
static int load_page(struct aura_w25n01gv *d, uint32_t page, bool check_ecc)
{
    uint8_t status;
    int r=ready(d,&status); if(r)return r;
    const uint8_t h[]={0x13,0,(uint8_t)(page>>8),(uint8_t)page};
    r=transfer(d,h,sizeof(h),NULL,0,NULL,0); if(r)return r;
    r=ready(d,&status); if(r)return r;
    if (!check_ecc) return 0;
    unsigned ec=(status>>4)&3;
    if(ec>=2){++d->failed_reads;return AURA_NAND_UNCORRECTABLE;}
    if(ec){++d->corrected_reads;return AURA_NAND_CORRECTED;}
    return 0;
}
static int read_cache(struct aura_w25n01gv *d,uint16_t column,uint8_t *out,size_t n)
{
    const uint8_t h[]={0x03,(uint8_t)(column>>8),(uint8_t)column,0};
    return transfer(d,h,sizeof(h),NULL,0,out,n);
}
static int read_main(struct aura_w25n01gv *d,uint32_t page,uint16_t col,uint8_t *out,size_t n)
{
    int r=load_page(d,page,true); if(r<0)return r;
    int io=read_cache(d,col,out,n); return io ? io : r;
}
static bool all_ff(const uint8_t *p,size_t n)
{ for(size_t i=0;i<n;++i)if(p[i]!=255)return false; return true; }
static int enable_write(struct aura_w25n01gv *d)
{
    const uint8_t h=0x06; uint8_t s;
    int r=transfer(d,&h,1,NULL,0,NULL,0); if(r)return r;
    r=get_reg(d,REG_STATUS,&s);
    return r ? r : ((s&(BUSY|WEL))==WEL ? 0 : AURA_NAND_IO_ERROR);
}
static bool control_block(const struct aura_w25n01gv *d,uint32_t b)
{return d->control_configured&&(b==d->control_blocks[0]||b==d->control_blocks[1]);}
static bool unavailable(const struct aura_w25n01gv *d,uint32_t b,bool control)
{return bit(d->excluded,b)||(control?!control_block(d,b):control_block(d,b));}
static int bad(void *user,uint32_t block,bool *out)
{
    struct aura_w25n01gv *d=user;
    if(!d||!d->ready||block>=AURA_NAND_BLOCKS||!out)return AURA_NAND_BAD_ARGUMENT;
    d->ordinary_started=true;*out=unavailable(d,block,false); return 0;
}
static int read_access(void *user,uint32_t page,uint16_t col,uint8_t *out,size_t n,bool control)
{
    struct aura_w25n01gv *d=user;
    if(!d||!d->ready||page>=AURA_NAND_PAGES||!out||!n||col>=2048||n>2048u-col)
        return AURA_NAND_BAD_ARGUMENT;
    if(!control)d->ordinary_started=true;
    if(unavailable(d,page/64,control))return AURA_NAND_BAD_BLOCK;
    uint8_t failed=d->failed_page[page/64];
    if((failed&0x7f)==page%64+1)
        return (failed&0x80)?AURA_NAND_UNCERTAIN:AURA_NAND_PROGRAM_FAILED;
    return read_main(d,page,col,out,n);
}
static int read_page(void *u,uint32_t p,uint16_t c,uint8_t *out,size_t n)
{return read_access(u,p,c,out,n,false);}
static int control_read(void *u,uint32_t p,uint16_t c,uint8_t *out,size_t n)
{return read_access(u,p,c,out,n,true);}
static int program_fault(struct aura_w25n01gv *d,uint32_t b,uint32_t p,int result,bool uncertain)
{
    disarm(d,b);d->failed_page[b]=(uint8_t)((p+1)|(uncertain?0x80:0));return result;
}
static int program_access(void *user,uint32_t page,const uint8_t data[2048],bool control)
{
    struct aura_w25n01gv *d=user;
    if(!d||!d->ready||page>=AURA_NAND_PAGES||!data)return AURA_NAND_BAD_ARGUMENT;
    if(!control)d->ordinary_started=true;
    /* An all-FF A04 page is never a record. Refuse it so pre-existing erased
     * data cannot masquerade as evidence of a completed uncertain program. */
    if(all_ff(data,2048))return AURA_NAND_BAD_ARGUMENT;
    uint32_t b=page/64,p=page%64;
    if(unavailable(d,b,control))return AURA_NAND_BAD_BLOCK;
    if(d->failed_page[b]||!bit(d->writable,b)||p<2||(int)p<=d->highest[b])return AURA_NAND_PROGRAM_ORDER;
    int r=read_main(d,page,0,d->verify,2048);
    if(r||!all_ff(d->verify,2048)){disarm(d,b);return r<0?r:AURA_NAND_NOT_ERASED;}
    /* Consume permission before even loading the cache. No retry of uncertain
     * operations through this API, including a transport failure during load. */
    d->highest[b]=(int8_t)p;
    r=enable_write(d); if(r){disarm(d,b);return r;}
    const uint8_t h[]={0x02,0,0};
    r=transfer(d,h,sizeof(h),data,2048,NULL,0);
    if(r){disarm(d,b);return r;}
    const uint8_t exec[]={0x10,0,(uint8_t)(page>>8),(uint8_t)page};
    ++d->program_attempts;
    int execute_result=transfer(d,exec,sizeof(exec),NULL,0,NULL,0);
    /* Even a lost transport acknowledgement may follow a completed execute.
     * Resolve through status AND full readback; never reissue the command.
     * If status cannot be established, block this page from a generic read
     * promotion until cold recovery, while keeping earlier pages readable. */
    uint8_t status;
    r=ready(d,&status);
    if(r)return program_fault(d,b,p,AURA_NAND_UNCERTAIN,true);
    if(status&PFAIL)return program_fault(d,b,p,AURA_NAND_PROGRAM_FAILED,false);
    if(status&WEL)return program_fault(d,b,p,AURA_NAND_UNCERTAIN,true);
    r=read_main(d,page,0,d->verify,2048);
    if(r<0)return program_fault(d,b,p,r,r==AURA_NAND_IO_ERROR);
    if(memcmp(data,d->verify,2048))return program_fault(d,b,p,AURA_NAND_PROGRAM_FAILED,false);
    if(execute_result)++d->resolved_execute_errors;
    return 0;
}
static int program(void *u,uint32_t p,const uint8_t data[2048])
{return program_access(u,p,data,false);}
static int control_program(void *u,uint32_t p,const uint8_t data[2048])
{return program_access(u,p,data,true);}
static int erase_access(void *user,uint32_t b,bool control)
{
    struct aura_w25n01gv *d=user;
    if(!d||!d->ready||b>=AURA_NAND_BLOCKS)return AURA_NAND_BAD_ARGUMENT;
    if(!control)d->ordinary_started=true;
    /* Privilege is checked here, not trusted from a caller's control config. */
    if(unavailable(d,b,control))return AURA_NAND_BAD_BLOCK;
    if(d->failed_page[b])return AURA_NAND_BAD_BLOCK;
    disarm(d,b);
    /* No data reclamation: refuse any non-FF or ECC-corrected page, even when
     * a caller claims it is free. This catches torn erase/header cases. */
    for(unsigned p=0;!control&&p<64;++p){
        int r=read_main(d,b*64+p,0,d->verify,2048);
        if(r||!all_ff(d->verify,2048))return r<0?r:AURA_NAND_NOT_ERASED;
    }
    uint8_t status;
    int r=ready(d,&status); if(r)return r;
    r=enable_write(d); if(r)return r;
    uint32_t page=b*64;
    const uint8_t h[]={0xd8,0,(uint8_t)(page>>8),(uint8_t)page};
    ++d->erase_attempts;
    r=transfer(d,h,sizeof(h),NULL,0,NULL,0);
    if(r){d->failed_page[b]=255;return AURA_NAND_UNCERTAIN;}
    r=ready(d,&status); if(r){d->failed_page[b]=255;return AURA_NAND_UNCERTAIN;}
    if(status&EFAIL){d->failed_page[b]=255;return AURA_NAND_ERASE_FAILED;}
    if(status&WEL){d->failed_page[b]=255;return AURA_NAND_UNCERTAIN;}
    for(unsigned p=0;p<64;++p){
        r=read_main(d,page+p,0,d->verify,2048);
        if(r||!all_ff(d->verify,2048)){
            d->failed_page[b]=255;return r<0?r:AURA_NAND_ERASE_FAILED;
        }
    }
    d->highest[b]=1; mark(d->writable,b); return 0;
}
static int erase(void *u,uint32_t b){return erase_access(u,b,false);}
static int control_erase(void *u,uint32_t b){return erase_access(u,b,true);}
static int control_bad(void *user,uint32_t b,bool *out)
{
    struct aura_w25n01gv *d=user;
    if(!d||!d->ready||b>=AURA_NAND_BLOCKS||!out)return AURA_NAND_BAD_ARGUMENT;
    *out=unavailable(d,b,true);return 0;
}
int aura_w25n01gv_init(struct aura_w25n01gv *d,const struct aura_w25n01gv_bus *bus)
{
    if(!d||!bus||!bus->transfer||!bus->now_ms||!bus->sleep_us)return AURA_NAND_BAD_ARGUMENT;
    struct aura_w25n01gv_bus copy=*bus;
    memset(d,0,sizeof(*d)); d->bus=copy; memset(d->highest,-1,sizeof(d->highest));
    d->bus.sleep_us(d->bus.user,2000);
    uint8_t reset=0xff,status,id[3];
    int r=transfer(d,&reset,1,NULL,0,NULL,0); if(r)return r;
    d->bus.sleep_us(d->bus.user,2000);
    r=ready(d,&status); if(r)return r;
    const uint8_t ident[]={0x9f,0};
    r=transfer(d,ident,2,NULL,0,id,sizeof(id)); if(r)return r;
    if(id[0]!=0xef||id[1]!=0xaa||id[2]!=0x21)return AURA_NAND_IO_ERROR;
    uint8_t config,protect;
    r=get_reg(d,REG_CONFIG,&config); if(r)return r;
    r=get_reg(d,REG_PROTECT,&protect); if(r)return r;
    /* A04 has no OTP/protection-lock provisioning. Do not overwrite an
     * unexpected lock or enter OTP access in order to force initialization. */
    if((config&0xc4)||(protect&0x83))return AURA_NAND_IO_ERROR;
    r=set_reg(d,REG_CONFIG,(uint8_t)((config&~0x58u)|BUF),0x5c); if(r)return r;
    uint8_t lut[80]; const uint8_t lh[]={0xa5,0};
    r=transfer(d,lh,2,NULL,0,lut,sizeof(lut)); if(r)return r;
    for(unsigned i=0;i<20;++i){
        uint16_t l=(uint16_t)((uint16_t)lut[i*4]<<8|lut[i*4+1]);
        uint16_t p=(uint16_t)((uint16_t)lut[i*4+2]<<8|lut[i*4+3]);
        if(!l&&!p)continue;
        uint16_t logical=l&0x3fff;
        if(!(l&0x8000)||logical>=1024||p>=1024)return AURA_NAND_IO_ERROR;
        mark(d->excluded,logical); mark(d->excluded,p);
    }
    for(uint32_t b=0;b<1024;++b){
        if(bit(d->excluded,b))continue;
        for(unsigned p=0;p<2;++p){
            uint8_t main_marker,spare[2];
            r=load_page(d,b*64+p,false); if(r)return r;
            r=read_cache(d,0,&main_marker,1); if(r)return r;
            r=read_cache(d,2048,spare,2); if(r)return r;
            if(main_marker!=255||spare[0]!=255||spare[1]!=255){mark(d->excluded,b);break;}
        }
    }
    r=set_reg(d,REG_CONFIG,(uint8_t)((config&~0x58u)|BUF|ECC),0x5c); if(r)return r;
    r=set_reg(d,REG_PROTECT,0,0xff); if(r)return r;
    for(unsigned b=0;b<1024;++b)d->excluded_blocks+=bit(d->excluded,b);
    d->ready=true; return 0;
}
struct aura_nand_io aura_w25n01gv_io(struct aura_w25n01gv *d)
{return (struct aura_nand_io){d,d&&d->ready?1024u:0u,read_page,program,erase,bad};}
int aura_w25n01gv_configure_control(struct aura_w25n01gv *d,uint16_t first,uint16_t second)
{
    if(!d||!d->ready||first>=1024||second>=1024||first==second)return AURA_NAND_BAD_ARGUMENT;
    if(d->control_configured)
        return d->control_blocks[0]==first&&d->control_blocks[1]==second?0:AURA_CONTROL_CONFLICT;
    if(d->ordinary_started)return AURA_CONTROL_CONFLICT;
    if(bit(d->excluded,first)||bit(d->excluded,second))return AURA_NAND_BAD_BLOCK;
    d->control_blocks[0]=first;d->control_blocks[1]=second;d->control_configured=true;return 0;
}
struct aura_control_io aura_w25n01gv_control_io(struct aura_w25n01gv *d)
{
    struct aura_control_io io={
        .nand={d,d&&d->ready&&d->control_configured?1024u:0u,control_read,control_program,NULL,control_bad},
        .erase_user=d,.erase_control=control_erase};
    return io;
}
