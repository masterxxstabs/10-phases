"""The card shop: spend your Chip Bank on card skins."""

from __future__ import annotations

import pygame

from .. import shop
from ..cards import COLORS, number, wild
from . import sfx, theme
from .card_art import card_with_shadow
from .menus import PRIMARY, Scene, backdrop, status_bar
from .widgets import Button, Segmented

GRID = pygame.Rect(40, 196, 1200, 470)


class ShopScene(Scene):
    def __init__(self, app, back=None):
        super().__init__(app)
        self._back = back
        self.tab = "CARD FRONTS"
        self.tabs = Segmented((340, 128, 600, 52), ["CARD FRONTS", "CARD BACKS"], self.tab, self._set_tab, size=18)
        self.btn_done = Button((theme.WIDTH // 2 - 130, 690, 260, 58), "DONE", self._done, size=24, **PRIMARY)
        self.flash: tuple[str, float] | None = None
        self.confirm: tuple[str, float] | None = None   # item awaiting a second click to buy
        self.item_buttons: dict[str, Button] = {}
        self._build()

    def _set_tab(self, tab: str):
        self.tab = tab
        self.confirm = None
        self._build()

    def items(self) -> list[shop.Item]:
        kind = "face" if self.tab == "CARD FRONTS" else "back"
        return [i for i in shop.ITEMS if i.kind == kind]

    def tile_rect(self, k: int, n: int) -> pygame.Rect:
        cols = 3 if n <= 6 else 4
        rows = (n + cols - 1) // cols
        w = (GRID.w - (cols - 1) * 16) // cols
        h = (GRID.h - (rows - 1) * 14) // rows
        return pygame.Rect(GRID.x + (k % cols) * (w + 16), GRID.y + (k // cols) * (h + 14), w, h)

    def _build(self):
        self.item_buttons = {}
        items = self.items()
        for k, item in enumerate(items):
            r = self.tile_rect(k, len(items))
            self.item_buttons[item.id] = Button((r.right - 140, r.bottom - 50, 126, 40), "", lambda i=item: self._click(i),
                                                size=14, radius=8)

    def _click(self, item: shop.Item):
        s = self.app.settings
        try:
            if shop.owns(s, item.id):
                shop.equip(s, item.id)
                sfx.play("select")
                self.flash = (f"{item.name} equipped!", 2.0)
            elif self.confirm and self.confirm[0] == item.id:
                shop.buy(s, item.id)
                shop.equip(s, item.id)
                self.confirm = None
                sfx.play("round_win")
                sfx.play("coin")
                self.flash = (f"You bought {item.name}! It's equipped.", 2.5)
            else:
                if s.chip_bank < item.price:
                    raise shop.ShopError(f"You need {item.price - s.chip_bank} more chips. "
                                         "Play a game or try the slots!")
                self.confirm = (item.id, 3.0)
                sfx.play("click")
                return
        except shop.ShopError as e:
            sfx.play("error")
            self.flash = (str(e), 3.0)
            return
        s.save()
        theme.apply(s)

    def _done(self):
        self.app.settings.save()
        if self._back:
            self._back()
        else:
            from .menus import MenuScene
            self.app.go(MenuScene(self.app))

    def handle(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._done()
            return
        if self.btn_done.handle(event) or self.tabs.handle(event):
            return
        for b in self.item_buttons.values():
            if b.handle(event):
                return

    def update(self, dt: float):
        super().update(dt)
        if self.flash:
            self.flash = (self.flash[0], self.flash[1] - dt) if self.flash[1] > dt else None
        if self.confirm:
            self.confirm = (self.confirm[0], self.confirm[1] - dt) if self.confirm[1] > dt else None

    def draw(self, surf):
        s = self.app.settings
        backdrop(surf, self.clock)
        theme.logo(surf, "CARD SHOP", (theme.WIDTH // 2, 62), 54, angle=4)
        bank = pygame.Rect(40, 24, 250, 78)
        theme.panel(surf, bank)
        for k in range(3):
            theme.chip_stack(surf, (bank.x + 30 + k * 10, bank.bottom - 22), 13, theme.CHIP_COLORS[k], 3 - k)
        theme.ptext(surf, "CHIP BANK", (bank.x + 82, bank.y + 10), 14, theme.TEXT_DIM)
        theme.ptext(surf, f"{s.chip_bank:,}", (bank.x + 82, bank.bottom - 8), 30, theme.ACCENT, anchor="bottomleft")
        self.tabs.draw(surf)
        items = self.items()
        for k, item in enumerate(items):
            self._draw_tile(surf, item, self.tile_rect(k, len(items)))
        self.btn_done.draw(surf)
        msg = self.flash[0] if self.flash else "Skins only change how cards look on your screen. Buy once, keep forever."
        status_bar(surf, msg)

    def _draw_tile(self, surf, item: shop.Item, r: pygame.Rect):
        s = self.app.settings
        owned, on = shop.owns(s, item.id), shop.equipped(s, item)
        theme.panel(surf, r, edge=theme.ACCENT if on else theme.PANEL_EDGE, edge_w=3 if on else 2)
        # Preview
        ph = r.h - 90
        cw, ch = int(ph * 0.62 * 0.66), int(ph * 0.62)
        cx, cy = r.x + 20, r.y + 14
        if item.kind == "face":
            for n, card in enumerate((number(COLORS[0], 7), wild(), number(COLORS[1], 12))):
                img, _ = card_with_shadow(card, cw, ch, face=item.style)
                surf.blit(pygame.transform.rotate(img, 10 - n * 10), (cx + n * int(cw * 0.75), cy + abs(n - 1) * 4))
        else:
            for n in range(2):
                img, _ = card_with_shadow(None, cw, ch, back=item.style)
                surf.blit(pygame.transform.rotate(img, 8 - n * 14), (cx + n * int(cw * 0.8), cy + n * 4))
        tx = r.x + 30 + int(cw * 2.9)
        theme.ptext(surf, item.name, (tx, r.y + 16), 18, theme.ACCENT)
        for n, line in enumerate(_wrap_words(item.blurb, 20)):
            theme.text(surf, line, (tx, r.y + 44 + n * 18), 13, theme.TEXT_DIM, bold=False)
        # Price / state and the button
        b = self.item_buttons[item.id]
        if on:
            b.label, b.enabled, b.color, b.text_color = "EQUIPPED", False, "PANEL_LIGHT", "TEXT"
        elif owned:
            b.label, b.enabled, b.color, b.text_color = "EQUIP", True, "PANEL_LIGHT", "TEXT"
        elif self.confirm and self.confirm[0] == item.id:
            b.label, b.enabled, b.color, b.text_color = "CONFIRM?", True, "SUCCESS", "OUTLINE"
        else:
            b.label, b.enabled = f"BUY {item.price}", True
            b.color, b.text_color = ("ACCENT", "OUTLINE") if s.chip_bank >= item.price else ("PANEL_LIGHT", "TEXT_DIM")
        if owned:
            theme.ptext(surf, "OWNED" if not on else "IN USE", (r.x + 18, r.bottom - 36), 14,
                        theme.SUCCESS if on else theme.TEXT_DIM)
        else:
            theme.chip(surf, (r.x + 30, r.bottom - 26), 10, theme.ACCENT)
            theme.ptext(surf, f"{item.price}", (r.x + 46, r.bottom - 38), 20, theme.ACCENT)
        b.draw(surf)


def _wrap_words(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return lines + ([cur] if cur else [])
