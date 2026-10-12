"""Blackjack over the network: per-player views, the guest's mirror, and the host session.

In blackjack every player's cards are face up, so the only secret is the
dealer's hole card (and the order of the shoe). The host never sends the hole
card until it's turned over.
"""

from __future__ import annotations

import random

from ..blackjack.ai import BlackjackAI
from ..blackjack.engine import MAX_BET, MIN_BET, BJCard, BJEvent, BJPlayer, BlackjackGame, Hand, RuleError
from ..cards import Kind
from .protocol import Connection
from .snapshot import _COLOR_BACK, _KIND_BACK, card_out, rotate

GAME_NAME = "BLACKJACK"


def _hand_out(h: Hand) -> dict:
    return {"cards": [card_out(c) for c in h.cards], "bet": h.bet, "doubled": h.doubled, "split": h.split,
            "stood": h.stood, "result": h.result, "payout": h.payout}


def bj_snapshot_for(game: BlackjackGame, viewer: int) -> dict:
    n = len(game.players)
    order = [(viewer + k) % n for k in range(n)]
    dealer = [card_out(c) for c in game.dealer]
    if game.hole_hidden and len(dealer) > 1:
        dealer[1] = None
    turn = None if game.turn is None else [rotate(game.turn[0], viewer, n), game.turn[1]]
    return {
        "round": game.round, "hands": game.hands_per_game, "phase": game.phase, "game_over": game.game_over,
        "turn": turn, "dealer": dealer, "hole_hidden": game.hole_hidden, "shoe": len(game.shoe),
        "players": [{
            "name": game.players[r].name, "human": game.players[r].is_human, "difficulty": game.players[r].difficulty,
            "chips": game.players[r].chips, "bet": game.players[r].bet, "net": game.players[r].net,
            "results": game.players[r].results[-10:], "hands": [_hand_out(h) for h in game.players[r].hands],
        } for r in order],
    }


def bj_events_for(events: list[BJEvent], viewer: int, n: int) -> list[dict]:
    return [{"k": e.kind, "p": rotate(e.player, viewer, n), "h": e.hand, "c": card_out(e.card) if e.card else None,
             "hidden": e.hidden, "a": e.amount, "r": e.result} for e in events]


class _Count:
    def __init__(self, n: int):
        self.n = n

    def __len__(self) -> int:
        return self.n


class RemoteBlackjackGame:
    """Looks like a BlackjackGame to the table screen; moves are sent to the host."""

    def __init__(self, send):
        self._send = send
        self._cards: dict[int, BJCard] = {}
        self.events: list[BJEvent] = []
        self.history: list[BJEvent] = []
        self.pending = False
        self.players: list[BJPlayer] = []
        self.dealer: list[BJCard] = []
        self.hole_hidden = True
        self.phase = "betting"
        self.turn = None
        self.round = 0
        self.hands_per_game = 10
        self.game_over = False
        self.shoe = _Count(0)
        self.seen: list[BJCard] = []

    def _card(self, data) -> BJCard:
        if data is None:
            return BJCard(Kind.NUMBER, None, 0, id=-3)  # the face-down hole card
        cid, kind, color, value = data
        c = self._cards.get(cid)
        if c is None:
            c = self._cards[cid] = BJCard(_KIND_BACK[kind], _COLOR_BACK.get(color), value or None, id=cid)
        return c

    def apply(self, snap: dict, events: list[dict]) -> None:
        self.round, self.hands_per_game = snap["round"], snap["hands"]
        self.phase, self.game_over = snap["phase"], snap["game_over"]
        self.turn = tuple(snap["turn"]) if snap["turn"] else None
        self.dealer = [self._card(c) for c in snap["dealer"]]
        self.hole_hidden = snap["hole_hidden"]
        self.shoe = _Count(snap["shoe"])
        players = []
        for d in snap["players"]:
            p = BJPlayer(d["name"], is_human=d["human"], difficulty=d["difficulty"], chips=d["chips"])
            p.bet, p.net, p.results = d["bet"], d["net"], list(d["results"])
            p.hands = [Hand(cards=[self._card(c) for c in h["cards"]], bet=h["bet"], doubled=h["doubled"],
                            split=h["split"], stood=h["stood"], result=h["result"], payout=h["payout"])
                       for h in d["hands"]]
            players.append(p)
        self.players = players
        for e in events:
            ev = BJEvent(e["k"], player=e.get("p"), hand=e.get("h", 0), card=self._card(e["c"]) if e.get("c") else None,
                         hidden=bool(e.get("hidden")), amount=e.get("a", 0), result=e.get("r"))
            self.events.append(ev)
            self.history.append(ev)
        self.pending = False

    # ---------------------------------------------------------------- BlackjackGame-like helpers

    @property
    def dealer_up(self):
        return self.dealer[0] if self.dealer else None

    def pop_events(self) -> list[BJEvent]:
        ev, self.events = self.events, []
        return ev

    def max_bet(self, i: int) -> int:
        return max(0, min(MAX_BET, self.players[i].chips))

    def waiting_for_bets(self) -> list[int]:
        return [i for i, p in enumerate(self.players) if self.phase == "betting" and p.bet is None
                and p.chips >= MIN_BET]

    def legal_actions(self, i: int) -> list[str]:
        if self.phase != "playing" or self.turn is None or self.turn[0] != i or self.pending:
            return []
        p = self.players[i]
        hand = p.hands[self.turn[1]]
        acts = ["hit", "stand"]
        if len(hand.cards) == 2 and p.chips >= hand.bet:
            acts.append("double")
            if len(p.hands) == 1 and min(hand.cards[0].value, 10) == min(hand.cards[1].value, 10):
                acts.append("split")
        return acts

    def standings(self) -> list[int]:
        return sorted(range(len(self.players)), key=lambda i: -self.players[i].chips)

    def winners(self) -> list[int]:
        best = max(p.chips for p in self.players)
        return [i for i, p in enumerate(self.players) if p.chips == best]

    def _request(self, msg: dict):
        if self.pending:
            raise RuleError("Waiting for the host…")
        self.pending = True
        self._send({"t": "act", **msg})

    def place_bet(self, i: int, amount: int):
        if self.phase != "betting" or self.players[0].bet is not None:
            raise RuleError("Bets are closed for this hand.")
        if not MIN_BET <= amount <= self.max_bet(0):
            raise RuleError(f"Bet between {MIN_BET} and {self.max_bet(0)} chips.")
        self._request({"a": "bet", "amount": amount})

    def _move(self, action: str):
        if action not in self.legal_actions(0):
            raise RuleError("You can't do that right now.")
        self._request({"a": action})

    def hit(self, i: int):
        self._move("hit")

    def stand(self, i: int):
        self._move("stand")

    def double(self, i: int):
        self._move("double")

    def split(self, i: int):
        self._move("split")

    def next_round(self):
        raise RuleError("The host deals the next hand.")


class HostBlackjackSession:
    """A running networked blackjack table, seen from the host (same shape as HostSession)."""

    game_name = GAME_NAME

    def __init__(self, server, game: BlackjackGame, ais: dict[int, BlackjackAI]):
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
        try:
            a = msg.get("a")
            if a == "bet":
                if not isinstance(msg.get("amount"), int):
                    raise RuleError("Bad bet.")
                g.place_bet(seat, msg["amount"])
            elif a in ("hit", "stand", "double", "split"):
                getattr(g, a)(seat)
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
        self.ais[seat] = BlackjackAI("Medium")
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
            events = [] if only is not None else bj_events_for(new, seat, n)
            conn.send({"t": "state", "s": bj_snapshot_for(self.game, seat), "e": events})


def start_blackjack(server, ai_names: list[str], levels: list[str]) -> HostBlackjackSession:
    players = [BJPlayer(server.name, is_human=True)]
    players += [BJPlayer(g.tag, is_human=True) for g in server.guests]
    ais = {}
    for name, level in zip(ai_names, levels):
        players.append(BJPlayer(name, difficulty=level))
        ais[len(players) - 1] = BlackjackAI(level)
    return HostBlackjackSession(server, BlackjackGame(players, random.Random()), ais)

