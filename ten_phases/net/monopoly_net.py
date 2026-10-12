"""Monopoly over the network. Nothing is secret in Monopoly, so every guest gets the
whole table (seats rotated so they're seat 0), plus the events to animate."""

from __future__ import annotations

import random

from ..monopoly.ai import MonopolyAI
from ..monopoly.engine import MEvent, MonopolyGame, MonopolyRules, MPlayer, RuleError
from ..profile import clean_profile, player_profile
from ..skins import clean_skin, player_skin
from .protocol import Connection
from .snapshot import rotate, unrotate

GAME_NAME = "MONOPOLY"
PLAYER_KEYS = ("to", "owner", "creditor", "from", "bidder")


def _rot_dict(d: dict | None, viewer: int, n: int) -> dict | None:
    if d is None:
        return None
    out = dict(d)
    for key in PLAYER_KEYS + ("debtor",):
        if key in out and isinstance(out[key], int):
            out[key] = rotate(out[key], viewer, n)
    if "active" in out:
        out["active"] = [rotate(k, viewer, n) for k in out["active"]]
    if "cash" in out and isinstance(out["cash"], dict):
        out["cash"] = {str(rotate(int(k), viewer, n)): v for k, v in out["cash"].items()}
    return out


def mono_snapshot_for(game: MonopolyGame, viewer: int) -> dict:
    n = len(game.players)
    order = [(viewer + k) % n for k in range(n)]
    card = game.last_card
    return {
        "round": game.round, "max_rounds": game.max_rounds, "phase": game.phase,
        "current": rotate(game.current, viewer, n), "game_over": game.game_over,
        "winner": rotate(game.winner, viewer, n), "last_roll": list(game.last_roll), "doubles": game.doubles,
        "roll_again": game.roll_again,
        "owner": [rotate(o, viewer, n) for o in game.owner], "houses": list(game.houses),
        "mortgaged": list(game.mortgaged),
        "debt": _rot_dict(game.debt, viewer, n), "auction": _rot_dict(game.auction, viewer, n),
        "trade": _rot_dict(game.trade, viewer, n),
        "card": {"text": card.text, "deck": card.deck} if card else None,
        "players": [{
            "name": game.players[r].name, "human": game.players[r].is_human,
            "difficulty": game.players[r].difficulty, "token": game.players[r].token, "cash": game.players[r].cash,
            "pos": game.players[r].pos, "in_jail": game.players[r].in_jail, "jail_turns": game.players[r].jail_turns,
            "goojf": list(game.players[r].goojf), "bankrupt": game.players[r].bankrupt,
            "skin": list(player_skin(game.players[r])), "prof": player_profile(game.players[r]),
        } for r in order],
    }


def mono_events_for(events: list[MEvent], viewer: int, n: int) -> list[dict]:
    return [{"k": e.kind, "p": rotate(e.player, viewer, n), "sq": e.sq, "a": e.amount, "x": e.text,
             "d": _rot_dict(e.data, viewer, n)} for e in events]


class RemoteMonopolyGame(MonopolyRules):
    """Looks like a MonopolyGame to the table screen; moves are sent to the host."""

    def __init__(self, send):
        self._send = send
        self.events: list[MEvent] = []
        self.history: list[MEvent] = []
        self.pending = False
        self.players: list[MPlayer] = []
        self.owner = [None] * 40
        self.houses = [0] * 40
        self.mortgaged = [False] * 40
        self.round, self.max_rounds, self.phase = 1, 40, "pre_roll"
        self.current, self.game_over, self.winner = 0, False, None
        self.last_roll, self.doubles, self.roll_again = (0, 0), 0, False
        self.debt = self.auction = self.trade = None
        self.card = None

    def apply(self, snap: dict, events: list[dict]) -> None:
        self.round, self.max_rounds, self.phase = snap["round"], snap["max_rounds"], snap["phase"]
        self.current, self.game_over, self.winner = snap["current"], snap["game_over"], snap["winner"]
        self.last_roll, self.doubles, self.roll_again = tuple(snap["last_roll"]), snap["doubles"], snap["roll_again"]
        self.owner, self.houses, self.mortgaged = list(snap["owner"]), list(snap["houses"]), list(snap["mortgaged"])
        self.debt, self.auction, self.trade = snap["debt"], snap["auction"], snap["trade"]
        self.card = snap["card"]
        players = []
        for d in snap["players"]:
            p = MPlayer(d["name"], is_human=d["human"], difficulty=d["difficulty"], token=d["token"], cash=d["cash"],
                        pos=d["pos"], in_jail=d["in_jail"], jail_turns=d["jail_turns"], goojf=list(d["goojf"]),
                        bankrupt=d["bankrupt"])
            p.skin = clean_skin(d.get("skin"))
            p.profile = clean_profile(d.get("prof"))
            players.append(p)
        self.players = players
        for e in events:
            ev = MEvent(e["k"], e.get("p"), e.get("sq"), e.get("a", 0), e.get("x", ""), e.get("d") or {})
            self.events.append(ev)
            self.history.append(ev)
        del self.history[:-300]
        self.pending = False

    def pop_events(self) -> list[MEvent]:
        ev, self.events = self.events, []
        return ev

    def legal(self, i: int) -> list[str]:
        return [] if self.pending else super().legal(i)

    def act(self, i: int, action: str, **kw) -> None:
        if self.pending:
            raise RuleError("Waiting for the host…")
        checks = {"build": self.why_not_build, "sell": self.why_not_sell, "mortgage": self.why_not_mortgage,
                  "unmortgage": self.why_not_unmortgage}
        if action in checks:
            why = checks[action](0, kw.get("sq", -1)) if isinstance(kw.get("sq"), int) else "Pick a property."
            if why:
                raise RuleError(why)
        elif action not in self.legal(0):
            raise RuleError("You can't do that right now.")
        self.pending = True
        self._send({"t": "act", "a": action, **kw})


class HostMonopolySession:
    """A running networked game, seen from the host (same shape as HostSession)."""

    game_name = GAME_NAME

    def __init__(self, server, game: MonopolyGame, ais: dict[int, MonopolyAI]):
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
            a = msg.get("a")
            if not isinstance(a, str):
                raise RuleError("Unknown move.")
            kw = {k: msg[k] for k in ("sq", "amount", "give", "get", "give_cash", "get_cash") if k in msg}
            if "to" in msg:
                if not isinstance(msg["to"], int) or isinstance(msg["to"], bool):
                    raise RuleError("Pick someone to trade with.")
                kw["to"] = unrotate(msg["to"], seat, n)
            self.game.act(seat, a, **kw)
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
        self.ais[seat] = MonopolyAI("Medium")
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
            events = [] if only is not None else mono_events_for(new, seat, n)
            conn.send({"t": "state", "s": mono_snapshot_for(self.game, seat), "e": events})


def start_monopoly(server, ai_names: list[str], levels: list[str], max_rounds: int = 40) -> HostMonopolySession:
    """Build the table for a lobby: host, then guests, then computers."""
    players = [MPlayer(server.name, is_human=True, token=getattr(server, "token", ""))]
    players += [MPlayer(g.tag, is_human=True, token=getattr(g, "token", "")) for g in server.guests]
    ais = {}
    for name, level in zip(ai_names, levels):
        players.append(MPlayer(name, difficulty=level))
        ais[len(players) - 1] = MonopolyAI(level)
    return HostMonopolySession(server, MonopolyGame(players, random.Random(), max_rounds=max_rounds), ais)
