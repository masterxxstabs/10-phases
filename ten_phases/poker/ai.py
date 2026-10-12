"""Poker computer players and the Hint.

They only see what a real player sees: their own two cards and the board.
Hand strength is estimated by dealing out random opponent hands many times.

  Easy    - a "calling station": calls too much, rarely raises, never bluffs
  Medium  - plays by pot odds with a rough strength estimate, small raises with good hands
  Hard    - sharper estimates, sizes bets to the pot, bluffs now and then
  Expert  - adds position, semi-bluffs, blind steals and varied bet sizes
"""

from __future__ import annotations

import random

from ..cards import COLORS
from .engine import PokerCard, evaluate

TRIALS = {"Easy": 60, "Medium": 150, "Hard": 300, "Expert": 450}


def equity(hole, board, opponents: int, trials: int, rng: random.Random) -> float:
    """Chance to win (ties count half) against `opponents` random hands, finishing the board at random."""
    if opponents <= 0:
        return 1.0
    known = {(c.color, c.value) for c in list(hole) + list(board)}
    deck = [PokerCard(None, c, v, id=-9) for c in COLORS for v in range(2, 15) if (c, v) not in known]
    need = 5 - len(board)
    score = 0.0
    for _ in range(trials):
        draw = rng.sample(deck, need + 2 * opponents)
        full = list(board) + draw[:need]
        mine = evaluate(list(hole) + full)
        best_other = max(evaluate(draw[need + 2 * k:need + 2 * k + 2] + full) for k in range(opponents))
        if mine > best_other:
            score += 1
        elif mine == best_other:
            score += 0.5
    return score / trials


def _raise_to(game, me: int, fraction: float) -> int:
    """A raise of `fraction` of the pot (after calling), clamped to what's allowed."""
    least, most = game.raise_range(me)
    pot = game.pot_total() + game.to_call(me)
    target = game.current_bet + int(pot * fraction)
    return max(least, min(most, target))


class PokerAI:
    def __init__(self, difficulty: str = "Medium", rng: random.Random | None = None):
        self.difficulty = difficulty
        self.rng = rng or random.Random()

    def choose(self, game, me: int) -> tuple[str, int]:
        """(action, raise-to amount) for the player whose turn it is."""
        legal = game.legal_actions(me)
        p = game.players[me]
        opponents = sum(1 for k, q in enumerate(game.players) if k != me and q.live)
        eq = equity(p.hole, game.board, opponents, TRIALS.get(self.difficulty, 150), self.rng)
        to_call = game.to_call(me)
        pot = game.pot_total()
        odds = to_call / (pot + to_call) if to_call else 0.0
        d = self.difficulty
        r = self.rng.random()
        can_raise = "raise" in legal

        if d == "Easy":
            eq += self.rng.uniform(-0.12, 0.12)
            if can_raise and eq > 0.8 and r < 0.5:
                return "raise", _raise_to(game, me, 0.5)
            if to_call == 0:
                return "check", 0
            if eq > odds * 0.6 or to_call <= game.blinds[1] or r < 0.25:
                return "call", 0
            return "fold", 0

        # Strength needed to raise, given how many people we have to beat.
        strong = {"Medium": 0.62, "Hard": 0.58, "Expert": 0.55}[d] + 0.02 * max(0, opponents - 1)
        late = game.street in ("turn", "river")
        if d == "Expert":
            # Position: acting last (on the button) makes marginal hands playable.
            if me == game.button:
                eq += 0.04
            # Steal the blinds from late position when everyone folded to us.
            if game.street == "preflop" and can_raise and to_call <= game.blinds[1] and opponents <= 2 and r < 0.35:
                return "raise", _raise_to(game, me, 0.75)
        if can_raise and eq >= strong:
            # Value bet: bigger with better hands, sometimes just call to trap.
            if d != "Medium" and eq > 0.85 and r < 0.25 and to_call == 0 and not late:
                return "check", 0
            size = 0.5 if d == "Medium" else self.rng.choice((0.5, 0.66, 0.75, 1.0)) if d == "Expert" else 0.66
            if eq > 0.9 and late and d == "Expert" and r < 0.3:
                size = 3.0   # shove the nuts sometimes
            return "raise", _raise_to(game, me, size)
        if d in ("Hard", "Expert") and can_raise and to_call == 0:
            bluff = 0.08 if d == "Hard" else 0.14
            if game.street != "preflop" and r < bluff and opponents <= 2:
                return "raise", _raise_to(game, me, 0.6)   # a bluff (or a semi-bluff on the flop)
        if to_call == 0:
            return "check", 0
        margin = {"Medium": 0.0, "Hard": 0.02, "Expert": 0.0}[d]
        if eq >= odds + margin:
            return "call", 0
        return "fold", 0


def hint(game, me: int, rng: random.Random | None = None) -> tuple[str, str]:
    """(action, explanation) for the Hint button."""
    rng = rng or random.Random()
    p = game.players[me]
    opponents = sum(1 for k, q in enumerate(game.players) if k != me and q.live)
    eq = equity(p.hole, game.board, opponents, 400, rng)
    to_call = game.to_call(me)
    pot = game.pot_total()
    pct = round(eq * 100)
    vs = f"against {opponents} player{'s' if opponents != 1 else ''}"
    legal = game.legal_actions(me)
    strong = 0.6 + 0.03 * max(0, opponents - 1)
    if to_call == 0:
        if eq >= strong and "raise" in legal:
            return "raise", f"You win about {pct}% {vs} - bet around half the pot"
        return "check", f"You win about {pct}% {vs} - check for a free card"
    need = round(100 * to_call / (pot + to_call))
    if eq >= strong and "raise" in legal:
        return "raise", f"You win about {pct}% {vs} - raise for value"
    if eq * 100 >= need:
        return "call", f"You win about {pct}% {vs}; calling {to_call} only needs {need}% - call"
    return "fold", f"You win about {pct}% {vs}, but calling {to_call} needs {need}% - fold"
