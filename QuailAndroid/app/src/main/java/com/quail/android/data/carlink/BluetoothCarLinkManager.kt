package com.quail.android.data.carlink

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothSocket
import android.content.Context
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.BufferedReader
import java.io.IOException
import java.io.InputStreamReader
import java.io.OutputStream

/** Fixed RFCOMM channel both sides hardcode — matches
 * quail_maps_car/carlink/bluetooth_link.py's RFCOMM_CHANNEL. Sidesteps SDP
 * service-record discovery, which the public
 * [BluetoothDevice.createRfcommSocketToServiceRecord] path requires (the
 * car side would need BlueZ D-Bus profile registration, not just a plain
 * socket) — [createRfcommSocket] below is a documented-if-unofficial
 * reflection call used by most Android "serial over Bluetooth" apps for
 * exactly this reason. */
private const val RFCOMM_CHANNEL = 4

sealed class CarLinkEvent {
    data class RouteConfirmed(val minutes: Int, val distanceMi: Double) : CarLinkEvent()
    data class Position(
        val lat: Double,
        val lon: Double,
        val heading: Double,
        val etaMin: Int,
        val remainingMi: Double,
    ) : CarLinkEvent()
    object Arrived : CarLinkEvent()
    data class Error(val message: String) : CarLinkEvent()
}

/** Talks to the car's [BluetoothCarLink] over RFCOMM whenever this phone is
 * connected to it — sends a picked destination, the car does the actual
 * routing/driving with its own local extract data. When disconnected,
 * TileMapViewModel's existing local routing path is unaffected; this class
 * is purely additive. */
class BluetoothCarLinkManager(private val context: Context) {

    private val _connected = MutableStateFlow(false)
    val connected: StateFlow<Boolean> = _connected.asStateFlow()

    private val _events = MutableSharedFlow<CarLinkEvent>(extraBufferCapacity = 16)
    val events = _events.asSharedFlow()

    private var socket: BluetoothSocket? = null
    private var outputStream: OutputStream? = null
    private var connectionJob: Job? = null
    private val scope = CoroutineScope(Dispatchers.IO)

    /** Call once a paired car device is known (e.g. from the phone's own
     * Bluetooth settings — this app doesn't drive pairing itself, only the
     * post-pairing data channel). Retries the connection while the target
     * device is a recognized paired device but not yet reachable (car app
     * not running yet, still booting, etc.). */
    @SuppressLint("MissingPermission")
    fun connectToCar(carMac: String) {
        connectionJob?.cancel()
        connectionJob = scope.launch {
            val adapter = BluetoothAdapter.getDefaultAdapter() ?: return@launch
            while (isActive) {
                val device = adapter.getRemoteDevice(carMac)
                try {
                    val sock = createRfcommSocket(device, RFCOMM_CHANNEL)
                    sock.connect()
                    socket = sock
                    outputStream = sock.outputStream
                    _connected.value = true
                    readLoop(sock)
                } catch (e: IOException) {
                    // Car not reachable yet (out of range, app not started,
                    // still booting) — back off and retry rather than
                    // giving up, since "reconnect automatically once back
                    // in range" is the whole point of this being
                    // connection-state-driven rather than one-shot.
                } finally {
                    _connected.value = false
                    closeQuietly()
                }
                kotlinx.coroutines.delay(3000)
            }
        }
    }

    fun disconnect() {
        connectionJob?.cancel()
        closeQuietly()
        _connected.value = false
    }

    /** Reflection-based fixed-channel RFCOMM socket — see RFCOMM_CHANNEL's
     * doc comment for why the public SDP-based API isn't used here. */
    private fun createRfcommSocket(device: BluetoothDevice, channel: Int): BluetoothSocket {
        val method = device.javaClass.getMethod("createRfcommSocket", Int::class.javaPrimitiveType)
        return method.invoke(device, channel) as BluetoothSocket
    }

    private suspend fun readLoop(sock: BluetoothSocket) {
        val reader = BufferedReader(InputStreamReader(sock.inputStream, Charsets.UTF_8))
        while (isActive) {
            val line = try {
                reader.readLine()
            } catch (e: IOException) {
                null
            } ?: break
            parseLine(line)?.let { _events.emit(it) }
        }
    }

    private fun parseLine(line: String): CarLinkEvent? {
        val json = try {
            JSONObject(line)
        } catch (e: org.json.JSONException) {
            return null
        }
        return when (json.optString("type")) {
            "route_confirmed" -> CarLinkEvent.RouteConfirmed(
                json.optInt("minutes"),
                json.optDouble("distance_mi"),
            )
            "position" -> CarLinkEvent.Position(
                json.optDouble("lat"),
                json.optDouble("lon"),
                json.optDouble("heading"),
                json.optInt("eta_min"),
                json.optDouble("remaining_mi"),
            )
            "arrived" -> CarLinkEvent.Arrived
            "error" -> CarLinkEvent.Error(json.optString("message"))
            else -> null
        }
    }

    /** Sends the currently-picked destination to the car — call this from
     * TileMapViewModel.setDestination() (or a "Send to Car" affordance)
     * whenever [connected] is true, instead of routing locally. */
    suspend fun sendDestination(lat: Double, lon: Double, name: String) {
        val payload = JSONObject().apply {
            put("type", "destination")
            put("lat", lat)
            put("lon", lon)
            put("name", name)
        }
        withContext(Dispatchers.IO) {
            try {
                outputStream?.write((payload.toString() + "\n").toByteArray(Charsets.UTF_8))
                outputStream?.flush()
            } catch (e: IOException) {
                // Connection dropped mid-send — readLoop's own IOException
                // handling already tears the socket down and flips
                // `connected` back to false; nothing extra to do here.
            }
        }
    }

    private fun closeQuietly() {
        try {
            outputStream?.close()
        } catch (e: IOException) {
            // best-effort cleanup
        }
        try {
            socket?.close()
        } catch (e: IOException) {
            // best-effort cleanup
        }
        outputStream = null
        socket = null
    }
}
