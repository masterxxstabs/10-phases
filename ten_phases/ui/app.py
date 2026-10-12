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
        flags = pygame.SCALED | pygame.RESIZABLE
        self.screen = pygame.display.set_mode((theme.WIDTH, theme.HEIGHT), flags)
        self.clock = pygame.time.Clock()
        self.settings = Settings.load()
        sfx.init(self.settings.sfx)
        theme.apply(self.settings)
        self.updater = updater.Updater()
        if check_updates and self.settings.auto_update:
            self.updater.start()
        self.running = True
        from .menus import MenuScene
        self.scene = MenuScene(self)

    def go(self, scene) -> None:
        self.scene = scene

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
                    self.running = False
                else:
                    self.scene.handle(event)
            self.scene.update(dt)
            self.scene.draw(self.screen)
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
