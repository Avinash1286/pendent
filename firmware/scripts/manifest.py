"""Record exact release hashes and source identity after a successful ARM build."""
from pathlib import Path
import hashlib
import json
root = Path(__file__).resolve().parents[1]
files = [p for p in (root / 'release').iterdir() if p.is_file() and p.name != 'manifest.json']
sources = sorted([*root.glob('src/*.c'), *root.glob('include/*.h'), *root.glob('boards/**/*'), root / 'prj.conf', root / 'Kconfig', root / 'CMakeLists.txt'])
digest = hashlib.sha256()
for p in sources:
    if p.is_file():
        digest.update(p.relative_to(root).as_posix().encode())
        digest.update(p.read_bytes().replace(b'\r\n', b'\n'))
manifest = {'revision': 'A03', 'status': 'ARM-built engineering firmware; not bench validated',
            'zephyr': 'v4.2.0', 'zephyr_commit': '413b789deb391d3a37d06b463288a5fe765ee57e',
            'sdk': '0.17.2', 'target': 'aura_a03/nrf52840',
            'charging_enabled': False, 'haptics_enabled': False,
            'source_sha256': digest.hexdigest(),
            'files': {p.name: {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(files)}}
(root / 'release/manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
