"""Joining someone else's game."""

from __future__ import annotations

import queue
import threading

from .. import __version__
from .protocol import VERSION, Connection, NetError, clean_name, decode_invite, drain
from .snapshot import RemoteGame


class ClientSession:
    """A guest's connection. Connecting runs in the background so the screen never freezes."""

    def __init__(self, name: str, ip: str, port: int, key: int):
        self.name = clean_name(name)
        self.ip, self.port, self.key = ip, port, key
        self.inbox: queue.Queue = queue.Queue()
        self.conn: Connection | None = None
        self.status = "connecting"     # connecting, waiting, joined, failed, closed
        self.error: str | None = None
        self.host_name = ""
        self.members: list[dict] = []
        self.my_index = 0
        self.game: RemoteGame | None = None
        threading.Thread(target=self._connect, daemon=True).start()

    @classmethod
    def from_code(cls, name: str, code: str) -> "ClientSession":
        ip, port, key = decode_invite(code)
        return cls(name, ip, port, key)

    def _connect(self):
        try:
            conn = Connection.connect(self.ip, self.port, inbox=self.inbox)
        except NetError as e:
            self.error = str(e)
            self.status = "failed"
            return
        self.conn = conn
        self.status = "waiting"
        conn.send({"t": "hello", "v": VERSION, "app": __version__, "key": self.key, "name": self.name})

    def send(self, msg: dict):
        if self.conn:
            self.conn.send(msg)

    def poll(self) -> list[dict]:
        """Handle connection-level messages and return the rest for the current screen."""
        out = []
        for _, msg in drain(self.inbox):
            t = msg["t"]
            if t == "welcome":
                self.status = "joined"
                self.name = msg.get("name", self.name)
                self.host_name = msg.get("host", "")
            elif t == "reject":
                self.status = "failed"
                self.error = msg.get("reason", "The host turned you away.")
            elif t in ("kicked", "closed"):
                self.status = "closed"
                self.error = msg.get("reason", "Disconnected.")
            elif t == "_closed":
                if self.status not in ("failed", "closed"):
                    self.status = "closed"
                    self.error = "Lost connection to the host."
            elif t == "lobby":
                self.members = msg.get("players", [])
                self.my_index = msg.get("you", 0)
            elif t == "start":
                self.game = RemoteGame(self.send)
            elif t == "to_lobby":
                self.game = None
            elif t == "state" and self.game is not None:
                try:
                    self.game.apply(msg["s"], msg.get("e", []))
                except (KeyError, TypeError, ValueError, IndexError):
                    self.status = "closed"
                    self.error = "The host sent something this version doesn't understand."
                    self.leave()
                continue
            elif t == "error" and self.game is not None:
                self.game.pending = False
            out.append(msg)
        return out

    def leave(self):
        if self.conn:
            self.conn.send({"t": "leave"})
            self.conn.close()
        if self.status not in ("failed", "closed"):
            self.status = "closed"
