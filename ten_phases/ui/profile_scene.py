"""Your profile: name, picture, hover-card background, name colour, and your level."""

from __future__ import annotations

import pygame

from .. import profile
from ..levels import progress
from ..net.protocol import clean_name
from . import profile_art, sfx, theme
from .menus import PRIMARY, Scene, backdrop, status_bar
from .widgets import Button, Segmented, TextInput

CARD = pygame.Rect(40, 112, 430, 560)
GRID = pygame.Rect(500, 186, 740, 486)
TABS = ["PICTURES", "BACKGROUNDS", "NAME COLOR"]


class ProfileScene(Scene):
    def __init__(self, app, back=None):
        super().__init__(app)
        self._back = back
        s = app.settings
        self.tab = "PICTURES"
        self.tabs = Segmented((GRID.x, 118, GRID.w, 52), TABS, self.tab, self._set_tab, size=16)
        self.name = TextInput((CARD.x + 24, CARD.bottom - 140, CARD.w - 48, 50), s.player_name, max_len=10,
                              placeholder="YOUR NAME", on_enter=self._save_name)
        self.btn_done = Button((theme.WIDTH // 2 + 10, 700, 260, 54), "DONE", self._done, size=22, **PRIMARY)
        self.btn_shop = Button((theme.WIDTH // 2 - 270, 700, 260, 54), "SHOP", self._shop, size=22)
        self.flash: tuple[str, float] | None = None
        self.picked_at = -10.0

    # ---------------------------------------------------------------- choices

    def _set_tab(self, tab: str):
        self.tab = tab
        self.tabs.value = tab

    def items(self) -> list:
        if self.tab == "PICTURES":
            return list(profile.AVATARS)
        if self.tab == "BACKGROUNDS":
            return list(profile.BANNERS)
        return list(profile.NAME_COLORS)

    def tile_rect(self, k: int) -> pygame.Rect:
        if self.tab == "PICTURES":
            cols, rows = 7, 4
        elif self.tab == "BACKGROUNDS":
            cols, rows = 4, 6
        else:
            cols, rows = 4, 3
        w = (GRID.w - (cols - 1) * 10) // cols
        h = (GRID.h - (rows - 1) * 10) // rows
        return pygame.Rect(GRID.x + (k % cols) * (w + 10), GRID.y + (k // cols) * (h + 10), w, h)

    def _pick(self, item):
        s = self.app.settings
        try:
            if isinstance(item, profile.Cosmetic):
                if not profile.owns(s, item.id):
                    if item.level:
                        raise profile.ProfileError(f"{item.name} unlocks at level {item.level}.")
                    raise profile.ProfileError(f"Buy {item.name} in the SHOP ({item.price} chips).")
                profile.equip(s, item.id)
            else:
                profile.set_color(s, item[0])
        except profile.ProfileError as e:
            sfx.play("error")
            self.flash = (str(e), 3.0)
            return
        s.save()
        self.picked_at = self.clock
        sfx.play("select")

    def _save_name(self):
        name = clean_name(self.name.value)
        self.name.value = name
        self.name.focused = False
        self.app.settings.player_name = name
        self.app.settings.save()

    def _done(self):
        self._save_name()
        if self._back:
            self._back()
        else:
            from .menus import MenuScene
            self.app.go(MenuScene(self.app))

    def _shop(self):
        self._save_name()
        from .shop_scene import ShopScene
        tab = "BACKGROUNDS" if self.tab == "BACKGROUNDS" else "PICTURES"
        self.app.go(ShopScene(self.app, back=lambda: self.app.go(ProfileScene(self.app, self._back)), tab=tab))

    # ---------------------------------------------------------------- input

    def handle(self, event):
        if self.name.handle(event):
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._done()
            return
        if self.btn_done.handle(event) or self.btn_shop.handle(event) or self.tabs.handle(event):
            return
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            for k, item in enumerate(self.items()):
                if self.tile_rect(k).collidepoint(event.pos):
                    self._pick(item)
                    return

    def update(self, dt: float):
        super().update(dt)
        if self.flash:
            self.flash = (self.flash[0], self.flash[1] - dt) if self.flash[1] > dt else None

    # ---------------------------------------------------------------- drawing

    def draw(self, surf):
        s = self.app.settings
        backdrop(surf, self.clock)
        theme.logo(surf, "PROFILE", (theme.WIDTH // 2, 56), 52, angle=4)
        self._draw_card(surf)
        self.tabs.draw(surf)
        for k, item in enumerate(self.items()):
            r = self.tile_rect(k)
            if self.tab == "PICTURES":
                self._avatar_tile(surf, item, r)
            elif self.tab == "BACKGROUNDS":
                self._banner_tile(surf, item, r)
            else:
                self._color_tile(surf, item, r)
        self.btn_shop.draw(surf)
        self.btn_done.draw(surf)
        hint = {"PICTURES": "Pick a picture. Get more in the SHOP, or by levelling up!",
                "BACKGROUNDS": "Your background shows on your hover card and in lobbies.",
                "NAME COLOR": "The colour of your name at the table. Gold and Rainbow unlock with levels."}[self.tab]
        status_bar(surf, self.flash[0] if self.flash else f"{hint}   Chip Bank: {s.chip_bank:,}")

    def _draw_card(self, surf):
        """A preview of your hover card, plus your level."""
        s = self.app.settings
        prof = profile.my_profile(s)
        profile_art.panel(surf, CARD, prof["b"], self.clock)
        age = self.clock - self.picked_at
        pop = 1 + 0.15 * max(0.0, 1 - age / 0.3)
        profile_art.avatar(surf, (CARD.centerx, CARD.y + 110), int(72 * pop), prof, 0)
        name = s.player_name or "PLAYER"
        name_r = theme.ptext(surf, name, (CARD.centerx, CARD.y + 212), 34, profile_art.name_rgb(prof, self.clock),
                             anchor="center")
        profile_art.name_tag(surf, name_r, prof, 18)
        level, into, need = progress(s.xp)
        profile_art.level_badge(surf, (CARD.centerx, CARD.y + 258), level, 22)
        bar = pygame.Rect(CARD.x + 40, CARD.y + 298, CARD.w - 80, 18)
        pygame.draw.rect(surf, theme.OUTLINE, bar.move(0, 2), border_radius=9)
        pygame.draw.rect(surf, (50, 60, 90), bar, border_radius=9)
        fill = bar.copy()
        fill.w = max(10, int(bar.w * into / max(1, need)))
        pygame.draw.rect(surf, (110, 220, 255), fill, border_radius=9)
        theme.ptext(surf, f"{into:,} / {need:,} XP TO LEVEL {level + 1}", (CARD.centerx, bar.bottom + 18), 14,
                    theme.TEXT, anchor="center")
        theme.ptext(surf, f"TOTAL XP {s.xp:,}", (CARD.centerx, bar.bottom + 42), 13, theme.TEXT_DIM, anchor="center")
        theme.ptext(surf, "NAME (MULTIPLAYER)", (CARD.x + 24, self.name.rect.y - 26), 14, theme.ACCENT)
        self.name.draw(surf)
        theme.ptext(surf, "XP: play cards, win rounds, finish games", (CARD.centerx, CARD.bottom - 50), 12,
                    theme.TEXT_DIM, anchor="center")
        theme.ptext(surf, "Level-ups unlock prizes!", (CARD.centerx, CARD.bottom - 30), 12, theme.TEXT_DIM,
                    anchor="center")

    def _state(self, item) -> tuple[str, tuple]:
        s = self.app.settings
        if profile.equipped(s, item):
            return "IN USE", theme.SUCCESS
        if profile.owns(s, item.id):
            return "", theme.TEXT_DIM
        if item.level:
            return f"LV {item.level}", theme.INFO
        return f"{item.price}", theme.ACCENT

    def _tile_bg(self, surf, r, on, owned):
        hover = r.collidepoint(pygame.mouse.get_pos())
        edge = theme.ACCENT if on else theme.CARD_WHITE if hover and owned else theme.PANEL_EDGE
        theme.panel(surf, r, fill="PANEL_LIGHT" if hover and owned else "PANEL", edge=edge, edge_w=3 if on else 2)
        return hover

    def _avatar_tile(self, surf, item, r):
        s = self.app.settings
        owned, on = profile.owns(s, item.id), profile.equipped(s, item)
        hover = self._tile_bg(surf, r, on, owned)
        img = pygame.Surface((80, 80), pygame.SRCALPHA)
        profile_art.avatar(img, (40, 38), 34, {"a": item.style}, 0)
        if not owned:
            img.fill((110, 110, 130, 255), special_flags=pygame.BLEND_RGBA_MULT)
        surf.blit(img, img.get_rect(center=(r.centerx, r.y + 46 - (3 if hover and owned else 0))))
        state, color = self._state(item)
        label = state or item.name
        if not owned and not item.level:
            theme.chip(surf, (r.centerx - theme.pixel_width(label, 13) // 2 - 10, r.bottom - 16), 7, color)
        theme.ptext(surf, label[:12], (r.centerx + (6 if not owned and not item.level else 0), r.bottom - 16), 13,
                    color if state else theme.TEXT, anchor="center")

    def _banner_tile(self, surf, item, r):
        s = self.app.settings
        owned, on = profile.owns(s, item.id), profile.equipped(s, item)
        self._tile_bg(surf, r, on, owned)
        prev = pygame.Rect(r.x + 6, r.y + 6, r.w - 12, r.h - 30)
        profile_art.panel(surf, prev, item.style, self.clock, edge=theme.OUTLINE, edge_w=2)
        if not owned:
            shade = pygame.Surface(prev.size, pygame.SRCALPHA)
            shade.fill((0, 0, 0, 130))
            surf.blit(shade, prev)
        state, color = self._state(item)
        theme.ptext(surf, item.name, (r.x + 10, r.bottom - 20), 12, theme.TEXT if owned else theme.TEXT_DIM)
        if state:
            theme.ptext(surf, state, (r.right - 10, r.bottom - 20), 12, color, anchor="topright")

    def _color_tile(self, surf, item, r):
        s = self.app.settings
        name, _, lvl = item
        unlocked, on = profile.color_unlocked(s, name), s.name_color == name
        self._tile_bg(surf, r, on, unlocked)
        rgb = profile_art.swatch_rgb(name, self.clock)
        sw = pygame.Rect(r.x + 16, r.y + 16, 46, 46)
        pygame.draw.rect(surf, theme.OUTLINE, sw.move(0, 3), border_radius=10)
        pygame.draw.rect(surf, rgb, sw, border_radius=10)
        theme.ptext(surf, s.player_name or "PLAYER", (r.x + 76, r.y + 22), 20, rgb if unlocked else theme.TEXT_FAINT)
        theme.ptext(surf, name, (r.x + 76, r.y + 50), 13, theme.TEXT_DIM)
        if on:
            theme.ptext(surf, "IN USE", (r.x + 16, r.bottom - 30), 14, theme.SUCCESS)
        elif not unlocked:
            theme.ptext(surf, f"UNLOCKS AT LEVEL {lvl}", (r.x + 16, r.bottom - 30), 13, theme.INFO)
