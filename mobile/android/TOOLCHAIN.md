# Android toolchain review

Reviewed on 2026-09-09 for a native Kotlin app with Android 10 / API 29 minimum. This document records source checks and an installation proposal. The review did not install tools, change Windows features, build an APK, run an emulator, or test playback on a phone. Build and runtime results belong in the app's validation report.

**Subsequent installation:** the pinned build tools and a private API 29 emulator have now been installed. See [actual installed-toolchain evidence](verification/installed-toolchain.json), [boot evidence](verification/emulator-boot.json) and the [app verification guide](README.md#verification-status-and-runtime-checks). The installed emulator's own acceleration check successfully reported usable WHPX, superseding the earlier inconclusive WMI observation below. No Windows virtualization or security settings were changed. The following inspection remains a historical record, not a claim that these tools are still absent.

## Inspected Windows environment

| Item | Observed value |
| --- | --- |
| Workspace | `F:\circuit` |
| Java on PATH / JAVA_HOME | Temurin **JRE 25.0.3+9**, `C:\Program Files\Eclipse Adoptium\jre-25.0.3.9-hotspot` |
| Other Java directory | `jre-21.0.11.10-hotspot`; also a JRE |
| Development tools | No `javac`, `adb`, `sdkmanager`, `avdmanager`, `emulator`, or `gradle` on PATH or in the workspace `.tools` filename inventory |
| Default installations | No `%LOCALAPPDATA%\Android\Sdk` or `C:\Program Files\Android` directory |
| Free disk at inspection | F: 42,421,866,496 bytes; C: 25,512,497,152 bytes |
| RAM / CPU | 12,658,675,712 bytes; Intel Core i5-10210U |
| Hypervisor | `HypervisorPresent=true`; WMI virtualization/SLAT flags reported false |
| Optional Windows features | `VirtualMachinePlatform` enabled (InstallState 1); `HypervisorPlatform` disabled (InstallState 2) |

An active hypervisor can affect reported CPU virtualization capabilities; these flags do not establish that the CPU is incapable. The emulator is currently absent, so its accelerator check could not run. Google recommends Windows Hypervisor Platform; enabling it can require a reboot. Do not disable the existing hypervisor or security features to make an emulator work. After an authorized emulator installation, run `emulator -accel-check`. A physical Android phone is also a suitable runtime test target. [Official acceleration instructions](https://developer.android.com/studio/run/emulator-acceleration)

## Reproducible proposed recipe

| Component | Pin | Reason |
| --- | --- | --- |
| JDK, Windows x64 | Eclipse Temurin **17.0.20.1+1**, HotSpot JDK ZIP | Includes `javac`; meets AGP's JDK 17 requirement |
| Gradle | **9.4.1** binary distribution | AGP 9.2 compatibility table |
| Android Gradle plugin | **9.2.1** | Documented patch of the stable 9.2 series |
| Kotlin | AGP's built-in **2.3.10** dependency | No separately applied `org.jetbrains.kotlin.android` plugin |
| Command-line tools | **22.0**, archive build **15859902** | Fixed official download identity with published SHA-256 |
| SDK platform | **`platforms;android-37.0`**, revision **2** | Stable Android 17 base SDK, within AGP 9.2's maximum API 37.0 |
| Build tools | **36.0.0** | AGP 9.2 documented default and minimum |
| Platform tools | **37.0.1** | Current observed stable Windows package; lock its archive rather than assuming the rolling package ID never changes |
| Application levels | `minSdk = 29`, `compileSdk = 37`, `targetSdk = 37` | Android 10 minimum and Android 17 major API target |

The [AGP 9.2 release notes](https://developer.android.com/build/releases/agp-9-2-0-release-notes) supply the Gradle/JDK/build-tools compatibility table, the 9.2.1 patch, and Kotlin dependency update. [Built-in Kotlin documentation](https://developer.android.com/build/migrate-to-built-in-kotlin) says AGP 9.0+ enables Kotlin by default; applying the old Android Kotlin plugin as well causes a conflict. A simple Views app needs neither Compose nor a native NDK. Set Java source/target compatibility to 17; built-in Kotlin's JVM target follows that setting by default.

The [Android 17 setup page](https://developer.android.com/about/versions/17/setup-sdk) explicitly specifies integer compile/target SDK 37, but retains preview wording in its manual-install section. The [actual Google repository metadata](https://dl.google.com/android/repository/repository2-3.xml) resolves the package identity: `platforms;android-37.0`, revision 2, channel-0, empty codename, and no preview revision. **`platforms;android-37` was not present in that metadata.** Higher minor SDKs 37.1 and 37.2 were also listed; this recipe selects the stable base 37.0 within the checked AGP compatibility limit. It does not claim 37.0 is the newest minor SDK. Record the resolved installed platform and successful AGP build instead of renaming a platform directory to conceal a mismatch.

## Exact downloads and verification

The companion [toolchain-lock.json](toolchain-lock.json) records full URLs, versions, sizes where inspected, and checksums. These values identify downloads, not proof that they have been downloaded or verified locally.

| Archive | Official source and integrity source |
| --- | --- |
| [Temurin JDK ZIP](https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.20.1%2B1/OpenJDK17U-jdk_x64_windows_hotspot_17.0.20.1_1.zip) | [Adoptium API](https://api.adoptium.net/v3/assets/latest/17/hotspot?architecture=x64&heap_size=normal&image_type=jdk&jvm_impl=hotspot&os=windows&vendor=eclipse); [release SHA-256](https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.20.1%2B1/OpenJDK17U-jdk_x64_windows_hotspot_17.0.20.1_1.zip.sha256.txt) |
| [Gradle 9.4.1 ZIP](https://services.gradle.org/distributions/gradle-9.4.1-bin.zip) | [Official SHA-256](https://services.gradle.org/distributions/gradle-9.4.1-bin.zip.sha256) |
| [Command-line tools 22.0 ZIP](https://dl.google.com/android/repository/commandlinetools-win-15859902_latest.zip) | SHA-256 published on the [Android Studio download page](https://developer.android.com/studio); version and SHA-1 also verified in repository metadata |
| [Platform 37.0 revision 2 ZIP](https://dl.google.com/android/repository/platform-37.0_r02.zip) | Google's HTTPS repository metadata publishes SHA-1 |
| [Build tools 36 ZIP](https://dl.google.com/android/repository/build-tools_r36_windows.zip) | Google's HTTPS repository metadata publishes SHA-1 |
| [Platform tools 37.0.1 ZIP](https://dl.google.com/android/repository/platform-tools_r37.0.1-win.zip) | Google's HTTPS repository metadata publishes SHA-1 |

Before extracting or executing, compare `Get-FileHash -Algorithm SHA256` against the pinned SHA-256 for the JDK, Gradle, and command-line archives, failing on any difference. Let `sdkmanager` install SDK packages using Google repository metadata, then record installed `package.xml` / `source.properties`. If using the exact SDK ZIPs directly, verify their published SHA-1 and size before extraction; record an additional SHA-256 of the obtained files for future reproducibility. A locally computed SHA-256 is not a separately publisher-authenticated checksum. Add `distributionSha256Sum` to the Gradle wrapper properties so wrapper downloads are verified too. Do not silently substitute a different `latest` archive.

## Workspace-local setup proposal

Keep SDKs, archives, JDK, Gradle caches, local SDK paths, and debug signing material out of Git. Suggested locations:

```text
F:\circuit\.tools\android\jdk-17.0.20.1+1\
F:\circuit\.tools\android\sdk\cmdline-tools\22.0\bin\sdkmanager.bat
F:\circuit\.tools\android\gradle-9.4.1\bin\gradle.bat
F:\circuit\.tools\android\gradle-user-home\
```

After verified extraction, set `JAVA_HOME`, `ANDROID_HOME`, and `GRADLE_USER_HOME` in the build process only; prepend the selected JDK `bin` to that process's PATH. Preserve the existing machine Java configuration. Android command-line tools require their `bin`, `lib`, `NOTICE.txt`, and `source.properties` under the version directory, without another nested `cmdline-tools` folder. Use explicit `--sdk_root=F:\circuit\.tools\android\sdk` for SDK commands. [SDK manager documentation](https://developer.android.com/tools/sdkmanager)

The proposed package install command is:

```powershell
& "$env:ANDROID_HOME\cmdline-tools\22.0\bin\sdkmanager.bat" `
  "--sdk_root=$env:ANDROID_HOME" --channel=0 `
  'platforms;android-37.0' 'build-tools;36.0.0' 'platform-tools'
```

SDK license acceptance is a separate installer step. Capture `sdkmanager --list_installed`, `java -version`, `javac -version`, and `gradlew --version` in the actual setup evidence. The rolling `platform-tools` package might resolve differently on a later date; compare it with the lock. Start with the build toolchain; add the emulator/system image only when runtime testing needs them and the acceleration check can be satisfied. No Studio or NDK installation is required for this pure Kotlin proposal.

## Offline Opus playback contract

Android supports **Opus decoding from API 21** and lists **Ogg** as an extractor container. API 29 therefore meets the documented decoding requirement. This is platform support, not evidence that AURA's archive parser, Ogg writer, or a particular phone has passed playback tests. [Supported media formats](https://developer.android.com/media/platform/supported-formats)

The app should validate the AURA archive and complete its derived Ogg before decoding every audio packet through `MediaExtractor` + `MediaCodec` to output EOS. Opening a player or receiving one decoded frame does not qualify the entire file. Keep the original capture intact when derived audio fails validation.

Pass the extractor's track format, including Opus codec-specific buffers, into the decoder. Android specifies `csd-0` as the identification header, `csd-1` as a native-order unsigned 64-bit pre-skip duration in nanoseconds (overriding the header's pre-skip), and `csd-2` as seek pre-roll in nanoseconds. Drain after signaling input EOS until output EOS; release resources on every failure. [MediaCodec contract](https://developer.android.com/reference/android/media/MediaCodec)

Read the decoder's actual output `sample-rate`, `channel-count`, and PCM encoding when the output format changes. Do not compare decoded sample counts directly to the capture's 16 kHz count: the inspected [AOSP Android 16 Opus decoder](https://android.googlesource.com/platform/frameworks/av/+/refs/tags/android-16.0.0_r1/media/codec2/components/opus/C2SoftOpusDec.cpp) uses a 48 kHz decoding rate and discards its codec-delay samples internally. At 48 kHz, one 20 ms frame contains 960 samples per channel. This is an inspected implementation example; the app must use reported output properties rather than assume all devices behave identically.

Do not subtract pre-skip twice. The inspected [AOSP Ogg extractor](https://android.googlesource.com/platform/frameworks/av/+/refs/tags/android-16.0.0_r1/media/module/extractors/ogg/OggExtractor.cpp) emits the pre-skip and 80 ms seek pre-roll buffers, uses a 48 kHz granule clock, and attaches native per-packet valid-sample metadata. Ordinary Java `queueInputBuffer` does not expose that native metadata argument. Therefore a hand-written extractor/codec loop must independently account for the Ogg terminal granule and any trailing decoded samples; full decode success alone does not establish correct gapless trimming. Validate decoded duration and sample-count bounds using the actual output rate, then apply only remaining end trim if constructing playback PCM. If playing the Ogg through a separate player, verify its duration and final boundary independently.

The public `MediaFormat.KEY_ENCODER_DELAY` and `KEY_ENCODER_PADDING` constants describe frames to trim at the start/end and were added in API 30. With minSdk 29, do not rely on those public APIs being present or populated; use guarded access and an explicit container/codec trimming policy. Their literal keys are `encoder-delay` and `encoder-padding`, but existence of a string key is not proof that a decoder applied it. [MediaFormat documentation](https://developer.android.com/reference/android/media/MediaFormat#KEY_ENCODER_DELAY)

Runtime validation should include a complete known-good capture, damaged packet, truncated final page, nonzero pre-skip, and a recording ending inside a padded codec frame. Record decoder name, Android API, output format, EOS observed, duration, and the sample-count/trimming result. These tests remain required until actual phone/emulator evidence exists.
