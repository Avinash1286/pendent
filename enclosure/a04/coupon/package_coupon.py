"""Create a deterministic convenience archive after export verification/render QA."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
manifest = json.loads((ROOT/"coupon-manifest.json").read_text())
audit = json.loads((ROOT/"coupon-mesh-audit.json").read_text())
assert audit["specimen_count"] == 9 and audit["physical_qualification"] is False
assert audit["manifest_sha256"] == hashlib.sha256((ROOT/"coupon-manifest.json").read_bytes()).hexdigest()
assert audit["verifier_sha256"] == hashlib.sha256((ROOT/"verify_coupon.py").read_bytes()).hexdigest()
files = [p["file"] for p in manifest["parts"]] + [
    "README.md", "measurement-template.csv", "build_coupon.py", "verify_coupon.py", "render_coupon.py",
    "package_coupon.py", "coupon-manifest.json", "coupon-mesh-audit.json", "a04-coupon-layout.blend", "coupon-overview.png",
]
assert len(set(files)) == len(files)
for part in manifest["parts"]:
    assert hashlib.sha256((ROOT/part["file"]).read_bytes()).hexdigest() == part["sha256"]
for name in files:
    path = ROOT/name
    assert path.is_file() and not path.is_symlink() and path.resolve().parent == ROOT.resolve()
archive = ROOT/"a04-process-coupon.zip"
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
    for name in sorted(files):
        info = zipfile.ZipInfo("a04-process-coupon/"+name, date_time=(2026, 9, 9, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        output.writestr(info, (ROOT/name).read_bytes())
with zipfile.ZipFile(archive) as check:
    assert check.testzip() is None
    assert set(check.namelist()) == {"a04-process-coupon/"+n for n in files}
    for name in files:
        assert check.read("a04-process-coupon/"+name) == (ROOT/name).read_bytes()
result = {"archive": archive.name, "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
          "bytes": archive.stat().st_size, "file_count": len(files), "physical_qualification": False,
          "purpose": "Unpowered process coupon only; not complete pendant parts", "reopened_crc_and_bytes": "pass"}
(ROOT/"coupon-package.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
print(json.dumps(result))
