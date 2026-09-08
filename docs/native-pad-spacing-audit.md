# Native A03 SMD copper-pad spacing audit

Read-only audit at 2026-09-08T00:02:48.922823+00:00 of `hardware/native/aura-a03.kicad_pcb`, SHA-256 `b9ec8ebf1a0afaa7563ed4838e145cebb4f14055f71e25b2dbcb0329b0180064`. The native board is the placement authority. No PCB or rule settings were changed.

**Result: PASS, 0 violations across 25,158 different-net pad pairs.** [JLCPCB rigid-board capabilities](https://jlcpcb.com/capabilities/pcb-capabilities) specify 0.15 mm SMD pad-to-pad clearance for different nets. [Assembly component spacing](https://jlcpcb.com/help/article/minimum-spacing-for-smd-components) is a separate requirement.

| Scope | Pair | Nets | Layer | Native gap (mm) | Result |
|---|---|---|---|---|---|
| withinFootprint | U6.1 / U6.2 | HAPTIC_REG / I2C_SCL | F.Cu | 0.150000–0.150001 | PASS |
| betweenFootprints | C16.1 / U8.6 | MIC_VDD / PDM_CLK_BUF | F.Cu | 0.165000–0.165001 | PASS |
| B.Cu | J2.1 / J2.2 | VBAT / GND | B.Cu | 0.500000–0.500001 | PASS |

The audit examines 247 SMD pad objects representing 245 unique terminals, including custom microphone ground polygons with their holes. Non-SMD sound-port drill objects are outside this pad-pair check. Same-net pairs are excluded from this specific rule; different unassigned pads are treated as distinct electrical terminals, not as a shared net-zero. Both pairs within one footprint and between separate footprints are included.

[audit-native-pad-spacing.py](../hardware/scripts/audit-native-pad-spacing.py) uses `PAD.GetEffectiveShape(layer)` and native `SHAPE.Collide` on the loaded board. Actual polygons, holes, rectangles, circles and rounded shapes determine clearance; body rectangles and bounding boxes do not substitute for pad geometry. A binary search brackets distances within 1 nm. The pass/fail decision separately tests native collision at exactly 150,000 internal units. A rectangular pair with exactly 0.15 mm gap confirmed equality passes. These brackets describe computation resolution, not production tolerance.

The earlier board hash `b7a975bbb7aff69879f7040e7d914bfe41dc465224ab803978c5f10d15c5fd43` had one C7.2–U4.5 gap of 0.125 mm. The routing owner corrected C7 placement; the current report above is authoritative for the latest checked hash. No findings are suppressed.

[Complete JSON report](../hardware/output/native-smd-pad-spacing-audit.json) includes exact pad UUIDs, board hash, every violation, nearest 100 pairs, and minima within every footprint and between footprint pairs. The checksum stayed identical before and after the audit.

To repeat from the repository's `hardware/` directory:

```powershell
& 'C:/Program Files/KiCad/10.0/bin/python.exe' scripts/audit-native-pad-spacing.py
```

A board edit during the run aborts this audit. Any later board change invalidates this exact hash-bound result. Tracks, vias, soldermask dams, assembly-body spacing and fabrication/assembly qualification are separate checks.
