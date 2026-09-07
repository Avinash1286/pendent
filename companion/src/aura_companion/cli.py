import argparse
import asyncio
import json
from pathlib import Path
import struct
import sys

from .device import connect, discover
from .notes import transcribe, refine_with_ollama, write_note
from .upload import upload_note


async def bluetooth(args):
    if args.command == "scan":
        devices = await discover()
        for device, advert in devices:
            print(json.dumps({"address": device.address, "name": advert.local_name or device.name}))
        if not devices:
            print("No AURA found. Hold the idle pendant face for three seconds to open pairing.")
        return
    async with connect(args.device) as device:
        if args.command == "status":
            print(json.dumps(await device.status(), indent=2))
        elif args.command == "sync":
            status = await device.status()
            if status["state"] in (1, 2):
                raise ValueError("Stop the current recording and wait for it to save before syncing")
            await device.set_time()
            count = 0
            async for recording in device.recordings():
                path = await device.download(recording, args.output)
                print(f"Verified and saved: {path}")
                count += 1
                if args.transcribe:
                    note = await asyncio.to_thread(transcribe, path, args.model, args.language)
                    if args.ollama:
                        note = await asyncio.to_thread(refine_with_ollama, note, args.ollama)
                    write_note(note, path)
                    if args.upload:
                        saved = await asyncio.to_thread(upload_note, path.with_suffix(".note.json"))
                        print(f"Stored in portal: {saved['id']}")
            print(f"Synced {count} recordings. No recordings were deleted from the pendant.")
        elif args.command == "delete":
            if not args.confirm:
                raise ValueError("Deletion requires --confirm and a verified local recording metadata file")
            metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
            if metadata.get("verified") is not True:
                raise ValueError("Metadata does not describe a verified download")
            wav_path = args.metadata.parent / metadata["wav"]
            if not wav_path.is_file() or wav_path.resolve().parent != args.metadata.resolve().parent:
                raise ValueError("Matching local WAV is missing")
            # Revalidate the saved audio, not just a modifiable metadata flag.
            import wave, zlib
            with wave.open(str(wav_path), "rb") as wav:
                if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != 16000:
                    raise ValueError("Saved WAV format mismatch")
                pcm = wav.readframes(wav.getnframes())
            if len(pcm) != metadata["pcm_bytes"] or zlib.crc32(pcm) != metadata["pcm_crc32"]:
                raise ValueError("Saved WAV checksum mismatch; device deletion refused")
            await device.request(4, struct.pack("<III", metadata["id"], metadata["pcm_bytes"], metadata["pcm_crc32"]))
            print("Matching recording deleted from pendant; verified local WAV retained.")
        elif args.command == "format":
            if not args.confirm:
                raise ValueError("Maintenance requires --confirm after exporting and deleting every device note")
            print("Checking empty device journal. Maintenance can take up to ten minutes; keep power connected.")
            await device.format_storage(confirmed=True)
            print("Storage erased, verified and ready for new recordings. Local notes and Bluetooth bonds retained.")


def main():
    parser = argparse.ArgumentParser(description="AURA local companion")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("scan", help="Find nearby AURA devices in physical pairing mode")
    status = sub.add_parser("status")
    status.add_argument("--device", required=True, help="Bluetooth address from scan")
    sync = sub.add_parser("sync", help="Resume and verify saved audio; never auto-delete")
    sync.add_argument("--device", required=True)
    sync.add_argument("--output", type=Path, default=Path("recordings"))
    sync.add_argument("--transcribe", action="store_true")
    process = sub.add_parser("transcribe", help="Transcribe an existing audio file locally")
    process.add_argument("file", type=Path)
    for command in [sync, process]:
        command.add_argument("--model", default="base", help="faster-whisper model or local model directory")
        command.add_argument("--language", default=None, help="Optional language code; default auto-detect")
        command.add_argument("--ollama", default=None, help="Optional installed localhost Ollama model for refined notes")
        command.add_argument("--upload", action="store_true", help="Explicitly upload the generated note to the configured portal")
    delete = sub.add_parser("delete", help="Explicitly delete one already verified device recording")
    delete.add_argument("--device", required=True)
    delete.add_argument("--metadata", type=Path, required=True)
    delete.add_argument("--confirm", action="store_true")
    maintenance = sub.add_parser("format", help="Erase reusable storage only after every device note was exported and deleted")
    maintenance.add_argument("--device", required=True)
    maintenance.add_argument("--confirm", action="store_true", help="Confirm maintenance; firmware also requires a recent ten-second physical hold")
    upload = sub.add_parser("upload", help="Explicitly upload an existing .note.json to the notes portal")
    upload.add_argument("file", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "sync" and args.upload and not args.transcribe:
            raise ValueError("sync --upload also requires --transcribe; raw audio is never uploaded")
        if args.command == "transcribe":
            if not args.file.is_file():
                raise ValueError("Audio file does not exist")
            note = transcribe(args.file, args.model, args.language)
            if args.ollama:
                note = refine_with_ollama(note, args.ollama)
            for path in write_note(note, args.file):
                print(path)
            if args.upload:
                print(json.dumps(upload_note(args.file.with_suffix(".note.json")), indent=2))
        elif args.command == "upload":
            print(json.dumps(upload_note(args.file), indent=2))
        else:
            asyncio.run(bluetooth(args))
    except (Exception, KeyboardInterrupt) as error:
        print(f"AURA: {error}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
