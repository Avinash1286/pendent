# AURA local companion

Python3.12, Bleak3 and faster-whisper. The companion transfers committed audio from AURA, checks each packet and the complete recording, creates a normal WAV, and transcribes locally. It runs on Windows, macOS and Linux with a supported Bluetooth adapter. It is a desktop companion; this package is not an iOS/Android app.

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

`sync` saves `.wav` and verified metadata `.json`. Stop recording and wait for saving to finish before syncing; A03 rejects audio reads during an active capture. It keeps partial PCM for resuming interrupted transfers and never deletes device recordings. Rerunning sync may download the same saved recording again; filenames include the device ID and audio CRC. It rejects corrupted packets and never publishes a WAV when the complete checksum fails. CRC detects accidental corruption; it is not a cryptographic authenticity guarantee.

## Local transcription and notes

```sh
uv run aura transcribe recordings/your-recording.wav
uv run aura transcribe recordings/your-recording.wav --model tiny.en --language en
```

The default multilingual `base` Whisper model runs on the CPU with8-bit inference. The first transcription downloads model files from the upstream model host; after the cache is populated, audio processing is local. No audio is uploaded by these commands. `--model` can point to a local CTranslate2 Whisper model directory for an offline installation. Adding the explicit `--upload` flag uploads the resulting text note, as described below; the original audio stays local.

Each transcription creates `.note.json` and Markdown with timestamps. The default summary is an explicitly labeled extractive baseline that selects original sentences; it does not pretend to be an LLM. Suggested actions match explicit phrases in the speaker's words and remain drafts.

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

`sync --upload` requires `--transcribe`. There is no upload by default. The companion sends title, transcript, summary, suggested actions, tags and a recording timestamp to `/api/ingest` with a bearer token; it never sends the WAV. The upload identity is a SHA-256 of the sibling WAV, so retrying or editing a note's title does not create another identity. If its audio file is absent, a canonical note hash supplies a stable fallback. Prefer retaining the WAV for a consistent identity across edits. `recordedAt` comes from explicit note metadata, then the verified recording's time, then source-file modification time when the capture time is unknown.

The client permits HTTPS, plus loopback HTTP for local development, and refuses redirects entirely so the bearer token cannot be forwarded to a different origin. A successful response must explicitly confirm `{id, stored:true}`. A failure preserves local files and is not silently retried. Public demonstration portals may lack private ingestion configuration; the command requires your configured backend credential.

## Verification

```sh
uv run python -m unittest discover -s tests -v
uv run aura transcribe tests/assets/sample.wav --model tiny.en --language en
```

Twelve tests cover corrupt packets, metadata validation, interrupted-transfer resume, WAV formatting, complete CRC verification, no automatic device deletion, extractive-note provenance, explicit maintenance confirmation/magic/timeout, stable upload identity, URL validation and an actual loopback HTTP upload with redirect refusal. The synthetic speech fixture was generated locally through Windows speech synthesis solely for the transcription smoke test. These checks do not establish acoustic quality, the physical BLE link or a deployed production Convex backend.

Upstream: [Bleak](https://bleak.readthedocs.io/en/latest/) and [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Installed versions are pinned by `uv.lock`.
