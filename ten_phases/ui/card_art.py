"""Procedurally drawn cards in a bright, flat, classic shedding-game style:
white border, solid colour face, a tilted white oval in the middle with a big
number, and small numbers in the corners."""

from __future__ import annotations

import math

import pygame

from ..cards import COLORS, Card, Color
from . import theme

OVAL_TILT = 32  # degrees, the oval leans to the right

_cache: dict[tuple, pygame.Surface] = {}


def _rounded_mask(size, radius) -> pygame.Surface:
    mask = pygame.Surface(size, pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
    return mask


def _clip_rounded(surf: pygame.Surface, radius: int) -> pygame.Surface:
    surf.blit(_rounded_mask(surf.get_size(), radius), (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    return surf


def _oval(size, fill=None, quadrants=None) -> pygame.Surface:
    """A tilted oval, either solid or split into four coloured quarters."""
    w, h = size
    ow, oh = int(w * 0.86), int(h * 0.66)
    oval = pygame.Surface((ow, oh), pygame.SRCALPHA)
    if quadrants:
        cx, cy = ow / 2, oh / 2
        # Split along the diagonals so the quarters look right once rotated.
        polys = [[(cx, cy), (0, 0), (ow, 0)], [(cx, cy), (ow, 0), (ow, oh)],
                 [(cx, cy), (ow, oh), (0, oh)], [(cx, cy), (0, oh), (0, 0)]]
        for color, poly in zip(quadrants, polys):
            pygame.draw.polygon(oval, color, poly)
        mask = pygame.Surface((ow, oh), pygame.SRCALPHA)
        pygame.draw.ellipse(mask, (255, 255, 255, 255), mask.get_rect())
        oval.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    else:
        pygame.draw.ellipse(oval, fill, oval.get_rect())
    return pygame.transform.rotozoom(oval, -OVAL_TILT, 1)


def _number(surf, label: str, center, size: int, color, shadow=(0, 0, 0), offset=None, outline=None):
    f = theme.font(size, True, heavy=True)
    offset = offset if offset is not None else max(1, size // 14)
    if outline:
        o = f.render(label, True, outline)
        r = o.get_rect(center=center)
        step = max(1, size // 20)
        for dx in (-step, 0, step):
            for dy in (-step, 0, step):
                if dx or dy:
                    surf.blit(o, r.move(dx, dy))
    sh = f.render(label, True, shadow)
    img = f.render(label, True, color)
    r = img.get_rect(center=center)
    surf.blit(sh, r.move(offset, offset))
    surf.blit(img, r)


def _skip_symbol(surf, center, radius, color):
    w = max(3, radius // 3)
    pygame.draw.circle(surf, color, center, radius, w)
    a = math.radians(45)
    dx, dy = math.cos(a) * (radius - w / 2), math.sin(a) * (radius - w / 2)
    pygame.draw.line(surf, color, (center[0] - dx, center[1] - dy), (center[0] + dx, center[1] + dy), w + 1)


def render_card(card: Card | None, w: int, h: int) -> pygame.Surface:
    """Render a card face (or the back, if card is None)."""
    key = ("back",) if card is None else (card.kind, card.color, card.value)
    key += (w, h)
    cached = _cache.get(key)
    if cached:
        return cached

    radius = max(4, int(w * 0.12))
    border = max(2, int(w * 0.065))
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(surf, theme.CARD_WHITE, surf.get_rect(), border_radius=radius)

    iw, ih = w - border * 2, h - border * 2
    inner = pygame.Surface((iw, ih), pygame.SRCALPHA)
    icenter = (iw // 2, ih // 2)
    big = int(ih * 0.42)
    small = max(9, int(ih * 0.15))

    if card is None:
        inner.fill(theme.CARD_BLACK)
        oval = _oval((iw, ih), fill=theme.CARD_COLORS[Color.RED])
        inner.blit(oval, oval.get_rect(center=icenter))
        _number(inner, "10", (icenter[0], icenter[1] - ih * 0.07), int(ih * 0.3), theme.CARD_COLORS[Color.YELLOW],
                outline=theme.CARD_BLACK)
        _number(inner, "PHASES", (icenter[0], icenter[1] + ih * 0.15), max(8, int(ih * 0.1)), theme.CARD_WHITE,
                outline=theme.CARD_BLACK, offset=1)
    elif card.is_wild:
        inner.fill(theme.CARD_BLACK)
        quads = [theme.CARD_COLORS[c] for c in (Color.RED, Color.BLUE, Color.YELLOW, Color.GREEN)]
        oval = _oval((iw, ih), quadrants=quads)
        inner.blit(oval, oval.get_rect(center=icenter))
        _number(inner, "W", icenter, int(big * 0.82), theme.CARD_WHITE, outline=theme.CARD_BLACK)
        for pos, flip in (((small * 0.62, small * 0.62), False), ((iw - small * 0.62, ih - small * 0.62), True)):
            _corner(inner, "W", pos, small, theme.CARD_WHITE, flip)
    elif card.is_skip:
        inner.fill(theme.CARD_BLACK)
        oval = _oval((iw, ih), fill=theme.CARD_WHITE)
        inner.blit(oval, oval.get_rect(center=icenter))
        r = int(iw * 0.22)
        _skip_symbol(inner, (icenter[0] + 2, icenter[1] + 2), r, (0, 0, 0))
        _skip_symbol(inner, icenter, r, theme.CARD_BLACK)
        for pos, flip in (((small * 0.62, small * 0.62), False), ((iw - small * 0.62, ih - small * 0.62), True)):
            _corner_skip(inner, pos, int(small * 0.45), flip)
        label_size = max(7, int(ih * 0.08))
        _number(inner, "SKIP", (icenter[0], ih - label_size * 1.6), label_size, theme.CARD_WHITE, offset=1)
    else:
        color = theme.CARD_COLORS[card.color]
        inner.fill(color)
        oval = _oval((iw, ih), fill=theme.CARD_WHITE)
        inner.blit(oval, oval.get_rect(center=icenter))
        label = str(card.value)
        size = big if card.value < 10 else int(big * (0.78 if w >= 60 else 0.62))
        _number(inner, label, icenter, size, color, shadow=(0, 0, 0), offset=max(2, size // 12),
                outline=theme.CARD_BLACK)
        if card.value in (6, 9):
            # Underline 6 and 9 so they read correctly upside down.
            ul_w = int(size * 0.32)
            pygame.draw.line(inner, theme.CARD_BLACK, (icenter[0] - ul_w // 2, icenter[1] + size * 0.42),
                             (icenter[0] + ul_w // 2, icenter[1] + size * 0.42), max(2, size // 14))
        for pos, flip in (((small * 0.62, small * 0.62), False), ((iw - small * 0.62, ih - small * 0.62), True)):
            _corner(inner, label, pos, small, theme.CARD_WHITE, flip)

    _clip_rounded(inner, max(3, radius - border // 2))
    surf.blit(inner, (border, border))
    _cache[key] = surf
    return surf


def _corner(surf, label, pos, size, color, flip):
    f = theme.font(size, True, heavy=True)
    tmp = pygame.Surface((f.size(label)[0] + 4, f.get_height() + 4), pygame.SRCALPHA)
    tmp.blit(f.render(label, True, (0, 0, 0)), (2, 2))
    tmp.blit(f.render(label, True, color), (1, 1))
    if flip:
        tmp = pygame.transform.rotate(tmp, 180)
    surf.blit(tmp, tmp.get_rect(center=(int(pos[0]) + (0 if flip else 2), int(pos[1]))))


def _corner_skip(surf, pos, radius, flip):
    _skip_symbol(surf, (int(pos[0]) + 1, int(pos[1]) + 1), radius, (0, 0, 0))
    _skip_symbol(surf, (int(pos[0]), int(pos[1])), radius, theme.CARD_WHITE)


def card_with_shadow(card: Card | None, w: int, h: int, lift: int = 0) -> tuple[pygame.Surface, int]:
    """The card plus a flat offset shadow below it. Returns (surface, shadow_offset)."""
    key = ("shadow", None if card is None else (card.kind, card.color, card.value), w, h, lift)
    cached = _cache.get(key)
    off = 4 + lift // 3
    if cached:
        return cached, off
    face = render_card(card, w, h)
    surf = pygame.Surface((w + off, h + off), pygame.SRCALPHA)
    sh = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(sh, (0, 0, 0, 80), sh.get_rect(), border_radius=max(4, int(w * 0.12)))
    surf.blit(sh, (off, off))
    surf.blit(face, (0, 0))
    _cache[key] = surf
    return surf, off


def preview_sheet(path: str) -> None:
    """Debug helper: write every card design to an image."""
    from ..cards import number, skip, wild
    cards = [number(c, v) for c in COLORS for v in (1, 6, 9, 12)] + [wild(), skip(), None]
    w, h = 100, 150
    sheet = pygame.Surface((len(cards) * (w + 10) + 10, h + 20))
    sheet.fill(theme.BG)
    for i, c in enumerate(cards):
        sheet.blit(render_card(c, w, h), (10 + i * (w + 10), 10))
    pygame.image.save(sheet, path)
