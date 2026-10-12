"""Go Fish rules.

The deck is 48 cards: numbers 1-12, one of each colour. A *book* is all four
colours of one number. On your turn you ask another player for a number you
hold. If they have any, they hand over all of them and you go again. If not,
"Go fish!": draw from the pond. Draw the number you asked for and you go
again; otherwise the turn passes. Books are laid down as soon as they're made.
Run out of cards and you draw one from the pond on your turn. When all 12
books are made, the most books wins.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from ..cards import COLORS, Card, number

VALUES = range(1, 13)
BOOK = 4


class RuleError(Exception):
    """An illegal move. The message is shown to the player."""


@dataclass
class FishPlayer:
    name: str
    is_human: bool = False
    difficulty: str | None = None
    hand: list[Card] = field(default_factory=list)
    books: list[int] = field(default_factory=list)

    def values(self) -> set[int]:
        return {c.value for c in self.hand}

    def count(self, value: int) -> int:
        return sum(1 for c in self.hand if c.value == value)


@dataclass
class FishEvent:
    kind: str                  # ask, give, gofish, draw, book, turn, game_over
    player: int | None = None  # who acted (asker / drawer / book maker)
    target: int | None = None  # who was asked
    value: int | None = None
    cards: list[Card] = field(default_factory=list)
    lucky: bool = False        # drew the number they asked for


def build_pond() -> list[Card]:
    return [number(c, v) for v in VALUES for c in COLORS]


class GoFishGame:
    def __init__(self, players: list[FishPlayer], rng: random.Random | None = None):
        if not 2 <= len(players) <= 6:
            raise ValueError("Go Fish needs 2-6 players")
        self.players = players
        self.rng = rng or random.Random()
        self.pond = build_pond()
        self.rng.shuffle(self.pond)
        self.events: list[FishEvent] = []
        self.history: list[FishEvent] = []
        self.game_over = False
        self.last_ask: dict[int, int] = {}
        deal = 7 if len(players) <= 3 else 5
        for _ in range(deal):
            for p in players:
                p.hand.append(self.pond.pop())
        for i in range(len(players)):
            self._collect_books(i)
        self.current = self.rng.randrange(len(players))
        self._start_turn()

    # ------------------------------------------------------------------ helpers

    def _emit(self, ev: FishEvent) -> None:
        self.events.append(ev)
        self.history.append(ev)

    def pop_events(self) -> list[FishEvent]:
        ev, self.events = self.events, []
        return ev

    @property
    def player(self) -> FishPlayer:
        return self.players[self.current]

    def books_made(self) -> int:
        return sum(len(p.books) for p in self.players)

    def can_be_asked(self, i: int) -> list[int]:
        """Players `i` may ask: anyone else still holding cards."""
        return [j for j, p in enumerate(self.players) if j != i and p.hand]

    def standings(self) -> list[int]:
        return sorted(range(len(self.players)), key=lambda i: -len(self.players[i].books))

    def winners(self) -> list[int]:
        best = max(len(p.books) for p in self.players)
        return [i for i, p in enumerate(self.players) if len(p.books) == best]

    def _collect_books(self, i: int) -> None:
        p = self.players[i]
        for v in sorted(p.values()):
            cards = [c for c in p.hand if c.value == v]
            if len(cards) == BOOK:
                p.hand = [c for c in p.hand if c.value != v]
                p.books.append(v)
                self._emit(FishEvent("book", player=i, value=v, cards=cards))

    def _draw(self, i: int) -> Card | None:
        if not self.pond:
            return None
        card = self.pond.pop()
        self.players[i].hand.append(card)
        return card

    # ------------------------------------------------------------------ turns

    def _start_turn(self) -> None:
        """Begin the current player's turn, refilling an empty hand or passing if they're out."""
        for _ in range(len(self.players) + 1):
            if self.books_made() == len(VALUES) or not (self.pond or any(p.hand for p in self.players)):
                self._finish()
                return
            p = self.player
            if not p.hand and self.pond:
                card = self._draw(self.current)
                self._emit(FishEvent("draw", player=self.current, cards=[card]))
                self._collect_books(self.current)
            if p.hand and self.can_be_asked(self.current):
                self._emit(FishEvent("turn", player=self.current))
                return
            if p.hand and not self.can_be_asked(self.current):
                # Nobody else has cards: fish for the rest of the pond.
                while self.pond:
                    card = self._draw(self.current)
                    self._emit(FishEvent("draw", player=self.current, cards=[card]))
                    self._collect_books(self.current)
                self._finish()
                return
            self.current = (self.current + 1) % len(self.players)
        self._finish()

    def _finish(self) -> None:
        if not self.game_over:
            self.game_over = True
            self._emit(FishEvent("game_over"))

    def _next_player(self) -> None:
        self.current = (self.current + 1) % len(self.players)
        self._start_turn()

    def ask(self, asker: int, target: int, value: int) -> bool:
        """Ask `target` for `value`. Returns True if `asker` gets to go again."""
        if self.game_over:
            raise RuleError("The game is over.")
        if asker != self.current:
            raise RuleError("It's not your turn.")
        if target == asker or not 0 <= target < len(self.players):
            raise RuleError("Ask another player.")
        p, t = self.players[asker], self.players[target]
        if not p.count(value):
            raise RuleError("You can only ask for a number you have.")
        if not t.hand:
            raise RuleError(f"{t.name.title()} has no cards left.")
        self.last_ask[asker] = value
        self._emit(FishEvent("ask", player=asker, target=target, value=value))
        got = [c for c in t.hand if c.value == value]
        if got:
            t.hand = [c for c in t.hand if c.value != value]
            p.hand.extend(got)
            self._emit(FishEvent("give", player=asker, target=target, value=value, cards=got))
            self._collect_books(asker)
            again = True
        else:
            self._emit(FishEvent("gofish", player=asker, target=target, value=value))
            card = self._draw(asker)
            lucky = card is not None and card.value == value
            if card is not None:
                self._emit(FishEvent("draw", player=asker, value=value, cards=[card], lucky=lucky))
                self._collect_books(asker)
            again = lucky
        if self.books_made() == len(VALUES):
            self._finish()
            return False
        if again and p.hand and self.can_be_asked(asker):
            self._emit(FishEvent("turn", player=asker))
            return True
        if again:
            self._start_turn()  # out of cards: refill (or move on) without losing the turn
            return self.current == asker and not self.game_over
        self._next_player()
        return False
