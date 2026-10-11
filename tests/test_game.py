import random

import pytest

from ten_phases.ai import AIPlayer, build_groups, plan_phase
from ten_phases.cards import Color, number, skip, wild
from ten_phases.game import Game, Player, RuleError
from ten_phases.phases import PHASES


def new_game(n=2, seed=1):
    return Game([Player(f"P{i}") for i in range(n)], random.Random(seed))


def test_deal():
    g = new_game(4)
    assert all(len(p.hand) == 10 for p in g.players)
    assert len(g.discard_pile) == 1
    assert len(g.deck) == 108 - 41


def test_must_draw_before_discarding():
    g = new_game()
    i = g.current
    with pytest.raises(RuleError):
        g.discard(i, g.players[i].hand[0])
    g.draw_from_deck(i)
    with pytest.raises(RuleError):
        g.draw_from_deck(i)
    g.discard(i, g.players[i].hand[0])
    assert g.current != i


def test_lay_down_hit_and_go_out():
    g = new_game()
    i = g.current
    p = g.players[i]
    sets = [number(Color.RED, 4), number(Color.BLUE, 4), wild(), number(Color.RED, 8), number(Color.GREEN, 8),
            number(Color.YELLOW, 8)]
    extra = number(Color.GREEN, 4)
    p.hand = sets + [extra]
    g.draw_from_deck(i)
    drawn = p.hand[-1]
    g.lay_down_auto(i, sets)
    assert p.laid_down and len(g.melds) == 2
    four_meld = next(m for m in g.melds if any(c.value == 4 for c in m.cards if c.is_number))
    g.hit(i, extra, four_meld.id)
    assert p.hand == [drawn]
    g.discard(i, drawn, None)
    assert g.round_over
    assert p.phase == 1
    assert g.round_points[i] == 0


def test_skip_makes_player_lose_turn():
    g = new_game(3)
    i = g.current
    p = g.players[i]
    s = skip()
    p.hand.append(s)
    g.draw_from_deck(i)
    target = (i + 1) % 3
    g.discard(i, s, target)
    assert g.current == (i + 2) % 3


def test_cannot_take_skip_from_discard():
    g = new_game()
    g.discard_pile.append(skip())
    with pytest.raises(RuleError):
        g.draw_from_discard(g.current)


def test_plan_finds_complete_phase():
    hand = [number(Color.RED, 2), number(Color.BLUE, 3), wild(), number(Color.GREEN, 5),
            number(Color.RED, 11), number(Color.BLUE, 11), number(Color.GREEN, 11), number(Color.RED, 7)]
    plan = plan_phase(PHASES[1], hand)
    assert plan.complete
    groups = build_groups(plan)
    g = new_game()
    i = g.current
    g.players[i].hand = hand
    g.players[i].phase = 1
    g.draw_from_deck(i)
    g.lay_down(i, groups)


@pytest.mark.parametrize("difficulty", ["Easy", "Medium", "Hard", "Expert"])
def test_ai_plays_a_full_game(difficulty):
    rng = random.Random(7)
    players = [Player(str(i), difficulty=difficulty) for i in range(3)]
    g = Game(players, rng)
    ais = [AIPlayer(difficulty, random.Random(i)) for i in range(3)]
    for _ in range(20000):
        if g.game_over:
            break
        if g.round_over:
            g.next_round()
            continue
        i = g.current
        a = ais[i].next_action(g, i)
        if a[0] == "draw":
            (g.draw_from_deck if a[1] == "deck" else g.draw_from_discard)(i)
        elif a[0] == "lay":
            g.lay_down(i, a[1])
        elif a[0] == "hit":
            g.hit(i, a[1], a[2])
        else:
            g.discard(i, a[1], a[2])
    assert g.game_over
    assert sum(len(p.hand) for p in g.players) + len(g.deck) + len(g.discard_pile) + \
        sum(len(m.cards) for m in g.melds) == 108


def test_pot_goes_to_player_who_goes_out():
    g = new_game(3)
    assert g.pot == 3 and all(p.chips == 23 for p in g.players)
    i = g.current
    p = g.players[i]
    p.hand = [number(Color.RED, 4)]
    g.draw_from_deck(i)
    p.hand = [p.hand[-1]]
    g.discard(i, p.hand[0])
    assert g.round_over and g.pot == 0
    assert p.chips == 26 and g.round_chips[i] == 2
