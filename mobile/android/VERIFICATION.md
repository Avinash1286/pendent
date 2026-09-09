# Android verification — 2026-09-09

The current native A04 app built with **zero Android lint findings** and passed
**19 Android runtime cases / 366 assertions** on an Android 10 / API 29 x86-64
emulator. The run took 22.846 seconds. It retains the original nine local-import
cases and adds ten cases for the [durable download owner](DOWNLOADS.md), actual
SQLite rollback/replay, ownership cleanup and decoded-library handoff.

The current Kotlin core passes **30 groups / 82,213 checks**, including six
incremental-validator groups / 49,471 checks, seven response-fragment groups /
32,159 checks, seven transfer-wire groups / 338 checks and the complete-archive
checks. It uses 19 complete C-generated archives and rejects an additional raw
prefix. Exact ACK3/Ogg comparisons and independent FFmpeg sample counts pass.
Both file import and partial-download replay now use one canonical validator.

The [earlier local-import checkpoint](https://github.com/Avinash1286/pendent/tree/1a790597da5095423fdada9d86425f1ce4654a62/mobile/android)
and its `a04-android-local-dev` release remain available with their original
nine-case evidence. The current development APK includes the new storage and
protocol classes, but the Activity still exposes local file import. GATT,
enrollment and the foreground download coordinator are not integrated.

These results cover the source and development APKs identified below. They establish an exercised Android file-import, storage, recovery, and platform-decoding foundation. They do not establish a working physical pendant or a qualified release.

## Evidence map

| Evidence | Observed result and scope |
| --- | --- |
| [Installed toolchain](verification/installed-toolchain.json) | Actual executable versions, SDK package metadata, archive/executable hashes, and usable WHPX acceleration; this installation snapshot alone does not claim app execution. |
| [Runtime emulator boot](verification/emulator-download-runtime-boot.json) | Preserved `AuraApi29`, `emulator-5554`, API 29, observed `sys.boot_completed=1` and framework ready before this run. The record separately retains eventual shutdown; boot alone is not a runtime test. |
| [Build report](verification/android-build.json) and [build log](verification/build-output.txt) | Both debug APKs built; lint Fatal 0, Error 0, Warning 0, Information 0. Build inputs were unchanged during the build. |
| [Final Android runtime report](verification/android-runtime.json) and [instrumentation output](verification/instrumentation-output.txt) | Both APK installations reported success; 19 cases and 366 assertions passed. The report retains per-case and total execution time. Inputs were unchanged during the test. |
| [Current JVM report](core/verification/kotlin-core.json) and [JVM transcript](core/verification/jvm-host.txt) | 30 groups / 82,213 checks: shared complete/incremental validation, C/Python/Kotlin byte-contract comparisons, actual C command/reply/fragments and independent FFmpeg sample-count validation. No Android decoding or GATT claim from this report. |

The reports retain their exact UTC generation times. The instrumentation transcript contains both `resultdetailJSON.passed=true` and `INSTRUMENTATION_CODE: -1` (`Activity.RESULT_OK`). A zero `adb` process exit code by itself is not the success criterion.

## Environment actually used

The installed environment records Temurin **JDK/Javac 17.0.20.1**, **Gradle 9.4.1**, SDK platform **37.0 revision 2**, build tools **36.0.0**, platform tools **37.0.1**, and emulator **37.1.11**. The app compiles/targets API 37 and has minimum API 29; execution in this report used the **API 29 default x86-64 system image, revision 8**.

The emulator fingerprint was:

```text
Android/sdk_phone_x86_64/generic_x86_64:10/QSR1.210820.001/7663313:userdebug/test-keys
```

Boot evidence records WHPX CPU acceleration, SwiftShader graphics, 1,536 MiB RAM, one virtual CPU, and a 480×800 display at 240 dpi. The emulator ran headless with host audio disabled. Windows virtualization settings were not changed by this setup. Successful PCM decoding here is therefore not evidence of audible playback through a phone speaker or headphones.

## Exact build and runtime binding

The build and runtime reports contain the same **47 source/configuration/fixture
hashes**, including the verification runner. Both APK hashes match the build
report and runtime installation entries. The runtime's referenced build-report
digest matches the actual JSON file. The core report separately binds 61 current
source/fixture files before and after its JVM/FFmpeg run. Android's download
fixture copies match the exact owned C archive/physical-receipt files.

The [build report's `artifacts` entries](verification/android-build.json) give both APK byte lengths and SHA-256 values. The [runtime report](verification/android-runtime.json) repeats the installed APK digests and binds the exact build-report bytes through `build_report_sha256`. Use those machine-readable values when comparing a download; the development signing key on another machine can produce different APK bytes.

The retained local-import fixture-index digest is `7c089eaaeb7ad233e36c93138f6c7fd21a93d9adc1592085925dbddf29d7617f`; the new download fixture-index digest is `a160804c8090e09ecd2b13436e27d2ed334b65cdf819b12ad715b3d3882d96cd`. Full source, WAV, log, and verification-script hashes are retained in the machine-readable reports; the table does not replace them.

These hashes bind the observed local build and test run. They are not publisher signatures, device attestation, or a claim that another machine's development signing key will produce identical APK bytes. The APKs use development debug signing, not production release signing.

## What the Android tests exercised

The [instrumentation implementation](app/src/androidTest/kotlin/com/aura/notes/SmokeInstrumentation.kt) used actual Android `ContentResolver`, filesystem synchronization, SQLite, `MediaExtractor`, and `MediaCodec`. It did not substitute fake SQLite or a mocked decoder. A context wrapper redirected only the private files/database namespace to isolated test storage. The test-only content provider served fixed public synthetic fixtures and could not read the user's normal library.

The nine retained local-library cases passed:

1. Immutable C fixture asset identities.
2. Real platform Opus decoding through output EOS and exact WAV durations.
3. Preservation of an existing decoder destination and refusal of incomplete Ogg input.
4. Import through a real content provider into the actual store and SQLite inventory.
5. Idempotent retry and reopening through a fresh store instance.
6. Manual context surviving reopen without changing the original source or immutable bundle evidence.
7. Late physical **OPEN** receipt attachment remaining distinct from the export's derived interrupted seal.
8. Retention of corrupt sources, raw unsealed prefixes, and conflicting proof without publishing a new ready capture.
9. Cold inventory rebuilding from a complete decoded bundle, including refusal to silently downgrade missing known provenance and retention of changed source bytes.

Ten additional download cases passed: exact owned C SELECT/FINISH metadata;
complete-record resume and export; duplicate/conflicting READs; actual SQLite
INSERT/metadata/FINISH ABORT rollback; retained corrupt metadata/records; split
and concatenated row rejection; lifetime ownership and failed-open cleanup;
separate immutable source revisions; premature/conflicting FINISH rejection;
and finalized/OPEN handoff through the real library decoder. The process-owner
guard rejects a second opener before creating another file channel. Tests also
exercise failed file/database construction and stale double-close cleanup.

The recovery cases construct concrete filesystem/database conditions in the
isolated namespace. They are not cross-process contention, process-kill,
kernel-crash, flash-controller or sudden-power-loss tests. Android READ replies
are constructed from exact C exports and passed through `TransferWire`; the
test does not run C firmware over Bluetooth. Original export is checked through
the store API; this does not prove every document-provider UI destination works.

## Actual decoder and trim results

All three audio fixtures used **`OMX.google.opus.decoder`**, which returned mono PCM16 at **48,000 Hz**. The source archives use a 16,000 Hz source clock; retained PCM frame counts were compared at the actual decoder rate. The decoder's applied pre-skip was not removed a second time.

| Fixture | Physical receipt | Raw output frames | Retained frames | App applied remaining end trim |
| --- | --- | ---: | ---: | --- |
| `journal-0` | FINALIZED | 362,760 | 362,541 | Yes: 219 frames |
| `journal-2` | OPEN | 349,320 | 349,320 | No |
| `recorder-1` | INTERRUPTED | 143,880 | 143,880 | No |

The finalized fixture exercises a recording that ends inside its last encoded frame. The OPEN fixture exercises a complete interrupted export whose physical receipt covers only the prefix before its derived seal. Interrupted original duration remains unknown. Full output EOS, WAV shape, nonzero audio, exact retained counts, decoder identity, and resulting WAV hashes were checked or recorded.

These are generated test signals from the portable C fixture writer, not audio captured through an A04 microphone. Passing this specific platform decoder does not qualify every vendor codec, Android version, long recording, storage-pressure condition, or malformed future input.

The new owned finalized and OPEN fixtures also passed `CaptureStore.importDownload`
through `OMX.google.opus.decoder` at 48 kHz, preserving 120,847 and 116,440 source
samples respectively. Both became playback-ready; duplicate imports retained a
single library revision. The OPEN recording retained physical status OPEN,
export status INTERRUPTED and unknown original duration. Its SQLite source
remained byte-identical and exportable after library publication.

## Retained first failing attempt

The [first runtime report](verification/android-runtime-attempt-01.json), [first instrumentation transcript](verification/instrumentation-attempt-01.txt), and [associated build report](verification/android-build-attempt-01.json) are retained. That attempt is explicitly **failed**. The direct decoder checks passed, but the real provider/store import case failed with `FileNotFoundException: No content provider` after 109 assertions.

The issue was in the test fixture provider's process/classloader: its Kotlin implementation depended on runtime classes available to the target APK's instrumentation process, but not to the provider's separate test-APK process. The fixture provider was replaced with [Java using Android/Java APIs only](app/src/androidTest/java/com/aura/notes/FixtureProvider.java), retaining its fixed allowlist and read-only `content://` boundary. The production import path was not weakened to accept arbitrary file URIs, and SQLite/MediaCodec were not replaced with test doubles.

Both APKs were rebuilt and reinstalled, and the full suite was rerun. The passing report binds that final source set and those final APKs; the earlier partial pass is not counted as successful store validation.

## Earlier local-import UI smoke check

The [UI smoke record](verification/ui-smoke.json) belongs to the earlier
local-import APK. It records seven real-screen checks with synthetic fixtures:
update/restart preservation, document-picker retry, playback to completion,
keyboard layout, share-sheet payload, exact original export and system Back.
No receiving application was selected. The current change adds no download UI;
that earlier visual record is not a new APK UI test.

The first new import, saved title/context and clipboard copy occurred in the preceding passing build. A small-screen editor issue found during that UI check was then corrected with a scrollable body and resize behavior. The final APK was rebuilt, all nine instrumentation cases passed again, and the affected editor plus the flows above were checked. The [preceding passing runtime](verification/android-runtime-attempt-02.json) is retained alongside the earlier failing provider attempt. The UI record binds each screenshot to its actual APK, including the earlier empty-library image.

These are agent-driven UI observations and byte comparisons, not a claim that a generic UI automation suite or every provider has passed. The [library](verification/android-library.png), [playback](verification/android-playback.png), and [keyboard-open editor](verification/android-context-editor.png) screenshots are actual emulator captures. Returning from another activity can reset the detail scroll position; retaining that position is a remaining UI refinement.

## Limits of this result

No physical pendant, microphone/PDM input, NAND hardware, battery, charging, radio, BLE enrollment/download/reconnection, privacy-switch timing, PCB fabrication, enclosure fit, or wear test is covered. The app currently imports selected local archives; it does not implement the proposed phone BLE transport, automatic transcription, web-portal synchronization, or an Android background capture service.

Runtime coverage is API 29 only. Android 33+ callback/receiver branches, modern predictive Back behavior, audio focus with other applications, actual headset/Bluetooth route changes, OEM document providers, and newer platform codecs remain to be exercised on their target systems. No accessibility certification, store-release readiness, broad device compatibility, or physical power-loss durability is claimed by the zero-lint result.

## Reproduce and extend

The [app guide](README.md) contains setup prerequisites and build/install instructions. From the repository root, the evidence runner can rebuild both APKs and run lint, then execute the isolated suite on an explicitly selected available target:

```powershell
uv run --project companion --locked python mobile/android/scripts/verify_android.py build
uv run --project companion --locked python mobile/android/scripts/verify_android.py runtime --serial '<device-serial>'
```

The build phase uses `build.ps1 -SkipCore`; run the default `mobile/android/build.ps1` separately when reproducing the JVM/FFmpeg checks too. The runtime phase refuses changed source inputs or APKs relative to its successful build report, installs both development APKs with `adb install -r`, and records the actual result. It does not choose a target implicitly, wipe user data, uninstall an app, or flash device firmware. Preserve previous evidence before replacing a report if comparing runs, and report each platform's actual decoder, sample counts, and remaining limitations.
