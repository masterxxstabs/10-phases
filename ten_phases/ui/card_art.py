"""Procedurally drawn cards in a bright, flat, classic shedding-game style:
white border, solid colour face, a tilted white oval in the middle with a big
number, and small numbers in the corners."""

from __future__ import annotations

import math
import random

import pygame

from ..cards import COLORS, Card, Color
from . import theme

OVAL_TILT = 32  # degrees, the oval leans to the right

_cache: dict[tuple, pygame.Surface] = {}


def clear_cache() -> None:
    _cache.clear()


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


def _face(card) -> str:
    """What's printed on a card: blackjack cards show A/J/Q/K, everything else its number."""
    return getattr(card, "rank_label", None) or str(card.value)


GOLD = (244, 196, 64)
GOLD_DARK = (150, 104, 20)


def _shape(size, style: str, fill=None, quadrants=None, ring=None) -> pygame.Surface | None:
    """The centre shape for a card front style (None = no shape)."""
    w, h = size
    if style == "minimal":
        return None
    if style == "classic" or style == "gold":
        shape = _oval(size, fill=fill, quadrants=quadrants)
        if ring:
            ring_s = _oval(size, fill=ring)
            ring_s.blit(_oval((int(w * 0.92), int(h * 0.92)), fill=fill, quadrants=quadrants),
                        _oval((int(w * 0.92), int(h * 0.92)), fill=fill).get_rect(center=ring_s.get_rect().center))
            return ring_s
        return shape
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    if style == "bubble":
        d = int(min(w, h) * 0.86)
        rect = pygame.Rect(0, 0, d, d)
        rect.center = (w // 2, h // 2)
        draw = lambda c, r_: pygame.draw.ellipse(surf, c, r_)  # noqa: E731
    elif style == "diamond":
        cx, cy, rx, ry = w // 2, h // 2, int(w * 0.48), int(h * 0.36)
        pts = [(cx, cy - ry), (cx + rx, cy), (cx, cy + ry), (cx - rx, cy)]
        draw = lambda c, r_: pygame.draw.polygon(surf, c, pts)  # noqa: E731
        rect = None
    else:  # neon: an outline only
        shape = _oval(size, fill=fill or (255, 255, 255))
        hole = _oval((int(w * 0.86), int(h * 0.86)), fill=(0, 0, 0))
        shape.blit(hole, hole.get_rect(center=shape.get_rect().center))
        return shape
    if quadrants:
        cx, cy = w // 2, h // 2
        polys = [[(cx, cy), (0, 0), (w, 0)], [(cx, cy), (w, 0), (w, h)], [(cx, cy), (w, h), (0, h)],
                 [(cx, cy), (0, h), (0, 0)]]
        for color, poly in zip(quadrants, polys):
            pygame.draw.polygon(surf, color, poly)
        mask = pygame.Surface((w, h), pygame.SRCALPHA)
        old = surf
        surf = mask
        draw((255, 255, 255, 255), rect)
        old.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        return old
    draw(fill, rect)
    return surf


def _draw_back(inner: pygame.Surface, style: str) -> None:
    """Card back patterns. The base colour is the Customize card-back colour."""
    iw, ih = inner.get_size()
    c = (iw // 2, ih // 2)
    base = theme.CARD_BACK
    dark = theme.darken(base, 70)
    yellow = theme.CARD_COLORS[Color.YELLOW]
    rng = random.Random(7)

    def logo(color=yellow, edge=theme.CARD_BLACK, word=theme.CARD_WHITE):
        _number(inner, "10", (c[0], c[1] - ih * 0.07), int(ih * 0.3), color, outline=edge)
        _number(inner, "PHASES", (c[0], c[1] + ih * 0.15), max(8, int(ih * 0.1)), word, outline=edge, offset=1)

    if style == "stars":
        inner.fill((18, 26, 70))
        for _ in range(int(iw * ih / 180)):
            x, y = rng.randrange(iw), rng.randrange(ih)
            theme.star(inner, (x, y), rng.choice([1.5, 2, 3, 4]), rng.choice([(255, 255, 255), (170, 210, 255), yellow]))
        pygame.draw.circle(inner, base, c, int(iw * 0.36))
        pygame.draw.circle(inner, theme.CARD_WHITE, c, int(iw * 0.36), max(2, iw // 30))
        logo()
    elif style == "checker":
        cell = max(4, iw // 6)
        for y in range(0, ih, cell):
            for x in range(0, iw, cell):
                pygame.draw.rect(inner, base if (x // cell + y // cell) % 2 else dark, (x, y, cell, cell))
        pygame.draw.circle(inner, theme.CARD_BLACK, c, int(iw * 0.38))
        pygame.draw.circle(inner, theme.CARD_WHITE, c, int(iw * 0.38), max(2, iw // 30))
        logo()
    elif style == "stripes":
        inner.fill(theme.CARD_BLACK)
        step = max(6, iw // 5)
        for k in range(-ih, iw + ih, step):
            pygame.draw.polygon(inner, base, [(k, 0), (k + step // 2, 0), (k + step // 2 - ih, ih), (k - ih, ih)])
        oval = _oval((iw, ih), fill=theme.CARD_BLACK)
        inner.blit(oval, oval.get_rect(center=c))
        logo()
    elif style == "galaxy":
        for y in range(ih):
            k = y / max(1, ih - 1)
            col = (int(40 + 80 * k), int(10 + 20 * math.sin(k * 3)), int(110 - 50 * k))
            pygame.draw.line(inner, col, (0, y), (iw, y))
        for _ in range(int(iw * ih / 120)):
            x, y = rng.randrange(iw), rng.randrange(ih)
            inner.set_at((x, y), rng.choice([(255, 255, 255), (200, 180, 255), (255, 220, 150)]))
        for k in range(3):
            pygame.draw.ellipse(inner, (150, 110, 255), (c[0] - iw * 0.45 + k * 4, c[1] - ih * 0.1 + k * 3,
                                                          iw * 0.9 - k * 8, ih * 0.2 - k * 6), 1)
        logo((255, 230, 120), (40, 10, 80), (230, 220, 255))
    elif style == "gold":
        inner.fill(theme.CARD_BLACK)
        m = max(4, iw // 12)
        pygame.draw.rect(inner, GOLD, (m, m, iw - 2 * m, ih - 2 * m), max(2, iw // 28), border_radius=max(3, iw // 10))
        pygame.draw.rect(inner, GOLD_DARK, (m * 2, m * 2, iw - 4 * m, ih - 4 * m), 1, border_radius=max(3, iw // 12))
        logo(GOLD, theme.CARD_BLACK, GOLD)
    elif style == "neon":
        inner.fill((8, 8, 16))
        for k, col in enumerate((theme.lighten(base, 60), base, dark)):
            pygame.draw.rect(inner, col, (3 + k * 2, 3 + k * 2, iw - 6 - k * 4, ih - 6 - k * 4), 1,
                             border_radius=max(3, iw // 10))
        _number(inner, "10", (c[0], c[1] - ih * 0.07), int(ih * 0.3), (8, 8, 16), outline=theme.lighten(base, 80))
        _number(inner, "PHASES", (c[0], c[1] + ih * 0.15), max(8, int(ih * 0.1)), theme.lighten(base, 90), offset=1)
    else:  # classic
        inner.fill(theme.CARD_BLACK)
        oval = _oval((iw, ih), fill=base)
        inner.blit(oval, oval.get_rect(center=c))
        logo()


def render_card(card: Card | None, w: int, h: int, face: str | None = None, back: str | None = None) -> pygame.Surface:
    """Render a card face (or the back, if card is None) in the equipped skin, or the one given."""
    face = face or theme.FACE_STYLE
    back = back or theme.BACK_STYLE
    key = ("back", back) if card is None else (card.kind, card.color, card.value, _face(card), face)
    key += (w, h)
    cached = _cache.get(key)
    if cached:
        return cached

    radius = max(4, int(w * 0.12))
    border = max(2, int(w * 0.065))
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    frame = GOLD if (card is not None and face == "gold") else (16, 16, 24) if (card is not None and face == "neon") \
        else theme.CARD_WHITE
    pygame.draw.rect(surf, frame, surf.get_rect(), border_radius=radius)
    if card is not None and face == "gold":
        pygame.draw.rect(surf, GOLD_DARK, surf.get_rect(), max(1, border // 2), border_radius=radius)

    iw, ih = w - border * 2, h - border * 2
    inner = pygame.Surface((iw, ih), pygame.SRCALPHA)
    icenter = (iw // 2, ih // 2)
    big = int(ih * 0.42)
    small = max(9, int(ih * 0.15))

    if card is None:
        _draw_back(inner, back)
    elif card.is_wild:
        inner.fill(theme.CARD_BLACK)
        quads = [theme.CARD_COLORS[c] for c in (Color.RED, Color.BLUE, Color.YELLOW, Color.GREEN)]
        oval = _shape((iw, ih), face if face != "minimal" else "classic", quadrants=quads)
        if face == "neon":
            oval = _shape((iw, ih), "neon", fill=theme.CARD_COLORS[Color.YELLOW])
        inner.blit(oval, oval.get_rect(center=icenter))
        _number(inner, "W", icenter, int(big * 0.82), theme.CARD_WHITE, outline=theme.CARD_BLACK)
        for pos, flip in (((small * 0.62, small * 0.62), False), ((iw - small * 0.62, ih - small * 0.62), True)):
            _corner(inner, "W", pos, small, theme.CARD_WHITE, flip)
    elif card.is_skip:
        inner.fill(theme.CARD_BLACK)
        oval = _shape((iw, ih), face if face not in ("minimal", "neon") else "classic", fill=theme.CARD_WHITE)
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
        if face == "neon":
            inner.fill((10, 10, 18))
            shape = _shape((iw, ih), "neon", fill=color)
        else:
            inner.fill(color)
            if face == "minimal":
                pygame.draw.polygon(inner, theme.lighten(color, 30), [(0, ih * 0.62), (iw, ih * 0.3), (iw, ih * 0.45),
                                                                    (0, ih * 0.77)])
            shape = _shape((iw, ih), face, fill=theme.CARD_WHITE, ring=GOLD if face == "gold" else None)
        if shape is not None:
            inner.blit(shape, shape.get_rect(center=icenter))
        label = _face(card)
        size = big if len(label) < 2 else int(big * (0.78 if w >= 60 else 0.62))
        number_color = theme.CARD_WHITE if face == "minimal" else color
        if face == "neon":
            _number(inner, label, icenter, size, color, shadow=(0, 0, 0), offset=max(2, size // 12),
                    outline=theme.lighten(color, 90))
        else:
            _number(inner, label, icenter, size, number_color, shadow=(0, 0, 0), offset=max(2, size // 12),
                    outline=theme.CARD_BLACK)
        if label in ("6", "9"):
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


def card_with_shadow(card: Card | None, w: int, h: int, lift: int = 0, face: str | None = None,
                     back: str | None = None) -> tuple[pygame.Surface, int]:
    """The card plus a flat offset shadow below it. Returns (surface, shadow_offset)."""
    face, back = face or theme.FACE_STYLE, back or theme.BACK_STYLE
    key = ("shadow", None if card is None else (card.kind, card.color, card.value, _face(card)), w, h, lift,
           face, back)
    cached = _cache.get(key)
    off = 4 + lift // 3
    if cached:
        return cached, off
    img = render_card(card, w, h, face, back)
    surf = pygame.Surface((w + off, h + off), pygame.SRCALPHA)
    sh = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(sh, (0, 0, 0, 80), sh.get_rect(), border_radius=max(4, int(w * 0.12)))
    surf.blit(sh, (off, off))
    surf.blit(img, (0, 0))
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


def app_icon(size: int = 256) -> pygame.Surface:
    """The app/window icon: a tilted card back on a rounded blue tile."""
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    radius = size // 5
    pygame.draw.rect(surf, (14, 52, 132), surf.get_rect().move(0, size // 40), border_radius=radius)
    pygame.draw.rect(surf, (30, 112, 226), surf.get_rect().inflate(0, -size // 40).move(0, -size // 80),
                     border_radius=radius)
    for k, (dx, angle) in enumerate(((-0.13, 14), (0.06, -8))):
        card = render_card(None, int(size * 0.5), int(size * 0.75))
        if k == 0:
            card = card.copy()
            card.fill((255, 255, 255, 140), special_flags=pygame.BLEND_RGBA_MULT)
        card = pygame.transform.rotozoom(card, angle, 1)
        surf.blit(card, card.get_rect(center=(size // 2 + int(dx * size), size // 2)))
    return surf
