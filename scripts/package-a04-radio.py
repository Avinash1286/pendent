import hashlib, json, subprocess, zipfile
from pathlib import Path

def require(condition, message):
    if not condition: raise RuntimeError(message)

ROOT = Path(__file__).resolve().parents[1]
TAG = 'a04-radio-dk-dev'
OUT = ROOT / '.tools/a04-radio/releases' / TAG
OUT.mkdir(parents=True, exist_ok=True)
commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
require(not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT), 'Commit final sources first')
report_path = ROOT/'firmware/a04/radio/verification/arm-resources.json'
report = json.loads(report_path.read_text())
require(report['status'] == 'ARM_cross_compiled_not_executed' and not report['hardware_tested'], 'Unexpected build scope')
memory = report['memory_regions']
def sha(data): return hashlib.sha256(data).hexdigest()
for relative, digest in report['source_sha256'].items():
    require(sha((ROOT/relative).read_bytes()) == digest, 'Source changed: '+relative)
for relative, digest in report['generated_sha256'].items():
    require(sha((ROOT/relative).read_bytes()) == digest, 'Build changed: '+relative)
base = f'https://github.com/Avinash1286/pendent/blob/{commit}/'
readme = f'''# AURA A04 radio DK development checkpoint

Source commit: `{commit}`. Target: `nrf52840dk/nrf52840` with the external
microphone/NAND fixture. This is not A03 or A04 wearable firmware.

The image was cross-compiled, not flashed or physically executed. There is no
physical SMP, audio, battery, radio or wear qualification. Android still needs
the matching ASC1 proof exchange and trusted enrollment/UI integration.

- [Application, UART commands and limits]({base}firmware/a04/radio/README.md)
- [Fixture wiring]({base}firmware/a04/bench/WIRING.md)
- [Exact authentication contract]({base}docs/a04/session-auth-v1.md)
- [Source-bound ARM report]({base}firmware/a04/radio/verification/arm-resources.json)
- [Route to a physical wearable]({base}docs/research/aura-first-wearable.md)

Static allocations: {memory['FLASH']['used_bytes']:,} bytes FLASH; {memory['RAM']['used_bytes']:,} bytes RAM; {memory['RAM']['remaining_bytes']:,} bytes RAM
unallocated. Runtime stack headroom, timing and power remain unmeasured.
The 48 KiB storage/codec stack and 4 KiB reader stack are retained.

Local reproduction: `pwsh -NoProfile -File firmware/a04/radio/build.ps1 -Mode arm -Jobs 2`.
No GitHub Actions were used. The image reserves 32 KiB internal NOR at
`0xf8000` for Bluetooth settings, with no signed bootloader/update slots.
Owner context is loaded through trusted local UART after reset, not over BLE.
No remote key provisioning, recording, deletion or audio-release API is exposed.

Verify the five release assets with `SHA256SUMS` and `manifest.json`. The
firmware ZIP contains ELF/BIN/HEX/map, resolved configuration and device tree;
the evidence ZIP contains the build/host reports and retained failed attempts.
The tests exercise software boundaries and are not physical device results.
'''
readme_path = OUT/'README-download.md'
readme_path.write_text(readme, encoding='utf-8', newline='\n')
artifacts = {}
with zipfile.ZipFile(OUT/'aura-a04-radio-dk-firmware.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for name in ('zephyr.elf','zephyr.bin','zephyr.hex','zephyr.map','.config','zephyr.dts'):
        relative = '.tools/a04-radio/arm/zephyr/'+name
        data = (ROOT/relative).read_bytes()
        require(sha(data) == report['generated_sha256'][relative], 'Package input changed: '+relative)
        member = 'firmware/'+('zephyr.config' if name=='.config' else name)
        z.writestr(member, data)
        artifacts[member] = {'bytes': len(data), 'sha256': sha(data)}
    z.writestr('README-download.md',readme)
    z.writestr('SOURCE-COMMIT.txt',commit+'\n')
    notices = [ROOT/'LICENSE',ROOT/'firmware/THIRD_PARTY_NOTICES.md',
               ROOT/'firmware/a04/THIRD_PARTY_NOTICES.md',
               ROOT/'firmware/a04/licenses/Opus-COPYING.txt']
    notices += sorted((ROOT/'firmware/licenses').glob('*.txt'))
    for path in notices:
        member = path.relative_to(ROOT).as_posix()
        data = path.read_bytes()
        z.writestr(member,data)
        artifacts[member] = {'bytes':len(data),'sha256':sha(data)}
with zipfile.ZipFile(OUT/'aura-a04-radio-dk-evidence.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for path in sorted((ROOT/'firmware/a04/radio/verification').rglob('*')):
        if path.is_file(): z.write(path,path.relative_to(ROOT).as_posix())
    for relative in ('firmware/a04/radio/tests/gatt-host-tests.json',
                     'firmware/a04/radio/tests/gatt-host-tests.txt',
                     'docs/a04/session-auth-v1.md'):
        z.write(ROOT/relative,relative)
    z.writestr('SOURCE-COMMIT.txt',commit+'\n')
names = ['README-download.md','aura-a04-radio-dk-firmware.zip','aura-a04-radio-dk-evidence.zip']
assets = {name: {'bytes': (OUT/name).stat().st_size,'sha256': sha((OUT/name).read_bytes())} for name in names}
manifest = {'schema':1,'tag':TAG,'source_commit':commit,'scope':report['status'],
            'target':report['target'],'physical_hardware_tested':False,
            'memory_regions':report['memory_regions'],'firmware_members':artifacts,
            'assets':assets}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8',newline='\n')
names.append('manifest.json')
(OUT/'SHA256SUMS').write_text(''.join(sha((OUT/name).read_bytes())+'  '+name+'\n' for name in names),encoding='utf-8',newline='\n')
for name in names:
    if name.endswith('.zip'):
        with zipfile.ZipFile(OUT/name) as z: require(z.testzip() is None, 'ZIP validation failed: '+name)
print(json.dumps({'directory':str(OUT),'source_commit':commit,'assets':names+['SHA256SUMS']},indent=2))
