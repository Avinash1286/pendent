import fs from 'node:fs';
import path from 'node:path';
import { parseKicadModToKicadJson } from 'kicad-component-converter';

// Land patterns are copied intact for review, then projected into tscircuit.
// The source KiCad 10 libraries are CC-BY-SA-4.0 with the KiCad library exception.
const root = process.env.KICAD_FOOTPRINT_DIR || 'C:/Program Files/KiCad/10.0/share/kicad/footprints';
const specs = {
  radio:['RF_Module','Raytac_MDBT50Q',10.5,15.5,2.05],
  mic:['Sensor_Audio','Knowles_LGA-5_3.5x2.65mm',2.65,3.5,1.0],
  charger:['Package_DFN_QFN','Texas_DLH0010A_WSON-10-1EP_2.2x2mm_P0.4mm_EP0.9x1.5mm',2.2,2,0.8],
  ldo:['Package_TO_SOT_SMD','SOT-23-5',2.9,2.8,1.2],
  gauge:['Package_DFN_QFN','TDFN-8-1EP_2x2mm_P0.5mm_EP0.8x1.2mm',2,2,0.8],
  haptic:['Package_SO','MSOP-10_3x3mm_P0.5mm',4.9,3,1.1],
  flash:['Package_SON','WSON-8-1EP_6x5mm_P1.27mm_EP3.4x4mm',6,5,0.8],
  buffer:['Package_SO','VSSOP-8_2.3x2mm_P0.5mm',3.1,2,0.9],
  privacy:['Button_Switch_SMD','SW_DPDT_CK_JS202011JCQN',6.7,4.1,1.5],
  record:['Button_Switch_SMD','SW_Push_1P1T_NO_CK_KMR2',4.6,3.8,1.9],
  r0402:['Resistor_SMD','R_0402_1005Metric',1,0.5,0.35],
  c0402:['Capacitor_SMD','C_0402_1005Metric',1,0.5,0.5],
  c0603:['Capacitor_SMD','C_0603_1608Metric',1.6,0.8,0.8],
  led:['LED_SMD','LED_0603_1608Metric',1.6,0.8,0.8],
  diode:['Diode_SMD','D_SOD-323',2.5,1.25,1.0],
};
const out={};
for(const [key,[lib,name,w,h,z]] of Object.entries(specs)){
  const raw=fs.readFileSync(path.join(root,`${lib}.pretty`,`${name}.kicad_mod`),'utf8');
  fs.writeFileSync(`library/${name}.kicad_mod`,raw);
  const k=parseKicadModToKicadJson(raw);
  out[key]={key,library:`${lib}:${name}`,width:w,height:h,z,pads:k.pads,holes:k.holes||[],lines:k.fp_lines.filter(x=>x.layer==='F.SilkS'),source: k.descr};
}
fs.writeFileSync('src/footprints.json',JSON.stringify(out,null,2));
console.log(`Copied ${Object.keys(out).length} original KiCad land patterns.`);
