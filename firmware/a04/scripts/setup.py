"""Fetch and verify the exact unmodified libopus source; no global installation."""
import hashlib
import json
from pathlib import Path
import tarfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
PIN = ROOT / "dependencies/opus-1.6.1.json"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    pin = json.loads(PIN.read_text(encoding="utf-8"))
    source = ROOT / "third_party" / pin["directory"]
    if not source.exists():
        cache = WORKSPACE / ".tools/a04-opus"
        cache.mkdir(parents=True, exist_ok=True)
        archive = cache / pin["archive"]
        if not archive.is_file():
            temporary = archive.with_suffix(".download")
            with urlopen(pin["url"], timeout=60) as response, temporary.open("wb") as output:
                while data := response.read(1024 * 1024):
                    output.write(data)
            temporary.replace(archive)
        if digest(archive) != pin["sha256"]:
            raise RuntimeError("Opus archive does not match the official pinned SHA256")
        source.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "r:gz") as package:
            for member in package.getmembers():
                target = (source.parent / member.name).resolve()
                if not target.is_relative_to(source.resolve()) or member.issym() or member.islnk():
                    raise RuntimeError("Unexpected archive path or link")
            package.extractall(source.parent, filter="data")
    problems = [name for name, expected in pin["files"].items()
                if not (source / name).is_file() or digest(source / name) != expected]
    if problems:
        raise RuntimeError("Pinned Opus source mismatch: " + ", ".join(problems[:8]))
    actual = {str(path.relative_to(source)).replace("\\", "/") for path in source.rglob("*") if path.is_file()}
    if actual != set(pin["files"]):
        raise RuntimeError("Unexpected files were added to the pinned Opus source directory")
    print(f"Verified libopus {pin['version']}: {len(pin['files'])} source files; no upstream files changed")


if __name__ == "__main__":
    main()
