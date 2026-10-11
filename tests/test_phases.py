from ten_phases.cards import Color, number, skip, wild
from ten_phases.phases import PHASES, GroupType, arrange_run, is_valid_group, partition_for_phase

R, B, G, Y = Color.RED, Color.BLUE, Color.GREEN, Color.YELLOW


def test_set_with_wild():
    assert is_valid_group(GroupType.SET, [number(R, 7), number(B, 7), wild()], 3)
    assert not is_valid_group(GroupType.SET, [number(R, 7), number(B, 8), wild()], 3)


def test_group_needs_a_natural_and_no_skips():
    assert not is_valid_group(GroupType.SET, [wild(), wild(), wild()], 3)
    assert not is_valid_group(GroupType.SET, [number(R, 7), number(B, 7), skip()], 3)


def test_runs():
    assert is_valid_group(GroupType.RUN, [number(R, v) for v in (3, 4, 5, 6)], 4)
    assert is_valid_group(GroupType.RUN, [number(R, 3), wild(), number(B, 5), number(G, 6)], 4)
    assert not is_valid_group(GroupType.RUN, [number(R, 3), number(B, 3), number(G, 4), number(Y, 5)], 4)
    assert not is_valid_group(GroupType.RUN, [number(R, 1), number(B, 2), number(G, 9)], 3)
    # A run can't go past 12
    assert not is_valid_group(GroupType.RUN, [number(R, 12)] + [wild()] * 12, 4)


def test_arrange_run_places_wilds_in_gaps():
    w = wild()
    cards = [number(R, 5), w, number(B, 3), number(G, 6)]
    arranged = arrange_run(cards)
    assert [v for _, v in arranged] == [3, 4, 5, 6]
    assert arranged[1][0] is w


def test_color_group():
    assert is_valid_group(GroupType.COLOR, [number(R, v) for v in (1, 1, 4, 9, 10, 11)] + [wild()], 7)
    assert not is_valid_group(GroupType.COLOR, [number(R, 1)] * 6 + [number(B, 2)], 7)


def test_partition_set_and_run():
    cards = [number(R, 9), number(B, 9), wild(), number(R, 2), number(G, 3), number(Y, 4), number(B, 5)]
    split = partition_for_phase(PHASES[1], cards)
    assert split is not None
    assert sorted(r.type.value for r, _ in split) == ["run", "set"]


def test_partition_rejects_incomplete():
    cards = [number(R, 9), number(B, 9), number(R, 2), number(G, 3), number(Y, 4), number(B, 5)]
    assert partition_for_phase(PHASES[0], cards) is None
