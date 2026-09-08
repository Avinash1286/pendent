import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (name) => JSON.parse(fs.readFileSync(path.join(root, name), 'utf8'));
const digest = (bytes) => crypto.createHash('sha256').update(bytes).digest('hex');
const hash = (name) => digest(fs.readFileSync(path.join(root, name)));
const report = read('native/review/manufacturing-checks.json');
const linkage = read('native/project-linkage.json');
const boardSha256 = hash('native/aura-a03.kicad_pcb');
assert.equal(report.boardSha256, boardSha256, 'Stale manufacturing report');
assert.equal(linkage.pairedBoardSha256, boardSha256, 'Stale native project linkage');
assert.equal(linkage.inputBoardSha256, hash('output/aura-a03-native-routing.kicad_pcb'));
assert.equal(linkage.status, 'PASS');
assert.equal(report.status, 'CONNECTED_PROTOTYPE_FABRICATION_REVIEW');
for (const key of ['unconnectedItems', 'schematicParityFindings', 'ercErrors', 'ercWarnings', 'bareBoardDrcErrors']) {
  assert.equal(report[key], 0, `Release gate: ${key}`);
}
for (const file of report.files) {
  const bytes = fs.readFileSync(path.join(root, 'native', file.path));
  assert.equal(bytes.length, file.bytes, `Size changed: ${file.path}`);
  assert.equal(digest(bytes), file.sha256, `Export changed: ${file.path}`);
}
const drc = read('native/review/drc.json');
const erc = read('native/review/erc.json');
assert.equal(drc.unconnected_items.length, 0);
assert.equal(drc.schematic_parity?.length ?? 0, 0);
assert.ok(drc.violations.every(v => v.type === 'courtyards_overlap'), 'Review unexpected DRC finding');
assert.equal(erc.sheets.flatMap(s => s.violations || []).length, 0);
assert.equal(report.drcFindingsByType.courtyards_overlap ?? 0, drc.violations.length);
for (const [name, expected] of [['native-smd-pad-spacing-audit.json', 'PASS'], ['native-via-aperture-audit.json', 'PASS_NO_INTERSECTIONS']]) {
  const audit = read(`native/review/${name}`);
  assert.equal(audit.inputSha256, boardSha256, `Stale audit: ${name}`);
  assert.equal(audit.status, expected);
  assert.equal(audit.boardUnchanged, true);
}
assert.equal(report.componentOriginChecks.length, 57);
assert.ok(report.componentOriginChecks.every(c => c.status === 'PASS'));

const files = new Set();
function add(name) {
  const target = path.join(root, name);
  const stat = fs.lstatSync(target);
  assert.ok(!stat.isSymbolicLink(), `Do not package symlink: ${name}`);
  if (stat.isDirectory()) {
    for (const child of fs.readdirSync(target).sort()) {
      if (child === '__pycache__' || child.startsWith('.') || child.endsWith('-backups')) continue;
      add(`${name}/${child}`);
    }
  } else {
    assert.ok(stat.isFile());
    if (/\.(?:pyc|log|kicad_prl|lck)$/.test(name)) return;
    files.add(name);
  }
}
for (const directory of ['native', 'src', 'scripts', 'firmware', 'library', 'library.pretty', 'pcb-snapshot.pretty']) add(directory);
for (const name of [
  'README.md', 'package.json', 'package-lock.json', 'requirements-native.txt',
  'sources/README.md', 'sources/jlc-4layer-08mm-stackups.json',
  'output/active-build.json', 'output/design-manifest.json', 'output/logical-netlist.json', 'output/logical-checks.json',
  'output/aura-placement.circuit.json', 'output/aura-placement.pcb.svg', 'output/placement.csv',
  'output/assembly-bom.csv', 'output/cpl-top.csv', 'output/external-bom.csv',
  'output/aura-a03-native-routing.kicad_pcb', 'output/aura-a03-native-routing.kicad_pro',
  'output/aura-a03-electrical.kicad_sch', 'output/aura-a03-electrical.kicad_pro',
  'output/aura-a03-native.net.xml', 'output/aura-a03-native-erc.json',
  'output/aura-a03-native-schematic.pdf', 'output/aura-a03-restored-final-drc.json',
  'output/fp-lib-table', 'output/sym-lib-table',
  'output/aura-a03-copper-cleanup.json', 'output/native-footprint-library-restoration.json',
  'output/native-footprint-alignment-audit.json', 'output/native-schematic-format-checks.json',
  'output/native-schematic-parity.json', 'output/native-sheetfile-layout-checks.json',
  'output/native-smd-pad-spacing-audit.json', 'output/native-via-aperture-audit.json',
  ...['radio', 'audio', 'storage', 'charging', 'controls'].map(n => `output/a03-${n}.kicad_sch`),
]) add(name);
const manifest = {
  revision: 'EVT-A03',
  createdAt: new Date().toISOString(),
  status: report.status,
  boardSha256,
  nativeProject: 'native/aura-a03.kicad_pro',
  prototypeManufacturingOutputsReleased: true,
  bareBoardExportValidated: true,
  fabricationReady: false,
  assemblyApproved: false,
  physicalQualification: false,
  assemblyCourtyardFindings: drc.violations.length,
  interpretation: 'Connected prototype fabrication data; courtyard margins require assembler review. No production, assembled-device or purchasing approval.',
  board: { widthMm: 24, heightMm: 42, radiusMm: 10, thicknessMm: 0.8, copperLayers: 4, stackup: linkage.stackup },
  logical: { references: 61, intendedNets: 43, connectedPins: 208, intentionalNcPins: 37 },
  assembly: { candidateSmtReferences: 57, customPcbFeatures: 4 },
  checks: {
    unconnectedItems: 0, schematicParityFindings: 0, ercErrors: 0, ercWarnings: 0, bareBoardDrcErrors: 0,
    ...report.additionalClearanceAudits,
  },
  historicalEvidence: 'Other output/ routing/converter snapshots are superseded; native/ is the current editable authority.',
  files: [...files].sort().map(name => {
    const bytes = fs.readFileSync(path.join(root, name));
    return { path: name, bytes: bytes.length, sha256: digest(bytes) };
  }),
};
fs.writeFileSync(path.join(root, 'output/engineering-package-manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
console.log(JSON.stringify({ status: manifest.status, boardSha256, files: manifest.files.length, assemblyCourtyardFindings: manifest.assemblyCourtyardFindings }));
