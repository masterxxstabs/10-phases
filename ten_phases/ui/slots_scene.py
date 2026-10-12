"""Slots: a single-player slot machine that bets real Chip Bank chips."""

from __future__ import annotations

import math
import random

import pygame

from ..cards import wild
from ..levels import SPIN_XP
from ..slots.engine import (BELL, BETS, CHERRY, JACKPOT, LEMON, ONE_CHERRY, SEVEN, STAR, THREE, TWO_CHERRIES, WILD,
                            SlotMachine)
from . import sfx, theme
from .card_art import render_card
from .menus import PRIMARY, Scene, backdrop, status_bar
from .widgets import Button, Segmented
from .xp import XpTracker

SPLIT_Y = 222
CABINET = pygame.Rect(300, 238, 680, 380)
PAYTABLE = pygame.Rect(20, 238, 262, 526)
CONTROLS = pygame.Rect(300, 630, 960, 134)
SIDE = pygame.Rect(998, 238, 262, 380)
CELL = 120
REEL_W = 190
REEL_TOP = CABINET.y + 40
_symbol_cache: dict[tuple, pygame.Surface] = {}


def ease_out(t: float) -> float:
    return 1 - (1 - t) ** 3


def symbol_surface(sym: str, size: int) -> pygame.Surface:
    """Hand-drawn reel symbols (drawn at 100px, then scaled)."""
    key = (sym, size, theme.BACK_STYLE, theme.CARD_BACK, theme.FACE_STYLE)
    if key in _symbol_cache:
        return _symbol_cache[key]
    if size != 100:
        img = pygame.transform.smoothscale(symbol_surface(sym, 100), (size, size))
        _symbol_cache[key] = img
        return img
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    c = size // 2
    edge = theme.CARD_BLACK
    if sym == CHERRY:
        pygame.draw.lines(s, (40, 140, 50), False, [(c - 18, c + 4), (c - 2, c - 30), (c + 16, c + 2)], 6)
        pygame.draw.ellipse(s, (60, 180, 70), (c - 4, c - 40, 30, 16))
        for x in (c - 20, c + 16):
            pygame.draw.circle(s, edge, (x, c + 16), 21)
            pygame.draw.circle(s, (220, 30, 50), (x, c + 15), 19)
            pygame.draw.circle(s, (255, 150, 160), (x - 6, c + 8), 5)
    elif sym == LEMON:
        pygame.draw.ellipse(s, edge, (c - 40, c - 28, 80, 58))
        pygame.draw.ellipse(s, (250, 220, 40), (c - 38, c - 26, 76, 54))
        pygame.draw.ellipse(s, (255, 245, 160), (c - 22, c - 18, 26, 14))
    elif sym == BELL:
        pts = [(c - 34, c + 24), (c - 26, c - 4), (c - 18, c - 28), (c, c - 36), (c + 18, c - 28), (c + 26, c - 4),
               (c + 34, c + 24)]
        pygame.draw.polygon(s, edge, [(x, y + 3) for x, y in pts])
        pygame.draw.polygon(s, (250, 190, 40), pts)
        pygame.draw.rect(s, edge, (c - 38, c + 20, 76, 12), border_radius=6)
        pygame.draw.rect(s, (230, 160, 20), (c - 36, c + 21, 72, 9), border_radius=5)
        pygame.draw.circle(s, edge, (c, c + 36), 9)
        pygame.draw.circle(s, (230, 160, 20), (c, c + 35), 7)
    elif sym == STAR:
        pts = []
        for k in range(10):
            r = 44 if k % 2 == 0 else 19
            a = math.radians(-90 + k * 36)
            pts.append((c + math.cos(a) * r, c + math.sin(a) * r))
        pygame.draw.polygon(s, edge, [(x, y + 4) for x, y in pts])
        pygame.draw.polygon(s, (255, 214, 40), pts)
        pygame.draw.polygon(s, (255, 245, 170), [(x * 0.5 + c * 0.5, y * 0.5 + c * 0.5 - 4) for x, y in pts[:5]])
    elif sym == SEVEN:
        img = theme.outlined("7", int(size * 0.9), (230, 30, 40), edge, 4)
        s.blit(img, img.get_rect(center=(c, c + 2)))
    elif sym == WILD:
        img = render_card(wild(), int(size * 0.62), int(size * 0.92))
        s.blit(img, img.get_rect(center=(c, c)))
    elif sym == JACKPOT:
        img = render_card(None, int(size * 0.62), int(size * 0.92))
        s.blit(img, img.get_rect(center=(c, c)))
    _symbol_cache[key] = s
    return s


class SlotsScene(Scene):
    def __init__(self, app):
        super().__init__(app)
        self.machine = SlotMachine()
        n = len(self.machine.reels[0])
        self.pos = [float(self.machine.stops[k]) for k in range(3)]
        self.reel_len = n
        self.spinning: list[dict] | None = None   # per reel: start, target, t, duration
        self.result = None
        self.unseen_win = 0
        self.bet = 5 if app.settings.chip_bank >= 5 else 1
        self.win_flash = 0.0
        self.coins: list[list[float]] = []
        self.lever = 0.0            # 0..1 pull amount
        self.session_net = 0
        self.spins = 0
        self.last = "Pull the lever or press SPIN!"
        self.splash: tuple[str, str, float, float] | None = None
        self.bet_picker = Segmented((CONTROLS.x + 250, CONTROLS.y + 40, 330, 56), [str(b) for b in BETS], str(self.bet),
                                    self._set_bet, size=20)
        self.btn_spin = Button((CONTROLS.x + 610, CONTROLS.y + 30, 200, 76), "SPIN", self.spin, size=32, **PRIMARY)
        self.btn_menu = Button((CONTROLS.right - 130, CONTROLS.y + 40, 112, 56), "MENU", self.to_menu, size=18)
        self.lever_rect = pygame.Rect(CABINET.right - 6, CABINET.y + 40, 70, 260)
        self.xp = XpTracker(self, "slots")

    # ---------------------------------------------------------------- actions

    @property
    def bank(self) -> int:
        """What the player sees: a win only shows up once the reels stop."""
        return self.app.settings.chip_bank - self.unseen_win

    def _set_bet(self, v: str):
        self.bet = int(v)

    def can_spin(self) -> bool:
        return self.spinning is None and self.bank >= self.bet

    def spin(self):
        if self.spinning is not None:
            return
        if self.bank < self.bet:
            sfx.play("error")
            affordable = [b for b in BETS if b <= self.bank]
            if affordable:
                self.bet = affordable[-1]
                self.bet_picker.value = str(self.bet)
                self.last = f"Bet lowered to {self.bet} - that's what you can afford."
            else:
                self.last = "Out of chips! Win more in 10 Phases, Go Fish, Blackjack or Poker."
            return
        s = self.app.settings
        self.result = self.machine.spin(self.bet)
        # Settle the spin straight away, so closing the window mid-spin can't lose a win.
        s.chip_bank += self.result.win - self.bet
        s.save()
        self.unseen_win = self.result.win
        self.spinning = []
        for k in range(3):
            start = self.pos[k]
            target = start + ((self.result.stops[k] - start) % self.reel_len) + self.reel_len * (2 + k)
            self.spinning.append({"start": start, "target": target, "t": 0.0, "dur": 0.9 + 0.38 * k, "done": False})
        self.lever = 1.0
        self.win_flash = 0.0
        self.spins += 1
        self.last = "Spinning..."
        sfx.play("shuffle")

    def _finish_spin(self):
        r = self.result
        self.spinning = None
        self.unseen_win = 0
        self.session_net += r.win - r.bet
        self.xp.gain(SPIN_XP + (3 if r.win else 0) + (20 if r.multiplier >= 25 else 0))
        if r.win:
            self.win_flash = 2.5
            self.last = f"{r.name}! You win {r.win} chips ({r.multiplier}x)"
            big = r.multiplier >= 25
            sfx.play("game_win" if big else "round_win" if r.multiplier >= 4 else "coin")
            for _ in range(min(80, 8 + r.multiplier * 2)):
                self.coins.append([CABINET.centerx + random.uniform(-200, 200), CABINET.bottom - 20,
                                   random.uniform(-160, 160), random.uniform(-520, -260), random.uniform(1.0, 1.8)])
            if big:
                self.splash = ("JACKPOT!!" if r.name == "JACKPOT!" else "BIG WIN!", f"+{r.win} CHIPS", 2.2, 2.2)
        else:
            self.last = "No win this time. Spin again!"

    def to_menu(self):
        if self.spinning is not None:
            return
        from .menus import MenuScene
        self.app.go(MenuScene(self.app))

    # ---------------------------------------------------------------- input / update

    def handle(self, event):
        if self.splash and event.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN):
            self.splash = None
            return
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                self.spin()
            elif event.key == pygame.K_ESCAPE:
                self.to_menu()
            elif event.key in (pygame.K_LEFT, pygame.K_RIGHT) and self.spinning is None:
                k = BETS.index(self.bet) + (1 if event.key == pygame.K_RIGHT else -1)
                self.bet = BETS[max(0, min(len(BETS) - 1, k))]
                self.bet_picker.value = str(self.bet)
                sfx.play("select")
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.lever_rect.collidepoint(event.pos):
            sfx.play("click")
            self.spin()
            return
        for w in (self.btn_spin, self.btn_menu):
            if w.handle(event):
                return
        if self.spinning is None:
            self.bet_picker.handle(event)

    def update(self, dt: float):
        super().update(dt)
        self.xp.update(dt)
        self.lever = max(0.0, self.lever - dt * 2.2)
        self.win_flash = max(0.0, self.win_flash - dt)
        if self.splash:
            t, s_, left, total = self.splash
            self.splash = (t, s_, left - dt, total) if left > dt else None
        for c in self.coins:
            c[0] += c[2] * dt
            c[1] += c[3] * dt
            c[3] += 900 * dt
            c[4] -= dt
        self.coins = [c for c in self.coins if c[4] > 0]
        if self.spinning is not None:
            all_done = True
            for k, reel in enumerate(self.spinning):
                if reel["done"]:
                    continue
                reel["t"] += dt
                f = min(1.0, reel["t"] / reel["dur"])
                self.pos[k] = reel["start"] + (reel["target"] - reel["start"]) * ease_out(f)
                if f >= 1.0:
                    reel["done"] = True
                    self.pos[k] = float(self.result.stops[k])
                    sfx.play("discard")
                else:
                    all_done = False
            if all_done:
                self._finish_spin()

    # ---------------------------------------------------------------- drawing

    def draw(self, surf):
        backdrop(surf, self.clock, SPLIT_Y)
        self._draw_marquee(surf)
        self._draw_paytable(surf)
        self._draw_cabinet(surf)
        self._draw_side(surf)
        self._draw_controls(surf)
        for x, y, _, _, life in self.coins:
            theme.chip(surf, (int(x), int(y)), 11, theme.ACCENT if int(life * 10) % 2 else theme.lighten(theme.ACCENT, 40))
        status_bar(surf, self.last if self.bank >= min(BETS) or self.spinning else
                   "Out of chips! Win more in 10 Phases, Go Fish, Blackjack or Poker.")
        self.xp.draw(surf)
        if self.splash:
            title, sub, t, total = self.splash
            k = min(1.0, (total - t) / 0.25, t / 0.3)
            band = pygame.Rect(0, 300, theme.WIDTH, 170)
            shade = pygame.Surface(band.size, pygame.SRCALPHA)
            shade.fill((*theme.OUTLINE, int(200 * k)))
            surf.blit(shade, band)
            theme.logo(surf, title, (theme.WIDTH // 2, band.y + 70), 78, angle=6)
            theme.ptext(surf, sub, (theme.WIDTH // 2, band.bottom - 26), 22, theme.ACCENT, anchor="center")

    def _draw_marquee(self, surf):
        box = pygame.Rect(140, 14, 1000, 194)
        theme.panel(surf, box, edge=theme.ACCENT, edge_w=3)
        # Chasing lights around the sign
        n = 36
        for k in range(n):
            t = k / n
            if t < 0.5:
                x, y = box.x + 14 + (box.w - 28) * (t * 2), box.y + 12
            else:
                x, y = box.x + 14 + (box.w - 28) * ((t - 0.5) * 2), box.bottom - 12
            on = (k + int(self.clock * 8)) % 3 == 0 or self.win_flash > 0 and int(self.clock * 12) % 2
            pygame.draw.circle(surf, theme.OUTLINE, (int(x), int(y) + 2), 7)
            pygame.draw.circle(surf, theme.ACCENT if on else theme.PANEL_LIGHT, (int(x), int(y)), 6)
        theme.logo(surf, "LUCKY 10 SLOTS", (box.centerx, box.y + 82), 64, angle=3)
        jack = f"JACKPOT: {THREE[JACKPOT] * self.bet:,} CHIPS AT BET {self.bet}"
        theme.ptext(surf, jack, (box.centerx, box.bottom - 38), 18, theme.ACCENT, anchor="center")

    def _draw_paytable(self, surf):
        theme.panel(surf, PAYTABLE)
        theme.ptext(surf, "PAYTABLE", (PAYTABLE.x + 16, PAYTABLE.y + 12), 20, theme.ACCENT)
        theme.ptext(surf, "x BET", (PAYTABLE.right - 16, PAYTABLE.y + 16), 14, theme.TEXT_DIM, anchor="topright")
        rows = [(JACKPOT,) * 3, (WILD,) * 3, (SEVEN,) * 3, (STAR,) * 3, (BELL,) * 3, (LEMON,) * 3, (CHERRY,) * 3]
        pays = [THREE[r[0]] for r in rows] + [TWO_CHERRIES, ONE_CHERRY]
        rows += [(CHERRY, CHERRY, None), (CHERRY, None, None)]
        hit = self.result and self.win_flash > 0 and self.result.win
        for k, (row, pay) in enumerate(zip(rows, pays)):
            y = PAYTABLE.y + 48 + k * 50
            lit = hit and self.result.multiplier == pay and int(self.clock * 8) % 2 == 0
            if lit:
                theme.rounded(surf, theme.ACCENT, (PAYTABLE.x + 8, y - 4, PAYTABLE.w - 16, 46), 8)
            for n, sym in enumerate(row):
                if sym:
                    img = symbol_surface(sym, 40)
                    surf.blit(img, (PAYTABLE.x + 14 + n * 42, y))
                else:
                    theme.ptext(surf, "ANY", (PAYTABLE.x + 34 + n * 42, y + 20), 11, theme.TEXT_DIM, anchor="center")
            theme.ptext(surf, f"{pay}", (PAYTABLE.right - 16, y + 20), 22, theme.OUTLINE if lit else theme.ACCENT,
                        None if lit else "OUTLINE", anchor="midright")
        theme.text(surf, "WILD counts as any symbol", (PAYTABLE.x + 14, PAYTABLE.bottom - 40), 13, theme.TEXT_DIM,
                   bold=False)
        theme.text(surf, "except the 10 PHASES jackpot.", (PAYTABLE.x + 14, PAYTABLE.bottom - 22), 13, theme.TEXT_DIM,
                   bold=False)

    def _draw_cabinet(self, surf):
        theme.panel(surf, CABINET, fill=theme.INNER, edge=theme.ACCENT, edge_w=4)
        x0 = CABINET.x + (CABINET.w - 3 * REEL_W - 2 * 16) // 2
        for k in range(3):
            win = pygame.Rect(x0 + k * (REEL_W + 16), REEL_TOP, REEL_W, CELL * 2 + 60)
            pygame.draw.rect(surf, theme.OUTLINE, win.inflate(10, 10), border_radius=14)
            pygame.draw.rect(surf, theme.CARD_WHITE, win, border_radius=10)
            clip = surf.get_clip()
            surf.set_clip(win)
            pos = self.pos[k]
            base = math.floor(pos)
            frac = pos - base
            reel = self.machine.reels[k]
            spinning = self.spinning is not None and not self.spinning[k]["done"]
            for row in range(-2, 3):
                sym = reel[(base + row) % len(reel)]
                cy = win.centery - (row - frac) * CELL  # symbols scroll downward as pos grows
                img = symbol_surface(sym, 100)
                if spinning:
                    img = img.copy()
                    img.set_alpha(150)
                surf.blit(img, img.get_rect(center=(win.centerx, int(cy))))
            surf.set_clip(clip)
            # Soft shading at the top and bottom of each reel window
            shade = pygame.Surface((win.w, 50), pygame.SRCALPHA)
            for n in range(50):
                pygame.draw.line(shade, (*theme.OUTLINE, int(150 * (1 - n / 50))), (0, n), (win.w, n))
            surf.blit(shade, win.topleft)
            surf.blit(pygame.transform.flip(shade, False, True), (win.x, win.bottom - 50))
        # Payline
        y = REEL_TOP + CELL + 30
        lit = self.win_flash > 0 and int(self.clock * 10) % 2 == 0
        color = theme.ACCENT if lit else theme.DANGER
        pygame.draw.line(surf, color, (CABINET.x + 16, y), (CABINET.right - 16, y), 4)
        for x, d in ((CABINET.x + 10, 1), (CABINET.right - 10, -1)):
            pygame.draw.polygon(surf, color, [(x, y - 12), (x + 16 * d, y), (x, y + 12)])
        # Coin tray
        tray = pygame.Rect(CABINET.x + 120, CABINET.bottom - 40, CABINET.w - 240, 26)
        theme.rounded(surf, theme.OUTLINE, tray, 10)
        theme.rounded(surf, theme.darken(theme.INNER, 20), tray.inflate(-6, -6), 8)
        # Lever
        top = self.lever_rect.y + 20 + int(self.lever * 150)
        base = (self.lever_rect.centerx, self.lever_rect.bottom - 20)
        pygame.draw.rect(surf, theme.OUTLINE, (base[0] - 14, self.lever_rect.y + 10, 28, self.lever_rect.h - 20),
                         border_radius=14)
        pygame.draw.line(surf, theme.CARD_WHITE, (base[0], base[1]), (base[0], top), 8)
        hover = self.lever_rect.collidepoint(pygame.mouse.get_pos()) and self.can_spin()
        pygame.draw.circle(surf, theme.OUTLINE, (base[0], top + 3), 22)
        pygame.draw.circle(surf, theme.lighten(theme.DANGER, 30) if hover else theme.DANGER, (base[0], top), 20)
        pygame.draw.circle(surf, (255, 190, 190), (base[0] - 6, top - 6), 6)

    def _draw_side(self, surf):
        box = pygame.Rect(SIDE.x + 72, SIDE.y, SIDE.w - 72, SIDE.h)
        theme.panel(surf, box)
        theme.ptext(surf, "CHIP BANK", (box.x + 16, box.y + 14), 16, theme.TEXT_DIM)
        theme.chip(surf, (box.x + 30, box.y + 66), 14, theme.ACCENT)
        theme.ptext(surf, f"{self.bank:,}", (box.x + 52, box.y + 46), 32, theme.ACCENT)
        theme.ptext(surf, "THIS VISIT", (box.x + 16, box.y + 110), 14, theme.TEXT_DIM)
        net = f"+{self.session_net}" if self.session_net > 0 else str(self.session_net)
        theme.ptext(surf, net, (box.x + 16, box.y + 132), 24,
                    theme.SUCCESS if self.session_net > 0 else theme.DANGER if self.session_net < 0 else theme.TEXT)
        theme.ptext(surf, f"{self.spins} SPINS", (box.x + 16, box.y + 168), 14, theme.TEXT_DIM)
        if self.result and self.spinning is None and self.result.win:
            theme.ptext(surf, "LAST WIN", (box.x + 16, box.y + 210), 14, theme.TEXT_DIM)
            theme.ptext(surf, f"+{self.result.win}", (box.x + 16, box.y + 232), 30, theme.ACCENT)
        theme.text(surf, "Pays back about 95%", (box.x + 16, box.bottom - 54), 13, theme.TEXT_DIM, bold=False)
        theme.text(surf, "of bets over time.", (box.x + 16, box.bottom - 36), 13, theme.TEXT_DIM, bold=False)

    def _draw_controls(self, surf):
        theme.panel(surf, CONTROLS)
        theme.ptext(surf, "BET", (CONTROLS.x + 250, CONTROLS.y + 14), 16, theme.ACCENT)
        theme.ptext(surf, "Space: spin   Left/Right: bet", (CONTROLS.x + 24, CONTROLS.y + 100), 12, theme.TEXT_DIM)
        theme.ptext(surf, "SINGLE PLAYER", (CONTROLS.x + 24, CONTROLS.y + 20), 16, theme.ACCENT)
        theme.text(surf, "Bets come out of", (CONTROLS.x + 24, CONTROLS.y + 46), 14, theme.TEXT_DIM, bold=False)
        theme.text(surf, "your Chip Bank.", (CONTROLS.x + 24, CONTROLS.y + 64), 14, theme.TEXT_DIM, bold=False)
        self.bet_picker.draw(surf)
        self.btn_spin.enabled = self.can_spin()
        self.btn_spin.draw(surf)
        self.btn_menu.enabled = self.spinning is None
        self.btn_menu.draw(surf)
