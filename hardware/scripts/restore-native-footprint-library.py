"""Prepare a portable snapshot library and restore source Fab/courtyard geometry.

Default mode only changes a detached in-memory board and writes a JSON plan.
--apply requires --expected-sha256 to avoid racing the routing task. Existing pad,
mask, paste, copper and keepout geometry is preserved. No PCB sync is performed.
Run with the Python shipped with KiCad 10.
"""
import argparse, hashlib, json, math, re, sys, traceback
from pathlib import Path
import pcbnew

ROOT=Path(__file__).resolve().parents[1]
BOARD_PATH=ROOT/'output/aura-a03-native-routing.kicad_pcb'
LIBRARY_PATH=ROOT/'pcb-snapshot.pretty'
GRAPHIC_LAYERS=(pcbnew.F_Fab,pcbnew.B_Fab,pcbnew.F_CrtYd,pcbnew.B_CrtYd)

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def xy(v): return [round(v.x/1e6,6),round(v.y/1e6,6)]
def pad_fingerprint(board):
    return sorted((f.GetReference(),p.m_Uuid.AsString(),p.GetNumber(),p.GetNetname(),p.GetPosition().x,p.GetPosition().y,p.GetSize().x,p.GetSize().y,p.GetOrientationDegrees(),p.GetShape(),p.GetLayerSet().FmtBin(),p.GetDrillSize().x,p.GetDrillSize().y,p.GetLocalSolderMaskMargin(),p.GetLocalSolderPasteMargin(),p.GetLocalSolderPasteMarginRatio()) for f in board.GetFootprints() for p in f.Pads())
def copper_fingerprint(board):
    return sorted((t.m_Uuid.AsString(),t.GetClass(),t.GetLayer(),t.GetNetCode(),t.GetStart().x,t.GetStart().y,t.GetEnd().x,t.GetEnd().y,t.GetWidth(pcbnew.F_Cu) if isinstance(t,pcbnew.PCB_VIA) else t.GetWidth()) for t in board.GetTracks())
def bbox(graphics):
    if not graphics: return None
    boxes=[g.GetBoundingBox() for g in graphics]
    return (min(b.GetLeft() for b in boxes),min(b.GetTop() for b in boxes),max(b.GetRight() for b in boxes),max(b.GetBottom() for b in boxes))
def intersections(boxa,boxb):
    if not boxa or not boxb: return None
    w=min(boxa[2],boxb[2])-max(boxa[0],boxb[0]); h=min(boxa[3],boxb[3])-max(boxa[1],boxb[1])
    return [round(w/1e6,6),round(h/1e6,6)] if w>1000 and h>1000 else None

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--expected-sha256')
    args=parser.parse_args()
    before_hash=sha(BOARD_PATH)
    if args.apply and args.expected_sha256!=before_hash:
        raise RuntimeError('--apply requires the exact current board SHA-256 supplied by routing owner')
    board=pcbnew.LoadBoard(str(BOARD_PATH))
    before_pads=pad_fingerprint(board); before_copper=copper_fingerprint(board)
    specs=json.loads((ROOT/'src/footprints.json').read_text())
    parts={p['ref']:p for p in json.loads((ROOT/'output/design-manifest.json').read_text())['parts']}
    native=list(board.GetFootprints()); records=[]; source_origins={}; bodies={}
    assert len(native)==61
    for f in sorted(native,key=lambda f:f.GetReference()):
        ref=f.GetReference(); part=parts[ref]
        directory=ROOT/('library.pretty' if ref.startswith('J') else 'library')
        name=part['mpn'] if ref.startswith('J') else specs[part['fp']]['library'].split(':')[1]
        original=pcbnew.FootprintLoad(str(directory),name)
        if original is None: raise RuntimeError(f'Missing source footprint {name}')
        original.SetParent(board)
        original.SetOrientation(f.GetOrientation())
        # tscircuit already mirrored the four B.Cu contact patterns; its container
        # remains F.Cu. Preserve that container and align the source geometry only.
        if ref.startswith('J'):
            original.Flip(pcbnew.VECTOR2I(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        elif f.GetLayer()==pcbnew.B_Cu:
            original.Flip(pcbnew.VECTOR2I(0,0),pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
        n1=next(p for p in f.Pads() if p.GetNumber()=='1')
        o1=next(p for p in original.Pads() if p.GetNumber()=='1')
        original.SetPosition(original.GetPosition()+n1.GetPosition()-o1.GetPosition())
        residuals=[]
        for p in f.Pads():
            if not p.GetNumber(): continue
            choices=[q for q in original.Pads() if q.GetNumber()==p.GetNumber()]
            if not choices: raise RuntimeError(f'{ref}.{p.GetNumber()} absent in source')
            residual=min(math.hypot(p.GetPosition().x-q.GetPosition().x,p.GetPosition().y-q.GetPosition().y)/1e6 for q in choices)
            residuals.append(residual)
            if residual>0.000002: raise RuntimeError(f'{ref}.{p.GetNumber()} source alignment error {residual} mm')
        source_origins[ref]=original.GetPosition()
        copies=[]
        for graphic in original.GraphicalItems():
            if isinstance(graphic,pcbnew.PCB_SHAPE) and graphic.GetLayer() in GRAPHIC_LAYERS:
                copied=graphic.Duplicate()
                copied.SetParent(f)
                copies.append(copied)
        # Only replace the target documentation layers; preserve the microphone's
        # custom copper annulus, mask/paste arcs and every other existing layer.
        removed=[]
        for graphic in list(f.GraphicalItems()):
            if isinstance(graphic,pcbnew.PCB_SHAPE) and graphic.GetLayer() in GRAPHIC_LAYERS:
                removed.append(graphic.m_Uuid.AsString()); f.Remove(graphic)
        for copied in copies: f.Add(copied)
        old_id=f.GetFPIDAsString(); snapshot_name='A03_'+ref
        f.SetFPIDAsString('AURA_PCB:'+snapshot_name)
        f.BuildCourtyardCaches()
        body_layer=pcbnew.B_Fab if ref.startswith('J') or f.GetLayer()==pcbnew.B_Cu else pcbnew.F_Fab
        bodies[ref]=(body_layer,bbox([g for g in copies if g.GetLayer()==body_layer]))
        records.append({'ref':ref,'oldId':old_id,'newId':f.GetFPIDAsString(),'source':str((directory/(name+'.kicad_mod')).relative_to(ROOT)),'sourceSha256':sha(directory/(name+'.kicad_mod')),'nativeOrigin':xy(f.GetPosition()),'alignedBodyOrigin':xy(original.GetPosition()),'sourcePadAlignmentMaxResidualMm':max(residuals),'restoredGraphicShapes':len(copies),'replacedGraphicShapes':len(removed),'frontCourtyardContours':f.GetCourtyard(pcbnew.F_CrtYd).OutlineCount(),'backCourtyardContours':f.GetCourtyard(pcbnew.B_CrtYd).OutlineCount(),'contactContainerPreserved':ref.startswith('J')})
        records[-1]['fabBoundsMm']=[round(v/1e6,6) for v in bodies[ref][1]] if bodies[ref][1] else None
        for layer,key in [(pcbnew.F_CrtYd,'frontCourtyardBoundsMm'),(pcbnew.B_CrtYd,'backCourtyardBoundsMm')]:
            poly=f.GetCourtyard(layer)
            if poly.OutlineCount():
                bound=poly.BBox()
                records[-1][key]=[round(v/1e6,6) for v in [bound.GetLeft(),bound.GetTop(),bound.GetRight(),bound.GetBottom()]]
    text_updates=[]
    for text in board.GetDrawings():
        if not isinstance(text,pcbnew.PCB_TEXT) or text.GetLayer() not in (pcbnew.F_Fab,pcbnew.B_Fab): continue
        ref=text.GetText()
        if ref in source_origins:
            old=xy(text.GetPosition()); text.SetPosition(source_origins[ref])
            mirrored=text.GetLayer()==pcbnew.B_Fab
            changed=(text.IsMirrored()!=mirrored)
            text.SetMirrored(mirrored)
            if old!=xy(text.GetPosition()) or changed: text_updates.append({'ref':ref,'oldPosition':old,'newPosition':xy(text.GetPosition()),'mirrored':mirrored})
    overlaps=[]; body_overlaps=[]
    for i,a in enumerate(native):
        for b in native[i+1:]:
            for layer in (pcbnew.F_CrtYd,pcbnew.B_CrtYd):
                ca=a.GetCourtyard(layer); cb=b.GetCourtyard(layer)
                if ca.OutlineCount() and cb.OutlineCount() and ca.Collide(cb,0): overlaps.append({'references':sorted([a.GetReference(),b.GetReference()]),'layer':board.GetLayerName(layer)})
            la,ba=bodies[a.GetReference()]; lb,bb=bodies[b.GetReference()]
            hit=intersections(ba,bb) if la==lb else None
            if hit: body_overlaps.append({'references':sorted([a.GetReference(),b.GetReference()]),'layer':board.GetLayerName(la),'bboxOverlapMm':hit,'interpretation':'Conservative Fab graphic bounds: inspect actual outlines; this is not a waived placement error.'})
    assert before_pads==pad_fingerprint(board),'Pad/copper/mask/paste identity changed; do not save'
    assert before_copper==copper_fingerprint(board),'Routed copper changed; do not save'
    if sha(BOARD_PATH)!=before_hash: raise RuntimeError('Routing board changed while preparing: rerun on a stable snapshot')
    report={'mode':'APPLIED' if args.apply else 'READ_ONLY_PLAN','board':str(BOARD_PATH.relative_to(ROOT)),'inputSha256':before_hash,'footprints':records,'padIdentityGeometryAndLayerSetsUnchanged':True,'routedCopperUnchanged':True,'textUpdates':text_updates,'courtyardOverlaps':overlaps,'fabBoundingBoxOverlaps':body_overlaps,'library':'pcb-snapshot.pretty','tableUri':'${KIPRJMOD}/../pcb-snapshot.pretty','limitations':['No source copper, masks or paste replace the reviewed native pad geometry.','Four contact footprint containers remain F.Cu as in the converter; their B.Cu lands and mirrored B.Fab/B.CrtYd source geometry are preserved.','Courtyard and Fab overlaps are reported for correction, never suppressed.','Final native DRC after application is required; footprints are unique per reference to avoid MPN geometry conflation.']}
    if args.apply:
        LIBRARY_PATH.mkdir(exist_ok=True)
        # KiCad 10's convenience wrapper guesses a plugin from library contents;
        # a new empty .pretty directory can resolve to no plugin. Select the
        # native KiCad writer explicitly for the new snapshot library.
        footprint_writer=pcbnew.PCB_IO_MGR.FindPlugin(pcbnew.PCB_IO_MGR.KICAD_SEXP)
        if footprint_writer is None: raise RuntimeError('Native KiCad footprint writer unavailable')
        for f in native:
            snapshot=pcbnew.FOOTPRINT(f)
            snapshot.SetParent(board)
            snapshot.SetOrientationDegrees(0)
            snapshot.SetPosition(pcbnew.VECTOR2I(0,0))
            snapshot.SetReference('REF**')
            for pad in snapshot.Pads(): pad.SetNetCode(0)
            footprint_writer.FootprintSave(str(LIBRARY_PATH),snapshot)
            saved_path=LIBRARY_PATH/('A03_'+f.GetReference()+'.kicad_mod')
            if not saved_path.is_file(): raise RuntimeError(f'Cannot save snapshot {f.GetReference()}')
        table_path=ROOT/'output/fp-lib-table'
        table=table_path.read_text()
        entry='  (lib (name "AURA_PCB")(type "KiCad")(uri "${KIPRJMOD}/../pcb-snapshot.pretty")(options "")(descr "AURA A03 exact native pad snapshots with restored manufacturer Fab and courtyards"))'
        if '(name "AURA_PCB")' in table:
            table=re.sub(r'\s*\(lib \(name "AURA_PCB"\).*?\)\)(?=\s)', '\n'+entry, table)
        else:
            table=table.rstrip()[:-1]+'\n'+entry+'\n)\n'
        table_path.write_text(table)
        if sha(BOARD_PATH)!=before_hash: raise RuntimeError('Board changed before save; do not overwrite routing')
        pcbnew.SaveBoard(str(BOARD_PATH),board)
        reloaded=pcbnew.LoadBoard(str(BOARD_PATH))
        assert before_pads==pad_fingerprint(reloaded),'Saved pad fingerprint changed'
        assert before_copper==copper_fingerprint(reloaded),'Saved copper fingerprint changed'
        report['outputSha256']=sha(BOARD_PATH)
    report_path=ROOT/('output/native-footprint-library-restoration.json' if args.apply else 'output/native-footprint-library-plan.json')
    report_path.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'mode':report['mode'],'footprints':len(records),'restoredShapes':sum(r['restoredGraphicShapes'] for r in records),'courtyardOverlaps':overlaps,'fabBoundingBoxOverlaps':body_overlaps,'textUpdates':text_updates,'report':str(report_path.relative_to(ROOT))},indent=2))

if __name__=='__main__':
    try: main()
    except Exception:
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)
