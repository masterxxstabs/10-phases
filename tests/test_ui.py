"""Smoke tests for the pygame front end, run headless."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from ten_phases.cards import Color, number  # noqa: E402
from ten_phases.ui import sfx  # noqa: E402
from ten_phases.ui.game_scene import GameScene  # noqa: E402


def test_every_sound_builds():
    pygame.mixer.init(sfx.RATE, -16, 1, 512)
    sfx.init("Low")
    assert set(sfx._sounds) == set(sfx.recipes())
    for name in sfx.recipes():
        sfx.play(name)


def test_going_out_with_a_hit_keeps_the_table_drawable(app):
    """Going out by hitting moves the player up a phase immediately; the table must still
    show the groups of the phase that was just played."""
    scene = GameScene(app)
    g = scene.game
    scene.splash = None
    me = g.current
    p = g.players[me]
    sevens = [number(c, 7) for c in Color]
    run = [number(Color.BLUE, v) for v in (1, 2, 3, 4)]
    extra = number(Color.RED, 7)
    p.phase = 2  # set of 4 + run of 4; the next phase (run of 7) has only one group
    g.draw_from_deck(me)
    p.hand = sevens + run + [extra]
    g.lay_down(me, [sevens, run])
    set_meld = next(m for m in g.melds if m.owner == me and m.cards[0].value == 7)
    g.hit(me, extra, set_meld.id)
    assert g.round_over and p.phase == 3
    scene._consume_events()
    scene.draw(app.screen)
    assert scene.shown_phase(me) == 2
    for _ in range(60):
        scene.update(1 / 30)
    assert scene.overlay == "round"
    scene.draw(app.screen)


def test_every_look_option_renders(app):
    from ten_phases.ui import theme
    from ten_phases.ui.customize import CustomizeScene

    s = app.settings
    for table in theme.TABLE_PRESETS.values():
        for accent, back, palette in zip(theme.ACCENT_PRESETS, theme.CARD_BACK_PRESETS, theme.CARD_PALETTES):
            s.table_color = theme.rgb_to_hex(table)
            s.accent, s.card_back, s.card_palette = accent, back, palette
            theme.apply(s)
    s.text_style, s.sparkles = "Smooth", False
    s.table_color = theme.rgb_to_hex(theme.hue_color(0.3))
    theme.apply(s)
    scene = GameScene(app)
    scene.draw(app.screen)
    CustomizeScene(app).draw(app.screen)
    assert theme.PIXEL_TEXT is False and theme.BG == theme.hue_color(0.3)
    s.reset_look()
    theme.apply(s)
    assert theme.BG == theme.TABLE_PRESETS["Classic Blue"] and theme.PIXEL_TEXT


def test_look_settings_round_trip_and_bad_values(tmp_path):
    from ten_phases.settings import Settings

    path = tmp_path / "s.json"
    s = Settings(table_color="#123456", accent="Pink", text_style="Smooth", sparkles=False)
    s.save(path)
    loaded = Settings.load(path)
    assert (loaded.table_color, loaded.accent, loaded.text_style, loaded.sparkles) == ("#123456", "Pink", "Smooth", False)
    path.write_text('{"table_color": "blue", "text_style": "Comic"}')
    bad = Settings.load(path)
    assert bad.table_color == Settings().table_color and bad.text_style == "Pixel"


def test_menu_shows_version_and_each_update_state(app):
    from ten_phases import __version__
    from ten_phases.ui.menus import MenuScene
    from ten_phases.updater import UpdateInfo

    menu = MenuScene(app)
    up = app.updater
    up.info = UpdateInfo("9.9.9", "v9.9.9", ["Shiny new things", "Fixes"], "https://github.com", None, 1, None)
    for state in ("checking", "current", "failed", "downloading", "ready", "available"):
        up.state = state
        up.progress = 0.4
        menu.draw(app.screen)
        assert menu.btn_restart.visible == (state == "ready")
        assert menu.btn_get.visible == (state == "available")
    menu._later()
    menu.draw(app.screen)
    assert not menu.btn_restart.visible
    assert __version__
    up.state, up.info, up.dismissed = "idle", None, False


def test_pixel_font_is_bundled_and_used(app):
    from ten_phases.ui import theme

    assert theme.PIXEL_FONT_PATH.exists()
    assert theme._pixel_font(20) is not None


def test_chips_are_banked_once_when_a_game_ends(app):
    app.settings.chip_bank = 100
    scene = GameScene(app)
    scene.splash = None
    g = scene.game
    scene.human.chips = 31
    g.game_over, g.winner, g.went_out = True, 0, 0
    scene._set_overlay("game")
    scene._set_overlay("game")  # showing it again must not bank twice
    assert app.settings.chip_bank == 131 and scene._banked == 31
    scene.draw(app.screen)


def test_hovering_an_opponent_shows_their_info(app, monkeypatch):
    scene = GameScene(app)
    scene.splash = None
    g = scene.game
    seat = 1
    g.picked_from_discard[seat] = g.players[seat].hand[:2]
    scene.note(seat, "Drew from the deck")
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: scene.panel_rect(seat).center)
    calls = []
    original = scene._draw_player_info
    monkeypatch.setattr(scene, "_draw_player_info", lambda *a: (calls.append(a[1]), original(*a)))
    scene.draw(app.screen)
    assert calls == [seat]


def test_menu_switches_games_and_go_fish_plays(app):
    from ten_phases.ui.gofish_scene import GoFishScene
    from ten_phases.ui.menus import MenuScene

    app.settings.game = "10 PHASES"
    menu = MenuScene(app)
    menu.switch_game(1)
    assert menu.game == app.settings.game == "GO FISH"
    menu.draw(app.screen)
    menu._play()
    scene = app.scene
    assert isinstance(scene, GoFishScene)
    scene.splash = None
    bank = app.settings.chip_bank
    for _ in range(5000):
        scene.update(0.2)
        if scene.overlay == "game":
            break
        if scene.my_turn:
            scene.do_hint()
            target, value = scene.hint_ai.choose_ask(scene.game, 0)
            scene.ask(target)
        scene.draw(app.screen)
    assert scene.game.game_over and scene.overlay == "game"
    assert app.settings.chip_bank == bank + 5 * len(scene.me.books)
    from ten_phases.ui.menus import GAMES
    seen = [app.settings.game]
    for _ in range(len(GAMES)):
        menu.switch_game(1)
        seen.append(app.settings.game)
    assert seen[0] == seen[-1] == "GO FISH"          # a full lap wraps around
    assert sorted(set(seen)) == sorted(GAMES)
    menu.switch_game(-1)
    assert app.settings.game == GAMES[GAMES.index("GO FISH") - 1]
    app.settings.game = "10 PHASES"


def test_blackjack_plays_through_the_screen(app):
    from ten_phases.blackjack.ai import BlackjackAI
    from ten_phases.ui.blackjack_scene import BlackjackScene

    scene = BlackjackScene(app)
    scene.splash = None
    me = BlackjackAI("Hard")
    bank = app.settings.chip_bank
    for _ in range(20000):
        scene.update(0.2)
        if scene.overlay == "game":
            break
        if scene.can_bet():
            scene.do_bet()
        if scene.my_turn():
            scene.do_hint()
            scene.act(me.choose_action(scene.game, 0))
        scene.draw(app.screen)
    assert scene.game.game_over and scene.overlay == "game"
    assert app.settings.chip_bank == bank + scene.me.chips


def test_slots_bank_accounting_through_the_screen(app):
    from ten_phases.ui.menus import MenuScene
    from ten_phases.ui.slots_scene import SlotsScene

    app.settings.chip_bank = 200
    menu = MenuScene(app)
    while menu.game != "SLOTS":
        menu.switch_game(1)
    menu.draw(app.screen)
    assert not menu.btn_multi.enabled          # slots is single player
    menu._play()
    scene = app.scene
    assert isinstance(scene, SlotsScene)
    expected = 200
    for _ in range(25):
        scene.spin()
        for _ in range(300):
            scene.update(1 / 30)
            if scene.spinning is None:
                break
        expected += scene.result.win - scene.result.bet
        scene.draw(app.screen)
    assert app.settings.chip_bank == expected
    app.settings.chip_bank = 0
    scene.spin()
    assert scene.spinning is None              # can't spin with no chips
    app.settings.game = "10 PHASES"


def _drive(app, frames=1, dt=1 / 60):
    for _ in range(frames):
        app.scene.update(dt)
        app.scene.draw(app.screen)


def test_pack_opening_from_swipe_to_summary(app):
    from ten_phases import shop
    from ten_phases.ui.pack_open import PackOpenScene
    from ten_phases.ui.shop_scene import ShopScene

    app.settings.chip_bank = 2000
    app.go(ShopScene(app))
    shop_scene = app.scene
    btn = shop_scene.pack_buttons["legendary"]
    for _ in range(2):   # tap twice: confirm, then buy
        app.scene.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=btn.rect.center, button=1))
        app.scene.handle(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=btn.rect.center, button=1))
    scene = app.scene
    assert isinstance(scene, PackOpenScene) and app.settings.chip_bank <= 2000 - 500 + 450
    _drive(app, 60)
    assert scene.state == "ready"
    r = scene.pack_rect()
    y = r.y + 66
    scene.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(r.x, y), button=1))
    x = r.x
    while scene.state == "tearing" and x < r.right + 400:
        x += 20
        scene.handle(pygame.event.Event(pygame.MOUSEMOTION, pos=(x, y), rel=(20, 0), buttons=(1, 0, 0)))
        _drive(app)
    assert scene.state == "burst"
    _drive(app, 120)
    assert scene.state == "reveal"
    for _ in range(40):   # keep tapping: flips every card and dismisses the legendary close-up
        scene.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE, mod=0, unicode=" "))
        scene.handle(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(5, 5), button=1))
        _drive(app, 30)
        if scene.state == "done":
            break
    assert scene.state == "done" and all(s.revealed for s in scene.slots)
    owned = set(app.settings.owned_items)
    assert all(s.skin.id in owned for s in scene.slots)
    scene._equip(scene.slots[-1])
    assert shop.equipped(app.settings, scene.slots[-1].skin)
    scene._again()
    assert isinstance(app.scene, PackOpenScene) and app.scene is not scene
    app.scene._skip()
    _drive(app, 5)
    assert app.scene.state == "done"


def test_shop_collection_pages(app):
    from ten_phases.ui.shop_scene import ShopScene

    app.go(ShopScene(app, tab="CARD BACKS"))
    s = app.scene
    assert s.pages() > 5
    seen = set()
    for _ in range(s.pages()):
        seen |= {sk.id for sk in s.skins()}
        _drive(app)
        s._turn(1)
    assert len(seen) == len(s.all_skins()) and s.page == 0
    s._toggle_owned()
    assert all(sk.id in app.settings.owned_items or sk.free for sk in s.all_skins())
    _drive(app)


def test_random_clicking_never_crashes_any_screen(app):
    """Mash the mouse and keyboard on every screen (without leaving it) and keep drawing."""
    import random

    from ten_phases.ui.blackjack_scene import BlackjackScene
    from ten_phases.ui.customize import CustomizeScene
    from ten_phases.ui.deepdig_scene import DeepDigScene
    from ten_phases.ui.gofish_scene import GoFishScene
    from ten_phases.ui.menus import HowToScene, MenuScene, SettingsScene
    from ten_phases.ui.pack_open import PackOpenScene
    from test_cah import fake_packs

    from ten_phases.cah import cards as cc
    from ten_phases.cah.engine import CahOptions
    from ten_phases.ui.cah_scene import CahScene
    from ten_phases.ui.cah_setup import CahSetupScene
    from ten_phases.ui.monopoly_scene import MonopolyScene
    from ten_phases.ui.monopoly_setup import MonopolySetupScene
    from ten_phases.ui.poker_scene import PokerScene
    from ten_phases.ui.profile_scene import ProfileScene
    from ten_phases.ui.shop_scene import ShopScene
    from ten_phases.ui.slots_scene import SlotsScene
    from ten_phases import shop

    rng = random.Random(5)
    makers = [lambda: GameScene(app), lambda: GoFishScene(app), lambda: BlackjackScene(app), lambda: PokerScene(app),
              lambda: SlotsScene(app), lambda: HowToScene(app, "POKER"), lambda: HowToScene(app, "CAH"),
              lambda: CahScene(app, packs=cc.normalize(fake_packs()), options=CahOptions(packs=[0, 1], blanks=20)),
              lambda: CahSetupScene(app),
              lambda: ShopScene(app), lambda: ShopScene(app, tab="CARD FRONTS"), lambda: MenuScene(app),
              lambda: SettingsScene(app), lambda: CustomizeScene(app), lambda: HowToScene(app, "GO FISH"),
              lambda: PackOpenScene(app, "premium", shop.open_pack(shop.PACK_BY_ID["premium"], set(), rng)),
              lambda: MonopolyScene(app), lambda: MonopolySetupScene(app), lambda: HowToScene(app, "MONOPOLY"),
              lambda: ProfileScene(app), lambda: ShopScene(app, tab="PICTURES"), lambda: ShopScene(app, tab="BACKGROUNDS"),
              lambda: DeepDigScene(app), lambda: HowToScene(app, "DEEP DIG")]
    keys = [pygame.K_SPACE, pygame.K_RETURN, pygame.K_LEFT, pygame.K_RIGHT, pygame.K_a, pygame.K_1, pygame.K_DOWN,
            pygame.K_e, pygame.K_ESCAPE]
    for make in makers:
        app.settings.chip_bank = 1000
        scene = make()
        app.go(scene)
        for _ in range(250):
            if app.scene is not scene:   # a click left the screen: come back to it
                app.go(scene)
            pos = (rng.randrange(1280), rng.randrange(800))
            kind = rng.random()
            if kind < 0.4:
                scene.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=rng.choice([1, 1, 3])))
                scene.handle(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1))
            elif kind < 0.7:
                scene.handle(pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(rng.randint(-40, 40), 0),
                                                buttons=(1, 0, 0)))
            elif kind < 0.8:
                scene.handle(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=rng.choice([-1, 1])))
            else:
                scene.handle(pygame.event.Event(pygame.KEYDOWN, key=rng.choice(keys), mod=0, unicode=""))
            scene.update(rng.choice([0.0, 1 / 60, 0.1]))
            scene.draw(app.screen)


def test_poker_table_plays_a_whole_game_with_the_bet_picker(app):
    from ten_phases.ui.poker_scene import SLIDER, PokerScene

    app.settings.chip_bank = 0
    app.settings.ai_speed = "Fast"
    app.go(PokerScene(app))
    scene = app.scene
    scene.splash = None
    picked = False
    for _ in range(60 * 600):
        _drive(app)
        if scene.overlay == "game":
            break
        if scene.my_turn():
            bounds = scene.raise_bounds()
            if bounds and not picked:
                lo, hi = bounds
                # The slider, the nudge buttons and the shortcuts all stay inside the legal range.
                scene.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(SLIDER.right - 5, SLIDER.centery),
                                                button=1))
                scene.handle(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(SLIDER.right - 5, SLIDER.centery),
                                                button=1))
                assert scene.raise_to == hi
                scene.nudge(-1)
                assert scene.raise_to == max(lo, hi - 1)
                scene.pick("min")
                assert scene.raise_to == lo
                scene.pick(1.0)
                assert lo <= scene.raise_to <= hi
                scene.act("raise")
                picked = True
                continue
            scene.check_or_call()
    assert picked and scene.overlay == "game"
    assert app.settings.chip_bank == max(0, scene.me.chips)


def test_fullscreen_setting_and_keys(app):
    """The DISPLAY setting and F11 / Alt+Enter switch fullscreen and remember it (headless: it falls back safely)."""
    from ten_phases.ui.menus import SettingsScene
    scene = SettingsScene(app)
    app.go(scene)
    display = [c for label, _, c in scene.rows if label == "DISPLAY"][0]
    display.on_change("Fullscreen")
    assert app.settings.fullscreen                        # remembered (and used from the next start, at least)
    for key, mod in ((pygame.K_F11, 0), (pygame.K_RETURN, pygame.KMOD_ALT)):
        assert app._is_fullscreen_key(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod, unicode=""))
    assert not app._is_fullscreen_key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0, unicode=""))
    app.set_fullscreen(False)
    assert not app.fullscreen and not app.settings.fullscreen
    assert app.screen.get_size() == (1280, 800)
    scene.draw(app.screen)
