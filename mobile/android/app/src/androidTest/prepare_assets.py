"""Copy exact public C test fixtures into the instrumentation APK, with origins.

These synthetic reference captures are not recordings from physical hardware.
"""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / "companion/src"))
from aura_companion.protocol_v2 import Receipt, read_archive

source = ROOT / "firmware/a04/fixtures"
destination = HERE / "assets/fixtures"
destination.mkdir(parents=True, exist_ok=True)
entries = []
for stem in ("journal-0", "journal-2", "recorder-1", "capture-20ms-open"):
    archive_path = source / f"{stem}.aura"
    data = archive_path.read_bytes()
    archive = read_archive(archive_path, allow_interrupted=True)
    (destination / archive_path.name).write_bytes(data)
    entry = {"name": stem, "asset": archive_path.name,
             "origin": archive_path.relative_to(ROOT).as_posix(),
             "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
             "complete": archive.seal is not None and archive.discarded_tail_bytes == 0,
             "source_samples": archive.source_samples,
             "original_source_samples": archive.original_source_samples,
             "archive_status": archive.termination.status,
             "archive_receipt": archive.receipt.encode().hex(),
             "device_id": archive.capture.device_id.hex(), "capture_id": archive.capture.capture_id.hex()}
    receipt_path = source / f"{stem}.receipt"
    if entry["complete"] and receipt_path.exists():
        receipt = receipt_path.read_bytes()
        receipt_asset = f"{stem}.physical.ack3"
        (destination / receipt_asset).write_bytes(receipt)
        entry.update(physical_asset=receipt_asset, physical_origin=receipt_path.relative_to(ROOT).as_posix(),
                     physical_sha256=hashlib.sha256(receipt).hexdigest(), physical_status=Receipt.parse(receipt).status)
    entries.append(entry)
index = {"schema": "aura-android-instrumentation-fixtures-v1", "physical_hardware_recordings": False,
         "fixtures": entries}
(destination / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
print(f"Prepared {len(entries)} exact C archive assets and their available physical receipt fixtures")
