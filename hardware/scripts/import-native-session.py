"""Import an authored tscircuit/Freerouting interchange after explicit CLI fallback authorization.

Preserves original placement and verifies footprint pad identities before saving
to a separate native working board. This is not a fabrication-release assertion.
Run with the Python distributed with KiCad 10.
"""
import hashlib
import json
from pathlib import Path
import pcbnew

root = Path(__file__).resolve().parents[1]
source = root / "output/aura-placement.kicad_pcb"
session = root / "output/aura-a03-route-refine.ses"
destination = root / "output/aura-a03-native-routing.kicad_pcb"

def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def pads(board):
    return sorted((f.GetReference(),p.GetNumber(),p.GetNetname(),p.GetPosition().x,p.GetPosition().y,p.GetSize().x,p.GetSize().y) for f in board.GetFootprints() for p in f.Pads())

inputs=json.loads((root / "output/aura-a03-routing-inputs.json").read_text())
for item in inputs["inputs"]:
    assert checksum(root/item["path"]) == item["sha256"], item["path"]
board=pcbnew.LoadBoard(str(source))
before=pads(board)
assert pcbnew.ImportSpecctraSES(board,str(session)), "Native SES import failed"
after=pads(board)
assert before == after, "SES changed pad identity/geometry; do not save"
pcbnew.SaveBoard(str(destination),board)
tracks=list(board.GetTracks())
vias=sum(isinstance(t,pcbnew.PCB_VIA) for t in tracks)
report={"source":str(source.relative_to(root)),"sourceSha256":checksum(source),"session":str(session.relative_to(root)),"sessionSha256":checksum(session),"destination":str(destination.relative_to(root)),"destinationSha256":checksum(destination),"padIdentitiesAndGeometryUnchanged":True,"footprints":len(list(board.GetFootprints())),"trackSegments":len(tracks)-vias,"vias":vias,"fabricationReady":False,"authorization":"User explicitly requested tscircuit/CLI fallback after connector import cancellation."}
(root/"output/aura-a03-native-import.json").write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps(report,indent=2))
