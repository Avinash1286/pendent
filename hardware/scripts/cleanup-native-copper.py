"""Remove DRC-identified dangling branches, preserving complete connectivity."""
import pcbnew,json,subprocess,hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[1];boardpath=root/'output/aura-a03-native-routing.kicad_pcb';drcpath=root/'output/kicad-a03-cleanup-drc.json'
cli=Path(pcbnew.__file__).parents[2]/'kicad-cli.exe'
if not cli.exists():cli=Path('C:/Program Files/KiCad/10.0/bin/kicad-cli.exe')
def drc():
    subprocess.run([str(cli),'pcb','drc','--format','json','--all-track-errors','--output',str(drcpath),str(boardpath)],check=True,capture_output=True)
    return json.loads(drcpath.read_text())
history=[];report=drc();assert not report['unconnected_items'],'Complete all intended nets before dangling cleanup'
for iteration in range(12):
    ids={i['uuid'] for v in report['violations'] if v['type'] in ('track_dangling','via_dangling') for i in v['items']}
    if not ids:break
    original=boardpath.read_bytes();b=pcbnew.LoadBoard(str(boardpath));removed=[]
    for t in list(b.GetTracks()):
        if t.m_Uuid.AsString() in ids:removed.append({'uuid':t.m_Uuid.AsString(),'net':t.GetNetname()});b.Remove(t);t.thisown=False
    if not removed:raise RuntimeError('DRC dangling items did not resolve to copper')
    b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones());pcbnew.SaveBoard(str(boardpath),b)
    report=drc()
    if report['unconnected_items']:
        boardpath.write_bytes(original);raise RuntimeError('Cleanup altered connectivity; restored previous board')
    history.append({'iteration':iteration,'removed':removed,'remainingDangling':sum(v['type'] in ('track_dangling','via_dangling') for v in report['violations'])});print('Cleanup',iteration,len(removed),'items; remaining',history[-1]['remainingDangling'],flush=True)
else:raise RuntimeError('More cleanup passes required')
(root/'output/aura-a03-copper-cleanup.json').write_text(json.dumps({'passes':history,'finalBoardSha256':hashlib.sha256(boardpath.read_bytes()).hexdigest(),'unconnected':len(report['unconnected_items'])},indent=2)+'\n')
print('Dangling copper cleanup complete; all nets remain connected')
