"""Check actual ELF/HEX/BIN identity, MCU target, flash bounds and safe build gates."""
from pathlib import Path
import hashlib
import json
from elftools.elf.elffile import ELFFile
from intelhex import IntelHex

root = Path(__file__).resolve().parents[1]
release = root / "release"
manifest = json.loads((release / "manifest.json").read_text())
for name, info in manifest["files"].items():
    data = (release / name).read_bytes()
    assert len(data) == info["bytes"], name
    assert hashlib.sha256(data).hexdigest() == info["sha256"], name
sources = sorted([*root.glob('src/*.c'), *root.glob('include/*.h'), *root.glob('boards/**/*'), root / 'prj.conf', root / 'Kconfig', root / 'CMakeLists.txt'])
digest = hashlib.sha256()
for path in sources:
    if path.is_file():
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes().replace(b'\r\n', b'\n'))
assert digest.hexdigest() == manifest["source_sha256"], "Source changed after release build"
with (release / "aura-a03.elf").open("rb") as stream:
    elf = ELFFile(stream)
    assert elf.header["e_machine"] == "EM_ARM"
    assert elf.elfclass == 32
    assert elf.header["e_entry"] < 0xF8000
image = IntelHex(str(release / "aura-a03.hex"))
assert image.minaddr() == 0
assert image.maxaddr() < 0xF8000, "Image overlaps persistent MCU settings"
assert bytes(image.tobinarray()) == (release / "aura-a03.bin").read_bytes()
config = (release / "build.config").read_text()
for option in ["CONFIG_BT_SMP_SC_ONLY=y", "CONFIG_BT_SMP_APP_PAIRING_ACCEPT=y", "CONFIG_CLOCK_CONTROL_NRF_K32SRC_RC=y", "CONFIG_BT_L2CAP_TX_MTU=247", "CONFIG_USE_DT_CODE_PARTITION=y"]:
    assert option in config, option
for option in ["CONFIG_AURA_CHARGE_QUALIFIED", "CONFIG_AURA_HAPTIC_QUALIFIED"]:
    assert f"# {option} is not set" in config, option
print("PASS release hashes and source identity")
print("PASS ARM Cortex-M image and ELF/HEX/BIN consistency")
print("PASS application ends before persistent MCU NVS")
print("PASS Secure Connections, physical pairing callback, LFRC and MTU configuration")
print("PASS distributed charging and haptic qualification gates disabled")
