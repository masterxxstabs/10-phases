"""What each player is allowed to see, and a client-side mirror of the game.

The host sends every guest a snapshot built just for them: only their own hand
is included (opponents' hands are just counts). Seats are rotated so the
viewer is always seat 0, which is how the table is drawn locally.
"""

from __future__ import annotations

from ..cards import Card, Color, Kind
from ..game import Event, Meld, Player, RuleError
from ..phases import GroupType, PHASES, partition_for_phase

_KIND = {Kind.NUMBER: "n", Kind.WILD: "w", Kind.SKIP: "s"}
_KIND_BACK = {v: k for k, v in _KIND.items()}
_COLOR = {Color.RED: "r", Color.BLUE: "b", Color.GREEN: "g", Color.YELLOW: "y"}
_COLOR_BACK = {v: k for k, v in _COLOR.items()}


def card_out(c: Card) -> list:
    return [c.id, _KIND[c.kind], _COLOR.get(c.color, ""), c.value or 0]


def rotate(seat: int | None, viewer: int, n: int) -> int | None:
    return None if seat is None else (seat - viewer) % n


def unrotate(seat: int | None, viewer: int, n: int) -> int | None:
    return None if seat is None else (seat + viewer) % n


def snapshot_for(game, viewer: int) -> dict:
    n = len(game.players)
    order = [(viewer + k) % n for k in range(n)]
    players = []
    for real in order:
        p = game.players[real]
        players.append({
            "name": p.name, "human": p.is_human, "difficulty": p.difficulty, "phase": p.phase, "score": p.score,
            "chips": p.chips, "laid": p.laid_down, "skips": p.skips_pending, "done": p.completed_this_round,
            "count": len(p.hand), "hand": [card_out(c) for c in p.hand] if real == viewer else None,
        })
    return {
        "round": game.round, "current": rotate(game.current, viewer, n), "drawn": game.has_drawn,
        "round_over": game.round_over, "game_over": game.game_over,
        "winner": rotate(game.winner, viewer, n), "went_out": rotate(getattr(game, "went_out", None), viewer, n),
        "pot": game.pot, "deck": len(game.deck), "discard": [card_out(c) for c in game.discard_pile],
        "players": players,
        "melds": [{"id": m.id, "owner": rotate(m.owner, viewer, n), "type": m.type.value, "min": m.min_size,
                   "cards": [card_out(c) for c in m.cards]} for m in game.melds],
        "picked": {str(rotate(i, viewer, n)): [card_out(c) for c in cards]
                   for i, cards in game.picked_from_discard.items()},
        "points": {str(rotate(i, viewer, n)): v for i, v in game.round_points.items()},
        "chip_delta": {str(rotate(i, viewer, n)): v for i, v in game.round_chips.items()},
    }


def events_for(events, viewer: int, n: int) -> list[dict]:
    out = []
    for ev in events:
        card = ev.card
        if ev.kind == "draw" and ev.source == "deck" and ev.player != viewer:
            card = None  # nobody else sees what you drew
        out.append({"k": ev.kind, "p": rotate(ev.player, viewer, n), "c": card_out(card) if card else None,
                    "s": ev.source, "t": rotate(ev.target, viewer, n), "m": ev.meld})
    return out


class _Count:
    def __init__(self, n: int):
        self.n = n

    def __len__(self) -> int:
        return self.n


class RemoteGame:
    """Looks like a Game to the table screen, but every move is sent to the host.

    `send` is called with action dicts; the host replies with a new snapshot
    (or an error), which `apply` folds in.
    """

    def __init__(self, send):
        self._send = send
        self._cards: dict[int, Card] = {}
        self.events: list[Event] = []
        self.pending = False
        self.players: list[Player] = []
        self.melds: list[Meld] = []
        self.discard_pile: list[Card] = []
        self.deck = _Count(0)
        self.round = 0
        self.current = 0
        self.has_drawn = False
        self.round_over = False
        self.game_over = False
        self.winner = None
        self.went_out = None
        self.pot = 0
        self.picked_from_discard: dict[int, list[Card]] = {}
        self.round_points: dict[int, int] = {}
        self.round_chips: dict[int, int] = {}

    # ---------------------------------------------------------------- state

    def _card(self, data) -> Card:
        cid, kind, color, value = data
        c = self._cards.get(cid)
        if c is None:
            c = Card(_KIND_BACK[kind], _COLOR_BACK.get(color), value or None, id=cid)
            self._cards[cid] = c
        return c

    def apply(self, snap: dict, events: list[dict]) -> None:
        self.round = snap["round"]
        self.current = snap["current"]
        self.has_drawn = snap["drawn"]
        self.round_over = snap["round_over"]
        self.game_over = snap["game_over"]
        self.winner = snap["winner"]
        self.went_out = snap["went_out"]
        self.pot = snap["pot"]
        self.deck = _Count(snap["deck"])
        self.discard_pile = [self._card(c) for c in snap["discard"]]
        players = []
        for d in snap["players"]:
            p = Player(d["name"], is_human=d["human"], difficulty=d["difficulty"])
            p.phase, p.score, p.chips = d["phase"], d["score"], d["chips"]
            p.laid_down, p.skips_pending, p.completed_this_round = d["laid"], d["skips"], d["done"]
            if d["hand"] is not None:
                p.hand = [self._card(c) for c in d["hand"]]
            else:
                p.hand = [Card(Kind.SKIP, id=-1) for _ in range(d["count"])]  # face-down placeholders
            players.append(p)
        self.players = players
        self.melds = [Meld(m["id"], m["owner"], GroupType(m["type"]), m["min"], [self._card(c) for c in m["cards"]])
                      for m in snap["melds"]]
        self.picked_from_discard = {int(k): [self._card(c) for c in v] for k, v in snap["picked"].items()}
        self.round_points = {int(k): v for k, v in snap["points"].items()}
        self.round_chips = {int(k): v for k, v in snap["chip_delta"].items()}
        for e in events:
            card = self._card(e["c"]) if e.get("c") else None
            self.events.append(Event(e["k"], player=e.get("p"), card=card, source=e.get("s"), target=e.get("t"),
                                     meld=e.get("m")))
        self.pending = False
        # Forget cards that left the game view, so the cache can't grow forever.
        live = {c.id for c in self.discard_pile}
        live.update(c.id for m in self.melds for c in m.cards)
        if self.players:
            live.update(c.id for c in self.players[0].hand)
        live.update(c.id for cards in self.picked_from_discard.values() for c in cards)
        live.update(ev.card.id for ev in self.events if ev.card)
        self._cards = {k: v for k, v in self._cards.items() if k in live}

    # ---------------------------------------------------------------- Game-like helpers

    @property
    def player(self) -> Player:
        return self.players[self.current]

    @property
    def top_discard(self) -> Card | None:
        return self.discard_pile[-1] if self.discard_pile else None

    def opponents_of(self, index: int) -> list[int]:
        return [i for i in range(len(self.players)) if i != index]

    def meld_by_id(self, meld_id: int) -> Meld:
        for m in self.melds:
            if m.id == meld_id:
                return m
        raise RuleError("No such group on the table.")

    def standings(self) -> list[int]:
        return sorted(range(len(self.players)),
                      key=lambda i: (-self.players[i].phase, self.players[i].score, -self.players[i].chips))

    def pop_events(self) -> list[Event]:
        ev, self.events = self.events, []
        return ev

    # ---------------------------------------------------------------- moves (sent to the host)

    def _check_turn(self):
        if self.pending:
            raise RuleError("Waiting for the host…")
        if self.round_over or self.current != 0:
            raise RuleError("It's not your turn.")

    def _request(self, action: dict):
        self.pending = True
        self._send({"t": "act", **action})

    def draw_from_deck(self, _seat: int = 0):
        self._check_turn()
        if self.has_drawn:
            raise RuleError("You already drew this turn.")
        self._request({"a": "draw", "src": "deck"})

    def draw_from_discard(self, _seat: int = 0):
        self._check_turn()
        if self.has_drawn:
            raise RuleError("You already drew this turn.")
        top = self.top_discard
        if top is None or top.is_skip:
            raise RuleError("You can't pick up a Skip." if top else "The discard pile is empty.")
        self._request({"a": "draw", "src": "discard"})

    def lay_down_auto(self, _seat: int, cards: list[Card]):
        self._check_turn()
        me = self.players[0]
        if me.laid_down:
            raise RuleError("You've already completed your phase this round.")
        if any(c.is_skip for c in cards):
            raise RuleError("Skips can't be part of a phase.")
        need = sum(r.size for r in me.requirements)
        if len(cards) < need:
            raise RuleError(f"Your phase needs at least {need} cards.")
        if partition_for_phase(PHASES[me.phase], cards) is None:
            raise RuleError("Those cards don't complete your phase.")
        self._request({"a": "lay", "cards": [c.id for c in cards]})

    def hit(self, _seat: int, card: Card, meld_id: int):
        self._check_turn()
        if not self.players[0].laid_down:
            raise RuleError("Complete your own phase before adding to others.")
        if not self.meld_by_id(meld_id).accepts(card):
            raise RuleError(f"{card.label()} doesn't fit that group.")
        self._request({"a": "hit", "card": card.id, "meld": meld_id})

    def discard(self, _seat: int, card: Card, skip_target: int | None = None):
        self._check_turn()
        if not self.has_drawn:
            raise RuleError("Draw a card first.")
        self._request({"a": "discard", "card": card.id, "target": skip_target})

    def next_round(self):
        raise RuleError("The host starts the next round.")
