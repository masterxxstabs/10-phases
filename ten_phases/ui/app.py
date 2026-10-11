"""Window, main loop and scene switching."""

from __future__ import annotations

import pygame

from ..settings import Settings
from . import sfx, theme


class App:
    def __init__(self):
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
        self.running = True
        from .menus import MenuScene
        self.scene = MenuScene(self)

    def go(self, scene) -> None:
        self.scene = scene

    def quit(self) -> None:
        self.running = False

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


def smoke_test() -> None:
    """Start the app, open a game, render some frames and exit. Used to check packaged builds."""
    from .game_scene import GameScene

    app = App()
    app.run(max_frames=30)
    app.running = True
    app.go(GameScene(app))
    app.run(max_frames=120)
    pygame.quit()


def main() -> None:
    import sys

    if "--smoke-test" in sys.argv:
        smoke_test()
        return
    App().run()
    pygame.quit()
