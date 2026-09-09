package com.aura.notes

import android.content.ContentValues
import android.content.Context
import android.database.DatabaseErrorHandler
import android.database.sqlite.SQLiteDatabase
import android.system.Os
import android.system.OsConstants
import com.aura.capture.ArchiveStream
import com.aura.capture.AuraArchive
import com.aura.capture.TransferResponse
import com.aura.capture.TransferSelection
import com.aura.capture.VerifiedArchive
import java.io.Closeable
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.channels.FileLock
import java.nio.file.Files
import java.security.MessageDigest

class DownloadStoreException(message: String) : IOException(message)

/** Validated source preservation, not decoded playback or a device erase grant. */
data class DownloadProgress(
    val key: String,
    val committedBytes: Long,
    val receivedBytes: Long,
    val exportBytes: Long,
    val complete: Boolean,
    val receiptHex: String?,
)

/** One blocking foreground download owner. A lifetime file lock serializes all
 * sessions/processes. Exact complete records and their resume metadata commit in
 * one FULL-or-stronger SQLite transaction; partial records remain only in RAM.
 * No GATT, enrollment, background scheduling, source deletion or release exists
 * here. A trusted caller must obtain selection/READ/FINISH through TransferWire.
 */
class DownloadStore(context: Context) {
    private val root = File(context.applicationContext.noBackupFilesDir, "a04-downloads")

    fun open(selection: TransferSelection): DownloadSession {
        requireDownload(root.isDirectory || root.mkdir(), "Could not create private download storage")
        requireDownload(!Files.isSymbolicLink(root.toPath()), "Private download storage must not be a symbolic link")
        syncDownloadDirectory(root.parentFile!!)
        val lockPath = File(root, ".owner.lock")
        requireDownload(!Files.isSymbolicLink(lockPath.toPath()), "Download lock must not be a symbolic link")
        val ownerPath = lockPath.canonicalPath
        // Reserve before opening any second channel: closing that second channel
        // can release the first channel's process-wide OS lock on some systems.
        val reservation = DownloadOwnerReservations.acquire(ownerPath)
        var lockFile: RandomAccessFile? = null
        var lock: FileLock? = null
        var database: SQLiteDatabase? = null
        try {
            val file = RandomAccessFile(lockPath, "rw")
            lockFile = file
            lock = file.channel.tryLock()
            requireDownload(lock != null, "Another download owner is active")
            val db = SQLiteDatabase.openDatabase(File(root, "downloads.sqlite").absolutePath, null,
                SQLiteDatabase.CREATE_IF_NECESSARY, DatabaseErrorHandler {
                    throw DownloadStoreException("Download database is corrupt; its files have been retained")
                })
            database = db
            configure(db)
            syncDownloadDirectory(root)
            return DownloadSession(db, lock!!, file, selection) {
                DownloadOwnerReservations.release(ownerPath, reservation)
            }
        } catch (error: Throwable) {
            try { database?.close() } catch (close: Throwable) { error.addSuppressed(close) }
            try { lock?.release() } catch (close: Throwable) { error.addSuppressed(close) }
            try { lockFile?.close() } catch (close: Throwable) { error.addSuppressed(close) }
            DownloadOwnerReservations.release(ownerPath, reservation)
            throw error
        }
    }

    private fun configure(db: SQLiteDatabase) {
        db.rawQuery("PRAGMA journal_mode = DELETE", null).use {
            requireDownload(it.moveToFirst() && it.getString(0).equals("delete", true), "Durable rollback journal required")
        }
        db.execSQL("PRAGMA synchronous = EXTRA")
        db.rawQuery("PRAGMA synchronous", null).use {
            requireDownload(it.moveToFirst() && it.getInt(0) >= 2, "SQLite FULL synchronization required")
        }
        db.setForeignKeyConstraintsEnabled(true)
        val version = db.version
        requireDownload(version in 0..1, "Unsupported download database version")
        if (version == 0) transaction(db) {
            db.rawQuery("SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'android_metadata'", null).use {
                requireDownload(it.moveToFirst() && it.getInt(0) == 0, "Unknown database retained; initialization refused")
            }
            db.execSQL("""CREATE TABLE downloads (
                revision TEXT PRIMARY KEY NOT NULL, descriptor BLOB NOT NULL,
                committed INTEGER NOT NULL CHECK(committed >= 0),
                record_count INTEGER NOT NULL CHECK(record_count >= 0), receipt BLOB,
                finished INTEGER NOT NULL CHECK(finished IN (0,1)), created_ms INTEGER NOT NULL)""")
            db.execSQL("""CREATE TABLE records (
                revision TEXT NOT NULL REFERENCES downloads(revision), ordinal INTEGER NOT NULL,
                start INTEGER NOT NULL CHECK(start >= 0), wire BLOB NOT NULL CHECK(length(wire) BETWEEN 26 AND 1301),
                PRIMARY KEY(revision, ordinal), UNIQUE(revision, start))""")
            db.version = 1
        }
    }
}

class DownloadSession internal constructor(
    private val db: SQLiteDatabase,
    private val lock: FileLock,
    private val lockFile: RandomAccessFile,
    private val selection: TransferSelection,
    private val releaseReservation: () -> Unit,
) : Closeable {
    private val descriptor = downloadDescriptor(selection)
    val key: String = downloadHex(MessageDigest.getInstance("SHA-256").digest(descriptor))
    private var closed = false
    private var faulted = false
    private var committed = 0L
    private var recordCount = 0L
    private var committedReceipt: ByteArray? = null
    private var complete = false
    private val staged = ArrayList<Pair<Long, ByteArray>>()
    private val stream: ArchiveStream
    private var lastOffset: Long? = null
    private var lastData: ByteArray? = null

    init {
        if (row() == null) transaction(db) {
            db.insertOrThrow("downloads", null, ContentValues().apply {
                put("revision", key); put("descriptor", descriptor); put("committed", 0L)
                put("record_count", 0L); putNull("receipt"); put("finished", 0)
                put("created_ms", System.currentTimeMillis())
            })
        }
        stream = replay()
        val current = row() ?: throw DownloadStoreException("Missing download metadata")
        committed = current.offset; recordCount = current.count
        committedReceipt = current.receipt?.copyOf(); complete = current.finished
        // Replayed records must not be appended again by the next transaction.
        staged.clear()
    }

    @Synchronized fun progress(): DownloadProgress {
        usable()
        return result()
    }

    @Synchronized fun append(response: TransferResponse.ReadData): DownloadProgress = guarded {
        requireDownload(response.handle == selection.handle, "READ belongs to another selected handle")
        val data = response.bytes()
        if (lastOffset == response.offset) {
            requireDownload(lastData?.contentEquals(data) == true, "Retried READ changed its bytes")
            return@guarded result()
        }
        requireDownload(!complete, "Completed source cannot accept more READ data")
        val before = stream.snapshot()
        requireDownload(response.offset == before.receivedBytes && data.size <= 256 &&
            response.offset <= selection.exportBytes && data.size <= selection.exportBytes - response.offset,
            "READ offset or length does not match the current stream")
        requireDownload(data.isNotEmpty() || response.offset == selection.exportBytes,
            "Zero READ before selected EOF")
        staged.clear()
        stream.feed(data)
        val after = stream.snapshot()
        requireDownload(after.receivedBytes == response.offset + data.size, "Validator did not consume exact READ")
        if (staged.isNotEmpty()) {
            val nextReceipt = after.receipt?.encode()
            transaction(db) {
                checkMetadata()
                var offset = committed
                var ordinal = recordCount
                for ((start, wire) in staged) {
                    requireDownload(start == offset, "Validated records are not contiguous")
                    db.insertOrThrow("records", null, ContentValues().apply {
                        put("revision", key); put("ordinal", ordinal++); put("start", start); put("wire", wire)
                    })
                    offset += wire.size
                }
                requireDownload(offset == after.validatedOffset, "Committed record boundary differs from validator")
                val changed = db.update("downloads", ContentValues().apply {
                    put("committed", offset); put("record_count", ordinal); put("receipt", nextReceipt)
                }, "revision = ?", arrayOf(key))
                requireDownload(changed == 1, "Download metadata update failed")
            }
            // Publication happens only after endTransaction returns successfully.
            committed = after.validatedOffset; recordCount += staged.size
            committedReceipt = nextReceipt?.copyOf()
        }
        staged.clear()
        lastOffset = response.offset; lastData = data.copyOf()
        result()
    }

    @Synchronized fun finish(response: TransferResponse.Finished): DownloadProgress = guarded {
        requireDownload(response.selection.handle == selection.handle &&
            downloadDescriptor(response.selection).contentEquals(descriptor), "FINISH differs from the selected source")
        if (complete) return@guarded result()
        val progress = stream.snapshot()
        requireDownload(progress.receivedBytes == selection.exportBytes &&
            progress.validatedOffset == committed && committed == selection.exportBytes && progress.bufferedBytes == 0,
            "FINISH requires every selected source byte to be committed")
        stream.finish()
        transaction(db) {
            checkMetadata()
            requireDownload(db.update("downloads", ContentValues().apply { put("finished", 1) },
                "revision = ?", arrayOf(key)) == 1, "Completion transaction failed")
        }
        complete = true
        result()
    }

    /** Exclusive complete-source copy. A failed copy is retained, never reused
     * as a saved source. This does not decode audio or insert a playback row.
     * CaptureStore's existing import path has a separate 128 MiB limit.
     */
    @Synchronized fun export(destination: File): VerifiedArchive = guarded {
        requireDownload(complete, "Download is not durably complete")
        requireDownload(destination.parentFile?.isDirectory == true && destination.createNewFile(),
            "Export requires a new file in an existing private directory")
        FileOutputStream(destination).use { output ->
            replay { output.write(it) }
            output.flush(); output.fd.sync()
        }
        syncDownloadDirectory(destination.parentFile!!)
        val verified = AuraArchive.verify(destination, selection.physicalReceipt.encode())
        requireDownload(verified.fileBytes == selection.exportBytes &&
            verified.capture.encode().contentEquals(selection.manifest.encode()), "Export differs from selection")
        verified
    }

    private fun replay(copy: ((ByteArray) -> Unit)? = null): ArchiveStream {
        val metadata = row() ?: throw DownloadStoreException("Missing download metadata")
        requireDownload(metadata.descriptor.contentEquals(descriptor) && metadata.offset in 0..selection.exportBytes &&
            metadata.count in 0..1_000_002, "Download identity or metadata bounds changed")
        var collecting = false
        var replayedRecords = 0L
        val validator = ArchiveStream(expectedManifest = selection.manifest.encode(),
            physicalAck = selection.physicalReceipt.encode(), recordVisitor = { start, wire ->
                if (collecting) {
                    requireDownload(staged.sumOf { it.second.size } + wire.size <= 1556, "Validated batch exceeds bounded input")
                    staged += start to wire.copyOf()
                } else replayedRecords++
            })
        var ordinal = 0L
        var offset = 0L
        db.query("records", arrayOf("ordinal", "start", "wire"), "revision = ?", arrayOf(key),
            null, null, "ordinal ASC").use { cursor ->
            while (cursor.moveToNext()) {
                cancelled()
                requireDownload(ordinal < metadata.count && cursor.getLong(0) == ordinal && cursor.getLong(1) == offset,
                    "Saved record ordinal or offset is missing, repeated or inconsistent")
                val wire = cursor.getBlob(2)
                requireDownload(wire.size in 26..1301 && wire.size <= selection.exportBytes - offset,
                    "Saved record exceeds source bounds")
                var at = 0
                while (at < wire.size) {
                    val end = minOf(at + 256, wire.size)
                    validator.feed(wire.copyOfRange(at, end)); at = end
                }
                offset += wire.size; ordinal++
                requireDownload(replayedRecords == ordinal && validator.snapshot().bufferedBytes == 0 &&
                    validator.snapshot().validatedOffset == offset,
                    "Saved row is not an exact complete record")
                copy?.invoke(wire)
            }
        }
        val progress = validator.snapshot()
        requireDownload(ordinal == metadata.count && offset == metadata.offset && progress.validatedOffset == offset &&
            nullableBytesEqual(metadata.receipt, progress.receipt?.encode()), "Resume metadata differs from verified records")
        if (progress.seal != null) {
            requireDownload(offset == selection.exportBytes, "Saved seal does not end at selected EOF")
            validator.finish()
        }
        requireDownload(!metadata.finished || validator.snapshot().complete, "Finished metadata lacks complete source")
        collecting = true
        return validator
    }

    private data class Row(val descriptor: ByteArray, val offset: Long, val count: Long,
        val receipt: ByteArray?, val finished: Boolean)

    private fun row(): Row? = db.query("downloads", arrayOf("descriptor", "committed", "record_count", "receipt", "finished"),
        "revision = ?", arrayOf(key), null, null, null).use {
        if (!it.moveToFirst()) null else {
            requireDownload(it.getInt(4) in 0..1, "Invalid completion state")
            Row(it.getBlob(0), it.getLong(1), it.getLong(2), if (it.isNull(3)) null else it.getBlob(3), it.getInt(4) == 1)
        }
    }

    private fun checkMetadata() {
        val row = row() ?: throw DownloadStoreException("Missing active download")
        requireDownload(row.descriptor.contentEquals(descriptor) && row.offset == committed && row.count == recordCount &&
            row.finished == complete && nullableBytesEqual(row.receipt, committedReceipt), "Active download metadata changed")
    }

    private fun result() = DownloadProgress(key, committed, stream.snapshot().receivedBytes, selection.exportBytes,
        complete, committedReceipt?.let(::downloadHex))

    private fun usable() {
        requireDownload(!closed && !faulted && lock.isValid && db.isOpen, "Download session is closed or faulted; reopen to recover")
        cancelled()
    }

    private inline fun <T> guarded(action: () -> T): T {
        usable()
        try { return action() } catch (error: Throwable) {
            faulted = true; staged.clear(); lastData = null
            throw error
        }
    }

    @Synchronized override fun close() {
        if (closed) return
        closed = true; staged.clear(); lastData = null
        try { db.close() } finally {
            try { lock.release() } finally {
                try { lockFile.close() } finally { releaseReservation() }
            }
        }
    }
}

private object DownloadOwnerReservations {
    private val owners = HashMap<String, Any>()
    @Synchronized fun acquire(path: String): Any {
        requireDownload(path !in owners, "Another download owner is active in this process")
        return Any().also { owners[path] = it }
    }
    @Synchronized fun release(path: String, token: Any) {
        if (owners[path] === token) owners.remove(path)
    }
}

private fun downloadDescriptor(selection: TransferSelection): ByteArray {
    val incarnation = selection.storageIncarnation.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
    requireDownload(incarnation.size == 16, "Invalid storage incarnation")
    // ADS1 is a local revision descriptor, not a wire command or owner proof.
    return ByteBuffer.allocate(211).order(ByteOrder.LITTLE_ENDIAN).apply {
        put(byteArrayOf(65, 68, 83, 49, 1, 0, 0, 0)); put(incarnation)
        put(selection.manifest.encode()); put(selection.physicalReceipt.encode())
        putLong(selection.physicalBytes); putLong(selection.exportBytes)
        put(if (selection.derivedSeal) 1.toByte() else 0.toByte()); putLong(selection.allocationGeneration.toLong())
    }.array()
}

private fun nullableBytesEqual(a: ByteArray?, b: ByteArray?): Boolean =
    if (a == null || b == null) a == null && b == null else a.contentEquals(b)
private fun downloadHex(bytes: ByteArray) = bytes.joinToString("") { "%02x".format(it.toInt() and 255) }
private fun requireDownload(value: Boolean, message: String) { if (!value) throw DownloadStoreException(message) }
private fun cancelled() { if (Thread.currentThread().isInterrupted) throw DownloadStoreException("Download was cancelled") }
private inline fun <T> transaction(db: SQLiteDatabase, action: () -> T): T {
    db.beginTransaction()
    try { val result = action(); db.setTransactionSuccessful(); return result } finally { db.endTransaction() }
}
private fun syncDownloadDirectory(directory: File) {
    requireDownload(directory.isDirectory && !Files.isSymbolicLink(directory.toPath()), "Expected private download directory")
    val descriptor = Os.open(directory.absolutePath,
        OsConstants.O_RDONLY or OsConstants.O_NOFOLLOW or OsConstants.O_CLOEXEC, 0)
    try {
        requireDownload(OsConstants.S_ISDIR(Os.fstat(descriptor).st_mode), "Download descriptor is not a directory")
        Os.fsync(descriptor)
    } finally { Os.close(descriptor) }
}
