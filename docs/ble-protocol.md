# AURA protocol v1

This document is the shared firmware/companion contract for A03. Integers are little-endian. Audio is signed PCM16 LE, mono, 16000 Hz. The pendant captures the two microphone channels and mixes to mono. The protocol transfers saved recordings; it cannot remotely start the microphones.

## GATT service

Service: `7f510000-1b15-4f0d-8fe5-3f942170a001`.

| Characteristic | UUID prefix (remaining UUID identical) | Property |
|---|---|---|
| Command | `7f510001` | Write with response, encrypted link required |
| Response | `7f510002` | Read / long read, encrypted link required |

Commands have a four-byte header: version `u8` (=1), opcode `u8`, transaction `u16`. Only one command may be outstanding per connection. Every command fits the default ATT write payload. A write schedules work; the response is initially BUSY, then replaced atomically with a completed response. The client polls by reading Response. Its header is status `u8`, opcode `u8`, transaction `u16`; a client ignores another transaction. Long-read fragments must come from the same immutable completed response until another command is accepted.

Statuses: 0 OK, 1 BUSY, 2 INVALID, 3 NOT_FOUND, 4 IO_ERROR, 5 FORBIDDEN, 6 END_OF_LIST. Failed responses have no payload. Timeout is30seconds; a timed-out read may reconnect and resume at a previously verified offset.

| Opcode | Request after header | Successful response after header |
|---|---|---|
| 1 STATUS | empty | version `u8`, state `u8`, privacy_off `u8`, flags `u8`, battery_mV `u16`, free_bytes `u32`, recording_count `u16` |
| 2 LIST | index `u16` | id `u32`, started_unix_seconds `u64`, pcm_bytes `u32`, pcm_crc32 `u32`, sample_rate `u32`, channels `u8`, sample_bits `u8`, flags `u8` |
| 3 READ | id `u32`, offset `u32`, requested_length `u16` (1–180) | id `u32`, offset `u32`, count `u16`, PCM bytes, chunk_crc32 `u32` |
| 4 DELETE | id `u32`, expected_pcm_bytes `u32`, expected_pcm_crc32 `u32` | empty; mismatch must reject, deletion only marks the matching committed recording |
| 5 TIME | unix_seconds `u64` | empty |

CRC32 is IEEE802.3, identical to Python `zlib.crc32(data)` and Zephyr `crc32_ieee`. Offset and count refer to PCM data only, with no WAV header. A zero-length READ at EOF is valid. Never return a silently repaired CRC for corrupted NAND data. Uncorrectable ECC is IO_ERROR. Flags bit0 marks an interrupted/recovered recording; other bits are reserved. STATUS states:0idle,1recording,2saving,3muted,4error. STATUS flags bit0 means charging-disabled, bit1 means storage fault; battery voltage0 means unknown.

## Pairing and retention

An idle three-second physical hold opens a bounded pairing/advertising window. Previously bonded clients may reconnect according to the firmware's policy. Pairing requires physical control of the device; a displayless Just Works association does not provide authenticated MITM protection. All audio characteristics require link encryption. No public advertisement exposes note contents.

Sync never deletes audio automatically. The client validates each chunk and the complete recording CRC, writes a WAV file atomically, and retains metadata. Deletion is a separate explicit action with matching size and CRC. NAND journaling, interrupted recording recovery, bad-block handling and pairing must be tested on the actual board before relying on the device for unique recordings. This contract does not assert those tests have passed.
