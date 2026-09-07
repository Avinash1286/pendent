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

`sync` saves `.wav` and verified metadata `.json`. It keeps partial PCM for resuming interrupted transfers and never deletes device recordings. Rerunning sync may download the same saved recording again; filenames include the device ID and audio CRC. It rejects corrupted packets and never publishes a WAV when the complete checksum fails. CRC detects accidental corruption; it is not a cryptographic authenticity guarantee.

## Local transcription and notes

```sh
uv run aura transcribe recordings/your-recording.wav
uv run aura transcribe recordings/your-recording.wav --model tiny.en --language en
```

The default multilingual `base` Whisper model runs on the CPU with8-bit inference. The first transcription downloads model files from the upstream model host; after the cache is populated, audio processing is local. No audio is uploaded by these commands. `--model` can point to a local CTranslate2 Whisper model directory for an offline installation.

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

## Verification

```sh
uv run python -m unittest discover -s tests -v
uv run aura transcribe tests/assets/sample.wav --model tiny.en --language en
```

Tests cover corrupt packets, metadata validation, interrupted-transfer resume, WAV formatting, complete CRC verification, no automatic device deletion and extractive-note provenance. The synthetic speech fixture was generated locally through Windows speech synthesis solely for the transcription smoke test. These checks do not establish acoustic quality or the physical BLE link.

Upstream: [Bleak](https://bleak.readthedocs.io/en/latest/) and [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Installed versions are pinned by `uv.lock`.
