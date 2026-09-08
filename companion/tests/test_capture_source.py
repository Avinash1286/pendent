import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import wave

from aura_companion import files
from aura_companion.capture_source import attach_capture_source, file_sha256, load_capture_source
from aura_companion.notes import transcribe, write_note
from aura_companion.upload import note_payload
from aura_companion.protocol_v2 import BOOKMARK, PCM16, Capture, Packet, Seal, read_archive


class CaptureSourceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.wav = self.root / "source.wav"
        with wave.open(str(self.wav), "wb") as output:
            output.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            output.writeframes(bytes(32000))
        self.capture = {
            "version": 2, "deviceId": "12" * 16, "captureId": "34" * 16,
            "archiveDigest": "56" * 32, "sampleRate": 16000, "sourceSamples": 16000,
            "startedAtMs": 0, "timeConfidence": "unknown", "interrupted": False,
            "bookmarks": [8000],
        }
        self.raw = self.root / "source.aur"
        capture = Capture(b"\x12" * 16, b"\x34" * 16, PCM16, pre_skip=0, bitrate=0, codec_profile=0, complexity=0)
        manifest = capture.encode()
        packets = [Packet(i, i * 320, 320, bytes(640)).encode() for i in range(50)]
        packets.append(Packet(50, 8000, 0, b"", BOOKMARK).encode())
        chain = hashlib.sha256(manifest).digest()
        for packet in packets:
            chain = hashlib.sha256(chain + packet).digest()
        seal = Seal(capture.device_id, capture.capture_id, 51, 50, 32000, 16000, 16000, 16000, 0, 0, chain)
        self.raw.write_bytes(manifest + b"".join(packets) + seal.encode())
        self.capture["archiveDigest"] = read_archive(self.raw).receipt.chain_sha256.hex()
        self.sidecar = self.wav.with_suffix(".capture.json")
        self.save_source()
        self.note = {
            "audio_file": self.wav.name, "title": "A thought", "transcript": "Keep the source.",
            "summary": ["Keep the source."], "suggested_actions": [], "summary_method": "extractive",
            "segments": [{"start": 0.0, "end": 1.0, "text": "Keep the source."}],
            "transcription": {"engine": "test-fixture", "model": "synthetic", "version": "1"},
        }

    def tearDown(self):
        self.directory.cleanup()

    def save_source(self):
        archive = read_archive(self.raw)
        self.sidecar.write_text(json.dumps({"kind": "aura-capture-export", "wav": self.wav.name,
                                            "wavSha256": file_sha256(self.wav), "capture": self.capture,
                                            "archive": self.raw.name, "archiveSha256": archive.sha256_hex,
                                            "receipt": archive.receipt.encode().hex(), "binaryWireVersion": 3,
                                            "originalSourceSamples": archive.original_source_samples,
                                            "discardedTailBytes": archive.discarded_tail_bytes}), encoding="utf-8")

    def save_note(self):
        note = attach_capture_source(self.note, self.wav)
        path = self.wav.with_suffix(".note.json")
        path.write_text(json.dumps(note), encoding="utf-8")
        return path, note

    def run_fake_transcription(self, during_inference=None):
        self.inference_paths = []

        def decode(audio, **kwargs):
            private_path = Path(audio)
            self.inference_paths.append(private_path)

            def segments():
                if during_inference is not None:
                    during_inference(private_path)
                yield SimpleNamespace(start=0, end=1, text="Keep the source.")

            return segments(), SimpleNamespace(language="en", duration=1)

        engine = SimpleNamespace(transcribe=decode)
        module = SimpleNamespace(WhisperModel=Mock(return_value=engine))
        with patch.dict("sys.modules", {"faster_whisper": module}), \
                patch("aura_companion.notes.version", return_value="test-version"):
            return transcribe(self.wav, model="test-model")

    def replace_source_identity(self):
        # A complete valid replacement with the same audio tests provenance
        # independently from the WAV hash (an editable sidecar alone is invalid).
        capture = Capture(b"\xab" * 16, b"\xcd" * 16, PCM16,
                          pre_skip=0, bitrate=0, codec_profile=0, complexity=0)
        packets = [Packet(i, i * 320, 320, bytes(640)).encode() for i in range(50)]
        packets.append(Packet(50, 8000, 0, b"", BOOKMARK).encode())
        chain = hashlib.sha256(capture.encode()).digest()
        for packet in packets:
            chain = hashlib.sha256(chain + packet).digest()
        seal = Seal(capture.device_id, capture.capture_id, 51, 50, 32000, 16000,
                    16000, 16000, 0, 0, chain)
        self.raw.write_bytes(capture.encode() + b"".join(packets) + seal.encode())
        self.capture.update(deviceId=capture.device_id.hex(), captureId=capture.capture_id.hex(),
                            archiveDigest=read_archive(self.raw).receipt.chain_sha256.hex())
        self.save_source()
        self.assertEqual(load_capture_source(self.wav), self.capture)

    def test_coherent_source_replacement_during_transcription_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "^Recording source changed during transcription; no note was produced$"):
            self.run_fake_transcription(lambda _: self.replace_source_identity())
        self.assertFalse(self.wav.with_suffix(".note.json").exists())
        self.assertFalse(self.inference_paths[0].exists())

    def test_source_sidecar_addition_or_removal_during_transcription_is_rejected(self):
        saved = self.sidecar.read_bytes()
        for adding in (False, True):
            with self.subTest(adding=adding):
                if adding:
                    self.sidecar.unlink(missing_ok=True)
                else:
                    self.sidecar.write_bytes(saved)

                def change_sidecar(_):
                    if adding:
                        self.sidecar.write_bytes(saved)
                    else:
                        self.sidecar.unlink()

                with self.assertRaisesRegex(ValueError, "Recording source changed"):
                    self.run_fake_transcription(change_sidecar)
                self.assertFalse(self.inference_paths[0].exists())

    def test_plain_audio_replacement_during_transcription_is_rejected(self):
        self.sidecar.unlink()
        before = self.wav.read_bytes()
        with self.assertRaisesRegex(ValueError, "Recording source changed"):
            self.run_fake_transcription(lambda _: self.wav.write_bytes(before[:-2] + b"\x01\x00"))
        self.assertFalse(self.inference_paths[0].exists())

    def test_private_snapshot_prevents_swap_then_restore_from_changing_model_audio(self):
        before = self.wav.read_bytes()
        original_capture = dict(self.capture)

        def swap_and_restore(private_path):
            self.assertNotEqual(private_path, self.wav)
            self.wav.write_bytes(before[:-2] + b"\x01\x00")
            self.assertEqual(private_path.read_bytes(), before)
            self.wav.write_bytes(before)

        note = self.run_fake_transcription(swap_and_restore)
        self.assertEqual(note["audio_file"], self.wav.name)
        self.assertEqual(note["recordedAt"], 0)
        self.assertEqual({key: note["capture"][key] for key in original_capture}, original_capture)
        self.assertEqual(note["capture"]["transcriptRevision"], hashlib.sha256(b"Keep the source.").hexdigest())
        self.assertEqual(note["capture"]["transcription"], note["transcription"])
        self.assertFalse(self.inference_paths[0].exists())

    def test_unchanged_plain_audio_does_not_acquire_capture_metadata(self):
        self.sidecar.unlink()
        note = self.run_fake_transcription()
        self.assertNotIn("capture", note)
        self.assertNotIn("recordedAt", note)
        self.assertFalse(self.inference_paths[0].exists())

    def test_unknown_time_and_source_survive_note_and_upload(self):
        path, note = self.save_note()
        payload = note_payload(path)
        self.assertEqual(payload["recordedAt"], 0)
        self.assertEqual(payload["sourceId"], "v2:" + "12" * 16 + ":" + "34" * 16)
        self.assertEqual(payload["capture"]["segments"], self.note["segments"])
        self.assertEqual(payload["capture"]["transcriptRevision"], hashlib.sha256(b"Keep the source.").hexdigest())
        note["title"] = "Reviewed title"
        path.write_text(json.dumps(note), encoding="utf-8")
        self.assertEqual(note_payload(path)["sourceId"], payload["sourceId"])
        self.assertNotIn("capture", self.note)

    def test_portable_note_keeps_identity_when_wav_is_unavailable(self):
        path, _ = self.save_note()
        before = note_payload(path)
        self.wav.unlink()
        self.assertEqual(note_payload(path), before)

    def test_substituted_wav_cannot_reuse_source_identity(self):
        with self.wav.open("ab") as stream:
            stream.write(b"changed")
        with self.assertRaisesRegex(ValueError, "does not match"):
            load_capture_source(self.wav)

    def test_source_duration_and_bookmark_validation(self):
        for key, value in (("sourceSamples", 16001), ("bookmarks", [-1]), ("bookmarks", [16001]),
                           ("startedAtMs", 100), ("version", True)):
            with self.subTest(key=key, value=value):
                original = self.capture[key]
                self.capture[key] = value
                self.save_source()
                with self.assertRaises(ValueError):
                    load_capture_source(self.wav)
                self.capture[key] = original
        self.save_source()

    def test_interrupted_unavailable_bookmark_is_preserved_and_labelled(self):
        # Portable note field validation/presentation. This isolated case asserts
        # sender metadata; the real interrupted-archive path has separate tests.
        self.capture.update(interrupted=True, bookmarks=[8000, 16010])
        note = {**self.note, "recordedAt": 0, "capture": {**self.capture,
                "segments": self.note["segments"], "transcription": self.note["transcription"],
                "transcriptRevision": hashlib.sha256(self.note["transcript"].encode()).hexdigest()}}
        path = self.wav.with_suffix(".note.json")
        path.write_text(json.dumps(note), encoding="utf-8")
        self.wav.unlink()
        self.assertEqual(note_payload(path)["capture"]["bookmarks"], [8000, 16010])
        _, markdown = write_note(note, self.wav)
        self.assertIn("audio unavailable", markdown.read_text(encoding="utf-8"))
        self.assertIn("original total duration is unknown", markdown.read_text(encoding="utf-8"))

    def test_sidecar_identity_edit_cannot_retag_unchanged_audio(self):
        self.capture["deviceId"] = "ab" * 16
        self.save_source()
        with self.assertRaisesRegex(ValueError, "preserved source archive"):
            load_capture_source(self.wav)

    def test_retranscription_preserves_the_complete_previous_note_revision(self):
        path, note = self.save_note()
        before = path.read_bytes()
        changed = {**note, "transcription": {"engine": "test-fixture", "model": "new", "version": "2"}}
        changed["capture"] = {**note["capture"], "transcription": changed["transcription"]}
        write_note(changed, self.wav)
        snapshots = list((self.root / ".note-revisions").rglob("*.note.json"))
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].read_bytes(), before)
        self.assertEqual(json.loads(path.read_text())["capture"]["transcription"]["model"], "new")

    def test_missing_sidecar_does_not_erase_a_prior_captured_note_revision(self):
        path, _ = self.save_note()
        before = path.read_bytes()
        self.sidecar.unlink()
        write_note(self.note, self.wav)
        snapshots = list((self.root / ".note-revisions").rglob("*.note.json"))
        self.assertEqual(snapshots[0].read_bytes(), before)

    def test_revision_directory_sync_failure_preserves_current_note_and_can_retry(self):
        path, note = self.save_note()
        before = path.read_bytes()
        markdown = self.wav.with_suffix(".md")
        markdown.write_bytes(b"previous readable view")
        changed = {**note, "title": "Reviewed title"}
        identity = hashlib.sha256(self.wav.name.encode()).hexdigest()[:16]
        revision_directory = self.root / ".note-revisions" / identity
        directories = (revision_directory, revision_directory.parent, self.root)
        for failed_directory in directories:
            with self.subTest(failed_directory=failed_directory):
                def fail_sync(directory):
                    if directory == failed_directory:
                        raise OSError("simulated directory sync failure")

                with patch("aura_companion.notes.sync_directory", side_effect=fail_sync), \
                        self.assertRaisesRegex(OSError, "simulated directory sync failure"):
                    write_note(changed, self.wav)
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(markdown.read_bytes(), b"previous readable view")
        snapshots = list(revision_directory.glob("*.note.json"))
        self.assertEqual([snapshot.read_bytes() for snapshot in snapshots], [before])
        write_note(changed, self.wav)
        self.assertEqual(json.loads(path.read_text())["title"], "Reviewed title")
        self.assertEqual(snapshots[0].read_bytes(), before)

    def test_existing_revision_file_sync_failure_preserves_current_note(self):
        path, note = self.save_note()
        before = path.read_bytes()
        changed = {**note, "title": "Reviewed title"}
        write_note(changed, self.wav)
        path.write_bytes(before)
        with patch("aura_companion.notes.sync_file", side_effect=OSError("simulated file sync failure")), \
                self.assertRaisesRegex(OSError, "simulated file sync failure"):
            write_note(changed, self.wav)
        self.assertEqual(path.read_bytes(), before)

    def test_revision_is_synced_through_directory_chain_before_current_replacement(self):
        path, note = self.save_note()
        events = []
        original_replace, original_fsync = files.os.replace, files.os.fsync

        def replace(source, destination):
            events.append(("replace", destination))
            return original_replace(source, destination)

        def fsync(descriptor):
            events.append(("file-sync", None))
            return original_fsync(descriptor)

        def directory_sync(directory):
            events.append(("directory-sync", directory))

        with patch("aura_companion.files.os.replace", side_effect=replace), \
                patch("aura_companion.files.os.fsync", side_effect=fsync), \
                patch("aura_companion.files.sync_directory", side_effect=directory_sync), \
                patch("aura_companion.notes.sync_directory", side_effect=directory_sync):
            write_note({**note, "title": "Reviewed title"}, self.wav)
        revision = next((self.root / ".note-revisions").rglob("*.note.json"))
        revision_publish = events.index(("replace", revision))
        self.assertEqual(events[revision_publish - 1][0], "file-sync")
        # Leaf entry, leaf/parent links, and root link must all be prepared
        # before even the regenerable Markdown or authoritative JSON changes.
        chain_end = events.index(("directory-sync", self.root))
        for directory in (revision.parent, revision.parent.parent, self.root):
            self.assertIn(("directory-sync", directory), events[revision_publish + 1:chain_end + 1])
        self.assertLess(chain_end, events.index(("replace", self.wav.with_suffix(".md"))))
        self.assertLess(chain_end, events.index(("replace", path)))
        self.assertEqual(events[-1], ("directory-sync", self.root))

    def test_atomic_publication_directory_sync_failure_is_not_silenced(self):
        destination = self.root / "publication.txt"
        with patch("aura_companion.files.sync_directory", side_effect=OSError("directory sync failed")), \
                self.assertRaisesRegex(OSError, "directory sync failed"):
            files.atomic_write_text(destination, "complete replacement")
        # Rename precedes directory sync: the complete new file may exist even
        # when durability fails. Callers must not assume the old file remains.
        self.assertEqual(destination.read_text(), "complete replacement")
        self.assertEqual(list(self.root.glob("publication.txt.*.tmp")), [])

    def test_posix_directory_sync_closes_descriptor_and_propagates_failure(self):
        operating_system = SimpleNamespace(name="posix", O_RDONLY=0, O_DIRECTORY=123,
                                          open=Mock(return_value=17), fsync=Mock(), close=Mock())
        with patch("aura_companion.files.os", operating_system):
            files.sync_directory(self.root)
            operating_system.open.assert_called_once_with(self.root, 123)
            operating_system.fsync.assert_called_once_with(17)
            operating_system.close.assert_called_once_with(17)
            operating_system.fsync.side_effect = OSError("fsync failed")
            with self.assertRaisesRegex(OSError, "fsync failed"):
                files.sync_directory(self.root)
            self.assertEqual(operating_system.close.call_count, 2)

    def test_windows_directory_sync_does_not_claim_unsupported_flush(self):
        operating_system = SimpleNamespace(name="nt", open=Mock(), fsync=Mock(), close=Mock())
        with patch("aura_companion.files.os", operating_system):
            files.sync_directory(self.root)
        operating_system.open.assert_not_called()
        operating_system.fsync.assert_not_called()

    def test_changed_recovery_explanation_is_rejected(self):
        data = json.loads(self.sidecar.read_text())
        data["discardedTailBytes"] = 12
        self.sidecar.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "recovery metadata"):
            load_capture_source(self.wav)

    def test_modified_transcript_requires_a_new_reviewed_revision(self):
        path, note = self.save_note()
        note["transcript"] = "A different thought."
        path.write_text(json.dumps(note), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Transcript changed"):
            note_payload(path)

    def test_source_metadata_rebinding_is_rejected_with_sibling_audio(self):
        path, note = self.save_note()
        note["capture"]["deviceId"] = "78" * 16
        path.write_text(json.dumps(note), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "conflicts"):
            note_payload(path)

    def test_invalid_segment_timing_and_method_fail_before_upload(self):
        bad = [
            [{"start": 0, "end": 1.1, "text": "too late"}],
            [{"start": -1, "end": 1, "text": "negative"}],
            [{"start": 0, "end": float("nan"), "text": "nonfinite"}],
            [{"start": 0, "end": .5, "text": "first"}, {"start": .4, "end": .6, "text": "overlap"}],
        ]
        for segments in bad:
            path, note = self.save_note()
            note["capture"]["segments"] = segments
            path.write_text(json.dumps(note), encoding="utf-8")
            with self.subTest(segments=segments), self.assertRaises(ValueError):
                note_payload(path)
        path, note = self.save_note()
        note["capture"]["transcription"]["model"] = ""
        path.write_text(json.dumps(note), encoding="utf-8")
        with self.assertRaises(ValueError):
            note_payload(path)


if __name__ == "__main__":
    unittest.main()
