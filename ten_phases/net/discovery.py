"""Finding games on the same network.

A hosting game broadcasts a small UDP beacon every second; the Join screen
listens for them and lists what it hears.
"""

from __future__ import annotations

import json
import socket
import threading
import time

from .protocol import DISCOVERY_PORT, VERSION

BEACON_EVERY = 1.0
FORGET_AFTER = 4.0


class Beacon:
    """Runs on the host while the lobby is open."""

    def __init__(self, info_fn):
        self.info_fn = info_fn  # returns the dict to announce, or None to stay quiet
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except OSError:
            return
        while self.running:
            info = self.info_fn()
            if info is not None:
                data = json.dumps({"g": "10phases", "v": VERSION, **info}).encode()
                for addr in ("255.255.255.255", "127.0.0.1"):
                    try:
                        sock.sendto(data, (addr, DISCOVERY_PORT))
                    except OSError:
                        pass
            time.sleep(BEACON_EVERY)
        sock.close()

    def stop(self):
        self.running = False


class Browser:
    """Runs on the Join screen; collects beacons from nearby hosts."""

    def __init__(self):
        self.games: dict[tuple[str, int], dict] = {}
        self.running = True
        self.error: str | None = None
        self._lock = threading.Lock()
        self._sock = None
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except OSError:
                    pass
            sock.bind(("", DISCOVERY_PORT))
            sock.settimeout(0.5)
        except OSError:
            self.error = "Can't listen for nearby games on this network."
            return
        self._sock = sock
        while self.running:
            try:
                data, (ip, _) = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                info = json.loads(data.decode())
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(info, dict) or info.get("g") != "10phases" or info.get("v") != VERSION:
                continue
            port = info.get("port")
            # Anyone on the network can send these, so only trust well-formed ones.
            if not (isinstance(port, int) and isinstance(info.get("key"), int)
                    and isinstance(info.get("players", 0), int) and isinstance(info.get("max", 0), int)
                    and isinstance(info.get("name", ""), str) and isinstance(info.get("ip", ""), (str, type(None)))):
                continue
            with self._lock:
                key = (info.get("ip") or ip, port)
                # Prefer a real LAN address over loopback for the same game.
                if ip == "127.0.0.1" and any(k[1] == port and k[0] != "127.0.0.1" for k in self.games):
                    continue
                self.games[key] = {**info, "ip": key[0], "seen": time.monotonic()}
        sock.close()

    def list(self) -> list[dict]:
        now = time.monotonic()
        with self._lock:
            self.games = {k: v for k, v in self.games.items() if now - v["seen"] < FORGET_AFTER}
            return sorted(self.games.values(), key=lambda g: g.get("name", ""))

    def stop(self):
        self.running = False
