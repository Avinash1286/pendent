# A04 recording firmware notices

The authored wrapper, probe, test harness and scripts are MIT under the repository license. They do not contain copied Omi implementation code.

The project-local [monitored DMIC driver](drivers/aura_dmic_nrfx_pdm.c) is a modified derivative of Zephyr v4.2.0's `drivers/audio/dmic_nrfx_pdm.c`, Copyright (c) 2021 Nordic Semiconductor ASA, licensed Apache-2.0. Its original notice is retained in the source. AURA's changes add sticky faults, explicit buffer/clock ownership, release sequencing, guarded reset and asynchronous start/stop cleanup; [the driver record](drivers/README.md) identifies provenance and differences. Redistribute the retained [Apache-2.0 license](../licenses/Zephyr-Apache-2.0.txt) with this source. The accompanying binding and DK pin configuration derive from the same pinned Zephyr tree. This integration does not modify the installed upstream checkout.

The experiment statically links **libopus 1.6.1** from the [official Xiph release archive](https://downloads.xiph.org/releases/opus/opus-1.6.1.tar.gz). The complete upstream notice is retained unchanged in [licenses/Opus-COPYING.txt](licenses/Opus-COPYING.txt). Preserve it when redistributing source or binaries. Opus uses a BSD-style license; its [official licensing page](https://opus-codec.org/license/) also describes the patent licenses and conditions. The build does not enable the optional deep-learning enhancements.

[dependencies/opus-1.6.1.json](dependencies/opus-1.6.1.json) pins the official archive SHA256 and all 482 extracted files. `scripts/setup.py` verifies both the archive and the unmodified source tree. The dependency download is excluded from Git; the pin, retrieval script and notices are committed so a fresh checkout can reproduce it.

The Cortex-M4 probe additionally links Zephyr v4.2.0, Nordic HAL, CMSIS and the Zephyr SDK 0.17.2 C/compiler runtime. Their retained license texts and pinned source identities are in the existing [firmware notices](../THIRD_PARTY_NOTICES.md) and [licenses](../licenses/). Consult the probe's actual map and `.config` for linked objects; this probe does not enable the A03 Bluetooth stack. Zig 0.14.1 and FFmpeg are host verification tools, not embedded in the probe image.

The speech input is a locally generated Windows speech-synthesis fixture already present in `companion/tests/assets/sample.wav`, resampled to mono PCM16 at 16 kHz. It is used only for reproducible codec regression tests. It is not a human recording, acoustic benchmark or language-quality dataset.
