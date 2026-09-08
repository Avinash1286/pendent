"""Generate declarative review JSON only. Never reads/writes KiCad CAD files."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
old = json.loads((ROOT / 'hardware/output/design-manifest.json').read_text(encoding='utf-8'))
rename = {'V3': '+3V0', 'RECORD_EN': 'MIC_ENABLE', 'RECORD_N': 'CAPTURE_N', 'PRIVACY_N': 'PRIVACY_SENSE', 'SPI_CS_N': 'NAND_CS_N', 'FLASH_WP_N': 'NAND_WP_N', 'FLASH_HOLD_N': 'NAND_HOLD_N', 'CHG_STAT1': 'CHARGER_INT_N', 'CHG_STAT2': 'CHARGER_PG_N', 'CHG_DISABLE': 'CHARGER_CE_N', 'CHG_ALLOW': 'CHARGE_ALLOW', 'DOCK_IN': 'DOCK_5V_PROTECTED', 'TS_MON': 'BAT_TS', 'LRA_P': 'HAPTIC_P', 'LRA_N': 'HAPTIC_N'}
parts = []
for p in old['parts']:
    ref = {'U2':'U3', 'U3':'U2'}.get(p['ref'], p['ref'])
    parts.append({'ref':ref, 'mpn':p['mpn'], 'value':p['value'], 'block':p['block'], 'pins':{n:rename.get(net,net) for n,net in p['pins'].items()}, 'pinReviewSource':'../../hardware/scripts/native-symbol-specs.json (reviewed pin roles only; no CAD reused)'})
byref = {p['ref']:p for p in parts}
byref['U1']['pins'].update({'23':'RING_PWM','46':'NOR_CS_N'})
byref['U1']['pins']['38']='SPI_SCK_MCU'
byref['U1']['noConnect']=[str(n) for n in range(1,62) if str(n) not in byref['U1']['pins']]
byref['U2'].update(mpn='BQ25186DLHR',value='40mA I2C power-path charger; qualification pending',pins={'1':'VSYS','2':'VBAT','3':'CHARGER_PG_N','4':'CHARGER_CE_N','5':'GND','6':'BAT_TS','7':'I2C_SDA','8':'I2C_SCL','9':'CHARGER_INT_N','10':'DOCK_5V_PROTECTED','11':'GND'},pinReviewSource='pin-definitions.json')
for ref in ['U4','U7']:
    byref[ref]['noConnect']=['4']
byref['U9']['noConnect']=['1']
byref['U6']['pins'].update({'6':'+3V0','10':'+3V0'})
byref['U6'].update(value='ERM closed-loop haptics', nativeSymbol='Driver:DRV2605LDGS', footprint='Package_SO:TSSOP-10_3x3mm_P0.5mm')
byref['U6']['notes']='A04 ERM motor. Feed from regulated 3 V to bound motor voltage. EN default low; no haptic during capture. Calibrate actual motor, test 80 mA startup pulse and LDO transient. REG capacitor 1 uF. TSSOP footprint candidate checked against TI DGS0010A lead envelope; actual TI package is VSSOP.'
byref['C12'].update(value='4.7uF',mpn='C0603C475K8PACTU',pins={'1':'+3V0','2':'GND'})
byref['C7'].update(value='4.7uF 25V X5R',mpn='GRM188R61E475KE11D',footprint='Capacitor_SMD:C_0603_1608Metric',voltageRatingV=25,maxBodyMm=[1.75,0.95,0.95],notes='Root adopted 2026-09-09: higher input transient voltage rating. Require >=1uF effective at 5.5V after bias/temperature/tolerance/aging; nominal value alone does not prove this.')
byref['D2'].update(value='Bidirectional 5.5V ESD protection',mpn='TPD1E10B06DYAR',footprint='AuraA04:TI_DYA0002A_TPD1E10B06',pinReviewSource='https://www.ti.com/lit/ds/symlink/tpd1e10b06.pdf',notes='Root adopted and authored exact TI lands via MCP 2026-09-09 to cover USB 5.50V DC maximum. Pin1 DOCK_5V, pin2 GND unchanged. System ESD/overshoot qualification remains open.',maxBodyMm=[1.3,0.85,0.77],maxWidthIncludingMoldFlashMm=1.15,maxLeadSpanMm=1.7,reverseStandoffV=5.5,exactLandPattern={'sourceDrawing':'TI 4224978/C 11/2024','padCentersMm':[[-0.74,0],[0.74,0]],'padSizeMm':[0.67,0.40],'cornerRadiusMm':0.05,'pasteExampleStencilThicknessMm':0.10,'courtyardExtentsMm':[-1.325,-0.825,1.325,0.825]})
byref['R1'].update(value='10k',mpn='RC0402FR-0710KL',pins={'1':'NOR_CS_N','2':'+3V0'},block='storage')
byref['R2'].update(value='10k',mpn='RC0402FR-0710KL',pins={'1':'NOR_WP_N','2':'+3V0'},block='storage')
byref['R14'].update(value='2.2k',mpn='RC0402FR-072K2L')
byref['R22'].update(value='3.3k',mpn='RC0402FR-073K3L',notes='Conservative nominal hot cutoff approximately 34-35 C. Conditional full corners in electrical-architecture.md and electrical-validation.json. Do not equate a BQ programmed temperature label to actual cell temperature with this series resistor. Sensor attachment and R/T qualification remain open.')
byref['J4'].update(mpn='AURA-A04-MOTOR-PADS',value='Vybronics VCLP1020B002L ERM wire pads')
byref['J1'].update(mpn='AURA-A04-DOCK-CONTACTS',value='Keyed 5V100mA dock GND/5V/GND',notes='Symmetric outergrounds; PG detectsdock. Prefer nonmagnetic cradle until motor magnetic-field compatibility qualified. Contact material and wear process unresolved.')
byref['J2'].update(mpn='AURA-A04-BATTERY-PADS',value='Protected cell plus attached NTC; pack not qualified')
byref['J3'].update(mpn='AURA-A04-SWD-PADS',notes='VTref senses3V; never use as batterycharginginput. Keyed pogo SWD fixture; physical access in enclosure required.')
def add(ref,mpn,value,block,pins,**extra):
    assert ref not in byref
    p=dict(ref=ref,mpn=mpn,value=value,block=block,pins=pins,**extra)
    parts.append(p); byref[ref]=p
add('U10','MX25R3235FM1IL0','32Mbit/4MiB secure OTA staging','storage',{'1':'NOR_CS_N','2':'SPI_MISO','3':'NOR_WP_N','4':'GND','5':'SPI_MOSI','6':'SPI_SCK','7':'NOR_RESET_N','8':'+3V0'},nativeSymbol='Memory_Flash:MX25R3235FM1xx0',footprint='Package_SO:JEITA_SOIC-8_3.9x4.9mm_P1.27mm',notes='Pin7 RESET, notHOLD. SPI only. Default low-power mode; actual bootloader driver and reset/power-cycle qualification required.')
add('C19','C0402C104K4RACTU','100nF','storage',{'1':'+3V0','2':'GND'})
add('R24','RC0402FR-0710KL','10k','storage',{'1':'NOR_RESET_N','2':'+3V0'})
add('SW3','KMR211NGULCLFS','Recessed recovery reset','radio',{'1':'RESET_N','2':'GND'},notes='Hold face while pressing service reset requests signed recovery in bootloader. In charger shutdown, dock insertion wakes power; SW3alone does not.')
add('Q2','DMG2302UK-7','Ring LED low-side switch','ux',{'1':'RING_GATE','2':'GND','3':'RING_RETURN'})
add('R25','RC0402FR-07100RL','100','ux',{'1':'RING_PWM','2':'RING_GATE'})
add('R26','RC0402FR-07100KL','100k','ux',{'1':'RING_GATE','2':'GND'})
for suffix in [2,3]:
    add('LED'+str(suffix),'LTST-C190KFKT','Amber perimeter emitter','ux',{'1':'RING_RETURN','2':'RING_LED_A'+str(suffix)})
    add('R'+str(suffix+25),'RC0402FR-071KL','1k','ux',{'1':'+3V0','2':'RING_LED_A'+str(suffix)})
byref['LED1']['notes']='Dedicated central optical path, hardwired microphone-power indicator. Never hide behind firmware-controlledring or use an opaque face.'
byref['SW1']['notes']='DPDTcommons2,5: OFF2-3/5-6 groundsMIC_VDD and sensesHIGH. Enabled2-1/5-4 sensesLOW. Verifybreakbeforemake andphysicalactuatororientation.'
byref['Q1']['notes']='Gate1CHARGE_ALLOW with10kpulldown; source2TEMP_ALLOW_SINK; drain3CE. Bodydiode source->drain. CE10kpulluptoVSYS. NeverdirectlydriveCEfromMCU.'
for p in parts:
    if p['ref'].startswith('R'): p.update(tolerancePercent=1,footprint='Resistor_SMD:R_0402_1005Metric')
    if p['ref'].startswith('C'): p['capacitanceQualification']='Effective capacitance after DC bias, temperature and tolerance must meet device minimum. Nominal alone insufficient.'
result={'schemaVersion':1,'revision':'A04 candidate wiring 1','reviewedDate':'2026-09-09','scope':'Declarative review only. Root authors all CAD through KiCad MCP; no PCB position or route inherited. Prior A03 reviewed pin assignments inform compatible unchangedparts.', 'referenceCoordination':'U1/U2/U10 C1/C2 already placed byroot. U2charger/U3NAND. R1/R2repurposedNORpullups; newR24-R28. Allrefs enumeratedhere.', 'status':'Digital wiring ready for capture/ERC. Charging is candidate pending analog bias/corner evidence and exactpack. This is not releaseapproval.', 'components':parts,'externalParts':[{'ref':'M1','mpn':'VCLP1020B002L','maxBodyMm':{'diameter':10.1,'height':2.2},'tapeNominalMm':0.15,'installedReserveHeightMm':2.45,'runningMaxMa':30,'startingMaxMa':80,'pins':{'red':'HAPTIC_P','blue':'HAPTIC_N'}},{'ref':'TH1','mpn':'103AT-2','pins':{'1':'BAT_NTC','2':'GND'},'status':'Electricalcandidate; attachment and fullpackageheight unresolved'},{'ref':'BAT1','mpn':None,'status':'No approved battery. Procurement requirement, not partselection.','fullPackMaxEnvelopeMm':[26,21,3.3],'resetWorstChargeVoltageV':4.221,'maxNormalChargeMa':44,'targetContinuousDischargeMa':160}], 'releaseGates':['BQ25186TSadapterbias withCEhigh, acrossreset andwatchdog; R22thermalcorners andsensortolerance','Protectedpack approved4.221V chargermaximum; capacity/current/geometry/PCM/NTCmatched','MainLDOtransient/thermal budget with80mAmotorstartup','Native0.8mmboardrequested vs actualMCP1.6mm unresolved','NativeERC/netlistpinparity/DRC/actualmaxbodyspacing/noopenvia-in-paste','Actualacoustic/RF/ringdiffusion/firstarticle tests']}
assert len({p['ref'] for p in parts})==len(parts)
assert set(byref['U1']['pins']).isdisjoint(byref['U1']['noConnect'])
assert len(byref['U1']['pins'])+len(byref['U1']['noConnect'])==61
(ROOT/'docs/a04/schematic-contract.json').write_text(json.dumps(result,indent=2,ensure_ascii=True)+'\n',encoding='utf-8')
print(json.dumps({'components':len(parts),'connectedPins':sum(len(p['pins']) for p in parts),'mcuConnectedPins':len(byref['U1']['pins']),'mcuNC':len(byref['U1']['noConnect'])}))
