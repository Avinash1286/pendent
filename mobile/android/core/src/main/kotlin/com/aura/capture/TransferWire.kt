package com.aura.capture

import java.util.zip.CRC32

class TransferWireException(message: String) : Exception(message)

enum class TransferOpcode(val wireValue: Int) { HELLO(1), LIST(2), SELECT(3), READ(4), FINISH(5), CANCEL(6) }
enum class TransferStatus { OK, BUSY, INVALID, NOT_FOUND, IO_ERROR, FORBIDDEN, END_OF_LIST, STALE, CONFLICT }
enum class TransferVerification { UNVERIFIED, OPEN, FINALIZED, INTERRUPTED, INVALID }

/** Caller-supplied trusted IDs only. This type neither authenticates nor enrolls. */
class TransferSession(deviceId: ByteArray, storageIncarnation: ByteArray) {
    private val device = transferIdentity(deviceId)
    private val incarnation = transferIdentity(storageIncarnation)
    val deviceId: String get() = device.hexString()
    val storageIncarnation: String get() = incarnation.hexString()
    fun deviceIdBytes(): ByteArray = device.copyOf()
    fun incarnationBytes(): ByteArray = incarnation.copyOf()
}

class TransferCommand internal constructor(val opcode: TransferOpcode, val transaction: Int, bytes: ByteArray) {
    private val wire = bytes.copyOf()
    fun encode(): ByteArray = wire.copyOf()
}

/** Validated SELECT metadata, not proof that any archive has reached the phone. */
class TransferSelection internal constructor(
    val handle: Long,
    val manifest: CaptureManifest,
    val physicalReceipt: ArchiveReceipt,
    val physicalBytes: Long,
    val exportBytes: Long,
    val derivedSeal: Boolean,
    val allocationGeneration: ULong,
    val storageIncarnation: String,
)

sealed class TransferResponse(val opcode: TransferOpcode, val transaction: Int) {
    class Failure(opcode: TransferOpcode, transaction: Int, val status: TransferStatus) : TransferResponse(opcode, transaction)
    class Hello(transaction: Int, val deviceId: String, val storageIncarnation: String,
                val revision: Long, val catalogCount: Int) : TransferResponse(TransferOpcode.HELLO, transaction) {
        val maxLogicalBytes: Int get() = 512
        val maxChunkBytes: Int get() = 256
    }
    class Listing(transaction: Int, val revision: Long, val index: Int, val manifest: CaptureManifest,
                  val verification: TransferVerification, val sourceFlags: Int) : TransferResponse(TransferOpcode.LIST, transaction)
    class Selected(transaction: Int, val selection: TransferSelection) : TransferResponse(TransferOpcode.SELECT, transaction)
    class ReadData(transaction: Int, val handle: Long, val offset: Long, data: ByteArray) : TransferResponse(TransferOpcode.READ, transaction) {
        private val owned = data.copyOf()
        val count: Int get() = owned.size
        fun bytes(): ByteArray = owned.copyOf()
    }
    class Finished(transaction: Int, val selection: TransferSelection) : TransferResponse(TransferOpcode.FINISH, transaction)
    class Cancelled(transaction: Int, val handle: Long) : TransferResponse(TransferOpcode.CANCEL, transaction)
}

/**
 * Exact command encoding and logical response validation for transfer-wire-v1.md.
 * No GATT, authorization, transaction allocator, retries, resume coordinator or
 * durable publication. Callers serialize transactions and retain the selected
 * context for this connection. READ bytes still require complete AUR3 validation.
 */
object TransferWire {
    const val MAX_FILE_BYTES = 320L * 1024 * 1024
    const val MAX_PAYLOAD_BYTES = 256L * 1024 * 1024

    private fun command(opcode: TransferOpcode, transaction: Int, size: Int, fill: (ByteArray) -> Unit = {}): TransferCommand {
        transferCheck(transaction in 1..65535, "Transaction must be nonzero u16")
        val wire = ByteArray(size)
        wire[0] = 1; wire[1] = opcode.wireValue.toByte(); putLe(wire, 2, transaction.toLong(), 2)
        fill(wire)
        return TransferCommand(opcode, transaction, wire)
    }

    fun hello(transaction: Int): TransferCommand = command(TransferOpcode.HELLO, transaction, 4)
    fun list(transaction: Int, revision: Long, index: Int): TransferCommand {
        nonzeroU32(revision); transferCheck(index in 0..65535, "Catalog index must be u16")
        return command(TransferOpcode.LIST, transaction, 10) { putLe(it, 4, revision, 4); putLe(it, 8, index.toLong(), 2) }
    }
    fun select(transaction: Int, captureId: ByteArray): TransferCommand {
        val id = transferIdentity(captureId)
        return command(TransferOpcode.SELECT, transaction, 20) { id.copyInto(it, 4) }
    }
    fun read(transaction: Int, handle: Long, offset: Long, requested: Int): TransferCommand {
        nonzeroU32(handle); fileBound(offset); transferCheck(requested in 1..256, "READ request must be 1..256 bytes")
        return command(TransferOpcode.READ, transaction, 18) {
            putLe(it, 4, handle, 4); putLe(it, 8, offset, 8); putLe(it, 16, requested.toLong(), 2)
        }
    }
    fun finish(transaction: Int, handle: Long, expectedExportBytes: Long): TransferCommand {
        nonzeroU32(handle); fileBound(expectedExportBytes)
        return command(TransferOpcode.FINISH, transaction, 16) { putLe(it, 4, handle, 4); putLe(it, 8, expectedExportBytes, 8) }
    }
    fun cancel(transaction: Int, handle: Long): TransferCommand {
        nonzeroU32(handle)
        return command(TransferOpcode.CANCEL, transaction, 8) { putLe(it, 4, handle, 4) }
    }

    /** Same domain, terminating NUL, LE u64 and SHA256 prefix as aura_storage_capture_id. */
    fun captureId(session: TransferSession, allocationGeneration: ULong): ByteArray {
        transferCheck(allocationGeneration != 0uL, "Allocation generation must be nonzero")
        val generation = ByteArray(8)
        putLe(generation, 0, allocationGeneration.toLong(), 8)
        return sha("AURA-A04-CAPTURE-v1\u0000".toByteArray(Charsets.US_ASCII),
            session.deviceIdBytes(), session.incarnationBytes(), generation).copyOf(16)
    }

    fun decode(request: TransferCommand, response: ByteArray, session: TransferSession,
               selected: TransferSelection? = null): TransferResponse {
        transferCheck(response.size in 4..512, "Invalid logical response length")
        val wire = response.copyOf()
        val status = u8(wire, 0)
        transferCheck(status in TransferStatus.entries.indices, "Unknown response status")
        transferCheck(u8(wire, 1) == request.opcode.wireValue && u16(wire, 2) == request.transaction,
            "Response opcode or transaction does not match request")
        if (status != 0) {
            exact(wire, 4)
            return TransferResponse.Failure(request.opcode, request.transaction, TransferStatus.entries[status])
        }
        val command = request.encode()
        val transaction = request.transaction
        return when (request.opcode) {
            TransferOpcode.HELLO -> {
                exact(wire, 46)
                val device = transferIdentity(wire.copyOfRange(4, 20)).hexString()
                val incarnation = transferIdentity(wire.copyOfRange(20, 36)).hexString()
                transferCheck(device == session.deviceId && incarnation == session.storageIncarnation, "HELLO differs from trusted session")
                val revision = u32(wire, 36); nonzeroU32(revision)
                val count = u16(wire, 40)
                transferCheck(count <= 128 && u16(wire, 42) == 512 && u16(wire, 44) == 256, "Unsupported catalog or response limits")
                TransferResponse.Hello(transaction, device, incarnation, revision, count)
            }
            TransferOpcode.LIST -> {
                exact(wire, 80)
                val revision = u32(wire, 4); val index = u16(wire, 8)
                transferCheck(revision == u32(command, 4) && index == u16(command, 8) && index < 128,
                    "LIST echo or successful catalog index is invalid")
                val manifest = parseManifest(wire.copyOfRange(10, 78))
                val verification = u8(wire, 78); val flags = u8(wire, 79)
                transferCheck(verification in TransferVerification.entries.indices && flags and 0xf0 == 0, "Invalid LIST state or flags")
                transferCheck((flags and 8 != 0) == (manifest.deviceId != session.deviceId), "LIST device flag contradicts manifest")
                TransferResponse.Listing(transaction, revision, index, manifest, TransferVerification.entries[verification], flags)
            }
            TransferOpcode.SELECT -> {
                exact(wire, 195)
                val handle = u32(wire, 4); nonzeroU32(handle)
                val manifest = parseManifest(wire.copyOfRange(8, 76))
                val receipt = parseReceipt(wire.copyOfRange(76, 170))
                val physicalBytes = fileValue(wire, 170); val exportBytes = fileValue(wire, 178)
                val derived = flag(wire, 186); val generation = u64(wire, 187)
                transferCheck(manifest.deviceId == session.deviceId && manifest.captureId == command.copyOfRange(4, 20).hexString(),
                    "SELECT manifest differs from requested trusted identity")
                transferCheck(generation != 0uL && captureId(session, generation).hexString() == manifest.captureId,
                    "SELECT capture ID differs from allocation generation")
                transferCheck(receipt.deviceId == manifest.deviceId && receipt.captureId == manifest.captureId, "SELECT receipt identity differs")
                transferCheck(receipt.encodedBytes <= MAX_PAYLOAD_BYTES, "SELECT payload count exceeds archive bound")
                val framed = 68L + 26L * receipt.nextSequence + receipt.encodedBytes +
                    if (receipt.status == ReceiptStatus.OPEN) 0 else 120
                transferCheck(physicalBytes == framed, "SELECT physical length differs from exact record framing")
                transferCheck(derived == (receipt.status == ReceiptStatus.OPEN) && exportBytes == physicalBytes + if (derived) 120 else 0,
                    "SELECT export length or derived seal contradicts physical receipt")
                transferCheck(receipt.encodedSamples % manifest.frameSamples == 0L &&
                    receipt.encodedSamples / manifest.frameSamples <= receipt.nextSequence, "SELECT sample count contradicts record framing")
                val audioPackets = receipt.encodedSamples / manifest.frameSamples
                if (manifest.codec == CaptureCodec.PCM16) {
                    transferCheck(receipt.encodedBytes == receipt.encodedSamples * 2, "SELECT PCM payload count contradicts sample count")
                } else transferCheck(receipt.encodedBytes in (audioPackets * 2)..(audioPackets * 1275), "SELECT Opus byte count contradicts packet count")
                TransferResponse.Selected(transaction, TransferSelection(handle, manifest, receipt, physicalBytes, exportBytes,
                    derived, generation, session.storageIncarnation))
            }
            TransferOpcode.READ -> {
                transferCheck(wire.size >= 22, "Truncated READ response")
                val context = selection(selected, session, command)
                val handle = u32(wire, 4); val offset = fileValue(wire, 8); val count = u16(wire, 16)
                transferCheck(handle == context.handle && offset == fileValue(command, 8), "READ handle or offset does not match request")
                transferCheck(count <= u16(command, 16) && count <= 256 && wire.size == 22 + count, "READ count or exact length is invalid")
                transferCheck(offset <= context.exportBytes && count.toLong() <= context.exportBytes - offset,
                    "READ exceeds selected export EOF")
                transferCheck(count != 0 || offset == context.exportBytes, "Zero READ is only valid at selected EOF")
                val data = wire.copyOfRange(18, 18 + count)
                transferCheck(CRC32().apply { update(data) }.value == u32(wire, 18 + count), "READ data CRC differs")
                TransferResponse.ReadData(transaction, handle, offset, data)
            }
            TransferOpcode.FINISH -> {
                exact(wire, 119)
                val context = selection(selected, session, command)
                transferCheck(u32(wire, 4) == context.handle && fileValue(command, 8) == context.exportBytes &&
                    fileValue(wire, 102) == context.exportBytes, "FINISH handle or length differs from selection")
                transferCheck(wire.copyOfRange(8, 102).contentEquals(context.physicalReceipt.encode()) &&
                    flag(wire, 110) == context.derivedSeal && u64(wire, 111) == context.allocationGeneration,
                    "FINISH physical receipt or allocation differs from SELECT")
                TransferResponse.Finished(transaction, context)
            }
            TransferOpcode.CANCEL -> {
                exact(wire, 8)
                val context = selection(selected, session, command)
                transferCheck(u32(wire, 4) == context.handle, "CANCEL handle does not match request")
                TransferResponse.Cancelled(transaction, context.handle)
            }
        }
    }

    private fun selection(value: TransferSelection?, session: TransferSession, command: ByteArray): TransferSelection {
        val selected = value ?: throw TransferWireException("Selected capture context is required")
        transferCheck(selected.handle == u32(command, 4) && selected.manifest.deviceId == session.deviceId &&
            selected.storageIncarnation == session.storageIncarnation, "Command does not match selected session and handle")
        return selected
    }
    private fun parseManifest(wire: ByteArray): CaptureManifest = try { AuraArchive.parseManifest(wire) }
        catch (error: ArchiveException) { throw TransferWireException("Invalid canonical manifest: ${error.message}") }
    private fun parseReceipt(wire: ByteArray): ArchiveReceipt = try { AuraArchive.parseReceipt(wire) }
        catch (error: ArchiveException) { throw TransferWireException("Invalid canonical physical receipt: ${error.message}") }
    private fun exact(wire: ByteArray, bytes: Int) = transferCheck(wire.size == bytes, "Response has incorrect exact length")
    private fun nonzeroU32(value: Long) = transferCheck(value in 1..0xffff_ffffL, "Expected nonzero u32")
    private fun fileBound(value: Long) = transferCheck(value in 0..MAX_FILE_BYTES, "File offset or length exceeds bound")
    private fun u32(bytes: ByteArray, at: Int): Long = (0..3).fold(0L) { value, i -> value or (u8(bytes, at + i).toLong() shl (8 * i)) }
    private fun u64(bytes: ByteArray, at: Int): ULong = (0..7).fold(0uL) { value, i -> value or (u8(bytes, at + i).toULong() shl (8 * i)) }
    private fun fileValue(bytes: ByteArray, at: Int): Long {
        val value = u64(bytes, at)
        transferCheck(value <= MAX_FILE_BYTES.toULong(), "Unsigned file offset or length exceeds bound")
        return value.toLong()
    }
    private fun flag(bytes: ByteArray, at: Int): Boolean {
        val value = u8(bytes, at); transferCheck(value in 0..1, "Invalid derived-seal flag"); return value == 1
    }
}

private fun transferCheck(condition: Boolean, message: String) {
    if (!condition) throw TransferWireException(message)
}
private fun transferIdentity(bytes: ByteArray): ByteArray {
    transferCheck(bytes.size == 16 && bytes.any { it != 0.toByte() }, "Identity must be a nonzero 16-byte value")
    return bytes.copyOf()
}
