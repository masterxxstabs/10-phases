"""Profiles (pictures, hover backgrounds, name colours) and levels."""

import json
from types import SimpleNamespace

import pygame
import pytest

from ten_phases import levels, profile
from ten_phases.levels import level_for, progress, total_for, xp_to_next
from ten_phases.settings import Settings


def test_level_curve():
    assert level_for(0) == 1 and level_for(99) == 1 and level_for(100) == 2
    assert xp_to_next(1) == 100 and xp_to_next(2) == 125
    for n in range(2, levels.MAX_LEVEL + 1):
        assert level_for(total_for(n)) == n and level_for(total_for(n) - 1) == n - 1
    assert level_for(10 ** 9) == levels.MAX_LEVEL
    assert progress(150) == (2, 50, 125)
    assert progress(10 ** 9)[0] == levels.MAX_LEVEL


def test_buying_equipping_and_level_rewards():
    s = Settings()
    s.chip_bank = 160
    assert profile.owns(s, "avatar:robot") and profile.owns(s, "banner:classic")
    assert not profile.owns(s, "avatar:fox")
    with pytest.raises(profile.ProfileError):
        profile.equip(s, "avatar:fox")
    profile.buy(s, "avatar:fox")
    assert s.chip_bank == 10 and s.avatar == "fox" and "avatar:fox" in s.owned_items
    with pytest.raises(profile.ProfileError):
        profile.buy(s, "avatar:owl")                       # can't afford
    profile.buy(s, "avatar:fox")                           # already owned: just equips, free
    assert s.chip_bank == 10
    with pytest.raises(profile.ProfileError):
        profile.buy(s, "avatar:star")                      # a level reward, not for sale
    with pytest.raises(profile.ProfileError):
        profile.set_color(s, "GOLD")
    s.xp = total_for(10)
    assert profile.owns(s, "avatar:star")
    profile.equip(s, "avatar:star")
    profile.set_color(s, "GOLD")
    assert s.avatar == "star" and s.name_color == "GOLD"
    with pytest.raises(profile.ProfileError):
        profile.set_color(s, "RAINBOW")
    with pytest.raises(profile.ProfileError):
        profile.buy(s, "avatar:nope")


def test_settings_keep_profile_items_and_reject_junk(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"owned_items": ["avatar:fox", "banner:gold", "avatar:hacked"], "avatar": "fox",
                                "banner": "lava", "name_color": "RAINBOW", "xp": -5}))
    s = Settings.load(path)
    assert "avatar:fox" in s.owned_items and "banner:gold" in s.owned_items and "avatar:hacked" not in s.owned_items
    assert s.avatar == "fox"
    assert s.banner == "classic"            # not owned
    assert s.name_color == "WHITE"          # rainbow needs level 20
    assert s.xp == 0
    s.save(path)
    assert Settings.load(path).avatar == "fox"


def test_profiles_from_the_network_are_cleaned():
    assert profile.clean_profile(None) == {"a": "robot", "b": "classic", "c": "WHITE", "l": 1}
    assert profile.clean_profile({"a": "dragon", "b": "gold", "c": "LIME", "l": 42}) == \
        {"a": "dragon", "b": "gold", "c": "LIME", "l": 42}
    junk = profile.clean_profile({"a": 5, "b": "<script>", "c": [], "l": 10 ** 9})
    assert junk == {"a": "robot", "b": "classic", "c": "WHITE", "l": levels.MAX_LEVEL}
    assert profile.clean_profile({"l": True})["l"] == 1
    assert profile.ai_profile("ZOE") == profile.ai_profile("ZOE")   # the same every time
    assert profile.player_profile(SimpleNamespace(name="ZOE")) == profile.ai_profile("ZOE")


def test_every_picture_and_background_draws(app):
    from ten_phases.ui import profile_art
    surf = pygame.Surface((400, 300))
    for k, a in enumerate(profile.AVATARS):
        for r in (11, 24, 72):
            profile_art.avatar(surf, (200, 150), r, {"a": a.style, "l": 5}, k, level=True)
    for b in profile.BANNERS:
        profile_art.panel(surf, (10, 10, 380, 200), b.style, 1.3)
    for name, _, _ in profile.NAME_COLORS:
        assert len(profile_art.name_rgb({"c": name}, 2.0)) == 3


# --------------------------------------------------------------------------- XP at the table


class FakeScene:
    def __init__(self, app):
        self.app = app


def ev(kind, player=0, **kw):
    return SimpleNamespace(kind=kind, player=player, **kw)


def test_xp_for_your_own_moves_round_and_game(app):
    from ten_phases.ui.xp import XpTracker
    app.settings.xp = 0
    xp = XpTracker(FakeScene(app), "phases")
    xp.event(ev("discard"))
    xp.event(ev("discard", player=2))               # someone else's move: nothing
    xp.event(ev("lay"))
    assert app.settings.xp == 2 + 25
    xp.round_end(1, went_out=True)
    xp.round_end(1, went_out=True)                  # once per round
    assert app.settings.xp == 27 + 30
    xp.game_end(won=True)
    xp.game_end(won=True)                           # once per game
    assert app.settings.xp == 57 + 150 and xp.earned == 207
    assert xp.toast and xp.toast[0] == 2            # 207 XP: level 2 (level 3 takes 225)
    surf = pygame.Surface((1280, 800))
    xp.update(0.1)
    xp.draw(surf)


def test_xp_special_cases(app):
    from ten_phases.ui.xp import XpTracker
    app.settings.xp = 0
    bj = XpTracker(FakeScene(app), "blackjack")
    bj.event(ev("settle", result="blackjack"))
    bj.event(ev("settle", player=1, result="win"))
    assert app.settings.xp == 15
    mono = XpTracker(FakeScene(app), "monopoly")
    mono.event(ev("pay", player=None, text="passed GO", data={"to": 0}))
    mono.event(ev("rent", player=2, data={"owner": 0}))           # someone paid YOU rent
    mono.event(ev("trade_done", player=1, data={"accepted": True, "from": 1, "to": 0}))
    mono.event(ev("buy", data={}))
    assert app.settings.xp == 15 + 5 + 3 + 5 + 10


def test_xp_is_saved_when_leaving_a_table(app, tmp_path):
    from ten_phases.ui.game_scene import GameScene
    from ten_phases.ui.menus import MenuScene
    import ten_phases.settings as settings_module
    scene = GameScene(app)
    app.go(scene)
    app.settings.xp = 0
    scene.xp.gain(7)
    app.go(MenuScene(app))
    assert Settings.load(settings_module.SETTINGS_PATH).xp == 7


def test_playing_a_game_earns_xp_and_levels(app):
    from ten_phases.ui.gofish_scene import GoFishScene
    app.settings.xp = 0
    scene = GoFishScene(app)
    app.go(scene)
    scene.splash = None
    for _ in range(5000):
        scene.update(0.2)
        if scene.overlay == "game":
            break
        if scene.my_turn:
            scene.do_hint()
            target, value = scene.hint_ai.choose_ask(scene.game, 0)
            scene.ask(target)
        scene.draw(app.screen)
    assert scene.overlay == "game"
    assert app.settings.xp >= levels.GAME_XP and scene.xp.game_done
    scene.draw(app.screen)


# --------------------------------------------------------------------------- screens


def test_profile_screen_and_menu_card(app):
    from ten_phases.ui.menus import PROFILE_CARD, MenuScene
    from ten_phases.ui.profile_scene import ProfileScene
    s = app.settings
    s.xp, s.avatar, s.name_color = 0, "robot", "WHITE"
    menu = MenuScene(app)
    app.go(menu)
    menu.draw(app.screen)
    menu.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=PROFILE_CARD.center))
    scene = app.scene
    assert isinstance(scene, ProfileScene)

    def click(k):
        pos = scene.tile_rect(k).center
        scene.handle(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos))
    click(2)                                        # the cat: free
    assert s.avatar == "cat"
    click(len(profile.AVATARS) - 1)                 # level 25 reward: locked
    assert s.avatar == "cat" and scene.flash
    scene._set_tab("BACKGROUNDS")
    click(3)
    assert s.banner == "sunset"
    scene._set_tab("NAME COLOR")
    click(4)
    assert s.name_color == "PINK"
    scene.name.value = "ace!!"
    scene.draw(app.screen)
    scene._done()
    assert s.player_name == "ACE"


def test_buying_in_the_shop(app):
    from ten_phases.ui.shop_scene import ShopScene
    s = app.settings
    s.chip_bank = 500
    s.owned_items = [i for i in s.owned_items if i != "avatar:panda"]
    shop = ShopScene(app, tab="PICTURES")
    app.go(shop)
    panda = next(k for k, item in enumerate(shop.skins()) if item.style == "panda")
    pos = shop.tile_rect(panda).center
    up = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos)
    shop.handle(up)
    assert s.chip_bank == 500 and s.avatar != "panda"     # first click asks
    shop.draw(app.screen)
    shop.handle(up)
    assert s.chip_bank == 350 and s.avatar == "panda" and "avatar:panda" in s.owned_items
    shop._set_tab("BACKGROUNDS")
    shop.draw(app.screen)


# --------------------------------------------------------------------------- multiplayer


@pytest.mark.parametrize("game_name", ["10 PHASES", "POKER", "MONOPOLY"])
def test_everyone_sees_everyone_elses_profile(game_name):
    from ten_phases.net.client import ClientSession
    from ten_phases.net.host import HostServer
    from test_net import wait_for

    server = HostServer("HOSTY", port=0, announce=False, game=game_name)
    server.profile = profile.clean_profile({"a": "king", "b": "gold", "c": "LIME", "l": 30})
    try:
        guest = ClientSession("ANA", "127.0.0.1", server.port, server.key,
                              profile={"a": "koi", "b": "galaxy", "c": "PINK", "l": 7})
        other = ClientSession("BO", "127.0.0.1", server.port, server.key, profile={"a": "??", "l": "x"})

        def pump_all():
            server.pump()
            guest.poll()
            other.poll()
        assert wait_for(lambda: guest.status == other.status == "joined" and len(guest.members) == 3, pump_all)
        lobby = {m["name"]: m["prof"] for m in guest.members}
        assert lobby["HOSTY"]["a"] == "king" and lobby["ANA"]["b"] == "galaxy" and lobby["BO"]["a"] == "robot"
        server.set_ai_count(1)
        session = server.start_game()
        assert wait_for(lambda: other.game is not None and other.game.players, pump_all)
        seen = {p.name: profile.player_profile(p) for p in other.game.players}
        real = {p.name: profile.player_profile(p) for p in session.game.players}
        assert seen == real
        assert seen["HOSTY"]["c"] == "LIME" and seen["ANA"]["l"] == 7 and seen["BO"] == profile.clean_profile(None)
    finally:
        server.close()


def test_lobby_rows_draw_profiles(app):
    from ten_phases.net.host import HostServer
    from ten_phases.ui.multiplayer import HostLobbyScene
    server = HostServer("HOSTY", port=0, announce=False)
    try:
        server.set_ai_count(3)
        scene = HostLobbyScene(app, server)
        scene.update(0.1)
        scene.draw(app.screen)
    finally:
        server.close()


def test_computers_have_varied_profiles():
    names = [f"BOT{k}" for k in range(30)]
    profs = [profile.ai_profile(n) for n in names]
    assert len({p["a"] for p in profs}) > 5 and len({p["b"] for p in profs}) > 5
    assert all(1 <= p["l"] <= 30 for p in profs)


def test_dev_tag_for_shawn_in_any_capitalisation(app):
    from ten_phases.ui import profile_art
    s = app.settings
    for name in ("shawn", "SHAWN", "Shawn", " sHaWn "):
        s.player_name = name
        assert profile.my_profile(s).get("d") is True
    s.player_name = "SHAUN"
    assert "d" not in profile.my_profile(s)
    assert profile.player_profile(SimpleNamespace(name="Shawn", is_human=True, profile=None))["d"] is True
    assert "d" not in profile.player_profile(SimpleNamespace(name="SHAWN", is_human=False, profile=None))
    # A tag sent over the network means nothing: only the name counts.
    assert "d" not in profile.clean_profile({"d": True})
    assert "d" not in profile.player_profile(SimpleNamespace(name="BO", is_human=True, profile={"d": True}))
    surf = pygame.Surface((300, 60))
    r = profile_art.name_tag(surf, pygame.Rect(10, 10, 80, 20), {"d": True})
    assert r.w > 80
    s.player_name = "PLAYER"
