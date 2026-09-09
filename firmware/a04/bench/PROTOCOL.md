# A04B bench UART protocol, version 1

This is a local developer link for a separate nRF52840 DK bench application. It is not the AURA Bluetooth protocol, a secure enrollment channel or wearable firmware. No erase/release command is exposed. The host retains the enrollment context and supplies it again after a reset; the bench application stores no secret in MCU flash. Actual microphone/NAND wiring must match WIRING.md.

UART0 is 115200 8N1, ASCII LF-terminated lines. Requests are `A04B <request-id> <verb> [argument]`, where request-id is exactly eight hexadecimal digits. A request fits 256 bytes including LF. Only one host request may be outstanding. Replies use the same prefix and ID; unrelated boot/debug lines are not protocol replies. All hex fields are lowercase on output and case-insensitive on input. No arguments are echoed for OPEN/PROVISION. Errors are `A04B <id> ERROR <signed-code>`.

| Request | Successful response |
|---|---|
| `INFO` | `OK INFO <device-id-32hex> <ready-0-or-1> <audio-state-int> <fault-int> <catalog-count> <free-blocks>` |
| `STATS` | `OK STATS <service-max-us> <late-service-count> <fifo-high-water> <reader-stack-free> <storage-stack-free> <nand-read-calls> <nand-program-attempts> <nand-erase-attempts> <peak-first> <peak-second> <clip-first> <clip-second>` |
| `PROVISION <context-176hex>` | `OK PROVISION` after explicit blank-media provisioning |
| `OPEN <context-176hex>` | `OK OPEN` after existing authority and journal verification |
| `LIST` | Zero or more `ITEM <manifest-136hex> <verification-int> <block-count>` lines, then `END LIST <count>` |
| `START` | `OK START <capture-id-32hex>` after capture initialization; failure may leave an interrupted source discoverable through LIST |
| `STOP` | `OK STOP <audio-state-int> <fault-int> <capture-id-32hex>` after the capture has reached a terminal state; this is status, not a durable host receipt |
| `EXPORT <capture-id-32hex>` | `DATA <offset-16hex> <payload-hex> <crc32-8hex>` lines, then `END EXPORT <total-bytes-16hex> <physical-ACK3-188hex>` |

Context is the existing trusted release context serialized as device ID[16], storage incarnation[16], owner ID[16], owner generation uint64 little-endian, key[32], exactly88 bytes. The application rejects a device ID that differs from its hardware-derived ID. The two reserved control blocks are fixed at1022/1023; unavailable factory/LUT targets fail without selecting another layout. No default key, automatic provisioning, floor reset or media repair is supplied.

START/STOP, enrollment, catalog and export run on one serialized storage owner. INFO and STOP are available while recording; other requests are rejected as busy. Export is idle-only. DATA carries at most128 bytes per line; offset must exactly equal bytes already received. CRC32 is the archive IEEE CRC over payload bytes. Successful export revalidates the journal source; an ERROR or interrupted link makes the temporary export unusable as a completed download. The host independently verifies the complete AUR3 archive and its returned receipt before publishing it or importing it into the durable receiver.

Captures stop automatically after60 seconds in this bench build. STATS is idle-only. Service duration/FIFO/peak/clipping counters reset at START; a late service means elapsed time greater than20ms, including encoding, storage and preemption, not an isolated encoder measurement. Stack free values are Zephyr's initialized-stack observations, not a complete proof of stack safety. Read calls count journal metadata/payload plus control-ledger calls since their most recent open; they exclude the backend's cold marker/LUT scan. NAND program/erase attempts are command-core counters since boot. Values are actual runtime observations only when this application runs on hardware.

Service timing stops when audio/reader/recorder cleanup is complete, so later INFO or EXPORT work does not change the last capture's service maximum. INFO and STOP report the first nonzero diagnostic in boot, storage owner, audio producer, recorder close, recorder source, then journal order. A failed terminal seal cannot be reported as fault zero merely because the microphone producer stopped cleanly. STOP replies after audio cleanup even if an uncertain journal write keeps further storage operations locked; preserve the source and use cold recovery in that case.

At the initial1MHz SPI setting, checking all128MiB before first provisioning has a wire-time floor of about18 minutes, plus command/read/status overhead. The host uses a separate2400-second default PROVISION deadline. INFO cannot interrupt that synchronous scan. A timeout retains the exact host context; OPEN resolves whether provisioning committed. Explicit `provision --resume` may reuse that context for a still-entirely-blank medium, but cannot reset or repair existing authority. Startup and STOP operations also include physical storage verification time and are not yet a finished product's responsiveness target.

For a finalized or physically sealed interrupted source, returned ACK3 equals the exported archive receipt. For an unsealed physical prefix, the journal adds a derived interrupted seal only to the export: the returned ACK remains OPEN and must equal the verified prefix immediately before that derived seal. The host must not mistake the derived export seal for a device-side finalized recording or release permission.

STOP may take the monitored driver's bounded cleanup period plus pending encoding/storage time. Host timeouts leave source intact and require reconnect/LIST/recovery; they do not imply erase or success. A failed/quarantined microphone driver remains locked until cold restart where required by its ownership contract. The physical privacy input can cut microphone power independently of a blocked UART/storage operation; its actual electrical behavior and latency still require measurement.
