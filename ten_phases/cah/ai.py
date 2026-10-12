"""Computer players for Cards Against Humanity.

There's no "right" answer in this game, so computers play for laughs:
  Easy    - plays any cards at random
  Medium  - prefers short, punchy answers
  Hard    - likes answers that echo words from the question
  Expert  - mixes the two, and as Czar favours answers that sound like a sentence
Computers never play blank cards unless that's all they have, and then write a stock line.
"""

from __future__ import annotations

import random
import re

STOCK_BLANKS = ("My ex.", "Whatever's in the fridge.", "A disappointing sandwich.", "The group chat.",
                "Grandma's secret recipe.", "Absolutely nothing.", "A suspiciously large goose.",
                "Tuesday.", "The 10 Phases admin panel.")


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z']+", text.lower()) if len(w) > 3}


class CahAI:
    def __init__(self, difficulty: str = "Medium", rng: random.Random | None = None):
        self.difficulty = difficulty
        self.rng = rng or random.Random()

    def _score(self, black: str, text: str) -> float:
        d = self.difficulty
        noise = self.rng.random()
        if d == "Easy":
            return noise
        short = 1.0 / (1 + len(text) / 30)
        echo = len(_words(black) & _words(text))
        if d == "Medium":
            return short + noise * 0.8
        if d == "Hard":
            return echo + noise * 0.9
        return short * 0.6 + echo * 0.6 + noise * 0.7

    def choose_cards(self, game, me: int) -> tuple[list[int], dict]:
        hand = game.players[me].hand
        pick = game.black.pick
        real = [c for c in hand if not c.blank]
        pool = sorted(real, key=lambda c: -self._score(game.black.text, c.text))[:pick]
        written = {}
        if len(pool) < pick:   # only blanks left: write something
            for c in [c for c in hand if c.blank][:pick - len(pool)]:
                pool.append(c)
                written[c.id] = {"text": self.rng.choice(STOCK_BLANKS)}
        return [c.id for c in pool], written

    def choose_winner(self, game, me: int) -> int:
        def score(sub):
            text = " ".join(sub.card_text(c) for c in sub.cards)
            return self._score(game.black.text, text)
        return max(game.order, key=score).id
