import fs from 'node:fs';
import path from 'node:path';

// Narrow source-level fallback for the MCP batch label orientation/field defect.
// No symbol pins, component positions, NC points, wire endpoints or net names change.
function parse(source) {
  const tokens = source.match(/\(|\)|"(?:\\.|[^"\\])*"|[^\s()]+/g);
  let i = 0;
  function take() {
    const raw = tokens[i++];
    if (raw === '(') {
      const node = [];
      while (tokens[i] !== ')') node.push(take());
      i++;
      return node;
    }
    return {raw, value: raw.startsWith('"') ? JSON.parse(raw) : raw};
  }
  return take();
}
const atom = (value, quoted = false) => ({value: String(value), raw: quoted ? JSON.stringify(String(value)) : String(value)});
const tag = n => Array.isArray(n) ? n[0]?.value : undefined;
const children = (n, key) => n.filter(x => tag(x) === key);
const child = (n, key) => children(n, key)[0];
const val = (n, i = 1) => n?.[i]?.value;
const num = (n, i = 1) => Number(val(n, i));
const node = (key, ...args) => [atom(key), ...args.map(a => Array.isArray(a) ? a : atom(a))];
function emit(n, depth = 0) {
  if (!Array.isArray(n)) return n.raw;
  if (!n.some(Array.isArray)) return '(' + n.map(x => x.raw).join(' ') + ')';
  let out = '(';
  for (const c of n) out += Array.isArray(c) ? '\n' + '  '.repeat(depth + 1) + emit(c, depth + 1) : (out === '(' ? '' : ' ') + c.raw;
  return out + '\n' + '  '.repeat(depth) + ')';
}
function setChild(n, key, replacement) {
  const i = n.findIndex(x => tag(x) === key);
  if (i < 0) n.push(replacement); else n[i] = replacement;
}
function field(symbol, key, value, x, y, hidden, justify = 'center') {
  const previous = children(symbol, 'property').find(p => val(p) === key);
  const effects = node('effects', node('font', node('size', '1.27', '1.27')));
  if (hidden) effects.push(node('hide', 'yes'));
  if (justify !== 'center') effects.push(node('justify', justify));
  const p = [atom('property'), atom(key, true), atom(value, true), node('at', x.toFixed(6), y.toFixed(6), 0), effects];
  if (previous) symbol[symbol.indexOf(previous)] = p; else symbol.push(p);
}
function invariant(root) {
  const items = [];
  for (const s of children(root, 'symbol')) items.push(['symbol', val(child(s, 'uuid')), child(s, 'at').slice(1).map(a => Number(a.value)), val(child(s, 'lib_id'))]);
  for (const w of children(root, 'wire')) items.push(['wire', val(child(w, 'uuid')), children(child(w, 'pts'), 'xy').map(p => p.slice(1).map(a => Number(a.value)))]);
  for (const n of children(root, 'no_connect')) items.push(['nc', val(child(n, 'uuid')), child(n, 'at').slice(1).map(a => Number(a.value))]);
  const labels = children(root, 'global_label').map(l => [val(l), num(child(l, 'at')), num(child(l, 'at'), 2)]);
  items.push(['labelAnchors', [...new Set(labels.map(JSON.stringify))].sort()]);
  return JSON.stringify(items);
}
const manifest = JSON.parse(fs.readFileSync('output/design-manifest.json', 'utf8'));
const titles = {radio:'Radio and programming',audio:'Audio and physical privacy',storage:'Offline flash storage',charging:'Charging and thermal permission',controls:'System power and controls'};
const contacts = new Set(['AURA_DOCK_PADS','AURA_BATTERY_PADS','AURA_SWD_PADS','AURA_LRA_PADS']);
function normalizeContactDatasheet(s) {
  const name=val(s).split(':').at(-1);
  if (!contacts.has(name)) return;
  const p=children(s,'property').find(p=>val(p)==='Datasheet');
  // The 20241209 MCP library treats ~ as empty; the 20260101 schematic treats it literally.
  // KiCad 10's native sym upgrade confirms empty string is the canonical representation.
  if (val(p,2)==='~') p[2]=atom('',true);
}
const report = [];
for (const [sheet, title] of Object.entries(titles)) {
  const filename = path.resolve(`output/a03-${sheet}.kicad_sch`);
  const root = parse(fs.readFileSync(filename, 'utf8'));
  const before = invariant(root);
  const symbols = children(root, 'symbol');
  const libraries = children(child(root, 'lib_symbols'), 'symbol');
  libraries.forEach(normalizeContactDatasheet);
  const endpoints = [];
  for (const s of symbols) {
    const ref = val(children(s,'property').find(p => val(p) === 'Reference'), 2);
    const at = child(s,'at');
    const cx = num(at), cy = num(at,2), rotation = num(at,3) || 0;
    const lib = libraries.find(l => val(l) === val(child(s,'lib_id')));
    const rad = rotation * Math.PI / 180;
    for (const sub of children(lib,'symbol')) for (const pin of children(sub,'pin')) {
      const pa = child(pin,'at'), lx = num(pa), ly = num(pa,2);
      endpoints.push({x:cx+lx*Math.cos(rad)+ly*Math.sin(rad),y:cy-lx*Math.sin(rad)-ly*Math.cos(rad),cx,cy,ref,outAngle:(num(pa,3)+rotation+180)%360});
    }
    if (ref.startsWith('#')) {
      field(s,'Reference',ref,cx,cy,true); field(s,'Value','PWR_FLAG',cx,cy,true);
      continue;
    }
    const part = manifest.parts.find(p => p.ref === ref);
    if (!part) throw Error(`Unexpected reference ${ref}`);
    field(s,'MPN',part.mpn,cx,cy,true);
    field(s,'Function',part.value,cx,cy,true);
    const display = ref.startsWith('R') || ref.startsWith('C') ? part.value : part.mpn;
    if (/^[RC]\d+$/.test(ref)) {
      field(s,'Reference',ref,cx+5.08,cy-1.27,false,'left');
      field(s,'Value',display,cx+5.08,cy+1.27,false,'left');
    } else if (ref === 'U1') {
      field(s,'Reference',ref,45.72,34.29,false,'left');
      field(s,'Value',display,45.72,38.10,false,'left');
    } else {
      const ys = endpoints.filter(p=>p.ref===ref).map(p=>p.y);
      field(s,'Reference',ref,cx,Math.min(...ys)-6.35,false);
      field(s,'Value',display,cx,Math.max(...ys)+6.35,false);
    }
  }
  let oriented = 0;
  const unique = new Set();
  for (const label of [...children(root,'global_label')]) {
    const at = child(label,'at'), x = num(at), y = num(at,2);
    const key = [val(label),x,y].join('|');
    if (unique.has(key)) { root.splice(root.indexOf(label),1); continue; }
    unique.add(key);
    const match = endpoints.find(p=>Math.abs(p.x-x)<1e-5 && Math.abs(p.y-y)<1e-5);
    if (!match) throw Error(`Label ${val(label)} is not on a verified pin endpoint`);
    const dx=x-match.cx, dy=y-match.cy;
    let angle;
    if (/^[RC]\d+$/.test(match.ref) && Math.abs(dy)>Math.abs(dx)) angle=dy<0?180:0;
    else angle=match.outAngle;
    at[3]=atom(angle);
    const effects = child(label,'effects');
    setChild(effects,'justify',node('justify',angle===0||angle===90?'left':'right'));
    oriented++;
  }
  const tb=[atom('title_block'),[atom('title'),atom('AURA / '+title,true)],[atom('date'),atom('2026-09-08',true)],[atom('rev'),atom('EVT-A03',true)],[atom('company'),atom('AURA product engineering',true)]];
  setChild(root,'title_block',tb);
  if (invariant(root)!==before) throw Error(`Electrical geometry changed in ${sheet}`);
  fs.writeFileSync(filename,emit(root)+'\n');
  report.push({sheet,orientedLabels:oriented,electricalGeometry:'UNCHANGED',metadataReferences:symbols.filter(s=>!val(children(s,'property').find(p=>val(p)==='Reference'),2).startsWith('#')).length});
}
const libraryPath='library/AuraA03.kicad_sym';
const library=parse(fs.readFileSync(libraryPath,'utf8'));
children(library,'symbol').forEach(normalizeContactDatasheet);
fs.writeFileSync(libraryPath,emit(library)+'\n');
const rootPath='output/aura-a03-electrical.kicad_sch';
const top=parse(fs.readFileSync(rootPath,'utf8'));
setChild(top,'title_block',[atom('title_block'),[atom('title'),atom('AURA / Native electrical design',true)],[atom('date'),atom('2026-09-08',true)],[atom('rev'),atom('EVT-A03',true)],[atom('company'),atom('AURA product engineering',true)]]);
fs.writeFileSync(rootPath,emit(top)+'\n');
for (const [file,from,to] of [
  ['output/sym-lib-table','F:/circuit/hardware/library/AuraA03.kicad_sym','${KIPRJMOD}/../library/AuraA03.kicad_sym'],
  ['output/fp-lib-table','F:/circuit/hardware/library.pretty','${KIPRJMOD}/../library.pretty']
]) fs.writeFileSync(file,fs.readFileSync(file,'utf8').replace(from,to));
fs.writeFileSync('output/native-schematic-format-checks.json',JSON.stringify(report,null,2)+'\n');
console.log(report);
