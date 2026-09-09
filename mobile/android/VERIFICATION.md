# Android verification — 2026-09-09

The current native A04 app built with **zero Android lint findings**. Its source
storage, playback and foreground recovery suite passed **29 Android runtime
cases / 428 assertions** on an Android 14 / API 34 x86-64 emulator. The nine
local-import and ten durable-download cases are retained; ten new recovery
cases exercise the actual coordinator with scripted logical replies, real
SQLite and the platform decoder.

The final smoke run took 65.355 seconds and binds the same final APKs as both
virtual-link runs below.

The separate virtual Bluetooth suite passed **4 cases / 33 assertions at each of MTU
23 and MTU 517** using the real Android GATT stack and a Python Bumble peripheral through
Netsim. It recovered both original C-generated recordings, decoded them into the
library, and revalidated them on a second connection without duplicate entries.
See the virtual-link evidence below for the exact scope and retained first failure.

The current Kotlin core passes **30 groups / 82,213 checks**, including six
incremental-validator groups / 49,471 checks, seven response-fragment groups /
32,159 checks, seven transfer-wire groups / 338 checks and the complete-archive
checks. It uses 19 complete C-generated archives and rejects an additional raw
prefix. Exact ACK3/Ogg comparisons and independent FFmpeg sample counts pass.
Both file import and partial-download replay now use one canonical validator.

The [earlier local-import checkpoint](https://github.com/Avinash1286/pendent/tree/1a790597da5095423fdada9d86425f1ce4654a62/mobile/android)
and its `a04-android-local-dev` release remain available with their original
nine-case evidence. The current development APK includes the new storage and
protocol classes, [foreground recovery coordinator and Android GATT client](RECOVERY.md). The Activity still exposes local file import. Consumer access requires ownership enrollment, a matching device radio service and Activity integration.

These results cover the source and development APKs identified below. They establish an exercised Android file-import, storage, recovery, and platform-decoding foundation. They do not establish a working physical pendant or a qualified release.

## Evidence map

| Evidence | Observed result and scope |
| --- | --- |
| [Installed toolchain](verification/installed-toolchain.json) | Actual executable versions, SDK package metadata, archive/executable hashes, and usable WHPX acceleration; this installation snapshot alone does not claim app execution. |
| [Runtime emulator boot](verification/emulator-ble-runtime-boot.json) | Separate preserved `AuraApi34Ble`, `emulator-5556`, API 34, observed boot completion and Bluetooth ON. Exact Netsim/VM identity and terminal observations are retained; boot alone is not a test. |
| [Build report](verification/android-build.json) and [build log](verification/build-output.txt) | Both debug APKs built; lint Fatal 0, Error 0, Warning 0, Information 0. Build inputs were unchanged during the build. |
| [Final Android runtime report](verification/android-runtime.json) and [instrumentation output](verification/instrumentation-output.txt) | Both APK installations reported success; 29 cases and 428 assertions passed. The report retains per-case and total execution time. Inputs were unchanged during the test. |
| [Current JVM report](core/verification/kotlin-core.json) and [JVM transcript](core/verification/jvm-host.txt) | 30 groups / 82,213 checks: shared complete/incremental validation, C/Python/Kotlin byte-contract comparisons, actual C command/reply/fragments and independent FFmpeg sample-count validation. No Android decoding or GATT claim from this report. |

The reports retain their exact UTC generation times. The instrumentation transcript contains both `resultdetailJSON.passed=true` and `INSTRUMENTATION_CODE: -1` (`Activity.RESULT_OK`). A zero `adb` process exit code by itself is not the success criterion.

## Environment actually used

The installed environment records Temurin **JDK/Javac 17.0.20.1**, **Gradle 9.4.1**, SDK platform **37.0 revision 2**, build tools **36.0.0**, platform tools **37.0.1**, and emulator **37.1.11**. The app compiles/targets API 37 and has minimum API 29; execution in the current report used the **API 34 default x86-64 system image**. Its official r04 archive advertises revision 4, while its shipped `source.properties` and installed SDK metadata identify revision 2; [the setup record](verification/ble-toolchain.json) preserves that discrepancy and exact archive hashes.

The emulator fingerprint was:

```text
Android/sdk_phone64_x86_64/emu64x:14/UE1A.230829.036.A1/11228894:userdebug/test-keys
```

Boot evidence records WHPX CPU acceleration, SwiftShader graphics, 1,536 MiB RAM, one virtual CPU, and a 480×800 display at 240 dpi. The emulator ran headless with host audio disabled. Windows virtualization settings were not changed by this setup. Successful PCM decoding here is therefore not evidence of audible playback through a phone speaker or headphones.

## Exact build and runtime binding

The build and runtime reports contain the same **57 source/configuration/fixture
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

All three current audio fixtures used **`c2.android.opus.decoder`**, which returned mono PCM16 at **48,000 Hz**. The source archives use a 16,000 Hz source clock; retained PCM frame counts were compared at the actual decoder rate. The decoder's applied pre-skip was not removed a second time.

| Fixture | Physical receipt | Raw output frames | Retained frames | App applied remaining end trim |
| --- | --- | ---: | ---: | --- |
| `journal-0` | FINALIZED | 362,760 | 362,541 | Yes: 219 frames |
| `journal-2` | OPEN | 349,320 | 349,320 | No |
| `recorder-1` | INTERRUPTED | 143,880 | 143,880 | No |

The finalized fixture exercises a recording that ends inside its last encoded frame. The OPEN fixture exercises a complete interrupted export whose physical receipt covers only the prefix before its derived seal. Interrupted original duration remains unknown. Full output EOS, WAV shape, nonzero audio, exact retained counts, decoder identity, and resulting WAV hashes were checked or recorded.

These are generated test signals from the portable C fixture writer, not audio captured through an A04 microphone. Passing this specific platform decoder does not qualify every vendor codec, Android version, long recording, storage-pressure condition, or malformed future input.

The new owned finalized and OPEN fixtures also passed `CaptureStore.importDownload`
through `c2.android.opus.decoder` at 48 kHz, preserving 120,847 and 116,440 source
samples respectively. Both became playback-ready; duplicate imports retained a
single library revision. The OPEN recording retained physical status OPEN,
export status INTERRUPTED and unknown original duration. Its SQLite source
remained byte-identical and exportable after library publication.

## Foreground recovery and virtual Bluetooth

The ten coordinator cases cover exact finalized/OPEN recovery, transaction-space
rollover, background cancellation and foreground resume, coalesced wakes,
identity/FINISH mismatch, finite reconnect/catalog budgets, unavailable sources,
source pinning across reconnect and revoked access, resolved failure counts,
and bounded failure when tiny READs cannot advance a complete record. They use
scripted connections; their timings are not radio performance measurements.

The [MTU 517 report](verification/ble-517/verification.json),
[Android transcript](verification/ble-517/instrumentation-output.txt) and
[peripheral report](verification/ble-517/peripheral.json) record four real-GATT
cases / 33 assertions in 36.540 seconds. The first connection transferred
73,674 original bytes using 298 notifications; the second used nine notifications
and no source payload bytes to repeat SELECT, explicit EOF READ and FINISH.
Both source receipts remained exact, including physical OPEN / export INTERRUPTED.
Both connections negotiated MTU 517; the peripheral reported no errors or retries.
Elapsed time includes virtual connection, SQLite and decoding work, and is not a
physical-radio throughput claim.

The [MTU 23 report](verification/ble-23/verification.json),
[Android transcript](verification/ble-23/instrumentation-output.txt) and
[peripheral report](verification/ble-23/peripheral.json) passed the same four
cases / 33 assertions in 36.538 seconds. Both connections negotiated MTU 23.
The first delivered the same 73,674 bytes across 6,985 notifications; the second
revalidated completed sources across 76 notifications without payload reread.
No peripheral errors or exact command retries were observed. These success
runs do not exercise deliberate packet loss, authentication or physical RF.

The Android client did encounter transient setup failures during the second
pass: MTU 517 recorded a command-write failure and a missing-service result;
MTU 23 recorded one command-write failure. Its bounded recovery created four
and three client connection attempts respectively, entered `RETRY_WAIT`, and
then completed both passes. Each peripheral report contains two established
connections. These client reconnects are distinct from exact-command retries
within a connection, whose peripheral counters remained zero. Their cause is
not established by this evidence; the successful recovery does not mean every
connection attempt succeeded.


The virtual peripheral is **Python protocol fixture code**, not the Zephyr
firmware or a real microphone/NAND recording. It permits only the fixed public
synthetic fixture address. It does not implement encrypted ownership enrollment.
The production caller still needs separately trusted enrollment credentials;
HELLO, addresses and bonds are not ownership proof. The runner installs only on
an explicitly selected API33+ emulator, owns its Bumble child, stops it at the
end, and binds the build report, APKs, fixture source and output logs. The
[pinned setup evidence](verification/ble-toolchain.json),
[fixture procedure](ble-fixture/README.md) and [recovery contract](RECOVERY.md)
provide reproduction details.

The [first virtual attempt](verification/recovery-attempt-01/ble-517/verification.json)
failed **before test execution**: Android could not find a separately declared
instrumentation component because the Gradle manifest pipeline replaced its
registration with the configured smoke runner. The associated passing smoke run,
build report and transcripts are retained in that directory. The fixed test APK
uses the registered `SmokeInstrumentation` with explicit `suite=virtualBle`,
delegating to the same Bluetooth checks with the runner's attached context.
The failed attempt is not counted as a transport test or pass.

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

No physical pendant, microphone/PDM input, NAND hardware, battery, charging,
privacy-switch timing, PCB fabrication, enclosure fit or wear test is covered.
Virtual GATT uses Android 14 and a Python peripheral; it does not execute the
Zephyr adapter, prove physical-radio reliability or authenticate device ownership.
The Activity still imports selected local archives and does not expose consumer
Bluetooth downloads, automatic transcription, portal sync or background capture.

The earlier API29 storage/playback checkpoint remains available in the
[a04-android-download-dev release](https://github.com/Avinash1286/pendent/releases/tag/a04-android-download-dev).
Current runtime coverage is API34. The new GATT client's API29–32 callback branches,
real app process death, permission/bond transitions, physical out-of-range return,
OEM codecs, long recordings, storage pressure, audio-focus/route changes and broad
phone compatibility remain unqualified. Scripted cancellation tests do not
replace physical disconnect or OS process-kill evidence. Zero lint findings are
not a certification or store-release approval.

## Reproduce and extend

The [app guide](README.md) contains setup prerequisites and build/install instructions. From the repository root, the evidence runner can rebuild both APKs and run lint, then execute the isolated suite on an explicitly selected available target:

```powershell
uv run --project companion --locked python mobile/android/scripts/verify_android.py build
uv run --project companion --locked python mobile/android/scripts/verify_android.py runtime --serial '<device-serial>'
```

The build phase uses `build.ps1 -SkipCore`; run the default `mobile/android/build.ps1` separately when reproducing the JVM/FFmpeg checks too. The runtime phase refuses changed source inputs or APKs relative to its successful build report, installs both development APKs with `adb install -r`, and records the actual result. It does not choose a target implicitly, wipe user data, uninstall an app, or flash device firmware. Preserve previous evidence before replacing a report if comparing runs, and report each platform's actual decoder, sample counts, and remaining limitations.
