"""Deep Dig: fly the drill pod, dig for ore, and spend it on upgrades in the town on the surface.

Arrow keys or WASD fly and drill (down digs, sideways into a wall digs). E (or Enter) uses the
building you're parked at. 1-5 use items. Your game is saved as you play.
"""

from __future__ import annotations

import math
import random

import pygame

from ..deepdig import engine as dd
from ..deepdig.engine import (BUILDINGS, FEET_PER_ROW, ITEM_KEYS, ITEMS, TOWN_W, UPGRADE_INFO, UPGRADE_SHOP, UPGRADES,
                              W, DeepDig, DigError, tile_name, tile_value, upgrade_text)
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
SHOP_UPGRADES = [n for n in UPGRADES if UPGRADE_SHOP[n] == "SHOP"]    # the garage's pod parts
LAB_UPGRADES = [n for n in UPGRADES if UPGRADE_SHOP[n] == "LAB"]      # the tech lab's gadgets (and the items)
BOT_UPGRADES = [n for n in UPGRADES if UPGRADE_SHOP[n] == "BOTS"]     # robotics: hire and improve dig bots


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
        self.discarded = False              # set when starting over, so leaving doesn't save the old dig
        self.spin = 0.0
        self.splash: tuple | None = ("DEEP DIG", "WELCOME BACK!" if not self.fresh else "DIG DOWN, FIND ORE, GET RICH",
                                     1.8, 1.8)
        self.btn_menu = Button((HUD.right - 104, 12, 92, 40), "MENU", lambda: self._set_overlay("pause"), size=15)
        self.flash = ("Arrows or WASD: fly and drill. Park at a building and press E.", 6.0) if self.fresh else None
        sfx.play("shuffle")

    # ================================================================== controller

    @property
    def pad_mode(self) -> str:
        """Flying and digging: the stick is the arrow keys. A shop or menu open: a pointer to click with."""
        return "cursor" if (self.panel or self.overlay) else "keys"

    @property
    def pad_buttons(self) -> dict:
        if self.panel or self.overlay:
            return {}                     # A clicks, B / Start back out
        return {"A": pygame.K_e, "LB": pygame.K_1, "RB": pygame.K_2, "X": pygame.K_3, "LT": pygame.K_4,
                "Y": pygame.K_5, "B": None}

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
        if not self.discarded:
            save_game(self.game)
        self.save_timer = 0.0

    def on_leave(self):
        """The app calls this when you leave the screen or close the window."""
        self.save()

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
            if cost and g.emergency_fuel():
                label = "FREE EMERGENCY FUEL"
            b = Button((p.centerx - 170, p.bottom - 110, 340, 64), label,
                       lambda: self._do(g.refuel), size=22, **primary)
            b.enabled = cost > 0
            out.append(b)
        elif self.panel == "REPAIR":
            cost = g.repair_cost()
            b = Button((p.centerx - 170, p.bottom - 110, 340, 64), f"REPAIR  {money(cost)}" if cost else "ALL FIXED",
                       lambda: self._do(g.repair), size=22, **primary)
            b.enabled = cost > 0
            out.append(b)
        elif self.panel == "BANK":
            n = g.can_exchange()
            for k, (label, amount) in enumerate((("1 CHIP", 1), ("10 CHIPS", 10), ("100 CHIPS", 100),
                                                 (f"ALL: {n:,}", n))):
                b = Button((p.x + 40 + (k % 2) * 270, p.bottom - 180 + (k // 2) * 76, 250, 62),
                           label, lambda a=amount: self._do(g.exchange, a), size=19,
                           **(primary if 0 < amount <= n else {}))
                b.enabled = 0 < amount <= n
                out.append(b)
        elif self.panel == "OIL":
            if g.oil is None:
                b = Button((p.centerx - 190, p.bottom - 100, 380, 64), f"BUY IT  {money(dd.OIL_PRICE)}",
                           lambda: self._do(g.buy_oil), size=22, **primary)
                b.enabled = g.cash >= dd.OIL_PRICE
            else:
                b = Button((p.centerx - 190, p.bottom - 100, 380, 64), "GO TO THE OIL FIELD", self.enter_oil, size=22,
                           **primary)
            out.append(b)
        elif self.panel == "SELL":
            b = Button((p.centerx - 170, p.bottom - 90, 340, 56),
                       f"SELL ALL  {money(g.cargo_value)}" if g.cargo else "NOTHING TO SELL",
                       lambda: self._do(g.sell), size=22, **primary)
            b.enabled = bool(g.cargo)
            out.append(b)
        elif self.panel in ("SHOP", "LAB", "BOTS"):
            for k, name in enumerate(self.panel_upgrades()):
                price = g.upgrade_price(name)
                r = self.card_rect(k)
                can = price is not None and g.cash >= price
                b = Button((r.right - 150, r.centery - 22, 136, 44), "MAXED" if price is None else money(price),
                           lambda n=name: self._do(g.buy_upgrade, n), size=16, **(primary if can else {}))
                b.enabled = can
                out.append(b)
            if self.panel == "LAB":
                for k, name in enumerate(ITEM_KEYS):
                    price = ITEMS[name][0]
                    r = self.item_rect(k)
                    b = Button((r.right - 126, r.centery - 22, 112, 44), money(price),
                               lambda n=name: self._do(g.buy_item, n), size=15, **(primary if g.cash >= price else {}))
                    b.enabled = g.cash >= price
                    out.append(b)
        out.append(Button((p.right - 62, p.y + 18, 46, 44), "X", self.close_panel, size=18))
        self.panel_buttons = out

    def enter_oil(self):
        """Over to the Oil Field (it comes back here when you leave it)."""
        from .oil_scene import OilFieldScene
        self.panel = None
        self.panel_buttons = []
        self.save()
        self.app.go(OilFieldScene(self.app, self))

    def panel_rect(self) -> pygame.Rect:
        if self.panel in ("SHOP", "LAB", "BOTS"):
            return pygame.Rect(60, 84, 1160, 656)
        return pygame.Rect(340, 140, 600, 500)

    def panel_upgrades(self) -> list[str]:
        return {"SHOP": SHOP_UPGRADES, "LAB": LAB_UPGRADES, "BOTS": BOT_UPGRADES}.get(self.panel, [])

    def card_rect(self, k: int) -> pygame.Rect:
        """Where upgrade k's card goes: two columns of four at the garage, one column of five at the lab."""
        p = self.panel_rect()
        top = p.y + 104
        if self.panel == "SHOP":
            return pygame.Rect(p.x + 20 + (k % 2) * 568, top + (k // 2) * 134, 552, 124)
        return pygame.Rect(p.x + 20, top + 26 + k * 104, 600, 96)

    def item_rect(self, k: int) -> pygame.Rect:
        p = self.panel_rect()
        return pygame.Rect(p.x + 636, p.y + 130 + k * 104, 504, 96)

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
        self.discarded = True
        delete_save()
        self.app.go(DeepDigScene(self.app, DeepDig()))

    def to_menu(self):
        self.save()
        from .menus import MenuScene
        self.app.go(MenuScene(self.app))

    # ================================================================== input

    def handle(self, event):
        if event.type == getattr(pygame, "WINDOWFOCUSLOST", -1):
            self.keys.clear()          # the key-up events go to another window: don't keep flying
            if not self.overlay and not self.panel:
                self._set_overlay("pause")
            return
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
        self.cam[0] = max(-TOWN_W * TILE, min(W * TILE - VIEW.w, self.cam[0]))
        self.cam[1] = max(-9 * TILE, self.cam[1])          # no bottom: the ground goes on forever
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
            elif k == "bot_ore":
                _, i, t, col, row = ev
                self.burst((col + 0.5) * TILE, (row + 0.5) * TILE, art.BOT_COLORS[i % 3], 6, 120, 3)
            elif k == "bot_sell":
                _, i, total, chips, n = ev
                bot = g.bots[i] if i < len(g.bots) else None
                if bot:
                    bx, by = bot.pos
                    self.floater(f"+{money(total)}", bx * TILE, by * TILE - 20, art.BOT_COLORS[i % 3])
                if chips:
                    self.app.settings.chip_bank += chips
                    self.app.settings.save()
                    self.say(f"Bot {i + 1} sold {n} ore for {money(total)}: +{chips} chip{'s' if chips != 1 else ''}!")
                sfx.play("coin")
            elif k == "exchange":
                _, chips, cost = ev
                self.app.settings.chip_bank += chips
                self.app.settings.save()
                self.say(f"Exchanged {money(cost)} for {chips:,} chip{'s' if chips != 1 else ''}! "
                         f"Chip Bank: {self.app.settings.chip_bank:,}.", 3.5)
                sfx.play("coin")
            elif k == "oil_bought":
                sfx.play("game_win")
                self.say("You're in the oil business! Press GO TO THE OIL FIELD to start drilling.", 4.0)
            elif k == "oil_sell":
                _, total, chips, side = ev
                if chips:
                    self.app.settings.chip_bank += chips
                    self.app.settings.save()
                    self.say(f"Your oil trucks sold {money(total)} of oil: +{chips} chip{'s' if chips != 1 else ''}!")
            elif k == "town":
                self.say("No digging in town: it's built on solid foundations. Roll right to the mine!", 2.4)
                sfx.play("deselect")
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
        self._draw_bots(surf)
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
        if g.on_surface and g.x < 0:
            return "This is the town. Roll right to the mine (rolling on the surface is free)."
        if g.on_surface:
            return "Drill down to dig. Fly back up and roll left to town to sell your ore."
        if len(g.cargo) >= g.cargo_space:
            return "Cargo bay full! Fly up and sell it."
        if g.fuel < g.max_fuel * 0.2:
            return "Fuel is low! Head back up to the fuel station (or use a fuel can: key 2)."
        if g.hull < g.max_hull * 0.25:
            return "Hull damaged! Repair on the surface (or use a repair kit: key 1)."
        if getattr(self.app, "pad", None) and self.app.pad.active:
            return "Stick: fly and drill.  A: use a building.  LB RB X LT Y: items 1-5.  Start: menu."
        return "Down/Left/Right drill, Up flies. 1-5 use items, Esc for the menu."

    def _draw_world(self, surf):
        g = self.game
        cam_x, cam_y = self.cam
        # Sky and the town, when they're in view.
        if cam_y < 0:
            h = int(-cam_y) + 4
            sky = art.sky(VIEW.w, max(h, VIEW.h))            # one picture, showing its bottom h pixels
            surf.blit(sky, (VIEW.x, VIEW.y), (0, sky.get_height() - h, VIEW.w, h))
            lit = int(self.clock * 2) % 2 == 0
            for name, (a, b) in BUILDINGS.items():
                width = (b - a + 1) * TILE
                img = art.building(name, width, lit)
                x, y = self.to_screen(a * TILE, 0)
                surf.blit(img, (x, y - img.get_height()))
            sign = art.mine_sign(lit)
            x, y = self.to_screen(-1.85 * TILE, 0)
            surf.blit(sign, (x - sign.get_width() // 2, y - sign.get_height()))
        c0 = max(-TOWN_W, int(cam_x // TILE))
        c1 = min(W - 1, int((cam_x + VIEW.w) // TILE) + 1)
        r0 = max(0, int(cam_y // TILE))
        r1 = int((cam_y + VIEW.h) // TILE) + 1
        g.tile(0, r1)                                       # make sure the ground in view exists
        for row in range(r0, r1 + 1):
            line = g.grid[row]
            for col in range(c0, c1 + 1):
                t = line[col] if col >= 0 else g.tile(col, row)
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
            drilling = d.way
        img = art.pod(g.facing, drilling, self.spin, g.thrusting, self.clock, self.hurt_flash,
                      drill_level=g.levels["DRILL"], top_drill=bool(g.stat("TOP DRILL")))
        x, y = self.to_screen(g.x * TILE, g.y * TILE)
        jitter = (random.uniform(-1.5, 1.5) if d else 0)
        surf.blit(img, img.get_rect(center=(x + jitter, y - 2)))

    def _draw_bots(self, surf):
        g = self.game
        for i, bot in enumerate(g.bots):
            bx, by = bot.pos
            x, y = self.to_screen(bx * TILE, by * TILE)
            if not VIEW.inflate(60, 60).collidepoint(x, y):
                continue
            dx, dy = bot.to_col - bot.col, bot.to_row - bot.row
            digging = bot.moving and bot.to_row >= 0 and dd.solid(g.tile(bot.to_col, bot.to_row))
            img = art.bot_sprite(art.BOT_COLORS[i % 3], dx, dy, self.clock if digging else 0.0, self.clock,
                                 30, len(bot.carry), glow=g.y > 2)
            jitter = random.uniform(-1, 1) if digging else 0
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
        radius = int(g.stat("LAMP") * TILE)
        hole = art.light_hole(radius)
        x, y = self.to_screen(g.x * TILE, g.y * TILE)
        dark.blit(hole, (x - radius - VIEW.x, y - radius - VIEW.y), special_flags=pygame.BLEND_RGBA_MIN)
        surf.blit(dark, VIEW.topleft)
        self._draw_scanner(surf, alpha / 255)
        if g.heat() > 0:   # a red haze when it's hot
            haze = pygame.Surface(VIEW.size, pygame.SRCALPHA)
            haze.fill((255, 60, 0, int(60 * min(1.0, g.heat()))))
            surf.blit(haze, VIEW.topleft)
        if self.hurt_flash > 0:
            red = pygame.Surface(VIEW.size, pygame.SRCALPHA)
            red.fill((255, 0, 0, int(120 * self.hurt_flash)))
            surf.blit(red, VIEW.topleft)

    def _draw_scanner(self, surf, darkness: float):
        """The scanner marks ore hidden in the dark: a pulsing box in the ore's colour, fading in where it's dark."""
        g = self.game
        reach = g.stat("SCANNER")
        if not reach or darkness < 0.2:
            return
        lamp = g.stat("LAMP")
        pulse = 0.5 + 0.5 * math.sin(self.clock * 5)
        layer = pygame.Surface(VIEW.size, pygame.SRCALPHA)
        cx, cy = int(g.x), int(g.y)
        for row in range(max(0, cy - reach), cy + reach + 1):
            for col in range(max(0, cx - reach), min(W - 1, cx + reach) + 1):
                t = g.tile(col, row)
                dist2 = (col + 0.5 - g.x) ** 2 + (row + 0.5 - g.y) ** 2
                if not dd.is_ore(t) or dist2 > reach * reach:
                    continue
                dark_here = darkness * min(1.0, (math.sqrt(dist2) / lamp) ** 1.6)   # as dark as the lamp leaves it
                if dark_here < 0.25:
                    continue
                color = (255, 120, 220) if t == dd.CORE else dd.ore_of(t).color
                a = int(255 * min(1.0, dark_here * 1.4))
                x, y = self.to_screen(col * TILE, row * TILE)
                r = pygame.Rect(x - VIEW.x + 6, y - VIEW.y + 6, TILE - 12, TILE - 12).inflate(int(pulse * 6),
                                                                                              int(pulse * 6))
                pygame.draw.rect(layer, (*color, a), r, 2, border_radius=6)
                pygame.draw.circle(layer, (*color, a), r.center, 4)
        surf.blit(layer, VIEW.topleft)

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
            surf.blit(art.icon(name, 30), (box.centerx - 15, box.centery - 16))
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
        self._draw_header(surf, p, color, label)
        if self.panel == "FUEL":
            self._big_bar(surf, p, "FUEL", g.fuel, g.max_fuel, (240, 170, 40))
            theme.ptext(surf, f"${dd.FUEL_PRICE} per litre", (p.centerx, p.y + 300), 18, theme.TEXT_DIM, anchor="center")
        elif self.panel == "REPAIR":
            self._big_bar(surf, p, "HULL", g.hull, g.max_hull, (90, 200, 110))
            theme.ptext(surf, f"${dd.REPAIR_PRICE} per point", (p.centerx, p.y + 300), 18, theme.TEXT_DIM,
                        anchor="center")
        elif self.panel == "SELL":
            self._draw_sell(surf, p)
        elif self.panel == "OIL":
            self._draw_oil_panel(surf, p)
        elif self.panel == "BANK":
            self._draw_bank_panel(surf, p)
        elif self.panel in ("SHOP", "LAB", "BOTS"):
            if self.panel == "BOTS":
                theme.ptext(surf, "UPGRADES", (p.x + 24, p.y + 104), 16, theme.TEXT_DIM)
                self._draw_roster(surf, p)
            if self.panel == "LAB":
                theme.ptext(surf, "GADGETS", (p.x + 24, p.y + 104), 16, theme.TEXT_DIM)
                theme.ptext(surf, "ITEMS  (keys 1-5 use them)", (p.x + 640, p.y + 104), 16, theme.TEXT_DIM)
            for k, name in enumerate(self.panel_upgrades()):
                self._draw_upgrade_card(surf, self.card_rect(k), name, color)
            if self.panel == "LAB":
                for k, name in enumerate(ITEM_KEYS):
                    r = self.item_rect(k)
                    theme.rounded(surf, theme.INNER, r, 12)
                    theme.rounded(surf, theme.PANEL, pygame.Rect(r.x + 10, r.y + 10, 76, 76), 10)
                    surf.blit(art.icon(name, 64), (r.x + 16, r.y + 16))
                    theme.ptext(surf, f"{name}  ({k + 1})", (r.x + 100, r.y + 12), 17)
                    theme.text(surf, ITEMS[name][1], (r.x + 100, r.y + 40), 12, theme.TEXT_DIM, bold=False)
                    theme.ptext(surf, f"YOU HAVE {g.items[name]}", (r.x + 100, r.y + 66), 12,
                                theme.TEXT if g.items[name] else theme.TEXT_FAINT)
        for b in self.panel_buttons:
            b.draw(surf)

    def _draw_roster(self, surf, p):
        """Robotics: a row for each bot slot (what it's up to and what it carries)."""
        g = self.game
        theme.ptext(surf, f"YOUR BOTS  (up to {dd.MAX_BOTS})", (p.x + 640, p.y + 104), 16, theme.TEXT_DIM)
        lvl = g.levels["BOT LEVEL"]
        for k in range(dd.MAX_BOTS):
            r = self.item_rect(k)
            theme.rounded(surf, theme.INNER, r, 12)
            pad = pygame.Rect(r.x + 10, r.y + 10, 76, 76)
            theme.rounded(surf, theme.PANEL, pad, 10)
            if k < len(g.bots):
                bot = g.bots[k]
                surf.blit(art.bot_sprite(art.BOT_COLORS[k], 1, 0, self.clock, self.clock, 64, len(bot.carry)),
                          (pad.x + 6, pad.y + 6))
                theme.ptext(surf, f"BOT {k + 1}", (r.x + 100, r.y + 12), 18, art.BOT_COLORS[k])
                where = "at the surface" if bot.row < 0 else f"{int(bot.row * FEET_PER_ROW):,} ft down"
                doing = "bringing ore up" if bot.state == "home" else "digging for ore"
                theme.text(surf, f"{doing.capitalize()}, {where}", (r.x + 100, r.y + 42), 13, theme.TEXT_DIM,
                           bold=False)
                theme.ptext(surf, f"CARRYING {len(bot.carry)}/{dd.BOT_CARRY[lvl]}", (r.x + 100, r.y + 66), 12,
                            theme.TEXT)
            else:
                theme.ptext(surf, "?", pad.center, 30, theme.TEXT_FAINT, anchor="center")
                theme.ptext(surf, "EMPTY SLOT", (r.x + 100, r.y + 14), 18, theme.TEXT_FAINT)
                theme.text(surf, "Buy DIG BOTS to put a robot to work.", (r.x + 100, r.y + 44), 13, theme.TEXT_FAINT,
                           bold=False)
        y = self.item_rect(dd.MAX_BOTS).y + 16
        theme.ptext(surf, f"YOUR BOTS HAVE EARNED {money(g.bot_earned)}", (p.x + 640, y), 18, theme.SUCCESS)
        theme.text(surf, f"They dig to {int(dd.BOT_DEPTH[lvl] * FEET_PER_ROW):,} ft, steer around rock, gas and lava,",
                   (p.x + 640, y + 34), 13, theme.TEXT_DIM, bold=False)
        theme.text(surf, "and sell what they find when they get back up.", (p.x + 640, y + 54), 13,
                   theme.TEXT_DIM, bold=False)

    def _draw_header(self, surf, p, color, label):
        """The shop's banner: its colour with a stripe pattern, its little building, name and tagline."""
        band = pygame.Rect(p.x + 8, p.y + 8, p.w - 16, 84)
        theme.rounded(surf, color, band, 12)
        stripes = pygame.Surface(band.size, pygame.SRCALPHA)
        for x in range(-band.h, band.w, 28):
            pygame.draw.polygon(stripes, (255, 255, 255, 26), [(x, band.h), (x + 14, band.h), (x + 14 + band.h, 0),
                                                               (x + band.h, 0)])
        surf.blit(stripes, band)
        a, b = BUILDINGS[self.panel]
        pic = art.building(self.panel, (b - a + 1) * TILE, int(self.clock * 2) % 2 == 0)
        k = 76 / pic.get_height()
        thumb = pygame.transform.smoothscale(pic, (int(pic.get_width() * k), 76))
        surf.blit(thumb, (band.x + 10, band.bottom - 78))
        x = band.x + thumb.get_width() + 26
        theme.logo(surf, label, (x + theme.pixel_surface(label, 34).get_width() // 2 + 8, band.y + 30), 34, angle=0)
        theme.ptext(surf, art.BUILDING_TAGLINE[self.panel], (x, band.y + 56), 15, (255, 255, 255))
        theme.ptext(surf, f"CASH {money(self.game.cash)}", (band.right - 74, band.y + 32), 20, (255, 255, 255),
                    anchor="topright")

    def _draw_upgrade_card(self, surf, r, name, color):
        g = self.game
        lvl = g.levels[name]
        top = len(UPGRADES[name][0]) - 1
        theme.rounded(surf, theme.INNER, r, 12)
        pad = pygame.Rect(r.x + 10, r.centery - 38, 76, 76)
        theme.rounded(surf, color if lvl else theme.PANEL, pad, 10)
        surf.blit(art.icon(name, 64), (pad.x + 6, pad.y + 6))
        x = pad.right + 14
        tall = r.h > 110
        theme.ptext(surf, name, (x, r.y + (14 if tall else 8)), 18)
        theme.text(surf, UPGRADE_INFO[name], (x, r.y + (42 if tall else 32)), 12, theme.TEXT_DIM, bold=False)
        y = r.y + (66 if tall else 54)
        for n in range(1, top + 1):
            pip = pygame.Rect(x + (n - 1) * 20, y, 15, 15)
            pygame.draw.rect(surf, theme.ACCENT if n <= lvl else theme.PANEL, pip, border_radius=4)
            pygame.draw.rect(surf, theme.OUTLINE, pip, 2, border_radius=4)
        now = upgrade_text(name, lvl)
        nxt = upgrade_text(name, lvl + 1) if lvl < top else None
        theme.ptext(surf, f"{now}  >  {nxt}" if nxt else f"{now}  (BEST)", (x, y + 22), 12,
                    theme.TEXT if nxt else theme.TEXT_DIM)

    def _draw_bank_panel(self, surf, p):
        g = self.game
        theme.ptext(surf, f"{money(dd.BANK_RATE)} = 1 CHIP", (p.centerx, p.y + 116), 30, theme.ACCENT, anchor="midtop")
        theme.ptext(surf, "YOUR CHIP BANK", (p.x + 40, p.y + 176), 16, theme.TEXT_DIM)
        theme.ptext(surf, f"{self.app.settings.chip_bank:,} CHIPS", (p.right - 40, p.y + 172), 22, theme.SUCCESS,
                    anchor="topright")
        theme.ptext(surf, "YOUR CASH BUYS", (p.x + 40, p.y + 214), 16, theme.TEXT_DIM)
        theme.ptext(surf, f"{g.can_exchange():,} CHIPS", (p.right - 40, p.y + 210), 22, theme.TEXT, anchor="topright")
        theme.ptext(surf, "Spend chips on card packs and more in the Card Shop.", (p.centerx, p.y + 258), 13,
                    theme.TEXT_DIM, anchor="midtop")

    def _draw_oil_panel(self, surf, p):
        g = self.game
        x, y = p.x + 40, p.y + 116
        if g.oil is None:
            lines = ["Buy into oil: your own field of land next to town.",
                     "Scan for oil, build rigs and lay pipes down to it,",
                     "then truck the oil to whichever buyer pays more.",
                     "It never stops: buy more land whenever you like,",
                     "and it keeps pumping while you dig."]
            for line in lines:
                theme.text(surf, line, (x, y), 17, theme.TEXT, bold=False)
                y += 32
            return
        oil = g.oil
        stored = sum(r.tank for r in oil.rigs) + sum(t.load for t in oil.trucks)
        rows = [("LAND", f"{oil.plots} plots"), ("RIGS", str(len(oil.rigs))), ("TRUCKS", str(len(oil.trucks))),
                ("OIL WAITING", f"{int(stored):,} barrels"),
                ("PRICES", f"ACME ${oil.prices['L']:.2f}   PETRO ${oil.prices['R']:.2f}"),
                ("EARNED", money(oil.earned))]
        for label, value in rows:
            theme.ptext(surf, label, (x, y), 16, theme.TEXT_DIM)
            theme.ptext(surf, value, (p.right - 40, y), 18, theme.SUCCESS if label == "EARNED" else theme.TEXT,
                        anchor="topright")
            y += 38

    def _draw_sell(self, surf, p):
        g = self.game
        counts: dict[int, int] = {}
        for t in g.cargo:
            counts[t] = counts.get(t, 0) + 1
        y = p.y + 112
        if not counts:
            theme.ptext(surf, "Your hold is empty. Go dig!", (p.centerx, p.y + 230), 20, theme.TEXT_DIM, anchor="center")
        kinds = sorted(counts.items(), key=lambda kv: -tile_value(kv[0]))
        shown = kinds if len(kinds) <= 5 else kinds[:4]
        for t, n in shown:
            img = art.tile_surface(t, 100, 3)
            surf.blit(img, (p.x + 40, y))
            theme.ptext(surf, f"{tile_name(t)} x{n}", (p.x + 96, y + 8), 20)
            theme.ptext(surf, money(tile_value(t) * n), (p.right - 40, y + 8), 20, theme.SUCCESS, anchor="topright")
            y += 46
        if len(shown) < len(kinds):              # the rest on one line
            rest = kinds[len(shown):]
            theme.ptext(surf, f"+ {sum(n for _, n in rest)} MORE ({len(rest)} KINDS)", (p.x + 96, y + 8), 18,
                        theme.TEXT_DIM)
            theme.ptext(surf, money(sum(tile_value(t) * n for t, n in rest)), (p.right - 40, y + 8), 18,
                        theme.SUCCESS, anchor="topright")
        bonus = g.stat("REFINERY")
        if bonus > 1 and counts:
            theme.ptext(surf, f"REFINERY BONUS +{round((bonus - 1) * 100)}%", (p.centerx, p.bottom - 100), 16,
                        theme.ACCENT, anchor="center")
        theme.ptext(surf, f"Every {money(dd.CHIP_EVERY)} sold = 1 chip for your Chip Bank", (p.centerx, p.bottom - 18),
                    14, theme.TEXT_DIM, anchor="center")

    def _big_bar(self, surf, p, label, value, maximum, color):
        bar = pygame.Rect(p.x + 60, p.y + 200, p.w - 120, 40)
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
            theme.ptext(surf, "The ground goes on forever below, richer and hotter. How deep can you go?", (cx, 470),
                        16, theme.TEXT_DIM, anchor="center")
            theme.ptext(surf, f"Total earned so far: {money(g.earned)}", (cx, 420), 18, theme.TEXT_DIM, anchor="center")
        for b in self.overlay_buttons:
            b.draw(surf)
