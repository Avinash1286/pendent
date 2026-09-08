import argparse
import asyncio
import json
from pathlib import Path
import struct
import sys

from .device import connect, discover
from .files import atomic_write_text
from .notes import transcribe, refine_with_ollama, write_note
from .upload import upload_note


def _sync_receipt(path: Path, stage: str, status: str):
    """A recovery hint only: no source text, credentials, or automatic retry policy."""
    receipt = {"version": 1, "wav": path.name, "stage": stage,
               "status": status, "success": status == "completed"}
    if status == "failed":
        receipt["error_code"] = "upload_not_confirmed" if stage == "upload" else "stage_failed"
    atomic_write_text(path.with_suffix(".sync.json"), json.dumps(receipt, indent=2))


async def _process_saved_recording(path: Path, args):
    stage = "transcription"
    try:
        _sync_receipt(path, stage, "started")
        note = await asyncio.to_thread(transcribe, path, args.model, args.language)
        _sync_receipt(path, stage, "completed")
        if args.ollama:
            stage = "refinement"
            _sync_receipt(path, stage, "started")
            note = await asyncio.to_thread(refine_with_ollama, note, args.ollama)
            _sync_receipt(path, stage, "completed")
        stage = "notes"
        _sync_receipt(path, stage, "started")
        for saved_path in await asyncio.to_thread(write_note, note, path):
            print(f"Saved note: {saved_path}")
        _sync_receipt(path, stage, "completed")
        if args.upload:
            stage = "upload"
            _sync_receipt(path, stage, "started")
            await asyncio.to_thread(upload_note, path.with_suffix(".note.json"))
            _sync_receipt(path, stage, "completed")
            print(f"Portal confirmed storage: {path.with_suffix('.note.json')}")
    except Exception:
        # External model/server failures may echo private source text or tokens.
        # Keep both the receipt and aggregate CLI error limited to known stages.
        receipt_warning = ""
        try:
            _sync_receipt(path, stage, "failed")
        except Exception:
            receipt_warning = " The status receipt could not be saved; check local storage."
        outcome = "was not confirmed" if stage == "upload" else "did not complete"
        return f"{path}: {stage} {outcome}; local files retained.{receipt_warning}"
    return None


async def _sync(args):
    if args.upload and not args.transcribe:
        raise ValueError("sync --upload also requires --transcribe; raw audio is never uploaded")
    paths = []
    failures = []
    session_closed = False
    try:
        async with connect(args.device) as device:
            try:
                status = await device.status()
                if status["state"] in (1, 2):
                    failures.append("Stop the current recording and wait for it to save before syncing.")
                else:
                    await device.set_time()
                    async for recording in device.recordings():
                        try:
                            path = await device.download(recording, args.output)
                        except Exception:
                            failures.append(f"Recording {recording.id:08x}: download not verified; partial files retained in {args.output}.")
                            continue
                        paths.append(path)
                        print(f"Verified and saved: {path}")
            except Exception:
                failures.append("Bluetooth transfer did not complete; reconnect and resume sync. Partial files are retained.")
        session_closed = True
    except Exception:
        failures.append("Bluetooth session could not be opened or closed cleanly; local processing was not started.")

    # Do not retain the BLE session through model loading, inference or HTTP.
    # If disconnect itself failed, preserve the files and require an explicit retry.
    if session_closed and args.transcribe:
        for path in paths:
            failure = await _process_saved_recording(path, args)
            if failure:
                failures.append(failure)
    print(f"Synced {len(paths)} recordings. No recordings were deleted from the pendant.")
    if failures:
        retained = "\n".join(f"  {path}" for path in paths) or "  No WAVs verified during this run."
        raise RuntimeError(
            f"Sync finished with {len(failures)} failure(s):\n"
            + "\n".join(f"- {failure}" for failure in failures)
            + f"\nVerified WAVs retained:\n{retained}\n"
            + "Retry transfer with sync, local processing with 'aura transcribe <WAV>', "
            + "or upload with 'aura upload <note.json>'. No retries were scheduled."
        )


async def bluetooth(args):
    if args.command == "scan":
        devices = await discover()
        for device, advert in devices:
            print(json.dumps({"address": device.address, "name": advert.local_name or device.name}))
        if not devices:
            print("No AURA found. Hold the idle pendant face for three seconds to open pairing.")
        return
    if args.command == "sync":
        return await _sync(args)
    async with connect(args.device) as device:
        if args.command == "status":
            print(json.dumps(await device.status(), indent=2))
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
