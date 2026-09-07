"""Refresh A03 print ZIP and SHA256 manifest after rendering/independent audit.

Usage: python finalize_package.py
The caller must visually inspect final renders. This script does not claim that QA.
"""
from pathlib import Path
import json,hashlib,zipfile,struct,datetime,sys
root=Path(__file__).resolve().parent
contract=json.loads((root/'design-contract.json').read_text(encoding='utf-8'))
assert contract['revision']=='A03'
audit=json.loads((root/'assembly-audit.json').read_text(encoding='utf-8'))
assert audit['revision']=='A03'
for name,item in audit['topology'].items():
    assert item['connected_components']==1 and item['non_manifold_edges']==0,(name,item)
for name,item in audit['nominal_envelope_intersections'].items():
    assert item['intersection_mm3']<.0001,(name,item)
parts=['aura-front-shell.stl','aura-rear-shell.stl','aura-record-face.stl','aura-privacy-slider.stl','aura-top-retainer.stl','aura-contact-carrier.stl','aura-fit-coupon.stl','aura-dock-alignment-jig.stl']
for name in parts:
    data=(root/name).read_bytes();count=int.from_bytes(data[80:84],'little')
    assert count>0 and len(data)==84+50*count,('Invalid/empty binary STL',name,count,len(data))
docs=['PRINTING.md','MECHANICAL.md','aura-mechanical-drawing.svg','design-contract.json','mesh-audit.json','assembly-audit.json']
with zipfile.ZipFile(root/'aura-a03-print-kit.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
    for name in parts+docs:archive.write(root/name,name)
if '--prints-only' in sys.argv:
    (root/'asset-manifest.json').write_text(json.dumps({'revision':'A03','body_mm':contract['body_mm'],'overall_case_height_mm':54,'print_parts':parts,'print_kit':'aura-a03-print-kit.zip','physical_qualification':False,'render_batch_state':'RUNNING; run finalize_package.py after all six final renders and visual QA','render_log':'a03-release.log'},indent=2),encoding='utf-8')
    print('A03 eight-part print ZIP refreshed; render manifest unchanged')
    sys.exit(0)
renders=[]
for name in ['hero-transparent.png','detail.png','profile.png','hero.png','rear.png','exploded.png']:
    p=root/'renders'/name;raw=p.read_bytes();assert raw[:8]==b'\x89PNG\r\n\x1a\n'
    w,h=struct.unpack('>II',raw[16:24]);renders.append({'path':'renders/'+name,'width':w,'height':h})
files=[]
for p in sorted(root.iterdir()):
    if p.is_file() and p.suffix.lower() in ['.blend','.glb','.stl','.svg','.md','.json','.zip','.py'] and p.name not in ['asset-manifest.json','revise_a03.py','check_normals.py']:
        files.append(p)
files += [root/r['path'] for r in renders]
manifest={'revision':'A03','generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'units':{'blender_glb':'metres','stl':'millimetres'},'body_mm':contract['body_mm'],'overall_case_height_mm':54,'physical_qualification':False,'render_visual_qa':'Caller must inspect final images after the render batch; not validated by this script','print_parts':parts,'renders':renders,'files':[{'path':p.relative_to(root).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]}
(root/'asset-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('A03 print ZIP and manifest refreshed:',len(files),'files')
