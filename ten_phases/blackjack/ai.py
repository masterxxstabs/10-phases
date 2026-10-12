"""Blackjack computer players and the Hint.

  Easy    - plays by feel: hits below 15ish, never doubles or splits, random bets
  Medium  - copies the dealer: hits to 17, doubles on 11, flat bets
  Hard    - perfect basic strategy (4 decks, dealer stands on soft 17)
  Expert  - basic strategy + Hi-Lo card counting: bets more when the count is
            high and makes the best-known count-based plays
"""

from __future__ import annotations

import random

from .engine import DECKS, MAX_BET, MIN_BET, BlackjackGame, hand_value

H, S, D, DS, P = "hit", "stand", "double", "double_or_stand", "split"


def up_value(card) -> int:
    """Dealer up card as basic-strategy charts use it: 2-10, ace = 11."""
    return 11 if card.value == 1 else min(card.value, 10)


def basic_strategy(cards, dealer_up: int, can_double: bool, can_split: bool) -> tuple[str, str]:
    """Return (action, reason) from the standard chart."""
    total, soft = hand_value(cards)
    d = dealer_up
    dealer = "an ace" if d == 11 else str(d)
    if can_split and len(cards) == 2:
        a, b = min(cards[0].value, 10), min(cards[1].value, 10)
        if a == b:
            pair = 11 if cards[0].value == 1 else a
            rule = {
                11: (True, "Always split aces"),
                8: (True, "Always split 8s - 16 is the worst hand"),
                10: (False, ""),
                5: (False, ""),
                9: (d in (2, 3, 4, 5, 6, 8, 9), f"Split 9s against {dealer}"),
                7: (d <= 7, f"Split 7s against a weak {dealer}"),
                6: (d <= 6, f"Split 6s against a weak {dealer}"),
                4: (d in (5, 6), f"Split 4s against {dealer}"),
                3: (d <= 7, f"Split 3s against {dealer}"),
                2: (d <= 7, f"Split 2s against {dealer}"),
            }[pair]
            if rule[0]:
                return P, rule[1]

    def dbl(reason):
        return (D, reason) if can_double else (H, reason.replace("Double", "Hit"))

    if soft and len(cards) >= 2:
        if total >= 19:
            return S, f"Soft {total} is strong - stand"
        if total == 18:
            if 3 <= d <= 6:
                return (D, f"Double soft 18 against a weak {dealer}") if can_double else \
                    (S, f"Stand on soft 18 against {dealer}")
            if d in (2, 7, 8):
                return S, f"Stand on soft 18 against {dealer}"
            return H, f"Soft 18 can't beat {dealer} often - hit (you can't bust)"
        if total == 17 and 3 <= d <= 6:
            return dbl(f"Double soft 17 against a weak {dealer}")
        if total in (15, 16) and 4 <= d <= 6:
            return dbl(f"Double soft {total} against a weak {dealer}")
        if total in (13, 14) and 5 <= d <= 6:
            return dbl(f"Double soft {total} against a weak {dealer}")
        return H, f"Soft {total}: hit - an ace means you can't bust"
    if total >= 17:
        return S, f"{total} is high enough - stand"
    if 13 <= total <= 16:
        if d <= 6:
            return S, f"{total} against {dealer}: stand and let the dealer bust"
        return H, f"{total} against {dealer}: the dealer is likely to make 17+, so hit"
    if total == 12:
        if 4 <= d <= 6:
            return S, f"12 against {dealer}: stand and let the dealer bust"
        return H, f"12 against {dealer}: hit"
    if total == 11:
        return dbl(f"11 against {dealer}: double down") if d <= 10 else (H, "11 against an ace: hit")
    if total == 10:
        return dbl(f"10 against {dealer}: double down") if d <= 9 else (H, f"10 against {dealer}: hit")
    if total == 9:
        return dbl(f"9 against {dealer}: double down") if 3 <= d <= 6 else (H, f"9 against {dealer}: hit")
    return H, f"{total} can't bust - hit"


def true_count(game) -> float:
    """Hi-Lo: 2-6 = +1, 7-9 = 0, 10-A = -1, divided by decks left in the shoe."""
    running = sum(1 if 2 <= c.value <= 6 else -1 if c.value >= 10 or c.value == 1 else 0 for c in game.seen)
    decks_left = max(0.5, len(game.shoe) / 52) if hasattr(game.shoe, "__len__") else DECKS
    return running / decks_left


class BlackjackAI:
    def __init__(self, difficulty: str = "Medium", rng: random.Random | None = None):
        self.difficulty = difficulty
        self.rng = rng or random.Random()

    def choose_bet(self, game: BlackjackGame, me: int) -> int:
        top = game.max_bet(me)
        if self.difficulty == "Easy":
            bet = self.rng.randint(MIN_BET, MAX_BET)
        elif self.difficulty == "Expert":
            bet = round(2 + 3 * true_count(game))
        else:
            bet = 4
        return max(MIN_BET, min(top, bet))

    def choose_action(self, game: BlackjackGame, me: int) -> str:
        legal = game.legal_actions(me)
        hand = game.players[me].hands[game.turn[1]]
        total, soft = hand_value(hand.cards)
        d = up_value(game.dealer_up)
        if self.difficulty == "Easy":
            limit = 15 + self.rng.choice([-1, 0, 0, 1])
            return "hit" if total < limit else "stand"
        if self.difficulty == "Medium":
            if total == 11 and "double" in legal:
                return "double"
            return "hit" if total < 17 or (soft and total < 18) else "stand"
        action, _ = basic_strategy(hand.cards, d, "double" in legal, "split" in legal)
        if self.difficulty == "Expert":
            action = self._deviation(game, total, soft, d, legal) or action
        if action == DS:
            action = "double" if "double" in legal else "stand"
        return action if action in legal else ("hit" if action == "double" else "stand")

    def _deviation(self, game, total, soft, d, legal) -> str | None:
        """A few of the best-known count-based plays."""
        if soft:
            return None
        tc = true_count(game)
        if total == 16 and d == 10 and tc >= 0:
            return "stand"
        if total == 15 and d == 10 and tc >= 4:
            return "stand"
        if total == 12 and d == 3 and tc >= 2:
            return "stand"
        if total == 12 and d == 2 and tc >= 3:
            return "stand"
        if total == 11 and d == 11 and tc >= 1 and "double" in legal:
            return "double"
        if total == 10 and d == 10 and tc >= 4 and "double" in legal:
            return "double"
        if total == 9 and d == 2 and tc >= 1 and "double" in legal:
            return "double"
        return None


def hint(game: BlackjackGame, me: int) -> tuple[str, str]:
    """(action, reason) for the Hint button: plain basic strategy."""
    legal = game.legal_actions(me)
    hand = game.players[me].hands[game.turn[1]]
    action, reason = basic_strategy(hand.cards, up_value(game.dealer_up), "double" in legal, "split" in legal)
    if action == DS:
        action = "double" if "double" in legal else "stand"
    if action not in legal:
        action = "hit" if action == "double" else "stand"
    return action, reason
