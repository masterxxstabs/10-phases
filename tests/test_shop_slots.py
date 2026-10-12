import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest  # noqa: E402

from ten_phases import shop, skins  # noqa: E402
from ten_phases.settings import Settings  # noqa: E402
from ten_phases.slots.engine import SlotMachine, payout, return_to_player  # noqa: E402
from ten_phases.slots.engine import CHERRY, JACKPOT, LEMON, SEVEN, WILD  # noqa: E402


def test_packs_cost_chips_and_fill_the_collection(tmp_path):
    s = Settings(chip_bank=100)
    with pytest.raises(shop.ShopError, match="more chips"):
        shop.buy_pack(s, "premium")
    pulls = shop.buy_pack(s, "basic", random.Random(1))
    assert len(pulls) == 3
    assert s.chip_bank == 100 - 75 + sum(p.refund for p in pulls)
    for p in pulls:
        assert not p.skin.free and shop.owns(s, p.skin.id)
    with pytest.raises(shop.ShopError):
        shop.equip(s, next(sk.id for sk in skins.IN_PACKS if not shop.owns(s, sk.id)))
    skin = pulls[0].skin
    shop.equip(s, skin.id)
    path = tmp_path / "s.json"
    s.save(path)
    loaded = Settings.load(path)
    assert skin.id in loaded.owned_items and shop.equipped(loaded, skin)


def test_duplicates_pay_out_and_free_skins_never_drop():
    rng = random.Random(7)
    owned = {s.id for s in skins.IN_PACKS}
    for pack in shop.PACKS:
        for _ in range(50):
            pulls = shop.open_pack(pack, owned, rng)
            assert all(not p.new and p.refund == skins.DUPLICATE_CHIPS[p.skin.rarity] for p in pulls)
    for pack in shop.PACKS:
        for _ in range(200):
            for p in shop.open_pack(pack, set(), rng):
                assert not p.skin.free


def test_pack_guarantees():
    rng = random.Random(3)
    rank = {r: k for k, r in enumerate(skins.RARITIES)}
    for _ in range(300):
        assert rank[shop.open_pack(shop.PACK_BY_ID["premium"], set(), rng)[-1].skin.rarity] >= rank["RARE"]
        assert rank[shop.open_pack(shop.PACK_BY_ID["legendary"], set(), rng)[-1].skin.rarity] >= rank["EPIC"]
    odds = shop.odds_percent(shop.PACK_BY_ID["legendary"])
    assert odds["EPIC"] > 50 and 0 < odds["LEGENDARY"] < 100


def test_catalogue_is_big_unique_and_stable():
    assert len(skins.SKINS) > 250
    assert len({s.id for s in skins.SKINS}) == len(skins.SKINS)
    assert len({(s.kind, s.name) for s in skins.SKINS}) == len(skins.SKINS)
    assert {"face:koi", "back:koi"} <= set(skins.BY_ID)
    assert sum("foil" in s.blurb.lower() for s in skins.SKINS) >= 80
    # Generated skins must come out the same on every machine (multiplayer depends on it).
    assert skins.gen_spec("back", 5) == skins.gen_spec("back", 5)
    assert skins.BY_ID["face:g000"].name == skins._generated()[0].name


def test_settings_reject_unowned_or_unknown_skins(tmp_path):
    path = tmp_path / "s.json"
    path.write_text('{"face_style": "gold", "owned_items": ["face:fake", 3, ["x"]], "back_style": "galaxy"}')
    s = Settings.load(path)
    assert s.face_style == "classic" and s.back_style == "classic"
    assert set(s.owned_items) == set(skins.FREE_IDS)


def test_network_skins_are_sanitised():
    assert skins.clean_skin(["neon", "galaxy"]) == ("neon", "galaxy")
    assert skins.clean_skin(["future-skin", 3]) == ("classic", "classic")
    assert skins.clean_skin(None) == ("classic", "classic")


def test_every_skin_renders_every_card(app_surface):
    from ten_phases.blackjack.engine import bj_card
    from ten_phases.cards import COLORS, number, skip, wild
    from ten_phases.ui.card_art import card_with_shadow

    cards = [number(COLORS[0], 7), number(COLORS[3], 12), wild(), skip(), bj_card(COLORS[1], 13), None]
    for item in skins.SKINS:
        for c in (cards if item.kind == "face" else [None]):
            kw = {"face": item.style} if item.kind == "face" else {"back": item.style}
            img, _ = card_with_shadow(c, 60, 90, **kw)
            assert img.get_width() > 60
    for c in cards:   # unknown styles (from a newer version) still draw
        card_with_shadow(c, 60, 90, face="zz-new", back="zz-new")


def test_slot_payouts_and_return():
    assert payout((JACKPOT,) * 3)[0] == 300
    assert payout((WILD, WILD, WILD))[0] == 100
    assert payout((SEVEN, WILD, SEVEN))[0] == 25
    assert payout((JACKPOT, WILD, JACKPOT))[0] == 0        # wild never completes the jackpot
    assert payout((CHERRY, LEMON, CHERRY))[0] == 2
    assert payout((CHERRY, LEMON, SEVEN))[0] == 1
    assert payout((LEMON, CHERRY, SEVEN))[0] == 0
    assert 0.94 <= return_to_player() <= 0.96


def test_spins_use_the_reel_mix():
    m = SlotMachine(random.Random(3))
    bet = win = 0
    for _ in range(60000):
        s = m.spin(5)
        bet, win = bet + 5, win + s.win
    assert 0.90 < win / bet < 1.00


@pytest.fixture
def app_surface():
    import pygame
    pygame.init()   # card art only needs fonts, not a window (the UI tests own the window)
    return True
