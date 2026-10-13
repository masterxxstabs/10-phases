"""Controllers: the pad drives every screen as a pointer plus keys, and action games get direct controls."""

import pygame
import pytest

from ten_phases.ui import gamepad


@pytest.fixture(autouse=True)
def fresh_pad(app):
    """Each test starts (and leaves) with the pad idle, so other tests see the real mouse."""
    def reset():
        app.pad.active = False
        app.pad.axes = dict.fromkeys(app.pad.axes, 0.0)
        app.pad.pressed.clear()
        app.pad.held_keys.clear()
    reset()
    yield
    reset()

A, B, X, Y = (pygame.CONTROLLER_BUTTON_A, pygame.CONTROLLER_BUTTON_B, pygame.CONTROLLER_BUTTON_X,
              pygame.CONTROLLER_BUTTON_Y)


def press(app, button, down=True):
    kind = pygame.CONTROLLERBUTTONDOWN if down else pygame.CONTROLLERBUTTONUP
    for e in app.pad.translate(pygame.event.Event(kind, button=button, instance_id=0)):
        app.scene.handle(e)


def tap(app, button):
    press(app, button)
    press(app, button, False)


def stick(app, axis, value):
    app.pad.translate(pygame.event.Event(pygame.CONTROLLERAXISMOTION, axis=axis, value=int(value * 32767),
                                         instance_id=0))


def frames(app, n, dt=1 / 60):
    for _ in range(n):
        for e in app.pad.update(dt):
            app.scene.handle(e)
        app.scene.update(dt)
    app.scene.draw(app.screen)
    app.pad.draw(app.screen)


class Recorder:
    """A stand-in screen that writes down what it's handed."""
    def __init__(self, mode="cursor", buttons=None):
        self.seen = []
        self.pad_mode = mode
        self.pad_buttons = buttons or {}

    def handle(self, event):
        self.seen.append(event)

    def update(self, dt):
        pass

    def draw(self, surf):
        pass


def test_the_pointer_moves_clicks_and_drags(app):
    rec = Recorder()
    app.go(rec)
    app.pad.cursor = [100.0, 100.0]
    stick(app, pygame.CONTROLLER_AXIS_LEFTX, 1.0)
    frames(app, 30)
    assert app.pad.active and app.pad.cursor[0] > 400 and abs(app.pad.cursor[1] - 100) < 1
    assert pygame.mouse.get_pos() == (int(app.pad.cursor[0]), 100)      # every screen's hover follows it
    moves = [e for e in rec.seen if e.type == pygame.MOUSEMOTION]
    assert moves and moves[-1].buttons == (0, 0, 0)
    press(app, A)                                                       # hold A and move: a drag
    frames(app, 5)
    press(app, A, False)
    kinds = [e.type for e in rec.seen]
    assert pygame.MOUSEBUTTONDOWN in kinds and pygame.MOUSEBUTTONUP in kinds
    down = kinds.index(pygame.MOUSEBUTTONDOWN)
    assert any(e.type == pygame.MOUSEMOTION and e.buttons == (1, 0, 0) for e in rec.seen[down:])
    stick(app, pygame.CONTROLLER_AXIS_LEFTX, 1.0)
    frames(app, 200)
    assert app.pad.cursor[0] <= 1279                                   # stays on the screen
    stick(app, pygame.CONTROLLER_AXIS_LEFTX, 0.0)
    stick(app, pygame.CONTROLLER_AXIS_RIGHTY, 1.0)                      # the right stick scrolls
    frames(app, 30)
    wheels = [e for e in rec.seen if e.type == pygame.MOUSEWHEEL]
    assert len(wheels) >= 3 and all(e.y == -1 for e in wheels)
    stick(app, pygame.CONTROLLER_AXIS_RIGHTY, 0.0)
    # Touching the real mouse hands control back.
    out = app.pad.translate(pygame.event.Event(pygame.MOUSEMOTION, pos=(5, 5), rel=(1, 1), buttons=(0, 0, 0)))
    assert out and not app.pad.active


def test_buttons_dpad_and_triggers(app):
    rec = Recorder(buttons={"X": pygame.K_h, "RT": pygame.K_4})
    app.go(rec)
    for button, key in ((B, pygame.K_ESCAPE), (X, pygame.K_h), (Y, pygame.K_RETURN),
                        (pygame.CONTROLLER_BUTTON_START, pygame.K_ESCAPE),
                        (pygame.CONTROLLER_BUTTON_DPAD_LEFT, pygame.K_LEFT)):
        rec.seen.clear()
        tap(app, button)
        assert [(e.type, e.key) for e in rec.seen] == [(pygame.KEYDOWN, key), (pygame.KEYUP, key)]
    rec.seen.clear()
    for value in (0.9, 0.95, 0.1):
        for e in app.pad.translate(pygame.event.Event(pygame.CONTROLLERAXISMOTION,
                                                      axis=pygame.CONTROLLER_AXIS_TRIGGERRIGHT,
                                                      value=int(value * 32767), instance_id=0)):
            rec.handle(e)
    assert [(e.type, e.key) for e in rec.seen] == [(pygame.KEYDOWN, pygame.K_4), (pygame.KEYUP, pygame.K_4)]
    # A button pressed on one screen is let go of the same way, even if the next screen maps it differently.
    rec.seen.clear()
    press(app, X)
    rec.pad_buttons = {"X": "click"}
    press(app, X, False)
    assert [e.type for e in rec.seen] == [pygame.KEYDOWN, pygame.KEYUP]
    # Raw joystick events for an open pad are dropped (the controller events cover them).
    app.pad.pads[99] = object()
    assert app.pad.translate(pygame.event.Event(pygame.JOYBUTTONDOWN, button=0, instance_id=99, joy=0)) == []
    del app.pad.pads[99]


def test_keys_mode_holds_arrows_and_unplugging_lets_go(app):
    rec = Recorder(mode="keys")
    app.go(rec)
    stick(app, pygame.CONTROLLER_AXIS_LEFTY, 0.9)
    stick(app, pygame.CONTROLLER_AXIS_LEFTX, -0.8)
    frames(app, 3)
    downs = {e.key for e in rec.seen if e.type == pygame.KEYDOWN}
    assert downs == {pygame.K_DOWN, pygame.K_LEFT}
    assert len([e for e in rec.seen if e.type == pygame.KEYDOWN]) == 2      # held, not repeated
    stick(app, pygame.CONTROLLER_AXIS_LEFTX, 0.0)
    frames(app, 1)
    assert rec.seen[-1].type == pygame.KEYUP and rec.seen[-1].key == pygame.K_LEFT
    app.pad.pads[7] = object()
    out = app.pad.translate(pygame.event.Event(pygame.CONTROLLERDEVICEREMOVED, instance_id=7))
    assert [(e.type, e.key) for e in out] == [(pygame.KEYUP, pygame.K_DOWN)] and not app.pad.held_keys
    app.pad.axes["LY"] = 0.0


def test_main_menu_with_a_controller(app):
    from ten_phases.ui.menus import MenuScene
    menu = MenuScene(app)
    app.go(menu)
    game = app.settings.game
    tap(app, pygame.CONTROLLER_BUTTON_DPAD_RIGHT)                     # the D-pad switches games
    assert app.settings.game != game
    frames(app, 2)
    # Point at SETTINGS and press A.
    button = next(b for b in menu.buttons if b.label == "SETTINGS")
    app.pad.cursor = [float(button.rect.centerx), float(button.rect.centery)]
    tap(app, A)
    from ten_phases.ui.menus import SettingsScene
    assert isinstance(app.scene, SettingsScene)
    tap(app, B)                                                        # B is back
    assert isinstance(app.scene, MenuScene)


def test_deep_dig_with_a_controller(app, tmp_path, monkeypatch):
    from ten_phases import settings
    from ten_phases.deepdig.engine import BUILDINGS, DeepDig
    from ten_phases.ui.deepdig_scene import DeepDigScene
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "s.json")
    g = DeepDig(seed=2)
    g.x = 16.5
    scene = DeepDigScene(app, g)
    app.go(scene)
    scene.splash = None
    assert app.pad.mode() == "keys"
    stick(app, pygame.CONTROLLER_AXIS_LEFTY, 1.0)                      # push down: drill
    frames(app, 150)
    stick(app, pygame.CONTROLLER_AXIS_LEFTY, 0.0)
    frames(app, 2)
    assert g.row >= 2 and not scene.keys
    assert "Stick" in scene._status()
    # Park at the garage, press A: the shop opens and the pad becomes a pointer.
    g.drill, g.cash = None, 5000
    a, b = BUILDINGS["SHOP"]
    g.x, g.y, g.vx, g.vy = (a + b + 1) / 2, -0.4, 0.0, 0.0
    frames(app, 2)
    tap(app, A)
    assert scene.panel == "SHOP" and app.pad.mode() == "cursor"
    buy = scene.panel_buttons[0]                                       # the drill upgrade
    app.pad.cursor = [float(buy.rect.centerx), float(buy.rect.centery)]
    tap(app, A)
    assert g.levels["DRILL"] == 1
    tap(app, B)                                                        # B closes the shop
    assert scene.panel is None
    g.items["REPAIR KIT"], g.hull = 1, 50
    g.y = 5.6
    tap(app, pygame.CONTROLLER_BUTTON_LEFTSHOULDER)                    # LB: item 1
    assert g.items["REPAIR KIT"] == 0 and g.hull > 50
    tap(app, B)                                                        # B does nothing while digging...
    assert scene.overlay is None
    tap(app, pygame.CONTROLLER_BUTTON_START)                           # ...Start pauses
    assert scene.overlay == "pause"


def test_every_table_maps_its_shortcuts():
    from ten_phases.ui.blackjack_scene import BlackjackScene
    from ten_phases.ui.game_scene import GameScene
    from ten_phases.ui.monopoly_scene import MonopolyScene
    from ten_phases.ui.poker_scene import PokerScene
    assert BlackjackScene.pad_buttons["X"] == pygame.K_h and PokerScene.pad_buttons["LB"] == pygame.K_f
    assert GameScene.pad_buttons["Y"] == pygame.K_s and MonopolyScene.pad_buttons["X"] == pygame.K_r
    assert gamepad.DEFAULT_BUTTONS["A"] == "click" and gamepad.DEFAULT_BUTTONS["B"] == pygame.K_ESCAPE


def test_app_loop_reads_controller_events(app):
    rec = Recorder()
    app.go(rec)
    pygame.event.post(pygame.event.Event(pygame.CONTROLLERBUTTONDOWN, button=Y, instance_id=0))
    pygame.event.post(pygame.event.Event(pygame.CONTROLLERBUTTONUP, button=Y, instance_id=0))
    app.running = True
    app.run(max_frames=3)
    assert [e.key for e in rec.seen if e.type == pygame.KEYDOWN] == [pygame.K_RETURN]
