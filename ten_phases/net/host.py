"""Hosting: the lobby server and the in-game session.

The host's game is the only real copy of the game. Guests send moves; the host
checks them with the rules engine and sends everyone their own view back.
"""

from __future__ import annotations

import queue
import random
import socket
import threading

from .. import __version__
from ..ai import AIPlayer
from ..game import Game, Player, RuleError
from ..names import AI_NAMES
from .discovery import Beacon
from .protocol import GAME_PORT, MAX_PLAYERS, VERSION, Connection, NetError, clean_name, drain, encode_invite, \
    local_ips, new_room_key
from .bj_net import start_blackjack
from .fish_net import start_fish
from .snapshot import events_for, snapshot_for, unrotate

GAMES = ("10 PHASES", "GO FISH", "BLACKJACK")



class HostServer:
    def __init__(self, name: str, port: int = GAME_PORT, announce: bool = True, game: str = "10 PHASES"):
        self.name = clean_name(name, "HOST")
        self.game = game if game in GAMES else GAMES[0]   # which card game this lobby plays
        self.key = new_room_key()
        self.inbox: queue.Queue = queue.Queue()
        self.guests: list[Connection] = []      # joined, in seat order
        self.ai_count = 0
        self.ai_level = "Medium"
        self.in_game = False
        self.session = None   # HostSession (10 Phases) or HostFishSession (Go Fish) while playing
        self.notices: list[str] = []
        # Shuffled once per lobby so the computer names stay put while you set things up.
        self._ai_pool = random.sample(AI_NAMES, len(AI_NAMES))
        self.ips = local_ips()
        self.ip_index = 0
        self.custom_ip: str | None = None
        self.listener = self._listen(port)
        self.port = self.listener.getsockname()[1]
        self.running = True
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()
        self.beacon = Beacon(self._beacon_info) if announce else None

    # ---------------------------------------------------------------- sockets

    def _listen(self, port: int) -> socket.socket:
        last = None
        for p in [port + k for k in range(10)] + [0]:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.bind(("0.0.0.0", p))
                s.listen(8)
                return s
            except OSError as e:
                last = e
                s.close()
        raise NetError(f"Couldn't open a port to host on ({last}).")

    def _accept_loop(self):
        while self.running:
            try:
                sock, _ = self.listener.accept()
            except OSError:
                break
            Connection(sock, self.inbox)  # joins self.guests only after a valid hello

    def _beacon_info(self):
        if self.in_game or not self.running or self.seats_free() <= 0:
            return None
        return {"name": self.name, "game": self.game, "app": __version__, "ip": self.address, "port": self.port, "key": self.key,
                "players": 1 + len(self.guests), "max": MAX_PLAYERS}

    # ---------------------------------------------------------------- invite

    @property
    def address(self) -> str:
        return self.custom_ip or self.ips[self.ip_index % len(self.ips)]

    def next_address(self):
        self.custom_ip = None
        self.ip_index = (self.ip_index + 1) % len(self.ips)

    @property
    def invite_code(self) -> str:
        return encode_invite(self.address, self.port, self.key)

    # ---------------------------------------------------------------- lobby

    def seats_free(self) -> int:
        return MAX_PLAYERS - 1 - len(self.guests) - self.ai_count

    def set_ai_count(self, n: int):
        self.ai_count = max(0, min(n, MAX_PLAYERS - 1 - len(self.guests)))
        self.broadcast_lobby()

    def set_game(self, game: str):
        if game in GAMES and not self.in_game:
            self.game = game
            self.broadcast_lobby()

    def set_ai_level(self, level: str):
        self.ai_level = level
        self.broadcast_lobby()

    def members(self) -> list[dict]:
        out = [{"name": self.name, "kind": "host"}]
        out += [{"name": g.tag, "kind": "guest"} for g in self.guests]
        out += [{"name": name, "kind": "ai", "difficulty": self._ai_level(k)} for k, name in enumerate(self._ai_names())]
        return out

    def _ai_names(self) -> list[str]:
        """Computer names that don't clash with anyone at the table."""
        taken = {self.name} | {g.tag for g in self.guests}
        return [n for n in self._ai_pool if n not in taken][:self.ai_count]

    def _ai_level(self, k: int) -> str:
        if self.ai_level != "Mixed":
            return self.ai_level
        return ["Easy", "Medium", "Hard", "Expert"][k % 4]

    def broadcast_lobby(self):
        members = self.members()
        for i, g in enumerate(self.guests):
            g.send({"t": "lobby", "players": members, "you": i + 1, "game": self.game})

    def kick(self, conn: Connection, reason: str = "The host removed you from the lobby."):
        conn.send({"t": "kicked", "reason": reason})
        self._drop(conn)

    def _drop(self, conn: Connection):
        if conn in self.guests:
            self.guests.remove(conn)
            self.ai_count = min(self.ai_count, MAX_PLAYERS - 1 - len(self.guests))
            if self.session:
                self.session.player_left(conn)
            else:
                self.notices.append(f"{conn.tag} left")
                self.broadcast_lobby()
        conn.close()

    # ---------------------------------------------------------------- messages

    def pump(self):
        for conn, msg in drain(self.inbox):
            t = msg["t"]
            if t == "_closed":
                self._drop(conn)
            elif t == "hello":
                self._hello(conn, msg)
            elif t == "leave":
                self._drop(conn)
            elif t == "act" and self.session and conn in self.guests:
                self.session.handle_action(conn, msg)
        if self.session:
            self.session.flush()

    def _hello(self, conn: Connection, msg: dict):
        def reject(reason):
            conn.send({"t": "reject", "reason": reason})
            conn.close()
        if msg.get("v") != VERSION:
            theirs = f"v{msg['app']}" if isinstance(msg.get("app"), str) else "an older version"
            return reject(f"Version mismatch: the host has v{__version__}, you have {theirs}. "
                          "Both players need the latest version.")
        if msg.get("key") != self.key:
            return reject("That invite code is out of date. Ask the host for a new one.")
        if self.in_game:
            return reject("That game has already started.")
        if conn in self.guests:
            return
        if len(self.guests) >= MAX_PLAYERS - 1:
            return reject("That game is full.")
        if self.seats_free() <= 0:
            self.ai_count -= 1  # a real person beats a computer seat
        name = clean_name(msg.get("name", ""), "GUEST")
        taken = {self.name} | {g.tag for g in self.guests}
        base, k = name, 2
        while name in taken:
            name = f"{base[:8]}{k}"
            k += 1
        conn.tag = name
        self.guests.append(conn)
        conn.send({"t": "welcome", "name": name, "host": self.name})
        self.notices.append(f"{name} joined")
        self.broadcast_lobby()

    # ---------------------------------------------------------------- game

    def start_game(self, ai_speed_delay: float = 0.0):
        if 1 + len(self.guests) + self.ai_count < 2:
            raise NetError("You need at least one other player or computer.")
        self.in_game = True
        if self.game in ("GO FISH", "BLACKJACK"):
            names = self._ai_names()
            starter = start_fish if self.game == "GO FISH" else start_blackjack
            self.session = starter(self, names, [self._ai_level(k) for k in range(len(names))])
            for g in self.guests:
                g.send({"t": "start", "game": self.game})
            self.session.flush(force=True)
            return self.session
        players = [Player(self.name, is_human=True)]
        players += [Player(g.tag, is_human=True) for g in self.guests]
        ais = {}
        for k, name in enumerate(self._ai_names()):
            level = self._ai_level(k)
            players.append(Player(name, difficulty=level))
            ais[len(players) - 1] = AIPlayer(level)
        game = Game(players, random.Random())
        self.session = HostSession(self, game, ais)
        for g in self.guests:
            g.send({"t": "start", "game": self.game})
        self.session.flush(force=True)
        return self.session

    def back_to_lobby(self):
        self._ai_pool = random.sample(AI_NAMES, len(AI_NAMES))  # new computer opponents for the rematch
        self.in_game = False
        self.session = None
        for g in self.guests:
            g.send({"t": "to_lobby"})
        self.broadcast_lobby()

    def close(self):
        self.running = False
        if self.beacon:
            self.beacon.stop()
        for g in list(self.guests):
            g.send({"t": "closed", "reason": "The host closed the game."})
            g.close()
        self.guests.clear()
        try:
            self.listener.close()
        except OSError:
            pass


class HostSession:
    """A running networked game, seen from the host."""

    def __init__(self, server: HostServer, game: Game, ais: dict[int, AIPlayer]):
        self.server = server
        self.game = game
        self.ais = ais
        self.seat_of: dict[Connection, int] = {g: i + 1 for i, g in enumerate(server.guests)}
        self.sent = 0
        self.notices: list[str] = []

    def handle_action(self, conn: Connection, msg: dict):
        seat = self.seat_of.get(conn)
        if seat is None:
            return
        g = self.game
        n = len(g.players)
        hand = {c.id: c for c in g.players[seat].hand}
        try:
            a = msg.get("a")
            if a == "draw":
                (g.draw_from_discard if msg.get("src") == "discard" else g.draw_from_deck)(seat)
            elif a == "lay":
                ids = msg.get("cards") or []
                if not all(isinstance(i, int) and i in hand for i in ids):
                    raise RuleError("Those cards aren't in your hand.")
                g.lay_down_auto(seat, [hand[i] for i in ids])
            elif a == "hit":
                card = hand.get(msg.get("card"))
                if card is None:
                    raise RuleError("That card isn't in your hand.")
                g.hit(seat, card, msg.get("meld"))
            elif a == "discard":
                card = hand.get(msg.get("card"))
                if card is None:
                    raise RuleError("That card isn't in your hand.")
                target = msg.get("target")
                target = unrotate(target, seat, n) if isinstance(target, int) else None
                g.discard(seat, card, target)
            else:
                raise RuleError("Unknown move.")
        except RuleError as e:
            conn.send({"t": "error", "msg": str(e)})
            self.flush(force=True, only=conn)

    def player_left(self, conn: Connection):
        seat = self.seat_of.pop(conn, None)
        if seat is None:
            return
        p = self.game.players[seat]
        p.is_human = False
        p.difficulty = "Medium"
        self.ais[seat] = AIPlayer("Medium")
        msg = f"{p.name} left. A computer took their seat."
        self.notices.append(msg)
        for g in self.seat_of:
            g.send({"t": "notice", "msg": msg})
        self.flush(force=True)

    def flush(self, force: bool = False, only: Connection | None = None):
        """Send everyone the latest state and any new events."""
        history = self.game.history
        if len(history) == self.sent and not force:
            return
        new = history[self.sent:]
        if only is None:
            self.sent = len(history)
        n = len(self.game.players)
        for conn, seat in self.seat_of.items():
            if only is not None and conn is not only:
                continue
            events = [] if only is not None else events_for(new, seat, n)
            conn.send({"t": "state", "s": snapshot_for(self.game, seat), "e": events})
