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


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr("ten_phases.settings.SETTINGS_PATH", tmp_path / "settings.json")
    a = App()
    yield a
    pygame.quit()


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
