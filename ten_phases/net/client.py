"""Joining someone else's game."""

from __future__ import annotations

import queue
import threading

from .. import __version__
from ..profile import clean_profile
from ..skins import clean_skin
from .protocol import VERSION, Connection, NetError, clean_name, decode_invite, drain
from .bj_net import RemoteBlackjackGame
from .cah_net import RemoteCahGame
from .fish_net import RemoteFishGame
from .monopoly_net import RemoteMonopolyGame
from .poker_net import RemotePokerGame
from .snapshot import RemoteGame


class ClientSession:
    """A guest's connection. Connecting runs in the background so the screen never freezes."""

    def __init__(self, name: str, ip: str, port: int, key: int, skin=("classic", "classic"), token: str = "",
                 profile=None):
        self.name = clean_name(name)
        self.skin = list(clean_skin(skin))
        self.token = token   # Monopoly piece we'd like
        self.profile = clean_profile(profile)
        self.ip, self.port, self.key = ip, port, key
        self.inbox: queue.Queue = queue.Queue()
        self.conn: Connection | None = None
        self.status = "connecting"     # connecting, waiting, joined, failed, closed
        self.error: str | None = None
        self.host_name = ""
        self.members: list[dict] = []
        self.my_index = 0
        self.game: RemoteGame | RemoteFishGame | RemoteBlackjackGame | None = None
        self.game_name = "10 PHASES"   # which card game the host picked
        threading.Thread(target=self._connect, daemon=True).start()

    @classmethod
    def from_code(cls, name: str, code: str, skin=("classic", "classic"), token: str = "",
                  profile=None) -> "ClientSession":
        ip, port, key = decode_invite(code)
        return cls(name, ip, port, key, skin, token, profile)

    def _connect(self):
        try:
            conn = Connection.connect(self.ip, self.port, inbox=self.inbox)
        except NetError as e:
            self.error = str(e)
            self.status = "failed"
            return
        self.conn = conn
        self.status = "waiting"
        conn.send({"t": "hello", "v": VERSION, "app": __version__, "key": self.key, "name": self.name,
                   "skin": self.skin, "token": self.token, "prof": self.profile})

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
                self.game_name = msg.get("game", self.game_name)
            elif t == "start":
                self.game_name = msg.get("game", "10 PHASES")
                self.game = {"GO FISH": RemoteFishGame, "BLACKJACK": RemoteBlackjackGame,
                             "POKER": RemotePokerGame, "CAH": RemoteCahGame, "MONOPOLY": RemoteMonopolyGame}.get(
                    self.game_name, RemoteGame)(self.send)
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
            elif t == "img":
                if self.game is not None and hasattr(self.game, "add_image"):
                    self.game.add_image(msg.get("id"), msg.get("data"))
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
