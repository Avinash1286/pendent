"""Reverse the nonpolar bypass capacitor in place for a direct supply/ground
fanout; its body position and mechanical envelope are unchanged."""
import pcbnew
from pathlib import Path
root=Path(__file__).resolve().parents[1];path=root/'output/aura-a03-native-routing.kicad_pcb'
b=pcbnew.LoadBoard(str(path));f=next(f for f in b.GetFootprints() if f.GetReference()=='C18');f.SetOrientationDegrees(270)
old=None
for t in b.GetTracks():
    if t.m_Uuid.AsString()=='4b42b9db-e610-4f63-87d7-665effcca09b':
        old=t.GetPosition();new=pcbnew.VECTOR2I(old.x,old.y-pcbnew.FromMM(.2));t.SetPosition(new);break
if old:
    for t in b.GetTracks():
        if isinstance(t,pcbnew.PCB_VIA):continue
        if t.GetStart()==old:t.SetStart(new)
        if t.GetEnd()==old:t.SetEnd(new)
b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones());pcbnew.SaveBoard(str(path),b)
print('C18 reversed in place to270deg; RECORD_N via moved0.2mm from C17 paste edge')
