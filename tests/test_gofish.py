import random

import pytest

from ten_phases.cards import COLORS, number
from ten_phases.gofish.ai import GoFishAI
from ten_phases.gofish.engine import FishPlayer, GoFishGame, RuleError


def new_game(n=3, seed=1):
    return GoFishGame([FishPlayer(f"P{i}") for i in range(n)], random.Random(seed))


def total_cards(g):
    return len(g.pond) + sum(len(p.hand) + 4 * len(p.books) for p in g.players)


def test_deal_and_deck():
    g = new_game(3)
    assert total_cards(g) == 48
    assert all(len(p.hand) + 4 * len(p.books) == 7 for p in g.players)
    g = new_game(5)
    assert all(len(p.hand) + 4 * len(p.books) == 5 for p in g.players)


def test_rule_errors():
    g = new_game()
    i = g.current
    missing = next(v for v in range(1, 13) if not g.players[i].count(v))
    with pytest.raises(RuleError):
        g.ask(i, (i + 1) % 3, missing)
    with pytest.raises(RuleError):
        g.ask(i, i, next(iter(g.players[i].values())))
    with pytest.raises(RuleError):
        g.ask((i + 1) % 3, i, 1)


def test_giving_cards_keeps_the_turn_and_makes_books():
    g = new_game(2)
    me, other = g.current, 1 - g.current
    g.players[me].hand = [number(c, 7) for c in COLORS[:3]] + [number(COLORS[0], 2)]
    g.players[other].hand = [number(COLORS[3], 7), number(COLORS[1], 9)]
    assert g.ask(me, other, 7) is True
    assert 7 in g.players[me].books and g.current == me
    assert not any(c.value == 7 for p in g.players for c in p.hand)


def test_go_fish_passes_the_turn_unless_lucky():
    g = new_game(2)
    me, other = g.current, 1 - g.current
    g.players[me].hand = [number(COLORS[0], 5)]
    g.players[other].hand = [number(COLORS[0], 9)]
    g.pond = [number(COLORS[2], 1)]
    assert g.ask(me, other, 5) is False and g.current == other
    g = new_game(2)
    me, other = g.current, 1 - g.current
    g.players[me].hand = [number(COLORS[0], 5)]
    g.players[other].hand = [number(COLORS[0], 9)]
    g.pond = [number(COLORS[2], 1), number(COLORS[1], 5)]
    assert g.ask(me, other, 5) is True and g.current == me


@pytest.mark.parametrize("difficulty", ["Easy", "Medium", "Hard", "Expert"])
def test_ai_games_finish_with_all_books(difficulty):
    for seed in range(15):
        n = 2 + seed % 5
        g = GoFishGame([FishPlayer(str(i)) for i in range(n)], random.Random(seed))
        ais = [GoFishAI(difficulty, random.Random(seed + i)) for i in range(n)]
        for _ in range(3000):
            if g.game_over:
                break
            i = g.current
            g.ask(i, *ais[i].choose_ask(g, i))
        assert g.game_over and g.books_made() == 12 and not g.pond
        assert sorted(v for p in g.players for v in p.books) == list(range(1, 13))


def test_smarter_ai_wins_more():
    wins = {"Easy": 0, "Expert": 0}
    for s in range(300):
        order = ["Easy", "Easy", "Expert", "Expert"] if s % 2 else ["Expert", "Expert", "Easy", "Easy"]
        g = GoFishGame([FishPlayer(str(i)) for i in range(4)], random.Random(s))
        ais = [GoFishAI(d, random.Random(s * 9 + i)) for i, d in enumerate(order)]
        while not g.game_over:
            i = g.current
            g.ask(i, *ais[i].choose_ask(g, i))
        for w in g.winners():
            wins[order[w]] += 1
    assert wins["Expert"] > wins["Easy"] * 1.5
