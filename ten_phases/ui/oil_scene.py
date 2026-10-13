"""The Oil Field: Deep Dig's oil business (rules in deepdig/oil.py).

Scan the ground, build rigs, click where pipes should go, and send trucks between rigs and the two buyers at
the ends of the road (or buy the Dispatcher and they drive themselves). It never stops: buy more land to the
right whenever you like. The field keeps running back in the mine too.

Mouse: pick a tool (1 scan, 2 rig, 3 pipe) and click the ground. Click a truck, then a rig or a buyer, to send
it. Arrows, A/D or the wheel scroll. 4 buys a truck, U upgrades, L buys land, T toggles a truck's autopilot.
Controller: the pointer and A, LB/RB change tool, X autopilot, Y upgrades, D-pad scrolls, B back.
"""

from __future__ import annotations

import math
import random

import pygame

from ..deepdig import oil as oilmod
from ..deepdig.oil import BUYER_NAMES, BUYER_W, GAS, OIL, OIL_INFO, OIL_UPGRADES, PLOT, ROCK, ROWS, OilError
from ..deepdig.save import save_game
from . import deepdig_art as art
from . import sfx, theme
from .menus import Scene, status_bar
from .widgets import Button
from .xp import XpTracker

CELL = 24
HUD_H = 72
GROUND_Y = 296                      # the surface; the ground runs down from here
UNDER_H = ROWS * CELL
TOOLBAR_Y = GROUND_Y + UNDER_H + 6
TOOLS = ("SCAN", "RIG", "PIPE")
BUYER_COLORS = {"L": (200, 70, 60), "R": (60, 120, 210)}
_cache: dict = {}


def money(n) -> str:
    return f"${int(n):,}"


def _tile(kind: str, variant: int) -> pygame.Surface:
    key = (kind, variant)
    if key in _cache:
        return _cache[key]
    s = pygame.Surface((CELL, CELL))
    rng = random.Random(hash(key) & 0xFFFF)
    base = {"fog": (52, 40, 40), "dirt": (128, 86, 56), "rock": (120, 120, 132), "gas": (110, 140, 90),
            "oil": (26, 24, 30), "tar": (70, 56, 46)}[kind]
    s.fill(base)
    for _ in range(7):
        c = tuple(max(0, min(255, int(v * rng.choice((0.8, 1.15))))) for v in base)
        pygame.draw.circle(s, c, (rng.randrange(CELL), rng.randrange(CELL)), rng.choice((1, 2)))
    if kind == "rock":
        pygame.draw.polygon(s, (150, 150, 162), [(4, 8), (10, 3), (20, 4), (21, 15), (14, 21), (4, 18)])
        pygame.draw.line(s, (96, 96, 108), (9, 10), (15, 15), 2)
    elif kind == "gas":
        for _ in range(3):
            pygame.draw.circle(s, (190, 230, 150), (rng.randrange(4, 20), rng.randrange(4, 20)), 3, 1)
    elif kind == "oil":
        pygame.draw.ellipse(s, (70, 70, 96), (4, 4, 10, 5))
        pygame.draw.circle(s, (110, 100, 150), (7, 6), 1)
    elif kind == "fog":
        pygame.draw.line(s, (60, 48, 48), (0, CELL - 1), (CELL, CELL - 1))
    _cache[key] = s
    return s


def truck_sprite(load_k: float, facing: int, auto: bool, selected: bool) -> pygame.Surface:
    key = ("truck", round(load_k, 1), facing, auto, selected)
    if key in _cache:
        return _cache[key]
    s = pygame.Surface((52, 30), pygame.SRCALPHA)
    ink = theme.OUTLINE
    if selected:
        pygame.draw.rect(s, theme.ACCENT, (0, 0, 52, 30), 2, border_radius=8)
    tank = pygame.Rect(4, 6, 30, 14)
    pygame.draw.rect(s, ink, tank.inflate(2, 2), border_radius=7)
    pygame.draw.rect(s, (210, 214, 224), tank, border_radius=7)
    fill = int((tank.w - 4) * max(0.0, min(1.0, load_k)))
    if fill:
        pygame.draw.rect(s, (30, 28, 36), (tank.x + 2, tank.y + 7, fill, 5), border_radius=2)
    cab = pygame.Rect(35, 8, 14, 13)
    pygame.draw.rect(s, ink, cab.inflate(2, 2), border_radius=3)
    pygame.draw.rect(s, (230, 80, 60), cab, border_radius=3)
    pygame.draw.rect(s, (150, 210, 250), (cab.x + 6, cab.y + 2, 6, 5))
    pygame.draw.rect(s, (60, 60, 70), (3, 19, 46, 3))
    for x in (11, 27, 42):
        pygame.draw.circle(s, ink, (x, 23), 5)
        pygame.draw.circle(s, (150, 150, 160), (x, 23), 2)
    if auto:
        pygame.draw.circle(s, (90, 220, 120), (8, 6), 5)
        pygame.draw.circle(s, ink, (8, 6), 5, 1)
    if facing < 0:
        s = pygame.transform.flip(s, True, False)
    _cache[key] = s
    return s


def rig_sprite(tank_k: float, selected: bool, nod: int) -> pygame.Surface:
    """A derrick with its tank showing how full it is, and a pump nodding at its foot."""
    key = ("rig", round(tank_k, 2), selected, nod)
    if key in _cache:
        return _cache[key]
    s = pygame.Surface((48, 130), pygame.SRCALPHA)
    ink = theme.OUTLINE
    steel = (200, 120, 60)
    if selected:
        pygame.draw.rect(s, theme.ACCENT, (0, 0, 48, 130), 2, border_radius=6)
    top, base = (24, 8), 126
    for lx in (6, 42):
        pygame.draw.line(s, ink, (lx, base), top, 5)
        pygame.draw.line(s, steel, (lx, base), top, 3)
    for k in range(5):                          # cross braces
        y = base - 20 - k * 22
        half = 18 * (y - top[1]) / (base - top[1])
        pygame.draw.line(s, steel, (24 - half, y), (24 + half, y - 16), 2)
        pygame.draw.line(s, steel, (24 + half, y), (24 - half, y - 16), 2)
    pygame.draw.rect(s, ink, (16, 2, 16, 8), border_radius=2)
    pygame.draw.rect(s, (90, 90, 100), (18, 4, 12, 4))
    tank = pygame.Rect(14, base - 44, 20, 40)    # the tank
    pygame.draw.rect(s, ink, tank.inflate(4, 4), border_radius=6)
    pygame.draw.rect(s, (220, 224, 232), tank, border_radius=5)
    h = int((tank.h - 4) * max(0.0, min(1.0, tank_k)))
    if h:
        pygame.draw.rect(s, (30, 28, 36), (tank.x + 2, tank.bottom - 2 - h, tank.w - 4, h), border_radius=3)
    beam_y = base - 52 + (nod - 1) * 3            # the pump's nodding beam
    pygame.draw.line(s, ink, (2, beam_y + 4), (46, beam_y - 4), 4)
    pygame.draw.circle(s, (60, 60, 70), (2, beam_y + 4), 4)
    _cache[key] = s
    return s


class OilFieldScene(Scene):
    pad_buttons = {"LB": pygame.K_q, "RB": pygame.K_e, "X": pygame.K_t, "Y": pygame.K_u, "BACK": pygame.K_TAB}

    def __init__(self, app, dig_scene):
        super().__init__(app)
        self.dig = dig_scene                      # the Deep Dig screen to go back to
        self.game = dig_scene.game
        self.field = self.game.oil
        self.xp = XpTracker(self, "deepdig")
        self.xp.corner = (12, TOOLBAR_Y - 70)
        self.tool = "SCAN" if not self.field.revealed else "PIPE" if self.field.rigs else "RIG"
        self.sel_rig: int | None = None
        self.sel_truck: int | None = None
        self.panel = False                       # the upgrades window
        self.panel_buttons: list[Button] = []
        self.cam = self._cam_limits()[0] if self._content_w() > theme.WIDTH else self._centered()
        self.cam_goal = self.cam
        self.flash: tuple[str, float] | None = None
        self.particles: list[list] = []
        self.floaters: list[list] = []
        self.save_timer = 0.0
        self.hover: tuple | None = None
        self.preview = None                      # (key, plan) for the pipe tool
        self.btn_back = Button((theme.WIDTH - 118, 14, 104, 44), "TOWN", self.back, size=16)
        self.btn_land = Button((theme.WIDTH - 300, 14, 172, 44), "", self.buy_land, size=14,
                               color="ACCENT", text_color="OUTLINE")
        self.tool_buttons = [Button((16 + k * 158, TOOLBAR_Y, 150, 40), "", lambda t=t: self.set_tool(t), size=15)
                             for k, t in enumerate(TOOLS)]
        self.btn_truck = Button((16 + 3 * 158, TOOLBAR_Y, 170, 40), "", self.buy_truck, size=15)
        self.btn_upgrades = Button((16 + 3 * 158 + 178, TOOLBAR_Y, 150, 40), "UPGRADES (U)", self.open_panel,
                                   size=15)
        self.btn_auto = Button((theme.WIDTH - 210, TOOLBAR_Y, 194, 40), "", self.toggle_auto, size=14)
        self.say("Welcome to your oil field! Scan for oil, build a rig, then pipe down to it."
                 if not self.field.rigs else "Back at the oil field.", 4.0)
        sfx.play("shuffle")

    # ================================================================== camera and coordinates

    def _content_left(self) -> int:
        return -(BUYER_W + 1) * CELL

    def _content_w(self) -> int:
        return (self.field.width + PLOT + 2 * BUYER_W + 3) * CELL

    def _cam_limits(self) -> tuple[float, float]:
        lo = self._content_left()
        return lo, max(lo, lo + self._content_w() - theme.WIDTH)

    def _centered(self) -> float:
        return self._content_left() - (theme.WIDTH - self._content_w()) / 2

    def sx(self, col: float) -> int:
        return int(col * CELL - self.cam)

    def cell_at(self, pos) -> tuple[int, int] | None:
        x, y = pos
        if not GROUND_Y <= y < GROUND_Y + UNDER_H:
            return None
        return int(math.floor((x + self.cam) / CELL)), int((y - GROUND_Y) // CELL)

    def col_at(self, x) -> int:
        return int(math.floor((x + self.cam) / CELL))

    def scroll(self, cols: float) -> None:
        lo, hi = self._cam_limits()
        if self._content_w() <= theme.WIDTH:
            self.cam_goal = self._centered()
            return
        self.cam_goal = max(lo, min(hi, self.cam_goal + cols * CELL))

    # ================================================================== actions

    def say(self, text: str, secs: float = 2.6):
        self.flash = (text, secs)

    def error(self, text: str):
        self.say(text, 2.8)
        sfx.play("error")

    def _try(self, fn, *args):
        try:
            out = fn(*args)
        except OilError as e:
            self.error(str(e))
            return None
        self.preview = None
        self._consume(self.game.step_oil(0))
        self._bank_events()
        return out

    def set_tool(self, tool: str):
        self.tool = tool
        self.preview = None
        sfx.play("select")

    def cycle_tool(self, d: int):
        self.set_tool(TOOLS[(TOOLS.index(self.tool) + d) % len(TOOLS)])

    def buy_land(self):
        self._try(self.field.buy_land)
        self.scroll(0)                       # (the field got wider: the camera's limits moved)

    def buy_truck(self):
        self._try(self.field.buy_truck)

    def toggle_auto(self):
        if self.sel_truck is None:
            self.error("Pick a truck first (click it).")
            return
        truck = self.field.trucks[self.sel_truck]
        self._try(self.field.set_auto, self.sel_truck, not truck.auto)

    def open_panel(self):
        self.panel = True
        self._build_panel()
        sfx.play("select")

    def close_panel(self):
        self.panel = False
        self.panel_buttons = []

    def back(self):
        save_game(self.game)
        self.dig.keys.clear()
        self.app.go(self.dig)

    def on_leave(self):
        save_game(self.game)

    # ================================================================== the upgrades window

    def _card(self, k: int) -> pygame.Rect:
        return pygame.Rect(96 + (k % 2) * 552, 186 + (k // 2) * 118, 536, 108)

    def _build_panel(self):
        out = []
        for k, name in enumerate(OIL_UPGRADES):
            price = self.field.upgrade_price(name)
            r = self._card(k)
            can = price is not None and self.game.cash >= price
            b = Button((r.right - 146, r.centery - 22, 134, 44), "MAXED" if price is None else money(price),
                       lambda n=name: self._buy_upgrade(n), size=15,
                       **(dict(color="ACCENT", text_color="OUTLINE") if can else {}))
            b.enabled = can
            out.append(b)
        out.append(Button((1130, 106, 46, 44), "X", self.close_panel, size=18))
        self.panel_buttons = out

    def _buy_upgrade(self, name):
        self._try(self.field.buy_upgrade, name)
        self._build_panel()

    # ================================================================== input

    def handle(self, event):
        if self.panel:
            for b in self.panel_buttons:
                if b.handle(event):
                    return
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_u):
                self.close_panel()
            return
        for b in [self.btn_back, self.btn_land, self.btn_truck, self.btn_upgrades, self.btn_auto] + self.tool_buttons:
            if b.visible and b.handle(event):
                return
        if event.type == pygame.KEYDOWN:
            self._key(event.key)
        elif event.type == pygame.MOUSEWHEEL:
            self.scroll(-3 * (event.x or event.y))
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._click(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            self.sel_truck = self.sel_rig = None
        elif event.type == pygame.MOUSEMOTION:
            self.hover = event.pos

    def _key(self, key):
        tools = {pygame.K_1: "SCAN", pygame.K_2: "RIG", pygame.K_3: "PIPE"}
        if key == pygame.K_ESCAPE:
            if self.sel_truck is not None or self.sel_rig is not None:
                self.sel_truck = self.sel_rig = None
            else:
                self.back()
        elif key in tools:
            self.set_tool(tools[key])
        elif key == pygame.K_q:
            self.cycle_tool(-1)
        elif key == pygame.K_e:
            self.cycle_tool(1)
        elif key == pygame.K_4:
            self.buy_truck()
        elif key == pygame.K_u or key == pygame.K_5:
            self.open_panel()
        elif key == pygame.K_l:
            self.buy_land()
        elif key == pygame.K_t:
            self.toggle_auto()
        elif key == pygame.K_TAB:
            n = len(self.field.trucks)
            self.sel_truck = 0 if self.sel_truck is None else (self.sel_truck + 1) % n
        elif key in (pygame.K_LEFT, pygame.K_a):
            self.scroll(-PLOT)
        elif key in (pygame.K_RIGHT, pygame.K_d):
            self.scroll(PLOT)

    def _truck_at(self, pos) -> int | None:
        for i in reversed(range(len(self.field.trucks))):
            if self._truck_rect(i).collidepoint(pos):
                return i
        return None

    def _truck_rect(self, i: int) -> pygame.Rect:
        t = self.field.trucks[i]
        return pygame.Rect(self.sx(t.x) - 26, GROUND_Y - 32 - (i % 3) * 4, 52, 30)

    def _rig_at(self, pos) -> int | None:
        x, y = pos
        if not GROUND_Y - 140 <= y < GROUND_Y:
            return None
        for i, rig in enumerate(self.field.rigs):
            if abs(x - self.sx(rig.col + 0.5)) <= 24:
                return i
        return None

    def _buyer_at(self, pos) -> str | None:
        x, y = pos
        if not HUD_H <= y < GROUND_Y:
            return None
        col = (x + self.cam) / CELL
        if -BUYER_W - 1 <= col < 0:
            return "L"
        if self.field.width <= col < self.field.width + BUYER_W + 1:
            return "R"
        return None

    def _click(self, pos):
        f = self.field
        t = self._truck_at(pos)
        if t is not None:
            self.sel_truck = t
            sfx.play("select")
            return
        if self.sel_truck is not None:
            rig, buyer = self._rig_at(pos), self._buyer_at(pos)
            if rig is not None or buyer is not None:
                goal = ("rig", rig) if rig is not None else ("buyer", buyer)
                self._try(f.send, self.sel_truck, goal)
                where = f"rig {rig + 1}" if rig is not None else BUYER_NAMES[buyer]
                self.say(f"Truck {self.sel_truck + 1} is heading to {where}.")
                sfx.play("click")
                return
            self.sel_truck = None
        if pos[1] < GROUND_Y:                           # up top
            rig = self._rig_at(pos)
            if rig is not None:
                self.sel_rig = rig
                self.set_tool("PIPE")
                self.say(f"Rig {rig + 1} picked: click underground to lay its pipe.")
                return
            col = self.col_at(pos[0])
            if f.width + BUYER_W + 1 <= col < f.width + BUYER_W + 1 + PLOT:
                self.buy_land()
            elif self.tool == "RIG" and f.owned(col):
                self._place_rig(col)
            return
        cell = self.cell_at(pos)
        if cell is None:
            return
        col, row = cell
        if self.tool == "SCAN":
            self._try(f.scan, col, row)
        elif self.tool == "RIG":
            self._place_rig(col)
        else:
            n = self._try(f.lay_pipe, col, row, self.sel_rig)
            if n:
                sfx.play("click")

    def _place_rig(self, col):
        i = self._try(self.field.place_rig, col)
        if i is not None:
            self.sel_rig = i
            self.tool = "PIPE"
            self.say("Rig built! Now click underground to lay a pipe down to the oil.")
            sfx.play("lay")

    # ================================================================== update

    def update(self, dt: float):
        super().update(dt)
        self.xp.update(dt)
        if self.flash:
            self.flash = (self.flash[0], self.flash[1] - dt) if self.flash[1] > dt else None
        self._consume(self.game.step_oil(dt))
        self._bank_events()
        if not self.panel:
            held = pygame.key.get_pressed() if pygame.display.get_init() else None
            if held is not None and (held[pygame.K_LEFT] or held[pygame.K_a]):
                self.scroll(-18 * dt)
            if held is not None and (held[pygame.K_RIGHT] or held[pygame.K_d]):
                self.scroll(18 * dt)
        self.cam += (self.cam_goal - self.cam) * min(1.0, dt * 10)
        for p in self.particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += 400 * dt
            p[4] -= dt
        self.particles = [p for p in self.particles if p[4] > 0][-300:]
        for fl in self.floaters:
            fl[2] -= 30 * dt
            fl[3] -= dt
        self.floaters = [fl for fl in self.floaters if fl[3] > 0]
        self.save_timer += dt
        if self.save_timer > 20:
            self.save_timer = 0.0
            save_game(self.game)
        self.btn_land.label = f"BUY LAND {money(self.field.land_price())}"
        self.btn_truck.label = (f"TRUCK +{money(self.field.truck_price())}" if len(self.field.trucks) < oilmod.MAX_TRUCKS
                                else "TRUCKS: MAX")
        for b, t in zip(self.tool_buttons, TOOLS):
            price = {"SCAN": f"${oilmod.SCAN_PRICE}", "RIG": money(self.field.rig_price()),
                     "PIPE": f"${oilmod.PIPE_PRICE}/CELL"}[t]
            b.label = f"{TOOLS.index(t) + 1} {t} {price}"
            b.color = "ACCENT" if t == self.tool else "PANEL"
            b.text_color = "OUTLINE" if t == self.tool else "TEXT"
        self.btn_auto.visible = self.sel_truck is not None
        if self.sel_truck is not None:
            self.btn_auto.label = f"AUTOPILOT: {'ON' if self.field.trucks[self.sel_truck].auto else 'OFF'} (T)"

    def _bank_events(self):
        for ev in self.game.pop_events():
            if ev[0] == "oil_sell":
                _, total, chips, side = ev
                if chips:
                    self.app.settings.chip_bank += chips
                    self.app.settings.save()

    def _consume(self, events):
        f = self.field
        for ev in events:
            k = ev[0]
            if k == "sell":
                _, total, side, t = ev
                x = f.buyer_x(side)
                self.floater(f"+{money(total)}", self.sx(x), GROUND_Y - 120, theme.SUCCESS)
                self.xp.gain(max(1, min(60, total // 150)))
                sfx.play("coin")
            elif k == "strike":
                rig = f.rigs[ev[1]]
                x = self.sx(rig.col + 0.5)
                for _ in range(40):
                    self.particles.append([x + random.uniform(-6, 6), GROUND_Y - 120, random.uniform(-90, 90),
                                           random.uniform(-380, -160), random.uniform(0.6, 1.3), (24, 22, 30),
                                           random.uniform(2, 5)])
                self.say(f"GUSHER! Rig {ev[1] + 1} struck oil.", 3.0)
                self.xp.gain(10)
                sfx.play("round_win")
            elif k == "boom":
                c, r = ev[1]
                x, y = self.sx(c + 0.5), GROUND_Y + int((r + 0.5) * CELL)
                for _ in range(30):
                    self.particles.append([x, y, random.uniform(-200, 200), random.uniform(-260, 60),
                                           random.uniform(0.3, 0.8), random.choice([(255, 160, 40), (255, 230, 140)]),
                                           random.uniform(2, 6)])
                self.say("BOOM! The pipe hit a gas pocket and the tip blew off.", 3.0)
                sfx.play("game_lose")
            elif k == "stopped" and ev[2] == "rock":
                self.say(f"The drill hit rock and stopped (refunded {money(ev[3])}). Pipe around it.", 3.0)
                sfx.play("deselect")
            elif k == "dry":
                self.say(f"A pocket on rig {ev[1] + 1} ran dry. Time to find more oil!", 3.0)
            elif k == "scan":
                _, c, r, found = ev
                self.say(f"Scanned: {found} oil cell{'s' if found != 1 else ''} found." if found
                         else "Scanned: no oil around here.", 2.4)
                sfx.play("phase" if found else "click")
            elif k == "land":
                self.say(f"You bought plot {ev[1]}! The land past PETRO CO is up for sale next.", 3.0)
                sfx.play("lay")
            elif k == "truck":
                self.say(f"A new truck! You have {ev[1]}.")
                sfx.play("lay")
            elif k == "upgrade":
                self.say(f"{ev[1].title()} upgraded to level {ev[2]}!")
                sfx.play("lay")

    def floater(self, text, x, y, color):
        self.floaters.append([text, x, y, 1.6, color])

    # ================================================================== drawing

    def draw(self, surf):
        surf.fill((40, 30, 30))
        sky = art.sky(theme.WIDTH, GROUND_Y - HUD_H)
        surf.blit(sky, (0, HUD_H))
        self._draw_ground(surf)
        self._draw_surface(surf)
        for x, y, _, _, ttl, color, size in self.particles:
            pygame.draw.circle(surf, color, (int(x), int(y)), max(1, int(size * min(1.0, ttl * 2))))
        for text, x, y, ttl, color in self.floaters:
            img = theme.pixel_surface(text, 18, color)
            if ttl < 0.4:
                img.set_alpha(int(255 * ttl / 0.4))
            surf.blit(img, img.get_rect(center=(int(x), int(y))))
        self._draw_hud(surf)
        self._draw_toolbar(surf)
        status_bar(surf, self.flash[0] if self.flash else self._status())
        if self.panel:
            self._draw_panel(surf)
        self.xp.draw(surf)

    def _status(self) -> str:
        if self.sel_truck is not None:
            return "Click a rig to load up, or ACME (left) / PETRO (right) to sell. Right-click or Esc to let go."
        return {"SCAN": f"Click underground to scan for oil (${oilmod.SCAN_PRICE}). Click a truck to drive it.",
                "RIG": "Click your land to build a rig. Then pipe down to oil.",
                "PIPE": "Click underground: the pipe drills there from the picked rig, around rock you've seen."}[self.tool]

    def _draw_ground(self, surf):
        f = self.field
        c0 = int(math.floor(self.cam / CELL)) - 1
        c1 = c0 + theme.WIDTH // CELL + 3
        owners = f.pipe_owner()
        for c in range(c0, c1):
            x = self.sx(c)
            for r in range(ROWS):
                y = GROUND_Y + r * CELL
                if f.owned(c) or c < f.width + BUYER_W + 1 + PLOT:
                    if f.owned(c) and (c, r) in f.revealed:
                        t = f.tile(c, r)
                        kind = {ROCK: "rock", GAS: "gas", OIL: "oil"}.get(t, "dirt")
                        if t == OIL and f.pockets[f.pocket_at[(c, r)]].amount <= 0:
                            kind = "tar"
                    else:
                        kind = "fog"
                else:
                    kind = "fog"
                img = _tile(kind, (c * 7 + r * 13) % 3)
                surf.blit(img, (x, y))
                if not f.owned(c):
                    shade = _cache.get("shade")
                    if shade is None:
                        shade = _cache["shade"] = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
                        shade.fill((0, 0, 0, 110))
                    surf.blit(shade, (x, y))
        # Pipes: a thick grey line between neighbouring pipe cells (black inside where oil's flowing).
        for i, rig in enumerate(f.rigs):
            cells = set(rig.pipe)
            flowing = any(p.amount > 0 for p in f.rig_pockets(rig)) and rig.tank < f.stat("TANKS")
            x0 = self.sx(rig.col + 0.5)
            pygame.draw.line(surf, theme.OUTLINE, (x0, GROUND_Y - 4), (x0, GROUND_Y + CELL // 2), 8)
            for (c, r) in rig.pipe:
                a = (self.sx(c + 0.5), GROUND_Y + int((r + 0.5) * CELL))
                for nb in ((c + 1, r), (c, r + 1)):
                    if nb in cells and owners.get(nb) == i:
                        b = (self.sx(nb[0] + 0.5), GROUND_Y + int((nb[1] + 0.5) * CELL))
                        pygame.draw.line(surf, theme.OUTLINE, a, b, 9)
                        pygame.draw.line(surf, (170, 176, 190), a, b, 5)
                        if flowing:
                            pygame.draw.line(surf, (24, 22, 30), a, b, 2)
                pygame.draw.circle(surf, (170, 176, 190), a, 4)
            # Still to drill: a dotted line, and the drill bit at work.
            for c, r in rig.queue:
                pygame.draw.circle(surf, (255, 230, 120), (self.sx(c + 0.5), GROUND_Y + int((r + 0.5) * CELL)), 2)
            if rig.queue:
                c, r = rig.queue[0]
                cx, cy = self.sx(c + 0.5), GROUND_Y + int((r + 0.5) * CELL)
                spin = self.clock * 12
                pygame.draw.polygon(surf, (220, 224, 236), [(cx + math.cos(spin + a) * 9, cy + math.sin(spin + a) * 9)
                                                             for a in (0, 2.1, 4.2)])
                pygame.draw.circle(surf, theme.OUTLINE, (cx, cy), 4)
        self._draw_preview(surf)

    def _draw_preview(self, surf):
        """What a click would do: the scan's reach, or the pipe's route and price."""
        if self.panel or not self.hover:
            return
        cell = self.cell_at(self.hover)
        if cell is None or not self.field.owned(cell[0]):
            return
        c, r = cell
        if self.tool == "SCAN":
            x, y = self.sx(c + 0.5), GROUND_Y + int((r + 0.5) * CELL)
            pygame.draw.circle(surf, theme.ACCENT, (x, y), int((oilmod.SCAN_RADIUS + 0.5) * CELL), 2)
        elif self.tool == "PIPE":
            key = (c, r, self.sel_rig, len(self.field.rigs), sum(len(rg.pipe) + len(rg.queue) for rg in self.field.rigs))
            if self.preview is None or self.preview[0] != key:
                self.preview = (key, self.field.plan_pipe(c, r, self.sel_rig))
            plan = self.preview[1]
            if plan:
                for pc, pr in plan[1]:
                    rect = pygame.Rect(self.sx(pc) + 6, GROUND_Y + pr * CELL + 6, CELL - 12, CELL - 12)
                    pygame.draw.rect(surf, theme.ACCENT, rect, 2, border_radius=4)
                cost = oilmod.PIPE_PRICE * len(plan[1])
                theme.ptext(surf, money(cost), (self.hover[0] + 16, self.hover[1] - 22), 14,
                            theme.ACCENT if self.game.cash >= cost else theme.DANGER)
        elif self.tool == "RIG":
            x = self.sx(c)
            pygame.draw.rect(surf, theme.ACCENT, (x, GROUND_Y - 120, CELL, 120), 2)

    def _draw_surface(self, surf):
        f = self.field
        lit = int(self.clock * 2) % 2 == 0
        road = pygame.Rect(0, GROUND_Y - 10, theme.WIDTH, 10)
        pygame.draw.rect(surf, (70, 70, 80), road)
        for x in range(-int(self.cam) % 40 - 40, theme.WIDTH, 40):
            pygame.draw.rect(surf, (230, 220, 120), (x, GROUND_Y - 6, 18, 2))
        # The plot for sale, past the right-hand buyer.
        sale_x = self.sx(f.width + BUYER_W + 1)
        if -PLOT * CELL < sale_x < theme.WIDTH:
            pygame.draw.rect(surf, (110, 150, 90), (sale_x, GROUND_Y - 4, PLOT * CELL, 4))
            post = pygame.Rect(sale_x + PLOT * CELL // 2 - 4, GROUND_Y - 70, 8, 66)
            pygame.draw.rect(surf, (130, 90, 56), post)
            board = pygame.Rect(sale_x + 10, GROUND_Y - 110, PLOT * CELL - 20, 46)
            theme.rounded(surf, (250, 246, 230), board, 6)
            theme.rounded(surf, theme.OUTLINE, board, 6, 2)
            theme.ptext(surf, "FOR SALE", (board.centerx, board.y + 6), 14, (200, 60, 50), anchor="midtop")
            theme.ptext(surf, money(f.land_price()), (board.centerx, board.y + 24), 14, (40, 40, 48), anchor="midtop")
        for p in range(f.plots + 1):                          # fence posts between plots
            x = self.sx(p * PLOT)
            if 0 <= x < theme.WIDTH:
                pygame.draw.line(surf, (130, 90, 56), (x, GROUND_Y - 22), (x, GROUND_Y - 4), 3)
        for side in ("L", "R"):
            img = art.oil_buyer(BUYER_NAMES[side], BUYER_COLORS[side], BUYER_W * CELL + 20, lit)
            left = -BUYER_W - 1 if side == "L" else f.width + 0.5
            x = self.sx(left) - 10
            surf.blit(img, (x, GROUND_Y - img.get_height()))
            board = pygame.Rect(x + 16, GROUND_Y - 186, BUYER_W * CELL - 12, 30)
            theme.rounded(surf, theme.OUTLINE, board.inflate(4, 4), 6)
            theme.rounded(surf, (30, 30, 36), board, 6)
            hist = f.history[side]
            up = f.prices[side] >= hist[-5]
            theme.ptext(surf, f"${f.prices[side]:.2f}", (board.x + 8, board.y + 7), 15,
                        theme.SUCCESS if up else theme.DANGER)
            pygame.draw.polygon(surf, theme.SUCCESS if up else theme.DANGER,
                                [(board.right - 18, board.y + (20 if up else 10)), (board.right - 8, board.y + (20 if up else 10)),
                                 (board.right - 13, board.y + (8 if up else 22))])
        nod = int(self.clock * 3) % 3
        for i, rig in enumerate(f.rigs):
            img = rig_sprite(rig.tank / f.stat("TANKS"), i == self.sel_rig, nod if rig.tank < f.stat("TANKS") else 1)
            surf.blit(img, (self.sx(rig.col + 0.5) - 24, GROUND_Y - 128))
            theme.ptext(surf, str(i + 1), (self.sx(rig.col + 0.5), GROUND_Y - 146), 13, theme.TEXT, anchor="midtop")
        cap = f.stat("TRUCK SIZE")
        order = sorted(range(len(f.trucks)), key=lambda i: i == self.sel_truck)
        for i in order:
            t = f.trucks[i]
            goal_x = f._goal_x(t.goal) if t.goal else t.x
            facing = -1 if goal_x < t.x - 0.01 else 1
            img = truck_sprite(t.load / cap, facing, t.auto and bool(f.stat("DISPATCHER")), i == self.sel_truck)
            surf.blit(img, self._truck_rect(i))

    def _draw_hud(self, surf):
        f = self.field
        theme.panel(surf, (4, 4, theme.WIDTH - 8, HUD_H - 8), edge_w=2)
        theme.ptext(surf, "CASH", (20, 10), 12, theme.TEXT_DIM)
        theme.ptext(surf, money(self.game.cash), (20, 26), 24, theme.SUCCESS)
        theme.ptext(surf, "OIL EARNED", (200, 10), 12, theme.TEXT_DIM)
        theme.ptext(surf, money(f.earned), (200, 26), 20, theme.TEXT)
        for k, side in enumerate(("L", "R")):
            x = 380 + k * 270
            theme.ptext(surf, BUYER_NAMES[side] + (" (LEFT)" if side == "L" else " (RIGHT)"), (x, 10), 12,
                        theme.TEXT_DIM)
            theme.ptext(surf, f"${f.prices[side]:.2f}", (x, 28), 20, BUYER_COLORS[side])
            graph = pygame.Rect(x + 90, 28, 150, 28)
            pygame.draw.rect(surf, theme.INNER, graph, border_radius=4)
            hist = f.history[side]
            lo, hi = min(hist), max(hist)
            span = max(0.2, hi - lo)
            pts = [(graph.x + 3 + j * (graph.w - 6) / (len(hist) - 1), graph.bottom - 3 - (v - lo) / span * (graph.h - 6))
                   for j, v in enumerate(hist)]
            pygame.draw.lines(surf, BUYER_COLORS[side], False, pts, 2)
        self.btn_land.draw(surf)
        self.btn_back.draw(surf)

    def _draw_toolbar(self, surf):
        for b in self.tool_buttons + [self.btn_truck, self.btn_upgrades, self.btn_auto]:
            if b.visible:
                b.draw(surf)
        f = self.field
        if self.sel_truck is not None:
            t = f.trucks[self.sel_truck]
            text = f"TRUCK {self.sel_truck + 1}: {int(t.load)}/{f.stat('TRUCK SIZE')} BBL"
        elif self.sel_rig is not None and self.sel_rig < len(f.rigs):
            rig = f.rigs[self.sel_rig]
            left = sum(p.amount for p in f.rig_pockets(rig))
            text = f"RIG {self.sel_rig + 1}: TANK {int(rig.tank)}/{f.stat('TANKS')}, {int(left):,} BBL LEFT BELOW"
        else:
            text = f"{len(f.rigs)} RIGS  {len(f.trucks)} TRUCKS  {f.plots} PLOTS"
        theme.ptext(surf, text, (16 + 3 * 158 + 340, TOOLBAR_Y + 12), 13, theme.TEXT_DIM)

    def _draw_panel(self, surf):
        f = self.field
        shade = pygame.Surface((theme.WIDTH, theme.HEIGHT), pygame.SRCALPHA)
        shade.fill((*theme.OUTLINE, 160))
        surf.blit(shade, (0, 0))
        p = pygame.Rect(76, 96, 1128, 600)
        theme.panel(surf, p, edge=(70, 70, 84), edge_w=4)
        theme.logo(surf, "OIL UPGRADES", (p.x + 190, p.y + 40), 34, angle=0)
        theme.ptext(surf, f"CASH {money(self.game.cash)}", (p.right - 96, p.y + 30), 20, theme.SUCCESS,
                    anchor="topright")
        for k, name in enumerate(OIL_UPGRADES):
            r = self._card(k)
            theme.rounded(surf, theme.INNER, r, 12)
            lvl = f.levels[name]
            top = len(OIL_UPGRADES[name][0]) - 1
            theme.ptext(surf, name, (r.x + 16, r.y + 12), 18)
            theme.text(surf, OIL_INFO[name], (r.x + 16, r.y + 40), 13, theme.TEXT_DIM, bold=False)
            for n in range(1, top + 1):
                pip = pygame.Rect(r.x + 16 + (n - 1) * 20, r.y + 66, 15, 15)
                pygame.draw.rect(surf, theme.ACCENT if n <= lvl else theme.PANEL, pip, border_radius=4)
                pygame.draw.rect(surf, theme.OUTLINE, pip, 2, border_radius=4)
            now = OIL_UPGRADES[name][0][lvl]
            nxt = OIL_UPGRADES[name][0][lvl + 1] if lvl < top else None
            fmt = (lambda v: "YES" if v else "NO") if name in ("ROCK BIT", "DISPATCHER") else (lambda v: f"{v:g}")
            theme.ptext(surf, f"{fmt(now)}  >  {fmt(nxt)}" if nxt is not None else f"{fmt(now)}  (BEST)",
                        (r.x + 190, r.y + 66), 13, theme.TEXT if nxt is not None else theme.TEXT_DIM)
        for b in self.panel_buttons:
            b.draw(surf)
