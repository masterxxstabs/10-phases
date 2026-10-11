"""Main menu, settings and how-to-play screens."""

from __future__ import annotations

import random

import pygame

from ..cards import COLORS, number, skip, wild
from ..phases import NUM_PHASES, describe_phase
from ..settings import DIFFICULTY_CHOICES, SPEED_CHOICES
from . import theme
from .card_art import card_with_shadow
from .widgets import Button, Segmented


class Scene:
    def __init__(self, app):
        self.app = app

    def handle(self, event): ...
    def update(self, dt: float): ...
    def draw(self, surf): ...


def _backdrop(surf):
    surf.fill(theme.BG)
    pygame.draw.circle(surf, theme.BG_DARK, (theme.WIDTH // 2, theme.HEIGHT + 260), 620)


def _title(surf, y: int, size: int = 96):
    theme.shadow_text(surf, "10 PHASES", (theme.WIDTH // 2, y), size, theme.ACCENT, shadow=theme.BG_DARK, offset=6)


class MenuScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        cx = theme.WIDTH // 2
        self.buttons = [
            Button((cx - 140, 404, 280, 64), "PLAY", self._play, theme.ACCENT, theme.BG_DARK, size=28),
            Button((cx - 140, 482, 280, 54), "Settings", lambda: app.go(SettingsScene(app))),
            Button((cx - 140, 546, 280, 54), "How to Play", lambda: app.go(HowToScene(app))),
            Button((cx - 140, 610, 280, 54), "Quit", app.quit),
        ]
        rng = random.Random()
        deck = [number(c, v) for c in COLORS for v in range(1, 13)] + [wild(), wild(), skip()]
        self.fan = rng.sample(deck, 7)

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
        _backdrop(surf)
        cx = theme.WIDTH // 2
        n = len(self.fan)
        for i, card in enumerate(self.fan):
            angle = (i - (n - 1) / 2) * 11
            img, _ = card_with_shadow(card, 104, 156)
            img = pygame.transform.rotozoom(img, -angle, 1)
            x = cx + (i - (n - 1) / 2) * 64
            y = 268 + abs(i - (n - 1) / 2) ** 2 * 5
            surf.blit(img, img.get_rect(center=(x, y)))
        _title(surf, 86, 84)
        theme.text(surf, "a phase card game against the computer", (cx, 146), 20, theme.TEXT_DIM, anchor="center")
        s = self.app.settings
        info = f"{s.opponents} opponent{'s' if s.opponents > 1 else ''}  ·  {s.difficulty}  ·  {s.ai_speed} speed"
        theme.text(surf, info, (cx, 700), 18, theme.TEXT_DIM, anchor="center")
        for b in self.buttons:
            b.draw(surf)


class SettingsScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        s = app.settings
        x, w = 440, 640
        self.rows = []

        def row(label, sub, control):
            self.rows.append((label, sub, control))

        def set_attr(name, conv=lambda v: v):
            return lambda v: setattr(s, name, conv(v))

        row("AI difficulty", "Mixed gives you one of each, easiest first",
            Segmented((x, 170, w, 56), list(DIFFICULTY_CHOICES), s.difficulty, set_attr("difficulty")))
        row("Opponents", "How many computer players join the table",
            Segmented((x, 270, w, 56), ["1", "2", "3", "4", "5"], str(s.opponents), set_attr("opponents", int)))
        row("AI speed", "How long the computer pauses between moves",
            Segmented((x, 370, w, 56), list(SPEED_CHOICES), s.ai_speed, set_attr("ai_speed")))
        row("Hints", "Show the Hint button during play",
            Segmented((x, 470, w, 56), ["On", "Off"], "On" if s.hints else "Off",
                      set_attr("hints", lambda v: v == "On")))
        row("Sort hand by", "You can also switch this in game",
            Segmented((x, 570, w, 56), ["Number", "Color"], s.sort_by.title(), set_attr("sort_by", str.lower)))
        self.back = Button((theme.WIDTH // 2 - 120, 680, 240, 60), "Done", self._done, theme.ACCENT, theme.BG_DARK, 24)

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
        _backdrop(surf)
        theme.shadow_text(surf, "SETTINGS", (theme.WIDTH // 2, 80), 56, theme.ACCENT, shadow=theme.BG_DARK, offset=4)
        for label, sub, c in self.rows:
            theme.text(surf, label, (120, c.rect.y + 4), 24)
            theme.text(surf, sub, (120, c.rect.y + 34), 15, theme.TEXT_DIM, bold=False)
            c.draw(surf)
        self.back.draw(surf)


HOW_TO = [
    "Be the first to complete all 10 phases. Each round you try to complete your current phase.",
    "On your turn: draw one card from the deck or the discard pile, then discard one card.",
    "When you hold your phase, select its cards and press Lay Down. The groups are worked out for you.",
    "After laying down you can hit: select cards and click any group on the table to add to it.",
    "The round ends when someone empties their hand. Players who laid down move to the next phase.",
    "Cards left in hand score penalty points: 1-9 = 5, 10-12 = 10, Skip = 15, Wild = 25. Low score wins ties.",
    "Set = same number. Run = numbers in a row. Wilds stand in for anything. Skips make a player lose a turn.",
    "Shortcuts: Space draws from the deck, double-click a card to discard it, Esc opens the menu.",
]


class HowToScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        self.back = Button((theme.WIDTH // 2 - 120, 712, 240, 60), "Back", lambda: app.go(MenuScene(app)),
                           theme.ACCENT, theme.BG_DARK, 24)

    def handle(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.go(MenuScene(self.app))
            return
        self.back.handle(event)

    def draw(self, surf):
        _backdrop(surf)
        theme.shadow_text(surf, "HOW TO PLAY", (theme.WIDTH // 2, 64), 52, theme.ACCENT, shadow=theme.BG_DARK, offset=4)
        y = 120
        for line in HOW_TO:
            pygame.draw.circle(surf, theme.ACCENT, (80, y + 11), 5)
            for chunk in _wrap(line, 17, 620):
                theme.text(surf, chunk, (96, y), 17, theme.TEXT, bold=False)
                y += 24
            y += 10
        panel = pygame.Rect(780, 120, 440, 570)
        theme.rounded(surf, theme.PANEL, panel, 16)
        theme.text(surf, "THE 10 PHASES", (panel.x + 24, panel.y + 18), 20, theme.ACCENT)
        for i in range(NUM_PHASES):
            yy = panel.y + 62 + i * 50
            pygame.draw.circle(surf, theme.PANEL_LIGHT, (panel.x + 42, yy + 12), 18)
            theme.text(surf, str(i + 1), (panel.x + 42, yy + 12), 18, anchor="center")
            theme.text(surf, describe_phase(i), (panel.x + 76, yy + 1), 19, bold=False)
        self.back.draw(surf)


def _wrap(msg: str, size: int, width: int) -> list[str]:
    f = theme.font(size, False)
    words, lines, cur = msg.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if f.size(trial)[0] > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines
