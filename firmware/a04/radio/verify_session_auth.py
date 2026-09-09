"""Compile actual portable ASC1 code and independently compare Python HMAC bytes.

Writes only a temporary executable; prints source-bound evidence to stdout.
All keys/nonces are public synthetic data. No BLE, SMP, firmware flashing or
physical owner enrollment occurs here. No previous evidence is overwritten.
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

A04 = Path(__file__).resolve().parents[1]
WORKSPACE = A04.parents[1]
KEY = bytes(range(1, 33))
SERVER_DOMAIN = b"AURA-A04-SESSION-SERVER-v1\0"
CLIENT_DOMAIN = b"AURA-A04-SESSION-CLIENT-v1\0"
CONFIRM_DOMAIN = b"AURA-A04-SESSION-CONFIRM-v1\0"


def digest(path):
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def expected():
    body = struct.pack("<4sBBBB16s16s16sQQ16s16sII", b"ASC1", 1, 1, 1, 0,
                       b"\x11" * 16, b"\x33" * 16, b"\x44" * 16,
                       0x0102030405060708, 9, bytes(range(0x60, 0x70)),
                       bytes(range(0x80, 0x90)), 30000, 0)
    require(len(body) == 112, "Independent ASC1 body length changed")
    challenge = body + hmac.digest(KEY, SERVER_DOMAIN + body, "sha256")
    proof = hmac.digest(KEY, CLIENT_DOMAIN + challenge, "sha256")
    confirmation = struct.pack("<4sBBHQ", b"ASOK", 1, 1, 0, 9)
    confirmation += hmac.digest(KEY, CONFIRM_DOMAIN + challenge + proof, "sha256")
    require((len(challenge), len(proof), len(confirmation)) == (144, 32, 48), "Wire sizes changed")
    return challenge, proof, confirmation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", type=Path)
    args = parser.parse_args()
    bundled = WORKSPACE / ".tools/zephyr/venv/Lib/site-packages/ziglang/zig.exe"
    compiler = args.cc or (bundled if bundled.is_file() else None)
    if compiler is None:
        found = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
        if not found:
            raise RuntimeError("No C compiler; pass --cc PATH")
        compiler = Path(found)
    compiler_command = [str(compiler)] + (["cc"] if compiler.stem == "zig" else [])
    options = ["-std=c11", "-Wall", "-Wextra", "-Werror", "-UNDEBUG", "-O2"]
    opus = A04 / "third_party/opus-1.6.1/include"
    sources = [A04 / "src/aura_session_auth.c", A04 / "src/aura_release_auth.c",
               A04 / "src/aura_archive.c", A04 / "radio/tests/session_auth.c"]
    bindings = sources + [A04 / "include/aura_session_auth.h", A04 / "include/aura_release_auth.h",
                          A04 / "include/aura_archive.h", A04 / "include/aura_opus.h",
                          Path(__file__).resolve(), WORKSPACE / "docs/a04/session-auth-v1.md"]
    bindings += [opus / name for name in ("opus.h", "opus_types.h", "opus_defines.h")]
    before = {p.relative_to(WORKSPACE).as_posix(): digest(p) for p in bindings}
    challenge, proof, confirmation = expected()
    with tempfile.TemporaryDirectory(prefix="aura-session-auth-") as directory:
        executable = Path(directory) / "session-auth.exe"
        command = compiler_command + options + ["-I" + str(A04 / "include"), "-I" + str(opus)]
        command += [str(p) for p in sources] + ["-o", str(executable)]
        built = subprocess.run(command, capture_output=True, text=True, cwd=WORKSPACE)
        require(built.returncode == 0, "Compilation failed:\n" + built.stdout + built.stderr)
        run = subprocess.run([str(executable)], capture_output=True, text=True, cwd=WORKSPACE)
        require(run.returncode == 0, "C checks failed:\n" + run.stdout + run.stderr)
        output = run.stdout.replace("\r\n", "\n")
        groups = re.findall(r"^PASS (?!session_auth )(.+)$", output, re.MULTILINE)
        summary = re.findall(r"^PASS session_auth groups=(\d+) checks=(\d+) physical_hardware=false SMP_tested=false$", output, re.MULTILINE)
        require(len(groups) == 12 and len(summary) == 1 and summary[0][0] == "12", "Expected12 C groups")
        for label, wire in (("ASC1", challenge), ("CLIENT_PROOF", proof), ("ASOK", confirmation)):
            found = re.findall(rf"^{label} ([0-9a-f]+)$", output, re.MULTILINE)
            require(len(found) == 1 and bytes.fromhex(found[0]) == wire,
                    label + " differs from independent Python struct/HMAC encoding")
        accepted = subprocess.run([str(executable), "--proof", proof.hex()], capture_output=True,
                                  text=True, check=True, cwd=WORKSPACE)
        require(accepted.stdout.strip() == "PYTHON_PROOF_ACCEPTED " + confirmation.hex(),
                "Independent Python proof was not accepted with exact confirmation")
        negative_proofs = {
            "missing_domain_NUL": hmac.digest(KEY, CLIENT_DOMAIN[:-1] + challenge, "sha256"),
            "server_role_reflection": hmac.digest(KEY, SERVER_DOMAIN + challenge, "sha256"),
            "confirm_role_reflection": hmac.digest(KEY, CONFIRM_DOMAIN + challenge, "sha256"),
            "wrong_key": hmac.digest(bytes(range(2, 34)), CLIENT_DOMAIN + challenge, "sha256"),
            "truncated_then_zero_padded": proof[:16] + bytes(16),
        }
        for offset, label in ((8, "device"), (24, "incarnation"), (40, "owner"), (56, "owner_generation"),
                              (64, "connection_generation"), (72, "client_nonce"), (88, "server_nonce"),
                              (104, "deadline"), (112, "server_proof")):
            changed = bytearray(challenge)
            changed[offset] ^= 1
            negative_proofs["changed_" + label] = hmac.digest(KEY, CLIENT_DOMAIN + changed, "sha256")
        for label, invalid in negative_proofs.items():
            rejected = subprocess.run([str(executable), "--proof", invalid.hex()], capture_output=True,
                                      text=True, check=True, cwd=WORKSPACE)
            require(rejected.stdout.strip() == "PYTHON_PROOF_REJECTED -904", "Accepted " + label)
        executable_hash = digest(executable)
    after = {p.relative_to(WORKSPACE).as_posix(): digest(p) for p in bindings}
    require(before == after, "A tested input changed during verification")
    report = {
        "schema": "aura.session-auth.host.v1", "passed": True,
        "groups": groups, "c_groups": 12, "c_checks": int(summary[0][1]),
        "python_checks": ["exact_ASC1", "exact_client_proof", "exact_ASOK", "Python_proof_to_C"] + list(negative_proofs),
        "source_sha256": after, "inputs_unchanged": True,
        "compiler": str(compiler), "compile_options": options,
        "compiler_output": built.stdout + built.stderr,
        "executable_sha256": executable_hash,
        "transcript_sha256": hashlib.sha256(output.encode()).hexdigest(), "transcript": output,
        "wire": {"challenge_hex": challenge.hex(), "client_proof_hex": proof.hex(), "confirmation_hex": confirmation.hex()},
        "domain_bytes_including_NUL": {"server": len(SERVER_DOMAIN), "client": len(CLIENT_DOMAIN), "confirm": len(CONFIRM_DOMAIN)},
        "physical_hardware_tested": False, "SMP_tested": False, "radio_transport_tested": False,
        "owner_enrollment_tested": False, "whole_system_secret_erasure_tested": False,
        "scope": "Actual portable C provider plus Python standard-library HMAC; deterministic public inputs; no platform security-level truth or physical channel claim."
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
