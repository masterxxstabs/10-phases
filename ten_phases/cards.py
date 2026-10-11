"""Cards and the deck.

A standard deck has 108 cards:
  * numbers 1-12 in four colours, two of each  (96 cards)
  * 8 wild cards
  * 4 skip cards
"""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field
from enum import Enum


class Color(str, Enum):
    RED = "red"
    BLUE = "blue"
    GREEN = "green"
    YELLOW = "yellow"


COLORS = (Color.RED, Color.BLUE, Color.GREEN, Color.YELLOW)


class Kind(str, Enum):
    NUMBER = "number"
    WILD = "wild"
    SKIP = "skip"


MIN_VALUE = 1
MAX_VALUE = 12

_ids = itertools.count(1)


@dataclass(eq=False)
class Card:
    """A single physical card. Identity matters (two red 7s are different cards)."""

    kind: Kind
    color: Color | None = None
    value: int | None = None
    id: int = field(default_factory=lambda: next(_ids))

    @property
    def is_wild(self) -> bool:
        return self.kind is Kind.WILD

    @property
    def is_skip(self) -> bool:
        return self.kind is Kind.SKIP

    @property
    def is_number(self) -> bool:
        return self.kind is Kind.NUMBER

    @property
    def points(self) -> int:
        """Penalty points if the card is left in hand at the end of a round."""
        if self.kind is Kind.WILD:
            return 25
        if self.kind is Kind.SKIP:
            return 15
        return 5 if self.value <= 9 else 10

    def sort_key(self) -> tuple:
        order = {Kind.NUMBER: 0, Kind.WILD: 1, Kind.SKIP: 2}[self.kind]
        color = COLORS.index(self.color) if self.color else 0
        return (order, self.value or 0, color)

    def color_sort_key(self) -> tuple:
        order = {Kind.NUMBER: 0, Kind.WILD: 1, Kind.SKIP: 2}[self.kind]
        color = COLORS.index(self.color) if self.color else 0
        return (order, color, self.value or 0)

    def label(self) -> str:
        if self.kind is Kind.WILD:
            return "Wild"
        if self.kind is Kind.SKIP:
            return "Skip"
        return f"{self.color.value.title()} {self.value}"

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{self.label()}#{self.id}>"


def number(color: Color, value: int) -> Card:
    return Card(Kind.NUMBER, color, value)


def wild() -> Card:
    return Card(Kind.WILD)


def skip() -> Card:
    return Card(Kind.SKIP)


def build_deck() -> list[Card]:
    deck = [number(c, v) for c in COLORS for v in range(MIN_VALUE, MAX_VALUE + 1) for _ in range(2)]
    deck += [wild() for _ in range(8)]
    deck += [skip() for _ in range(4)]
    return deck


class Deck:
    """Draw pile. Refilled from the discard pile when it runs out."""

    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self.cards = build_deck()
        self.rng.shuffle(self.cards)

    def __len__(self) -> int:
        return len(self.cards)

    def draw(self) -> Card:
        return self.cards.pop()

    def refill(self, cards: list[Card]) -> None:
        self.cards = list(cards)
        self.rng.shuffle(self.cards)
