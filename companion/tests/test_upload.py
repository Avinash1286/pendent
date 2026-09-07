import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import AsyncMock, patch

from aura_companion.device import Device
from aura_companion.protocol import ProtocolError
from aura_companion.upload import ingest_url, note_payload, upload_note


class IngestHandler(BaseHTTPRequestHandler):
    received = []
    redirect_to = None

    def log_message(self, *_):
        pass

    def do_POST(self):
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        type(self).received.append((self.path, self.headers.get("Authorization"), json.loads(raw)))
        if type(self).redirect_to:
            self.send_response(302)
            self.send_header("Location", type(self).redirect_to)
            self.end_headers()
            return
        response = b'{"id":"test-note-id","stored":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def do_GET(self):
        type(self).received.append((self.path, self.headers.get("Authorization"), "REDIRECTED"))
        self.send_response(500)
        self.end_headers()


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.note = self.root / "audio.note.json"
        self.wav = self.root / "audio.wav"
        self.wav.write_bytes(b"synthetic audio bytes used only for identity")
        self.data = {"audio_file": "audio.wav", "title": "Design review", "transcript": "Keep it simple.",
                     "summary": ["Keep it simple."], "suggested_actions": [], "tags": ["design"],
                     "recordedAt": 1788800000000}
        self.note.write_text(json.dumps(self.data), encoding="utf-8")

    def tearDown(self):
        self.directory.cleanup()

    def test_stable_source_audio_hash_and_schema(self):
        payload = note_payload(self.note)
        self.assertEqual(payload["sourceId"], "sha256:audio:" + hashlib.sha256(self.wav.read_bytes()).hexdigest())
        self.assertEqual(payload["actions"], [])
        self.assertEqual(payload["recordedAt"], 1788800000000)
        self.data["title"] = "Edited title"
        self.note.write_text(json.dumps(self.data), encoding="utf-8")
        self.assertEqual(note_payload(self.note)["sourceId"], payload["sourceId"])
        self.assertNotIn("audio_file", payload)

    def test_missing_audio_uses_canonical_note_hash(self):
        self.wav.unlink()
        before = note_payload(self.note)["sourceId"]
        self.note.write_text(json.dumps(dict(reversed(list(self.data.items()))), indent=4), encoding="utf-8")
        self.assertEqual(note_payload(self.note)["sourceId"], before)
        self.assertTrue(before.startswith("sha256:note:"))

    def test_rejects_unsafe_urls_and_note_structure(self):
        for url in ["http://example.com", "file:///tmp/aura", "https://user:secret@example.com",
                    "https://example.com?token=x", "https://example.com/#fragment"]:
            with self.assertRaises(ValueError):
                ingest_url(url)
        self.assertEqual(ingest_url("http://127.0.0.1:4321"), "http://127.0.0.1:4321/api/ingest")
        self.assertEqual(ingest_url("https://notes.example.com/"), "https://notes.example.com/api/ingest")
        self.data["suggested_actions"] = "not an array"
        self.note.write_text(json.dumps(self.data), encoding="utf-8")
        with self.assertRaises(ValueError):
            note_payload(self.note)

    def test_explicit_local_http_upload_and_redirect_refusal(self):
        IngestHandler.received = []
        IngestHandler.redirect_to = None
        server = ThreadingHTTPServer(("127.0.0.1", 0), IngestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            result = upload_note(self.note, portal_url=base, token="test-only-token")
            self.assertEqual(result["id"], "test-note-id")
            self.assertEqual(IngestHandler.received[0][:2], ("/api/ingest", "Bearer test-only-token"))
            self.assertEqual(IngestHandler.received[0][2]["transcript"], "Keep it simple.")
            IngestHandler.redirect_to = base + "/steal"
            with self.assertRaisesRegex(RuntimeError, "no redirect followed"):
                upload_note(self.note, portal_url=base, token="test-only-token")
            self.assertEqual(len(IngestHandler.received), 2)
            self.assertTrue(all(row[0] == "/api/ingest" for row in IngestHandler.received))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_no_network_without_explicit_configuration(self):
        with patch.dict("os.environ", {}, clear=True), patch("aura_companion.upload.build_opener") as opener:
            with self.assertRaises(ValueError):
                upload_note(self.note)
            opener.assert_not_called()


class MaintenanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_requires_confirmation_and_empty_idle_device(self):
        device = Device(None)
        device.status = AsyncMock(return_value={"recording_count": 1, "state": 0})
        device.request = AsyncMock()
        with self.assertRaises(ValueError):
            await device.format_storage()
        with self.assertRaises(ProtocolError):
            await device.format_storage(confirmed=True)
        device.request.assert_not_called()

    async def test_sends_exact_magic_with_extended_timeout(self):
        device = Device(None)
        device.status = AsyncMock(return_value={"recording_count": 0, "state": 0})
        device.request = AsyncMock(return_value=b"")
        await device.format_storage(confirmed=True)
        device.request.assert_awaited_once_with(6, b"ERAS", timeout=600)


if __name__ == "__main__":
    unittest.main()
