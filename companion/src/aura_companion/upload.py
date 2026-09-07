"""Explicit, bounded note upload. No redirects and no automatic network side effects."""
import hashlib
import ipaddress
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        # Never forward the private bearer token, even to a same-origin redirect.
        return None


def ingest_url(value: str) -> str:
    parts = urlsplit(value)
    if not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("AURA_PORTAL_URL must be a plain HTTPS base URL without credentials, query or fragment")
    loopback = parts.hostname.lower() == "localhost"
    try:
        loopback |= ipaddress.ip_address(parts.hostname).is_loopback
    except ValueError:
        pass
    if parts.scheme != "https" and not (parts.scheme == "http" and loopback):
        raise ValueError("Portal upload requires HTTPS; HTTP is allowed only for loopback development")
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/") + "/api/ingest", "", ""))


def _strings(note: dict, key: str, limit: int, item_limit=2000) -> list[str]:
    values = note.get(key, [])
    if not isinstance(values, list) or any(not isinstance(x, str) for x in values):
        raise ValueError(f"Note {key} must be a list of strings")
    if len(values) > limit or any(len(x) > item_limit for x in values):
        raise ValueError(f"Note {key} exceeds the portal upload limit")
    return values


def note_payload(note_path: Path) -> dict:
    if note_path.stat().st_size > 2_000_000:
        raise ValueError("Note file exceeds 2 MB")
    note = json.loads(note_path.read_text(encoding="utf-8"))
    if not isinstance(note, dict) or not isinstance(note.get("transcript"), str):
        raise ValueError("Note JSON must contain a transcript string")
    title = note.get("title", "Untitled recording")
    if not isinstance(title, str) or not title.strip() or len(title) > 160:
        raise ValueError("Note title must contain 1–160 characters")
    if len(note["transcript"]) > 60_000:
        raise ValueError("Transcript exceeds 60,000 characters; split the note before uploading")
    # Only a sibling source file may supply audio identity; note JSON cannot select arbitrary files.
    source = note.get("audio_file")
    digest = hashlib.sha256()
    wav = None
    if isinstance(source, str) and Path(source).name == source:
        candidate = note_path.parent / source
        if candidate.is_file() and candidate.resolve().parent == note_path.resolve().parent:
            wav = candidate
    if wav:
        with wav.open("rb") as stream:
            for block in iter(lambda: stream.read(65536), b""):
                digest.update(block)
        source_id = "sha256:audio:" + digest.hexdigest()
    else:
        # Canonical note bytes keep retry identity stable when the WAV was moved elsewhere.
        canonical = json.dumps(note, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        source_id = "sha256:note:" + hashlib.sha256(canonical.encode()).hexdigest()
    recorded_at = note.get("recordedAt")
    if recorded_at is None and wav:
        metadata = wav.with_suffix(".json")
        if metadata.is_file() and metadata.stat().st_size < 100_000:
            saved = json.loads(metadata.read_text(encoding="utf-8"))
            seconds = saved.get("started_unix_seconds", 0)
            if isinstance(seconds, int) and seconds > 0:
                recorded_at = seconds * 1000
    if recorded_at is None:
        recorded_at = int((wav or note_path).stat().st_mtime * 1000)
    if isinstance(recorded_at, bool) or not isinstance(recorded_at, int) or not 0 <= recorded_at <= int(time.time() * 1000) + 86_400_000:
        raise ValueError("recordedAt must be an epoch timestamp in milliseconds")
    return {"sourceId": source_id, "title": title, "transcript": note["transcript"],
            "summary": _strings(note, "summary", 20),
            "actions": _strings(note, "suggested_actions", 30),
            "tags": _strings(note, "tags", 10, 40), "recordedAt": recorded_at}


def upload_note(note_path: Path, *, portal_url=None, token=None) -> dict:
    portal_url = portal_url or os.environ.get("AURA_PORTAL_URL")
    token = token or os.environ.get("AURA_INGEST_TOKEN")
    if not portal_url or not token:
        raise ValueError("Set AURA_PORTAL_URL and AURA_INGEST_TOKEN before an explicit upload")
    if any(c in token for c in "\r\n"):
        raise ValueError("Invalid portal token")
    endpoint = ingest_url(portal_url)
    payload = note_payload(note_path)
    request = Request(endpoint, data=json.dumps(payload, ensure_ascii=False).encode(), method="POST",
                      headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    try:
        with build_opener(NoRedirects()).open(request, timeout=30) as response:
            result = json.loads(response.read(100_001))
    except HTTPError as error:
        # A server response may contain tokens or copied source notes; do not echo it.
        raise RuntimeError(f"Portal upload rejected (HTTP {error.code}); no redirect followed") from None
    except URLError:
        raise RuntimeError("Portal upload failed; check the portal URL and connectivity") from None
    if not isinstance(result, dict) or result.get("stored") is not True or not isinstance(result.get("id"), str):
        raise RuntimeError("Portal did not confirm storage; keep the local note and retry explicitly")
    return {"id": result["id"], "stored": True, "sourceId": payload["sourceId"]}
