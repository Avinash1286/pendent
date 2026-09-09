"""Arithmetic/source checks accompanying the M2 saved-solid audits; no native CAD mutation."""
import hashlib,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parent;REPO=ROOT.parents[2]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
c=json.loads((ROOT/'contract.json').read_text(encoding='utf-8'));authority=REPO/'docs/a04/cus22-candidate-verification.json';cus=json.loads(authority.read_text(encoding='utf-8'))
scenarios=[];errors=[]
for case in c['scenarios']:
 s=case['id'];m=json.loads((ROOT/s/'parts-manifest.json').read_text(encoding='utf-8'));padchecks=[]
 for pad in m['cusPadMap']:
  source=next(p for p in cus['proposedPadGeometry'] if p['pad']==str(pad['pin']))
  ok=all(abs(x-y)<1e-8 for x,y in zip(pad['cadXY'],source['proposedCadCentreMm'])) and pad['cadSizeMm']==source['proposedNativeSizeMm'];padchecks.append({'pin':pad['pin'],'matchesAuthoritativeCandidate':ok})
  if not ok:errors.append(s+' pad '+str(pad['pin']))
 p=m['pcbBottomZMm'];pt=m['pcbTopZMm'];maxr=math.hypot(16.2,10.5)
 scenarios.append({'scenario':s,'bodyDiameterMm':43,'bodyDepthMm':case['bodyDepthMm'],'pcbPlaneMm':[p,pt],'cellBottomMm':1.15,'maximumCellTopMm':1.15+case['cellDepthMm'],'growthTopMm':p-.15,'dielectricTopMm':p-.05,'cellCornerToCavityNominalMm':20-maxr,'threeLowerPcbSeatsXYMm':c['pcbDatums']['centresXYMm'],'padChecks':padchecks,'allObjectBoundsAndGeometryHashesPresent':len(m['allAssemblyObjects'])==70,'manifestSha256':sha(ROOT/s/'parts-manifest.json')})
 if len(m['allAssemblyObjects'])!=70:errors.append(s+' complete object metadata')
area=6.2**2
report={'status':'ARITHMETIC AND SOURCE CONCORDANCE ONLY; NO NATIVE/PHYSICAL APPROVAL','allPass':not errors,'errors':errors,'contractSha256':sha(ROOT/'contract.json'),'authoritativeCusReview':str(authority.relative_to(REPO)).replace('\\','/'),'authoritativeCusReviewSha256':sha(authority),'cusNativeAssigned':False,'nativePlacementImported':False,'scenarios':scenarios,'capture':{'freeFoamMm':.79,'restFoamMm':.74,'nominalFullFoamMm':.39,'restCompressionPercent':100*(.79-.74)/.79,'nominalFullCompressionPercent':100*(.79-.39)/.79,'areaMm2':area,'releasePreloadStressMustBeBelowKPa':.9/area*1000,'operationStressMustExceedKPa':1.5/area*1000,'datasheet25PercentDeflectionStressKPa':[41,97],'calculated25PercentForceN':[area*.041,area*.097],'forceMeasurementExists':False,'safeSwitchEndpointKnown':False,'installedThinSheetUseQualified':False,'source':'https://www.rogerscorp.com/-/media/project/rogerscorp/documents/elastomeric-material-solutions/bisco/english/data-sheets/180-070-ht-800---medium-cellular-silicone.pdf'},'returnBearing':{'padRadiusMm':.7,'bossRadiusMm':.9,'nominalFullBearingAreaEachMm2':math.pi*.7**2,'nominalRadialAlignmentAllowanceMm':.2,'workingRestThicknessMm':1,'workingFullThicknessMm':.4,'forceCreepShearQualified':False},'privacy':{'mapping':'CAD X=13.5+sourceY; CAD Y=-sourceX','nominalCentreX':14.85,'fullTransverseTolerancePlusLocatorMm':[13.95,15.75],'externalTravelRule':'T+G-w','keeperChannelRule':'2.2+T+G-w','minimumNominalMaximumChannelMm':[4.1,4.4,4.7],'asymmetricLocatorAndEndpointCalibrationRequired':True,'contactTimingQualified':False,'anchorElectricalIdentityResolved':False},'structuralQualification':{'proven':False,'revision':'S1 hybrid candidate','separateHardware':['0.30 mm candidate steel shoe','1.00 mm CAD maximum lower steel plate','Measured insulating contact pad'],'screenReport':'structural-screen.json','required':'Incoming stock certificate/thickness, measured root joint/liner/closure force-displacement, print process, off-axis load, cycle/creep and switch endpoint tests before any print or powered release.'},'physicalQualification':False,'scriptSha256':sha(Path(__file__))}
(ROOT/'engineering-audit.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps({'allPass':not errors,'errors':errors}))
if errors:raise SystemExit(1)
