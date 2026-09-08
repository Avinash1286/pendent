# AURA A03 firmware and companion

The active firmware implementation is now in [../../firmware/](../../firmware/). The TypeScript CaptureController here remains an executable UX reference, not the device binary.

A03 has one whole-face flush paddle and a mechanical privacy slider. There is no SW3 or separate external bookmark control. A single press starts/stops, a double press while recording journals a bookmark, and a three-second idle hold opens pairing. A ten-second hold grants bounded maintenance permission; it does not erase data by itself.

The shared transfer contract is [../../docs/ble-protocol.md](../../docs/ble-protocol.md). The firmware uses dual PDM capture, mono PCM16 at 16 kHz, recoverable CRC-protected NAND pages and encrypted BLE access. See the implementation README for exact behavior and limitations, including bookmark export, finite journal capacity, explicit maintenance format and recovery tests.

Charging is default disabled in the distributed engineering image. A03 P0.23 CHG_ALLOW must remain LOW during reset/faults and may only permit the independently gated charger after stable supplies and pack/thermal qualification. The hardware uses R_ISET 5.62 kOhm and a separate TLV6700 thermistor hot cutoff; see thermal-review.md. Haptics are also qualification-gated: candidate C08-00A is rated 1.2 Vrms, maximum 1.25 Vrms at 240 Hz, with an initial reduced engineering target; do not reuse the former 1.8 V settings.

There is no claim of flashed/bench-tested hardware, at-rest encryption, signed DFU, measured battery runtime or consumer readiness. The actual ARM artifacts, host tests, detailed bring-up sequence and enablement gates are in the main firmware package. The companion performs transfer and AI processing; the pendant does not run an on-device LLM.
