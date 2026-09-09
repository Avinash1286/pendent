# Real Android smoke instrumentation

`com.aura.notes.SmokeInstrumentation` runs on an actual Android runtime through `android.app.Instrumentation`. It has no JUnit, AndroidX, Robolectric, fake MediaCodec, or substituted SQLite implementation. Compilation alone is not execution. A runtime result is successful only when the instrumentation finishes with `Activity.RESULT_OK` and `resultdetailJSON.passed` is true.

The test APK contains four exact public C-generated archive fixtures, with three paired physical-receipt fixtures. `assets/fixtures/index.json` records each repository origin, byte length, SHA-256, receipt, and expected source duration. `prepare_assets.py` reproduces those copies. These are synthetic reference captures, not recordings from a microphone or assembled device.

The test-only exported `FixtureProvider` serves a fixed allowlist of those public assets and one deterministic corrupt variant. It accepts only read-only `content://com.aura.notes.tests.fixtures/...` access, has no arbitrary path API, and cannot serve the user library. The provider belongs to the **test APK only**. It permits the production store's real SAF/content-URI path to be exercised without weakening the production import boundary. Small assets are materialized in the provider's private cache and returned through read-only descriptors; no potentially blocked pipe writer is used.

The provider uses Java and Android APIs only. Android loads it in the test APK's separate process, whose classloader does not inherit the target APK's Kotlin runtime. The instrumentation runner itself executes in the target process.

Instrumentation wraps the real target context only to place files and databases in a fresh private test namespace. ContentResolver, filesystem calls, directory fsync, Android SQLite, MediaExtractor, and MediaCodec remain real. It neither clears nor modifies the user's normal AURA library. Its private fixture, WAV and recovery artifacts remain in cache for inspection.

Checks cover:

- Exact fixture and physical-receipt identities.
- Three actual platform Opus decodes through EOS, PCM WAV headers, nonzero audio, decoder identity, and exact retained sample counts at the reported 16 or 48 kHz output rate.
- Existing decoder-output preservation and refusal of incomplete Ogg input.
- Content-provider import into the real store and SQLite inventory, exact source export, idempotent retry, and reopening through a new store instance.
- Manual note/context edits without changing source bytes, terminal receipt or immutable bundle metadata.
- Late attachment of physical OPEN proof while retaining the derived interrupted-seal distinction and unknown original duration.
- Retention of corrupt, unsealed or conflicting imports without publishing a new ready library row.
- Rebuilding inventory from a complete previously decoded bundle, refusal to silently downgrade lost physical provenance, and preservation of a changed source during cold reconciliation.

The cold-recovery cases create concrete on-disk conditions inside the isolated namespace; they do not claim process-kill or sudden-power-loss testing. PCM hashes are reported as runtime evidence rather than compared bit-for-bit across different legal platform decoder implementations. Tests do not establish hardware capture, NAND behavior, microphone privacy latency, Android background/BLE lifecycle, or wearable qualification.

After the production and test APKs have been built and installed on a selected emulator/device, the runner is invoked with:

```text
adb shell am instrument -w -r com.aura.notes.test/com.aura.notes.SmokeInstrumentation
```

The runner reports per-case progress and a final JSON result in the instrumentation bundle. A 240-second watchdog returns failure if the run exceeds its bound. A build log, prepared fixture index, or unexecuted test source is not a passing runtime result.
