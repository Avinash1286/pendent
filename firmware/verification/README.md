# A03 engineering firmware verification

Verified locally on 2026-09-08. No physical PCB was connected.

| Check | Result |
|---|---|
| Actual ARM build | PASS, Zephyr v4.2.0 / SDK 0.17.2 / ARM GCC 12.2.0, custom `aura_a03/nrf52840` board |
| Application flash | **219,108 bytes / 992 KiB** (21.57%); final 32 KiB reserved for persistent settings |
| Static RAM and configured stacks/buffers | **83,452 bytes / 256 KiB** (31.83%); runtime stack high-water remains a bench check |
| Shared C journal/gesture/PCM/maintenance tests | **14 passed** |
| Production NAND command serializer tests | **4 passed** against a strict simulated SPI device |
| Release identity/configuration checks | **5 passed**, including matching ELF/HEX/BIN and safe qualification gates |
| Physical audio/BLE/NAND/charger/haptic/thermal tests | **Not performed** |

Evidence: `arm-build.txt`, `host-tests.txt`, `nand-tests.txt` and `release-checks.txt`. `../release/manifest.json` contains the exact hashes; source hashing normalizes CRLF to LF, and `.gitattributes` preserves binary release bytes through Git.

The checked BIN is 219,108 bytes, SHA-256 `cf3b32c688537ce48575260b3c993c980eae5410aef9a080df693749f4b707cf`. The HEX SHA-256 is `94a72d7d68decde347c0619d4564a80548defff8fb68da6ce57a53e4a12192f8`.

The final configuration requests 1.280 MHz PDM with RATIO80 for exactly 16 kHz, two channels mixed to mono, 50 ms rail settling and two discarded 40 ms startup DMA blocks. The nRF52840's documented ratio capability was checked in the pinned Nordic MDK and Zephyr driver; the clock is within the microphone's retrieved standard-mode limits. First-article scope/acoustic measurements are still required.

The distributed image disables charge permission and haptics. It requires physical pairing, encrypted characteristics and a separate physical hold plus explicit command for storage reuse. Firmware code, successful compilation and simulated fault tests do not establish a safe assembled battery product, manufacturing readiness, or consumer security certification.
