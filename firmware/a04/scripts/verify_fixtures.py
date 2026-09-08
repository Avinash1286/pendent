"""Decode real Opus fixtures with the host harness and FFmpeg's independent path."""
import array
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import wave

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
HEADER = struct.Struct("<4sHHIQQIHH")
PACKET = struct.Struct("<IQHH")


def ogg_crc(data):
    crc = 0
    for byte in data:
        crc ^= byte << 24
        for _ in range(8):
            crc = ((crc << 1) ^ (0x04C11DB7 if crc & 0x80000000 else 0)) & 0xFFFFFFFF
    return crc


def page(payload, serial, sequence, granule, flags):
    lace = [255] * (len(payload) // 255) + [len(payload) % 255]
    raw = struct.pack("<4sBBQIIIB", b"OggS", 0, flags, granule, serial, sequence, 0, len(lace))
    raw += bytes(lace) + payload
    return raw[:22] + struct.pack("<I", ogg_crc(raw)) + raw[26:]


def read_archive(path):
    data = path.read_bytes()
    magic, version, ms, rate, source, encoded, count, pre, tail = HEADER.unpack_from(data)
    if (magic, version, rate) != (b"AOC1", 1, 16000) or ms not in (10, 20):
        raise ValueError("Unexpected fixture archive header")
    if encoded - pre - tail != source or not source or tail >= ms * 16:
        raise ValueError("Inconsistent fixture trim metadata")
    offset = HEADER.size
    packets = []
    cursor = 0
    for expected in range(count):
        sequence, sample_offset, samples, size = PACKET.unpack_from(data, offset)
        offset += PACKET.size
        if sequence != expected or sample_offset != cursor or samples != ms * 16 or not 0 < size <= 1275:
            raise ValueError("Unexpected fixture packet metadata")
        payload = data[offset:offset + size]
        if len(payload) != size:
            raise ValueError("Truncated fixture packet")
        packets.append(payload)
        offset += size
        cursor += samples
    if offset != len(data) or cursor != encoded:
        raise ValueError("Fixture archive length mismatch")
    return dict(frame_ms=ms, sample_rate=rate, source_samples=source, encoded_samples=encoded,
                packets=count, pre_skip=pre, end_trim=tail), packets


def make_ogg(metadata, packets):
    serial = 0xA04C0000 + metadata["frame_ms"]
    head = struct.pack("<8sBBHIhB", b"OpusHead", 1, 1, metadata["pre_skip"] * 3, 16000, 0, 0)
    vendor = b"AURA A04 experimental libopus 1.6.1 fixture"
    tags = b"OpusTags" + struct.pack("<I", len(vendor)) + vendor + struct.pack("<I", 0)
    result = page(head, serial, 0, 0, 2) + page(tags, serial, 1, 0, 0)
    for index, packet in enumerate(packets):
        final = index == len(packets) - 1
        granule = ((metadata["source_samples"] + metadata["pre_skip"]) if final
                   else (index + 1) * metadata["frame_ms"] * 16) * 3
        result += page(packet, serial, index + 2, granule, 4 if final else 0)
    return result


def pcm(path):
    with wave.open(str(path), "rb") as stream:
        if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate()) != (1, 2, 16000):
            raise ValueError("Unexpected WAV format")
        result = array.array("h")
        result.frombytes(stream.readframes(stream.getnframes()))
        return result


def signal_snr(source, decoded):
    if len(source) != len(decoded):
        raise ValueError("Decoder changed exact source duration")
    energy = sum(int(x) ** 2 for x in source)
    error = sum((int(a) - int(b)) ** 2 for a, b in zip(source, decoded))
    if energy == 0:
        raise ValueError("Speech fixture contains no signal")
    return round(10 * math.log10(energy / max(1, error)), 3)


def main():
    tools = WORKSPACE / ".tools/a04-opus"
    input_wav = ROOT / "fixtures/source-speech-16k.wav"
    source = pcm(input_wav)
    source_raw = tools / "source-speech-16k.pcm"
    source_raw.write_bytes(source.tobytes())
    prefix = ROOT / "fixtures/speech"
    run = subprocess.run([str(tools / "host/aura_codec_test.exe"), str(source_raw), str(prefix)],
                         text=True, capture_output=True, check=True)
    (ROOT / "verification/host-codec.txt").write_text(run.stdout, encoding="utf-8")
    metrics = []
    for ms in (10, 20):
        archive = ROOT / f"fixtures/speech-{ms}ms.aoc"
        metadata, packets = read_archive(archive)
        opus_path = archive.with_suffix(".opus")
        opus_path.write_bytes(make_ogg(metadata, packets))
        decoded_raw = ROOT / f"fixtures/speech-{ms}ms-decoded.pcm"
        host_wav = ROOT / f"fixtures/speech-{ms}ms-host.wav"
        with wave.open(str(host_wav), "wb") as output:
            output.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            output.writeframes(decoded_raw.read_bytes())
        ffmpeg_wav = ROOT / f"fixtures/speech-{ms}ms-ffmpeg.wav"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(opus_path),
                        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(ffmpeg_wav)], check=True)
        host = pcm(host_wav)
        independent = pcm(ffmpeg_wav)
        metadata.update(encoded_bytes=sum(map(len, packets)), max_packet_bytes=max(map(len, packets)),
                        host_snr_db=signal_snr(source, host), ffmpeg_snr_db=signal_snr(source, independent),
                        decoder_agreement_snr_db=signal_snr(host, independent),
                        measured_payload_bitrate=round(sum(map(len, packets)) * 8 * 16000 / len(source), 3),
                        archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
        # This is a regression floor for this exact speech fixture, not a product
        # perceptual-quality claim, language benchmark, or hardware acoustic test.
        if metadata["host_snr_db"] < 8 or metadata["ffmpeg_snr_db"] < 8:
            raise ValueError("Unexpected severe codec/trim regression on this fixture")
        metrics.append(metadata)
    report = {
        "status": "host_passed_device_unmeasured",
        "opus_version": "1.6.1",
        "source": "AURA's pre-existing synthetic speech fixture, resampled to mono PCM16 16 kHz",
        "source_sha256": hashlib.sha256(input_wav.read_bytes()).hexdigest(),
        "ffmpeg_version": subprocess.run(["ffmpeg", "-version"], text=True, capture_output=True, check=True).stdout.splitlines()[0],
        "profiles": metrics,
        "not_verified": ["MCU encode deadline", "MCU stack high-water", "power", "PDM input", "durable flash sink",
                         "BLE concurrency", "physical microphone quality", "language/transcription benchmark"],
    }
    (ROOT / "verification/host-roundtrip.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(run.stdout, end="")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
