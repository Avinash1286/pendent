/** AURA EVT-A: connected engineering design, not a production release. Units mm. */
export interface Part {ref:string; mpn:string; value:string; fp:string; x:number; y:number; r?:number; layer?:'top'|'bottom'; pins:Record<string,string>; labels?:Record<string,string>; nc?:string[]; block:string; note?:string}
import placement from './placement-overrides.json';
const p=(ref:string,mpn:string,value:string,fp:string,x:number,y:number,pins:Record<string,string>,block:string,extra:Partial<Part>={}):Part=>({ref,mpn,value,fp,x,y,pins,block,...extra});
const radioPins:Record<string,string>={1:'GND',2:'GND',15:'GND',28:'V3',30:'V3',32:'GND',33:'GND',55:'GND',16:'I2C_SCL',19:'I2C_SDA',20:'PDM_CLK_MCU',21:'PDM_DATA_MCU',22:'RECORD_EN',24:'RECORD_N',25:'PRIVACY_N',36:'SPI_MOSI',37:'SPI_MISO',38:'SPI_SCK_MCU',39:'SPI_CS_N',40:'RESET_N',41:'HAPTIC_EN',42:'GAUGE_ALERT_N',43:'CHG_STAT1',44:'CHG_STAT2',45:'CHG_DISABLE',46:'BOOKMARK_N',51:'SWDIO',53:'SWDCLK'};
export const parts:Part[]=[
 p('U1','MDBT50Q-1MV2','nRF52840 BLE module','radio',0,8,radioPins,'radio',{nc:Array.from({length:61},(_,i)=>String(i+1)).filter(n=>!radioPins[n]),labels:{32:'VBUS'},note:'Normal-voltage mode: VDD and VDDH tied3.0V; DCCH open; unused VBUS grounded; internal LFRC initial firmware. Antenna keepout Y>11.95 per Raytac Version L.'}),
 p('MK1','SPH0641LU4H-1','Left PDM microphone','mic',-8.5,9.27,{1:'PDM_DATA_MIC',2:'GND',3:'GND',4:'PDM_CLK_MIC',5:'MIC_VDD'},'audio'),
 p('MK2','SPH0641LU4H-1','Right PDM microphone','mic',8.5,9.27,{1:'PDM_DATA_MIC',2:'MIC_VDD',3:'GND',4:'PDM_CLK_MIC',5:'MIC_VDD'},'audio'),
 p('U2','W25N01GVZEIG','1Gbit SPI NAND /128MiB','flash',-5.5,-4,{1:'SPI_CS_N',2:'SPI_MISO',3:'FLASH_WP_N',4:'GND',5:'SPI_MOSI',6:'SPI_SCK',7:'FLASH_HOLD_N',8:'V3'},'storage',{nc:['9'],note:'Exposed pad electrically NC; use internal ECC and bad-block management. SPI single mode chosen.'}),
 p('U3','BQ25185DLHR','75mA Li-ion powerpath charger','charger',-6,-10,{1:'VSYS',2:'VBAT',3:'CHG_STAT2',4:'CHG_DISABLE',5:'GND',6:'BAT_NTC',7:'CHG_VSET',8:'CHG_ISET',9:'CHG_STAT1',10:'DOCK_IN',11:'GND'},'power'),
 p('U4','TLV75530PDBVR','3.0V system regulator','ldo',-1,-11,{1:'VSYS',2:'GND',3:'VSYS',5:'V3'},'power',{nc:['4']}),
 p('U5','MAX17048G+T10','ModelGauge fuel gauge','gauge',-9,1.6,{1:'GND',2:'VBAT',3:'VBAT',4:'GND',5:'GAUGE_ALERT_N',6:'GND',7:'I2C_SCL',8:'I2C_SDA',9:'GND'},'power'),
 p('U6','DRV2605LDGSR','LRA closed-loop haptics','haptic',6,-10,{1:'HAPTIC_REG',2:'I2C_SCL',3:'I2C_SDA',4:'GND',5:'HAPTIC_EN',6:'VSYS',7:'LRA_P',8:'GND',9:'LRA_N',10:'VSYS'},'ux'),
 p('U7','TLV75530PDBVR','Recording-only3V microphone regulator','ldo',5,-4.8,{1:'VSYS',2:'GND',3:'RECORD_EN',5:'MIC_SUPPLY'},'privacy',{nc:['4']}),
 p('U8','SN74LVC2G125DCUR','Ioff protected PDM isolation','buffer',8,4,{1:'GND',2:'PDM_CLK_MCU',3:'PDM_DATA_MCU',4:'GND',5:'PDM_DATA_MIC',6:'PDM_CLK_BUF',7:'GND',8:'MIC_VDD'},'privacy'),
 p('SW1','JS202011JCQN','Mechanical DPDT microphone OFF','privacy',9.5,-0.2,{1:'MIC_SUPPLY',2:'MIC_VDD',3:'GND',4:'GND',5:'PRIVACY_N',6:'V3'},'privacy',{r:90,note:'Center commons2,5. OFF connects2-3 and5-6. Break-before-make; verify actuator orientation on first article.'}),
 p('SW2','KMR221GLFS','Record / stop','record',0,-6,{1:'RECORD_N',2:'GND'},'ux'),
 p('SW3','KMR221GLFS','Optional internal bookmark/debug button (DNP in enclosed unit)','record',-9,-7.7,{1:'BOOKMARK_N',2:'GND'},'ux',{r:90,note:'Internal debug only; case has no actuator aperture. Front-button doublepress is the planned bookmark UX.'}),
 p('D1','BAT54WS-7-F','Reverse-dock Schottky','diode',-5,-14,{1:'DOCK_IN',2:'DOCK_5V'},'power'),
 p('D2','PESD5V0S1BA,115','Dock transient suppression','diode',5,-14,{1:'DOCK_5V',2:'GND'},'power'),
 p('LED1','LTST-C190KFKT','Amber hard recording indicator','led',0,-1,{1:'GND',2:'LED_RECORD_A'},'privacy',{note:'Indicator receives microphone rail power, has no independent firmware-off command.'}),
 p('J1','AURA-DOCK-PADS','3 ENIG rear pogo contacts','dock',0,-15,{1:'GND',2:'DOCK_5V',3:'GND'},'power',{layer:'bottom',note:'Mating dock mechanically keyed, current-limited5V100mA, magnets in case only.'}),
 p('J2','AURA-BATTERY-PADS','Protected LiPo and pack10kNTC','battery',-6,-12,{1:'VBAT',2:'GND',3:'BAT_NTC'},'power',{layer:'bottom',note:'250mAh target20×25×5mm maximum protected pack with10k3435K NTC,4.2V chemistry. Supplier cell not yet qualified.'}),
 p('J3','AURA-SWD-PADS','6 pogo programming pads','debug',1,0,{1:'V3',2:'SWDIO',3:'SWDCLK',4:'RESET_N',5:'GND',6:'GND'},'radio',{layer:'bottom'}),
 p('J4','AURA-LRA-PADS','8mm LRA wire pads','motor',8,-13,{1:'LRA_P',2:'LRA_N'},'ux',{layer:'bottom',note:'External LRA target1.8Vrms; motor part, resonance and driver calibration pending selection.'}),
];
const addR=(ref:string,value:string,x:number,y:number,a:string,b:string,block='power',r=0)=>parts.push(p(ref,'TBD-0402-1PCT',value,'r0402',x,y,{1:a,2:b},block,{r,note:'0402 1% 63mW minimum. Exact purchasing MPN unassigned; not orderable BOM.'}));
const addC=(ref:string,value:string,x:number,y:number,rail:string,block='power',fp='c0402')=>parts.push(p(ref,'GENERIC-X7R-10V',value,fp,x,y,{1:rail,2:'GND'},block,{note:'X7R10V minimum; verify effective capacitance under bias and manufacturer MPN.'}));
addR('R1','4.02k',-3.8,-9.3,'CHG_ISET','GND');
addR('R2','24k',-3.8,-10.4,'CHG_VSET','GND');
addR('R3','100k',-3.8,-11.5,'CHG_DISABLE','GND');
addR('R4','10k',-9,-10,'CHG_STAT1','V3');
addR('R5','10k',-9,-11.2,'CHG_STAT2','V3');
addR('R6','4.7k',-7,4.3,'I2C_SCL','V3','radio',90);
addR('R7','4.7k',-8.3,4.3,'I2C_SDA','V3','radio',90);
addR('R8','100k',-10.5,4.3,'GAUGE_ALERT_N','V3','power',90);
addR('R9','100k',2.5,-9,'RECORD_EN','GND','privacy');
addR('R10','100k',4,-7.6,'HAPTIC_EN','GND','ux');
addR('R11','10k',-1,-3.3,'RECORD_N','V3','ux');
addR('R12','10k',-6,-7.6,'BOOKMARK_N','V3','ux');
addR('R13','10k',7.2,-3,'PRIVACY_N','V3','privacy');
addR('R14','1k',-1.9,-1,'MIC_VDD','LED_RECORD_A','privacy');
addR('R15','100k',2.8,-3,'MIC_VDD','GND','privacy',90);
addR('R16','33',7,6,'PDM_CLK_BUF','PDM_CLK_MIC','audio');
addR('R17','33',-5.5,-0.3,'SPI_SCK_MCU','SPI_SCK','storage');
addR('R18','10k',-3,-0.3,'SPI_CS_N','V3','storage');
addR('R19','10k',-8.5,-1.3,'FLASH_WP_N','V3','storage');
addR('R20','10k',-8.5,-2.5,'FLASH_HOLD_N','V3','storage');
addR('R21','10k',1.8,-1.5,'RESET_N','V3','radio',90);
addC('C1','100nF',-6.4,1.7,'V3','radio');
addC('C2','4.7uF',-6.4,2.9,'V3','radio','c0603');
addC('C3','100nF',-8.5,6,'MIC_VDD','audio');
addC('C4','100nF',10,6,'MIC_VDD','audio');
addC('C5','100nF',-3,-7.5,'V3','storage');
addC('C6','4.7uF',-4.7,-7.5,'V3','storage','c0603');
addC('C7','2.2uF',-7,-12.6,'DOCK_IN','power','c0603');
addC('C8','4.7uF',-5,-12.6,'VBAT','power','c0603');
addC('C9','10uF',-1.8,-13.5,'VSYS','power','c0603');
addC('C10','2.2uF',1,-12.7,'V3','power','c0603');
addC('C11','100nF',-10.3,0,'VBAT','power');
addC('C12','1uF',4,-12,'VSYS','ux','c0603');
addC('C13','1uF',4.3,-8.8,'HAPTIC_REG','ux','c0603');
addC('C14','1uF',5.2,-6.6,'VSYS','privacy','c0603');
addC('C15','1uF',3,-4.8,'MIC_SUPPLY','privacy','c0603');
addC('C16','100nF',10.3,3.5,'MIC_VDD','privacy');
addC('C17','10nF',-1,-4.5,'RECORD_N','ux');
addC('C18','10nF',-6,-6.4,'BOOKMARK_N','ux');

// Numeric pad identity is authoritative. Labels improve the editable schematic.
const labels:Record<string,Record<string,string>>={
 U1:{28:'VDD',30:'VDDH',16:'P027_SCL',19:'P026_SDA',20:'P004_PDM_CLK',21:'P005_PDM_DATA',22:'P006_REC_EN',24:'P008_RECORD',25:'P108_PRIVACY',36:'P014_MOSI',37:'P013_MISO',38:'P016_SCK',39:'P015_CS',40:'P018_RESET',41:'P017_HAPTIC',42:'P019_GAUGE',43:'P021_STAT1',44:'P020_STAT2',45:'P023_CHG_DISABLE',46:'P022_BOOKMARK',51:'SWDIO',53:'SWDCLK'},
 U3:{1:'SYS',2:'BAT',3:'STAT2',4:'N_CE',5:'GND',6:'TS_MR',7:'ILIM_VSET',8:'ISET',9:'STAT1',10:'IN',11:'EP_GND'},
 U4:{1:'IN',2:'GND',3:'EN',4:'NC',5:'OUT'},U7:{1:'IN',2:'GND',3:'EN',4:'NC',5:'OUT'},
 U2:{1:'N_CS',2:'DO_IO1',3:'N_WP',4:'GND',5:'DI_IO0',6:'CLK',7:'N_HOLD',8:'VCC',9:'EP_NC'},
 U5:{1:'CTG',2:'CELL',3:'VDD',4:'GND',5:'N_ALRT',6:'QSTRT',7:'SCL',8:'SDA',9:'EP_GND'},
 U6:{1:'REG',2:'SCL',3:'SDA',4:'TRIG',5:'EN',6:'VDD2',7:'OUT_P',8:'GND',9:'OUT_N',10:'VDD'},
 U8:{1:'N_OE1',2:'A1_CLK',3:'Y2_DATA',4:'GND',5:'A2_DATA',6:'Y1_CLK',7:'N_OE2',8:'VCC'},
 MK1:{1:'DATA',2:'SELECT',3:'GND',4:'CLOCK',5:'VDD'},MK2:{1:'DATA',2:'SELECT',3:'GND',4:'CLOCK',5:'VDD'}
};
for(const part of parts)part.labels=labels[part.ref];
for(const part of parts)Object.assign(part,placement[part.ref]);
export const boardSpec={width:24,height:34,radius:4,thickness:0.8,layers:4,antennaKeepout:{minY:11.95},revision:'EVT-A',status:'Logical design and PCB routing draft. Do not fabricate before the validation gates in hardware.md.'};
