"""Independent envelope collision/connected-topology audit of saved Blender file.
Run with Blender background --python verify_geometry.py. Does not save the scene.
"""
import bpy,bmesh,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'aura-product.blend'))
result={'units':'mm / cubic mm','method':'Manifold boolean kernel with millimetre-scaled, normal-recalculated mesh copies; nominal geometry only','topology':{},'nominal_envelope_intersections':{}}
contacts=[ob for ob in bpy.data.objects if ob.name.startswith('Charging_Contact_') and ob.name!='Charging_Contact_Bed']
contacts.sort(key=lambda ob:ob.location.x)
result['charging_interface']={
    'contact_count':len(contacts),
    'centers_mm':[[round(v*1000,4) for v in ob.location] for ob in contacts],
    'diameters_mm':[round(ob.dimensions.x*1000,4) for ob in contacts],
    'required_interposer':'passive flex/insulated leads routed around cell perimeter; not direct through-cell pogo pins',
}
assert len(contacts)==3,'Charging interface must have exactly3contacts'
for ob,x in zip(contacts,[-3,0,3]):
    assert abs(ob.location.x*1000-x)<.001 and abs(ob.location.y*1000+15)<.001,'Charging XY coordinates must align with J1'
    assert abs(ob.dimensions.x*1000-1.7)<.001,'Charging pad diameter must be1.7mm'
for name in ['Housing_Front','Housing_Back','Record_Button']:
    ob=bpy.data.objects[name];bm=bmesh.new();bm.from_mesh(ob.data)
    todo=set(bm.verts);components=0
    while todo:
        seed=todo.pop();stack=[seed];components+=1
        while stack:
            v=stack.pop()
            for edge in v.link_edges:
                neighbor=edge.other_vert(v)
                if neighbor in todo:todo.remove(neighbor);stack.append(neighbor)
    result['topology'][name]={'connected_components':components,'non_manifold_edges':sum(not e.is_manifold for e in bm.edges),'volume_mm3':round(bm.calc_volume()*1e9,5)}
    bm.free()
for a,b in [('Housing_Front','Housing_Back'),('PCB_Reference','Housing_Back'),('PCB_Reference','Housing_Front'),('Battery_Envelope','Housing_Back'),('Battery_Envelope','PCB_Reference'),('RF_Module_Envelope','Housing_Front'),('Record_Button','Housing_Front'),('Haptic_Reference','Housing_Front'),('Haptic_Reference','PCB_Reference')]:
    copies=[]
    for name in [a,b]:
        ob=bpy.data.objects[name].copy();ob.data=ob.data.copy();bpy.context.collection.objects.link(ob)
        bm=bmesh.new();bm.from_mesh(ob.data);bmesh.ops.recalc_face_normals(bm,faces=bm.faces);bm.to_mesh(ob.data);bm.free()
        for v in ob.data.vertices:v.co*=1000
        ob.location*=1000
        copies.append(ob)
    ob,other=copies
    mod=ob.modifiers.new('Envelope check','BOOLEAN');mod.operation='INTERSECT';mod.solver='MANIFOLD';mod.object=other
    bpy.context.view_layer.objects.active=ob
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bm=bmesh.new();bm.from_mesh(ob.data)
    result['nominal_envelope_intersections'][a+' vs '+b]={'intersection_mm3':round(abs(bm.calc_volume()),6),'faces':len(bm.faces)}
    bm.free()
    for ob in copies:bpy.data.objects.remove(ob,do_unlink=True)
(ROOT/'assembly-audit.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
