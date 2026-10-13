"""Deep Dig: fly the drill pod, dig for ore, and spend it on upgrades in the town on the surface.

Arrow keys or WASD fly and drill (down digs, sideways into a wall digs). E (or Enter) uses the
building you're parked at. 1-5 use items. Your game is saved as you play.
"""

from __future__ import annotations

import math
import random

import pygame

from ..deepdig import engine as dd
from ..deepdig.engine import (BUILDINGS, FEET_PER_ROW, ITEM_KEYS, ITEMS, UPGRADE_INFO, UPGRADES, W, DeepDig,
                              DigError, tile_name, tile_value)
from ..deepdig.save import delete_save, load_game, save_game
from . import deepdig_art as art
from . import sfx, theme
from .menus import Scene, status_bar
from .widgets import Button
from .xp import XpTracker

TILE = art.TILE
HUD = pygame.Rect(0, 0, 1280, 64)
VIEW = pygame.Rect(0, HUD.bottom, 1280, 800 - HUD.bottom - 30)
LEFT_KEYS = (pygame.K_LEFT, pygame.K_a)
RIGHT_KEYS = (pygame.K_RIGHT, pygame.K_d)
UP_KEYS = (pygame.K_UP, pygame.K_w)
DOWN_KEYS = (pygame.K_DOWN, pygame.K_s)
ITEM_ICONS = {"REPAIR KIT": (230, 90, 80), "FUEL CAN": (240, 170, 40), "DYNAMITE": (220, 60, 50),
              "MEGA BLAST": (150, 60, 220), "TELEPORTER": (80, 200, 240)}


def money(n: int) -> str:
    return f"${n:,}"


class DeepDigScene(Scene):
    def __init__(self, app, game: DeepDig | None = None):
        super().__init__(app)
        loaded = game or load_game()
        self.game = loaded or DeepDig()
        self.fresh = loaded is None
        self.xp = XpTracker(self, "deepdig")
        self.keys: set[int] = set()
        self.cam = [self.game.x * TILE - VIEW.w / 2, self.game.y * TILE - VIEW.h / 2]
        self.particles: list[list] = []     # [x, y, vx, vy, ttl, color, size] in world pixels
        self.floaters: list[list] = []      # [text, x, y, ttl, color]
        self.shake = 0.0
        self.hurt_flash = 0.0
        self.flash: tuple[str, float] | None = None
        self.panel: str | None = None       # FUEL, SELL, SHOP, REPAIR
        self.overlay: str | None = None     # pause, confirm_new, win
        self.panel_buttons: list[Button] = []
        self.overlay_buttons: list[Button] = []
        self.save_timer = 0.0
        self.spin = 0.0
        self.splash: tuple | None = ("DEEP DIG", "WELCOME BACK!" if not self.fresh else "DIG DOWN, FIND ORE, GET RICH",
                                     1.8, 1.8)
        self.btn_menu = Button((HUD.right - 104, 12, 92, 40), "MENU", lambda: self._set_overlay("pause"), size=15)
        self.flash = ("Arrows or WASD: fly and drill. Park at a building and press E.", 6.0) if self.fresh else None
        sfx.play("shuffle")

    # ================================================================== helpers

    @property
    def held(self):
        k = self.keys
        return (any(x in k for x in LEFT_KEYS), any(x in k for x in RIGHT_KEYS), any(x in k for x in UP_KEYS),
                any(x in k for x in DOWN_KEYS))

    def say(self, text: str, secs: float = 2.6):
        self.flash = (text, secs)

    def error(self, text: str):
        self.say(text, 2.8)
        sfx.play("error")

    def to_screen(self, wx: float, wy: float) -> tuple[int, int]:
        sx = self.shake and random.uniform(-self.shake, self.shake) * 8
        sy = self.shake and random.uniform(-self.shake, self.shake) * 8
        return int(wx - self.cam[0] + VIEW.x + sx), int(wy - self.cam[1] + VIEW.y + sy)

    def burst(self, wx, wy, color, n=10, speed=160, size=4):
        for _ in range(n):
            a = random.uniform(0, 2 * math.pi)
            v = random.uniform(0.3, 1.0) * speed
            self.particles.append([wx, wy, math.cos(a) * v, math.sin(a) * v - speed * 0.3,
                                   random.uniform(0.4, 0.9), color, random.uniform(2, size)])

    def floater(self, text, wx, wy, color=None):
        self.floaters.append([text, wx, wy, 1.6, color or theme.ACCENT])

    def save(self):
        save_game(self.game)
        self.save_timer = 0.0

    # ================================================================== actions

    def use_building(self):
        b = self.game.building()
        if b is None:
            self.error("Park at a building first (land on the ground in front of it).")
            return
        self.open_panel(b)

    def open_panel(self, name: str):
        self.panel = name
        self.keys.clear()
        self.game.vx = 0
        self._build_panel()
        sfx.play("select")

    def close_panel(self):
        self.panel = None
        self.panel_buttons = []
        self.save()

    def _do(self, fn, *args):
        try:
            fn(*args)
        except DigError as e:
            self.error(str(e))
            return
        self._consume()
        self._build_panel()
        self.save()

    def use_item(self, name: str):
        if self.panel or self.overlay:
            return
        self._do(self.game.use_item, name)

    def _build_panel(self):
        g = self.game
        p = self.panel_rect()
        out = []
        primary = dict(color="ACCENT", text_color="OUTLINE")
        if self.panel == "FUEL":
            cost = g.refuel_cost()
            label = f"FILL UP  {money(cost)}" if cost else "TANK FULL"
            if cost and g.cash < dd.FUEL_PRICE and g.fuel < 0.25 * g.max_fuel:
                label = "FREE EMERGENCY FUEL"
            b = Button((p.centerx - 170, p.bottom - 150, 340, 64), label,
                       lambda: self._do(g.refuel), size=22, **primary)
            b.enabled = cost > 0
            out.append(b)
        elif self.panel == "REPAIR":
            cost = g.repair_cost()
            b = Button((p.centerx - 170, p.bottom - 150, 340, 64), f"REPAIR  {money(cost)}" if cost else "ALL FIXED",
                       lambda: self._do(g.repair), size=22, **primary)
            b.enabled = cost > 0
            out.append(b)
        elif self.panel == "SELL":
            b = Button((p.centerx - 170, p.bottom - 150, 340, 64),
                       f"SELL ALL  {money(g.cargo_value)}" if g.cargo else "NOTHING TO SELL",
                       lambda: self._do(g.sell), size=22, **primary)
            b.enabled = bool(g.cargo)
            out.append(b)
        elif self.panel == "SHOP":
            for k, name in enumerate(UPGRADES):
                price = g.upgrade_price(name)
                r = self.shop_row(k)
                b = Button((r.right - 170, r.y + 10, 160, 48), "MAXED" if price is None else money(price),
                           lambda n=name: self._do(g.buy_upgrade, n), size=17,
                           **(primary if price is not None and g.cash >= price else {}))
                b.enabled = price is not None and g.cash >= price
                out.append(b)
            for k, name in enumerate(ITEM_KEYS):
                price = ITEMS[name][0]
                r = self.item_row(k)
                b = Button((r.right - 130, r.y + 10, 120, 48), money(price), lambda n=name: self._do(g.buy_item, n),
                           size=16, **(primary if g.cash >= price else {}))
                b.enabled = g.cash >= price
                out.append(b)
        out.append(Button((p.right - 64, p.y + 14, 48, 44), "X", self.close_panel, size=18))
        self.panel_buttons = out

    def panel_rect(self) -> pygame.Rect:
        if self.panel == "SHOP":
            return pygame.Rect(60, 90, 1160, 640)
        return pygame.Rect(340, 150, 600, 470)

    def shop_row(self, k: int) -> pygame.Rect:
        p = self.panel_rect()
        return pygame.Rect(p.x + 24, p.y + 92 + k * 86, 640, 76)

    def item_row(self, k: int) -> pygame.Rect:
        p = self.panel_rect()
        return pygame.Rect(p.x + 690, p.y + 92 + k * 100, 446, 88)

    # ================================================================== overlays

    def _set_overlay(self, kind: str | None):
        self.overlay = kind
        self.keys.clear()
        cx = theme.WIDTH // 2
        primary = dict(color="ACCENT", text_color="OUTLINE")
        if kind == "pause":
            self.save()
            self.overlay_buttons = [
                Button((cx - 150, 300, 300, 58), "RESUME", lambda: self._set_overlay(None), size=22, **primary),
                Button((cx - 150, 370, 300, 52), "NEW GAME", lambda: self._set_overlay("confirm_new"), size=18),
                Button((cx - 150, 434, 300, 52), "MAIN MENU", self.to_menu, size=18)]
        elif kind == "confirm_new":
            self.overlay_buttons = [
                Button((cx - 290, 430, 270, 58), "YES, START OVER", self.new_game, size=18, color="DANGER"),
                Button((cx + 20, 430, 270, 58), "KEEP DIGGING", lambda: self._set_overlay("pause"), size=18,
                       **primary)]
        elif kind == "win":
            self.overlay_buttons = [Button((cx - 160, 560, 320, 60), "KEEP DIGGING", lambda: self._set_overlay(None),
                                           size=22, **primary)]
        else:
            self.overlay_buttons = []

    def new_game(self):
        delete_save()
        self.app.go(DeepDigScene(self.app, DeepDig()))

    def to_menu(self):
        self.save()
        from .menus import MenuScene
        self.app.go(MenuScene(self.app))

    # ================================================================== input

    def handle(self, event):
        if self.overlay:
            for b in self.overlay_buttons:
                if b.handle(event):
                    return
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._set_overlay(None if self.overlay in ("pause", "win") else "pause")
            return
        if self.splash and event.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN):
            self.splash = None
        if self.panel:
            for b in self.panel_buttons:
                if b.handle(event):
                    return
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_e, pygame.K_RETURN):
                self.close_panel()
            return
        if self.btn_menu.handle(event):
            return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._set_overlay("pause")
            elif event.key in (pygame.K_e, pygame.K_RETURN):
                self.use_building()
            elif pygame.K_1 <= event.key <= pygame.K_5:
                self.use_item(ITEM_KEYS[event.key - pygame.K_1])
            else:
                self.keys.add(event.key)
        elif event.type == pygame.KEYUP:
            self.keys.discard(event.key)

    # ================================================================== update

    def update(self, dt: float):
        super().update(dt)
        self.xp.update(dt)
        if self.flash:
            self.flash = (self.flash[0], self.flash[1] - dt) if self.flash[1] > dt else None
        if self.splash:
            t, s, left, total = self.splash
            self.splash = (t, s, left - dt, total) if left > dt else None
        g = self.game
        if not self.overlay and not self.panel:
            left, right, up, down = self.held
            g.step(dt, left, right, up, down)
            self._consume()
            if g.drill:
                self.spin += dt * 4
                if random.random() < dt * 30:
                    d = g.drill
                    color = art.DIRT_COLORS[art.band(d.row)]
                    self.burst((d.col + 0.5) * TILE, (d.row + 0.5) * TILE, color, 2, 110, 4)
            if g.thrusting and random.random() < dt * 40:
                self.particles.append([g.x * TILE + random.uniform(-10, 10), g.y * TILE + 18, random.uniform(-20, 20),
                                       random.uniform(60, 120), 0.35, (255, 170, 60), 3])
        # Camera follows the pod smoothly.
        tx = g.x * TILE - VIEW.w / 2
        ty = g.y * TILE - VIEW.h / 2 + 40
        k = min(1.0, dt * 8)
        self.cam[0] += (tx - self.cam[0]) * k
        self.cam[1] += (ty - self.cam[1]) * k
        self.cam[0] = max(0, min(W * TILE - VIEW.w, self.cam[0]))
        self.cam[1] = max(-9 * TILE, min(dd.H * TILE - VIEW.h, self.cam[1]))
        for p in self.particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += 500 * dt
            p[4] -= dt
        self.particles = [p for p in self.particles if p[4] > 0][-400:]
        for f in self.floaters:
            f[2] -= 30 * dt
            f[3] -= dt
        self.floaters = [f for f in self.floaters if f[3] > 0]
        self.shake = max(0.0, self.shake - dt * 2.5)
        self.hurt_flash = max(0.0, self.hurt_flash - dt)
        self.save_timer += dt
        if self.save_timer > 20 and not g.drill:
            self.save()

    def _consume(self):
        g = self.game
        for ev in g.pop_events():
            k = ev[0]
            if k == "drill":
                sfx.play("click")
            elif k == "ore":
                _, t, col, row = ev
                self.floater(f"+{tile_name(t)}", (col + 0.5) * TILE, row * TILE, art.ORES[t - dd.ORE0].color
                             if t != dd.CORE else (255, 120, 220))
                self.burst((col + 0.5) * TILE, (row + 0.5) * TILE, (255, 240, 160), 14, 200, 4)
                sfx.play("coin")
                self.xp.gain(1)
            elif k == "full":
                self.floater("CARGO FULL!", g.x * TILE, g.y * TILE - 30, theme.DANGER)
                self.say("Your cargo bay is full - fly up and sell, or buy a bigger bay.")
                sfx.play("error")
            elif k == "rock":
                self.say("Too hard to drill! Go around it, or blow it up with dynamite (key 3).", 2.2)
                sfx.play("deselect")
            elif k in ("hurt", "bump"):
                self.hurt_flash = 0.4
                self.shake = max(self.shake, 0.6)
                if k == "hurt":
                    self.floater(f"-{ev[1]} HULL", g.x * TILE, g.y * TILE - 26, theme.DANGER)
                sfx.play("skip")
            elif k == "boom":
                _, col, row, why = ev
                self.shake = 1.2
                self.burst((col + 0.5) * TILE, (row + 0.5) * TILE, (255, 160, 40), 40, 320, 7)
                self.burst((col + 0.5) * TILE, (row + 0.5) * TILE, (255, 240, 180), 20, 200, 5)
                if why == "gas":
                    self.say("BOOM! A gas pocket exploded.")
                sfx.play("game_lose")
            elif k == "lava":
                _, col, row = ev
                self.shake = 0.9
                self.burst((col + 0.5) * TILE, (row + 0.5) * TILE, (255, 90, 20), 30, 260, 6)
                self.say("Ouch! Lava. Upgrade your hull and radiator for the deep stuff.")
            elif k == "tow":
                _, why, fee, lost = ev
                self.say(f"{why}! Towed to the surface for {money(fee)}" + (f" - {lost} ore lost." if lost else "."),
                         5.0)
                sfx.play("game_lose")
                self.shake = 0.8
                self.save()
            elif k == "empty":
                self.say("Out of fuel! Roll to the FUEL station (it's free to roll on the surface).")
            elif k == "sell":
                _, total, chips, counts = ev
                self.floater(f"+{money(total)}", g.x * TILE, g.y * TILE - 40, theme.SUCCESS)
                if chips:
                    self.app.settings.chip_bank += chips
                    self.app.settings.save()
                    self.say(f"Sold for {money(total)}! +{chips} chip{'s' if chips != 1 else ''} for your Chip Bank.")
                else:
                    self.say(f"Sold for {money(total)}!")
                self.xp.gain(max(2, min(200, total // 40)))
                sfx.play("round_win")
            elif k in ("refuel", "repair"):
                sfx.play("coin")
            elif k in ("upgrade", "buy"):
                sfx.play("lay")
                self.say(f"{ev[1].title()} upgraded to level {ev[2]}!" if k == "upgrade" else f"Bought a {ev[1].lower()}.")
            elif k == "item":
                sfx.play("phase")
            elif k == "teleport":
                self.burst(g.x * TILE, g.y * TILE, (120, 220, 255), 30, 240, 5)
                self.say("Beamed back to the surface!")
            elif k == "depth":
                self.floater(f"{int(ev[1] * FEET_PER_ROW):,} FT!", g.x * TILE, g.y * TILE - 50, (150, 230, 255))
                self.xp.gain(25)
                sfx.play("phase")
            elif k == "land":
                if ev[1] > 4:
                    self.burst(g.x * TILE, (g.y + 0.4) * TILE, (200, 180, 150), 6, 90, 3)
            elif k == "core":
                self.xp.gain(500)
                sfx.play("game_win")
                self._set_overlay("win")
                self.save()

    # ================================================================== drawing

    def draw(self, surf):
        g = self.game
        surf.fill(art.tunnel_color(max(0, g.row)))
        clip = surf.get_clip()
        surf.set_clip(VIEW)
        self._draw_world(surf)
        self._draw_effects(surf)
        self._draw_dark(surf)
        surf.set_clip(clip)
        self._draw_hud(surf)
        self._draw_prompt(surf)
        status_bar(surf, self.flash[0] if self.flash else self._status())
        if self.panel:
            self._draw_panel(surf)
        if self.splash:
            self._draw_splash(surf)
        if self.overlay:
            self._draw_overlay(surf)
        self.xp.draw(surf)

    def _status(self) -> str:
        g = self.game
        b = g.building()
        if b:
            return f"Press E to use the {art.BUILDING_STYLE[b][1].title()}."
        if g.on_surface:
            return "Drill down to dig. Fly back up to sell ore at the Ore Buyer."
        if len(g.cargo) >= g.cargo_space:
            return "Cargo bay full! Fly up and sell it."
        if g.fuel < g.max_fuel * 0.2:
            return "Fuel is low! Head back up to the fuel station (or use a fuel can: key 2)."
        if g.hull < g.max_hull * 0.25:
            return "Hull damaged! Repair on the surface (or use a repair kit: key 1)."
        return "Down/Left/Right drill, Up flies. 1-5 use items, Esc for the menu."

    def _draw_world(self, surf):
        g = self.game
        cam_x, cam_y = self.cam
        # Sky and the town, when they're in view.
        if cam_y < 0:
            sky = art.sky(VIEW.w, int(-cam_y) + 4)
            surf.blit(sky, (VIEW.x, VIEW.y))
            for name, (a, b) in BUILDINGS.items():
                width = (b - a + 1) * TILE
                img = art.building(name, width)
                x, y = self.to_screen(a * TILE, 0)
                surf.blit(img, (x, y - img.get_height()))
        c0 = max(0, int(cam_x // TILE))
        c1 = min(W - 1, int((cam_x + VIEW.w) // TILE) + 1)
        r0 = max(0, int(cam_y // TILE))
        r1 = min(dd.H - 1, int((cam_y + VIEW.h) // TILE) + 1)
        for row in range(r0, r1 + 1):
            line = g.grid[row]
            for col in range(c0, c1 + 1):
                t = line[col]
                x, y = self.to_screen(col * TILE, row * TILE)
                img = art.tile_surface(t, row, col)
                if img is None:
                    pygame.draw.rect(surf, art.tunnel_color(row), (x, y, TILE, TILE))
                else:
                    surf.blit(img, (x, y))
                    if t == dd.LAVA and (int(self.clock * 6) + col + row) % 7 == 0:
                        pygame.draw.circle(surf, (255, 220, 120), (x + 20, y + 20), 4)
        # The pod.
        d = g.drill
        drilling = None
        if d:
            drilling = "down" if d.row > g.y + 0.2 else ("right" if d.col > g.x else "left")
        img = art.pod(g.facing, drilling, self.spin, g.thrusting, self.clock, self.hurt_flash)
        x, y = self.to_screen(g.x * TILE, g.y * TILE)
        jitter = (random.uniform(-1.5, 1.5) if d else 0)
        surf.blit(img, img.get_rect(center=(x + jitter, y - 2)))

    def _draw_effects(self, surf):
        for x, y, _, _, ttl, color, size in self.particles:
            sx, sy = self.to_screen(x, y)
            pygame.draw.circle(surf, color, (sx, sy), max(1, int(size * min(1.0, ttl * 2))))
        for text, x, y, ttl, color in self.floaters:
            img = theme.pixel_surface(text, 18, color)
            if ttl < 0.4:
                img.set_alpha(int(255 * ttl / 0.4))
            sx, sy = self.to_screen(x, y)
            surf.blit(img, img.get_rect(center=(sx, sy)))

    def _draw_dark(self, surf):
        """Underground it gets darker the deeper you go; the pod's lamp lights the way."""
        g = self.game
        depth = max(0.0, g.y) / dd.H
        alpha = int(min(235, 40 + 260 * depth)) if g.y > 2 else int(max(0, g.y) * 20)
        if alpha <= 0:
            return
        dark = pygame.Surface(VIEW.size, pygame.SRCALPHA)
        dark.fill((0, 0, 8, alpha))
        radius = 300
        hole = art.light_hole(radius)
        x, y = self.to_screen(g.x * TILE, g.y * TILE)
        dark.blit(hole, (x - radius - VIEW.x, y - radius - VIEW.y), special_flags=pygame.BLEND_RGBA_MIN)
        surf.blit(dark, VIEW.topleft)
        if g.heat() > 0:   # a red haze when it's hot
            haze = pygame.Surface(VIEW.size, pygame.SRCALPHA)
            haze.fill((255, 60, 0, int(60 * g.heat())))
            surf.blit(haze, VIEW.topleft)
        if self.hurt_flash > 0:
            red = pygame.Surface(VIEW.size, pygame.SRCALPHA)
            red.fill((255, 0, 0, int(120 * self.hurt_flash)))
            surf.blit(red, VIEW.topleft)

    def _gauge(self, surf, x, label, value, maximum, color, low_color):
        theme.ptext(surf, label, (x, 8), 12, theme.TEXT_DIM)
        bar = pygame.Rect(x, 26, 150, 18)
        pygame.draw.rect(surf, theme.OUTLINE, bar.move(0, 2), border_radius=9)
        pygame.draw.rect(surf, theme.INNER, bar, border_radius=9)
        k = max(0.0, min(1.0, value / maximum)) if maximum else 0
        low = k < 0.25
        col = low_color if low and int(self.clock * 4) % 2 else color
        if k > 0:
            pygame.draw.rect(surf, col, (bar.x, bar.y, max(10, int(bar.w * k)), bar.h), border_radius=9)
        theme.ptext(surf, f"{value:.0f}/{maximum:.0f}", bar.center, 12, theme.TEXT, anchor="center")

    def _draw_hud(self, surf):
        g = self.game
        theme.panel(surf, HUD.inflate(-8, -8), edge_w=2)
        theme.ptext(surf, "CASH", (20, 8), 12, theme.TEXT_DIM)
        theme.ptext(surf, money(g.cash), (20, 24), 26, theme.SUCCESS)
        theme.ptext(surf, "DEPTH", (210, 8), 12, theme.TEXT_DIM)
        theme.ptext(surf, f"{g.depth_ft:,} FT", (210, 24), 26, theme.ACCENT)
        self._gauge(surf, 380, "FUEL", g.fuel, g.max_fuel, (240, 170, 40), theme.DANGER)
        self._gauge(surf, 548, "HULL", g.hull, g.max_hull, (90, 200, 110), theme.DANGER)
        theme.ptext(surf, "CARGO", (716, 8), 12, theme.TEXT_DIM)
        full = len(g.cargo) >= g.cargo_space
        theme.ptext(surf, f"{len(g.cargo)}/{g.cargo_space}", (716, 24), 24, theme.DANGER if full else theme.TEXT)
        theme.ptext(surf, money(g.cargo_value), (790, 30), 13, theme.TEXT_DIM)
        x = 880
        for n, name in enumerate(ITEM_KEYS):
            box = pygame.Rect(x + n * 52, 12, 46, 40)
            theme.rounded(surf, theme.INNER, box, 8)
            pygame.draw.circle(surf, ITEM_ICONS[name], (box.centerx, box.centery - 2), 10)
            theme.ptext(surf, str(n + 1), (box.x + 4, box.y + 2), 10, theme.TEXT_DIM)
            count = g.items[name]
            theme.ptext(surf, str(count), (box.right - 4, box.bottom - 2), 13,
                        theme.TEXT if count else theme.TEXT_FAINT, anchor="bottomright")
        if g.heat() > 0:
            theme.ptext(surf, f"HEAT {int(g.heat() * 100)}%", (262, 8), 12, (255, 120, 60))
        self.btn_menu.draw(surf)

    def _draw_prompt(self, surf):
        b = self.game.building()
        if not b or self.panel or self.overlay:
            return
        a, c = BUILDINGS[b]
        x, y = self.to_screen((a + c + 1) / 2 * TILE, -5.2 * TILE)
        img = theme.pixel_surface(f"PRESS E: {art.BUILDING_STYLE[b][1]}", 18, theme.ACCENT)
        r = img.get_rect(center=(x, y + math.sin(self.clock * 4) * 4))
        theme.rounded(surf, theme.OUTLINE, r.inflate(16, 10), 8)
        surf.blit(img, r)

    def _draw_panel(self, surf):
        g = self.game
        shade = pygame.Surface((theme.WIDTH, theme.HEIGHT), pygame.SRCALPHA)
        shade.fill((*theme.OUTLINE, 150))
        surf.blit(shade, (0, 0))
        p = self.panel_rect()
        color, label = art.BUILDING_STYLE[self.panel]
        theme.panel(surf, p, edge=color, edge_w=4)
        theme.ptext(surf, label, (p.x + 28, p.y + 22), 32, color)
        theme.ptext(surf, f"CASH {money(g.cash)}", (p.right - 90, p.y + 30), 20, theme.SUCCESS, anchor="topright")
        if self.panel == "FUEL":
            self._big_bar(surf, p, "FUEL", g.fuel, g.max_fuel, (240, 170, 40))
            theme.ptext(surf, f"${dd.FUEL_PRICE} per litre", (p.centerx, p.y + 250), 18, theme.TEXT_DIM, anchor="center")
        elif self.panel == "REPAIR":
            self._big_bar(surf, p, "HULL", g.hull, g.max_hull, (90, 200, 110))
            theme.ptext(surf, f"${dd.REPAIR_PRICE} per point", (p.centerx, p.y + 250), 18, theme.TEXT_DIM, anchor="center")
        elif self.panel == "SELL":
            counts: dict[int, int] = {}
            for t in g.cargo:
                counts[t] = counts.get(t, 0) + 1
            y = p.y + 92
            if not counts:
                theme.ptext(surf, "Your hold is empty. Go dig!", (p.centerx, p.y + 200), 20, theme.TEXT_DIM,
                            anchor="center")
            for t, n in sorted(counts.items(), key=lambda kv: -tile_value(kv[0]))[:6]:
                img = art.tile_surface(t, 100, 3)
                surf.blit(img, (p.x + 40, y))
                theme.ptext(surf, f"{tile_name(t)} x{n}", (p.x + 96, y + 8), 20)
                theme.ptext(surf, money(tile_value(t) * n), (p.right - 40, y + 8), 20, theme.SUCCESS, anchor="topright")
                y += 46
            theme.ptext(surf, f"Every {money(dd.CHIP_EVERY)} sold = 1 chip for your Chip Bank", (p.centerx, p.bottom - 60),
                        14, theme.TEXT_DIM, anchor="center")
        elif self.panel == "SHOP":
            theme.ptext(surf, "UPGRADES", (p.x + 28, p.y + 66), 16, theme.TEXT_DIM)
            theme.ptext(surf, "ITEMS (keys 1-5 to use)", (p.x + 690, p.y + 66), 16, theme.TEXT_DIM)
            for k, name in enumerate(UPGRADES):
                r = self.shop_row(k)
                theme.rounded(surf, theme.INNER, r, 10)
                theme.ptext(surf, name, (r.x + 16, r.y + 10), 20)
                theme.text(surf, UPGRADE_INFO[name], (r.x + 16, r.y + 42), 13, theme.TEXT_DIM, bold=False)
                lvl = g.levels[name]
                for n in range(1, len(UPGRADES[name][0])):
                    pip = pygame.Rect(r.x + 300 + n * 26, r.y + 18, 20, 20)
                    pygame.draw.rect(surf, theme.ACCENT if n <= lvl else theme.PANEL, pip, border_radius=5)
                    pygame.draw.rect(surf, theme.OUTLINE, pip, 2, border_radius=5)
                theme.ptext(surf, f"LEVEL {lvl}", (r.x + 330, r.y + 46), 12, theme.TEXT_DIM)
            for k, name in enumerate(ITEM_KEYS):
                r = self.item_row(k)
                theme.rounded(surf, theme.INNER, r, 10)
                pygame.draw.circle(surf, ITEM_ICONS[name], (r.x + 32, r.centery), 16)
                theme.ptext(surf, f"{name}  ({k + 1})", (r.x + 60, r.y + 12), 18)
                theme.text(surf, ITEMS[name][1], (r.x + 60, r.y + 42), 13, theme.TEXT_DIM, bold=False)
                theme.ptext(surf, f"YOU HAVE {g.items[name]}", (r.x + 60, r.y + 62), 12, theme.TEXT_FAINT)
        for b in self.panel_buttons:
            b.draw(surf)

    def _big_bar(self, surf, p, label, value, maximum, color):
        bar = pygame.Rect(p.x + 60, p.y + 150, p.w - 120, 40)
        theme.ptext(surf, f"{label} {value:.0f} / {maximum:.0f}", (bar.x, bar.y - 32), 20)
        pygame.draw.rect(surf, theme.OUTLINE, bar.move(0, 3), border_radius=14)
        pygame.draw.rect(surf, theme.INNER, bar, border_radius=14)
        k = max(0.0, min(1.0, value / maximum))
        if k:
            pygame.draw.rect(surf, color, (bar.x, bar.y, max(20, int(bar.w * k)), bar.h), border_radius=14)

    def _draw_splash(self, surf):
        title, sub, t, total = self.splash
        k = min(1.0, (total - t) / 0.25, t / 0.3)
        band = pygame.Rect(0, 300, theme.WIDTH, 170)
        shade = pygame.Surface(band.size, pygame.SRCALPHA)
        shade.fill((*theme.OUTLINE, int(200 * k)))
        surf.blit(shade, band)
        theme.logo(surf, title, (theme.WIDTH // 2 + int((1 - k) * -300), band.y + 70), 74, angle=6)
        theme.ptext(surf, sub, (theme.WIDTH // 2, band.bottom - 26), 20, anchor="center")

    def _draw_overlay(self, surf):
        g = self.game
        shade = pygame.Surface((theme.WIDTH, theme.HEIGHT), pygame.SRCALPHA)
        shade.fill((*theme.OUTLINE, 190))
        surf.blit(shade, (0, 0))
        cx = theme.WIDTH // 2
        if self.overlay == "pause":
            theme.panel(surf, (cx - 220, 160, 440, 360))
            theme.logo(surf, "PAUSED", (cx, 214), 40, angle=4)
            theme.ptext(surf, f"Deepest: {int(g.deepest * FEET_PER_ROW):,} ft   Earned: {money(g.earned)}",
                        (cx, 262), 14, theme.TEXT_DIM, anchor="center")
        elif self.overlay == "confirm_new":
            theme.panel(surf, (cx - 330, 250, 660, 280))
            theme.logo(surf, "START OVER?", (cx, 310), 40, angle=4)
            theme.ptext(surf, "Your saved game, cash and upgrades will be gone.", (cx, 372), 18, anchor="center")
            theme.ptext(surf, "(Chips already in your Chip Bank stay.)", (cx, 400), 14, theme.TEXT_DIM, anchor="center")
        elif self.overlay == "win":
            theme.panel(surf, (cx - 400, 150, 800, 500))
            theme.logo(surf, "YOU DID IT!", (cx, 230), 60, angle=4)
            theme.ptext(surf, "You found the HEART OF THE EARTH!", (cx, 320), 26, theme.ACCENT, anchor="center")
            theme.ptext(surf, f"Sell it at the Ore Buyer for {money(dd.CORE_VALUE)}.", (cx, 370), 20, anchor="center")
            theme.ptext(surf, f"Total earned so far: {money(g.earned)}", (cx, 420), 18, theme.TEXT_DIM, anchor="center")
        for b in self.overlay_buttons:
            b.draw(surf)
