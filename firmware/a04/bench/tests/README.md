# Bench orchestration regression harness

`python firmware/a04/bench/test_control.py` compiles the **actual bench main.c,
audio adapter and archive SHA/CRC implementation** with deterministic host
doubles. The existing audio test kernel/atomic/DMIC declarations are reused;
this directory adds the APIs needed by the bench application.

The harness injects events at explicit preparation, health-reset, GPIO and
owner-loop boundaries. Recorder, storage, NAND and UART/DMIC devices are doubles.
Export uses a cursor phase double: initial verification, bounded chunk delivery,
final recheck and post-completion info. Tests require cancellation on every exit,
no END after initial/read/recheck/info failures, exact DATA offsets/CRC/payload,
and unchanged physical OPEN bytes when the export includes a derived seal.
These checks exercise the real UART dispatch and formatter; the separate
`host_journal_cursor` suite tests the actual cursor against its NAND model.
It proves the tested command ordering, framing and adapter state transitions,
not real scheduling, interrupt latency, electrical privacy, DMA continuity,
Opus encoding, NAND durability or physical operation. Those mechanisms have
separate tests and require real hardware measurements.

The runner fails on compiler errors, C assertions or a process timeout. It does
not edit the application, run its infinite threads as real threads, connect a
serial port or flash a target.
