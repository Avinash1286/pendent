"""Enforce antenna copper exclusion and use solid low-impedance ground bonds.

Solid ground lands require the assembly thermal profile documented in fab notes.
"""
import pcbnew,json
from pathlib import Path
root=Path(__file__).resolve().parents[1];path=root/'output/aura-a03-native-routing.kicad_pcb'
board=pcbnew.LoadBoard(str(path));report=json.loads((root/'output/kicad-a03-grounded-drc.json').read_text())
ids={i['uuid'] for v in report['violations'] if v['type']=='items_not_allowed' for i in v['items']}
for t in list(board.GetTracks()):
    if t.m_Uuid.AsString() in ids:board.Remove(t);t.thisown=False
for fp in board.GetFootprints():
    for pad in fp.Pads():
        if pad.GetNetname()=='GND':pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
for d in board.GetDrawings():
    if isinstance(d,pcbnew.PCB_TEXT) and d.GetLayer() in (pcbnew.F_SilkS,pcbnew.B_SilkS):
        d.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(1),pcbnew.FromMM(1)));d.SetTextThickness(pcbnew.FromMM(.15))
board.BuildConnectivity();assert pcbnew.ZONE_FILLER(board).Fill(board.Zones())
pcbnew.SaveBoard(str(path),board)
print('Removed',len(ids),'RF-exclusion crossings; solid GND lands and 1mm silkscreen set')
