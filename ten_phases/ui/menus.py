"""Main menu, settings and how-to-play screens."""

from __future__ import annotations

import random

import pygame

from ..cards import COLORS, number, skip, wild
from ..phases import NUM_PHASES, describe_phase
from ..settings import DIFFICULTY_CHOICES, SFX_CHOICES, SPEED_CHOICES
from . import sfx, theme
from .card_art import card_with_shadow
from .widgets import Button, Segmented

PRIMARY = dict(color="ACCENT", text_color="OUTLINE")


class Scene:
    def __init__(self, app):
        self.app = app
        self.clock = 0.0

    def handle(self, event): ...

    def update(self, dt: float):
        self.clock += dt

    def draw(self, surf): ...


def backdrop(surf, t: float = 0.0, split_y: int | None = None):
    surf.blit(theme.background(split_y), (0, 0))
    theme.twinkle(surf, t)


def status_bar(surf, msg: str):
    pygame.draw.rect(surf, theme.STATUS_BAR, (0, theme.HEIGHT - 30, theme.WIDTH, 30))
    theme.ptext(surf, msg, (theme.WIDTH // 2, theme.HEIGHT - 15), 18, theme.TEXT, None, anchor="center")


class MenuScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        cx = theme.WIDTH // 2
        self.buttons = [
            Button((cx - 150, 410, 300, 58), "PLAY", self._play, size=30, **PRIMARY),
            Button((cx - 150, 476, 300, 48), "MULTIPLAYER", self._multiplayer),
            Button((cx - 150, 530, 300, 46), "SETTINGS", lambda: app.go(SettingsScene(app))),
            Button((cx - 150, 582, 300, 46), "CUSTOMIZE", self._customize),
            Button((cx - 150, 634, 300, 46), "HOW TO PLAY", lambda: app.go(HowToScene(app))),
            Button((cx - 150, 686, 300, 46), "QUIT", app.quit),
        ]
        rng = random.Random()
        deck = [number(c, v) for c in COLORS for v in range(1, 13)] + [wild(), wild(), skip()]
        self.fan = rng.sample(deck, 7)

    def _multiplayer(self):
        from .multiplayer import MultiplayerScene
        self.app.go(MultiplayerScene(self.app))

    def _customize(self):
        from .customize import CustomizeScene
        self.app.go(CustomizeScene(self.app))

    def _play(self):
        from .game_scene import GameScene
        self.app.go(GameScene(self.app))

    def handle(self, event):
        for b in self.buttons:
            if b.handle(event):
                return
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._play()

    def draw(self, surf):
        backdrop(surf, self.clock)
        cx = theme.WIDTH // 2
        n = len(self.fan)
        for i, card in enumerate(self.fan):
            angle = (i - (n - 1) / 2) * 11
            img, _ = card_with_shadow(card, 100, 150)
            img = pygame.transform.rotozoom(img, -angle, 1)
            x = cx + (i - (n - 1) / 2) * 62
            y = 276 + abs(i - (n - 1) / 2) ** 2 * 5
            surf.blit(img, img.get_rect(center=(x, y)))
        theme.logo(surf, "10 PHASES", (cx, 120), 92, angle=6)
        s = self.app.settings
        info = f"{s.opponents} OPPONENT{'S' if s.opponents > 1 else ''}  -  {s.difficulty.upper()}"
        for b in self.buttons:
            b.draw(surf)
        status_bar(surf, f"Press PLAY to start!   {info}")


class SettingsScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        s = app.settings
        x, w = 470, 660
        self.rows = []

        def row(label, sub, control):
            self.rows.append((label, sub, control))

        def set_attr(name, conv=lambda v: v):
            return lambda v: setattr(s, name, conv(v))

        row("AI LEVEL", "Mixed: one of each, easiest first",
            Segmented((x, 156, w, 56), list(DIFFICULTY_CHOICES), s.difficulty, set_attr("difficulty")))
        row("OPPONENTS", "Computer players at the table",
            Segmented((x, 236, w, 56), ["1", "2", "3", "4", "5"], str(s.opponents), set_attr("opponents", int)))
        row("AI SPEED", "Pause between computer moves",
            Segmented((x, 316, w, 56), list(SPEED_CHOICES), s.ai_speed, set_attr("ai_speed")))
        row("HINTS", "Hint button + phase progress",
            Segmented((x, 396, w, 56), ["On", "Off"], "On" if s.hints else "Off",
                      set_attr("hints", lambda v: v == "On")))
        row("SORT HAND", "You can switch this in game",
            Segmented((x, 476, w, 56), ["Number", "Color"], s.sort_by.title(), set_attr("sort_by", str.lower)))

        def set_sfx(v):
            s.sfx = v
            sfx.set_volume(v)
            sfx.play("coin")
        row("SOUND FX", "Sound effect volume", Segmented((x, 556, w, 56), list(SFX_CHOICES), s.sfx, set_sfx))
        self.back = Button((theme.WIDTH // 2 - 130, 660, 260, 60), "DONE", self._done, size=24, **PRIMARY)

    def _done(self):
        self.app.settings.save()
        self.app.go(MenuScene(self.app))

    def handle(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._done()
            return
        if self.back.handle(event):
            return
        for _, _, c in self.rows:
            if c.handle(event):
                return

    def draw(self, surf):
        backdrop(surf, self.clock)
        theme.logo(surf, "SETTINGS", (theme.WIDTH // 2, 76), 52, angle=4)
        theme.panel(surf, (110, 136, 1060, 500), theme.PANEL)
        for label, sub, c in self.rows:
            theme.ptext(surf, label, (140, c.rect.y + 6), 22, theme.ACCENT)
            theme.ptext(surf, sub, (140, c.rect.y + 36), 14, theme.TEXT_DIM)
            c.draw(surf)
        self.back.draw(surf)
        status_bar(surf, "Settings are saved when you press DONE.")


HOW_TO = [
    "Be the first to complete all 10 phases. Each round you work on your current phase.",
    "On your turn: draw from the deck or the discard pile, then discard one card.",
    "When you hold your phase, select its cards and press LAY DOWN. Groups are worked out for you.",
    "After laying down, select cards and click any group on the table (or your own) to add to it.",
    "The round ends when someone empties their hand. Everyone who laid down moves up a phase.",
    "Chips: everyone antes 1 chip into the pot each round. Whoever goes out wins the pot!",
    "Cards left in hand cost points: 1-9 = 5, 10-12 = 10, Skip = 15, Wild = 25. Low score breaks ties.",
    "Space draws, double-click discards, Esc opens the menu.",
]


class HowToScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        self.back = Button((theme.WIDTH // 2 - 130, 690, 260, 58), "BACK", lambda: app.go(MenuScene(app)),
                           size=24, **PRIMARY)

    def handle(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.go(MenuScene(self.app))
            return
        self.back.handle(event)

    def draw(self, surf):
        backdrop(surf, self.clock)
        theme.logo(surf, "HOW TO PLAY", (theme.WIDTH // 2, 64), 50, angle=4)
        left = pygame.Rect(40, 120, 720, 550)
        theme.panel(surf, left)
        y = left.y + 20
        for line in HOW_TO:
            theme.star(surf, (left.x + 24, y + 10), 9, theme.ACCENT)
            for chunk in _wrap(line, 17, left.w - 70):
                theme.text(surf, chunk, (left.x + 44, y), 17, theme.TEXT, bold=False)
                y += 23
            y += 12
        panel = pygame.Rect(790, 120, 450, 550)
        theme.panel(surf, panel)
        theme.ptext(surf, "THE 10 PHASES", (panel.x + 24, panel.y + 18), 22, theme.ACCENT)
        for i in range(NUM_PHASES):
            yy = panel.y + 66 + i * 47
            pygame.draw.circle(surf, theme.OUTLINE, (panel.x + 40, yy + 14), 19)
            pygame.draw.circle(surf, theme.ACCENT, (panel.x + 40, yy + 12), 18)
            theme.ptext(surf, str(i + 1), (panel.x + 40, yy + 12), 16, theme.OUTLINE, None, anchor="center")
            theme.ptext(surf, describe_phase(i), (panel.x + 72, yy + 2), 18)
        self.back.draw(surf)
        status_bar(surf, "Good luck!")


def _wrap(msg: str, size: int, width: int, pixel: bool = False) -> list[str]:
    measure = (lambda t: theme.pixel_width(t, size)) if pixel else (lambda t: theme.font(size, False).size(t)[0])
    words, lines, cur = msg.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if measure(trial) > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines
