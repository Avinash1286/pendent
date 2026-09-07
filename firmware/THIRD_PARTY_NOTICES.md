# Firmware third-party notices

The authored AURA application is MIT. The linked engineering image also includes upstream code. Preserve these notices and the upstream license texts when redistributing binaries. This inventory identifies the components used by the pinned build; it is not a replacement license.

| Component | Pinned source | License/source notice |
|---|---|---|
| Zephyr RTOS | v4.2.0, 413b789deb391d3a37d06b463288a5fe765ee57e | Apache-2.0, per-file exceptions: https://github.com/zephyrproject-rtos/zephyr/blob/v4.2.0/LICENSE |
| Nordic HAL / nrfx / MDK | 9587b1dcb83d24ab74e89837843a5f7d573f7059 | Nordic BSD-style and per-file notices: https://github.com/zephyrproject-rtos/hal_nordic/tree/9587b1dcb83d24ab74e89837843a5f7d573f7059 |
| CMSIS | 512cc7e895e8491696b61f7ba8066b4a182569b8 | Apache-2.0: https://github.com/zephyrproject-rtos/cmsis/tree/512cc7e895e8491696b61f7ba8066b4a182569b8 |
| CMSIS 6 | 06d952b6713a2ca41c9224a62075e4059402a151 | Apache-2.0: https://github.com/zephyrproject-rtos/CMSIS_6/tree/06d952b6713a2ca41c9224a62075e4059402a151 |
| Mbed TLS | 85440ef5fffa95d0e9971e9163719189cf34d979 | Apache-2.0 or GPL-2.0-or-later as offered by upstream; this build uses Apache-2.0: https://github.com/zephyrproject-rtos/mbedtls/tree/85440ef5fffa95d0e9971e9163719189cf34d979 |
| Picolibc / compiler runtime | Zephyr SDK 0.17.2 ARM toolchain | BSD-style, newlib per-file notices and GCC runtime exceptions; see https://github.com/zephyrproject-rtos/sdk-ng/releases/tag/v0.17.2 and bundled SDK licenses |

License texts copied from the pinned sources are retained in `licenses/`. TinyCrypt is fetched as a pinned optional Zephyr dependency but the resolved Bluetooth build uses Mbed TLS PSA. Host tests use Zig 0.14.1 as a build tool; Zig is not embedded in the pendant image. Exact configured modules can be audited from `release/build.config` and linked objects from `release/aura-a03.map`.
