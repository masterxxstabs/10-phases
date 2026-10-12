"""Go Fish over the network: per-player views, the guest's mirror, and the host session.

As with 10 Phases, the host's game is the real one. Each guest only receives
their own hand; a card someone fishes from the pond stays hidden unless it was
the number they asked for (then everyone sees it, as in the real game).
"""

from __future__ import annotations

from ..cards import Card, Kind
from ..gofish.ai import GoFishAI
from ..gofish.engine import FishEvent, FishPlayer, GoFishGame, RuleError
from .protocol import Connection
from .snapshot import _KIND_BACK, _COLOR_BACK, card_out, rotate, unrotate

GAME_NAME = "GO FISH"


def fish_snapshot_for(game: GoFishGame, viewer: int) -> dict:
    n = len(game.players)
    order = [(viewer + k) % n for k in range(n)]
    return {
        "current": rotate(game.current, viewer, n), "game_over": game.game_over, "pond": len(game.pond),
        "players": [{
            "name": game.players[r].name, "human": game.players[r].is_human,
            "difficulty": game.players[r].difficulty, "books": list(game.players[r].books),
            "count": len(game.players[r].hand),
            "hand": [card_out(c) for c in game.players[r].hand] if r == viewer else None,
        } for r in order],
    }


def fish_events_for(events: list[FishEvent], viewer: int, n: int) -> list[dict]:
    out = []
    for ev in events:
        cards = ev.cards
        if ev.kind == "draw" and ev.player != viewer and not ev.lucky:
            cards = []  # nobody else sees what you fished
        out.append({"k": ev.kind, "p": rotate(ev.player, viewer, n), "t": rotate(ev.target, viewer, n),
                    "v": ev.value, "c": [card_out(c) for c in cards], "l": ev.lucky,
                    "hidden": ev.kind == "draw" and ev.player != viewer and not ev.lucky})
    return out


class _Pond:
    def __init__(self, n: int):
        self.n = n

    def __len__(self) -> int:
        return self.n


class RemoteFishGame:
    """Looks like a GoFishGame to the table screen; asks are sent to the host."""

    def __init__(self, send):
        self._send = send
        self._cards: dict[int, Card] = {}
        self.events: list[FishEvent] = []
        self.history: list[FishEvent] = []   # the hint AI reads this, just like on the host
        self.pending = False
        self.players: list[FishPlayer] = []
        self.pond = _Pond(0)
        self.current = 0
        self.game_over = False

    def _card(self, data) -> Card:
        cid, kind, color, value = data
        c = self._cards.get(cid)
        if c is None:
            c = self._cards[cid] = Card(_KIND_BACK[kind], _COLOR_BACK.get(color), value or None, id=cid)
        return c

    def apply(self, snap: dict, events: list[dict]) -> None:
        self.current = snap["current"]
        self.game_over = snap["game_over"]
        self.pond = _Pond(snap["pond"])
        players = []
        for d in snap["players"]:
            p = FishPlayer(d["name"], is_human=d["human"], difficulty=d["difficulty"])
            p.books = list(d["books"])
            p.hand = [self._card(c) for c in d["hand"]] if d["hand"] is not None else \
                [Card(Kind.SKIP, id=-1) for _ in range(d["count"])]
            players.append(p)
        self.players = players
        for e in events:
            cards = [self._card(c) for c in e.get("c", [])]
            if e.get("hidden"):
                cards = [Card(Kind.SKIP, id=-2)]  # a face-down card flies to them
            ev = FishEvent(e["k"], player=e.get("p"), target=e.get("t"), value=e.get("v"), cards=cards,
                           lucky=bool(e.get("l")))
            self.events.append(ev)
            self.history.append(ev)
        self.pending = False

    # ---------------------------------------------------------------- GoFishGame-like helpers

    @property
    def player(self) -> FishPlayer:
        return self.players[self.current]

    def pop_events(self) -> list[FishEvent]:
        ev, self.events = self.events, []
        return ev

    def books_made(self) -> int:
        return sum(len(p.books) for p in self.players)

    def can_be_asked(self, i: int) -> list[int]:
        return [j for j, p in enumerate(self.players) if j != i and p.hand]

    def standings(self) -> list[int]:
        return sorted(range(len(self.players)), key=lambda i: -len(self.players[i].books))

    def winners(self) -> list[int]:
        best = max(len(p.books) for p in self.players)
        return [i for i, p in enumerate(self.players) if len(p.books) == best]

    def ask(self, asker: int, target: int, value: int) -> None:
        if self.pending:
            raise RuleError("Waiting for the host…")
        if self.game_over or self.current != 0:
            raise RuleError("It's not your turn.")
        if not self.players[0].count(value):
            raise RuleError("You can only ask for a number you have.")
        if not 0 < target < len(self.players) or not self.players[target].hand:
            raise RuleError("Ask a player who still has cards.")
        self.pending = True
        self._send({"t": "act", "a": "ask", "target": target, "value": value})


class HostFishSession:
    """A running networked Go Fish game, seen from the host (same shape as HostSession)."""

    game_name = GAME_NAME

    def __init__(self, server, game: GoFishGame, ais: dict[int, GoFishAI]):
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
        n = len(self.game.players)
        try:
            if msg.get("a") != "ask" or not isinstance(msg.get("target"), int) or not isinstance(msg.get("value"), int):
                raise RuleError("Unknown move.")
            self.game.ask(seat, unrotate(msg["target"], seat, n), msg["value"])
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
        self.ais[seat] = GoFishAI("Medium")
        msg = f"{p.name} left. A computer took their seat."
        self.notices.append(msg)
        for g in self.seat_of:
            g.send({"t": "notice", "msg": msg})
        self.flush(force=True)

    def flush(self, force: bool = False, only: Connection | None = None):
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
            events = [] if only is not None else fish_events_for(new, seat, n)
            conn.send({"t": "state", "s": fish_snapshot_for(self.game, seat), "e": events})


def start_fish(server, ai_names: list[str], levels: list[str]) -> HostFishSession:
    """Build the Go Fish table for a lobby: host, then guests, then computers."""
    import random

    players = [FishPlayer(server.name, is_human=True)]
    players += [FishPlayer(g.tag, is_human=True) for g in server.guests]
    ais = {}
    for name, level in zip(ai_names, levels):
        players.append(FishPlayer(name, difficulty=level))
        ais[len(players) - 1] = GoFishAI(level)
    return HostFishSession(server, GoFishGame(players, random.Random()), ais)
