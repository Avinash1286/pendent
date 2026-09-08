"""Focused package/cavity audit; never saves or mutates the source Blender scene.
Run: blender --background --threads 4 --python audit_placement_sync.py
Bodies are source-catalog envelopes, with exact KEMET maximum dimensions where known.
This is a digital clearance check, not physical qualification or vendor STEP validation.
"""
import bpy,bmesh,json,math,hashlib,struct,sys
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parent
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'aura-product.blend'))
placements=json.loads((ROOT/'pcb-placement-reference.json').read_text())
spec=json.loads((ROOT/'component-body-reference.json').read_text())
proposals=json.loads((ROOT/'placement-sync-proposals.json').read_text(encoding='utf-8-sig'))
current_mode='--current' in sys.argv
if not current_mode:placements=proposals.get('baseline_positions',placements)
MM=.001

def box(ref,pos,dimensions=None):
    entry=spec['bodies'][ref]
    dims=dimensions or entry.get('maximum_body_mm',entry.get('body_nominal_mm',entry['nominal_mm']))
    if not dims or entry['side']!='top':return None
    radians=math.radians(pos.get('r',0))
    width=abs(math.cos(radians))*dims[0]+abs(math.sin(radians))*dims[1]
    height=abs(math.sin(radians))*dims[0]+abs(math.cos(radians))*dims[1]
    return {'ref':ref,'dims_mm':dims,'uses_verified_maximum':'maximum_body_mm' in entry,
            'min':[pos['x']-width/2,pos['y']-height/2,.65],
            'max':[pos['x']+width/2,pos['y']+height/2,.65+.10+dims[2]]}

def gap(a,b):
    distances=[max(a['min'][i]-b['max'][i],b['min'][i]-a['max'][i]) for i in range(3)]
    return math.sqrt(sum(max(0,d)**2 for d in distances)),distances

def temp_box(item):
    center=[(a+b)/2*MM for a,b in zip(item['min'],item['max'])]
    bpy.ops.mesh.primitive_cube_add(size=1,location=center)
    ob=bpy.context.object;ob.dimensions=[(b-a)*MM for a,b in zip(item['min'],item['max'])]
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    return ob

def intersect(source,obstacle):
    copies=[]
    for original in [source,obstacle]:
        ob=original.copy();ob.data=original.data.copy();bpy.context.collection.objects.link(ob)
        ob.data.transform(ob.matrix_world);ob.matrix_world.identity()
        for v in ob.data.vertices:v.co*=1000
        bm=bmesh.new();bm.from_mesh(ob.data);bmesh.ops.recalc_face_normals(bm,faces=bm.faces);bm.to_mesh(ob.data);bm.free()
        copies.append(ob)
    a,b=copies;bpy.context.view_layer.objects.active=a
    mod=a.modifiers.new('Focused intersection','BOOLEAN');mod.operation='INTERSECT';mod.solver='MANIFOLD';mod.object=b
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bm=bmesh.new();bm.from_mesh(a.data);volume=round(abs(bm.calc_volume()),6);bm.free()
    for ob in copies:bpy.data.objects.remove(ob,do_unlink=True)
    return volume

pressed=bpy.data.objects['Record_Button'].copy();pressed.data=pressed.data.copy();bpy.context.collection.objects.link(pressed)
pressed.location.z-=.35*MM;pressed.name='Audit_Pressed_Face'
obstacles=[bpy.data.objects[name] for name in ['Housing_Front','Housing_Back','Battery_Envelope','Haptic_Reference','Haptic_Insulator','RF_Module_Envelope']]+[pressed]
result={'scope':'Current saved component placement assessment' if current_mode else 'Provisional routing-move assessment; no placement changes made by this script',
 'scene_sha256':hashlib.sha256((ROOT/'aura-product.blend').read_bytes()).hexdigest(),
 'placement_reference_sha256':hashlib.sha256((ROOT/'pcb-placement-reference.json').read_bytes()).hexdigest() if current_mode else None,
 'body_reference_sha256':hashlib.sha256((ROOT/'component-body-reference.json').read_bytes()).hexdigest(),
 'baseline_positions':placements,
 'physical_qualification':False,'units':'mm and mm³','method':'Source body rectangles, exact manufacturer maximum bodies where verified, plus0.10mm vertical solder allowance; manifold boolean against actual saved cavity/face/cell/motor/RF solids',
 'limitations':'Dimensions for other packages are nominal source-catalog envelopes, not tolerance-qualified vendor STEP. No XY placement error or solder fillet envelope is included. Shell molding/printing and cell swelling remain unqualified.',
 'candidates':{}}
candidates={'current':{ref:{} for ref in ['C7','C8','C10','C18','R22','R23','D1','Q1','R7','C17']}} if current_mode else proposals['candidates']
for candidate,changes in candidates.items():
    values={ref:{**pos,**changes.get(ref,{})} for ref,pos in placements.items()}
    boxes={ref:box(ref,pos) for ref,pos in values.items() if ref in spec['bodies']}
    boxes={ref:entry for ref,entry in boxes.items() if entry}
    entry={'positions':{ref:values[ref] for ref in changes},'component_envelope_overlaps':[],'component_envelope_contacts':[],'nearest_other_body':{},'solid_intersections_mm3':{},'pressed_face_vertical_gap_mm':{}}
    seen=set()
    for ref in changes:
        current=boxes[ref];distances=[]
        for other,item in boxes.items():
            if ref==other:continue
            separation,axes=gap(current,item);key=tuple(sorted([ref,other]))
            distances.append((separation,other))
            if all(d<-.00001 for d in axes) and key not in seen:
                entry['component_envelope_overlaps'].append({'a':ref,'b':other,'axis_overlap_mm':[-round(d,6) for d in axes]});seen.add(key)
            elif separation<.00001 and key not in seen:
                entry['component_envelope_contacts'].append({'a':ref,'b':other,'note':'Zero nominal separation; no placement tolerance allowance'});seen.add(key)
        distance,other=min(distances)
        entry['nearest_other_body'][ref]={'ref':other,'gap_mm':round(distance,6)}
        entry['pressed_face_vertical_gap_mm'][ref]=round(3.70-current['max'][2],6)
        temp=temp_box(current)
        for obstacle in obstacles:entry['solid_intersections_mm3'][ref+' vs '+obstacle.name]=intersect(temp,obstacle)
        bpy.data.objects.remove(temp,do_unlink=True)
    if 'Q1' in changes:
        leadbox=box('Q1',values['Q1'],spec['bodies']['Q1']['maximum_lead_span_mm'])
        leads={'envelope_mm':spec['bodies']['Q1']['maximum_lead_span_mm'],'interpretation':'Conservative full rectangular sweep enclosing plastic body and all three leads; not solder lands or courtyard','overlaps':[],'nearest_other_body':None}
        distances=[]
        for other,item in boxes.items():
            if other=='Q1':continue
            separation,axes=gap(leadbox,item);distances.append((separation,other))
            if all(d<-.00001 for d in axes):leads['overlaps'].append({'ref':other,'axis_overlap_mm':[-round(d,6) for d in axes]})
        distance,other=min(distances);leads['nearest_other_body']={'ref':other,'gap_mm':round(distance,6)}
        entry['q1_maximum_lead_sweep']=leads
    result['candidates'][candidate]=entry
bpy.data.objects.remove(pressed,do_unlink=True)
(ROOT/('placement-current-audit.json' if current_mode else 'placement-sync-audit.json')).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps({name:{'overlaps':item['component_envelope_overlaps'],'solid_collisions':{key:volume for key,volume in item['solid_intersections_mm3'].items() if volume>.0001},'nearest_other_body':item['nearest_other_body'],'pressed_face_gaps':item['pressed_face_vertical_gap_mm']} for name,item in result['candidates'].items()},indent=2),flush=True)
