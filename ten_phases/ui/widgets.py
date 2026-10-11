"""Handheld-style buttons and segmented controls."""

from __future__ import annotations

from typing import Callable

import pygame

from . import sfx, theme


class Button:
    def __init__(self, rect, label: str, on_click: Callable[[], None], color="PANEL_LIGHT",
                 text_color="TEXT", size: int = 20, radius: int = 10):
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
                sfx.play("click")
                self.on_click()
                return True
        return False

    def draw(self, surf):
        if not self.visible:
            return
        hover = self.enabled and self.rect.collidepoint(pygame.mouse.get_pos())
        color = theme.resolve(self.color) if self.enabled else theme.INNER
        if hover:
            color = theme.lighten(color, 22)
        pressed = self._pressed and hover
        r = self.rect.move(-2, 3) if pressed else self.rect
        theme.panel(surf, r, color, theme.PANEL_EDGE if self.enabled else theme.PANEL_LIGHT, self.radius,
                    shadow=self.enabled and not pressed)
        tc = theme.resolve(self.text_color) if self.enabled else theme.TEXT_FAINT
        outline = None if tc == theme.OUTLINE else theme.OUTLINE
        theme.ptext(surf, self.label, r.center, self.size, tc, outline, anchor="center")


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
                    sfx.play("select")
                    self.value = opt
                    self.on_change(opt)
            return True
        return False

    def draw(self, surf):
        theme.panel(surf, self.rect, theme.INNER, radius=10)
        mouse = pygame.mouse.get_pos()
        for i, opt in enumerate(self.options):
            seg = self._seg(i).inflate(-10, -10)
            if opt == self.value:
                theme.rounded(surf, theme.ACCENT, seg, 7)
                theme.rounded(surf, theme.OUTLINE, seg, 7, 2)
                theme.ptext(surf, opt, seg.center, self.size, theme.OUTLINE, None, anchor="center")
            else:
                if seg.collidepoint(mouse):
                    theme.rounded(surf, theme.PANEL_HOVER, seg, 7)
                theme.ptext(surf, opt, seg.center, self.size, theme.TEXT, anchor="center")


class Swatches:
    """A row of colour circles; one is selected."""

    def __init__(self, rect, options: dict[str, tuple], value: str | None, on_change: Callable[[str], None],
                 radius: int = 20):
        self.rect = pygame.Rect(rect)
        self.options = options
        self.value = value
        self.on_change = on_change
        self.radius = radius

    def _centers(self):
        n = len(self.options)
        step = min(self.radius * 2 + 16, (self.rect.w - self.radius * 2) / max(1, n - 1))
        for k, name in enumerate(self.options):
            yield name, (int(self.rect.x + self.radius + k * step), self.rect.centery)

    def handle(self, event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for name, (cx, cy) in self._centers():
                if (event.pos[0] - cx) ** 2 + (event.pos[1] - cy) ** 2 <= (self.radius + 4) ** 2:
                    sfx.play("select")
                    self.value = name
                    self.on_change(name)
                    return True
        return False

    def draw(self, surf):
        mouse = pygame.mouse.get_pos()
        hovered = None
        for name, (cx, cy) in self._centers():
            r = self.radius
            if (mouse[0] - cx) ** 2 + (mouse[1] - cy) ** 2 <= (r + 4) ** 2:
                r += 2
                hovered = name
            pygame.draw.circle(surf, theme.OUTLINE, (cx, cy + 3), r + 2)
            pygame.draw.circle(surf, theme.CARD_WHITE, (cx, cy), r + 2)
            pygame.draw.circle(surf, self.options[name], (cx, cy), r - 1)
            if name == self.value:
                pygame.draw.circle(surf, theme.ACCENT, (cx, cy), r + 7, 4)
        if hovered:
            theme.ptext(surf, hovered.upper(), (self.rect.right, self.rect.y - 10), 12, theme.TEXT_DIM,
                        anchor="topright")


class HueBar:
    """A rainbow strip: click anywhere to pick a custom hue."""

    def __init__(self, rect, hue: float | None, on_change: Callable[[float], None]):
        self.rect = pygame.Rect(rect)
        self.hue = hue
        self.on_change = on_change
        self._drag = False
        self._strip = None

    def _set(self, x: int):
        self.hue = max(0.0, min(0.999, (x - self.rect.x) / self.rect.w))
        self.on_change(self.hue)

    def handle(self, event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.inflate(0, 10).collidepoint(event.pos):
            self._drag = True
            sfx.play("select")
            self._set(event.pos[0])
            return True
        if event.type == pygame.MOUSEMOTION and self._drag:
            self._set(event.pos[0])
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self._drag:
            self._drag = False
            return True
        return False

    def draw(self, surf):
        if self._strip is None:
            self._strip = pygame.Surface(self.rect.size)
            for x in range(self.rect.w):
                pygame.draw.line(self._strip, theme.hue_color(x / self.rect.w), (x, 0), (x, self.rect.h))
        theme.rounded(surf, theme.OUTLINE, self.rect.move(0, 3).inflate(4, 4), 8)
        theme.rounded(surf, theme.CARD_WHITE, self.rect.inflate(4, 4), 8)
        surf.blit(self._strip, self.rect)
        if self.hue is not None:
            x = self.rect.x + int(self.hue * self.rect.w)
            knob = pygame.Rect(x - 6, self.rect.y - 6, 12, self.rect.h + 12)
            theme.rounded(surf, theme.CARD_WHITE, knob, 4)
            theme.rounded(surf, theme.OUTLINE, knob, 4, 2)


def copy_text(value: str) -> bool:
    """Put text on the system clipboard. Returns False if the platform doesn't allow it."""
    try:
        pygame.scrap.put_text(value)
        return True
    except (AttributeError, pygame.error):
        pass
    try:
        if not pygame.scrap.get_init():
            pygame.scrap.init()
        pygame.scrap.put(pygame.SCRAP_TEXT, value.encode())
        return True
    except (AttributeError, pygame.error):
        return False


def paste_text() -> str:
    try:
        return pygame.scrap.get_text() or ""
    except (AttributeError, pygame.error):
        pass
    try:
        if not pygame.scrap.get_init():
            pygame.scrap.init()
        data = pygame.scrap.get(pygame.SCRAP_TEXT)
        return data.decode(errors="ignore").rstrip("\x00") if data else ""
    except (AttributeError, pygame.error):
        return ""


class TextInput:
    """A one-line text box. Click to focus; supports typing, backspace and Ctrl+V."""

    def __init__(self, rect, value: str = "", max_len: int = 20, placeholder: str = "",
                 allowed: Callable[[str], bool] | None = None, upper: bool = True, size: int = 20,
                 on_enter: Callable[[], None] | None = None):
        self.rect = pygame.Rect(rect)
        self.value = value
        self.max_len = max_len
        self.placeholder = placeholder
        self.allowed = allowed or (lambda ch: ch.isalnum() or ch in " -_")
        self.upper = upper
        self.size = size
        self.on_enter = on_enter
        self.focused = False

    def _insert(self, text: str):
        for ch in text:
            if self.upper:
                ch = ch.upper()
            if self.allowed(ch) and len(self.value) < self.max_len:
                self.value += ch

    def handle(self, event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            was = self.focused
            self.focused = self.rect.collidepoint(event.pos)
            if self.focused and not was:
                sfx.play("select")
            return self.focused
        if not self.focused:
            return False
        if event.type == pygame.TEXTINPUT:
            self._insert(event.text)
            return True
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self.value = self.value[:-1]
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                if self.on_enter:
                    self.on_enter()
            elif event.key == pygame.K_v and event.mod & (pygame.KMOD_CTRL | pygame.KMOD_META):
                self._insert(paste_text())
            elif event.key == pygame.K_ESCAPE:
                self.focused = False
            return True
        return False

    def draw(self, surf):
        theme.panel(surf, self.rect, theme.INNER, theme.ACCENT if self.focused else theme.PANEL_EDGE,
                    radius=8, shadow=False, edge_w=3 if self.focused else 2)
        cy = self.rect.centery
        if self.value:
            r = theme.ptext(surf, self.value, (self.rect.x + 14, cy), self.size, anchor="midleft")
        else:
            r = pygame.Rect(self.rect.x + 14, cy, 0, 0)
            theme.ptext(surf, self.placeholder, (self.rect.x + 14, cy), self.size, theme.TEXT_FAINT, None,
                        anchor="midleft")
        if self.focused and (pygame.time.get_ticks() // 500) % 2 == 0:
            x = r.right + 3 if self.value else self.rect.x + 14
            pygame.draw.rect(surf, theme.ACCENT, (x, cy - self.size // 2, 3, self.size))
