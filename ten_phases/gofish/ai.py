"""Go Fish computer players.

They only use what a person at the table would know: their own hand and
everything said out loud. Asking for 7s tells everyone you hold a 7; "Go fish!"
tells everyone the player had none (until they draw again). Difficulty sets how
long they remember and whether they work out the odds.

  Easy    - forgets quickly and often asks at random
  Medium  - remembers the last few turns
  Hard    - remembers everything and weighs the odds
  Expert  - also uses who said "go fish" and plays for the closest book
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .engine import BOOK, GoFishGame


@dataclass(frozen=True)
class FishProfile:
    memory_turns: int       # how many turns a remembered fact lasts
    random_rate: float      # chance of a random ask
    use_odds: bool          # estimate who probably holds a number
    use_misses: bool        # remember who said "go fish" for which number


FISH_PROFILES = {
    "Easy": FishProfile(3, 0.45, False, False),
    "Medium": FishProfile(10, 0.12, False, False),
    "Hard": FishProfile(10_000, 0.0, True, False),
    "Expert": FishProfile(10_000, 0.0, True, True),
}


class GoFishAI:
    def __init__(self, difficulty: str = "Medium", rng: random.Random | None = None):
        self.difficulty = difficulty
        self.profile = FISH_PROFILES[difficulty]
        self.rng = rng or random.Random()
        self.seen = 0
        self.turn = 0
        self.has: dict[tuple[int, int], tuple[int, int]] = {}   # (player, value) -> (count, turn learned)
        self.lacks: dict[tuple[int, int], int] = {}             # (player, value) -> turn learned
        self.booked: set[int] = set()

    # ---------------------------------------------------------------- memory

    def observe(self, game: GoFishGame) -> None:
        for ev in game.history[self.seen:]:
            k = ev.kind
            if k == "turn":
                self.turn += 1
            elif k == "ask":
                prev = self.has.get((ev.player, ev.value), (0, 0))[0]
                self.has[(ev.player, ev.value)] = (max(1, prev), self.turn)
                self.lacks.pop((ev.player, ev.value), None)
            elif k == "give":
                prev = self.has.get((ev.player, ev.value), (1, 0))[0]
                self.has[(ev.player, ev.value)] = (max(1, prev) + len(ev.cards), self.turn)
                self.has.pop((ev.target, ev.value), None)
                self.lacks[(ev.target, ev.value)] = self.turn
            elif k == "gofish":
                self.has.pop((ev.target, ev.value), None)
                self.lacks[(ev.target, ev.value)] = self.turn
            elif k == "draw":
                # A drawn card could be anything, so what they lacked is uncertain again.
                for key in [key for key in self.lacks if key[0] == ev.player]:
                    del self.lacks[key]
                if ev.lucky:
                    prev = self.has.get((ev.player, ev.value), (0, 0))[0]
                    self.has[(ev.player, ev.value)] = (prev + 1, self.turn)
            elif k == "book":
                self.booked.add(ev.value)
                for key in [key for key in self.has if key[1] == ev.value]:
                    del self.has[key]
        self.seen = len(game.history)

    def _knows_has(self, player: int, value: int) -> int:
        count, when = self.has.get((player, value), (0, 0))
        return count if count and self.turn - when <= self.profile.memory_turns else 0

    def _knows_lacks(self, player: int, value: int) -> bool:
        if not self.profile.use_misses:
            return False
        when = self.lacks.get((player, value))
        return when is not None and self.turn - when <= self.profile.memory_turns

    # ---------------------------------------------------------------- deciding

    def choose_ask(self, game: GoFishGame, me: int) -> tuple[int, int]:
        """Return (target player, value) to ask for."""
        self.observe(game)
        hand = game.players[me]
        values = sorted(hand.values())
        targets = game.can_be_asked(me)
        if self.rng.random() < self.profile.random_rate:
            return self.rng.choice(targets), self.rng.choice(values)

        unknown_cards = len(game.pond) + sum(len(game.players[t].hand) for t in targets)
        best, best_score = None, None
        for v in values:
            mine = hand.count(v)
            known_elsewhere = sum(self._knows_has(t, v) for t in targets)
            unknown_copies = max(0, BOOK - mine - known_elsewhere)
            for t in targets:
                held = self._knows_has(t, v)
                if held:
                    score = 100 + 10 * held
                elif self._knows_lacks(t, v):
                    score = -50
                elif self.profile.use_odds and unknown_cards:
                    share = len(game.players[t].hand) / unknown_cards
                    score = 10 * (1 - (1 - share) ** unknown_copies)
                else:
                    score = 10
                score += 10 * mine                      # closer to a book
                score += 0.5 * len(game.players[t].hand)
                score += self.rng.random() * 0.1        # break ties
                if best_score is None or score > best_score:
                    best, best_score = (t, v), score
        return best
