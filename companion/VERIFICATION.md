# Companion verification

## 0.4.0 — real archive import and source preservation, 2026-09-09

The complete suite passed **95 tests** on Python **3.12.13**: 28 baseline, 33 revision-3 protocol/receiver, 11 import/decode/publication and 23 source/notes/upload tests. The actual command and result are retained in [companion-integration.txt](../firmware/a04/verification/companion-integration.txt). These tests use the companion environment, including pinned PyAV 18.1.0; the firmware tool environment alone does not include the desktop decoder.

The new path reads actual C-generated Opus archives, verifies immutable manifests/packets/seals, commits their records to an on-disk SQLite transaction, compares the C receipt, publishes a verified raw archive/WAV/source bundle, and checks exact duration. Independent FFmpeg decoding agrees with the desktop decoder. Finalized 10/20 ms fixtures retain exactly **120,847 samples**; the interrupted fixture retains **120,600 samples** with the original duration explicitly unknown. Synthetic source audio and checked-in fixtures make this reproducible without private recordings.

Fault tests cover interrupted publication and repair, corrupt existing files, decoder failure, exclusive importer ownership, replay after reopening, torn archives, preserved interrupted/final revisions, source-metadata substitution and preservation of previous note JSON. An independent review caught a temporary SQLite database accepting a receipt; empty/in-memory paths are now rejected and regression-tested. SQLite/file flush calls are exercised, but these tests do not qualify a storage device against physical power loss.

The final independent review added 11 regressions for source replacement during inference and revision publication ordering. Transcription now consumes a private snapshot matching the initially verified WAV; changing the original source or its sidecar cannot attach another identity. A swap-and-restore during lazy inference cannot change the snapshot consumed by the model. Prior note revisions are flushed and their POSIX directory chain synced before the current note is replaced. Preparation failures preserve the current note, and retries verify/resync an existing revision. POSIX call ordering/failure handling was simulated on this Windows host; Windows file flush and replacement were exercised directly, without a directory-durability or physical power-loss guarantee. A repeat real Whisper run after these fixes produced the identical public fixture hash below.

The actual CLI imported `firmware/a04/fixtures/capture-20ms.aura` and ran local **faster-whisper 1.2.1 / tiny.en**. The resulting [synthetic note fixture](tests/assets/a04-capture.note.json) retains source identity, unknown capture time, bookmarks at samples 8,000 and 32,000, transcript segments and method metadata. Its SHA-256 is `dc0af0515c69fec8a981fac732c1d9e056559b1de547e89d4c642618024c652c`.

The real Python uploader then sent that note through local Next.js and Convex. [The integration report](../portal/verification/a04-provenance-local.json) records successful owner authentication, token rotation without duplication, token revocation, owner isolation, source-conflict rejection, retained original text after owner edits and consent-controlled context retrieval. This exercised the real local services and synthetic HTTP account flow; it was not a browser or production-cloud test. Synthetic notes were archived, tokens revoked and sessions signed out.

Run the suite from `companion/` with `uv run --locked python -m unittest discover -s tests -v`. [Import commands and bundle/recovery semantics](README.md#a04-archive-import--040) describe the working path. A04 PDM/NAND/BLE, mobile lifecycle, physical-device identity, account cloud deployment and real pendant execution remain outstanding. No importer operation sends an ACK or deletion request to a pendant.

`uv build --out-dir ../.scratch/omi-review/companion-dist` built the **0.4.0 source distribution and wheel** successfully. The importer help command and pinned lockfile also resolve successfully; generated packages are local reproducible build outputs.

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
