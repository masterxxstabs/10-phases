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
        flags = pygame.SCALED | pygame.RESIZABLE
        self.screen = pygame.display.set_mode((theme.WIDTH, theme.HEIGHT), flags)
        self.clock = pygame.time.Clock()
        self.settings = Settings.load()
        sfx.init(self.settings.sfx)
        self.running = True
        from .menus import MenuScene
        self.scene = MenuScene(self)

    def go(self, scene) -> None:
        self.scene = scene

    def quit(self) -> None:
        self.running = False

    def run(self) -> None:
        while self.running:
            dt = min(self.clock.tick(60) / 1000.0, 0.1)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                else:
                    self.scene.handle(event)
            self.scene.update(dt)
            self.scene.draw(self.screen)
            pygame.display.flip()
        pygame.quit()


def main() -> None:
    App().run()
