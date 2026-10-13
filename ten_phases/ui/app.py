"""Window, main loop and scene switching."""

from __future__ import annotations

import os
import sys

import pygame

from .. import updater
from ..settings import Settings
from . import sfx, theme


class App:
    def __init__(self, check_updates: bool = True):
        pygame.mixer.pre_init(sfx.RATE, -16, 1, 512)
        pygame.init()
        pygame.display.set_caption("10 Phases")
        try:
            from .card_art import app_icon
            pygame.display.set_icon(app_icon(64))
        except pygame.error:
            pass
        self.settings = Settings.load()
        self.fullscreen = False
        self._open_window(self.settings.fullscreen)
        self.clock = pygame.time.Clock()
        from .gamepad import Gamepad
        self.pad = Gamepad(self)
        sfx.init(self.settings.sfx)
        theme.apply(self.settings)
        self.updater = updater.Updater()
        if check_updates and self.settings.auto_update:
            self.updater.start()
        self.running = True
        from .menus import MenuScene
        self.scene = MenuScene(self)

    def _open_window(self, fullscreen: bool) -> None:
        """The game draws on a 1280x800 canvas; SCALED has the graphics card stretch it to fit the window (or
        the whole screen), keeping its shape, and maps the mouse back onto the canvas for us."""
        flags = pygame.SCALED | (pygame.FULLSCREEN if fullscreen else pygame.RESIZABLE)
        try:
            self.screen = pygame.display.set_mode((theme.WIDTH, theme.HEIGHT), flags)
            self.fullscreen = fullscreen
        except pygame.error:            # no fullscreen here (e.g. a headless test): a window it is
            self.screen = pygame.display.set_mode((theme.WIDTH, theme.HEIGHT), pygame.SCALED | pygame.RESIZABLE)
            self.fullscreen = False

    def set_fullscreen(self, on: bool) -> None:
        """Switch between a window and the whole screen, and remember it for next time."""
        if on != self.fullscreen:
            try:
                pygame.display.toggle_fullscreen()
                self.fullscreen = on
            except pygame.error:
                # Can't switch while running here (making the window again can break it): it applies next start.
                pass
            self.screen = pygame.display.get_surface() or self.screen
        self.settings.fullscreen = on
        self.settings.save()

    def _is_fullscreen_key(self, event) -> bool:
        return event.type == pygame.KEYDOWN and (
            event.key == pygame.K_F11 or (event.key == pygame.K_RETURN and event.mod & pygame.KMOD_ALT))

    def go(self, scene) -> None:
        self._flush_xp()
        self.scene = scene

    def _flush_xp(self) -> None:
        """XP earned at a table is saved when you leave it (and every few seconds while you play).

        A screen with an `on_leave` (like Deep Dig's saved game) gets to save too."""
        leave = getattr(getattr(self, "scene", None), "on_leave", None)
        if leave is not None:
            leave()
        xp = getattr(getattr(self, "scene", None), "xp", None)
        if xp is not None and xp._unsaved:
            xp.save()

    def quit(self) -> None:
        self.running = False

    def restart_for_update(self) -> None:
        """Install the downloaded update, start the new version and close this one."""
        if self.updater.apply(restart=True):
            self.running = False

    def finish(self) -> None:
        """On exit: a downloaded update that wasn't installed yet goes in now, for next time."""
        if self.updater.state == "ready":
            self.updater.apply(restart=False)
        pygame.quit()

    def run(self, max_frames: int | None = None) -> None:
        frames = 0
        while self.running:
            frames += 1
            if max_frames is not None and frames > max_frames:
                break
            dt = min(self.clock.tick(60) / 1000.0, 0.1)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._flush_xp()
                    self.running = False
                elif self._is_fullscreen_key(event):
                    self.set_fullscreen(not self.fullscreen)
                else:
                    for e in self.pad.translate(event):     # a controller acts as the mouse and keys
                        self.scene.handle(e)
            for e in self.pad.update(dt):
                self.scene.handle(e)
            self.scene.update(dt)
            self.scene.draw(self.screen)
            self.pad.draw(self.screen)
            pygame.display.flip()


def _arg_value(flag: str, default: int) -> int:
    if flag in sys.argv:
        try:
            return int(sys.argv[sys.argv.index(flag) + 1])
        except (IndexError, ValueError):
            pass
    return default


def smoke_test() -> None:
    """Start the app, open a game, render some frames and exit. Used to check packaged builds.

    --smoke-frames N keeps the game open longer; TEN_PHASES_SMOKE_MARKER=path writes "ok" there at the end.
    """
    from .game_scene import GameScene

    app = App(check_updates=False)
    if theme._pixel_font(20) is None:
        raise SystemExit("smoke test: the bundled pixel font is missing")
    from .gamepad import sdl_controller
    if sdl_controller is None:
        raise SystemExit("smoke test: controller support (pygame._sdl2.controller) is missing")
    app.run(max_frames=30)
    app.running = True
    app.go(GameScene(app))
    app.run(max_frames=_arg_value("--smoke-frames", 120))
    from .gofish_scene import GoFishScene
    app.running = True
    app.go(GoFishScene(app))
    app.run(max_frames=90)
    from .blackjack_scene import BlackjackScene
    app.running = True
    app.go(BlackjackScene(app))
    app.run(max_frames=90)
    from .poker_scene import PokerScene
    app.running = True
    app.go(PokerScene(app))
    app.run(max_frames=90)
    from ..cah.engine import CahOptions
    from .cah_scene import CahScene
    smoke_packs = [{"id": 0, "name": "Smoke test", "white": [f"Answer {k}." for k in range(80)],
                    "black": [{"text": f"Question {k}: _", "pick": 1} for k in range(10)]}]
    app.running = True
    app.go(CahScene(app, packs=smoke_packs, options=CahOptions(blanks=3)))
    app.run(max_frames=90)
    from .monopoly_scene import MonopolyScene
    from .monopoly_setup import MonopolySetupScene
    app.running = True
    app.go(MonopolyScene(app))
    app.run(max_frames=120)
    app.running = True
    app.go(MonopolySetupScene(app))
    app.run(max_frames=20)
    from .. import shop
    from .pack_open import PackOpenScene
    from .shop_scene import ShopScene
    from .slots_scene import SlotsScene
    pulls = shop.open_pack(shop.PACK_BY_ID["legendary"], set())   # just for show: nothing is saved
    from .deepdig_scene import DeepDigScene
    from .profile_scene import ProfileScene
    for scene in (ShopScene(app), ShopScene(app, tab="CARD BACKS"), ShopScene(app, tab="PICTURES"), SlotsScene(app),
                  ProfileScene(app), DeepDigScene(app),
                  PackOpenScene(app, "legendary", pulls)):
        app.running = True
        app.go(scene)
        app.run(max_frames=30)
    pygame.quit()
    marker = os.environ.get("TEN_PHASES_SMOKE_MARKER")
    if marker:
        with open(marker, "w") as f:
            f.write("ok")


def main() -> None:
    if "--smoke-test" in sys.argv:
        smoke_test()
        return
    if "--relaunch-test" in sys.argv:
        # Packaging check: start a fresh copy of ourselves the way an update restart does, then quit.
        exe = updater.running_exe()
        if exe is not None:
            updater.relaunch(exe, ["--smoke-test"])
        return
    app = App()
    app.run()
    app.finish()
