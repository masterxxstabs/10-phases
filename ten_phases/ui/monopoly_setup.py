"""Before a Monopoly game: pick your token and how long the game runs."""

from __future__ import annotations

import math

import pygame

from ..monopoly.engine import TOKENS
from ..settings import MONOPOLY_ROUNDS
from . import monopoly_art as art
from . import sfx, theme
from .menus import PRIMARY, Scene, backdrop, status_bar
from .widgets import Button, Segmented

LEFT = pygame.Rect(40, 120, 760, 550)
SIDE = pygame.Rect(820, 120, 420, 550)
LENGTHS = {20: "QUICK", 40: "NORMAL", 60: "LONG", 80: "EPIC"}


def token_rect(k: int) -> pygame.Rect:
    col, row = k % 3, k // 3
    return pygame.Rect(LEFT.x + 40 + col * 236, LEFT.y + 80 + row * 226, 210, 206)


class MonopolySetupScene(Scene):
    """mode "solo" starts a game against computers; mode "lobby" saves and goes back to the host lobby."""

    def __init__(self, app, mode: str = "solo", back=None):
        super().__init__(app)
        self.mode, self._back = mode, back
        s = app.settings
        self.token = s.monopoly_token if s.monopoly_token in TOKENS else TOKENS[0]
        self.picked_at = -10.0
        self.rounds = Segmented((SIDE.x + 20, SIDE.y + 84, 380, 50), [str(r) for r in MONOPOLY_ROUNDS],
                                str(s.monopoly_rounds), self._set_rounds, size=18)
        label = "START GAME" if mode == "solo" else "DONE"
        self.btn_go = Button((theme.WIDTH // 2 + 10, 700, 280, 56), label, self._go, size=22, **PRIMARY)
        self.btn_back = Button((theme.WIDTH // 2 - 290, 700, 280, 56), "BACK", self._leave, size=22)

    def _set_rounds(self, v: str):
        self.app.settings.monopoly_rounds = int(v)
        sfx.play("select")

    def _pick(self, kind: str):
        self.token = kind
        self.app.settings.monopoly_token = kind
        self.picked_at = self.clock
        sfx.play("lay")

    def _go(self):
        self.app.settings.save()
        if self.mode == "solo":
            from .monopoly_scene import MonopolyScene
            self.app.go(MonopolyScene(self.app))
        elif self._back:
            self._back()

    def _leave(self):
        self.app.settings.save()
        if self._back:
            self._back()
        else:
            from .menus import MenuScene
            self.app.go(MenuScene(self.app))

    def handle(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._leave()
            elif event.key == pygame.K_RETURN:
                self._go()
            elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                k = (TOKENS.index(self.token) + (1 if event.key == pygame.K_RIGHT else -1)) % len(TOKENS)
                self._pick(TOKENS[k])
            return
        for b in (self.btn_go, self.btn_back):
            if b.handle(event):
                return
        if self.rounds.handle(event):
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for k, kind in enumerate(TOKENS):
                if token_rect(k).collidepoint(event.pos):
                    self._pick(kind)
                    return

    def draw(self, surf):
        backdrop(surf, self.clock)
        theme.logo(surf, "MONOPOLY", (theme.WIDTH // 2, 58), 56, angle=3)
        theme.panel(surf, LEFT)
        theme.ptext(surf, "CHOOSE YOUR TOKEN", (LEFT.x + 24, LEFT.y + 20), 24, theme.ACCENT)
        theme.ptext(surf, "Computers get the others." if self.mode == "solo" else
                    "Everyone else gets a different one.", (LEFT.x + 24, LEFT.y + 52), 14, theme.TEXT_DIM)
        mouse = pygame.mouse.get_pos()
        for k, kind in enumerate(TOKENS):
            r = token_rect(k)
            on = kind == self.token
            hover = r.collidepoint(mouse)
            theme.rounded(surf, theme.PANEL_HOVER if on or hover else theme.INNER, r, 16)
            if on:
                pygame.draw.rect(surf, theme.ACCENT, r, 4, border_radius=16)
            color = art.TOKEN_COLORS[kind]
            pygame.draw.circle(surf, theme.OUTLINE, (r.centerx, r.centery - 8 + 4), 70)
            pygame.draw.circle(surf, theme.lighten(color, 40) if on else theme.darken(color, 40),
                               (r.centerx, r.centery - 8), 70)
            # The picked token jumps and spins once, then bobs.
            age = self.clock - self.picked_at
            hop = -abs(math.sin(age * 9)) * 30 * max(0.0, 1 - age / 0.7) if on and age < 0.7 else 0
            bob = math.sin(self.clock * 4) * 4 if on else 0
            img = art.token(kind, color, 110 if on else 92)
            if on and age < 0.5:
                img = pygame.transform.rotozoom(img, 360 * (age / 0.5), 1)
            surf.blit(img, img.get_rect(center=(r.centerx, int(r.centery - 12 + hop + bob))))
            theme.ptext(surf, kind.upper(), (r.centerx, r.bottom - 20), 18, theme.ACCENT if on else theme.TEXT,
                        anchor="center")
        theme.panel(surf, SIDE)
        theme.ptext(surf, "GAME LENGTH", (SIDE.x + 20, SIDE.y + 20), 22, theme.ACCENT)
        theme.ptext(surf, "Rounds before the richest player wins", (SIDE.x + 20, SIDE.y + 52), 13, theme.TEXT_DIM)
        self.rounds.draw(surf)
        n = self.app.settings.monopoly_rounds
        theme.ptext(surf, f"{LENGTHS.get(n, '')} GAME", (SIDE.x + 20, SIDE.y + 150), 20)
        minutes = {20: "about 15 minutes", 40: "about 30 minutes", 60: "about 45 minutes", 80: "an hour or more"}
        theme.ptext(surf, minutes.get(n, ""), (SIDE.x + 20, SIDE.y + 178), 14, theme.TEXT_DIM)
        lines = ["Go bankrupt and you're out.", "Last one standing wins early!", "",
                 "Money + property value counts", "at the end. Every £50 you're", "worth = 1 chip for your bank."]
        y = SIDE.y + 230
        for line in lines:
            theme.ptext(surf, line, (SIDE.x + 20, y), 15)
            y += 24
        if self.mode == "solo":
            s = self.app.settings
            theme.ptext(surf, f"{s.opponents} COMPUTER{'S' if s.opponents > 1 else ''} - {s.difficulty.upper()}",
                        (SIDE.x + 20, SIDE.bottom - 60), 16, theme.ACCENT)
            theme.ptext(surf, "Change them in SETTINGS.", (SIDE.x + 20, SIDE.bottom - 34), 13, theme.TEXT_DIM)
        self.btn_go.draw(surf)
        self.btn_back.draw(surf)
        status_bar(surf, "Pick a token (arrow keys work too), then START GAME.")
