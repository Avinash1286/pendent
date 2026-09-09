"""Build/run the isolated control primitive and independently parse its media.

Evidence defaults to the ignored .tools directory. This verifies accidental
fault handling and public hash linkage, not authentication or physical NAND.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
MAX_BYTES = 49152
BODY_BYTES = 1920
BLOCK_BYTES = 64 * 2048
DOMAIN = bytes(range(1, 17))
BLOCKS = (1, 6)
EXPECTED_GROUPS = 12
EXPECTED_CASES = 712


def uint(wire, offset, size):
    return int.from_bytes(wire[offset:offset + size], "little")


def page_check(page, slot, magic, kind):
    assert len(page) == 2048
    assert page[:4] == magic and page[4:6] == bytes((1, kind))
    assert uint(page, 6, 2) == (124 if kind == 2 else 128)
    assert uint(page, 8, 2) == BLOCKS[slot] and page[10:12] == bytes((slot, 0))
    assert page[32:48] == DOMAIN
    assert uint(page, 2044, 4) == zlib.crc32(page[:2044])


def parse_block(wire, slot):
    assert len(wire) == BLOCK_BYTES
    pages = [wire[n:n + 2048] for n in range(0, len(wire), 2048)]
    assert pages[0] == pages[1] == b"\xff" * 2048
    header, commit = pages[2], pages[63]
    page_check(header, slot, b"A4CH", 1)
    page_check(commit, slot, b"A4CC", 3)
    size, generation, parent = uint(header, 12, 4), uint(header, 16, 8), uint(header, 24, 8)
    assert size <= MAX_BYTES and generation > 0 and parent == generation - 1
    count = (size + BODY_BYTES - 1) // BODY_BYTES
    assert uint(header, 80, 2) == count
    assert header[82:2044] == bytes(2044 - 82)
    assert (header[48:80] != bytes(32)) if parent else (header[48:80] == bytes(32))
    header_hash = hashlib.sha256(header).digest()
    chain = header_hash
    payload = bytearray()
    for index, page in enumerate(pages[3:3 + count]):
        page_check(page, slot, b"A4CB", 2)
        offset = index * BODY_BYTES
        take = min(BODY_BYTES, size - offset)
        assert uint(page, 12, 2) == index and uint(page, 14, 2) == take
        assert uint(page, 16, 8) == generation and uint(page, 24, 4) == offset
        assert uint(page, 28, 4) == size and page[48:80] == chain
        assert page[80:124] == bytes(44)
        assert page[124 + take:2044] == b"\xff" * (BODY_BYTES - take)
        payload.extend(page[124:124 + take])
        chain = hashlib.sha256(page).digest()
    assert all(page == b"\xff" * 2048 for page in pages[3 + count:63])
    assert commit[8:82] == header[8:82]
    assert commit[82:88] == bytes(6)
    assert commit[88:120] == header_hash and commit[120:152] == chain
    assert commit[152:2044] == bytes(2044 - 152)
    return dict(generation=generation, parent=parent, bytes=size, body_pages=count,
                parent_sha256=header[48:80].hex(), commit_sha256=hashlib.sha256(commit).hexdigest(),
                payload_sha256=hashlib.sha256(payload).hexdigest()), bytes(payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true", help="Use the existing pinned Zig compiler")
    parser.add_argument("--exe", type=Path, default=WORKSPACE / ".tools/a04-control/aura_control_test.exe")
    parser.add_argument("--report-dir", type=Path, default=WORKSPACE / ".tools/a04-control/evidence")
    args = parser.parse_args()
    args.exe = args.exe.resolve()
    args.report_dir = args.report_dir.resolve()
    args.exe.parent.mkdir(parents=True, exist_ok=True)
    args.report_dir.mkdir(parents=True, exist_ok=True)
    source_paths = [ROOT / name for name in (
        "src/aura_control.c", "include/aura_control.h", "tests/host_control.c",
        "src/aura_archive.c", "include/aura_archive.h", "include/aura_nand.h", "include/aura_opus.h",
        "third_party/opus-1.6.1/include/opus.h", "third_party/opus-1.6.1/include/opus_types.h",
        "third_party/opus-1.6.1/include/opus_defines.h",
        "tests/nand_model.c", "tests/nand_model.h", "scripts/verify_control.py")]
    def source_hashes():
        return {p.relative_to(WORKSPACE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in source_paths}

    sources_before = source_hashes()
    build_command = None
    if args.build:
        zig = WORKSPACE / ".tools/zephyr/venv/Lib/site-packages/ziglang/zig.exe"
        build_command = [str(zig), "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1",
                         f"-I{ROOT / 'include'}", f"-I{ROOT / 'tests'}",
                         f"-I{ROOT / 'third_party/opus-1.6.1/include'}",
                         str(ROOT / "src/aura_control.c"), str(ROOT / "src/aura_archive.c"),
                         str(ROOT / "tests/nand_model.c"), str(ROOT / "tests/host_control.c"),
                         "-o", str(args.exe)]
        subprocess.run(build_command, check=True, cwd=WORKSPACE)
    executable_before = hashlib.sha256(args.exe.read_bytes()).hexdigest()
    fixture = args.report_dir / "control-pair.bin"
    run = subprocess.run([str(args.exe), str(fixture)], capture_output=True, text=True, check=False)
    (args.report_dir / "control-host.txt").write_text(run.stdout + run.stderr, encoding="utf-8", newline="\n")
    if run.returncode:
        raise RuntimeError(run.stdout + run.stderr)
    results = [line.removeprefix("RESULT ") for line in run.stdout.splitlines() if line.startswith("RESULT ")]
    assert len(results) == 1
    host = json.loads(results[0])
    assert host["groups"] == EXPECTED_GROUPS and host["fault_and_rotation_cases"] == EXPECTED_CASES
    wire = fixture.read_bytes()
    assert len(wire) == 2 * BLOCK_BYTES
    first, a = parse_block(wire[:BLOCK_BYTES], 0)
    second, b = parse_block(wire[BLOCK_BYTES:], 1)
    assert first["generation"] == 3 and second["generation"] == 2
    assert first["parent_sha256"] == second["commit_sha256"]
    assert a == bytes((n * 37 + 53) % 256 for n in range(1921))
    assert b == bytes((n * 37 + 23) % 256 for n in range(MAX_BYTES))
    # Independent decoder rejects canonical-size changes even with a fresh CRC.
    damaged = bytearray(wire[:BLOCK_BYTES])
    body_at = 3 * 2048
    damaged[body_at + 6:body_at + 8] = struct.pack("<H", 128)
    damaged[body_at + 2044:body_at + 2048] = struct.pack("<I", zlib.crc32(damaged[body_at:body_at + 2044]))
    try:
        parse_block(damaged, 0)
    except AssertionError:
        pass
    else:
        raise AssertionError("noncanonical body header accepted")
    assert source_hashes() == sources_before, "source changed during build/verification"
    assert hashlib.sha256(args.exe.read_bytes()).hexdigest() == executable_before, "executable changed during verification"
    report = dict(status="isolated_control_ledger_host_fault_tests_and_independent_wire_hash_verification_passed",
                  python=sys.version, host=host, control_block_ids=list(BLOCKS),
                  max_snapshot_bytes=MAX_BYTES, healthy_open_main_reads=128,
                  healthy_open_main_bytes=262144, snapshots=[first, second],
                  fixture_sha256=hashlib.sha256(wire).hexdigest(), build_command=build_command,
                  executable_sha256=executable_before,
                  host_transcript_sha256=hashlib.sha256((args.report_dir / "control-host.txt").read_bytes()).hexdigest(),
                  source_proven_by_this_run=args.build,
                  compiled_source_sha256=sources_before if args.build else None,
                  observed_source_sha256=sources_before,
                  limitations=["strict cold failure after torn newer snapshot can deny authority availability",
                               "operators cannot recover authority by simply reformatting",
                               "control hashes are public, not a MAC or physical anti-rollback",
                               "production populated-control erase callback is absent",
                               "no audio erasure, release controller, capture-ID issuance or catalog eviction",
                               "two fixed control blocks have no wear migration or bad-block replacement",
                               "host model is not physical power-loss or real-time qualification"])
    (args.report_dir / "control-ledger.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(run.stdout, end="")
    print(f"Independent Python wire/CRC/SHA256 verification passed: {args.report_dir}")


if __name__ == "__main__":
    main()
