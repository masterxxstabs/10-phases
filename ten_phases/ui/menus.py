"""Main menu, settings and how-to-play screens."""

from __future__ import annotations

import random
import webbrowser

import pygame

from .. import __version__

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


UPDATE_CARD = pygame.Rect(896, 500, 364, 220)


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
        card = UPDATE_CARD
        self.btn_restart = Button((card.x + 18, card.bottom - 62, 196, 46), "RESTART NOW", app.restart_for_update,
                                  size=16, **PRIMARY)
        self.btn_later = Button((card.right - 120, card.bottom - 62, 102, 46), "LATER", self._later, size=16)
        self.btn_get = Button((card.x + 18, card.bottom - 62, card.w - 36, 46), "GET IT ON GITHUB", self._open_release,
                              size=16, **PRIMARY)
        self.update_buttons = [self.btn_restart, self.btn_later, self.btn_get]

    def _later(self):
        self.app.updater.dismissed = True

    def _open_release(self):
        info = self.app.updater.info
        webbrowser.open(info.page_url if info else "https://github.com")

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
        for b in self.buttons + self.update_buttons:
            if b.visible and b.handle(event):
                return
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._play()

    def _draw_update(self, surf):
        """Version in the corner, plus a card while an update is downloading or ready."""
        up = self.app.updater
        for b in self.update_buttons:
            b.visible = False
        note = {"checking": "checking for updates...", "current": "up to date",
                "failed": up.error or "", "downloading": "downloading update...",
                "installed": "update installed"}.get(up.state, "")
        if up.state == "ready" and getattr(up, "dismissed", False):
            note = f"v{up.info.version} installs when you quit"
        version = f"v{__version__}" + (f"  -  {note}" if note else "")
        theme.ptext(surf, version, (16, theme.HEIGHT - 42), 14, theme.TEXT_DIM, anchor="bottomleft")
        if up.info is None or up.state not in ("downloading", "ready", "available") or getattr(up, "dismissed", False):
            return
        card = UPDATE_CARD
        theme.panel(surf, card, edge=theme.ACCENT, edge_w=3)
        title = {"downloading": "NEW VERSION!", "ready": "UPDATE READY!", "available": "NEW VERSION OUT!"}[up.state]
        theme.ptext(surf, title, (card.x + 18, card.y + 14), 20, theme.ACCENT)
        theme.ptext(surf, f"v{__version__}  >  v{up.info.version}", (card.x + 18, card.y + 44), 16)
        y = card.y + 72
        for line in up.info.notes[:3]:
            pygame.draw.circle(surf, theme.ACCENT, (card.x + 22, y + 8), 3)
            for chunk in _wrap(line, 13, card.w - 50)[:2]:
                theme.text(surf, chunk, (card.x + 30, y), 13, theme.TEXT_DIM, bold=False)
                y += 17
        if up.state == "downloading":
            bar = pygame.Rect(card.x + 18, card.bottom - 46, card.w - 36, 22)
            theme.rounded(surf, theme.INNER, bar, 11)
            fill = bar.copy()
            fill.w = max(22, int(bar.w * up.progress))
            theme.rounded(surf, theme.ACCENT, fill, 11)
            theme.ptext(surf, f"{int(up.progress * 100)}%", bar.center, 12, theme.OUTLINE, None, anchor="center")
        elif up.state == "ready":
            self.btn_restart.visible = self.btn_later.visible = True
        else:
            self.btn_get.visible = True
        for b in self.update_buttons:
            b.draw(surf)

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
        self._draw_update(surf)
        self._draw_bank(surf)
        status_bar(surf, f"Press PLAY to start!   {info}")

    def _draw_bank(self, surf):
        """Chips kept from finished games."""
        box = pygame.Rect(20, 20, 250, 78)
        theme.panel(surf, box)
        for k in range(3):
            theme.chip_stack(surf, (box.x + 30 + k * 10, box.bottom - 22), 13, theme.CHIP_COLORS[k], 3 - k)
        theme.ptext(surf, "CHIP BANK", (box.x + 82, box.y + 10), 14, theme.TEXT_DIM)
        theme.ptext(surf, f"{self.app.settings.chip_bank:,}", (box.x + 82, box.bottom - 8), 30, theme.ACCENT,
                    anchor="bottomleft")


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
            Segmented((x, 146, w, 52), list(DIFFICULTY_CHOICES), s.difficulty, set_attr("difficulty")))
        row("OPPONENTS", "Computer players at the table",
            Segmented((x, 216, w, 52), ["1", "2", "3", "4", "5"], str(s.opponents), set_attr("opponents", int)))
        row("AI SPEED", "Pause between computer moves",
            Segmented((x, 286, w, 52), list(SPEED_CHOICES), s.ai_speed, set_attr("ai_speed")))
        row("HINTS", "Hint button + phase progress",
            Segmented((x, 356, w, 52), ["On", "Off"], "On" if s.hints else "Off",
                      set_attr("hints", lambda v: v == "On")))
        row("SORT HAND", "You can switch this in game",
            Segmented((x, 426, w, 52), ["Number", "Color"], s.sort_by.title(), set_attr("sort_by", str.lower)))

        def set_sfx(v):
            s.sfx = v
            sfx.set_volume(v)
            sfx.play("coin")
        row("SOUND FX", "Sound effect volume", Segmented((x, 496, w, 52), list(SFX_CHOICES), s.sfx, set_sfx))
        row("UPDATES", "Download new versions on start",
            Segmented((x, 566, w, 52), ["Auto", "Off"], "Auto" if s.auto_update else "Off",
                      set_attr("auto_update", lambda v: v == "Auto")))
        self.back = Button((theme.WIDTH // 2 - 130, 660, 260, 60), "DONE", self._done, size=24, **PRIMARY)

    def _done(self):
        self.app.settings.save()
        if self.app.settings.auto_update:
            self.app.updater.start()  # no-op if it already ran
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
        theme.panel(surf, (110, 128, 1060, 508), theme.PANEL)
        for label, sub, c in self.rows:
            theme.ptext(surf, label, (140, c.rect.y + 6), 22, theme.ACCENT)
            theme.ptext(surf, sub, (140, c.rect.y + 36), 14, theme.TEXT_DIM)
            c.draw(surf)
        self.back.draw(surf)
        status_bar(surf, f"10 Phases v{__version__}  -  settings are saved when you press DONE.")


HOW_TO = [
    "Be the first to complete all 10 phases. Each round you work on your current phase.",
    "On your turn: draw from the deck or the discard pile, then discard one card.",
    "When you hold your phase, select its cards and press LAY DOWN. Groups are worked out for you.",
    "After laying down, select cards and click any group on the table (or your own) to add to it.",
    "The round ends when someone empties their hand. Everyone who laid down moves up a phase.",
    "Chips: everyone antes 1 chip into the pot each round. Whoever goes out wins the pot!",
    "Cards left in hand cost points: 1-9 = 5, 10-12 = 10, Skip = 15, Wild = 25. Low score breaks ties.",
    "Hover over a player's box to see their phase, what they've laid down and their recent moves.",
    "Chips you finish a game with go into your CHIP BANK on the main menu.",
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
        status_bar(surf, f"10 Phases v{__version__}  -  good luck!")


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
