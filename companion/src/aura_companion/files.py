"""Publish complete local artifacts without truncating the previous version.

POSIX publication also fsyncs the containing directory and propagates failures.
Windows uses file fsync plus os.replace; Python exposes no equivalent supported
directory fsync there, so this does not promise survival of a power failure.
"""
import os
from pathlib import Path
import tempfile


def sync_directory(path: Path):
    """Persist directory entries on POSIX; Windows has no portable equivalent."""
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def sync_file(path: Path):
    # Read/write mode also supports fsync on Windows. This is needed when a
    # prior attempt published a revision but failed before directory syncing.
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())


def atomic_write_text(path: Path, content: str):
    atomic_write_bytes(path, content.encode("utf-8"))


def atomic_write_bytes(path: Path, content: bytes):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix=path.name + ".",
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
