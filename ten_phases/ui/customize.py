"""Customize screen: table colour, accent, card back, card palette, text style, sparkles."""

from __future__ import annotations

import colorsys

import pygame

from ..cards import Color, number, skip, wild
from ..settings import TEXT_STYLES
from . import theme
from .card_art import card_with_shadow
from .menus import PRIMARY, Scene, backdrop, status_bar
from .widgets import Button, HueBar, Segmented, Swatches

LEFT = pygame.Rect(40, 104, 712, 534)
RIGHT = pygame.Rect(782, 104, 458, 610)
X = LEFT.x + 26
W = LEFT.w - 52


class CustomizeScene(Scene):
    def __init__(self, app, back=None):
        super().__init__(app)
        self._back = back
        self._build()

    # ---------------------------------------------------------------- controls

    def _build(self):
        s = self.app.settings
        current = theme.hex_to_rgb(s.table_color)
        preset = next((n for n, c in theme.TABLE_PRESETS.items() if theme.rgb_to_hex(c) == s.table_color), None)
        hue = None if preset else colorsys.rgb_to_hls(*(c / 255 for c in current))[0]

        self.table = Swatches((X, LEFT.y + 46, W, 44), theme.TABLE_PRESETS, preset, self._pick_table, radius=21)
        self.hue = HueBar((X + 96, LEFT.y + 106, W - 96, 22), hue, self._pick_hue)
        self.accent = Swatches((X, LEFT.y + 180, W * 2 // 3, 40), theme.ACCENT_PRESETS, s.accent,
                               self._setter("accent"), radius=19)
        self.back_color = Swatches((X, LEFT.y + 272, W * 2 // 3, 40), theme.CARD_BACK_PRESETS, s.card_back,
                                   self._setter("card_back"), radius=19)
        self.palette = Segmented((X, LEFT.y + 368, W, 50), list(theme.CARD_PALETTES), s.card_palette,
                                 self._setter("card_palette"))
        self.text_style = Segmented((X, LEFT.y + 464, W // 2 - 10, 50), list(TEXT_STYLES), s.text_style,
                                    self._setter("text_style"))
        self.sparkles = Segmented((X + W // 2 + 10, LEFT.y + 464, W // 2 - 10, 50), ["On", "Off"],
                                  "On" if s.sparkles else "Off", self._setter("sparkles", lambda v: v == "On"))
        self.controls = [self.table, self.hue, self.accent, self.back_color, self.palette, self.text_style,
                         self.sparkles]
        self.buttons = [
            Button((LEFT.x, 656, 340, 58), "RESET LOOK", self._reset, size=22),
            Button((LEFT.right - 340, 656, 340, 58), "DONE", self._done, size=24, **PRIMARY),
        ]

    def _apply(self):
        theme.apply(self.app.settings)

    def _setter(self, name, conv=lambda v: v):
        def set_value(v):
            setattr(self.app.settings, name, conv(v))
            self._apply()
        return set_value

    def _pick_table(self, name: str):
        self.app.settings.table_color = theme.rgb_to_hex(theme.TABLE_PRESETS[name])
        self.hue.hue = None
        self._apply()

    def _pick_hue(self, hue: float):
        self.app.settings.table_color = theme.rgb_to_hex(theme.hue_color(hue))
        self.table.value = None
        self._apply()

    def _reset(self):
        self.app.settings.reset_look()
        self._apply()
        self._build()

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
        for b in self.buttons:
            if b.handle(event):
                return
        for c in self.controls:
            if c.handle(event):
                return

    # ---------------------------------------------------------------- drawing

    def draw(self, surf):
        backdrop(surf, self.clock)
        theme.logo(surf, "CUSTOMIZE", (theme.WIDTH // 2, 58), 50, angle=4)
        theme.panel(surf, LEFT)

        def label(msg, y, sub=None):
            theme.ptext(surf, msg, (X, y), 20, theme.ACCENT)
            if sub:
                theme.ptext(surf, sub, (X + theme.pixel_width(msg, 20) + 14, y + 6), 13, theme.TEXT_DIM)

        label("TABLE COLOR", LEFT.y + 14)
        theme.ptext(surf, "CUSTOM", (X, LEFT.y + 108), 14, theme.TEXT_DIM)
        label("ACCENT", LEFT.y + 146, "highlights and buttons")
        label("CARD BACK", LEFT.y + 240)
        label("CARD COLORS", LEFT.y + 332, "Colorblind: easier to tell apart")
        label("TEXT", LEFT.y + 428)
        theme.ptext(surf, "SPARKLES", (X + W // 2 + 10, LEFT.y + 428), 20, theme.ACCENT)
        for c in self.controls:
            c.draw(surf)
        for b in self.buttons:
            b.draw(surf)
        self._draw_preview(surf)
        status_bar(surf, "Changes show up right away. Press DONE to save.")

    def _draw_preview(self, surf):
        theme.panel(surf, RIGHT)
        theme.ptext(surf, "PREVIEW", (RIGHT.x + 20, RIGHT.y + 14), 18, theme.TEXT_DIM)

        # An opponent box
        box = pygame.Rect(RIGHT.x + 20, RIGHT.y + 48, RIGHT.w - 40, 150)
        theme.panel(surf, box, edge=theme.ACCENT, edge_w=3)
        theme.face(surf, (box.x + 30, box.y + 30), 22, 1)
        theme.ptext(surf, "ZACH", (box.x + 60, box.y + 8), 20)
        theme.ptext(surf, "10", (box.right - 14, box.y + 8), 18, anchor="topright")
        theme.mini_card_icon(surf, (box.right - 58, box.y + 9))
        theme.ptext(surf, "23", (box.right - 14, box.y + 32), 18, theme.ACCENT, anchor="topright")
        theme.chip(surf, (box.right - 50, box.y + 42), 9, theme.ACCENT)
        inner = pygame.Rect(box.x + 8, box.y + 60, box.w - 16, 82)
        theme.rounded(surf, theme.INNER, inner, 8)
        theme.ptext(surf, "PHASE 2", (inner.x + 10, inner.y + 8), 16, theme.ACCENT)
        theme.ptext(surf, "SET OF 3", (inner.x + 10, inner.y + 34), 14, theme.TEXT)
        theme.ptext(surf, "2/3", (inner.x + 10, inner.y + 54), 16, theme.SUCCESS)
        for k, c in enumerate([number(Color.GREEN, 9), number(Color.RED, 9)]):
            img, _ = card_with_shadow(c, 44, 66)
            surf.blit(img, (inner.x + 130 + k * 50, inner.y + 8))
        ghost = pygame.Rect(inner.x + 230, inner.y + 8, 44, 66)
        theme.rounded(surf, theme.PANEL_LIGHT, ghost, 6, 2)
        theme.ptext(surf, "?", ghost.center, 16, theme.PANEL_LIGHT, None, anchor="center")

        # Cards
        cards = [number(Color.RED, 7), number(Color.BLUE, 3), number(Color.GREEN, 11), number(Color.YELLOW, 5),
                 wild(), skip(), None]
        step = (RIGHT.w - 40 - 72) / (len(cards) - 1)
        for k, c in enumerate(cards):
            img, _ = card_with_shadow(c, 72, 108)
            surf.blit(img, (RIGHT.x + 20 + k * step, RIGHT.y + 222))

        # Pot and buttons
        y = RIGHT.y + 366
        for k in range(3):
            theme.chip_stack(surf, (RIGHT.x + 44 + k * 40, y + 40), 15, theme.CHIP_COLORS[k], 3)
        theme.ptext(surf, "x6", (RIGHT.x + 180, y + 16), 28, theme.ACCENT)
        sample = pygame.Rect(RIGHT.x + 250, y, 188, 48)
        theme.panel(surf, sample, theme.ACCENT)
        theme.ptext(surf, "LAY DOWN", sample.center, 18, theme.OUTLINE, None, anchor="center")
        sample2 = pygame.Rect(RIGHT.x + 250, y + 60, 188, 44)
        theme.panel(surf, sample2, theme.PANEL_LIGHT)
        theme.ptext(surf, "DISCARD", sample2.center, 16, anchor="center")

        theme.logo(surf, "10 PHASES", (RIGHT.centerx, RIGHT.bottom - 70), 44, angle=6)
