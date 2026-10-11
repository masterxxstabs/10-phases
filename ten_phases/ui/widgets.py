"""Flat buttons and segmented controls."""

from __future__ import annotations

from typing import Callable

import pygame

from . import theme


class Button:
    def __init__(self, rect, label: str, on_click: Callable[[], None], color=theme.PANEL_LIGHT,
                 text_color=theme.TEXT, size: int = 20, radius: int = 12):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.on_click = on_click
        self.color = color
        self.text_color = text_color
        self.size = size
        self.radius = radius
        self.enabled = True
        self.visible = True
        self._pressed = False

    def handle(self, event) -> bool:
        if not (self.visible and self.enabled):
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(event.pos):
            self._pressed = True
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was = self._pressed
            self._pressed = False
            if was and self.rect.collidepoint(event.pos):
                self.on_click()
                return True
        return False

    def draw(self, surf):
        if not self.visible:
            return
        hover = self.enabled and self.rect.collidepoint(pygame.mouse.get_pos())
        color = self.color if self.enabled else theme.PANEL
        if hover:
            color = theme.lighten(color, 18)
        r = self.rect.move(0, 2) if self._pressed and hover else self.rect
        if self.enabled and not (self._pressed and hover):
            theme.rounded(surf, theme.darken(color, 40), self.rect.move(0, 4), self.radius)
        theme.rounded(surf, color, r, self.radius)
        tc = self.text_color if self.enabled else theme.TEXT_FAINT
        theme.text(surf, self.label, r.center, self.size, tc, anchor="center")


class Segmented:
    """A row of mutually exclusive options."""

    def __init__(self, rect, options: list[str], value: str, on_change: Callable[[str], None], size: int = 18):
        self.rect = pygame.Rect(rect)
        self.options = options
        self.value = value
        self.on_change = on_change
        self.size = size

    def _seg(self, i: int) -> pygame.Rect:
        w = self.rect.w / len(self.options)
        return pygame.Rect(int(self.rect.x + i * w), self.rect.y, int(w), self.rect.h)

    def handle(self, event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(event.pos):
            for i, opt in enumerate(self.options):
                if self._seg(i).collidepoint(event.pos):
                    self.value = opt
                    self.on_change(opt)
            return True
        return False

    def draw(self, surf):
        theme.rounded(surf, theme.BG_DARK, self.rect, 12)
        mouse = pygame.mouse.get_pos()
        for i, opt in enumerate(self.options):
            seg = self._seg(i).inflate(-8, -8)
            if opt == self.value:
                theme.rounded(surf, theme.ACCENT, seg, 9)
                color = theme.BG_DARK
            else:
                if seg.collidepoint(mouse):
                    theme.rounded(surf, theme.PANEL_HOVER, seg, 9)
                color = theme.TEXT
            theme.text(surf, opt, seg.center, self.size, color, anchor="center")
