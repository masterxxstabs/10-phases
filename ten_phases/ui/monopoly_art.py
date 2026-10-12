"""Drawing the Monopoly board: squares, corners, tokens, dice, title deeds and cards."""

from __future__ import annotations

import math

import pygame

from ..monopoly.board import GROUPS, SETS, SQUARES, STATION_RENTS
from . import theme

BOARD = pygame.Rect(14, 10, 756, 756)
CORNER = 100
CELL = (BOARD.w - 2 * CORNER) / 9
INNER = BOARD.inflate(-2 * CORNER, -2 * CORNER)

BOARD_BG = (196, 228, 204)
CELL_BG = (236, 246, 238)
LINE = (24, 40, 36)
INK = (20, 30, 28)
PLAYER_COLORS = [(232, 52, 52), (36, 116, 232), (40, 178, 80), (250, 196, 20), (168, 84, 230), (255, 132, 32)]
TOKEN_COLORS = {"car": PLAYER_COLORS[0], "hat": PLAYER_COLORS[1], "dog": PLAYER_COLORS[2],
                "ship": PLAYER_COLORS[3], "boot": PLAYER_COLORS[4], "cat": PLAYER_COLORS[5]}

_cache: dict[tuple, pygame.Surface] = {}


# --------------------------------------------------------------------------- geometry


def side(k: int) -> str:
    if k % 10 == 0:
        return "corner"
    return ("bottom", "left", "top", "right")[k // 10]


def cell_rect(k: int) -> pygame.Rect:
    """Where square k sits on the screen."""
    b, c, w = BOARD, CORNER, CELL
    if k == 0:
        return pygame.Rect(b.right - c, b.bottom - c, c, c)
    if k == 10:
        return pygame.Rect(b.x, b.bottom - c, c, c)
    if k == 20:
        return pygame.Rect(b.x, b.y, c, c)
    if k == 30:
        return pygame.Rect(b.right - c, b.y, c, c)
    if k < 10:
        x1 = b.right - c - k * w
        return pygame.Rect(round(x1), b.bottom - c, round(x1 + w) - round(x1), c)
    if k < 20:
        y1 = b.bottom - c - (k - 10) * w
        return pygame.Rect(b.x, round(y1), c, round(y1 + w) - round(y1))
    if k < 30:
        x0 = b.x + c + (k - 21) * w
        return pygame.Rect(round(x0), b.y, round(x0 + w) - round(x0), c)
    y0 = b.y + c + (k - 31) * w
    return pygame.Rect(b.right - c, round(y0), c, round(y0 + w) - round(y0))


def band_rect(k: int) -> pygame.Rect:
    """The colour band of a street (on the edge facing the middle of the board)."""
    r = cell_rect(k)
    t = 20
    return {"bottom": pygame.Rect(r.x, r.y, r.w, t), "top": pygame.Rect(r.x, r.bottom - t, r.w, t),
            "left": pygame.Rect(r.right - t, r.y, t, r.h), "right": pygame.Rect(r.x, r.y, t, r.h)}.get(
        side(k), r)


def owner_rect(k: int) -> pygame.Rect:
    """A strip just inside the middle of the board, next to a property, coloured for its owner."""
    r = cell_rect(k)
    t = 8
    return {"bottom": pygame.Rect(r.x + 3, r.y - t - 2, r.w - 6, t), "top": pygame.Rect(r.x + 3, r.bottom + 2, r.w - 6, t),
            "left": pygame.Rect(r.right + 2, r.y + 3, t, r.h - 6), "right": pygame.Rect(r.x - t - 2, r.y + 3, t, r.h - 6)
            }.get(side(k), r)


def spot(k: int, slot: int = 0, count: int = 1, jailed: bool = False) -> tuple[float, float]:
    """Where a token stands on square k (several tokens on one square spread out)."""
    r = cell_rect(k)
    if k == 10:
        if jailed:   # inside the cell, top right
            cx, cy = r.x + r.w * 0.64, r.y + r.h * 0.36
        else:        # just visiting: along the outer edges
            path = [(r.x + 14, r.y + 26 + n * 14) for n in range(4)] + [(r.x + 30 + n * 16, r.bottom - 14) for n in range(4)]
            return path[slot % len(path)]
    else:
        cx, cy = r.center
        s = side(k)
        if s == "bottom":
            cy += 10
        elif s == "top":
            cy -= 10
        elif s == "left":
            cx -= 10
        elif s == "right":
            cx += 10
    if count <= 1:
        return cx, cy
    ring = [(-1, -1), (1, -1), (-1, 1), (1, 1), (0, -1.6), (0, 1.6)]
    dx, dy = ring[slot % len(ring)]
    spread = 12 if count > 2 else 10
    return cx + dx * spread, cy + dy * spread


def perimeter_point(pos: float) -> tuple[float, float]:
    """A point along the board's track for a fractional square index (used while hopping)."""
    a = int(math.floor(pos)) % 40
    b = (a + 1) % 40
    t = pos - math.floor(pos)
    (x1, y1), (x2, y2) = spot(a), spot(b)
    return x1 + (x2 - x1) * t, y1 + (y2 - y1) * t


# --------------------------------------------------------------------------- little icons


def wrap(text: str, font: pygame.font.Font, width: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if font.size(trial)[0] <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    return lines + ([cur] if cur else [])


def _fitted(text: str, width: int, start: int = 9) -> tuple[pygame.font.Font, list[str]]:
    """The biggest small font at which every word of a square's name fits across it."""
    size = start
    while size > 6:
        font = theme.font(size, True)
        if all(font.size(w)[0] <= width for w in text.split()):
            break
        size -= 1
    font = theme.font(size, True)
    return font, wrap(text, font, width)


def _centered_lines(surf, lines, font, color, cx, y):
    for line in lines:
        img = font.render(line, True, color)
        surf.blit(img, img.get_rect(midtop=(cx, y)))
        y += font.get_linesize() - 1
    return y


def draw_train(surf, center, size, color=INK):
    x, y = center
    s = size
    pygame.draw.rect(surf, color, (x - s, y - s * 0.55, s * 1.5, s * 0.9), border_radius=3)
    pygame.draw.rect(surf, color, (x + s * 0.3, y - s * 0.95, s * 0.6, s * 0.5))
    pygame.draw.rect(surf, color, (x - s * 0.8, y - s * 0.9, s * 0.25, s * 0.4))
    for dx in (-0.6, 0.0, 0.6):
        pygame.draw.circle(surf, color, (x + dx * s, y + s * 0.5), s * 0.28)
    pygame.draw.polygon(surf, color, [(x + s * 0.5, y + s * 0.35), (x + s * 1.1, y + s * 0.35), (x + s * 0.5, y - s * 0.2)])


def draw_bulb(surf, center, size):
    x, y = center
    pygame.draw.circle(surf, (250, 220, 60), (x, y - size * 0.2), size * 0.7)
    pygame.draw.circle(surf, INK, (x, y - size * 0.2), size * 0.7, 2)
    pygame.draw.rect(surf, (120, 120, 130), (x - size * 0.35, y + size * 0.45, size * 0.7, size * 0.5))
    for k in range(6):
        a = k * math.pi / 3
        pygame.draw.line(surf, (250, 190, 40), (x + math.cos(a) * size * 0.9, y - size * 0.2 + math.sin(a) * size * 0.9),
                         (x + math.cos(a) * size * 1.2, y - size * 0.2 + math.sin(a) * size * 1.2), 2)


def draw_tap(surf, center, size):
    x, y = center
    pygame.draw.rect(surf, (90, 110, 130), (x - size, y - size * 0.6, size * 1.4, size * 0.45), border_radius=3)
    pygame.draw.rect(surf, (90, 110, 130), (x + size * 0.15, y - size * 0.6, size * 0.4, size * 0.9))
    pygame.draw.rect(surf, (90, 110, 130), (x - size * 0.5, y - size, size * 0.4, size * 0.4))
    for k in range(3):
        pygame.draw.circle(surf, (40, 140, 240), (x + size * 0.35, y + size * (0.55 + k * 0.32)), 3 - k * 0.5)


def draw_question(surf, center, size, color=(240, 120, 20)):
    f = theme.font(int(size * 2.2), True, heavy=True)
    img = f.render("?", True, color)
    sh = f.render("?", True, INK)
    r = img.get_rect(center=center)
    surf.blit(sh, r.move(2, 2))
    surf.blit(img, r)


def draw_chest(surf, center, size):
    x, y = center
    body = pygame.Rect(0, 0, size * 1.8, size * 1.1)
    body.center = (x, y + size * 0.2)
    pygame.draw.rect(surf, (150, 90, 40), body, border_radius=3)
    lid = pygame.Rect(body.x, body.y - size * 0.5, body.w, size * 0.6)
    pygame.draw.rect(surf, (180, 110, 50), lid, border_top_left_radius=8, border_top_right_radius=8)
    pygame.draw.rect(surf, INK, body, 2, border_radius=3)
    pygame.draw.rect(surf, INK, lid, 2, border_top_left_radius=8, border_top_right_radius=8)
    pygame.draw.rect(surf, (250, 200, 60), (x - 4, body.y - 4, 8, 10))
    pygame.draw.line(surf, (60, 120, 220), (body.x + 4, body.centery), (body.right - 4, body.centery), 3)


def draw_ring(surf, center, size):
    x, y = center
    pygame.draw.circle(surf, (250, 200, 60), (x, y), size, max(2, int(size * 0.35)))
    pygame.draw.polygon(surf, (120, 210, 255), [(x - size * 0.5, y - size * 1.1), (x + size * 0.5, y - size * 1.1),
                                                (x, y - size * 0.55)])


# --------------------------------------------------------------------------- the board


def _cell_surface(k: int, w: int, h: int) -> pygame.Surface:
    """An edge square drawn upright (colour band at the top); rotated into place later."""
    s = SQUARES[k]
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    surf.fill(CELL_BG)
    small = theme.font(9, True)
    tiny = theme.font(9, False)
    cx = w // 2
    if s.kind == "street":
        pygame.draw.rect(surf, SETS[s.group], (0, 0, w, 20))
        pygame.draw.line(surf, LINE, (0, 20), (w, 20), 2)
        _centered_lines(surf, *(lambda f, ls: (ls, f))(*_fitted(s.name.upper(), w - 4)), INK, cx, 25)
        img = tiny.render(f"£{s.price}", True, INK)
        surf.blit(img, img.get_rect(midbottom=(cx, h - 4)))
    elif s.kind == "station":
        _centered_lines(surf, *(lambda f, ls: (ls, f))(*_fitted(s.name.upper(), w - 4)), INK, cx, 6)
        draw_train(surf, (cx - 2, h * 0.62), 13)
        img = tiny.render("£200", True, INK)
        surf.blit(img, img.get_rect(midbottom=(cx, h - 4)))
    elif s.kind == "utility":
        _centered_lines(surf, *(lambda f, ls: (ls, f))(*_fitted(s.name.upper(), w - 4)), INK, cx, 6)
        (draw_bulb if "Electric" in s.name else draw_tap)(surf, (cx, h * 0.58), 12)
        img = tiny.render("£150", True, INK)
        surf.blit(img, img.get_rect(midbottom=(cx, h - 4)))
    elif s.kind == "chance":
        _centered_lines(surf, ["CHANCE"], small, INK, cx, 6)
        draw_question(surf, (cx, h * 0.58), 16)
    elif s.kind == "chest":
        _centered_lines(surf, *(lambda f, ls: (ls, f))(*_fitted("COMMUNITY CHEST", w - 4)), INK, cx, 6)
        draw_chest(surf, (cx, h * 0.62), 13)
    elif s.kind == "tax":
        _centered_lines(surf, *(lambda f, ls: (ls, f))(*_fitted(s.name.upper(), w - 4)), INK, cx, 6)
        draw_ring(surf, (cx, h * 0.6), 10)
        img = tiny.render(f"PAY £{s.tax}", True, INK)
        surf.blit(img, img.get_rect(midbottom=(cx, h - 4)))
    pygame.draw.rect(surf, LINE, surf.get_rect(), 1)
    return surf


def _corner_surface(k: int) -> pygame.Surface:
    c = CORNER
    surf = pygame.Surface((c, c), pygame.SRCALPHA)
    surf.fill(CELL_BG)
    big = theme.font(15, True, heavy=True)
    small = theme.font(9, True)
    if k == 0:   # GO, with a big arrow
        img = theme.font(34, True, heavy=True).render("GO", True, (220, 30, 40))
        rot = pygame.transform.rotate(img, 45)
        surf.blit(rot, rot.get_rect(center=(c * 0.55, c * 0.45)))
        _centered_lines(surf, ["COLLECT £200", "AS YOU PASS"], small, INK, c // 2, 6)
        pts = [(c * 0.15, c * 0.86), (c * 0.62, c * 0.86), (c * 0.62, c * 0.78), (c * 0.88, c * 0.9),
               (c * 0.62, c * 0.98), (c * 0.62, c * 0.92), (c * 0.15, c * 0.92)]
        pts = [(c - x, y - 6) for x, y in pts]   # pointing left: the way tokens travel from GO
        pygame.draw.polygon(surf, (220, 30, 40), pts)
        pygame.draw.polygon(surf, INK, pts, 1)
    elif k == 10:   # Jail / just visiting
        cell = pygame.Rect(int(c * 0.34), 0, int(c * 0.66), int(c * 0.66))
        pygame.draw.rect(surf, (250, 150, 40), cell)
        for x in range(cell.x + 8, cell.right, 10):
            pygame.draw.line(surf, INK, (x, cell.y + 4), (x, cell.bottom - 4), 3)
        pygame.draw.rect(surf, INK, cell, 2)
        img = small.render("IN JAIL", True, INK)
        bg = img.get_rect(center=cell.center).inflate(6, 2)
        pygame.draw.rect(surf, CELL_BG, bg)
        surf.blit(img, img.get_rect(center=cell.center))
        just = small.render("JUST", True, INK)
        surf.blit(pygame.transform.rotate(just, 90), (2, 26))
        vis = small.render("VISITING", True, INK)
        surf.blit(vis, vis.get_rect(midbottom=(c * 0.6, c - 2)))
    elif k == 20:   # Free parking
        _centered_lines(surf, ["FREE"], big, INK, c // 2, 8)
        img = theme.font(26, True, heavy=True).render("P", True, (220, 30, 40))
        pygame.draw.circle(surf, (255, 255, 255), (c // 2, c // 2 + 2), 20)
        pygame.draw.circle(surf, (220, 30, 40), (c // 2, c // 2 + 2), 20, 3)
        surf.blit(img, img.get_rect(center=(c // 2, c // 2 + 3)))
        _centered_lines(surf, ["PARKING"], big, INK, c // 2, c - 26)
    else:           # Go to jail
        _centered_lines(surf, ["GO TO"], big, INK, c // 2, 8)
        pygame.draw.circle(surf, (40, 70, 160), (c // 2, c // 2 + 2), 18)
        pygame.draw.rect(surf, (20, 30, 80), (c // 2 - 20, c // 2 - 18, 40, 10), border_radius=3)
        pygame.draw.circle(surf, (250, 220, 120), (c // 2, c // 2 + 6), 9)
        _centered_lines(surf, ["JAIL"], big, INK, c // 2, c - 26)
    pygame.draw.rect(surf, LINE, surf.get_rect(), 1)
    return surf


def board_surface() -> pygame.Surface:
    """The whole static board (squares, centre art). Cached; redrawn if the theme changes."""
    key = ("board", theme.ACCENT, theme.PIXEL_TEXT)
    if key in _cache:
        return _cache[key]
    surf = pygame.Surface(BOARD.size, pygame.SRCALPHA)
    pygame.draw.rect(surf, BOARD_BG, surf.get_rect(), border_radius=10)
    ox, oy = BOARD.topleft
    for k in range(40):
        r = cell_rect(k).move(-ox, -oy)
        if side(k) == "corner":
            img = _corner_surface(k)
            angle = {0: 0, 10: 0, 20: 0, 30: 0}[k]
            surf.blit(pygame.transform.rotate(img, angle), r)
            continue
        upright = _cell_surface(k, r.w if side(k) in ("bottom", "top") else r.h, CORNER)
        angle = {"bottom": 0, "left": -90, "top": 180, "right": 90}[side(k)]
        surf.blit(pygame.transform.rotate(upright, angle), r)
    inner = INNER.move(-ox, -oy)
    pygame.draw.rect(surf, LINE, inner, 2)
    pygame.draw.rect(surf, LINE, surf.get_rect(), 3, border_radius=10)
    # Centre art: the title across the middle, and the two card piles.
    banner = pygame.Surface((420, 92), pygame.SRCALPHA)
    pygame.draw.rect(banner, (0, 0, 0, 70), banner.get_rect().move(4, 5), border_radius=8)
    pygame.draw.rect(banner, (220, 30, 40), banner.get_rect().inflate(-4, -4), border_radius=8)
    pygame.draw.rect(banner, (255, 255, 255), banner.get_rect().inflate(-14, -14), 3, border_radius=6)
    word = theme.font(52, True, heavy=True).render("MONOPOLY", True, (255, 255, 255))
    shadow = theme.font(52, True, heavy=True).render("MONOPOLY", True, (120, 10, 20))
    banner.blit(shadow, shadow.get_rect(center=(213, 49)))
    banner.blit(word, word.get_rect(center=(210, 46)))
    rot = pygame.transform.rotozoom(banner, 38, 1)
    surf.blit(rot, rot.get_rect(center=inner.center))
    for name, color, pos, angle in (("CHANCE", (250, 150, 40), (0.3, 0.3), 45),
                                    ("COMMUNITY CHEST", (70, 160, 230), (0.7, 0.7), 45)):
        r = pygame.Rect(0, 0, 130, 84)
        r.center = (inner.x + inner.w * pos[0], inner.y + inner.h * pos[1])
        pile = pygame.Surface(r.size, pygame.SRCALPHA)
        pygame.draw.rect(pile, (0, 0, 0, 60), pile.get_rect().move(3, 3), border_radius=8)
        pygame.draw.rect(pile, color, pile.get_rect(), border_radius=8)
        pygame.draw.rect(pile, (255, 255, 255), pile.get_rect().inflate(-10, -10), 2, border_radius=6)
        f = theme.font(14 if len(name) < 10 else 11, True, heavy=True)
        img = f.render(name, True, (255, 255, 255))
        pile.blit(img, img.get_rect(center=(r.w // 2, r.h // 2)))
        rot = pygame.transform.rotate(pile, angle)
        surf.blit(rot, rot.get_rect(center=r.center))
    _cache[key] = surf
    return surf


def deck_center(deck: str) -> tuple[int, int]:
    pos = (0.3, 0.3) if deck == "chance" else (0.7, 0.7)
    return int(INNER.x + INNER.w * pos[0]), int(INNER.y + INNER.h * pos[1])


# --------------------------------------------------------------------------- tokens


def _token_shape(surf, kind: str, color, s: float):
    """Draw a token silhouette into a (2s x 2s) surface centred at (s, s)."""
    c = (s, s)
    dark = tuple(max(0, v - 90) for v in color)

    def poly(points):
        pts = [(c[0] + x * s, c[1] + y * s) for x, y in points]
        pygame.draw.polygon(surf, color, pts)
        return pts

    if kind == "car":
        body = poly([(-0.9, 0.2), (-0.9, -0.15), (-0.55, -0.2), (-0.3, -0.55), (0.35, -0.55), (0.6, -0.2),
                     (0.9, -0.12), (0.9, 0.2)])
        pygame.draw.polygon(surf, dark, body, 2)
        pygame.draw.polygon(surf, (190, 230, 255), [(c[0] - 0.22 * s, c[1] - 0.48 * s), (c[0] + 0.3 * s, c[1] - 0.48 * s),
                                                    (c[0] + 0.48 * s, c[1] - 0.22 * s), (c[0] - 0.4 * s, c[1] - 0.22 * s)])
        for dx in (-0.5, 0.5):
            pygame.draw.circle(surf, (30, 30, 34), (c[0] + dx * s, c[1] + 0.25 * s), 0.25 * s)
            pygame.draw.circle(surf, (190, 190, 200), (c[0] + dx * s, c[1] + 0.25 * s), 0.1 * s)
    elif kind == "hat":
        pygame.draw.ellipse(surf, color, (c[0] - 0.95 * s, c[1] + 0.15 * s, 1.9 * s, 0.5 * s))
        pygame.draw.rect(surf, color, (c[0] - 0.55 * s, c[1] - 0.8 * s, 1.1 * s, 1.15 * s), border_radius=int(s * 0.12))
        pygame.draw.rect(surf, dark, (c[0] - 0.55 * s, c[1] - 0.05 * s, 1.1 * s, 0.22 * s))
        pygame.draw.ellipse(surf, dark, (c[0] - 0.95 * s, c[1] + 0.15 * s, 1.9 * s, 0.5 * s), 2)
    elif kind == "dog":
        pts = poly([(-0.85, -0.05), (-0.55, -0.25), (0.35, -0.25), (0.45, -0.7), (0.6, -0.55), (0.9, -0.45),
                    (0.85, -0.25), (0.6, -0.15), (0.6, 0.6), (0.4, 0.6), (0.35, 0.15), (-0.45, 0.15),
                    (-0.5, 0.6), (-0.7, 0.6), (-0.7, 0.05), (-0.95, -0.25)])
        pygame.draw.polygon(surf, dark, pts, 2)
        pygame.draw.circle(surf, (30, 30, 34), (c[0] + 0.62 * s, c[1] - 0.48 * s), max(1, 0.08 * s))
    elif kind == "ship":
        hull = poly([(-0.95, 0.15), (0.95, 0.15), (0.6, 0.6), (-0.65, 0.6)])
        pygame.draw.polygon(surf, dark, hull, 2)
        pygame.draw.rect(surf, dark, (c[0] - 0.05 * s, c[1] - 0.9 * s, 0.1 * s, 1.05 * s))
        pygame.draw.polygon(surf, (250, 250, 250), [(c[0] + 0.05 * s, c[1] - 0.85 * s), (c[0] + 0.75 * s, c[1] + 0.05 * s),
                                                    (c[0] + 0.05 * s, c[1] + 0.05 * s)])
        pygame.draw.polygon(surf, (235, 235, 235), [(c[0] - 0.1 * s, c[1] - 0.7 * s), (c[0] - 0.65 * s, c[1] + 0.05 * s),
                                                    (c[0] - 0.1 * s, c[1] + 0.05 * s)])
    elif kind == "boot":
        pts = poly([(-0.35, -0.9), (0.35, -0.9), (0.35, 0.1), (0.9, 0.25), (0.95, 0.6), (-0.45, 0.6), (-0.45, 0.1)])
        pygame.draw.polygon(surf, dark, pts, 2)
        pygame.draw.rect(surf, dark, (c[0] - 0.45 * s, c[1] + 0.48 * s, 1.4 * s, 0.14 * s))
        for k in range(3):
            pygame.draw.line(surf, dark, (c[0] - 0.25 * s, c[1] - (0.6 - k * 0.25) * s),
                             (c[0] + 0.25 * s, c[1] - (0.6 - k * 0.25) * s), 2)
    else:   # cat
        pygame.draw.ellipse(surf, color, (c[0] - 0.7 * s, c[1] - 0.05 * s, 1.2 * s, 0.7 * s))
        pygame.draw.circle(surf, color, (c[0] + 0.45 * s, c[1] - 0.3 * s), 0.38 * s)
        for dx in (0.22, 0.62):
            pygame.draw.polygon(surf, color, [(c[0] + (dx - 0.15) * s, c[1] - 0.5 * s), (c[0] + dx * s, c[1] - 0.92 * s),
                                              (c[0] + (dx + 0.15) * s, c[1] - 0.5 * s)])
        pygame.draw.arc(surf, color, (c[0] - 1.05 * s, c[1] - 0.6 * s, 0.7 * s, 1.0 * s), 1.2, 4.0, max(2, int(0.14 * s)))
        for dx in (0.33, 0.58):
            pygame.draw.circle(surf, (30, 30, 34), (c[0] + dx * s, c[1] - 0.32 * s), max(1, 0.06 * s))


def token(kind: str, color, size: int = 22, outline=True) -> pygame.Surface:
    """A player token: the silhouette with a white outline and a soft shadow."""
    key = ("token", kind, tuple(color), size, outline)
    if key in _cache:
        return _cache[key]
    big = size * 4
    s = pygame.Surface((big, big), pygame.SRCALPHA)
    _token_shape(s, kind, color, big / 2)
    out = pygame.Surface((size + 6, size + 6), pygame.SRCALPHA)
    small = pygame.transform.smoothscale(s, (size, size))
    if outline:
        mask = pygame.mask.from_surface(small).to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0))
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, 1), (-1, 1), (1, -1)):
            out.blit(mask, (3 + dx, 3 + dy))
    out.blit(small, (3, 3))
    _cache[key] = out
    return out


# --------------------------------------------------------------------------- dice, deeds and cards


def die(value: int, size: int = 44, tint=(255, 255, 255)) -> pygame.Surface:
    key = ("die", value, size, tint)
    if key in _cache:
        return _cache[key]
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.rect(surf, (0, 0, 0, 70), surf.get_rect().move(2, 3), border_radius=size // 5)
    pygame.draw.rect(surf, tint, surf.get_rect().inflate(-2, -2), border_radius=size // 5)
    pygame.draw.rect(surf, (40, 40, 50), surf.get_rect().inflate(-2, -2), 2, border_radius=size // 5)
    pips = {1: [(0, 0)], 2: [(-1, -1), (1, 1)], 3: [(-1, -1), (0, 0), (1, 1)], 4: [(-1, -1), (1, -1), (-1, 1), (1, 1)],
            5: [(-1, -1), (1, -1), (0, 0), (-1, 1), (1, 1)], 6: [(-1, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (1, 1)]}
    for dx, dy in pips.get(value, []):
        pygame.draw.circle(surf, (220, 30, 40) if value == 1 else (20, 20, 30),
                           (size / 2 + dx * size * 0.26, size / 2 + dy * size * 0.26), size * 0.09)
    _cache[key] = surf
    return surf


def deed_height(k: int, w: int = 220) -> int:
    rows = {"street": 10 * 18 + 8, "station": 6 * 18 + 4, "utility": 4 * 18 + 4}[SQUARES[k].kind]
    return max(int(w * 1.2), 80 + rows + 34)


def deed(k: int, w: int = 220, owner_name: str | None = None, houses: int = 0, mortgaged: bool = False,
         full_set: bool = False) -> pygame.Surface:
    """A title deed card with the rent table (the rent that applies right now is highlighted)."""
    s = SQUARES[k]
    key = ("deed", k, w, owner_name, houses, mortgaged, full_set)
    if key in _cache:
        return _cache[key]
    h = deed_height(k, w)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(surf, (0, 0, 0, 80), surf.get_rect().move(4, 5), border_radius=10)
    pygame.draw.rect(surf, (252, 252, 246), surf.get_rect().inflate(-4, -4), border_radius=10)
    pygame.draw.rect(surf, LINE, surf.get_rect().inflate(-4, -4), 2, border_radius=10)
    head = pygame.Rect(12, 12, w - 24, 58)
    color = SETS.get(s.group, (230, 230, 230))
    pygame.draw.rect(surf, color, head)
    pygame.draw.rect(surf, LINE, head, 2)
    f_small = theme.font(11, True)
    f_name = theme.font(16, True, heavy=True)
    light = sum(color) > 450
    title_ink = INK if light else (255, 255, 255)
    kind = {"street": "TITLE DEED", "station": "STATION", "utility": "UTILITY"}[s.kind]
    img = f_small.render(kind, True, title_ink)
    surf.blit(img, img.get_rect(midtop=(w // 2, head.y + 5)))
    lines = wrap(s.name.upper(), f_name, head.w - 10)
    _centered_lines(surf, lines[:2], f_name, title_ink, w // 2, head.y + 20)
    f = theme.font(12, False)
    fb = theme.font(12, True)
    y = head.bottom + 10

    def row(label, value, bold=False, active=False):
        nonlocal y
        if active:
            pygame.draw.rect(surf, (255, 236, 150), (14, y - 1, w - 28, 17), border_radius=4)
        a = (fb if bold or active else f).render(label, True, INK)
        b = (fb if bold or active else f).render(value, True, INK)
        surf.blit(a, (20, y))
        surf.blit(b, b.get_rect(topright=(w - 20, y)))
        y += 18

    if s.kind == "street":
        row("Rent", f"£{s.rents[0]}", active=not mortgaged and houses == 0 and not full_set)
        row("Rent with full set", f"£{s.rents[0] * 2}", active=not mortgaged and houses == 0 and full_set)
        for n in range(1, 5):
            row(f"With {n} house{'s' if n > 1 else ''}", f"£{s.rents[n]}", active=houses == n)
        row("With a hotel", f"£{s.rents[5]}", active=houses == 5)
        y += 4
        row("Houses cost", f"£{s.house_price} each", bold=True)
    elif s.kind == "station":
        for n, r in enumerate(STATION_RENTS, 1):
            row(f"{n} station{'s' if n > 1 else ''} owned", f"£{r}")
    else:
        row("One utility owned", "4 x dice")
        row("Both utilities owned", "10 x dice")
    y += 4
    row("Price", f"£{s.price}", bold=True)
    row("Mortgage value", f"£{s.mortgage}")
    foot = (f"OWNED BY {owner_name.upper()}" if owner_name else "FOR SALE")
    img = theme.font(12, True).render(foot, True, (60, 60, 70))
    surf.blit(img, img.get_rect(midbottom=(w // 2, h - 12)))
    if mortgaged:
        stamp = theme.font(26, True, heavy=True).render("MORTGAGED", True, (220, 30, 40))
        stamp = pygame.transform.rotate(stamp, 20)
        stamp.set_alpha(200)
        surf.blit(stamp, stamp.get_rect(center=(w // 2, h // 2 + 10)))
    _cache[key] = surf
    return surf


def card_face(deck: str, text: str, w: int = 300, h: int = 180) -> pygame.Surface:
    key = ("card", deck, text, w, h)
    if key in _cache:
        return _cache[key]
    color = (250, 150, 40) if deck == "chance" else (70, 160, 230)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(surf, (0, 0, 0, 80), surf.get_rect().move(4, 5), border_radius=12)
    pygame.draw.rect(surf, (252, 250, 240), surf.get_rect().inflate(-4, -4), border_radius=12)
    pygame.draw.rect(surf, color, surf.get_rect().inflate(-4, -4), 4, border_radius=12)
    title = "CHANCE" if deck == "chance" else "COMMUNITY CHEST"
    img = theme.font(20, True, heavy=True).render(title, True, color)
    surf.blit(img, img.get_rect(midtop=(w // 2, 14)))
    if deck == "chance":
        draw_question(surf, (34, h - 40), 14)
    else:
        draw_chest(surf, (36, h - 34), 12)
    f = theme.font(17, True)
    lines = wrap(text, f, w - 50)
    y = 50 + max(0, (h - 70 - len(lines) * f.get_linesize()) // 2)
    _centered_lines(surf, lines, f, INK, w // 2, y)
    _cache[key] = surf
    return surf


def card_back(deck: str, w: int = 300, h: int = 180) -> pygame.Surface:
    key = ("cardback", deck, w, h)
    if key in _cache:
        return _cache[key]
    color = (250, 150, 40) if deck == "chance" else (70, 160, 230)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(surf, color, surf.get_rect().inflate(-4, -4), border_radius=12)
    pygame.draw.rect(surf, (255, 255, 255), surf.get_rect().inflate(-18, -18), 3, border_radius=10)
    if deck == "chance":
        draw_question(surf, (w // 2, h // 2), 30, (255, 255, 255))
    else:
        draw_chest(surf, (w // 2, h // 2), 26)
    _cache[key] = surf
    return surf


def house(size: int = 12, hotel: bool = False) -> pygame.Surface:
    key = ("house", size, hotel)
    if key in _cache:
        return _cache[key]
    w = size * (2 if hotel else 1)
    surf = pygame.Surface((w + 2, size + 2), pygame.SRCALPHA)
    color = (220, 40, 40) if hotel else (40, 170, 70)
    body = pygame.Rect(1, size * 0.45, w, size * 0.55)
    pygame.draw.rect(surf, color, body)
    pygame.draw.polygon(surf, color, [(1, size * 0.5), (1 + w / 2, 1), (1 + w, size * 0.5)])
    pygame.draw.polygon(surf, INK, [(1, size * 0.5), (1 + w / 2, 1), (1 + w, size * 0.5), (1 + w, size + 1), (1, size + 1)], 1)
    _cache[key] = surf
    return surf


def group_color(k: int):
    return SETS.get(SQUARES[k].group)


def set_squares(k: int) -> list[int]:
    return GROUPS[SQUARES[k].group]
