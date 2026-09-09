#!/usr/bin/env python3
"""C fixture -> independent Python expectation -> Kotlin JVM -> FFmpeg checks.

Run --prepare-only before Gradle :core:verifyCore, then --finish-only after it;
or provide --gradle/--java-jar to run the complete pipeline. No device is used.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

CORE = Path(__file__).resolve().parents[1]
ROOT = CORE.parents[2]
sys.path.insert(0, str(ROOT / "companion/src"))
from aura_companion.protocol_v2 import read_archive, Receipt, OPEN
from aura_companion.archive_import import _write_ogg


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            result.update(chunk)
    return result.hexdigest()


def transfer_source_paths():
    paths = [ROOT / name for name in (
        "firmware/a04/verification/transfer-wire-golden.tsv",
        "docs/a04/transfer-wire-v1.md",
        "firmware/a04/src/aura_transfer.c", "firmware/a04/include/aura_transfer.h",
        "firmware/a04/src/aura_storage.c", "firmware/a04/include/aura_storage.h",
    )]
    assert all(path.is_file() for path in paths), "Actual C transfer goldens and their contract/source inputs are required"
    return paths


def transfer_bindings():
    return {path.relative_to(ROOT).as_posix(): digest(path) for path in transfer_source_paths()}


def fixture_rows():
    fixture_dir = ROOT / "firmware/a04/fixtures"
    result = []
    for file in sorted(fixture_dir.glob("*.aura")):
        archive = read_archive(file, allow_interrupted=True)
        receipt_file = file.with_suffix(".receipt")
        if not receipt_file.exists():
            receipt_file = file.with_suffix(".ack3")
        physical = receipt_file.read_bytes() if receipt_file.exists() else None
        if physical is not None:
            Receipt.parse(physical)
        result.append((file, archive, physical))
    assert len(result) >= 10, "Actual C-generated source fixtures required"
    return result


def prepare(build):
    build.mkdir(parents=True, exist_ok=True)
    rows = []
    for file, archive, physical in fixture_rows():
        rows.append("\t".join((file.stem, str(file.resolve()), digest(file), archive.receipt.encode().hex(),
            physical.hex() if physical else "-", str(archive.source_samples), str(archive.termination.status),
            str(archive.original_source_samples) if archive.original_source_samples is not None else "-",
            "accept" if archive.seal is not None and archive.discarded_tail_bytes == 0 else "reject")))
    index = build / "fixture-index.tsv"
    index.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"Prepared {len(rows)} actual C fixture expectations: {index}")
    return index


def finish(build, ffmpeg, transfer_before):
    assert transfer_bindings() == transfer_before, "C transfer inputs changed after JVM fixture preparation"
    output = build / "jvm"
    lines = (output / "results.tsv").read_text(encoding="utf-8").splitlines()
    results = {fields[0]: fields for fields in (line.split("\t") for line in lines[1:])}
    evidence = []
    for file, archive, physical in fixture_rows():
        if archive.seal is None or archive.discarded_tail_bytes:
            continue
        fields = results.pop(file.stem)
        assert fields[1] == digest(file)
        assert fields[2] == archive.receipt.encode().hex()
        assert (output / f"{file.stem}.ack3").read_bytes() == archive.receipt.encode()
        expected_physical = str(Receipt.parse(physical).status) if physical else "-"
        assert fields[3] == expected_physical
        assert int(fields[4]) == archive.source_samples
        item = {"fixture": file.relative_to(ROOT).as_posix(), "source_sha256": digest(file),
                "archive_ack3": archive.receipt.encode().hex(), "physical_status": expected_physical,
                "status": archive.status, "source_samples": archive.source_samples,
                "original_source_samples": archive.original_source_samples,
                "derived_export_seal": physical is not None and Receipt.parse(physical).status == OPEN}
        if int(fields[5]):
            ogg = output / f"{file.stem}.ogg"
            comparison = build / f"{file.stem}-python.ogg"
            # Write exclusive reference output without deleting a prior artifact.
            if comparison.exists():
                comparison = build / f"{file.stem}-python-{digest(ogg)[:12]}.ogg"
            if not comparison.exists():
                _write_ogg(archive, comparison)
            assert ogg.read_bytes() == comparison.read_bytes(), "Kotlin Ogg differs from independent Python mapping"
            completed = subprocess.run([ffmpeg, "-v", "error", "-i", str(ogg), "-f", "s16le", "-acodec",
                "pcm_s16le", "-ar", "16000", "-ac", "1", "pipe:1"], capture_output=True, timeout=60, check=True)
            assert len(completed.stdout) == archive.source_samples * 2, "Independent decoder sample count differs"
            item.update(ogg_sha256=digest(ogg), ogg_bytes=ogg.stat().st_size,
                        decoded_samples=len(completed.stdout) // 2,
                        decoded_pcm_sha256=hashlib.sha256(completed.stdout).hexdigest(), python_ogg_exact=True)
        evidence.append(item)
    assert not results, "Unexpected JVM fixture output"
    source_paths = list((CORE / "src").rglob("*.kt")) + [CORE / "build.gradle.kts", CORE / "README.md", Path(__file__)]
    source_paths += [ROOT / "firmware/a04/ARCHIVE.md", ROOT / "companion/src/aura_companion/protocol_v2.py",
                     ROOT / "companion/src/aura_companion/archive_import.py"]
    source_paths += transfer_source_paths()
    assert transfer_bindings() == transfer_before, "C transfer inputs changed during verification"
    sources = {path.relative_to(ROOT).as_posix(): digest(path) for path in sorted(source_paths)}
    assert all(sources[path] == expected for path, expected in transfer_before.items()), "Report source hashes differ from tested C transfer inputs"
    assert transfer_bindings() == transfer_before, "C transfer inputs changed while binding report sources"
    report = {"schema": "aura-kotlin-core-verification-v1", "physical_hardware_tested": False,
              "android_decoder_tested": False, "jvm_fixture_count": len(evidence),
              "transfer_wire_golden_sha256": transfer_before["firmware/a04/verification/transfer-wire-golden.tsv"],
              "verification": "C archive bytes and receipts, independent Python mapping, JVM parser/mux, FFmpeg PCM length, actual C transfer wire and fragments",
              "sources": sources,
              "fixtures": evidence}
    report_text = json.dumps(report, indent=2) + "\n"
    (build / "verification.json").write_text(report_text, encoding="utf-8")
    published = CORE / "verification"
    published.mkdir(exist_ok=True)
    (published / "kotlin-core.json").write_text(report_text, encoding="utf-8")
    if (build / "jvm-host.txt").exists():
        (published / "jvm-host.txt").write_bytes((build / "jvm-host.txt").read_bytes())
    print(f"PASS {len(evidence)} C/Python/JVM fixtures; actual FFmpeg decode; report {build / 'verification.json'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--finish-only", action="store_true")
    parser.add_argument("--gradle", type=Path)
    parser.add_argument("--java-jar", type=Path)
    parser.add_argument("--java", default="java")
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg"))
    args = parser.parse_args()
    assert not (args.prepare_only and args.finish_only)
    build = CORE / "build/verification"
    baseline = build / "transfer-inputs.json"
    if args.finish_only:
        transfer_before = json.loads(baseline.read_text(encoding="utf-8"))
        assert transfer_before == transfer_bindings(), "C transfer inputs differ from prepared JVM inputs"
    else:
        transfer_before = transfer_bindings()
    index = prepare(build) if not args.finish_only else build / "fixture-index.tsv"
    if not args.finish_only:
        baseline.write_text(json.dumps(transfer_before, indent=2) + "\n", encoding="utf-8")
    if args.prepare_only:
        return
    if not args.finish_only:
        if args.java_jar:
            command = [args.java, "-jar", str(args.java_jar.resolve()), str(index), str(build / "jvm")]
        elif args.gradle:
            command = [str(args.gradle.resolve()), ":core:check", f"-PauraFixtureIndex={index}",
                       f"-PauraResultDirectory={build / 'jvm'}", "--console=plain"]
        else:
            parser.error("Supply --gradle/--java-jar, or use --prepare-only then --finish-only")
        completed = subprocess.run(command, cwd=CORE.parent, capture_output=True, text=True, timeout=600)
        (build / "jvm-host.txt").write_text(completed.stdout + completed.stderr, encoding="utf-8")
        print(completed.stdout, end="")
        print(completed.stderr, end="", file=sys.stderr)
        completed.check_returncode()
        assert transfer_bindings() == transfer_before, "C transfer inputs changed while JVM verification ran"
    assert args.ffmpeg, "Actual FFmpeg required for independent decoder verification"
    finish(build, args.ffmpeg, transfer_before)


if __name__ == "__main__":
    main()
