# A04 radio DK development build

This package is for inspecting and reproducing the separate
`nrf52840dk/nrf52840` Bluetooth development application. It is not firmware for
the A03 pendant or the unfinished A04 PCB. No physical board was flashed,
microphone exercised, SMP pairing executed or battery tested for this release.

The [application guide](README.md) describes the exact external DK fixtures,
local UART context and capture controls. Initial owner context is supplied over
physically trusted UART after every reset; Bluetooth bonds do not replace it.
The Android development app does not yet perform this target's ASC1 proof
exchange. There is no consumer end-to-end pairing/download claim.

The package contains the ELF, BIN, Intel HEX and linker map from one build,
the resolved Zephyr configuration/device tree, source-bound build and host-test
reports, and the matching source commit identity. The reproduction command is:

```powershell
pwsh -NoProfile -File firmware/a04/radio/build.ps1 -Mode arm -Jobs 2
```

After committing that exact source/evidence checkpoint, run
`python scripts/package-a04-radio.py` from the repository root to regenerate
the development ZIPs, manifest and checksums under
`.tools/a04-radio/releases/a04-radio-dk-dev/`. The packager requires a clean
checkout and matching recorded source/build hashes; it does not flash, publish
or claim hardware validation.

Use the release's `SHA256SUMS` and manifest to verify downloaded assets. Review
the exact source commit and [ARM resource report](verification/arm-resources.json),
not just a filename. The release is a development checkpoint and does not
replace [custom-board fabrication and first-wear gates](../../../docs/research/aura-first-wearable.md).

Important layout facts for review: this standalone image reserves internal
flash below `0xf8000` for code and `0xf8000..0xfffff` for Bluetooth settings.
It has no signed bootloader or update slots. NAND control blocks 1022/1023 and
the external microphone/privacy wiring follow the separate DK fixture contract.
The protected battery, charger/dock and enclosure are outside this application.
Do not infer an AURA flashing procedure from the DK build target.
