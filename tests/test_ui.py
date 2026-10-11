"""Smoke tests for the pygame front end, run headless."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

from ten_phases.cards import Color, number  # noqa: E402
from ten_phases.ui import sfx  # noqa: E402
from ten_phases.ui.app import App  # noqa: E402
from ten_phases.ui.game_scene import GameScene  # noqa: E402


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    # One window for the whole module: pygame can't recreate a scaled window headless, and
    # cached fonts belong to the running session.
    import ten_phases.settings as settings_module

    original = settings_module.SETTINGS_PATH
    settings_module.SETTINGS_PATH = tmp_path_factory.mktemp("cfg") / "settings.json"
    yield App(check_updates=False)
    settings_module.SETTINGS_PATH = original


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
