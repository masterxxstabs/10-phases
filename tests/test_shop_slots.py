import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest  # noqa: E402

from ten_phases import shop  # noqa: E402
from ten_phases.settings import Settings  # noqa: E402
from ten_phases.slots.engine import SlotMachine, payout, return_to_player  # noqa: E402
from ten_phases.slots.engine import CHERRY, JACKPOT, LEMON, SEVEN, WILD  # noqa: E402


def test_buying_and_equipping(tmp_path):
    s = Settings(chip_bank=100)
    with pytest.raises(shop.ShopError, match="more chips"):
        shop.buy(s, "face:gold")
    shop.buy(s, "back:checker")
    assert s.chip_bank == 50 and shop.owns(s, "back:checker")
    with pytest.raises(shop.ShopError):
        shop.buy(s, "back:checker")
    with pytest.raises(shop.ShopError):
        shop.equip(s, "face:neon")
    shop.equip(s, "back:checker")
    assert s.back_style == "checker"
    path = tmp_path / "s.json"
    s.save(path)
    loaded = Settings.load(path)
    assert loaded.back_style == "checker" and "back:checker" in loaded.owned_items and loaded.chip_bank == 50


def test_settings_reject_unowned_or_unknown_skins(tmp_path):
    path = tmp_path / "s.json"
    path.write_text('{"face_style": "gold", "owned_items": ["face:fake", 3], "back_style": "galaxy"}')
    s = Settings.load(path)
    assert s.face_style == "classic" and s.back_style == "classic"
    assert s.owned_items == ["back:classic", "face:classic"]


def test_every_skin_renders_every_card(app_surface):
    from ten_phases.blackjack.engine import bj_card
    from ten_phases.cards import COLORS, number, skip, wild
    from ten_phases.ui.card_art import card_with_shadow

    cards = [number(COLORS[0], 7), number(COLORS[3], 12), wild(), skip(), bj_card(COLORS[1], 13), None]
    for item in shop.ITEMS:
        for c in cards:
            kw = {"face": item.style} if item.kind == "face" else {"back": item.style}
            img, _ = card_with_shadow(c, 60, 90, **kw)
            assert img.get_width() > 60


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
