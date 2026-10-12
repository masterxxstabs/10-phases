"""Earning XP at the table: little "+5 XP" pops, an XP bar that peeks in, and LEVEL UP!

Every table scene makes one `XpTracker`, feeds it the engine's events (only your own
moves count), and tells it when a round or game ends. It saves your XP every few
seconds, and straight away on a level up or at the end of a game.
"""

from __future__ import annotations

import pygame

from ..levels import GAME_XP, ROUND_XP, SETTLE, WENT_OUT_XP, WIN_XP, XP, level_for, progress
from . import sfx, theme

ME = 0


class XpTracker:
    def __init__(self, scene, game: str):
        self.scene = scene
        self.game = game
        self.earned = 0                 # XP earned at this table
        self.pops: list[list] = []      # [amount, time left]
        self.bar = 0.0                  # how long the XP bar stays up
        self.toast: list | None = None  # [level, time left]
        self.rounds_done: set = set()
        self.game_done = False
        self._unsaved = 0.0
        self.corner = (12, theme.HEIGHT - 62)   # top-left of the XP bar (tables can move it out of the way)

    @property
    def settings(self):
        return self.scene.app.settings

    # ---------------------------------------------------------------- earning

    def gain(self, amount: int) -> None:
        if amount <= 0:
            return
        s = self.settings
        before = level_for(s.xp)
        s.xp += amount
        self.earned += amount
        if self.pops and self.pops[-1][1] > 0.9:
            self.pops[-1][0] += amount       # moves in quick succession share one pop
        else:
            self.pops.append([amount, 1.3])
        self.bar = 2.5
        after = level_for(s.xp)
        if after > before:
            self.toast = [after, 3.2]
            sfx.play("game_win")
            s.save()
            self._unsaved = 0.0
        elif not self._unsaved:
            self._unsaved = 0.001

    def event(self, ev, me: int = ME) -> None:
        """XP for one engine event, if it was your move."""
        kind = getattr(ev, "kind", None)
        who = getattr(ev, "player", None)
        if self.game == "blackjack" and kind == "settle":
            if who == me:
                self.gain(SETTLE.get(getattr(ev, "result", ""), 2))
            return
        if self.game == "monopoly":
            data = getattr(ev, "data", None) or {}
            if kind == "pay" and getattr(ev, "text", "") == "passed GO" and data.get("to") == me:
                self.gain(5)
                return
            if kind == "rent" and data.get("owner") == me:
                self.gain(3)
                return
            if kind == "trade_done" and data.get("accepted") and me in (data.get("from"), data.get("to")):
                self.gain(5)
                return
        if who == me:
            self.gain(XP.get(self.game, {}).get(kind, 0))

    def round_end(self, key, went_out: bool = False) -> None:
        if key in self.rounds_done:
            return
        self.rounds_done.add(key)
        self.gain(ROUND_XP + (WENT_OUT_XP if went_out else 0))

    def game_end(self, won: bool) -> None:
        if self.game_done:
            return
        self.game_done = True
        self.gain(GAME_XP + (WIN_XP if won else 0))
        self.save()

    def save(self) -> None:
        self.settings.save()
        self._unsaved = 0.0

    # ---------------------------------------------------------------- frame

    def update(self, dt: float) -> None:
        for p in self.pops:
            p[1] -= dt
        self.pops = [p for p in self.pops if p[1] > 0]
        self.bar = max(0.0, self.bar - dt)
        if self.toast:
            self.toast[1] -= dt
            if self.toast[1] <= 0:
                self.toast = None
        if self._unsaved:
            self._unsaved += dt
            if self._unsaved > 4.0:
                self.save()

    def draw(self, surf) -> None:
        if self.bar > 0 or self.toast:
            self._draw_bar(surf)
        y = self.corner[1] - 22
        for amount, left in reversed(self.pops):
            rise = int((1.3 - left) * 26)
            img = theme.pixel_surface(f"+{amount} XP", 16, (150, 240, 255))
            if left < 0.35:
                img.set_alpha(int(255 * left / 0.35))
            surf.blit(img, (self.corner[0] + 6, y - rise))
            y -= 22
        if self.toast:
            self._draw_toast(surf)

    def _draw_bar(self, surf):
        level, into, need = progress(self.settings.xp)
        alpha = min(1.0, self.bar / 0.4) if not self.toast else 1.0
        box = pygame.Rect(*self.corner, 236, 28)
        layer = pygame.Surface(box.size, pygame.SRCALPHA)
        pygame.draw.rect(layer, (*theme.OUTLINE, 210), layer.get_rect(), border_radius=14)
        bar = pygame.Rect(52, 9, box.w - 62, 10)
        pygame.draw.rect(layer, (60, 70, 100), bar, border_radius=5)
        fill = bar.copy()
        fill.w = max(6, int(bar.w * into / max(1, need)))
        pygame.draw.rect(layer, (110, 220, 255), fill, border_radius=5)
        img = theme.pixel_surface(f"LV{level}", 12, (255, 214, 60), None)
        layer.blit(img, img.get_rect(midleft=(10, box.h // 2)))
        layer.set_alpha(int(255 * alpha))
        surf.blit(layer, box)

    def _draw_toast(self, surf):
        level, left = self.toast
        age = 3.2 - left
        k = min(1.0, age / 0.25, left / 0.4)
        img = theme.logo_surface("LEVEL UP!", 48, 4, (110, 220, 255))
        img = pygame.transform.rotozoom(img, 0, 0.6 + 0.4 * k)
        img.set_alpha(int(255 * k))
        cx = theme.WIDTH // 2
        surf.blit(img, img.get_rect(center=(cx, 150)))
        sub = theme.pixel_surface(f"YOU REACHED LEVEL {level}", 20, (255, 214, 60))
        sub.set_alpha(int(255 * k))
        surf.blit(sub, sub.get_rect(center=(cx, 200)))
