package com.aura.notes

import android.app.Application
import android.os.Handler
import android.os.Looper
import java.util.concurrent.CopyOnWriteArraySet
import java.util.concurrent.Executors

/** One process-wide owner survives Activity recreation. OS process death is
 * recovered from private published sources by CaptureStore, not a UI timer. */
class AuraApp : Application() {
    private val worker = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private val listeners = CopyOnWriteArraySet<() -> Unit>()
    lateinit var store: CaptureStore
        private set
    @Volatile var captures: List<LocalCapture> = emptyList()
        private set
    @Volatile var busy = true
        private set
    @Volatile var message: String? = null
        private set

    override fun onCreate() {
        super.onCreate()
        worker.execute {
            try {
                store = CaptureStore(this)
                captures = store.list()
                message = recoveryNotice()
            } catch (_: Exception) {
                message = "Your library could not be opened. Existing recordings have been retained."
            } finally {
                busy = false
                changed()
            }
        }
    }

    fun observe(listener: () -> Unit) { listeners.add(listener) }
    fun unobserve(listener: () -> Unit) { listeners.remove(listener) }

    /** Main-thread entry; busy is set before queueing so rapid taps coalesce. */
    fun perform(success: String, operation: (CaptureStore) -> Unit) {
        check(Looper.myLooper() == Looper.getMainLooper())
        if (busy) return
        if (!::store.isInitialized) {
            message = "Reopen AURA to retry the library. Existing sources are retained."
            changed()
            return
        }
        busy = true
        message = null
        changed()
        worker.execute {
            try {
                operation(store)
                captures = store.list()
                message = listOfNotNull(success, recoveryNotice()).joinToString("\n\n")
            } catch (error: Exception) {
                // Provider/file/parser exceptions can contain private paths or
                // note text. Do not put them in logs, analytics or UI strings.
                // Store errors are fixed application strings, never source text.
                message = if (error is CaptureStoreException) error.message
                    else "That operation could not be completed. Existing sources are retained."
                // Validation can quarantine a changed bundle. Do not leave its
                // old playable row on screen after an unsuccessful operation.
                runCatching { captures = store.list() }
            } finally {
                busy = false
                changed()
            }
        }
    }

    private fun recoveryNotice(): String? = store.recoveryWarnings.distinct()
        .takeIf { it.isNotEmpty() }?.joinToString(" ")

    private fun changed() { main.post { listeners.forEach { it() } } }
}
