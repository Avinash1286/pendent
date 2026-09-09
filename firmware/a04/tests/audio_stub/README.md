# Audio adapter host surface

These minimal headers and the functions in `../host_audio.c` let the **actual**
`aura_audio_zephyr.c` compile with the actual recorder, Opus encoder, archive,
journal and host NAND model. They are test-only include overrides; do not add
this directory to a Zephyr/production target.

The queue copies fixed messages and enforces capacity. The slab tracks exact
allocations, rejects double frees, and records buffers intentionally retained
after unproven DMA quiescence. GPIO and DMIC health are deterministic state
machines. Hooks inject cancellation during health reset, power settling and a
read. The GPIO-enable hook defers simulated interrupt delivery while the fake
IRQ lock is held, then delivers at unlock; it does not invoke an ISR through a
locked critical section.

This is a set of serialized interleavings, **not real threads, atomics, DMA,
physical PDM or a hardware timing proof**. Block counters are supplied by the
fake driver, so this suite cannot prove that a real driver reports every
physical overflow or that a microphone clock yields an exact sample rate.
The custom nrfx driver's separate tests and physical qualification remain
necessary. The fixture/FFmpeg recorder suite separately checks real speech
decoding; this suite uses bounded deterministic stereo sample blocks to inspect
channel selection and clipping/mean arithmetic.

Build the host adapter target with this directory first on the include path,
followed by A04 `include` and upstream Opus `include`. Link `host_audio.c`,
`nand_model.c`, `aura_audio_zephyr.c`, `aura_recorder.c`, `aura_opus.c`,
`aura_archive.c`, `aura_journal.c` and the existing pinned host Opus library.
Compile with `-std=c11 -Wall -Wextra -Werror`. The test uses explicit checks,
so release `NDEBUG` does not remove assertions.
