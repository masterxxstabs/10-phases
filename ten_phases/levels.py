"""Levels: experience (XP) from playing, and how much XP each level needs.

Going from level L to L+1 takes 100 + 25 * (L - 1) XP, so the early levels come quickly
and later ones take a few games each. XP is earned for the things you do at the table
(see `XP`), plus a bonus at the end of every round and every game.
"""

from __future__ import annotations

MAX_LEVEL = 100


def xp_to_next(level: int) -> int:
    """XP needed to go from `level` to `level + 1`."""
    return 100 + 25 * (max(1, level) - 1)


def total_for(level: int) -> int:
    """Total XP at which you reach `level`."""
    return sum(xp_to_next(k) for k in range(1, max(1, min(level, MAX_LEVEL))))


def level_for(xp: int) -> int:
    level, need = 1, xp_to_next(1)
    while level < MAX_LEVEL and xp >= need:
        xp -= need
        level += 1
        need = xp_to_next(level)
    return level


def progress(xp: int) -> tuple[int, int, int]:
    """(level, XP into this level, XP this level needs). At the top level the bar is full."""
    level = level_for(xp)
    if level >= MAX_LEVEL:
        return level, 1, 1
    return level, xp - total_for(level), xp_to_next(level)


# XP for each thing you do, by game and event kind (only your own moves count).
XP = {
    "phases": {"draw": 1, "discard": 2, "hit": 4, "lay": 25},
    "fish": {"ask": 1, "give": 3, "book": 15},
    "blackjack": {"bet": 2, "hit": 1, "double": 2, "split": 2, "blackjack": 10},
    "poker": {"call": 1, "bet": 2, "raise": 2, "check": 1, "win": 10},
    "cah": {"submit": 3, "win": 15},
    "monopoly": {"roll": 1, "buy": 10, "auction_end": 8, "build": 5, "unmortgage": 2},
    "slots": {},
}
# Blackjack hands, by how they ended.
SETTLE = {"blackjack": 15, "win": 10, "push": 4, "lose": 2, "bust": 2, "surrender": 2}
ROUND_XP = 10          # finishing a round (10 Phases)
WENT_OUT_XP = 20       # ...and you went out first
GAME_XP = 50           # finishing a game
WIN_XP = 100           # ...and you won it
SPIN_XP = 1            # each slot spin
