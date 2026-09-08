# Companion verification

## 0.3.1 — recovery changes, 2026-09-09

`uv run --locked python -m unittest discover -s tests -v` passed **28 tests** on Python **3.12.13**: the 12 previous cases, eight download/publication recovery cases and eight CLI lifecycle cases. The new suite verifies repeat sync without Bluetooth audio reads, corrupt/truncated WAV rejection, conflicting receipt rejection, missing-WAV re-download, repair after interrupted receipt publication, and preservation of a previous file when atomic replacement fails.

CLI tests use a fake async connection and synthetic model/upload functions. They verify that all transfers and disconnect precede processing, later records continue after a failure at each processing stage, interrupted inventory preserves already verified work, disconnect cleanup failure prevents processing, active capture blocks sync, and plain sync never processes or uploads. Failure receipts and aggregate errors exclude injected transcript/token strings. These are controlled failure simulations, not physical power-cut or radio tests.

`uv build --out-dir ../.scratch/omi-review/companion-dist` successfully built the **0.3.1 source distribution and wheel**. `uv run --locked aura sync --help` also passed. Dependency versions stayed fixed; only the local package version changed in the lockfile.

Sync writes a `.sync.json` receipt describing the **last processing stage**, its started/completed/failed status and a bounded error code. A completed transcription stage alone does not mean notes or cloud storage completed. A status receipt is not a scheduler: no upload or retry is initiated on restart. WAVs, notes and the pendant's recordings remain available for explicit recovery. Markdown and JSON replacement are individually atomic, not a multi-file transaction.

The code received a separate static review with no must-fix data-loss regressions found within these changes. Independent writers to one output directory, physical filesystem/power-loss durability, mobile behavior and production backend operation remain outside this verification.

## Earlier baseline — 2026-09-08

On 2026-09-08, `uv run --locked python -m unittest discover -s tests -v` completed **12 tests successfully** on Python 3.12. The tests include five existing transfer/transcription-structure cases and seven maintenance/upload cases.

The upload integration test started an actual loopback HTTP server, sent the JSON contract and bearer header, checked the confirmed note ID, then returned a redirect and verified no redirected request was made. Source WAV hashing is stable across note-title edits. A missing WAV uses a canonical note hash. Unsafe HTTP origins, embedded URL credentials, malformed note arrays and missing upload configuration are rejected.

Maintenance tests confirm that no FORMAT is sent without explicit confirmation and an empty idle STATUS. The accepted request contains exactly `ERAS` and uses the special 600-second timeout. Firmware independently enforces the physical hold and committed tombstones.

`aura --help`, `aura format --help` and `aura upload --help` were exercised. The earlier locally synthesized speech fixture and Whisper transcription smoke result remain under `tests/assets/`.

No physical pendant, radio transfer or deployed Convex backend was exercised by these tests. Live portal integration requires the matching server route and private ingestion credential; it is not silently replaced by a mock in the shipping companion.
