"""A three-reel slot machine played with your Chip Bank.

One payline across the middle. WILD stands in for any symbol except the
jackpot. Payouts are multiples of the bet; the machine returns about 95% of
what's wagered over time (exact figure: `return_to_player()`).
"""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass

CHERRY, LEMON, BELL, STAR, SEVEN, WILD, JACKPOT = "CHERRY", "LEMON", "BELL", "STAR", "SEVEN", "WILD", "JACKPOT"
SYMBOLS = (CHERRY, LEMON, BELL, STAR, SEVEN, WILD, JACKPOT)

# How often each symbol appears on a reel (out of the total).
WEIGHTS = {CHERRY: 9, LEMON: 7, BELL: 6, STAR: 5, SEVEN: 3, WILD: 1, JACKPOT: 1}

# Three of a kind (wilds fill in), as multiples of the bet.
THREE = {JACKPOT: 300, WILD: 100, SEVEN: 25, STAR: 15, BELL: 10, LEMON: 6, CHERRY: 4}
TWO_CHERRIES = 2
ONE_CHERRY = 1        # a cherry on the first reel gives your bet back

BETS = (1, 5, 10, 25)


def strip() -> list[str]:
    """One reel's symbols in order (all three reels use the same mix, shuffled differently)."""
    return [s for s in SYMBOLS for _ in range(WEIGHTS[s])]


def payout(line: tuple[str, str, str]) -> tuple[int, str]:
    """(multiplier, name of the win) for the symbols on the payline."""
    if all(s == JACKPOT for s in line):
        return THREE[JACKPOT], "JACKPOT!"
    if all(s == WILD for s in line):
        return THREE[WILD], "TRIPLE WILD!"
    if JACKPOT not in line:
        real = {s for s in line if s != WILD}
        if len(real) == 1:
            sym = real.pop()
            return THREE[sym], f"THREE {sym[:-1] + 'IES' if sym.endswith('Y') else sym + 'S'}"
    cherries = sum(1 for s in line if s == CHERRY)
    if cherries >= 2:
        return TWO_CHERRIES, "TWO CHERRIES"
    if line[0] == CHERRY:
        return ONE_CHERRY, "CHERRY"
    return 0, ""


def return_to_player() -> float:
    """Exact long-run share of each bet paid back, over every reel combination."""
    total = sum(WEIGHTS.values())
    rtp = 0.0
    for line in itertools.product(SYMBOLS, repeat=3):
        p = WEIGHTS[line[0]] * WEIGHTS[line[1]] * WEIGHTS[line[2]] / total ** 3
        rtp += p * payout(line)[0]
    return rtp


@dataclass
class Spin:
    stops: list[int]                  # index of the payline symbol on each reel
    line: tuple[str, str, str]
    bet: int
    multiplier: int
    win: int
    name: str


class SlotMachine:
    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self.reels = []
        for _ in range(3):
            reel = strip()
            self.rng.shuffle(reel)
            self.reels.append(reel)
        self.stops = [self.rng.randrange(len(r)) for r in self.reels]

    def symbol(self, reel: int, offset: int = 0) -> str:
        r = self.reels[reel]
        return r[(self.stops[reel] + offset) % len(r)]

    def spin(self, bet: int) -> Spin:
        self.stops = [self.rng.randrange(len(r)) for r in self.reels]
        line = tuple(self.symbol(k) for k in range(3))
        mult, name = payout(line)
        return Spin(list(self.stops), line, bet, mult, bet * mult, name)
