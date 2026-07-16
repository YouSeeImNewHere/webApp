from __future__ import annotations

import json
import socket
import threading

from PySide6.QtCore import QObject, Signal

# Fixed RFCOMM channel both sides hardcode, sidestepping SDP service-record
# registration — BlueZ's D-Bus profile-registration API is real overhead
# to maintain for a single known paired phone talking to a single known
# car. The Android side opens this same channel directly (see
# BluetoothCarLinkManager.kt) instead of the public SDP-UUID-lookup path.
RFCOMM_CHANNEL = 4

_ENCODING = "utf-8"


class BluetoothCarLink(QObject):
    """Background RFCOMM server — accepts a connection only from one
    whitelisted paired phone MAC address, then exchanges newline-delimited
    JSON messages over it.

    Runs its own accept/read loop in a daemon thread since blocking socket
    calls can't live on the Qt GUI thread; Qt automatically queues signal
    emissions from another thread onto the receiver's thread, so every
    signal below is safe to connect directly to GUI-thread slots without
    extra plumbing.
    """

    connected = Signal(bool)
    destination_received = Signal(float, float, str)  # lat, lon, name
    # (minutes, distance_mi) — the phone's own already-computed route
    # numbers, or (-1, -1.0) when the phone didn't include them (older
    # client, or its own route wasn't ready yet). The car's local routing
    # engine and the phone's server-backed one can legitimately disagree
    # (different road data/algorithm), which is exactly the mismatch this
    # exists to paper over: displayed ETA/distance defer to the phone
    # whenever it sent real numbers, since that's the one the user is
    # actually looking at and trusting.
    start_drive_requested = Signal(int, float)
    # Real GPS fix streamed from the phone — replaces the fake timer-driven
    # progress simulation NavScreen used to run on its own.
    position_received = Signal(float, float)  # lat, lon

    def __init__(self, allowed_mac: str, parent=None):
        super().__init__(parent)
        self._allowed_mac = allowed_mac.upper()
        self._server_sock: socket.socket | None = None
        self._client_sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self._allowed_mac:
            # No phone configured yet (see carlink/config.py) — rather
            # than bind/listen for a connection that can never pass the
            # allowlist check, just don't start at all.
            return
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        with self._lock:
            for sock in (self._client_sock, self._server_sock):
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass

    def _serve_forever(self) -> None:
        print(f"[carlink] listening on RFCOMM channel {RFCOMM_CHANNEL}, allowed phone {self._allowed_mac}", flush=True)
        while self._running:
            try:
                self._accept_and_handle()
            except OSError as e:
                # TEMPORARY DIAGNOSTIC — was silently swallowing bind/
                # listen/accept errors (e.g. "Address already in use" from
                # a socket not cleanly released on a previous run), which
                # made a permanently-failing listener indistinguishable
                # from "nothing has connected yet" from the outside.
                print(f"[carlink] server loop error: {e!r}", flush=True)

    def _accept_and_handle(self) -> None:
        server = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        # "" isn't accepted as a local BT address here (confirmed on
        # device: raises "bad bluetooth address") — the all-zeros address
        # is AF_BLUETOOTH's actual "bind to any local adapter" wildcard.
        server.bind(("00:00:00:00:00:00", RFCOMM_CHANNEL))
        server.listen(1)
        with self._lock:
            self._server_sock = server
        try:
            client, addr = server.accept()
        except OSError as e:
            print(f"[carlink] accept() failed: {e!r}", flush=True)
            return
        finally:
            server.close()
            with self._lock:
                self._server_sock = None

        remote_mac = addr[0].upper()
        print(f"[carlink] incoming connection from {remote_mac}", flush=True)
        if remote_mac != self._allowed_mac:
            print(f"[carlink] rejected — does not match allowed {self._allowed_mac}", flush=True)
            client.close()
            return

        with self._lock:
            self._client_sock = client
        print("[carlink] connected", flush=True)
        self.connected.emit(True)
        try:
            self._read_loop(client)
        finally:
            client.close()
            with self._lock:
                self._client_sock = None
            print("[carlink] disconnected", flush=True)
            self.connected.emit(False)

    def _read_loop(self, client: socket.socket) -> None:
        buf = b""
        while self._running:
            chunk = client.recv(4096)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                self._handle_line(line)

    def _handle_line(self, line: bytes) -> None:
        try:
            msg = json.loads(line.decode(_ENCODING))
        except (ValueError, UnicodeDecodeError):
            return
        print(f"[carlink] received: {msg}", flush=True)
        msg_type = msg.get("type")
        if msg_type == "destination":
            lat, lon = msg.get("lat"), msg.get("lon")
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                self.destination_received.emit(float(lat), float(lon), str(msg.get("name", "")))
        elif msg_type == "start_drive":
            minutes = msg.get("minutes")
            distance_mi = msg.get("distance_mi")
            has_minutes = isinstance(minutes, (int, float))
            has_distance = isinstance(distance_mi, (int, float))
            self.start_drive_requested.emit(
                int(minutes) if has_minutes else -1,
                float(distance_mi) if has_distance else -1.0,
            )
        elif msg_type == "position":
            lat, lon = msg.get("lat"), msg.get("lon")
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                self.position_received.emit(float(lat), float(lon))

    def _send(self, payload: dict) -> None:
        with self._lock:
            client = self._client_sock
        if client is None:
            return
        try:
            client.sendall((json.dumps(payload) + "\n").encode(_ENCODING))
        except OSError:
            pass

    def send_route_confirmed(self, minutes: int, distance_mi: float) -> None:
        self._send({"type": "route_confirmed", "minutes": minutes, "distance_mi": distance_mi})

    def send_position(self, lat: float, lon: float, heading: float, eta_min: int, remaining_mi: float) -> None:
        self._send({
            "type": "position", "lat": lat, "lon": lon, "heading": heading,
            "eta_min": eta_min, "remaining_mi": remaining_mi,
        })

    def send_arrived(self) -> None:
        self._send({"type": "arrived"})

    def send_error(self, message: str) -> None:
        self._send({"type": "error", "message": message})
