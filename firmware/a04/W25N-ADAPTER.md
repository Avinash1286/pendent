# W25N01GV command driver and Zephyr adapter

Status: **experimental A04 implementation; command-model tested and Cortex-M4 cross-built; no physical flash, SPI, timing or power-fault qualification**. The real command core is separate from the journal's sparse NAND model. A03 firmware and released images are unchanged. The final resource and source-hash reports must match the exact code revision being inspected.

The portable [driver](src/aura_w25n01gv.c) uses an injected synchronous command transport and clock. [The Zephyr wrapper](src/aura_w25n01gv_zephyr.c) supplies actual `spi_transceive_dt`/`spi_write_dt`, a monotonic clock and sleeping. A mutex covers each complete NAND read/program/erase/bad-query operation, including cache load and readback. Serializing individual SPI transfers alone would allow another caller to replace the chip's shared page cache.

The caller supplies a reviewed `spi_dt_spec` to `aura_w25n01gv_zephyr_init`; no GPIO or devicetree node is selected implicitly. Accepted operation is standard full-duplex, 8-bit MSB-first, active-low CS, mode0 or3, up to32 MHz. Hold-CS, locked-CS, LSB, slave, half-duplex and extended line modes are rejected. Actual supported board speed remains a signal-integrity measurement, not a result of this argument check. The wrapper is for a storage thread, never an ISR. Its SPI transport must have a bounded hardware timeout; the ready polling bound cannot interrupt a driver stalled inside a synchronous transfer.

## Initialization and ownership

Initialize only at cold startup after power is stable and no live operation is running: initialization issues RESET. It must not be used as a retry while another task is recording. The driver checks JEDEC identity, buffer/ECC configuration and volatile protection readback. Unexpected OTP/protection-lock state is refused; the driver never issues OTP programming or the BBM mutation command.

Before permitting any array write, initialization reads the20-entry BBM LUT and reserves both addresses of each enabled valid or invalidated link. Malformed/unsupported entries fail initialization. It checks main byte0 and spare bytes2048/2049 on both reserved marker pages of each remaining block, with ECC disabled. Read failures leave the adapter unavailable. It then restores buffer mode/internal ECC and verifies volatile unprotection. This preserves the manufacturer markers and avoids aliasing an existing remapped address. The second marker page is an additional conservative reservation.

Command selection, status bits, dummy clocks, factory markers and sequential programming follow the [Winbond Rev.R manufacturer datasheet](https://www.mouser.com/datasheet/2/949/Winbond_Electronics_09072023_W25N01GV_Rev_R_070323-3313374.pdf), especially sections7.2–7.3,8.2 and10. The implementation deliberately supports less than the chip's permitted partial-program behavior.

## Irreversible-operation boundaries

- **Read:** wait for ready, load one page, inspect its ECC status, then read the requested main-area bytes. Corrected data has a distinct result and telemetry; uncorrectable data is refused. Array addresses and columns are bounded.
- **Program:** only pages2–63 of a block successfully erased by this adapter in the current boot are eligible. Pages must increase and each attempt consumes permission. All-FF input is rejected because A04 pages contain a header and pre-existing FF cannot prove that an uncertain program occurred. The driver checks an ECC-clean FF destination, WEL, load/execute completion, P-FAIL, cleared WEL and full-page ECC/readback. A lost execute response can resolve successfully only through those checks, without a second execute. An unresolved completion returns `AURA_NAND_UNCERTAIN`; a failed or uncertain page is also blocked from read-based promotion through this instance, while its prior pages remain readable. Matching bytes with P-FAIL set never count as a successful commit.
- **Erase:** only a factory/LUT-eligible block whose entire main area is readable, ECC-clean and FF can be erased. Any populated, corrected, unreadable or hidden later page prevents the command. E-FAIL, cleared WEL and all64 post-erase pages are checked before program permission is granted. A lost command acknowledgement remains uncertain: pre-existing FF alone cannot prove that a fresh erase actually happened. Erase faults retire write permission for the current instance. This port therefore has **no populated-block reclamation**; it cannot be used as an implicit delete or garbage collector.

No prior-boot write permission survives initialization. A failed operation disarms writing without mislabelling the block as factory bad, allowing the journal to preserve and investigate its existing source. The journal remains responsible for capture identity, page CRC/hash validation, its committed watermark and recovery semantics. The adapter cannot itself issue an application receipt.

The per-block failure guard is **volatile**. Persistent runtime bad-block retirement and verified migration have not been implemented. A later cold-recovery session may inspect a previously failed page through full source/ECC validation; that does not restore permission to append to an old capture or prove permanent reliability of that block. This limitation must be resolved before dependable daily wear.

Ready polling has a30 ms monotonic deadline and301-poll fallback. These are software bounds around a responding transport, not measured bus or startup latency. Initialization reads only marker locations; the journal separately reads its bounded metadata inventory. Neither should be described as a full128 MiB boot scan.

## Verification and limits

[The command-level host test](tests/host_w25n01gv.c) compiles the **production command core**, without an alternate implementation, against a chip command model. Its20 groups check transaction boundaries, headers/dummy clocks, write-enable ordering, reserved-page and address rules, and reject unexpected opcodes. Cases cover factory markers, LUT aliases and invalid entries, wrong identity/lock/configuration, cache/readback, restart/no-resume, ECC statuses, lost completion, program/erase faults, silently ignored erase, non-FF tail pages, refused WEL, busy timeout and stalled clock. Two groups combine the actual driver and journal to check staging/receipts/cold verification and prevent a P-FAIL page with matching bytes from advancing the committed snapshot. Those integration packets are protocol fixtures; the separate real-Opus journal roundtrip establishes decode behavior. The command model implements neither physical ECC encoding nor analogue corruption probabilities.

Run the integrated A04 host build:

```powershell
./firmware/a04/scripts/build.ps1 -Mode host
```

The raw result is retained in [command-test evidence](verification/w25n-command-tests.txt). The empty-chip model startup performs12306 command transactions, receives12383 bytes and loads2048 marker pages; it does not scan audio. The portable host context is4432 bytes. These are measured software/model counts, not physical startup timing. Target resource reporting includes the real wrapper/context and code paths, not merely an unreferenced source file. The probe must not initialize a physical chip until reviewed A04 pins and hardware exist.

Remaining qualification: actual CS/DMA and shared-bus behavior, measured ready/startup/service latency, power interruption during every irreversible phase, real ECC/bad-block behavior, thread scheduling under PDM/BLE load, energy usage, and full capture→durable NAND→verified receiver recovery. No GPIO execution, physical flash test or wearable approval follows from these host checks.
