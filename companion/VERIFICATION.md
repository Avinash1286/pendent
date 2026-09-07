# Companion verification

On 2026-09-08, `uv run --locked python -m unittest discover -s tests -v` completed **12 tests successfully** on Python 3.12. The tests include five existing transfer/transcription-structure cases and seven maintenance/upload cases.

The upload integration test started an actual loopback HTTP server, sent the JSON contract and bearer header, checked the confirmed note ID, then returned a redirect and verified no redirected request was made. Source WAV hashing is stable across note-title edits. A missing WAV uses a canonical note hash. Unsafe HTTP origins, embedded URL credentials, malformed note arrays and missing upload configuration are rejected.

Maintenance tests confirm that no FORMAT is sent without explicit confirmation and an empty idle STATUS. The accepted request contains exactly `ERAS` and uses the special 600-second timeout. Firmware independently enforces the physical hold and committed tombstones.

`aura --help`, `aura format --help` and `aura upload --help` were exercised. The earlier locally synthesized speech fixture and Whisper transcription smoke result remain under `tests/assets/`.

No physical pendant, radio transfer or deployed Convex backend was exercised by these tests. Live portal integration requires the matching server route and private ingestion credential; it is not silently replaced by a mock in the shipping companion.
