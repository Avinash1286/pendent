"""Add stitched ground pours and enforce the physical radio antenna exclusion.

All candidate stitching vias are checked against existing copper and drill
geometry before native zone filling; KiCad DRC remains the final acceptance gate.
"""
import importlib.util,json,math
from pathlib import Path
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('router',root/'scripts/complete-native-routing.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
pcbnew=r.pcbnew;board=pcbnew.LoadBoard(str(r.BOARD));items,drills,smd=r.geometry(board)
outline=r.box(98,89,102,111).buffer(10,resolution=64)
safe=outline.buffer(-.65).intersection(r.box(0,88.5,200,200))
foreign=r.unary_union([it[3] for it in items if it[1]!='GND'])
safe=safe.difference(foreign.buffer(.225+.12+.006))
safe=safe.difference(r.unary_union([g for n,g in drills]).buffer(.1+.25+.006))
safe=safe.difference(r.unary_union(smd).buffer(.225+.04))
ground=board.FindNet('GND');positions=[];pad_distances=[]
def place(p):
    if not safe.covers(r.Point(p)):return False
    if any(math.dist(p,q)<.65 for q in positions):return False
    v=pcbnew.PCB_VIA(board);v.SetPosition(r.pos(p));v.SetWidth(pcbnew.FromMM(.45));v.SetDrill(pcbnew.FromMM(.20));v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetNet(ground);board.Add(v);positions.append(p);return True
for fp in board.GetFootprints():
    for pad in fp.Pads():
        if pad.GetNetname()!='GND':continue
        p=r.pt(pad.GetPosition())
        if any(math.dist(p,q)<1.1 for q in positions):continue
        candidates=[]
        for radius in [i*.10 for i in range(4,26)]:
            for angle in range(0,360,15):
                rad=math.radians(angle);q=(round(p[0]+radius*math.cos(rad),3),round(p[1]+radius*math.sin(rad),3))
                if safe.covers(r.Point(q)):candidates.append((radius,q))
            if candidates:break
        if candidates:
            for distance,q in sorted(candidates):
                if place(q):pad_distances.append({'ref':fp.GetReference(),'pad':pad.GetNumber(),'distance':distance});break
for y in r.np.arange(89.5,120,3.0):
    for x in r.np.arange(89.5,111.5,3.0):
        p=(float(x),float(y))
        if not any(math.dist(p,q)<2.0 for q in positions):place(p)
for fp in board.GetFootprints():
    for pad in fp.Pads():
        if pad.GetNetname()=='GND' and ((fp.GetReference(),pad.GetNumber()) in [('U2','9'),('U3','11'),('U5','9')] or fp.GetReference() in ('MIC1','MIC2','J1','J2','J3','J4')):
            pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
for zone in list(board.Zones()):board.Remove(zone);zone.thisown=False
for layer in r.LAYERS:
    zone=pcbnew.ZONE(board);zone.SetLayer(layer);zone.SetNet(ground);zone.SetZoneName('GND return and shielding; RF exclusion north of y=11.95')
    zone.SetLocalClearance(pcbnew.FromMM(.12));zone.SetMinThickness(pcbnew.FromMM(.12));zone.SetThermalReliefGap(pcbnew.FromMM(.12));zone.SetThermalReliefSpokeWidth(pcbnew.FromMM(.15));zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL if layer in (pcbnew.F_Cu,pcbnew.B_Cu) else pcbnew.ZONE_CONNECTION_FULL)
    poly=zone.Outline();poly.NewOutline()
    for x,y in [(88.3,88.05),(111.7,88.05),(111.7,120.7),(88.3,120.7)]:poly.Append(round(x*1e6),round(y*1e6))
    board.Add(zone)
keepout=pcbnew.ZONE(board);ls=pcbnew.LSET()
for layer in r.LAYERS:ls.AddLayer(layer)
keepout.SetLayerSet(ls);keepout.SetIsRuleArea(True);keepout.SetZoneName('Raytac antenna: no board copper above physical Y11.95')
keepout.SetDoNotAllowTracks(True);keepout.SetDoNotAllowVias(True);keepout.SetDoNotAllowPads(True);keepout.SetDoNotAllowZoneFills(True);keepout.SetDoNotAllowFootprints(False)
poly=keepout.Outline();poly.NewOutline()
for x,y in [(88,79),(112,79),(112,88.05),(88,88.05)]:poly.Append(round(x*1e6),round(y*1e6))
board.Add(keepout)
board.BuildConnectivity();filler=pcbnew.ZONE_FILLER(board);assert filler.Fill(board.Zones()),'Native fill failed'
pcbnew.SaveBoard(str(r.BOARD),board)
(root/'output/aura-a03-ground-system.json').write_text(json.dumps({'stitchingViaDiameter':.45,'drill':.20,'newStitchingVias':positions,'nearPadStitches':pad_distances,'layers':['F.Cu','In1.Cu','In2.Cu','B.Cu'],'rfExclusionPhysicalY':[11.95,21],'zoneClearance':.12,'thermalSpoke':.15},indent=2)+'\n')
print('Added',len(positions),'checked ground stitches and four native filled return zones')
