package com.aura.notes

import android.annotation.SuppressLint
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothProfile
import android.bluetooth.BluetoothStatusCodes
import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.Looper
import android.os.SystemClock
import com.aura.capture.BleFragmentResult
import com.aura.capture.BleResponseFragments
import com.aura.capture.TransferCommand
import java.util.UUID

/** Raw A04 GATT transport, not an enrolled or authenticated device connection.
 * Construction does not start a thread, connect, scan, bond or request permission.
 * The caller must separately obtain platform permission and an authenticated
 * TransferSession before using this with a recovery owner. Bond state, public
 * IDs and HELLO are never treated as ownership proof here.
 *
 * A single background worker calls exchange; close may run on any thread. One
 * HandlerThread owns platform operations and their callbacks. No application
 * notification queue is built: callbacks copy a bounded value and immediately
 * parse it under the state lock. State retains one active response and at most
 * one prior completed parser so an exact late retry cannot satisfy a new call.
 * Older completed transactions are discarded, not revalidated or authenticated.
 *
 * There is at most one internal exact command retry, only after successful ATT
 * write completion and a missing logical response. The caller's total deadline
 * includes connection, discovery, MTU, subscription, both writes and fragments.
 * Unknown write completion is never retried. Failure permanently ends lineage.
 *
 * Platform references: developer.android.com/reference/android/bluetooth/
 * BluetoothGatt, BluetoothGattCallback and BluetoothDevice. API 33 value-based
 * writes/callbacks avoid mutable characteristic values; API 29-32 use immediate
 * copies. The handler connect overload remains necessary for the API 29 floor.
 */
@SuppressLint("MissingPermission") // Caller grants permission; this class never activates permission/UI flows.
@Suppress("DEPRECATION")
class AndroidGattConnection(context: Context, private val device: BluetoothDevice) : TransferConnection {
    companion object {
        val SERVICE_UUID: UUID = UUID.fromString("7f520000-1b15-4f0d-8fe5-3f942170a004")
        val COMMAND_UUID: UUID = UUID.fromString("7f520001-1b15-4f0d-8fe5-3f942170a004")
        val RESPONSE_UUID: UUID = UUID.fromString("7f520002-1b15-4f0d-8fe5-3f942170a004")
        private val CCCD_UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")
        // A full source verification can have a separately configured budget up
        // to two hours. This bound is not a calibrated radio/flash throughput claim.
        private const val MAX_TIMEOUT_MS = 7_200_000L
        private const val RETRY_DELAY_MS = 2_500L
    }

    private enum class Phase { NEW, CONNECTING, NEED_DISCOVERY, DISCOVERING, NEED_MTU, MTU, NEED_SUBSCRIBE, SUBSCRIBING, READY, CLOSED }
    private class Generation
    private class Pending(val transaction: Int, val command: ByteArray, val deadline: Long) {
        var attempts = 0
        var retryRequested = false
        var accepted = false
        var acknowledged = false
        var writeInFlight = false
        var retryAt = Long.MAX_VALUE
        var parser: BleResponseFragments? = null
        var token: BleResponseFragments.Generation? = null
        var response: ByteArray? = null
    }
    private class Completed(val transaction: Int, val parser: BleResponseFragments,
                            val token: BleResponseFragments.Generation)

    private val appContext = context.applicationContext
    private val gate = Object()
    private var phase = Phase.NEW
    private var failure: String? = null
    private var generation: Generation? = Generation()
    private var owner: HandlerThread? = null
    private var handler: Handler? = null
    private var pumpQueued = false
    private var cleanupQueued = false
    private var gatt: BluetoothGatt? = null
    private var commandCharacteristic: BluetoothGattCharacteristic? = null
    private var responseCharacteristic: BluetoothGattCharacteristic? = null
    private var cccd: BluetoothGattDescriptor? = null
    private var actualMtu = BleResponseFragments.DEFAULT_ATT_MTU
    private var highWaterTransaction = 0
    private var pending: Pending? = null
    private var prior: Completed? = null

    override fun exchange(command: TransferCommand, timeoutMillis: Long): ByteArray {
        if (Looper.myLooper() === Looper.getMainLooper()) failCaller("Bluetooth exchange requires a background worker")
        if (timeoutMillis !in 1..MAX_TIMEOUT_MS) failCaller("Bluetooth exchange deadline is outside the supported bound")
        val bytes = command.encode()
        if (bytes.size !in 4..20 || command.transaction !in 1..65535) failCaller("Unsupported Bluetooth command")
        synchronized(gate) {
            if (handler != null && Looper.myLooper() === handler?.looper) failCaller("Bluetooth callback owner cannot block on exchange")
            failure?.let(::failCaller)
            if (pending != null) failCaller("Another Bluetooth exchange is active")
            if (command.transaction <= highWaterTransaction) failCaller("Bluetooth transaction must increase within this connection")
            val active = Pending(command.transaction, bytes, SystemClock.elapsedRealtime() + timeoutMillis)
            highWaterTransaction = command.transaction
            pending = active
            try {
                startOwnerLocked()
                schedulePumpLocked()
                while (true) {
                    failure?.let(::failCaller)
                    if (Thread.currentThread().isInterrupted) {
                        terminateLocked("Bluetooth exchange was interrupted")
                        failCaller("Bluetooth exchange was interrupted")
                    }
                    val now = SystemClock.elapsedRealtime()
                    if (now >= active.deadline) {
                        terminateLocked("Bluetooth exchange deadline expired")
                        failCaller("Bluetooth exchange deadline expired")
                    }
                    val response = active.response
                    if (response != null && active.accepted && active.acknowledged && !active.writeInFlight) {
                        prior?.parser?.reset()
                        prior = Completed(active.transaction, checkNotNull(active.parser), checkNotNull(active.token))
                        pending = null
                        return response.copyOf()
                    }
                    if (active.attempts == 1 && active.accepted && active.acknowledged && !active.writeInFlight &&
                        response == null && now >= active.retryAt && !active.retryRequested) {
                        active.retryRequested = true
                        schedulePumpLocked()
                    }
                    val wakeAt = if (active.attempts == 1 && active.accepted && active.acknowledged &&
                        !active.retryRequested && response == null) minOf(active.deadline, active.retryAt) else active.deadline
                    try { gate.wait(maxOf(1L, wakeAt - now)) } catch (_: InterruptedException) {
                        terminateLocked("Bluetooth exchange was interrupted")
                        Thread.currentThread().interrupt()
                        failCaller("Bluetooth exchange was interrupted")
                    }
                }
            } catch (error: TransferConnectionException) {
                throw error
            } catch (_: Exception) {
                terminateLocked("Bluetooth exchange failed")
                failCaller("Bluetooth exchange failed")
            }
        }
    }

    override fun close() = synchronized(gate) { terminateLocked("Bluetooth connection is closed") }

    /** Do not wait for HandlerThread.looper while holding gate: close must remain
     * able to cancel even before the new owner thread has been scheduled. */
    private fun startOwnerLocked() {
        if (owner != null) return
        val thread = object : HandlerThread("aura-gatt-owner") {
            override fun onLooperPrepared() {
                synchronized(gate) {
                    handler = Handler(looper)
                    if (phase == Phase.CLOSED) scheduleCleanupLocked() else schedulePumpLocked()
                }
            }
        }
        owner = thread
        try { thread.start() } catch (_: Exception) {
            owner = null
            terminateLocked("Bluetooth callback owner could not start")
        }
    }

    private fun schedulePumpLocked() {
        if (phase == Phase.CLOSED || pumpQueued) return
        val target = handler ?: return
        pumpQueued = true
        if (!target.post(::pump)) {
            pumpQueued = false
            terminateLocked("Bluetooth callback owner is unavailable")
        }
    }

    /** Mark the expected callback before invoking the platform outside gate.
     * A callback may occur synchronously before the platform method returns. */
    private fun pump() {
        try {
            val action: (() -> Unit)? = synchronized(gate) {
                pumpQueued = false
                if (phase == Phase.CLOSED) return
                if (pending?.let { SystemClock.elapsedRealtime() >= it.deadline } == true) {
                    terminateLocked("Bluetooth exchange deadline expired")
                    return
                }
                val epoch = generation ?: return
                when (phase) {
                    Phase.NEW -> {
                        phase = Phase.CONNECTING
                        val operation: () -> Unit = { connect(epoch) }
                        operation
                    }
                    Phase.NEED_DISCOVERY -> {
                        phase = Phase.DISCOVERING
                        val current = checkNotNull(gatt)
                        val operation: () -> Unit = {
                            if (synchronized(gate) { currentLocked(epoch, current) })
                                initiated(epoch, current.discoverServices(), "Bluetooth service discovery could not start")
                        }
                        operation
                    }
                    Phase.NEED_MTU -> {
                        phase = Phase.MTU
                        val current = checkNotNull(gatt)
                        val operation: () -> Unit = { requestMtu(epoch, current) }
                        operation
                    }
                    Phase.NEED_SUBSCRIBE -> {
                        phase = Phase.SUBSCRIBING
                        val current = checkNotNull(gatt)
                        val characteristic = checkNotNull(responseCharacteristic)
                        val descriptor = checkNotNull(cccd)
                        val operation: () -> Unit = { subscribe(epoch, current, characteristic, descriptor) }
                        operation
                    }
                    Phase.READY -> {
                        val request = pending
                        if (request == null || request.writeInFlight ||
                            !(request.attempts == 0 || request.retryRequested)) null
                        else {
                            // A late response can complete before the queued retry executes.
                            if (request.response != null) { request.retryRequested = false; gate.notifyAll(); null }
                            else {
                                if (request.attempts == 0) {
                                    request.parser = BleResponseFragments()
                                    request.token = request.parser!!.begin(request.transaction, actualMtu)
                                }
                                request.attempts++
                                request.retryRequested = false
                                request.accepted = false; request.acknowledged = false; request.writeInFlight = true
                                val current = checkNotNull(gatt)
                                val characteristic = checkNotNull(commandCharacteristic)
                                val operation: () -> Unit = { write(epoch, current, characteristic, request) }
                                operation
                            }
                        }
                    }
                    else -> null
                }
            }
            action?.invoke()
        } catch (_: SecurityException) {
            synchronized(gate) { terminateLocked("Bluetooth permission is unavailable") }
        } catch (_: Exception) {
            synchronized(gate) { terminateLocked("Bluetooth platform operation failed") }
        }
    }

    private fun connect(epoch: Generation) {
        if (!synchronized(gate) { generation === epoch && phase != Phase.CLOSED }) return
        val callback = callbacks(epoch)
        val connected = device.connectGatt(appContext, false, callback, BluetoothDevice.TRANSPORT_LE,
            BluetoothDevice.PHY_LE_1M_MASK, checkNotNull(handler))
        var closeReturned = false
        synchronized(gate) {
            if (generation !== epoch || phase == Phase.CLOSED) {
                if (gatt === connected) gatt = null
                closeReturned = true
            } else if (connected == null) terminateLocked("Bluetooth connection could not start")
            else if (gatt != null && gatt !== connected) {
                closeReturned = true
                terminateLocked("Bluetooth connection identity changed")
            } else gatt = connected
        }
        if (closeReturned) releaseGatt(connected)
    }

    private fun requestMtu(epoch: Generation, current: BluetoothGatt) {
        if (!synchronized(gate) { currentLocked(epoch, current) }) return
        val accepted = current.requestMtu(517)
        synchronized(gate) {
            if (!currentLocked(epoch, current)) return
            if (!accepted && phase == Phase.MTU) {
                // No MTU operation was started. Retain the protocol-safe default.
                actualMtu = BleResponseFragments.DEFAULT_ATT_MTU
                phase = Phase.NEED_SUBSCRIBE
                schedulePumpLocked()
            }
        }
    }

    private fun subscribe(epoch: Generation, current: BluetoothGatt,
                          characteristic: BluetoothGattCharacteristic, descriptor: BluetoothGattDescriptor) {
        if (!synchronized(gate) { currentLocked(epoch, current) }) return
        if (!current.setCharacteristicNotification(characteristic, true)) {
            initiated(epoch, false, "Bluetooth notifications could not be enabled")
            return
        }
        val value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE.copyOf()
        if (!synchronized(gate) { currentLocked(epoch, current) }) return
        val accepted = if (Build.VERSION.SDK_INT >= 33) {
            current.writeDescriptor(descriptor, value) == BluetoothStatusCodes.SUCCESS
        } else {
            descriptor.value = value
            current.writeDescriptor(descriptor)
        }
        initiated(epoch, accepted, "Bluetooth subscription write could not start")
    }

    private fun write(epoch: Generation, current: BluetoothGatt,
                      characteristic: BluetoothGattCharacteristic, request: Pending) {
        if (!synchronized(gate) { currentLocked(epoch, current) && pending === request }) return
        val value = request.command.copyOf()
        val accepted = if (Build.VERSION.SDK_INT >= 33) {
            current.writeCharacteristic(characteristic, value, BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT) == BluetoothStatusCodes.SUCCESS
        } else {
            characteristic.writeType = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
            characteristic.value = value
            current.writeCharacteristic(characteristic)
        }
        synchronized(gate) {
            if (!currentLocked(epoch, current) || pending !== request) return
            if (!accepted) terminateLocked("Bluetooth command write could not start")
            else { request.accepted = true; gate.notifyAll() }
        }
    }

    private fun initiated(epoch: Generation, accepted: Boolean, message: String) = synchronized(gate) {
        if (generation === epoch && phase != Phase.CLOSED && !accepted) terminateLocked(message)
    }

    private fun callbacks(epoch: Generation) = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(current: BluetoothGatt, status: Int, newState: Int) = callback {
            synchronized(gate) {
                if (generation !== epoch || phase == Phase.CLOSED) return@synchronized
                // Only this first callback may bind a provisional instance while
                // connectGatt is still on the stack. The returned instance must match.
                if (gatt == null && phase == Phase.CONNECTING) gatt = current
                if (!currentLocked(epoch, current)) return@synchronized
                if (status != BluetoothGatt.GATT_SUCCESS || newState == BluetoothProfile.STATE_DISCONNECTED) {
                    terminateLocked("Bluetooth connection ended")
                } else if (newState == BluetoothProfile.STATE_CONNECTED && phase == Phase.CONNECTING) {
                    phase = Phase.NEED_DISCOVERY
                    schedulePumpLocked()
                }
            }
        }

        override fun onServicesDiscovered(current: BluetoothGatt, status: Int) = callback {
            synchronized(gate) {
                if (!currentLocked(epoch, current) || phase != Phase.DISCOVERING) return@synchronized
                if (status != BluetoothGatt.GATT_SUCCESS) { terminateLocked("Bluetooth service discovery failed"); return@synchronized }
                val services = current.services.filter { it.uuid == SERVICE_UUID }
                if (services.size != 1) { terminateLocked("Required Bluetooth service is unavailable"); return@synchronized }
                val commands = services.single().characteristics.filter { it.uuid == COMMAND_UUID }
                val responses = services.single().characteristics.filter { it.uuid == RESPONSE_UUID }
                if (commands.size != 1 || responses.size != 1 ||
                    commands.single().properties and BluetoothGattCharacteristic.PROPERTY_WRITE == 0 ||
                    responses.single().properties and BluetoothGattCharacteristic.PROPERTY_NOTIFY == 0) {
                    terminateLocked("Required Bluetooth characteristics are unavailable"); return@synchronized
                }
                val descriptors = responses.single().descriptors.filter { it.uuid == CCCD_UUID }
                if (descriptors.size != 1) { terminateLocked("Bluetooth notification descriptor is unavailable"); return@synchronized }
                commandCharacteristic = commands.single(); responseCharacteristic = responses.single(); cccd = descriptors.single()
                phase = Phase.NEED_MTU
                schedulePumpLocked()
            }
        }

        override fun onServiceChanged(current: BluetoothGatt) = callback {
            synchronized(gate) {
                if (currentLocked(epoch, current)) terminateLocked("Bluetooth services changed; reconnect required")
            }
        }

        override fun onMtuChanged(current: BluetoothGatt, mtu: Int, status: Int) = callback {
            synchronized(gate) {
                if (!currentLocked(epoch, current)) return@synchronized
                if (phase == Phase.MTU) {
                    if (status == BluetoothGatt.GATT_SUCCESS && mtu !in 23..517) {
                        terminateLocked("Bluetooth MTU is outside supported bounds"); return@synchronized
                    }
                    actualMtu = if (status == BluetoothGatt.GATT_SUCCESS) mtu else BleResponseFragments.DEFAULT_ATT_MTU
                    phase = Phase.NEED_SUBSCRIBE; schedulePumpLocked()
                } else if (status == BluetoothGatt.GATT_SUCCESS && mtu != actualMtu) {
                    terminateLocked("Bluetooth MTU changed outside negotiation")
                }
            }
        }

        override fun onDescriptorWrite(current: BluetoothGatt, descriptor: BluetoothGattDescriptor, status: Int) = callback {
            synchronized(gate) {
                if (!currentLocked(epoch, current) || phase != Phase.SUBSCRIBING || descriptor !== cccd ||
                    descriptor.characteristic !== responseCharacteristic) return@synchronized
                if (status != BluetoothGatt.GATT_SUCCESS) terminateLocked("Bluetooth subscription failed")
                else { phase = Phase.READY; schedulePumpLocked(); gate.notifyAll() }
            }
        }

        override fun onCharacteristicWrite(current: BluetoothGatt, characteristic: BluetoothGattCharacteristic, status: Int) = callback {
            synchronized(gate) {
                if (!currentLocked(epoch, current) || characteristic !== commandCharacteristic) return@synchronized
                val active = pending ?: return@synchronized
                if (!active.writeInFlight) return@synchronized
                if (status != BluetoothGatt.GATT_SUCCESS) { terminateLocked("Bluetooth command write failed"); return@synchronized }
                active.writeInFlight = false; active.acknowledged = true
                val now = SystemClock.elapsedRealtime()
                active.retryAt = now + minOf(RETRY_DELAY_MS, maxOf(1L, (active.deadline - now) / 2))
                gate.notifyAll()
            }
        }

        override fun onCharacteristicChanged(current: BluetoothGatt, characteristic: BluetoothGattCharacteristic, value: ByteArray) =
            notification(epoch, current, characteristic) { value }

        override fun onCharacteristicChanged(current: BluetoothGatt, characteristic: BluetoothGattCharacteristic) {
            // The API 33 overload is the sole path on 33+, even if a vendor also
            // invokes this legacy callback. Never call super and parse twice.
            if (Build.VERSION.SDK_INT < 33) notification(epoch, current, characteristic) { characteristic.value }
        }
    }

    private inline fun callback(action: () -> Unit) {
        try { action() } catch (_: Exception) {
            synchronized(gate) { terminateLocked("Bluetooth callback failed") }
        }
    }

    private fun notification(epoch: Generation, current: BluetoothGatt, characteristic: BluetoothGattCharacteristic,
                             value: () -> ByteArray?) = callback {
        synchronized(gate) {
            if (!currentLocked(epoch, current) || characteristic !== responseCharacteristic) return@synchronized
            val raw = value()
            if (raw == null || raw.size !in 9..minOf(514, actualMtu - 3)) {
                terminateLocked("Bluetooth fragment exceeds supported bounds"); return@synchronized
            }
            val owned = raw.copyOf() // First copy is bounded and follows identity checks.
            val transaction = (owned[2].toInt() and 255) or ((owned[3].toInt() and 255) shl 8)
            val active = pending
            val previous = prior
            if (previous != null && transaction == previous.transaction) {
                if (previous.parser.accept(previous.token, owned) !is BleFragmentResult.Duplicate)
                    terminateLocked("Completed Bluetooth response changed")
                return@synchronized
            }
            if (previous != null && transaction in 1 until previous.transaction) return@synchronized
            if (phase != Phase.READY || active == null || transaction != active.transaction ||
                active.parser == null || active.token == null) {
                terminateLocked("Bluetooth response has no matching command"); return@synchronized
            }
            when (val result = active.parser!!.accept(active.token!!, owned)) {
                is BleFragmentResult.Complete -> { active.response = result.bytes(); gate.notifyAll() }
                is BleFragmentResult.Pending, is BleFragmentResult.Duplicate -> Unit
                BleFragmentResult.Stale -> terminateLocked("Bluetooth response generation changed")
            }
        }
    }

    private fun currentLocked(epoch: Generation, current: BluetoothGatt) =
        phase != Phase.CLOSED && generation === epoch && gatt === current

    private fun terminateLocked(message: String) {
        if (phase == Phase.CLOSED) return
        failure = message; phase = Phase.CLOSED; generation = null
        pending?.parser?.reset(); pending = null
        prior?.parser?.reset(); prior = null
        gate.notifyAll()
        scheduleCleanupLocked()
    }

    private fun scheduleCleanupLocked() {
        if (cleanupQueued) return
        val target = handler ?: return // onLooperPrepared will finish a pre-start close.
        cleanupQueued = true
        target.removeCallbacksAndMessages(null)
        pumpQueued = false
        if (!target.postAtFrontOfQueue(::cleanup)) {
            // No live looper can own GATT now. Keep cross-thread close nonblocking.
            Thread(::cleanup, "aura-gatt-cleanup").apply { isDaemon = true; start() }
        }
    }

    private fun cleanup() {
        val current = synchronized(gate) {
            val selected = gatt
            gatt = null; commandCharacteristic = null; responseCharacteristic = null; cccd = null
            selected
        }
        try { releaseGatt(current) } finally { owner?.quitSafely() }
    }

    private fun releaseGatt(current: BluetoothGatt?) {
        if (current == null) return
        try { current.disconnect() } catch (_: Exception) { /* Already disconnected or permission revoked. */ }
        finally { try { current.close() } catch (_: Exception) { /* All local callbacks are invalidated first. */ } }
    }

    private fun failCaller(message: String): Nothing = throw TransferConnectionException(message)
}
