# A04 PCM source owner

Status: **portable implementation with real-Opus/NAND-model tests; physical PDM integration and driver health require separate evidence**. [aura_recorder.h](include/aura_recorder.h) and [aura_recorder.c](src/aura_recorder.c) connect a separately scheduled source reader to the existing staged codec/archive/journal. This module does not acquire a microphone or implement a concurrent queue.

## Ownership and bounded ingress

One storage thread owns all recorder calls, including start, service, consume, stop and interrupt. The upstream adapter owns its fixed PCM slab and nonblocking FIFO submission. A message contains a nonzero epoch, sequence, source-sample offset, PCM16 pointer and 1–320 mono samples. The pointer remains valid until `consume` returns, then the adapter releases that slot. The portable owner allocates no queue, heap, mutex or atomics; its tested host context is 3600 bytes, plus the existing externally owned encoder arena and journal.

Application block numbering detects missing, duplicated, reordered and stale messages. It **cannot establish physical microphone continuity** if a driver silently drops DMA buffers, overwrites a slab, ignores an overflow, or misreports STOP completion. The driver must expose health and healthy quiescence independently. Mono source offsets count the delivered mono samples; they do not infer an exact hardware sample rate or compensate an unknown clock error.

Hardware privacy and stop act immediately upstream. They never wait for an encoder, NAND program or recorder call. The reader must also report cancellation/failure to the storage owner so it can close the corresponding archive. Queued stale blocks/control messages from an earlier epoch are rejected without interrupting a later capture.

## Lifecycle

`aura_recorder_init` receives a mounted journal and a correctly aligned bounded Opus arena. Never reinitialize a live owner. `start` requires a fresh capture ID and a strictly increasing nonzero epoch. It prepares a blank journal block, initializes/services the monotonic deadline, initializes the 20 ms encoder and begins the staged archive. **Only return value zero permits upstream microphone startup.** `AURA_JOURNAL_RETRY_PREPARE` permits another start attempt before the microphone is enabled; it has not consumed the epoch. A failed attempt that begins an archive consumes its epoch.

The startup manifest must use `started_at_ms = 0` and `time_source = 0`. A button/request timestamp cannot locate the first usable source sample across asynchronous microphone startup and warmup. This owner has no later timestamp-rebinding operation. A future timing contract must bind a trustworthy first-sample event without rewriting an immutable archive manifest.

The storage thread calls `consume(recorder, block, now_ms, &consumed)` in FIFO order. It validates epoch, exact sequence and exact source offset before encoding. `consumed` is initialized to zero on every path where its pointer is valid and reports the exact PCM accepted into the codec, including a partial block before a callback/storage failure. Such a fault ends the capture; the adapter must release the message and **never resubmit its consumed prefix**. No later block is concatenated to this capture. The host test forces a NAND program failure after only 2 of 320 samples were accepted and proves that another consume cannot feed them again or issue another program.

Call `service(now_ms)` regularly while recording and paused; source processing cannot enforce the journal deadline while its owner is blocked. The adapter is responsible for its real queue, thread scheduling, worst-case storage stalls and overflow signal. The portable owner operates synchronously and does not promise a hardware encode/storage deadline.

Clean stop is legal only after the source reports healthy quiescence and the FIFO drains. `stop(recorder, epoch, source_end, now_ms)` compares the producer's final source watermark with the accepted count, catching a missing final block that has no subsequent sequence number. It then flushes the Opus lookahead/final frame and commits an exact finalized seal. Repeating a successful stop with the same epoch/end is idempotent. Zero-PCM clean stop produces a valid zero-source finalized capture.

Overflow, a source gap, upstream driver failure or explicit cancellation uses `interrupt(recorder, epoch, reason, now_ms)`. This closes the accepted complete-packet prefix as **interrupted with unknown original duration** and deliberately does not flush encoder lookahead or a partial PCM frame. Startup failure or privacy cancellation before any PCM produces a coherent zero-source interrupted archive. The caller must not treat those entries as usable recorded speech.

`fault_reason` records why the capture ended; `close_error` independently records failure to persist that ending. If NAND power loss or another I/O fault prevents sealing, state becomes `FAILED` and the existing verified physical prefix remains available through cold reopen/full verification/export. The export-only interrupted seal never becomes a physical terminal receipt. States `FINALIZED`, `INTERRUPTED` and `FAILED` reject additional PCM. Any new capture requires a fresh epoch and ID, and an unresolved journal I/O fault requires journal recovery first. There is no overwrite/reclamation expansion.

## Evidence

[The recorder transcript](verification/recorder-host.txt) and [roundtrip report](verification/recorder-roundtrip.json) bind the new owner and its actual codec/journal dependencies. The harness uses variable mono blocks across frame boundaries, real synthetic-speech Opus encoding, NAND model power interruption/reopen, existing Python/SQLite import and restart, and independent FFmpeg decoding. It covers startup preparation, zero-PCM stops/cancellations, stale epochs, duplicate/gapped blocks, a missing final block, service deadlines, partial consumption and separate source/close failures.

`scripts/verify_recorder.py` runs the built `aura_recorder_test.exe` and the independent import/decode checks. The Zephyr reader adapter requires separate driver/concurrency and target-build evidence. No test in this module proves physical PDM continuity, actual queue concurrency, STOP health, warmup, electrical privacy behavior, NAND power-cut behavior, BLE lifecycle or signed OTA.
