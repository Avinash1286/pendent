"""Analytic proposed XY map; not a native footprint or complete collision audit."""
import hashlib,itertools,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parent
cfg=json.loads((ROOT/'mechanism-contract.json').read_text())
cx,cy=cfg['privacy']['centreXYMm'];br=cfg['pcbDiameterMm']/2
def transform(x,y):return [cx+y,cy+x]
def corners(x,y,w,h):return [[x+dx*w/2,y+dy*h/2] for dx,dy in itertools.product((-1,1),repeat=2)]
pads=[]
for pin,x,y in [(1,-2.25,-2.55),(2,.75,-2.55),(3,2.25,-2.55),(4,-2.25,2.55),(5,.75,2.55),(6,2.25,2.55)]:
    pts=[transform(*p) for p in corners(x,y,.7,1.5)]
    pads.append({'pin':pin,'sourceCentreMm':[x,y],'sourceSizeMm':[.7,1.5],'cadCornersMm':pts,'edgeGapsMm':[br-math.hypot(*p) for p in pts]})
anchors=[]
for x,y in itertools.product((-3.65,3.65),(-1.8,1.8)):
    pts=[transform(*p) for p in corners(x,y,1,.8)]
    anchors.append({'sourceCentreMm':[x,y],'sourceSizeMm':[1,.8],'cadCornersMm':pts,'edgeGapsMm':[br-math.hypot(*p) for p in pts],'electricalIdentityUnresolved':True})
minimum=min(g for p in pads+anchors for g in p['edgeGapsMm'])
cellx,celly=cfg['cellCentreXYMm'];cellcorners=corners(cellx,celly,26,21)
col=cfg['retainerColumns']
result={
 'status':'PROPOSED XY MAP ONLY; NO NATIVE FOOTPRINT OR PHYSICAL ACCEPTANCE',
 'contractSha256':hashlib.sha256((ROOT/'mechanism-contract.json').read_bytes()).hexdigest(),
 'calculatorSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 'axes':'CAD X right, Y bail; native proposal X=100+CAD X,Y=100-CAD Y',
 'privacy':{
  'part':'CUS-22TB candidate, native JS202011JCQN unchanged',
  'source':'https://www.nidec-components.com/e/catalog/switch/cus.pdf',
  'sourcePage':3,'inspectedDrawingImages':['evidence/cus22-pad-detail.png','evidence/cus22-body-detail.png'],
  'sourceAxes':'X right and Y down on the inspected drawing; explicit backside transform must be verified against the selected land-pattern view before authoring',
  'backsideTransform':'CAD X=13.50+source Y; CAD Y=source X (reflection plus rotation)',
  'commons':[2,5],'throws':[[1,3],[4,6]],'pads':pads,'unnumberedAnchors':anchors,
  'npth':[{'sourceCentreMm':[x,0],'cadCentreMm':transform(x,0),'diameterMm':.9,'diameterPlusToleranceMm':.05} for x in (-1.5,1.5)],
  'minimumNominalPadEdgeGapMm':minimum,'currentNativeCopperEdgeRequirementMm':.5,
  'nominalPadCornersMeetRule':minimum>=.5,
  'ruleMarginMm':minimum-.5,
  'fullPadEnvelopeSourceMm':[8.3,6.6],
  'candidateRectangularCourtyardSourceMm':[8.9,7.2],
  'courtyardNote':'Nominal0.3mm pad margin; empty rectangle corners may extend outside board circle. Exact native courtyard/edge policy still requires review.',
  'maximumBodyCadBoundsMm':[[11.35,-3.45],[15.65,3.45]],
  'fullLeadConservativeCadBoundsMm':[[10.45,-4.15],[16.55,4.15]],
  'fullLeadBoundBasis':'Inference: nominal5.9mm transverse lead span plus general0.2mm tolerance; 8.3mm long bound conservatively equals pad envelope. Not manufacturer-selected worst-case terminal CAD.',
  'fullLeadConservativeCornerGapMm':br-math.hypot(16.55,4.15),
  'maximumLeverCentreNominalXYMm':[14.45,0],
  'maximumLeverBodyXYMm':[.9,1.4],
  'maximumLeverNominalMotionBoundsXYMm':[[14.0,-1.45],[14.9,1.45]],
  'leverMotionNote':'1.5mm nominal stroke, excluding position/stroke tolerances, fork take-up and unshimmed2.4mm housing travel. Shell endpoint shims are not yet designed.',
  'electricalOpenItem':'Four anchors are unnumbered; internal-structure ground-terminal wording does not establish their required grounding. Do not assign floating or ground as approved.',
  'fullTerminalsPresentInCsgAudit':False,
 },
 'cell':{'allocationMm':[26,21,3.3],'centreXYMm':[cellx,celly],'cornersXYMm':cellcorners,'minimumCavityGapMm':min(cfg['cavityDiameterMm']/2-math.hypot(*p) for p in cellcorners),'leftBossGapMm':(cellx-13)-(cfg['closure']['screwCentresXYMm'][0][0]+cfg['closure']['bossRadiusMm']),'privacyBodyGapMm':11.35-(cellx+13),'ntcInterfaceGapMm':11.2-(cellx+13),'growthReservationZMm':.4,'growthIncludedInRigidGauge':False,'qualified':False},
 'proposedNativeKeepouts':{
  'closureNotches':[{'centreXYMm':xy,'radiusMm':3.05} for xy in cfg['closure']['screwCentresXYMm']],
  'retainerColumnNotches':[{'centreXYMm':[col['radiusFromOriginMm']*math.cos(math.radians(a)),col['radiusFromOriginMm']*math.sin(math.radians(a))],'radiusMm':1.6} for a in col['anglesDeg']],
  'retainer':'Exact saved solid, not only annulus: R16.3..18.75 plus local boss bridges reaching inward aboutR13.4; upper11.3x16.3 radio relief at(0,8.6). PCB-relative bottom gap0.3mm.',
  'radio':{'centreXYMm':[0,8.6],'maximumBodyMm':[10.7,15.7,2.25],'solderSeatingMm':.15,'antennaCopperKeepoutImported':False},
  'erm':{'centreXYMm':[6,-5],'diameterMm':10.1,'mountedHeightMm':2.45,'tabReachFromCentreMm':6.6,'tabAndWiresIncludedInCsg':False},
  'faceSwitchCentreXYMm':[-5,-4],'centralStatusLedCentreXYMm':[0,0],
  'micPortsXYMm':[[-6.5,-13.8],[6.5,-13.8]],'gasketDiameterMm':3,
  'dockPadCentresXYMm':[[-3,-15.5],[0,-15.5],[3,-15.5]],'sensorBodyCentreXYMm':[13.2,-7],
  'actualNativePlacementImported':False,
 },
 'scenarioStacks':[{'scenario':s['id'],'bodyDepthMm':s['bodyDepthMm'],'pcbActualThicknessMm':1.6,'cellGaugeDepthMm':s['maximumAllocationMm'][2],'pcbBottomZMm':1+.15+s['maximumAllocationMm'][2]+.4+.15,'frontPressedMaximumPartClearanceMm':.3,'target0_8mmBoardScenarioAuthored':False} for s in cfg['cellScenarios']],
 'qualifiedClearanceFit':False,
 'limitations':['Small scalar gaps are unqualified, not acceptance margins for flexible pack, placement, solder or print tolerance.','No all-package placement, RF keepout, PCB axial support or complete assembly-path proof.','Full native pads, anchors, terminal geometry and copper rule checks remain in KiCad.']}
(ROOT/'allocation-audit.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'padEdgeMm':minimum,'cellGaps':result['cell'],'qualified':False}))
