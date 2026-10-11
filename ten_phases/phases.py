"""Phase definitions and the rules for sets, runs and colour groups."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from itertools import permutations, product

from .cards import MAX_VALUE, MIN_VALUE, Card


class GroupType(str, Enum):
    SET = "set"      # cards of the same number
    RUN = "run"      # consecutive numbers
    COLOR = "color"  # cards of the same colour


@dataclass(frozen=True)
class Requirement:
    type: GroupType
    size: int

    def describe(self) -> str:
        if self.type is GroupType.SET:
            return f"Set of {self.size}"
        if self.type is GroupType.RUN:
            return f"Run of {self.size}"
        return f"{self.size} of one color"


S, R, C = GroupType.SET, GroupType.RUN, GroupType.COLOR

PHASES: list[tuple[Requirement, ...]] = [
    (Requirement(S, 3), Requirement(S, 3)),
    (Requirement(S, 3), Requirement(R, 4)),
    (Requirement(S, 4), Requirement(R, 4)),
    (Requirement(R, 7),),
    (Requirement(R, 8),),
    (Requirement(R, 9),),
    (Requirement(S, 4), Requirement(S, 4)),
    (Requirement(C, 7),),
    (Requirement(S, 5), Requirement(S, 2)),
    (Requirement(S, 5), Requirement(S, 3)),
]

NUM_PHASES = len(PHASES)


def describe_phase(index: int) -> str:
    """Human readable text, e.g. '2 sets of 3' or '1 set of 3 + 1 run of 4'."""
    reqs = PHASES[index]
    if len(reqs) == 2 and reqs[0] == reqs[1]:
        r = reqs[0]
        return f"2 {r.type.value}s of {r.size}"
    return " + ".join(r.describe() for r in reqs)


# --------------------------------------------------------------------------- groups


def _naturals(cards: list[Card]) -> list[Card] | None:
    """Number cards in the group, or None if the group contains a skip."""
    if any(c.is_skip for c in cards):
        return None
    return [c for c in cards if c.is_number]


def run_start_range(values: list[int], length: int) -> range:
    """Possible first values of a run of `length` that contains all `values`."""
    if not values:
        return range(MIN_VALUE, MAX_VALUE - length + 2)
    lo = max(MIN_VALUE, max(values) - length + 1)
    hi = min(min(values), MAX_VALUE - length + 1)
    return range(lo, hi + 1)


def is_valid_group(gtype: GroupType, cards: list[Card], min_size: int = 1) -> bool:
    """True if `cards` form a legal group of the given type with at least `min_size` cards.

    Every group must contain at least one natural (non-wild) card.
    """
    if len(cards) < min_size:
        return False
    naturals = _naturals(cards)
    if not naturals:
        return False
    if gtype is GroupType.SET:
        return len({c.value for c in naturals}) == 1
    if gtype is GroupType.COLOR:
        return len({c.color for c in naturals}) == 1
    values = [c.value for c in naturals]
    if len(set(values)) != len(values):
        return False
    return len(cards) <= MAX_VALUE and len(run_start_range(values, len(cards))) > 0


def arrange_run(cards: list[Card]) -> list[tuple[Card, int]]:
    """Order a valid run for display, assigning a value to each wild card."""
    naturals = sorted((c for c in cards if c.is_number), key=lambda c: c.value)
    wilds = [c for c in cards if c.is_wild]
    starts = run_start_range([c.value for c in naturals], len(cards))
    start = starts.start if len(starts) else (naturals[0].value if naturals else 1)
    by_value = {c.value: c for c in naturals}
    out = []
    for v in range(start, start + len(cards)):
        out.append((by_value[v], v) if v in by_value else (wilds.pop(), v))
    return out


def arrange_group(gtype: GroupType, cards: list[Card]) -> list[Card]:
    """Display order for a group on the table."""
    if gtype is GroupType.RUN and is_valid_group(gtype, cards):
        return [c for c, _ in arrange_run(cards)]
    naturals = sorted((c for c in cards if c.is_number), key=lambda c: c.value)
    return naturals + [c for c in cards if not c.is_number]


# --------------------------------------------------------------------------- phases


def match_groups(reqs: tuple[Requirement, ...], groups: list[list[Card]]) -> list[Requirement] | None:
    """Match each group to one requirement. Returns requirements in group order or None."""
    if len(groups) != len(reqs):
        return None
    for perm in permutations(reqs):
        if all(is_valid_group(r.type, g, r.size) for r, g in zip(perm, groups)):
            return list(perm)
    return None


def partition_for_phase(reqs: tuple[Requirement, ...], cards: list[Card]) -> list[tuple[Requirement, list[Card]]] | None:
    """Split the selected cards into the phase's groups, using every card.

    Returns [(requirement, cards), ...] or None if no split works.
    """
    n = len(reqs)
    if len(cards) < sum(r.size for r in reqs):
        return None
    if n == 1:
        r = reqs[0]
        return [(r, list(cards))] if is_valid_group(r.type, cards, r.size) else None
    # Card 0 is always placed in group 0 to halve the symmetric search.
    first, rest = cards[0], cards[1:]
    for assignment in product(range(n), repeat=len(rest)):
        groups: list[list[Card]] = [[] for _ in range(n)]
        groups[0].append(first)
        for card, g in zip(rest, assignment):
            groups[g].append(card)
        matched = match_groups(reqs, groups)
        if matched:
            return list(zip(matched, groups))
    return None
