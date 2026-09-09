/* SPDX-License-Identifier: MIT
 * Command-level device model for the production W25N01GV core. This tests
 * actual opcodes, CS transaction boundaries, dummy clocks and error handling.
 * It does not model analogue timing, ECC encoding or a real SPI peripheral.
 */
#include "aura_w25n01gv.h"
#include "aura_journal.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct chip {
    uint8_t *pages[65536], ecc[65536], markers[1024][2][3];
    uint8_t lut[80], cache[2048], config, protect, status;
    uint8_t persistent_config, persistent_protect;
    int16_t highest[1024];
    uint16_t cached_page;
    uint32_t command_count[256], marker_bytes, programs, erases, busy_reads;
    uint32_t fail_read_page;
    uint64_t us;
    bool wrong_id, ignore_config, refuse_wel, busy_forever, stalled_clock;
    bool program_fail, execute_lost, erase_fail, erase_lost, bad_erase_readback;
    bool cache_loaded, program_bad_readback, program_fail_after_full, program_busy_forever, execute_not_received;
    bool erase_ignored, erase_corrected, erase_busy_forever;
};
static struct chip c;
static struct aura_w25n01gv d;
static struct aura_journal journal;
static struct aura_archive_writer writer;

static void fresh(void)
{
    for(unsigned p=0;p<65536;++p)free(c.pages[p]);
    memset(&c,0,sizeof(c));
    memset(c.markers,255,sizeof(c.markers));
    memset(c.highest,-1,sizeof(c.highest));
    c.fail_read_page=UINT32_MAX;
}
static uint8_t *page(uint32_t p)
{
    if(!c.pages[p]){c.pages[p]=malloc(2048);assert(c.pages[p]);memset(c.pages[p],255,2048);}
    return c.pages[p];
}
static uint32_t address(const uint8_t *h,size_t n)
{assert(n==4&&h[1]==0);return (uint32_t)h[2]*256+h[3];}
static int command(void *u,const uint8_t *h,size_t hn,const uint8_t *out,size_t on,uint8_t *in,size_t n)
{
    (void)u; assert(h&&hn&&!(on&&n)); ++c.command_count[h[0]];
    switch(h[0]){
    case 0xff:
        assert(hn==1&&!on&&!n); c.config=(uint8_t)(0x18|c.persistent_config);
        c.protect=(uint8_t)(0x7c|c.persistent_protect); c.status=0;c.cache_loaded=false;return 0;
    case 0x9f:
        assert(hn==2&&h[1]==0&&!on&&n==3);
        in[0]=c.wrong_id?0:0xef;in[1]=0xaa;in[2]=0x21;return 0;
    case 0x0f:
        assert(hn==2&&!on&&n==1);
        if(h[1]==0xb0)*in=c.config;
        else if(h[1]==0xa0)*in=c.protect;
        else{assert(h[1]==0xc0);*in=c.status;if(c.busy_forever||c.busy_reads)*in|=1;if(c.busy_reads)--c.busy_reads;}
        return 0;
    case 0x1f:
        assert(hn==3&&!on&&!n);
        if(h[1]==0xb0){assert(!(h[2]&0xc4));if(!c.ignore_config)c.config=h[2];}
        else{assert(h[1]==0xa0&&h[2]==0);c.protect=h[2];}
        return 0;
    case 0xa5:
        assert(hn==2&&h[1]==0&&!on&&n==80);memcpy(in,c.lut,80);return 0;
    case 0x13:{
        assert(!on&&!n);uint32_t p=address(h,hn);assert(p<65536);
        if(p==c.fail_read_page)return -1;
        c.cached_page=(uint16_t)p;c.cache_loaded=false;
        c.status&=(uint8_t)~0x32u; /* Page read clears WEL and ECC indication. */
        if(c.config&0x10)c.status|=(uint8_t)(c.ecc[p]<<4);
        c.busy_reads=1;return 0;
    }
    case 0x03:{
        assert(hn==4&&h[3]==0&&!on&&in&&n&&(c.config&8));
        uint32_t col=(uint32_t)h[1]*256+h[2],p=c.cached_page;
        assert(col+n<=2112);
        for(size_t i=0;i<n;++i){
            uint32_t index=col+(uint32_t)i;
            in[i]=index<2048&&c.pages[p]?c.pages[p][index]:255;
            if(p%64<2&&(index==0||index==2048||index==2049)){
                unsigned marker=index==0?0:index-2047;
                in[i]=c.markers[p/64][p%64][marker];
                if(!(c.config&0x10))++c.marker_bytes;
            }
        }
        return 0;
    }
    case 0x06:
        assert(hn==1&&!on&&!n);if(!c.refuse_wel)c.status|=2;return 0;
    case 0x02:
        assert(hn==3&&h[1]==0&&h[2]==0&&on==2048&&!n&&out&&(c.status&2));
        memcpy(c.cache,out,2048);c.cache_loaded=true;return 0;
    case 0x10:{
        assert(!on&&!n&&c.cache_loaded&&(c.status&2)&&!c.protect&&(c.config&0x18)==0x18);
        if(c.execute_not_received)return -1;
        uint32_t p=address(h,hn),b=p/64;assert(p%64>=2&&(int)(p%64)>c.highest[b]);
        c.highest[b]=(int16_t)(p%64);++c.programs;
        uint8_t *v=page(p);size_t bytes=c.program_fail&&!c.program_fail_after_full?11:2048;
        for(size_t i=0;i<bytes;++i){assert((v[i]&c.cache[i])==c.cache[i]);v[i]&=c.cache[i];}
        if(c.program_bad_readback)v[2047]^=1;
        c.status=(uint8_t)(c.program_fail?8:0);c.busy_reads=2;c.cache_loaded=false;
        if(c.program_busy_forever)c.busy_forever=true;
        return c.execute_lost?-1:0;
    }
    case 0xd8:{
        assert(!on&&!n&&(c.status&2)&&!c.protect);
        if(c.erase_ignored)return 0;
        uint32_t p=address(h,hn);assert(p%64==0);++c.erases;
        for(unsigned i=0;i<(c.erase_fail?7u:64u);++i){free(c.pages[p+i]);c.pages[p+i]=NULL;c.ecc[p+i]=0;}
        if(!c.erase_fail)c.highest[p/64]=-1;
        if(c.bad_erase_readback)page(p+10)[9]=0;
        if(c.erase_corrected)c.ecc[p+10]=1;
        c.status=(uint8_t)(c.erase_fail?4:0);c.busy_reads=2;
        if(c.erase_busy_forever)c.busy_forever=true;
        return c.erase_lost?-1:0;
    }
    default: /* In particular, no OTP, lock, BBM mutation or random program. */
        assert(!"Unexpected/destructive W25N01GV opcode");return -1;
    }
}
static uint64_t now(void *u){(void)u;return c.stalled_clock?0:c.us/1000;}
static void delay(void *u,uint32_t us){(void)u;c.us+=us;}
static struct aura_nand_io initialize(void)
{
    struct aura_w25n01gv_bus bus={NULL,command,now,delay};
    assert(aura_w25n01gv_init(&d,&bus)==0);
    return aura_w25n01gv_io(&d);
}
static int initialize_failure(void)
{
    struct aura_w25n01gv_bus bus={NULL,command,now,delay};
    int r=aura_w25n01gv_init(&d,&bus);
    assert(r<0&&!d.ready&&aura_w25n01gv_io(&d).blocks==0);
    assert(!c.programs&&!c.erases);return r;
}
static void lut(unsigned i,uint16_t l,uint16_t p)
{c.lut[i*4]=(uint8_t)(l>>8);c.lut[i*4+1]=(uint8_t)l;c.lut[i*4+2]=(uint8_t)(p>>8);c.lut[i*4+3]=(uint8_t)p;}

static void begin_capture(struct aura_nand_io io)
{
    assert(!aura_journal_mount(&journal,io));
    assert(!aura_journal_prepare(&journal));
    assert(!aura_journal_service(&journal,0));
    struct aura_archive_manifest m={.frame_samples=320,.pre_skip=40};
    memset(m.device_id,17,16);memset(m.capture_id,42,16);
    assert(!aura_archive_begin_staged(&writer,&m,aura_journal_stage,&journal));
}
static int container_packet(void)
{
    /* Protocol-profile fixture, not speech/decode evidence. The journal's
     * separate real-Opus roundtrip supplies that independent verification. */
    struct aura_opus_packet p={.sequence=writer.audio_packets,.sample_offset=writer.encoded_samples,
        .sample_count=320,.bytes=80};
    memset(p.data,0x33,80);p.data[0]=0x98;
    return aura_archive_opus_commit(&writer,&p);
}

static unsigned control_pair_tests(void)
{
    unsigned groups=0;uint8_t data[2048],got[2048];memset(data,0xa6,sizeof(data));
    fresh();memset(&d,0,sizeof(d));
    assert(aura_w25n01gv_configure_control(&d,0,1)==AURA_NAND_BAD_ARGUMENT);
    assert(!aura_w25n01gv_control_io(&d).nand.blocks);
    struct aura_nand_io ordinary=initialize();
    struct aura_control_io control=aura_w25n01gv_control_io(&d);
    uint64_t transfers=d.transfers;
    assert(!control.nand.blocks&&!control.nand.erase);
    assert(control.erase_control(control.erase_user,0)==AURA_NAND_BAD_BLOCK);
    assert(control.nand.read(control.nand.user,2,0,got,1)==AURA_NAND_BAD_BLOCK);
    assert(control.nand.program(control.nand.user,2,data)==AURA_NAND_BAD_BLOCK);
    assert(aura_w25n01gv_configure_control(&d,0,0)==AURA_NAND_BAD_ARGUMENT);
    assert(aura_w25n01gv_configure_control(&d,0,1024)==AURA_NAND_BAD_ARGUMENT);
    assert(!aura_w25n01gv_configure_control(&d,0,1));
    assert(!aura_w25n01gv_configure_control(&d,0,1));
    assert(aura_w25n01gv_configure_control(&d,1,0)==AURA_CONTROL_CONFLICT);
    assert(aura_w25n01gv_configure_control(&d,2,3)==AURA_CONTROL_CONFLICT);
    control=aura_w25n01gv_control_io(&d);assert(control.nand.blocks==1024&&!control.nand.erase);
    for(unsigned b=0;b<2;++b){
        bool bad=false;assert(!ordinary.bad(ordinary.user,b,&bad)&&bad);
        assert(ordinary.read(ordinary.user,b*64+2,0,got,1)==AURA_NAND_BAD_BLOCK);
        assert(ordinary.program(ordinary.user,b*64+2,data)==AURA_NAND_BAD_BLOCK);
        assert(ordinary.erase(ordinary.user,b)==AURA_NAND_BAD_BLOCK);
        assert(!control.nand.bad(control.nand.user,b,&bad)&&!bad);
    }
    bool bad=false;assert(!control.nand.bad(control.nand.user,2,&bad)&&bad);
    assert(control.nand.read(control.nand.user,130,0,got,1)==AURA_NAND_BAD_BLOCK);
    assert(control.nand.program(control.nand.user,130,data)==AURA_NAND_BAD_BLOCK);
    assert(control.erase_control(control.erase_user,2)==AURA_NAND_BAD_BLOCK);
    assert(control.erase_control(control.erase_user,1024)==AURA_NAND_BAD_ARGUMENT);
    assert(d.transfers==transfers&&!c.programs&&!c.erases);
    assert(!aura_journal_mount(&journal,ordinary));
    assert(journal.block_state[0]==AURA_BLOCK_EXCLUDED&&journal.block_state[1]==AURA_BLOCK_EXCLUDED);
    assert(!aura_journal_prepare(&journal)&&journal.prepared==2);
    assert(!ordinary.program(ordinary.user,130,data));
    uint32_t erases=c.erases;
    assert(ordinary.erase(ordinary.user,2)==AURA_NAND_NOT_ERASED);
    assert(control.erase_control(control.erase_user,2)==AURA_NAND_BAD_BLOCK&&c.erases==erases);
    ++groups;

    /* A live ordinary view cannot subsequently have its inventory reclassified. */
    fresh();ordinary=initialize();assert(!ordinary.bad(ordinary.user,0,&bad));
    assert(aura_w25n01gv_configure_control(&d,0,1)==AURA_CONTROL_CONFLICT);
    fresh();ordinary=initialize();assert(!ordinary.read(ordinary.user,2,0,got,1));
    assert(aura_w25n01gv_configure_control(&d,0,1)==AURA_CONTROL_CONFLICT);
    fresh();c.markers[5][1][2]=0;lut(0,0x8003,1000);ordinary=initialize();
    assert(aura_w25n01gv_configure_control(&d,5,6)==AURA_NAND_BAD_BLOCK);
    assert(aura_w25n01gv_configure_control(&d,3,6)==AURA_NAND_BAD_BLOCK);
    assert(aura_w25n01gv_configure_control(&d,6,1000)==AURA_NAND_BAD_BLOCK);
    assert(!d.control_configured&&!aura_w25n01gv_configure_control(&d,6,7));
    fresh();c.wrong_id=true;initialize_failure();
    assert(aura_w25n01gv_configure_control(&d,0,1)==AURA_NAND_BAD_ARGUMENT);++groups;

    /* Real journal and control ledger share the production command core. Only
     * the reserved pair cycles; ordinary capture bytes/receipt survive it. */
    fresh();ordinary=initialize();assert(!aura_w25n01gv_configure_control(&d,0,1));
    control=aura_w25n01gv_control_io(&d);begin_capture(ordinary);
    assert(journal.current_block==2&&!container_packet()&&!aura_archive_interrupt(&writer));
    uint8_t receipt[94],recovered[94];assert(!aura_journal_receipt(&journal,0,receipt));
    uint8_t markers[sizeof(c.markers)],lut_saved[sizeof(c.lut)];
    memcpy(markers,c.markers,sizeof(markers));memcpy(lut_saved,c.lut,sizeof(lut_saved));
    struct aura_control ledger;
    struct aura_control_config config={.blocks={0,1},.domain={1}};
    uint8_t snapshot[2500],loaded[2500];memset(snapshot,0x41,sizeof(snapshot));size_t bytes=0;
    erases=c.erases;uint32_t programs=c.programs;
    assert(aura_control_open(&ledger,control,&config)==AURA_CONTROL_UNPROVISIONED);
    assert(c.erases==erases&&c.programs==programs);
    assert(!aura_control_provision(&ledger,control,&config,snapshot,sizeof(snapshot)));
    assert(ledger.generation==1);snapshot[0]=0x42;c.execute_lost=true;
    assert(!aura_control_store(&ledger,snapshot,sizeof(snapshot)));c.execute_lost=false;
    assert(ledger.generation==2);snapshot[0]=0x43;
    assert(!aura_control_store(&ledger,snapshot,sizeof(snapshot))&&ledger.generation==3);
    assert(!memcmp(markers,c.markers,sizeof(markers))&&!memcmp(lut_saved,c.lut,sizeof(lut_saved)));
    assert(!aura_control_load(&ledger,loaded,sizeof(loaded),&bytes)&&bytes==sizeof(snapshot));
    assert(!memcmp(snapshot,loaded,bytes));
    ordinary=initialize();assert(!aura_w25n01gv_control_io(&d).nand.blocks);
    assert(control.erase_control(control.erase_user,0)==AURA_NAND_BAD_BLOCK);
    assert(!aura_w25n01gv_configure_control(&d,0,1));control=aura_w25n01gv_control_io(&d);
    assert(!aura_control_open(&ledger,control,&config)&&ledger.generation==3);
    assert(!aura_control_load(&ledger,loaded,sizeof(loaded),&bytes)&&!memcmp(snapshot,loaded,bytes));
    assert(!aura_journal_mount(&journal,ordinary)&&journal.count==1);
    assert(!aura_journal_verify(&journal,0)&&!aura_journal_receipt(&journal,0,recovered));
    assert(!memcmp(receipt,recovered,94));snapshot[0]=0x44;
    assert(!aura_control_store(&ledger,snapshot,sizeof(snapshot))&&ledger.generation==4);
    assert(!memcmp(markers,c.markers,sizeof(markers))&&!memcmp(lut_saved,c.lut,sizeof(lut_saved)));++groups;

    /* Every erase failure denies fresh program permission, including a lost
     * reply with all-FF readback, ignored execute and corrected FF readback. */
    for(unsigned mode=0;mode<8;++mode){
        fresh();ordinary=initialize();assert(!aura_w25n01gv_configure_control(&d,0,1));
        control=aura_w25n01gv_control_io(&d);
        assert(!control.erase_control(control.erase_user,0));
        assert(!control.nand.program(control.nand.user,2,data));
        switch(mode){
        case 0:c.erase_lost=true;break;
        case 1:c.erase_fail=true;break;
        case 2:c.bad_erase_readback=true;break;
        case 3:c.erase_ignored=true;break;
        case 4:c.erase_corrected=true;break;
        case 5:c.refuse_wel=true;break;
        case 6:c.fail_read_page=10;break;
        default:c.erase_busy_forever=true;break;
        }
        assert(control.erase_control(control.erase_user,0)<0);
        assert(control.nand.program(control.nand.user,3,data)==AURA_NAND_PROGRAM_ORDER);
        if(mode!=5)assert(control.erase_control(control.erase_user,0)==AURA_NAND_BAD_BLOCK);
        else{c.refuse_wel=false;assert(!control.erase_control(control.erase_user,0));
            assert(!control.nand.program(control.nand.user,2,data));}
    }
    ++groups;

    fresh();ordinary=initialize();assert(!aura_w25n01gv_configure_control(&d,0,1));
    control=aura_w25n01gv_control_io(&d);c.program_fail=c.program_fail_after_full=true;
    assert(aura_control_provision(&ledger,control,&config,snapshot,sizeof(snapshot))==AURA_NAND_PROGRAM_FAILED);
    assert(control.nand.read(control.nand.user,2,0,got,2048)==AURA_NAND_PROGRAM_FAILED);
    assert(aura_control_open(&ledger,control,&config)==AURA_CONTROL_INCOMPLETE);
    assert(!ledger.ready);++groups;
    printf("CONTROL pair: %u groups PASS; isolated callbacks, real ledger cycles/cold recovery, 8 erase faults\n",groups);
    return groups;
}

int main(void)
{
    unsigned groups=0;uint8_t data[2048],got[2048];memset(data,0xa6,sizeof(data));
    fresh();struct aura_nand_io io=initialize();
    assert(io.blocks==1024&&c.marker_bytes==6144&&c.config==0x18&&!c.protect);
    assert(!d.excluded_blocks&&!c.programs&&!c.erases);
    assert(c.command_count[0x13]==2048&&c.command_count[0xa5]==1);++groups;
    printf("Empty-chip startup: %llu commands, %llu received bytes, 2048 marker-page loads, 0 payload scans\n",
        (unsigned long long)d.transfers,(unsigned long long)d.received_bytes);

    /* Any of six retained manufacturer locations excludes a block. */
    fresh();for(unsigned p=0;p<2;++p)for(unsigned n=0;n<3;++n)c.markers[10+p*3+n][p][n]=0;
    io=initialize();assert(d.excluded_blocks==6);
    for(unsigned b=10;b<16;++b){bool excluded=false;assert(!io.bad(io.user,b,&excluded)&&excluded);
        assert(io.erase(io.user,b)==AURA_NAND_BAD_BLOCK&&io.program(io.user,b*64+2,data)==AURA_NAND_BAD_BLOCK);}
    assert(!c.programs&&!c.erases);++groups;

    fresh();lut(0,0x8003,1000);lut(1,0xc004,1001);io=initialize();assert(d.excluded_blocks==4);
    for(unsigned n=0;n<4;++n){uint32_t b=(uint32_t[]){3,1000,4,1001}[n];bool x=false;assert(!io.bad(io.user,b,&x)&&x);}
    fresh();lut(0,0x4003,1000);initialize_failure();
    fresh();lut(0,0x8400,1000);initialize_failure();
    fresh();lut(0,0x8003,1024);initialize_failure();
    fresh();lut(0,3,4);initialize_failure();++groups;

    fresh();c.wrong_id=true;initialize_failure();
    fresh();c.ignore_config=true;initialize_failure();
    fresh();c.persistent_config=0x80;initialize_failure();
    fresh();c.persistent_protect=0x80;initialize_failure();
    fresh();c.fail_read_page=128;initialize_failure();++groups;

    fresh();io=initialize();assert(io.program(io.user,2,data)==AURA_NAND_PROGRAM_ORDER);
    assert(!io.erase(io.user,0)&&c.erases==1);
    assert(io.program(io.user,0,data)==AURA_NAND_PROGRAM_ORDER);
    assert(io.program(io.user,1,data)==AURA_NAND_PROGRAM_ORDER);
    assert(!io.program(io.user,2,data)&&c.programs==1);
    assert(!io.read(io.user,2,0,got,sizeof(got))&&!memcmp(got,data,sizeof(data)));
    assert(io.program(io.user,2,data)==AURA_NAND_PROGRAM_ORDER);
    assert(!io.program(io.user,3,data));assert(io.erase(io.user,0)==AURA_NAND_NOT_ERASED&&c.erases==1);
    /* Reinitialization cannot resume old block's program order. */
    io=initialize();assert(io.program(io.user,4,data)==AURA_NAND_PROGRAM_ORDER);
    assert(!io.read(io.user,2,0,got,sizeof(got))&&!memcmp(got,data,sizeof(data)));++groups;

    fresh();io=initialize();assert(!io.erase(io.user,1023));assert(!io.program(io.user,65535,data));
    assert(!io.read(io.user,65535,2047,got,1)&&got[0]==0xa6);
    assert(io.read(io.user,65536,0,got,1)==AURA_NAND_BAD_ARGUMENT);
    assert(io.read(io.user,0,2047,got,2)==AURA_NAND_BAD_ARGUMENT);
    assert(io.read(io.user,0,2048,got,1)==AURA_NAND_BAD_ARGUMENT);
    assert(io.erase(io.user,1024)==AURA_NAND_BAD_ARGUMENT);++groups;

    fresh();io=initialize();c.ecc[10]=1;assert(io.read(io.user,10,0,got,10)==AURA_NAND_CORRECTED);
    assert(d.corrected_reads==1);assert(io.erase(io.user,0)==AURA_NAND_NOT_ERASED&&!c.erases);
    c.ecc[10]=2;assert(io.read(io.user,10,0,got,10)==AURA_NAND_UNCORRECTABLE);
    c.ecc[10]=3;assert(io.read(io.user,10,0,got,10)==AURA_NAND_UNCORRECTABLE);
    assert(d.failed_reads==2);++groups;

    fresh();io=initialize();assert(!io.erase(io.user,0));c.execute_lost=true;
    assert(io.program(io.user,2,data)==0&&c.programs==1);
    assert(d.resolved_execute_errors==1);
    assert(!io.read(io.user,2,0,got,2048)&&!memcmp(got,data,2048));
    c.execute_lost=false;assert(io.program(io.user,3,data)==0);
    assert(io.erase(io.user,0)==AURA_NAND_NOT_ERASED);++groups;

    fresh();io=initialize();assert(!io.erase(io.user,0));assert(!io.program(io.user,2,data));c.program_fail=true;
    assert(io.program(io.user,3,data)==AURA_NAND_PROGRAM_FAILED&&c.programs==2);
    assert(io.program(io.user,4,data)==AURA_NAND_PROGRAM_ORDER);
    assert(io.read(io.user,3,0,got,2048)==AURA_NAND_PROGRAM_FAILED);
    assert(c.pages[3][0]==0xa6&&c.pages[3][100]==255);
    assert(!io.read(io.user,2,0,got,2048)&&!memcmp(got,data,2048));++groups;

    fresh();io=initialize();assert(!io.erase(io.user,0));c.program_fail=c.program_fail_after_full=c.execute_lost=true;
    assert(io.program(io.user,2,data)==AURA_NAND_PROGRAM_FAILED);
    assert(!memcmp(c.pages[2],data,2048));
    assert(io.read(io.user,2,0,got,2048)==AURA_NAND_PROGRAM_FAILED);++groups;

    fresh();io=initialize();assert(!io.erase(io.user,0));c.program_busy_forever=true;
    assert(io.program(io.user,2,data)==AURA_NAND_UNCERTAIN);
    c.busy_forever=c.program_busy_forever=false;
    assert(io.read(io.user,2,0,got,2048)==AURA_NAND_UNCERTAIN);
    assert(io.program(io.user,3,data)==AURA_NAND_PROGRAM_ORDER);
    assert(io.erase(io.user,0)==AURA_NAND_BAD_BLOCK);
    /* Only a separately initiated cold-recovery session can inspect the page. */
    io=initialize();assert(!io.read(io.user,2,0,got,2048)&&!memcmp(got,data,2048));++groups;

    fresh();io=initialize();assert(!io.erase(io.user,0));memset(got,255,sizeof(got));
    assert(io.program(io.user,2,got)==AURA_NAND_BAD_ARGUMENT&&!c.programs);
    c.execute_not_received=true;
    assert(io.program(io.user,2,data)==AURA_NAND_UNCERTAIN&&!c.programs);
    assert(io.read(io.user,2,0,got,2048)==AURA_NAND_UNCERTAIN);++groups;

    fresh();io=initialize();assert(!io.erase(io.user,0));c.program_bad_readback=true;
    assert(io.program(io.user,2,data)==AURA_NAND_PROGRAM_FAILED);
    assert(io.program(io.user,3,data)==AURA_NAND_PROGRAM_ORDER);++groups;

    fresh();io=initialize();c.erase_lost=true;assert(io.erase(io.user,0)==AURA_NAND_UNCERTAIN);
    assert(io.program(io.user,2,data)==AURA_NAND_PROGRAM_ORDER);
    fresh();io=initialize();c.erase_fail=true;assert(io.erase(io.user,0)==AURA_NAND_ERASE_FAILED);
    assert(io.program(io.user,2,data)==AURA_NAND_PROGRAM_ORDER);
    fresh();io=initialize();c.bad_erase_readback=true;assert(io.erase(io.user,0)==AURA_NAND_ERASE_FAILED);
    assert(io.erase(io.user,0)==AURA_NAND_BAD_BLOCK&&c.erases==1);++groups;

    fresh();io=initialize();c.erase_ignored=true;
    assert(io.erase(io.user,0)==AURA_NAND_UNCERTAIN&&!c.erases);
    assert(io.program(io.user,2,data)==AURA_NAND_PROGRAM_ORDER);++groups;

    fresh();io=initialize();page(63)[2047]=0;assert(io.erase(io.user,0)==AURA_NAND_NOT_ERASED&&!c.erases);
    fresh();io=initialize();assert(!io.erase(io.user,0));c.refuse_wel=true;
    assert(io.program(io.user,2,data)==AURA_NAND_IO_ERROR&&!c.programs);
    assert(io.program(io.user,3,data)==AURA_NAND_PROGRAM_ORDER);++groups;

    fresh();io=initialize();uint64_t start=c.us;uint32_t reads=c.command_count[0x0f];c.busy_forever=true;
    assert(io.read(io.user,2,0,got,1)==AURA_NAND_IO_ERROR);
    assert(c.us-start<=30100&&c.command_count[0x0f]-reads<=301);++groups;

    fresh();io=initialize();reads=c.command_count[0x0f];c.busy_forever=c.stalled_clock=true;
    assert(io.read(io.user,2,0,got,1)==AURA_NAND_IO_ERROR);
    assert(c.command_count[0x0f]-reads==301);++groups;

    /* Production command core + production journal, not two parallel mocks:
     * staged receipt refusal, lost reply resolved once, terminal and cold read. */
    fresh();io=initialize();begin_capture(io);uint8_t ack[94],saved[94];
    assert(aura_archive_receipt(&writer,ack)==AURA_ARCHIVE_BUSY);
    assert(aura_journal_receipt(&journal,0,ack)==AURA_JOURNAL_NOT_COMMITTED);
    c.execute_lost=true;assert(!container_packet());c.execute_lost=false;
    assert(c.programs==2&&journal.committed.audio_packets==1);
    assert(!aura_archive_interrupt(&writer));
    assert(!aura_journal_receipt(&journal,0,saved));
    io=initialize();assert(!aura_journal_mount(&journal,io));
    assert(aura_journal_receipt(&journal,0,ack)==AURA_JOURNAL_NOT_COMMITTED);
    assert(!aura_journal_verify(&journal,0));
    assert(!aura_journal_receipt(&journal,0,ack)&&!memcmp(saved,ack,94));++groups;

    /* Matching physical bytes plus P-FAIL must never advance the journal. */
    fresh();io=initialize();begin_capture(io);assert(!container_packet());assert(!container_packet());
    assert(journal.committed.audio_packets==1);
    c.program_fail=c.program_fail_after_full=c.execute_lost=true;
    assert(aura_journal_flush(&journal)==AURA_NAND_PROGRAM_FAILED);
    assert(journal.committed.audio_packets==1);
    assert(aura_journal_receipt(&journal,0,ack)==AURA_NAND_PROGRAM_FAILED);
    assert(!io.read(io.user,3,0,got,2048));
    assert(io.read(io.user,4,0,got,2048)==AURA_NAND_PROGRAM_FAILED);++groups;

    groups+=control_pair_tests();
    fresh();printf("W25N01GV production command core: %u groups PASS; no physical SPI test\n",groups);
    printf("Portable driver context: %zu bytes\n",sizeof(struct aura_w25n01gv));return 0;
}
