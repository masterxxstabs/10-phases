import random

from ten_phases.names import AI_NAMES, pick_ai_names


def test_pool_is_big_unique_and_fits_the_boxes():
    assert len(AI_NAMES) >= 60
    assert len(set(AI_NAMES)) == len(AI_NAMES)
    assert all(n.isalpha() and n.isupper() and len(n) <= 7 for n in AI_NAMES)


def test_pick_avoids_taken_names_and_repeats():
    for seed in range(50):
        names = pick_ai_names(5, taken=["you", "Zach", "MAYA"], rng=random.Random(seed))
        assert len(names) == len(set(names)) == 5
        assert not {"YOU", "ZACH", "MAYA"} & set(names)


def test_games_get_different_casts():
    casts = {tuple(pick_ai_names(3, rng=random.Random(seed))) for seed in range(20)}
    assert len(casts) > 15
