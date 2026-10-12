import random

import pytest

from ten_phases.cards import COLORS
from ten_phases.poker.ai import PokerAI, equity, hint
from ten_phases.poker.engine import (STARTING_CHIPS, PokerGame, PokerPlayer, RuleError, describe, evaluate,
                                     poker_card)

R, B, G, Y = COLORS


def cards(text: str):
    ranks = {"A": 14, "K": 13, "Q": 12, "J": 11, "T": 10}
    suits = {"r": R, "b": B, "g": G, "y": Y}
    return [poker_card(suits[t[-1]], ranks.get(t[0]) or int(t[0])) for t in text.split()]


@pytest.mark.parametrize("hand, name", [
    ("Ar Kr Qr Jr Tr 2b 3g", "ROYAL FLUSH"),
    ("5b 4b 3b 2b Ab Kr Kg", "STRAIGHT FLUSH"),
    ("9r 9b 9g 9y 2r 3b 4g", "FOUR NINES"),
    ("Kr Kb Kg 2y 2r 3b 4g", "FULL HOUSE, KINGS FULL"),
    ("Kr Kb Kg Qr Qb Qg 2y", "FULL HOUSE, KINGS FULL"),
    ("2r 7r 9r Jr Kr Ab Ag", "FLUSH, KING HIGH"),
    ("Ar 2b 3g 4y 5r Kb Kg", "STRAIGHT TO THE FIVE"),
    ("6r 6b 6g Ar Kb 2g 3y", "THREE SIXES"),
    ("Ar Ab Kr Kb Qg Qy 2r", "TWO PAIR, ACES AND KINGS"),
    ("Ar Ab 2r 5b 7g 9y Jr", "PAIR OF ACES"),
    ("Ar Qb 9r 7b 5g 3y 2r", "ACE HIGH"),
])
def test_hand_names(hand, name):
    assert describe(evaluate(cards(hand))) == name


def test_hand_order_and_kickers():
    ladder = ["Ar Kr Qr Jr Tr", "9r 9b 9g 9y 2r", "Kr Kb Kg 2y 2r", "2r 7r 9r Jr Kr", "Ar 2b 3g 4y 5r",
              "6r 6b 6g Ar Kb", "Ar Ab Kr Kb Qg", "Ar Ab 2r 5b 7g", "Ar Qb 9r 7b 5g"]
    scores = [evaluate(cards(h)) for h in ladder]
    assert scores == sorted(scores, reverse=True)
    assert evaluate(cards("Ar Ab Kr 5b 3g")) > evaluate(cards("Ag Ay Qr 5b 3g"))      # kicker
    assert evaluate(cards("6r 5b 4g 3y 2r")) > evaluate(cards("5r 4b 3g 2y Ar"))       # six-high beats the wheel
    assert evaluate(cards("Ar Kr Qb Jg Ty")) == evaluate(cards("Ab Kb Qr Jy Tg"))      # suits never break ties


def rig(game: PokerGame, holes: dict[int, str], board: str):
    """Swap in known hole cards and put the board on top of the deck."""
    for k, h in holes.items():
        game.players[k].hole = cards(h)
    game.deck = list(reversed(cards(board))) + game.deck[:0]


def play_out(game):
    """Everyone checks or calls until the hand ends."""
    while game.phase == "playing":
        i = game.current
        game.act(i, "call" if game.to_call(i) else "check")


def test_side_pots_pay_the_right_people():
    players = [PokerPlayer("A", chips=10), PokerPlayer("B", chips=30), PokerPlayer("C", chips=60)]
    g = PokerGame(players, random.Random(1))
    total = sum(p.chips + p.total_in for p in g.players)
    rig(g, {0: "Ar Ab", 1: "Kr Kb", 2: "Qr Qb"}, "2g 7y 9g Jy 3b")   # A best, then B, then C
    # Everyone shoves.
    while g.phase == "playing":
        i = g.current
        if "raise" in g.legal_actions(i):
            g.act(i, "raise", g.raise_range(i)[1])
        else:
            g.act(i, "call" if g.to_call(i) else "check")
    assert g.phase == "settled"
    assert sum(p.chips for p in g.players) == total
    assert g.players[0].chips == 30           # main pot: 10 from each
    assert g.players[1].chips == 40           # side pot: 20 from B and C
    assert g.players[2].chips == 30           # C's unmatched 30 comes back


def test_folding_hands_the_pot_over():
    g = PokerGame([PokerPlayer("A"), PokerPlayer("B")], random.Random(2))
    i = g.current
    g.act(i, "fold")
    assert g.phase == "settled"
    assert g.last_wins[0]["player"] != i
    assert sum(p.chips for p in g.players) == 2 * STARTING_CHIPS


def test_illegal_moves_are_refused():
    g = PokerGame([PokerPlayer("A"), PokerPlayer("B"), PokerPlayer("C")], random.Random(3))
    i = g.current
    other = (i + 1) % 3
    with pytest.raises(RuleError):
        g.act(other, "call")                       # not their turn
    with pytest.raises(RuleError):
        g.act(i, "check")                          # facing the big blind
    lo, hi = g.raise_range(i)
    with pytest.raises(RuleError):
        g.act(i, "raise", lo - 1)
    with pytest.raises(RuleError):
        g.act(i, "raise", hi + 1)
    g.act(i, "raise", lo + 1)
    assert g.current_bet == lo + 1


@pytest.mark.parametrize("seed", range(150))
def test_random_games_never_lose_or_make_chips(seed):
    rng = random.Random(seed)
    n = rng.randint(2, 6)
    g = PokerGame([PokerPlayer(f"P{k}") for k in range(n)], random.Random(seed))
    while not g.game_over:
        if g.phase == "settled":
            assert sum(p.chips for p in g.players) == n * STARTING_CHIPS
            g.next_round()
            continue
        i = g.current
        a = rng.choice(g.legal_actions(i))
        if a == "raise":
            lo, hi = g.raise_range(i)
            g.act(i, a, rng.choice([lo, hi, rng.randint(lo, hi)]))
        else:
            g.act(i, a)
    assert sum(p.chips for p in g.players) == n * STARTING_CHIPS


def test_computer_players_finish_games_and_hints_make_sense():
    rng = random.Random(9)
    levels = ["Easy", "Medium", "Hard", "Expert"]
    g = PokerGame([PokerPlayer(lv, difficulty=lv) for lv in levels], random.Random(4), hands_per_game=6)
    ais = [PokerAI(lv, random.Random(k)) for k, lv in enumerate(levels)]
    while not g.game_over:
        if g.phase == "settled":
            g.next_round()
            continue
        i = g.current
        action, hint_reason = hint(g, i, rng)
        assert action in g.legal_actions(i) and "%" in hint_reason
        g.act(i, *ais[i].choose(g, i))
    assert equity(cards("Ar Ab"), [], 1, 300, rng) > 0.75
    assert equity(cards("7r 2b"), [], 1, 300, rng) < 0.45
