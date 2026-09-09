The A04 monitored PDM driver is a project-local derivative of Zephyr v4.2.0's
[Nordic DMIC driver](https://github.com/zephyrproject-rtos/zephyr/blob/v4.2.0/drivers/audio/dmic_nrfx_pdm.c).
Its Nordic copyright and Apache-2.0 notice are retained. The original clock
selection and channel mapping are retained; the lifecycle and buffer handoffs
have explicit ownership and fault handling. The nRF52840 restriction keeps this
change within the reviewed single-core nrfx lifecycle. No tool installation or
A03 source is changed.

The pinned local original driver's raw SHA-256 is
`8c411687eae8f83377452d797da036bbc5d049297dc34e53c6fcb5c71fe53518`.
The reviewed local nrfx PDM source's raw SHA-256 is
`0e720b164ae210bc3fe375e76f2f7f4867dbfa86de24e6f194556cef9a6bea5c`.
Both raw and LF-normalized upstream hashes are recorded by the test runner.

The added behavior is:

- Sticky faults for nrfx overflow, allocation, DMA prepare/release, buffer
  submission, RX queue, unexpected ownership, clock, initialization, start and
  stop failures. START and configuration cannot clear faults implicitly.
- Two explicit DMA records identify released pointers. Failed submission
  returns its prepared allocation. Uncertain DMA release retains ownership and
  prevents reset or restart. A completed block carries its 1-based source
  release sequence through the RX queue.
- STOP cancels run intent immediately. A pending clock callback cannot start
  capture later. If the first DMA buffer was armed but STARTED has not arrived,
  STOP waits for STARTED before invoking nrfx STOP: this avoids nrfx's STARTING
  stop path, which disables without returning its buffers. The application
  must bound this wait; a missing event cannot be treated as a clean stop.
- Clock references remain owned through asynchronous startup and DMA return.
  Ready/stopped/drained health requires the peripheral disabled, no pending
  clock request, no owned clock reference, no owned DMA buffers, and for drained
  no RX or caller-held slab blocks. Partial STOP returns are discarded.
- The health API checks exact custom API identity before accessing device data.
  IRQ masking makes 64-bit snapshots coherent on the supported single-core
  target. The application still serializes configure/trigger/read/reset calls
  and uses a dedicated slab. A blocked read needs a finite application timeout;
  faults do not forcibly wake an already waiting stock message-queue read.

Integration uses `drivers/Kconfig`, `drivers/CMakeLists.txt` and the custom
`aura,nrf-pdm` binding under `drivers/dts`. The application adds this directory
as a DTS root before Zephyr configuration, sources its Kconfig and adds its
CMake directory. Enable `AUDIO`, `AUDIO_DMIC`, `AURA_DMIC_NRFX_PDM`; the stock
`AUDIO_DMIC_NRFX_PDM` must be disabled. `pdm0` uses the custom compatible, so the
stock driver's automatic compatible selection does not apply.

`probe/nrf52840dk_nrf52840.overlay` is only an nRF52840 DK compile/bench binding.
P0.30 CLK and P0.31 DIN are copied from Zephyr v4.2.0's DK DMIC sample. Device
initialization applies that pinctrl. The resource probe does not start capture,
power microphones, or control charging. These are not AURA GPIO assignments.

Run `python firmware/a04/drivers/tests/run.py` from the repository after the
pinned tools are installed. It compiles the production callback, start/stop,
read and health implementation with `-Wall -Wextra -Werror`, substituting only
the kernel/HAL boundaries. Twenty assertion groups inject overflow, each buffer
handoff failure, clock/start/stop failures and startup races, and check ownership,
sequence, queue draining and reset guards. `tests/verification.json` binds the
tested source bytes and `tests/host-tests.txt` contains the results. Clock
selection, configuration and device instantiation are excluded from this host
shim; the application's actual Zephyr ARM build checks those portions.

Completed counts mean full nrfx release callbacks observed in this process;
they cannot reveal every missing physical sample, measure clock rate, or prove
electrical continuity. The pin/edge mapping, power and clocked settling,
privacy behavior, rate tolerance, clipping and storage-stall tolerance still
need hardware qualification. A nominal 1.28 MHz PDM clock with ratio 80 targets
16 kHz relative to the HFXO; requesting 16 kHz alone does not enforce it. Per
[SPH0641 Rev B, section 6](https://www.mouser.com/datasheet/2/218/sph0641lu4h_1_revb-3313002.pdf),
SELECT=VDD data is latched on falling clock and SELECT=GND on rising clock.
With A04 MK1 SELECT=GND and MK2 SELECT=MIC_VDD, Nordic LEFTFALLING yields MK2
then MK1 in RAM. Physical-reference channel identity must be verified on hardware.
