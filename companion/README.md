# AURA local companion

Python3.12, Bleak3 and faster-whisper. The companion transfers committed audio from AURA, checks each packet and the complete recording, creates a normal WAV, and transcribes locally. It runs on Windows, macOS and Linux with a supported Bluetooth adapter. It is a desktop companion; this package is not an iOS/Android app.

## A04 archive import — 0.4.0

The new local file path connects the C Opus encoder's **experimental revision-3 archive** to verified audio, transcription and portal provenance. It does not provide A04 Bluetooth or firmware for a physical pendant. A03 `scan`/`sync` commands below still use their original v1 protocol; old experimental v2 and AOC1 test-container bytes are rejected by this importer.

From `companion/`, with the pinned dependencies installed:

```sh
uv run --locked aura import-capture ../firmware/a04/fixtures/capture-20ms.aura --output recordings
uv run --locked aura import-capture ../firmware/a04/fixtures/capture-20ms.aura --output recordings --transcribe --model tiny.en --language en
```

These checked-in fixtures contain synthetic test speech. The second command runs real local Whisper transcription; initial model download may require network access. Add `--upload` only when you want the resulting text and provenance sent to your configured portal. `--upload` requires `--transcribe`. Raw audio remains local.

Import verifies a bounded archive snapshot, commits the complete source and terminal receipt in SQLite, exports Ogg Opus/mono 16 kHz WAV and publishes `.capture.json` last. The `.aur`, `.wav`, `.capture.json` and `.receipts/` files together preserve the source and its verification; `.opus` is a portable listening export. Keep the bundle and back it up. A file-level commit does not establish physical flash/power-loss guarantees, and this command sends no receipt or deletion request to a pendant.

Each filename binds the device, capture and terminal revision digest. Repeat imports verify and reuse a committed bundle without re-decoding it. New exports record decoder/library versions. A missing final sidecar after interrupted publication can be repaired by reimport; conflicting or corrupt existing files are preserved and rejected. One OS-held lock serializes import into each output directory. The input bound is 320 MiB, the protocol payload bound 256 MiB and the metadata bound 1,000 bookmarks; production mobile/storage limits still need measurement.

Interrupted source recovery is explicit:

```sh
uv run --locked aura import-capture ../firmware/a04/fixtures/capture-20ms-interrupted.aura --output recordings --allow-interrupted
```

Only complete verified records are retained. The original total duration remains unknown; a bookmark in lost encoder-tail audio is labelled unavailable. A recovered prefix and a later finalized source remain separate local revisions. The portal currently returns a source conflict for those differing revisions under one capture identity until an explicit review/promotion workflow is implemented.

Transcription rechecks the sibling source archive, receipt, exact WAV hash/dimensions and recovery metadata before attaching provenance. Notes preserve segments, method/model/version, capture time confidence and bookmarks. Unknown time stays unknown. Existing note JSON is saved under `.note-revisions/` before a different current note replaces it, including when a sidecar was accidentally removed. Hashes and capture IDs detect inconsistency; they do not authenticate a physical device.

Inference reads a private WAV snapshot verified against the initial source, then rechecks the original bundle before attaching that identity. Temporary snapshots are removed on normal/error exit; an abrupt process termination may leave one in the operating system's temporary directory. Revision publication flushes files and, on POSIX, their directory chain before replacing the current note. Windows uses file flush and atomic replacement without an equivalent directory-persistence guarantee here. Preserve backups; these operations have not been physically power-cut qualified.

[Wire specification and C implementation](../firmware/a04/ARCHIVE.md) · [Portal source contract](../docs/a04/portal-provenance.md) · [Real synthetic transcription fixture](tests/assets/a04-capture.note.json) · [Local portal integration evidence](../portal/verification/a04-provenance-local.json).

## Install and run

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then from this directory:

```sh
uv sync --locked
uv run aura --help
uv run aura scan
uv run aura status --device DEVICE_ADDRESS
uv run aura sync --device DEVICE_ADDRESS --output recordings --transcribe
```

Hold the idle pendant's recording face for three seconds to open its pairing window. The operating system may ask to pair. Replace DEVICE_ADDRESS with the value returned by scan; on macOS this may be an OS-assigned UUID. A03 firmware implements the [shared protocol](../docs/ble-protocol.md). Real Bluetooth/board operation requires the hardware bring-up checks; tests here use a simulated GATT peer.

`sync` saves `.wav` and verified metadata `.json`. Stop recording and wait for saving to finish before syncing; A03 rejects audio reads during an active capture. It keeps partial PCM for resuming interrupted transfers and never deletes device recordings. Rerunning sync checks an existing WAV's complete PCM checksum, length, format and matching recording metadata, then reuses it without transferring its audio again. A missing WAV is downloaded even if a receipt exists. Corrupt or conflicting files are preserved and rejected; inspect them or choose a separate output directory before retrying.

Filenames contain the **recording ID** and audio CRC, not a unique hardware identity. Use a separate output directory for each pendant and one sync process per directory. AURA v1 does not provide an authenticated device identifier. CRC detects accidental corruption; it is not a cryptographic authenticity guarantee.

If a previous run stopped after writing the WAV but before publishing its receipt, sync verifies the WAV against the device's current recording metadata and repairs the missing receipt. Files are flushed before atomic publication. The device copy remains available until you explicitly delete it; file-level replacement does not guarantee an atomic transaction across all files or survival of every filesystem/power fault.

## Local transcription and notes

```sh
uv run aura transcribe recordings/your-recording.wav
uv run aura transcribe recordings/your-recording.wav --model tiny.en --language en
```

The default multilingual `base` Whisper model runs on the CPU with8-bit inference. The first transcription downloads model files from the upstream model host; after the cache is populated, audio processing is local. No audio is uploaded by these commands. `--model` can point to a local CTranslate2 Whisper model directory for an offline installation. Adding the explicit `--upload` flag uploads the resulting text note, as described below; the original audio stays local.

Each transcription creates `.note.json` and Markdown with timestamps. The default summary is an explicitly labeled extractive baseline that selects original sentences; it does not pretend to be an LLM. Suggested actions match explicit phrases in the speaker's words and remain drafts.

During `sync --transcribe`, the companion first transfers the recordings, closes the Bluetooth session, then processes verified WAVs locally. Slow transcription or an upload failure cannot keep the radio session open or prevent already downloaded later notes from being processed. Failures still produce a nonzero result with recovery guidance. Rerunning `sync --transcribe` reuses verified audio but currently processes the notes again; it is not an automatic work-queue service. To retry just an upload, run `aura upload PATH.note.json`.

A `.sync.json` receipt records the last processing stage and its started/completed/failed status with a bounded error code. It contains no transcript, credential or raw exception. “Completed” refers to the named stage, not necessarily the whole pipeline; a run interrupted after transcription may still need note generation. The receipt does not schedule uploads or retries.

Each note file is written through a flushed temporary file and atomic replacement. The `.note.json` file is authoritative, while Markdown is a regenerable presentation of it; the pair is not a multi-file filesystem transaction.

For a more flexible local summary, install [Ollama](https://ollama.com/) and a suitable model separately, then pass its installed name:

```sh
uv run aura transcribe recordings/your-recording.wav --ollama YOUR_INSTALLED_MODEL
```

This optional request goes only to `http://127.0.0.1:11434`. The result is schema-checked and labeled as model-generated. Review names, dates, numbers and suggested actions against the audio. No tasks, messages or calendar events are created automatically.

## Explicit deletion

```sh
uv run aura delete --device DEVICE_ADDRESS --metadata recordings/VERIFIED_RECORDING.json --confirm
```

The companion rechecks the local WAV's format, size and CRC before sending a deletion request. Firmware must also match the recording ID, length and CRC. Local audio is retained. Keep a separate backup before deleting an irreplaceable device recording.

## Reuse device storage

The first firmware release uses an append-only journal. Individual deletion adds a tombstone; capacity is reclaimed through explicit maintenance after every recording has been exported and deleted. It never automatically erases a live recording.

1. Sync and verify all recordings, then use `delete --metadata ... --confirm` for each one.
2. Hold the idle pendant face for ten seconds. This grants maintenance permission for thirty seconds; the hold alone does not erase anything.
3. Run the command below. Keep the unit on its reviewed power supply while all NAND blocks are erased and verified.

```sh
uv run aura format --device DEVICE_ADDRESS --confirm
```

The companion requires an empty device STATUS, and the firmware independently requires no active capture, committed deletion of all notes, and the recent physical hold. It retains Bluetooth bonds, recording-ID continuity and all local files. The operation can take up to ten minutes. If disconnected or timed out, do not automatically repeat the command: keep power connected and reconnect to inspect recovery. The MCU stores erase intent before starting and resumes an interrupted erase before exposing notes again. Do not mass-erase the MCU's NVS partition while that recovery is pending. This maintenance operation does not guarantee secure erasure of data in failed NAND blocks.

## Explicit portal upload

The portal stores text notes in its Next.js/Convex backend. Configure its private ingestion credential in your environment; never commit a real token. `.env.example` lists the names. `uv run --env-file .env.local ...` can load a local file, or set variables in your shell:

```powershell
$env:AURA_PORTAL_URL = 'https://YOUR-PORTAL.vercel.app'
$env:AURA_INGEST_TOKEN = 'YOUR-PRIVATE-INGESTION-TOKEN'
uv run aura upload recordings/your-recording.note.json
```

You can opt into upload after local processing:

```sh
uv run aura transcribe recordings/your-recording.wav --upload
uv run aura sync --device DEVICE_ADDRESS --output recordings --transcribe --upload
```

`sync --upload` requires `--transcribe`. There is no upload by default. The companion sends title, transcript, summary, suggested actions, tags and a recording timestamp to `/api/ingest` with a bearer token; it never sends the WAV. For legacy notes without capture provenance, the upload identity is a SHA-256 of the sibling WAV, so retrying or editing a note's title does not create another identity. If its audio file is absent, a canonical note hash supplies a stable fallback. Prefer retaining the WAV for a consistent identity across edits. Legacy `recordedAt` comes from explicit note metadata, then the verified recording's time, then source-file modification time when the capture time is unknown. A04 captured notes instead retain their manifest time/confidence (including unknown time as zero), immutable device/capture identity, archive receipt digest, segments, transcription method and bookmarks. Token rotation deduplicates these captures within the authenticated owner; a conflicting source revision is rejected for review. No source authenticity is inferred from an ID or checksum.

The client permits HTTPS, plus loopback HTTP for local development, and refuses redirects entirely so the bearer token cannot be forwarded to a different origin. A successful response must explicitly confirm `{id, stored:true}`. A failure preserves local files and is not silently retried. Public demonstration portals may lack private ingestion configuration; the command requires your configured backend credential.

## Verification

```sh
uv run python -m unittest discover -s tests -v
uv run aura transcribe tests/assets/sample.wav --model tiny.en --language en
```

Tests cover corrupt packets, metadata validation, interrupted-transfer resume, verified download reuse, incomplete-publication recovery, WAV formatting, complete CRC verification, atomic-file failure handling, no automatic device deletion, processing after disconnect, extractive-note provenance, explicit maintenance confirmation/magic/timeout, stable upload identity, URL validation and an actual loopback HTTP upload with redirect refusal. See [verification results](VERIFICATION.md) for the latest executed count. The synthetic speech fixture was generated locally through Windows speech synthesis solely for the transcription smoke test. These checks do not establish acoustic quality, the physical BLE link or a deployed production Convex backend.

Upstream: [Bleak](https://bleak.readthedocs.io/en/latest/) and [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Installed versions are pinned by `uv.lock`.
