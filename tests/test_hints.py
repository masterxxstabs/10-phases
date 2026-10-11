"""The planner behind the Hint button must agree with an exhaustive check."""

import random

from exact_planner import exact_deficit
from ten_phases.ai import AIPlayer, build_groups, plan_phase
from ten_phases.cards import COLORS, Color, number, skip, wild
from ten_phases.game import Game, Player
from ten_phases.phases import PHASES, match_groups


def tricky_hand(rng):
    lo = rng.randint(1, 9)
    hi = min(12, lo + rng.randint(1, 5))
    cols = rng.sample(COLORS, rng.randint(1, 4))
    hand = []
    for _ in range(rng.choice([10, 11])):
        r = rng.random()
        hand.append(wild() if r < 0.12 else skip() if r < 0.15 else number(rng.choice(cols), rng.randint(lo, hi)))
    return hand


def test_planner_matches_exhaustive_check():
    rng = random.Random(42)
    for phase in range(10):
        for _ in range(150):
            hand = tricky_hand(rng)
            plan = plan_phase(PHASES[phase], hand)
            assert plan.deficit == exact_deficit(PHASES[phase], hand), (phase + 1, [c.label() for c in hand])
            if plan.complete:
                assert match_groups(PHASES[phase], build_groups(plan)) is not None


def test_same_number_can_be_split_between_two_sets():
    # Phase 9: set of 5 + set of 2 from five 4s and wilds -> 4444W and 4W.
    hand = [number(Color.BLUE, 4)] * 3 + [number(Color.GREEN, 4)] * 2 + [wild()] * 4 + [skip()]
    hand = [number(c.color, c.value) if c.is_number else c for c in hand]
    plan = plan_phase(PHASES[8], hand)
    assert plan.complete
    assert match_groups(PHASES[8], build_groups(plan)) is not None


def test_hint_discard_never_costs_phase_progress():
    """Play real games; whenever the hint says discard, it must be one of the cards that
    keeps you closest to your phase (the opponent AI may trade progress for defence; the hint must not)."""
    for seed in range(2):
        rng = random.Random(seed)
        g = Game([Player("YOU", is_human=True)] + [Player(f"A{i}", difficulty="Hard") for i in range(3)], rng)
        ais = {i: AIPlayer("Hard", random.Random(seed * 10 + i)) for i in range(4)}
        hint = AIPlayer("Expert", random.Random(0), advisor=True)
        for _ in range(1500):
            if g.game_over:
                break
            if g.round_over:
                g.next_round()
                continue
            i = g.current
            me = g.players[0]
            if i == 0 and not g.has_drawn and not me.laid_down and g.top_discard and not g.top_discard.is_skip:
                reqs, top = me.requirements, g.top_discard
                now = exact_deficit(reqs, me.hand)
                after = min(exact_deficit(reqs, [c for c in me.hand + [top] if c is not d]) for d in me.hand)
                assert hint.next_action(g, 0) == ("draw", "discard" if after < now else "deck")
            if i == 0 and g.has_drawn and not me.laid_down:
                a = hint.next_action(g, 0)
                reqs = me.requirements
                if exact_deficit(reqs, me.hand) == 0:
                    assert a[0] == "lay"
                if a[0] == "discard":
                    best = min(exact_deficit(reqs, [c for c in me.hand if c is not d]) for d in me.hand)
                    assert exact_deficit(reqs, [c for c in me.hand if c is not a[1]]) == best
            a = ais[i].next_action(g, i)
            if a[0] == "draw":
                (g.draw_from_deck if a[1] == "deck" else g.draw_from_discard)(i)
            elif a[0] == "lay":
                g.lay_down(i, a[1])
            elif a[0] == "hit":
                g.hit(i, a[1], a[2])
            else:
                g.discard(i, a[1], a[2])
