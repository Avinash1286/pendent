import array
import hashlib
import json
import math
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

from aura_companion.archive_import import _decode_ogg, _output_lock, _publish_or_verify, _write_ogg, import_capture
from aura_companion.capture_source import load_capture_source
from aura_companion.protocol import ProtocolError
from aura_companion.protocol_v2 import AUDIO, BOOKMARK, PCM16, Capture, Packet, Seal

FIXTURES = Path(__file__).resolve().parents[2] / "firmware/a04/fixtures"


def codec_fixture(ms):
    # Historical AOC1 is only a real-encoded test source for the Ogg exporter.
    # Shipping import rejects AOC1; the protocol agent supplies AUR3 fixtures.
    header = struct.Struct("<4sHHIQQIHH")
    frame = struct.Struct("<IQHH")
    data = (FIXTURES / f"speech-{ms}ms.aoc").read_bytes()
    magic, version, _, rate, source, _, count, pre, _ = header.unpack_from(data)
    assert (magic, version, rate) == (b"AOC1", 1, 16000)
    offset = header.size
    packets = []
    for _ in range(count):
        sequence, sample_offset, samples, size = frame.unpack_from(data, offset)
        offset += frame.size
        payload = data[offset:offset + size]
        offset += size
        packets.append(SimpleNamespace(kind=AUDIO, sequence=sequence, sample_offset=sample_offset,
                                       sample_count=samples, payload=payload))
    assert offset == len(data)
    return SimpleNamespace(capture=SimpleNamespace(capture_id=b"\x12" * 16, pre_skip=pre),
                           source_samples=source, iter_packets=lambda: iter(packets))


def pcm(path):
    with wave.open(str(path), "rb") as stream:
        assert (stream.getnchannels(), stream.getsampwidth(), stream.getframerate()) == (1, 2, 16000)
        values = array.array("h")
        values.frombytes(stream.readframes(stream.getnframes()))
        return values


def pcm_archive(path):
    capture = Capture(b"\x12" * 16, b"\x34" * 16, PCM16, pre_skip=0, bitrate=0, codec_profile=0, complexity=0)
    manifest = capture.encode()
    frames = [Packet(0, 0, 320, b"\x01\x00" * 320).encode(), Packet(1, 160, 0, b"", BOOKMARK).encode()]
    chain = hashlib.sha256(manifest).digest()
    for frame in frames:
        chain = hashlib.sha256(chain + frame).digest()
    seal = Seal(capture.device_id, capture.capture_id, 2, 1, 640, 320, 317, 317, 0, 3, chain)
    path.write_bytes(manifest + b"".join(frames) + seal.encode())
    return path


class ArchiveAudioTests(unittest.TestCase):
    def test_actual_opus_decodes_with_exact_tail_and_independent_reference(self):
        for ms in (10, 20):
            with self.subTest(ms=ms), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                archive = codec_fixture(ms)
                self.assertEqual(_write_ogg(archive, root / "source.opus"), [])
                _decode_ogg(root / "source.opus", root / "source.wav", archive.source_samples)
                decoded = pcm(root / "source.wav")
                reference = pcm(FIXTURES / f"speech-{ms}ms-ffmpeg.wav")
                self.assertEqual(len(decoded), 120847)
                self.assertEqual(len(decoded), len(reference))
                error = sum((int(a) - int(b)) ** 2 for a, b in zip(decoded, reference))
                energy = sum(int(a) ** 2 for a in reference)
                self.assertGreater(10 * math.log10(energy / max(1, error)), 40)

    def test_c_encoded_archive_import_and_decoder_independent_reuse(self):
        for ms in (10, 20):
            with self.subTest(ms=ms), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                path = FIXTURES / f"capture-{ms}ms.aura"
                result = import_capture(path, root)
                metadata = json.loads(result.metadata.read_text())
                self.assertEqual(bytes.fromhex(metadata["receipt"]), path.with_suffix(".receipt").read_bytes())
                self.assertEqual(len(pcm(result.wav)), 120847)
                self.assertEqual(metadata["capture"]["bookmarks"], [8000, 32000])
                self.assertIn("version", metadata["decoder"])
                with patch("aura_companion.archive_import._decode_ogg", side_effect=AssertionError("Must reuse verified WAV")) as decode:
                    repeated = import_capture(path, root)
                    self.assertTrue(repeated.reused)
                    decode.assert_not_called()

    def test_c_interrupted_opus_preserves_unknown_tail_and_exact_retained_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            result = import_capture(FIXTURES / "capture-20ms-interrupted.aura", Path(directory), allow_interrupted=True)
            metadata = json.loads(result.metadata.read_text())
            self.assertEqual(len(pcm(result.wav)), 120600)
            self.assertTrue(metadata["capture"]["interrupted"])
            self.assertIsNone(metadata["originalSourceSamples"])

    def test_decoder_rejects_inconsistent_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = codec_fixture(20)
            _write_ogg(archive, root / "source.opus")
            for duration in (archive.source_samples - 1, archive.source_samples + 1):
                with self.subTest(duration=duration), self.assertRaises(ProtocolError):
                    _decode_ogg(root / "source.opus", root / "wrong.wav", duration)

    def test_decoder_failure_does_not_echo_untrusted_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "bad.opus"
            source.write_bytes(b"private transcript or token")
            with self.assertRaisesRegex(ProtocolError, "could not be decoded") as failure:
                _decode_ogg(source, root / "wrong.wav", 320)
            self.assertNotIn("private transcript", str(failure.exception))

    def test_publication_never_overwrites_a_conflicting_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "new", root / "existing"
            source.write_bytes(b"new source")
            target.write_bytes(b"preserved source")
            with self.assertRaises(ValueError):
                _publish_or_verify(source, target)
            self.assertEqual(target.read_bytes(), b"preserved source")
            self.assertEqual(source.read_bytes(), b"new source")
            source.write_bytes(b"preserved source")
            before = target.stat().st_mtime_ns
            _publish_or_verify(source, target)
            self.assertEqual(target.stat().st_mtime_ns, before)

    def test_os_lock_rejects_a_second_import_and_can_be_reacquired(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with _output_lock(root):
                with self.assertRaises(RuntimeError):
                    with _output_lock(root):
                        self.fail("Second importer acquired the same output directory")
            with _output_lock(root):
                pass

    def test_real_archive_import_receipt_audio_and_repeat_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = pcm_archive(root / "input.aur")
            result = import_capture(raw, root / "recordings")
            self.assertEqual(result.status, "finalized")
            self.assertFalse(result.reused)
            self.assertEqual(result.archive.read_bytes(), raw.read_bytes())
            self.assertEqual(list(pcm(result.wav)), [1] * 317)
            source = load_capture_source(result.wav)
            self.assertEqual(source["bookmarks"], [160])
            self.assertEqual(source["startedAtMs"], 0)
            before = result.wav.stat().st_mtime_ns
            repeat = import_capture(raw, root / "recordings")
            self.assertTrue(repeat.reused)
            self.assertEqual(repeat.wav, result.wav)
            self.assertEqual(repeat.wav.stat().st_mtime_ns, before)

    def test_missing_final_sidecar_is_repaired_after_publication_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = pcm_archive(root / "input.aur")
            publish = _publish_or_verify

            def fail_sidecar(source, destination):
                if destination.name.endswith(".capture.json"):
                    raise OSError("Injected storage failure")
                publish(source, destination)

            with patch("aura_companion.archive_import._publish_or_verify", side_effect=fail_sidecar):
                with self.assertRaises(OSError):
                    import_capture(raw, root / "recordings")
            retained = list((root / "recordings").glob("*.wav"))
            self.assertEqual(len(retained), 1)
            before = retained[0].read_bytes()
            repaired = import_capture(raw, root / "recordings")
            self.assertEqual(repaired.wav.read_bytes(), before)
            self.assertIsNotNone(load_capture_source(repaired.wav))

    def test_corrupt_preserved_wav_is_rejected_without_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = pcm_archive(root / "input.aur")
            result = import_capture(raw, root / "recordings")
            result.wav.write_bytes(b"corrupt but retained")
            with self.assertRaises(ValueError):
                import_capture(raw, root / "recordings")
            self.assertEqual(result.wav.read_bytes(), b"corrupt but retained")
            self.assertEqual(result.archive.read_bytes(), raw.read_bytes())

    def test_interrupted_import_is_explicit_and_keeps_later_final_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = pcm_archive(root / "input.aur")
            interrupted = root / "interrupted.aur"
            interrupted.write_bytes(raw.read_bytes()[:-2])
            with self.assertRaises(ProtocolError):
                import_capture(interrupted, root / "recordings")
            prefix = import_capture(interrupted, root / "recordings", allow_interrupted=True)
            complete = import_capture(raw, root / "recordings")
            self.assertNotEqual(prefix.wav, complete.wav)
            self.assertEqual(len(pcm(prefix.wav)), 320)
            self.assertEqual(len(pcm(complete.wav)), 317)
            self.assertIsNone(json.loads(prefix.metadata.read_text())["originalSourceSamples"])
            self.assertTrue(load_capture_source(prefix.wav)["interrupted"])


if __name__ == "__main__":
    unittest.main()
