"""Poker over the network: per-player views, the guest's mirror, and the host session.

Everyone's two hole cards are secret until a showdown, so each guest only ever
receives their own (and the ones turned face up at a showdown).
"""

from __future__ import annotations

import random

from ..cards import Kind
from ..poker.ai import PokerAI
from ..poker.engine import PokerCard, PokerEvent, PokerGame, PokerPlayer, PokerRules, RuleError
from ..skins import clean_skin, player_skin
from .protocol import Connection
from .snapshot import _COLOR_BACK, _KIND_BACK, card_out, rotate

GAME_NAME = "POKER"


def _visible(game: PokerGame, seat: int, viewer: int) -> bool:
    return seat == viewer or seat in game.revealed


def poker_snapshot_for(game: PokerGame, viewer: int) -> dict:
    n = len(game.players)
    order = [(viewer + k) % n for k in range(n)]
    return {
        "round": game.round, "hands": game.hands_per_game, "phase": game.phase, "street": game.street,
        "game_over": game.game_over, "blinds": list(game.blinds), "button": rotate(game.button, viewer, n),
        "sb": rotate(game.sb_seat, viewer, n), "bb": rotate(game.bb_seat, viewer, n),
        "current": rotate(game.current, viewer, n), "current_bet": game.current_bet, "min_raise": game.min_raise,
        "board": [card_out(c) for c in game.board], "deck": len(game.deck),
        "revealed": [rotate(k, viewer, n) for k in game.revealed],
        "wins": [{"player": rotate(w["player"], viewer, n), "amount": w["amount"], "hand": w["hand"]}
                 for w in game.last_wins],
        "players": [{
            "name": game.players[r].name, "human": game.players[r].is_human,
            "difficulty": game.players[r].difficulty, "chips": game.players[r].chips, "bet": game.players[r].bet,
            "total_in": game.players[r].total_in, "folded": game.players[r].folded,
            "all_in": game.players[r].all_in, "acted": game.players[r].acted, "in_hand": game.players[r].in_hand,
            "net": game.players[r].net, "results": game.players[r].results[-10:],
            "last": game.players[r].last_action, "skin": list(player_skin(game.players[r])),
            "hole": [card_out(c) for c in game.players[r].hole] if _visible(game, r, viewer) else None,
            "count": len(game.players[r].hole),
        } for r in order],
    }


def poker_events_for(events: list[PokerEvent], viewer: int, n: int) -> list[dict]:
    out = []
    for e in events:
        hidden = e.hidden and e.player != viewer
        out.append({"k": e.kind, "p": rotate(e.player, viewer, n), "a": e.amount, "name": e.name,
                    "c": [] if hidden else [card_out(c) for c in e.cards], "n": len(e.cards),
                    "hidden": hidden})
    return out


class _Count:
    def __init__(self, n: int):
        self.n = n

    def __len__(self) -> int:
        return self.n


class RemotePokerGame(PokerRules):
    """Looks like a PokerGame to the table screen; moves are sent to the host."""

    def __init__(self, send):
        self._send = send
        self._cards: dict[int, PokerCard] = {}
        self.events: list[PokerEvent] = []
        self.history: list[PokerEvent] = []
        self.pending = False
        self.players: list[PokerPlayer] = []
        self.board: list[PokerCard] = []
        self.deck = _Count(0)
        self.round, self.hands_per_game = 0, 15
        self.phase, self.street = "playing", "preflop"
        self.game_over = False
        self.blinds = (1, 2)
        self.button = self.sb_seat = self.bb_seat = self.current = None
        self.current_bet, self.min_raise = 0, 2
        self.revealed: set[int] = set()
        self.last_wins: list[dict] = []

    def _card(self, data) -> PokerCard:
        cid, kind, color, value = data
        c = self._cards.get(cid)
        if c is None:
            c = self._cards[cid] = PokerCard(_KIND_BACK[kind], _COLOR_BACK.get(color), value or None, id=cid)
        return c

    def apply(self, snap: dict, events: list[dict]) -> None:
        self.round, self.hands_per_game = snap["round"], snap["hands"]
        self.phase, self.street, self.game_over = snap["phase"], snap["street"], snap["game_over"]
        self.blinds = tuple(snap["blinds"])
        self.button, self.sb_seat, self.bb_seat = snap["button"], snap["sb"], snap["bb"]
        self.current, self.current_bet, self.min_raise = snap["current"], snap["current_bet"], snap["min_raise"]
        self.board = [self._card(c) for c in snap["board"]]
        self.deck = _Count(snap["deck"])
        self.revealed = set(snap["revealed"])
        self.last_wins = list(snap["wins"])
        players = []
        for d in snap["players"]:
            p = PokerPlayer(d["name"], is_human=d["human"], difficulty=d["difficulty"], chips=d["chips"])
            p.bet, p.total_in, p.folded, p.all_in = d["bet"], d["total_in"], d["folded"], d["all_in"]
            p.acted, p.in_hand, p.net, p.results = d["acted"], d["in_hand"], d["net"], list(d["results"])
            p.last_action = d["last"]
            p.skin = clean_skin(d.get("skin"))
            p.hole = [self._card(c) for c in d["hole"]] if d["hole"] is not None else \
                [PokerCard(Kind.NUMBER, None, None, id=-1) for _ in range(d["count"])]   # face down
            players.append(p)
        self.players = players
        for e in events:
            cards = [self._card(c) for c in e.get("c", [])]
            if e.get("hidden"):
                cards = [PokerCard(Kind.NUMBER, None, None, id=-2) for _ in range(e.get("n", 2))]
            ev = PokerEvent(e["k"], player=e.get("p"), cards=cards, amount=e.get("a", 0), name=e.get("name", ""),
                            hidden=bool(e.get("hidden")))
            self.events.append(ev)
            self.history.append(ev)
        del self.history[:-400]
        self.pending = False

    # ---------------------------------------------------------------- PokerGame-like helpers

    def pop_events(self) -> list[PokerEvent]:
        ev, self.events = self.events, []
        return ev

    def legal_actions(self, i: int) -> list[str]:
        return [] if self.pending else super().legal_actions(i)

    def act(self, i: int, action: str, amount: int = 0) -> None:
        if self.pending:
            raise RuleError("Waiting for the host…")
        if action not in self.legal_actions(0):
            raise RuleError("You can't do that right now.")
        if action == "raise":
            least, most = self.raise_range(0)
            if not least <= amount <= most:
                raise RuleError(f"Raise to between {least} and {most} chips.")
        self.pending = True
        self._send({"t": "act", "a": action, "amount": amount})

    def next_round(self):
        raise RuleError("The host deals the next hand.")


class HostPokerSession:
    """A running networked poker table, seen from the host (same shape as HostSession)."""

    game_name = GAME_NAME

    def __init__(self, server, game: PokerGame, ais: dict[int, PokerAI]):
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
        try:
            a, amount = msg.get("a"), msg.get("amount", 0)
            if a not in ("fold", "check", "call", "raise") or not isinstance(amount, int) or isinstance(amount, bool):
                raise RuleError("Unknown move.")
            self.game.act(seat, a, amount)
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
        self.ais[seat] = PokerAI("Medium")
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
            events = [] if only is not None else poker_events_for(new, seat, n)
            conn.send({"t": "state", "s": poker_snapshot_for(self.game, seat), "e": events})


def start_poker(server, ai_names: list[str], levels: list[str]) -> HostPokerSession:
    """Build the poker table for a lobby: host, then guests, then computers."""
    players = [PokerPlayer(server.name, is_human=True)]
    players += [PokerPlayer(g.tag, is_human=True) for g in server.guests]
    ais = {}
    for name, level in zip(ai_names, levels):
        players.append(PokerPlayer(name, difficulty=level))
        ais[len(players) - 1] = PokerAI(level)
    return HostPokerSession(server, PokerGame(players, random.Random()), ais)
