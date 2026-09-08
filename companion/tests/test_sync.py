"""CLI recovery tests with synthetic files and no Bluetooth/model/network access."""
from contextlib import asynccontextmanager, contextmanager, ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from aura_companion import cli
from aura_companion.notes import write_note as real_write_note


class SyncHarness:
    def __init__(self, directory):
        self.directory = directory
        self.connected = False
        self.events = []
        self.fail_stage = None
        self.download_failures = set()
        self.fail_inventory_after_first = False
        self.fail_disconnect = False
        self.state = 0

    def args(self, **overrides):
        return SimpleNamespace(**({"command": "sync", "device": "test-pendant", "output": self.directory,
                                  "transcribe": True, "ollama": "test-local-model", "upload": True,
                                  "model": "test-whisper", "language": None} | overrides))

    @asynccontextmanager
    async def connect(self, address):
        self.connected = True
        self.events.append("connected")
        try:
            yield self
        finally:
            self.connected = False
            self.events.append("disconnected")
            if self.fail_disconnect:
                raise RuntimeError("synthetic disconnect failure")

    async def status(self):
        return {"state": self.state}

    async def set_time(self):
        self.events.append("set_time")

    async def recordings(self):
        yield SimpleNamespace(id=1)
        if self.fail_inventory_after_first:
            raise RuntimeError("synthetic interrupted inventory")
        yield SimpleNamespace(id=2)

    async def download(self, recording, output):
        if not self.connected:
            raise AssertionError("download requires an active BLE session")
        self.events.append(f"download:{recording.id}")
        if recording.id in self.download_failures:
            (output / f"record-{recording.id}.pcm.part").write_bytes(b"partial")
            raise RuntimeError("synthetic checksum failure")
        path = output / f"record-{recording.id}.wav"
        path.write_bytes(b"verified WAV stand-in; PCM verification is tested separately")
        return path

    def stage(self, stage, name):
        if self.connected:
            raise AssertionError("processing started before BLE disconnected")
        self.events.append(f"{stage}:{name}")
        if self.fail_stage == stage and name == "record-1.wav":
            raise RuntimeError("PRIVATE_TRANSCRIPT SECRET_TOKEN must not be recorded or printed")

    def transcribe(self, path, model, language):
        self.stage("transcription", path.name)
        return {"audio_file": path.name, "title": "Synthetic note", "transcript": "Synthetic words.",
                "summary": ["Synthetic words."], "suggested_actions": [], "summary_method": "test only",
                "segments": [{"start": 0, "end": 1, "text": "Synthetic words."}]}

    def refine(self, note, model):
        self.stage("refinement", note["audio_file"])
        return note

    def write_note(self, note, path):
        self.stage("notes", path.name)
        return real_write_note(note, path)

    def upload(self, path):
        self.stage("upload", path.name.replace(".note.json", ".wav"))
        if not path.exists():
            raise AssertionError("upload requires a published note")
        return {"stored": True, "id": "synthetic-id"}

    @contextmanager
    def patched(self):
        with ExitStack() as stack:
            for name, function in {"connect": self.connect, "transcribe": self.transcribe,
                                   "refine_with_ollama": self.refine, "write_note": self.write_note,
                                   "upload_note": self.upload}.items():
                stack.enter_context(patch.object(cli, name, side_effect=function))
            yield


class SyncTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    async def test_all_downloads_and_disconnect_precede_any_processing(self):
        harness = SyncHarness(self.directory)
        with harness.patched(), redirect_stdout(io.StringIO()) as output:
            await cli.bluetooth(harness.args())
        self.assertEqual(harness.events[:5], ["connected", "set_time", "download:1", "download:2", "disconnected"])
        self.assertEqual(harness.events[5:], [f"{stage}:record-{record}.wav" for record in (1, 2)
                                            for stage in ("transcription", "refinement", "notes", "upload")])
        self.assertIn("No recordings were deleted", output.getvalue())
        for record in (1, 2):
            receipt = json.loads((self.directory / f"record-{record}.sync.json").read_text())
            self.assertEqual(receipt, {"version": 1, "wav": f"record-{record}.wav", "stage": "upload",
                                       "status": "completed", "success": True})

    async def test_later_notes_continue_after_each_processing_stage_failure(self):
        for stage in ("transcription", "refinement", "notes", "upload"):
            with self.subTest(stage=stage):
                directory = self.directory / stage
                directory.mkdir()
                harness = SyncHarness(directory)
                harness.fail_stage = stage
                with harness.patched(), redirect_stdout(io.StringIO()) as output:
                    with self.assertRaises(RuntimeError) as failure:
                        await cli.bluetooth(harness.args())
                self.assertIn("upload:record-2.wav", harness.events)
                self.assertEqual(harness.events.count(f"{stage}:record-1.wav"), 1)
                self.assertTrue((directory / "record-1.wav").exists())
                self.assertTrue((directory / "record-2.note.json").exists())
                receipt_text = (directory / "record-1.sync.json").read_text()
                receipt = json.loads(receipt_text)
                self.assertEqual((receipt["stage"], receipt["status"], receipt["success"]), (stage, "failed", False))
                self.assertEqual(receipt["error_code"], "upload_not_confirmed" if stage == "upload" else "stage_failed")
                message = str(failure.exception)
                self.assertIn("1 failure(s)", message)
                self.assertIn(str(directory / "record-1.wav"), message)
                self.assertIn("No retries were scheduled", message)
                for secret in ("PRIVATE_TRANSCRIPT", "SECRET_TOKEN"):
                    self.assertNotIn(secret, receipt_text + message + output.getvalue())

    async def test_failed_download_does_not_block_later_verified_recording(self):
        harness = SyncHarness(self.directory)
        harness.download_failures.add(1)
        with harness.patched(), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "Recording 00000001: download not verified"):
                await cli.bluetooth(harness.args(upload=False))
        self.assertIn("notes:record-2.wav", harness.events)
        self.assertNotIn("transcription:record-1.wav", harness.events)
        self.assertTrue((self.directory / "record-1.pcm.part").exists())
        self.assertFalse(any(event.startswith("upload:") for event in harness.events))

    async def test_verified_downloads_are_processed_after_later_transfer_interruption(self):
        harness = SyncHarness(self.directory)
        harness.fail_inventory_after_first = True
        with harness.patched(), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "Bluetooth transfer did not complete"):
                await cli.bluetooth(harness.args(upload=False, ollama=None))
        self.assertLess(harness.events.index("disconnected"), harness.events.index("transcription:record-1.wav"))
        self.assertTrue((self.directory / "record-1.note.json").exists())
        self.assertFalse(any(event.startswith(("upload:", "refinement:")) for event in harness.events))

    async def test_disconnect_failure_preserves_wavs_without_starting_processing(self):
        harness = SyncHarness(self.directory)
        harness.fail_disconnect = True
        with harness.patched(), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "local processing was not started"):
                await cli.bluetooth(harness.args())
        self.assertTrue(all((self.directory / f"record-{record}.wav").exists() for record in (1, 2)))
        self.assertFalse(any(event.startswith("transcription:") for event in harness.events))

    async def test_plain_sync_never_transcribes_refines_uploads_or_deletes(self):
        harness = SyncHarness(self.directory)
        with harness.patched(), redirect_stdout(io.StringIO()):
            await cli.bluetooth(harness.args(transcribe=False, upload=False))
        self.assertEqual(harness.events, ["connected", "set_time", "download:1", "download:2", "disconnected"])
        self.assertEqual(list(self.directory.glob("*.sync.json")), [])

    async def test_upload_requires_explicit_transcription_before_connecting(self):
        harness = SyncHarness(self.directory)
        with harness.patched():
            with self.assertRaisesRegex(ValueError, "also requires --transcribe"):
                await cli.bluetooth(harness.args(transcribe=False))
        self.assertEqual(harness.events, [])

    async def test_active_capture_does_not_download_or_process(self):
        for state in (1, 2):
            with self.subTest(state=state):
                harness = SyncHarness(self.directory)
                harness.state = state
                with harness.patched(), redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(RuntimeError, "Stop the current recording"):
                        await cli.bluetooth(harness.args())
                self.assertEqual(harness.events, ["connected", "disconnected"])


if __name__ == "__main__":
    unittest.main()
