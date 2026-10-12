import random

import pytest

from ten_phases.blackjack.ai import BlackjackAI, basic_strategy, hint
from ten_phases.blackjack.engine import BJPlayer, BlackjackGame, RuleError, bj_card, hand_value, is_blackjack
from ten_phases.cards import COLORS

R, B = COLORS[0], COLORS[1]


def cards(*values):
    return [bj_card(R, v) for v in values]


def test_hand_values():
    assert hand_value(cards(1, 6)) == (17, True)
    assert hand_value(cards(1, 6, 10)) == (17, False)
    assert hand_value(cards(1, 1, 9)) == (21, True)
    assert hand_value(cards(13, 12)) == (20, False)
    assert is_blackjack(cards(1, 12)) and not is_blackjack(cards(10, 5, 6))


def test_basic_strategy_chart():
    assert basic_strategy(cards(10, 6), 10, True, False)[0] == "hit"
    assert basic_strategy(cards(10, 6), 6, True, False)[0] == "stand"
    assert basic_strategy(cards(6, 5), 6, True, False)[0] == "double"
    assert basic_strategy(cards(6, 5), 6, False, False)[0] == "hit"
    assert basic_strategy(cards(8, 8), 10, True, True)[0] == "split"
    assert basic_strategy(cards(10, 10), 6, True, True)[0] == "stand"
    assert basic_strategy(cards(1, 7), 9, True, False)[0] == "hit"     # soft 18 vs 9
    assert basic_strategy(cards(1, 7), 7, True, False)[0] == "stand"


def rigged(players, shoe_top):
    """A game whose next cards come off the shoe in the given order."""
    g = BlackjackGame([BJPlayer(f"P{i}") for i in range(players)], random.Random(0))
    g.shoe = g.shoe[:-len(shoe_top)] + list(reversed(shoe_top))
    return g


def test_win_blackjack_bust_and_push_payouts():
    # Deal order: P0, dealer up, P0, dealer hole.
    g = rigged(1, [bj_card(R, 1), bj_card(B, 10), bj_card(R, 13), bj_card(B, 7)])
    g.place_bet(0, 10)
    assert g.phase == "settled"                  # player blackjack, dealer 17: nothing left to play
    h = g.players[0].hands[0]
    assert h.result == "blackjack" and h.payout == 25 and g.players[0].chips == 65

    g = rigged(1, [bj_card(R, 10), bj_card(B, 10), bj_card(R, 6), bj_card(B, 7), bj_card(R, 9)])
    g.place_bet(0, 5)
    g.hit(0)
    assert g.players[0].hands[0].result == "bust" and g.players[0].chips == 45

    g = rigged(1, [bj_card(R, 10), bj_card(B, 10), bj_card(R, 8), bj_card(B, 8)])
    g.place_bet(0, 5)
    g.stand(0)
    assert g.players[0].hands[0].result == "push" and g.players[0].chips == 50


def test_double_and_split():
    g = rigged(1, [bj_card(R, 6), bj_card(B, 10), bj_card(R, 5), bj_card(B, 7), bj_card(R, 10)])
    g.place_bet(0, 5)
    g.double(0)
    h = g.players[0].hands[0]
    assert h.doubled and h.bet == 10 and h.result == "win" and g.players[0].chips == 60

    g = rigged(1, [bj_card(R, 8), bj_card(B, 10), bj_card(B, 8), bj_card(B, 9), bj_card(R, 3), bj_card(R, 2)])
    g.place_bet(0, 5)
    assert "split" in g.legal_actions(0)
    g.split(0)
    assert len(g.players[0].hands) == 2 and g.players[0].chips == 40
    with pytest.raises(RuleError):
        g.split(0)


def test_bets_are_checked():
    g = BlackjackGame([BJPlayer("A"), BJPlayer("B")], random.Random(1))
    with pytest.raises(RuleError):
        g.place_bet(0, 11)
    with pytest.raises(RuleError):
        g.place_bet(0, 0)
    g.place_bet(0, 3)
    with pytest.raises(RuleError):
        g.place_bet(0, 3)
    assert g.phase == "betting"   # still waiting for B
    g.place_bet(1, 2)
    assert g.phase in ("playing", "settled")


def test_chips_are_conserved_and_games_finish():
    for seed in range(10):
        diffs = ["Easy", "Medium", "Hard", "Expert"][: 1 + seed % 4]
        g = BlackjackGame([BJPlayer(d) for d in diffs], random.Random(seed))
        ais = [BlackjackAI(d, random.Random(seed + i)) for i, d in enumerate(diffs)]
        for _ in range(5000):
            if g.game_over:
                break
            if g.phase == "betting":
                for i in g.waiting_for_bets():
                    g.place_bet(i, ais[i].choose_bet(g, i))
            elif g.phase == "playing":
                i = g.turn[0]
                if i == 0:
                    action, reason = hint(g, i)
                    assert action in g.legal_actions(i) and reason
                getattr(g, ais[i].choose_action(g, i))(i)
            else:
                g.next_round()
        assert g.game_over
        for p in g.players:
            assert p.chips == 50 + p.net and p.chips >= 0
