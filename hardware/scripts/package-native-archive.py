"""Build a deterministic, verified archive from engineering-package-manifest.json.

Run with standard Python from any directory after the engineering manifest is final.
Only the prototype ZIP and its separate checksum report are written; no CAD is edited.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'output/engineering-package-manifest.json'
ARCHIVE = 'output/aura-a03-prototype-fabrication.zip'
REPORT = 'output/aura-a03-prototype-fabrication-manifest.json'
STATUS = 'CONNECTED_PROTOTYPE_FABRICATION_REVIEW'
BOARD = 'native/aura-a03.kicad_pcb'
CHECKS = 'native/review/manufacturing-checks.json'
ZIP_DATE = (1980, 1, 1, 0, 0, 0)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def is_link(path):
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    # Windows junctions are reparse points; Path.is_junction needs Python 3.12.
    return stat.S_ISLNK(metadata.st_mode) or bool(getattr(metadata, 'st_file_attributes', 0) & 0x400)


def safe_path(name, must_exist=True):
    require(isinstance(name, str) and name, 'Empty or non-string package path')
    require(not any(c in name for c in ('\\', ':', '\x00', '\r', '\n')), f'Unsafe path: {name!r}')
    pure = PurePosixPath(name)
    require(not pure.is_absolute() and pure.as_posix() == name
            and all(p not in ('', '.', '..') for p in name.split('/')), f'Noncanonical path: {name}')
    candidate = ROOT
    for part in pure.parts:
        candidate /= part
        require(not is_link(candidate), f'Linked path: {name}')
    resolved = candidate.resolve(strict=must_exist)
    require(resolved.is_relative_to(ROOT), f'Path escapes hardware/: {name}')
    if must_exist:
        require(resolved.is_file(), f'Not a regular file: {name}')
    return resolved


def valid_hash(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-fA-F]{64}', value) is not None


def write_zip(destination, payloads):
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9, strict_timestamps=True) as archive:
        for name, data in sorted(payloads.items()):
            info = zipfile.ZipInfo(name, date_time=ZIP_DATE)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data, compresslevel=9)
    with zipfile.ZipFile(destination) as archive:
        require(archive.testzip() is None, 'Archive CRC verification failed')
        require(archive.namelist() == sorted(payloads), 'Archive entry count/order/set mismatch')
        for info in archive.infolist():
            expected = payloads[info.filename]
            require(info.date_time == ZIP_DATE and info.file_size == len(expected),
                    f'Archive metadata mismatch: {info.filename}')
            require(sha(archive.read(info)) == sha(expected), f'Archive hash mismatch: {info.filename}')


def main():
    manifest_bytes = safe_path(MANIFEST).read_bytes()
    manifest = json.loads(manifest_bytes)
    require(manifest.get('status') == STATUS, 'Engineering manifest is not a connected prototype review release')
    board_hash = manifest.get('boardSha256')
    require(valid_hash(board_hash), 'Missing/invalid boardSha256')
    board_hash = board_hash.lower()
    courtyard_count = manifest.get('assemblyCourtyardFindings')
    require(type(courtyard_count) is int and courtyard_count >= 0, 'Invalid assemblyCourtyardFindings')
    files = manifest.get('files')
    require(isinstance(files, list) and files, 'Manifest has no files')
    payloads, included, names = {}, {}, set()
    forbidden = {p.casefold() for p in (MANIFEST, ARCHIVE, REPORT)}
    for item in files:
        require(isinstance(item, dict), 'Invalid file entry')
        name = item.get('path')
        source = safe_path(name)
        require(name.casefold() not in names, f'Duplicate or case-colliding path: {name}')
        require(name.casefold() not in forbidden, f'Self-inclusion or generated output in manifest: {name}')
        require(type(item.get('bytes')) is int and item['bytes'] >= 0 and valid_hash(item.get('sha256')),
                f'Invalid file size/hash: {name}')
        data = source.read_bytes()
        require(len(data) == item['bytes'] and sha(data) == item['sha256'].lower(), f'Stale manifest file: {name}')
        names.add(name.casefold())
        included[name] = data
        payloads['hardware/' + name] = data
    required = {BOARD, CHECKS, 'native/aura-a03.kicad_pro', 'native/aura-a03.kicad_sch', 'native/README.md'}
    require(required <= included.keys(), f'Missing native package essentials: {sorted(required - included.keys())}')
    require(sha(included[BOARD]) == board_hash, 'Native board does not match boardSha256')
    checks = json.loads(included[CHECKS])
    require(checks.get('status') == STATUS and checks.get('boardSha256', '').lower() == board_hash,
            'Native manufacturing report belongs to a different board/status')
    for key in ('unconnectedItems', 'schematicParityFindings', 'ercErrors', 'ercWarnings', 'bareBoardDrcErrors'):
        require(type(checks.get(key)) is int and checks[key] == 0, f'Native check has not passed: {key}')
    require(checks.get('drcFindingsByType', {}).get('courtyards_overlap', 0) == courtyard_count,
            'Courtyard count differs from the verified native report')
    require(checks.get('assemblyApproved') is False and checks.get('physicalQualification') is False,
            'This script packages an unqualified prototype review, not an approved assembly release')
    payloads['hardware/' + MANIFEST] = manifest_bytes
    payloads['START-HERE.md'] = f'''# AURA A03 prototype fabrication package

Open **hardware/native/aura-a03.kicad_pro** in KiCad 10. The paired project,
portable libraries, manufacturing files, authored sources and audit evidence are included.

Read the [native project and manufacturing guide](hardware/native/README.md)
before using any fabrication or assembly files.

Verified native board SHA-256: `{board_hash}`.

- Unconnected items: 0.
- Schematic/PCB parity findings: 0.
- ERC errors and warnings: 0.
- Bare-board DRC errors: 0.
- Unsuppressed assembly courtyard findings: **{courtyard_count}**.

**Assembly review hold:** the courtyard findings remain visible. Assembly approval
and physical qualification are false. These are connected prototype fabrication
and review files; they do not establish a qualified assembled wearable.

The [engineering manifest](hardware/output/engineering-package-manifest.json)
binds every included source file to its byte size and SHA-256. The external archive
checksum report is intentionally not included inside the archive it describes.

Original source and project documentation: [Avinash1286/pendent](https://github.com/Avinash1286/pendent).
'''.encode('utf-8')
    license_path = ROOT.parent / 'LICENSE'
    require(not is_link(license_path), 'Linked root LICENSE is not allowed')
    if license_path.exists():
        require(license_path.is_file(), 'Root LICENSE is not a regular file')
        payloads['LICENSE'] = license_path.read_bytes()
    archive_path, report_path = safe_path(ARCHIVE, False), safe_path(REPORT, False)
    require(archive_path.parent.is_dir(), 'Output directory does not exist')
    temporary = []
    try:
        with tempfile.NamedTemporaryFile(dir=archive_path.parent, prefix='.aura-package-', suffix='.zip', delete=False) as handle:
            temp_archive = Path(handle.name)
        temporary.append(temp_archive)
        write_zip(temp_archive, payloads)
        raw = temp_archive.read_bytes()
        result = {'status': STATUS, 'path': ARCHIVE, 'bytes': len(raw), 'sha256': sha(raw),
                  'fileCount': len(payloads), 'manifestFileCount': len(files), 'boardSha256': board_hash,
                  'sourceManifestSha256': sha(manifest_bytes), 'assemblyCourtyardFindings': courtyard_count,
                  'assemblyApproved': False, 'physicalQualification': False,
                  'zipDate': list(ZIP_DATE), 'compression': 'DEFLATE level 9',
                  'crcAndExactFileHashesVerified': True}
        with tempfile.NamedTemporaryFile(dir=report_path.parent, prefix='.aura-package-', suffix='.json', delete=False) as handle:
            temp_report = Path(handle.name)
            handle.write((json.dumps(result, indent=2) + '\n').encode('utf-8'))
        temporary.append(temp_report)
        require(safe_path(MANIFEST).read_bytes() == manifest_bytes, 'Engineering manifest changed during packaging')
        temp_archive.replace(archive_path)
        temp_report.replace(report_path)
        print(json.dumps(result, indent=2))
    finally:
        for path in temporary:
            path.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
