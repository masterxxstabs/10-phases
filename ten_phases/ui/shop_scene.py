"""The card shop: buy card packs with your Chip Bank, and equip the skins you've collected."""

from __future__ import annotations

import math

import pygame

from .. import shop
from ..skins import RARITIES, RARITY_COLORS, SKINS
from . import pack_art, sfx, theme
from .card_art import card_with_shadow
from .menus import PRIMARY, Scene, backdrop, status_bar
from .pack_open import sample_card
from .widgets import Button, Segmented

GRID = pygame.Rect(40, 196, 1200, 476)
TABS = ["PACKS", "CARD FRONTS", "CARD BACKS"]


class ShopScene(Scene):
    def __init__(self, app, back=None, tab: str = "PACKS"):
        super().__init__(app)
        self._back = back
        self.tab = tab if tab in TABS else "PACKS"
        self.tabs = Segmented((290, 128, 700, 52), TABS, self.tab, self._set_tab, size=18)
        self.btn_done = Button((theme.WIDTH // 2 - 130, 694, 260, 54), "DONE", self._done, size=24, **PRIMARY)
        self.flash: tuple[str, float] | None = None
        self.confirm: tuple[str, float] | None = None   # pack awaiting a second click to buy
        self.pack_buttons: dict[str, Button] = {}
        self.page = 0
        self.owned_only = False
        self.btn_prev = Button((40, 694, 90, 54), "<", lambda: self._turn(-1), size=26)
        self.btn_next = Button((theme.WIDTH - 130, 694, 90, 54), ">", lambda: self._turn(1), size=26)
        self.btn_owned = Button((146, 694, 230, 54), "", self._toggle_owned, size=16)
        self._build()

    def _set_tab(self, tab: str):
        self.tab = tab
        self.confirm = None
        self.page = 0
        self._build()

    PER_PAGE = 18

    def pages(self) -> int:
        return max(1, -(-len(self.all_skins()) // self.PER_PAGE))

    def _turn(self, step: int):
        self.page = (self.page + step) % self.pages()

    def _toggle_owned(self):
        self.owned_only = not self.owned_only
        self.page = 0

    # ------------------------------------------------------------------ layout

    def pack_rect(self, k: int) -> pygame.Rect:
        w = (GRID.w - 2 * 20) // 3
        return pygame.Rect(GRID.x + k * (w + 20), GRID.y, w, GRID.h)

    def all_skins(self):
        kind = "face" if self.tab == "CARD FRONTS" else "back"
        out = [s for s in SKINS if s.kind == kind]
        if self.owned_only:
            out = [s for s in out if shop.owns(self.app.settings, s.id)]
        return out

    def skins(self):
        """The skins on the current page."""
        self.page = min(self.page, self.pages() - 1)
        return self.all_skins()[self.page * self.PER_PAGE:(self.page + 1) * self.PER_PAGE]

    def tile_rect(self, k: int) -> pygame.Rect:
        cols, rows = 6, 3
        w = (GRID.w - (cols - 1) * 12) // cols
        h = (GRID.h - (rows - 1) * 12) // rows
        return pygame.Rect(GRID.x + (k % cols) * (w + 12), GRID.y + (k // cols) * (h + 12), w, h)

    def _build(self):
        self.pack_buttons = {}
        if self.tab == "PACKS":
            for k, pack in enumerate(shop.PACKS):
                r = self.pack_rect(k)
                self.pack_buttons[pack.id] = Button((r.x + 24, r.bottom - 64, r.w - 48, 48), "",
                                                    lambda p=pack: self._buy(p), size=20)

    # ------------------------------------------------------------------ actions

    def _buy(self, pack):
        s = self.app.settings
        if s.chip_bank < pack.price:
            sfx.play("error")
            self.flash = (f"You need {pack.price - s.chip_bank} more chips. Play a game or try the slots!", 3.0)
            return
        if not (self.confirm and self.confirm[0] == pack.id):
            self.confirm = (pack.id, 3.0)
            return
        self.confirm = None
        pulls = shop.buy_pack(s, pack.id)
        s.save()
        sfx.play("coin")
        from .pack_open import PackOpenScene
        back = self._back
        self.app.go(PackOpenScene(self.app, pack.id, pulls,
                                  lambda: self.app.go(ShopScene(self.app, back=back, tab="PACKS"))))

    def _tile_click(self, skin):
        s = self.app.settings
        if shop.owns(s, skin.id):
            if shop.equipped(s, skin):
                return
            shop.equip(s, skin.id)
            s.save()
            theme.apply(s)
            sfx.play("select")
            self.flash = (f"{skin.name} equipped!", 2.0)
        else:
            sfx.play("error")
            self.flash = (f"{skin.name} is a {skin.rarity.lower()} skin. Find it in card packs!", 3.0)

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
        if self.tab != "PACKS":
            if self.btn_prev.handle(event) or self.btn_next.handle(event) or self.btn_owned.handle(event):
                return
            if event.type == pygame.MOUSEWHEEL and event.y:
                self._turn(-1 if event.y > 0 else 1)
                return
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                self._turn(-1 if event.key == pygame.K_LEFT else 1)
                return
        for b in self.pack_buttons.values():
            if b.handle(event):
                return
        if self.tab != "PACKS" and event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            for k, skin in enumerate(self.skins()):
                if self.tile_rect(k).collidepoint(event.pos):
                    self._tile_click(skin)
                    return

    def update(self, dt: float):
        super().update(dt)
        if self.flash:
            self.flash = (self.flash[0], self.flash[1] - dt) if self.flash[1] > dt else None
        if self.confirm:
            self.confirm = (self.confirm[0], self.confirm[1] - dt) if self.confirm[1] > dt else None

    # ------------------------------------------------------------------ drawing

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
        owned, total = shop.collection(s)
        col = pygame.Rect(theme.WIDTH - 290, 24, 250, 78)
        theme.panel(surf, col)
        theme.ptext(surf, "COLLECTION", (col.x + 16, col.y + 10), 14, theme.TEXT_DIM)
        theme.ptext(surf, f"{owned}/{total}", (col.x + 16, col.bottom - 8), 30, theme.ACCENT, anchor="bottomleft")
        bar = pygame.Rect(col.x + 140, col.y + 14, 94, 12)
        pygame.draw.rect(surf, theme.INNER, bar, border_radius=7)
        pygame.draw.rect(surf, theme.SUCCESS, (bar.x, bar.y, int(bar.w * owned / total), bar.h), border_radius=7)
        self.tabs.draw(surf)
        if self.tab == "PACKS":
            for k, pack in enumerate(shop.PACKS):
                self._draw_pack_tile(surf, pack, self.pack_rect(k))
            msg = "Every pack holds 3 skins. Duplicates turn back into chips."
        else:
            for k, skin in enumerate(self.skins()):
                self._draw_skin_tile(surf, skin, self.tile_rect(k))
            if not self.skins():
                theme.ptext(surf, "Nothing here yet - open some packs!", GRID.center, 24, theme.TEXT_DIM, anchor="center")
            msg = "Click a skin you own to use it. Other players see your skins in multiplayer too!"
            self.btn_owned.label = "OWNED ONLY: ON" if self.owned_only else "OWNED ONLY: OFF"
            self.btn_owned.color = "SUCCESS" if self.owned_only else "PANEL_LIGHT"
            self.btn_owned.text_color = "OUTLINE" if self.owned_only else "TEXT"
            for b in (self.btn_prev, self.btn_next, self.btn_owned):
                b.draw(surf)
            theme.ptext(surf, f"PAGE {self.page + 1}/{self.pages()}", (theme.WIDTH - 150, 721), 18, theme.TEXT_DIM,
                        anchor="midright")
        self.btn_done.draw(surf)
        status_bar(surf, self.flash[0] if self.flash else msg)

    def _draw_pack_tile(self, surf, pack, r: pygame.Rect):
        s = self.app.settings
        hover = r.collidepoint(pygame.mouse.get_pos())
        theme.panel(surf, r, edge=pack.colors[0] if hover else theme.PANEL_EDGE, edge_w=3 if hover else 2)
        bob = math.sin(self.clock * 2 + r.x * 0.01) * 5
        img = pack_art.pack_surface(pack, 170, 250)
        if hover:
            img = pack_art.sheen(img, (self.clock / 1.6) % 1.0)
        prect = img.get_rect(center=(r.x + 104, r.y + 190 + bob))
        g = pack_art.glow(120, theme.darken(pack.colors[0], 70 if not hover else 30))
        surf.blit(g, g.get_rect(center=prect.center), special_flags=pygame.BLEND_RGB_ADD)
        surf.blit(img, prect)
        tx = r.x + 196
        theme.ptext(surf, pack.name, (r.centerx, r.y + 12), 24, pack.colors[0], anchor="midtop")
        theme.ptext(surf, "CHANCE OF AT", (tx + 10, r.y + 76), 14, theme.TEXT_DIM)
        theme.ptext(surf, "LEAST ONE:", (tx + 10, r.y + 92), 14, theme.TEXT_DIM)
        odds = shop.odds_percent(pack)
        for n, rarity in enumerate(RARITIES):
            y = r.y + 124 + n * 32
            pygame.draw.circle(surf, RARITY_COLORS[rarity], (tx + 17, y + 9), 7)
            theme.ptext(surf, rarity, (tx + 30, y), 16, RARITY_COLORS[rarity])
            pct = odds[rarity]
            theme.ptext(surf, f"{pct:.0f}%" if pct >= 1 or pct == 0 else f"{pct:.1f}%", (r.right - 16, y), 16,
                        theme.TEXT, anchor="topright")
        for n, line in enumerate(_wrap_words(pack.blurb, 30)):
            theme.ptext(surf, line, (r.centerx, r.bottom - 124 + n * 22), 16, theme.TEXT_DIM, anchor="midtop")
        b = self.pack_buttons[pack.id]
        afford = s.chip_bank >= pack.price
        if self.confirm and self.confirm[0] == pack.id:
            b.label, b.color, b.text_color = f"TAP AGAIN TO BUY ({pack.price})", "SUCCESS", "OUTLINE"
        else:
            b.label = f"OPEN FOR {pack.price}"
            b.color, b.text_color = ("ACCENT", "OUTLINE") if afford else ("PANEL_LIGHT", "TEXT_DIM")
        b.draw(surf)
        theme.chip(surf, (b.rect.x + 22, b.rect.centery), 10, theme.ACCENT if not afford else theme.OUTLINE)

    def _draw_skin_tile(self, surf, skin, r: pygame.Rect):
        s = self.app.settings
        owned, on = shop.owns(s, skin.id), shop.equipped(s, skin)
        hover = r.collidepoint(pygame.mouse.get_pos())
        edge = theme.ACCENT if on else skin.color if hover else theme.PANEL_EDGE
        theme.panel(surf, r, fill="PANEL_LIGHT" if hover and owned else "PANEL", edge=edge, edge_w=3 if on else 2)
        pygame.draw.rect(surf, skin.color, (r.x + 8, r.y + 6, r.w - 16, 5), border_radius=3)
        cw, ch = 70, 105
        card = sample_card(skin) if skin.kind == "face" else None
        img, _ = card_with_shadow(card, cw, ch, face=skin.style if card else None,
                                  back=skin.style if card is None else None)
        pos = (r.x + 12, r.y + 20 - (4 if hover and owned else 0))
        shiny = "foil" in skin.blurb.lower() or skin.rarity in ("EPIC", "LEGENDARY")
        if shiny:
            t = (self.clock * 0.6 + r.x * 0.0013 + r.y * 0.002) % 1.6
            if hover or t < 1.0:
                img = pack_art.sheen(img, (self.clock * 0.9) % 1.0 if hover else t, alpha=100)
        if owned:
            surf.blit(img, pos)
        else:
            dim = img.copy()
            dim.fill((90, 90, 110, 255), special_flags=pygame.BLEND_RGBA_MULT)
            surf.blit(dim, pos)
            lock = pygame.Rect(0, 0, 26, 20)
            lock.center = (pos[0] + cw // 2, pos[1] + ch // 2 + 6)
            pygame.draw.arc(surf, theme.TEXT, lock.move(0, -14).inflate(-8, 4), 0, math.pi, 4)
            pygame.draw.rect(surf, theme.TEXT, lock, border_radius=4)
            pygame.draw.circle(surf, theme.OUTLINE, lock.center, 3)
        tx = r.x + cw + 22
        for n, line in enumerate(_wrap_words(skin.name, 9)[:2]):
            theme.ptext(surf, line, (tx, r.y + 18 + n * 20), 17, theme.TEXT if owned else theme.TEXT_DIM)
        theme.ptext(surf, skin.rarity, (tx, r.y + 64), 14, skin.color)
        if on:
            state, color = "IN USE", theme.SUCCESS
        elif owned:
            state, color = "OWNED", theme.TEXT_DIM
        else:
            state, color = "IN PACKS", theme.TEXT_FAINT
        theme.ptext(surf, state, (tx, r.bottom - 30), 15, color)


def _wrap_words(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return lines + ([cur] if cur else [])
