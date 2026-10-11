"""Wire format, connections and invite codes.

Messages are JSON objects, one per line, over TCP. Every socket has a reader
thread that puts messages on a queue; the game loop drains the queue on the
main thread, so the game engine is only ever touched from one thread.
"""

from __future__ import annotations

import json
import queue
import secrets
import socket
import threading

VERSION = 1
GAME_PORT = 47610
DISCOVERY_PORT = 47611
MAX_LINE = 256 * 1024
MAX_PLAYERS = 6

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no I, O, 0 or 1


class NetError(Exception):
    """A connection problem with a message fit to show the player."""


# --------------------------------------------------------------------------- invite codes


def new_room_key() -> int:
    return secrets.randbits(24)


def encode_invite(ip: str, port: int, key: int) -> str:
    """Pack an IPv4 address, port and 24-bit room key into a 15-letter code."""
    parts = [int(p) for p in ip.split(".")]
    if len(parts) != 4 or not all(0 <= p <= 255 for p in parts):
        raise ValueError(f"not an IPv4 address: {ip}")
    n = 0
    for b in parts + [port >> 8, port & 0xFF, key >> 16, (key >> 8) & 0xFF, key & 0xFF]:
        n = (n << 8) | b
    chars = []
    for _ in range(15):
        n, r = divmod(n, 32)
        chars.append(CODE_ALPHABET[r])
    code = "".join(reversed(chars))
    return f"{code[:5]}-{code[5:10]}-{code[10:]}"


def decode_invite(code: str) -> tuple[str, int, int]:
    """Inverse of encode_invite. Forgiving about case, spaces and dashes."""
    clean = "".join(ch for ch in code.upper() if ch.isalnum())
    clean = clean.replace("0", "O").replace("1", "I")
    if len(clean) != 15 or any(ch not in CODE_ALPHABET for ch in clean):
        raise NetError("That invite code doesn't look right. It should be 15 letters and numbers.")
    n = 0
    for ch in clean:
        n = n * 32 + CODE_ALPHABET.index(ch)
    data = n.to_bytes(10, "big")
    if data[0] != 0:
        raise NetError("That invite code doesn't look right.")
    data = data[1:]
    ip = ".".join(str(b) for b in data[:4])
    port = (data[4] << 8) | data[5]
    key = (data[6] << 16) | (data[7] << 8) | data[8]
    return ip, port, key


def local_ips() -> list[str]:
    """This machine's IPv4 addresses, best guess for the LAN first."""
    found: list[str] = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))  # no packet is sent; this just picks a route
            found.append(s.getsockname()[0])
        finally:
            s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in found:
                found.append(ip)
    except OSError:
        pass
    found = [ip for ip in found if not ip.startswith("127.")] or found
    return found or ["127.0.0.1"]


# --------------------------------------------------------------------------- connections


class Connection:
    """A JSON-lines TCP connection with a background reader."""

    def __init__(self, sock: socket.socket, inbox: queue.Queue | None = None, tag=None):
        self.sock = sock
        self.tag = tag
        self.inbox = inbox if inbox is not None else queue.Queue()
        self.alive = True
        self._send_lock = threading.Lock()
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        sock.settimeout(None)
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    @classmethod
    def connect(cls, ip: str, port: int, timeout: float = 6.0, inbox: queue.Queue | None = None) -> "Connection":
        try:
            sock = socket.create_connection((ip, port), timeout=timeout)
        except socket.timeout:
            raise NetError(f"No answer from {ip}:{port}. Is the host's game open and reachable?") from None
        except ConnectionRefusedError:
            raise NetError(f"{ip}:{port} refused the connection. The host may have closed the lobby.") from None
        except OSError as e:
            raise NetError(f"Couldn't reach {ip}:{port} ({e.strerror or e}).") from None
        return cls(sock, inbox)

    def _read_loop(self):
        buf = b""
        try:
            while self.alive:
                chunk = self.sock.recv(65536)
                if not chunk:
                    break
                buf += chunk
                if len(buf) > MAX_LINE and b"\n" not in buf:
                    break  # garbage or abuse; drop the connection
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except (ValueError, UnicodeDecodeError):
                        continue
                    if isinstance(msg, dict) and isinstance(msg.get("t"), str):
                        self.inbox.put((self, msg))
        except OSError:
            pass
        self.alive = False
        self.inbox.put((self, {"t": "_closed"}))

    def send(self, msg: dict) -> bool:
        if not self.alive:
            return False
        data = (json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8")
        try:
            with self._send_lock:
                self.sock.sendall(data)
            return True
        except OSError:
            self.close()
            return False

    def close(self):
        if self.alive:
            self.alive = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


def drain(inbox: queue.Queue, limit: int = 200):
    """Yield queued (connection, message) pairs without blocking."""
    for _ in range(limit):
        try:
            yield inbox.get_nowait()
        except queue.Empty:
            return


def clean_name(name: str, fallback: str = "PLAYER") -> str:
    name = "".join(ch for ch in str(name).upper() if ch.isalnum() or ch in " -_")[:10].strip()
    return name or fallback
