"""Compile/test actual RLS1 code; emit a source-bound JSON report to stdout.

Only a temporary build directory is written. No keys, receipts, verification
files, project configuration or CAD are modified. All keys below are public
synthetic test data. This script does not issue authorization for real captures.
"""
import argparse
import hashlib
import hmac
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
DOMAIN = b"AURA-A04-OWNER-RELEASE-v1\0"


def digest(path):
    data = path.read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(),
            "lf_normalized_sha256": hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()}


def fixture(sequence=9):
    ack_body = struct.pack("<4sBB16s16sIQQ32s", b"ACK3", 3, 1,
                           b"\x11" * 16, b"\x22" * 16, 7, 80, 320,
                           bytes(range(0x60, 0x80)))
    ack = ack_body + struct.pack("<I", zlib.crc32(ack_body))
    body = struct.pack("<4sBBBB16s16sQQ", b"RLS1", 1, 1, 1, 0,
                       b"\x33" * 16, b"\x44" * 16,
                       0x0102030405060708, sequence) + ack
    assert len(body) == 150
    return body + hmac.digest(bytes(range(1, 33)), DOMAIN + body, "sha256")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", type=Path, help="C compiler executable; zig uses its cc subcommand")
    args = parser.parse_args()
    bundled = WORKSPACE / ".tools/zephyr/venv/Lib/site-packages/ziglang/zig.exe"
    compiler = args.cc or (bundled if bundled.is_file() else None)
    if compiler is None:
        found = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
        if not found:
            raise RuntimeError("No C compiler found; pass --cc PATH")
        compiler = Path(found)
    command = [str(compiler)]
    if compiler.stem == "zig":
        command.append("cc")
    options = ["-std=c11", "-Wall", "-Wextra", "-Werror", "-UNDEBUG", "-O2"]
    sources = [ROOT / "src/aura_release_auth.c", ROOT / "src/aura_archive.c",
               ROOT / "tests/host_release_auth.c"]
    bindings = sources + [ROOT / "include/aura_release_auth.h", ROOT / "include/aura_archive.h",
                          ROOT / "include/aura_opus.h", Path(__file__).resolve(),
                          ROOT / "RELEASE-AUTH.md"]
    # aura_archive.h includes aura_opus.h. These are real pinned public headers;
    # no Opus code or mock cryptography is needed by the linked archive object.
    opus_include = ROOT / "third_party/opus-1.6.1/include"
    bindings += [opus_include / name for name in ("opus.h", "opus_types.h", "opus_defines.h")]
    before = {p.relative_to(WORKSPACE).as_posix(): digest(p) for p in bindings}
    with tempfile.TemporaryDirectory(prefix="aura-release-auth-") as temporary:
        executable = Path(temporary) / "release-auth.exe"
        subprocess.run(command + options + ["-I" + str(ROOT / "include"),
                       "-I" + str(opus_include)] + [str(p) for p in sources] +
                       ["-o", str(executable)], check=True, cwd=WORKSPACE)
        result = subprocess.run([str(executable)], capture_output=True, text=True,
                                check=True, cwd=WORKSPACE)
        output = result.stdout.replace("\r\n", "\n")
        names = re.findall(r"^PASS (.+)$", output, flags=re.MULTILINE)
        require(len(names) == 13 and output.endswith("13 release-auth test groups passed\n"),
                "Expected exactly13 successful C groups")
        c_wire = re.search(r"^INTEROP_RLS1 ([0-9a-f]+)$", output, flags=re.MULTILINE)
        require(c_wire is not None and bytes.fromhex(c_wire[1]) == fixture(),
                "C envelope differs from independent Python struct/HMAC/CRC encoding")
        for label, key, message in (("EMPTY_HMAC", b"", b""),
                                    ("MAX_HMAC", bytes(256), bytes(256))):
            found = re.search(rf"^{label} ([0-9a-f]+)$", output, flags=re.MULTILINE)
            require(found is not None and found[1] == hmac.digest(key, message, "sha256").hex(),
                    f"Independent Python comparison failed: {label}")
        # Fresh, different sequence verifies Python->C independently of C signing.
        python_wire = fixture(sequence=0x1020304050607080)
        accepted = subprocess.run([str(executable), "--authenticate", python_wire.hex()],
                                  capture_output=True, text=True, check=True, cwd=WORKSPACE)
        require(accepted.stdout.strip() == "PYTHON_RLS1_ACCEPTED", "Python wire rejected by C")
        executable_hash = digest(executable)
    after = {p.relative_to(WORKSPACE).as_posix(): digest(p) for p in bindings}
    require(before == after, "A tested input changed during verification")
    report = {
        "status": "portable_authentication_tests_passed",
        "c_passed_groups": len(names), "groups": names,
        "python_comparisons": ["C_to_Python_exact_wire", "Python_to_C_authentication",
                               "empty_HMAC", "maximum_bounded_HMAC"],
        "sources": after,
        "compiler": str(compiler), "compile_options": options,
        "executable": executable_hash,
        "transcript": output,
        "synthetic_rls1_sha256": hashlib.sha256(fixture()).hexdigest(),
        "rls1_bytes": 182, "mac_domain_hex": DOMAIN.hex(),
        "not_implemented_or_verified": ["durable replay floor", "reclamation controller",
            "owner provisioning", "physical device authentication", "protected key storage",
            "physical anti-rollback", "BLE", "physical deletion", "constant-time measurements"],
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
