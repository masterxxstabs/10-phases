"""Opening a card pack: swipe to rip the wrapper, then flip the cards one at a time.

The skins are already in your collection by the time this screen opens (the
shop adds them when you pay), so quitting half way never loses anything.
"""

from __future__ import annotations

import math
import random

import pygame

from .. import shop
from ..cards import COLORS, number
from ..skins import COMMON, EPIC, LEGENDARY, RARE, RARITY_COLORS
from . import pack_art, sfx, theme
from .card_art import render_card
from .menus import PRIMARY, Scene, backdrop
from .pack_art import PACK_H, PACK_W, TEAR_Y
from .widgets import Button

CW, CH = 186, 279                     # revealed card size
CENTER = (theme.WIDTH // 2, 372)
SLOT_X = (theme.WIDTH // 2 - 290, theme.WIDTH // 2, theme.WIDTH // 2 + 290)
RANK = {COMMON: 0, RARE: 1, EPIC: 2, LEGENDARY: 3}
CHARGE = {COMMON: 0.0, RARE: 0.0, EPIC: 0.55, LEGENDARY: 1.35}
FLIP_TIME = 0.32


def ease_out_back(t: float) -> float:
    t = max(0.0, min(1.0, t))
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_in(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * t


def sample_card(skin):
    """The card used to show off a front skin: always the same one for the same skin."""
    k = sum(map(ord, skin.style))
    return number(COLORS[k % 4], (7, 10, 3, 12, 9, 5, 1, 8)[k % 8])


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "color", "size", "kind", "spin", "angle", "grav")

    def __init__(self, x, y, vx, vy, life, color, size, kind="spark", grav=600.0, spin=0.0):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max_life = life
        self.color, self.size, self.kind = color, size, kind
        self.grav, self.spin, self.angle = grav, spin, random.uniform(0, 360)


class CardSlot:
    def __init__(self, pull, index: int):
        self.pull = pull
        self.skin = pull.skin
        self.rarity = pull.skin.rarity
        self.index = index
        self.x, self.y, self.scale, self.angle = float(CENTER[0]), 900.0, 0.8, 0.0
        self.tx, self.ty, self.ts, self.ta = self.x, self.y, 1.0, 0.0
        self.revealed = False
        self.charging = -1.0   # time spent winding up before the flip (-1 = not started)
        self.flip = -1.0       # flip progress in seconds (-1 = not flipping)
        self.shine = random.uniform(0, 1.5)
        self.pop = 0.0         # little bounce when revealed
        self.focus = False     # legendary: held big in the middle of the screen
        self.equip_btn: Button | None = None

    @property
    def busy(self) -> bool:
        return self.charging >= 0 or self.flip >= 0

    def front(self) -> pygame.Surface:
        if self.skin.kind == "face":
            return render_card(sample_card(self.skin), CW, CH, face=self.skin.style)
        return render_card(None, CW, CH, back=self.skin.style)

    def rect(self) -> pygame.Rect:
        r = pygame.Rect(0, 0, int(CW * self.scale), int(CH * self.scale))
        r.center = (int(self.x), int(self.y))
        return r


class PackOpenScene(Scene):
    def __init__(self, app, pack_id: str, pulls: list[shop.Pull], back=None):
        super().__init__(app)
        self.pack = shop.PACK_BY_ID[pack_id]
        self.pulls = pulls
        self._back = back
        order = sorted(range(len(pulls)), key=lambda k: RANK[pulls[k].skin.rarity])   # best card last
        self.slots = [CardSlot(pulls[k], n) for n, k in enumerate(order)]
        self.best = max((s.rarity for s in self.slots), key=RANK.get)
        self.strip, self.body = pack_art.split_pack(self.pack)
        self.canvas = pygame.Surface((theme.WIDTH, theme.HEIGHT))
        self.state = "drop"
        self.t = 0.0                 # time in the current state
        self.progress = 0.0          # how far the wrapper is torn, 0..1
        self.next_rip = 0.08
        self.rip_n = 0
        self.dragging = False
        self.drag_x = 0
        self.drag_moved = 0.0
        self.auto_tear = False
        self.tear_speed = 0.0
        self.strip_fly: list[float] | None = None   # x, y, vx, vy, angle, spin
        self.pack_y = -PACK_H
        self.particles: list[Particle] = []
        self.flash = 0.0
        self.shake = 0.0
        self.dim = 0.0
        self.dim_target = 0.0
        self.ray_color = RARITY_COLORS[self.best]
        self.ray_strength = 0.0
        self.ray_target = 0.0
        self.ray_angle = 0.0
        self.ray_center = CENTER
        self.ray_rainbow = False
        self.banner: tuple[str, tuple, float] | None = None   # text, colour, age
        self.sheen_t = 0.0
        self.hint_t = 0.0
        bx = theme.WIDTH // 2
        self.btn_again = Button((bx - 330, 712, 320, 56), "", self._again, size=20, **PRIMARY)
        self.btn_back = Button((bx + 10, 712, 320, 56), "BACK TO SHOP", self._done, size=20)
        self.btn_skip = Button((theme.WIDTH - 210, 24, 186, 46), "SKIP", self._skip, size=18)
        self.btn_reveal_all = Button((theme.WIDTH - 236, 712, 212, 56), "REVEAL ALL", self._reveal_all, size=18)
        self.reveal_all = False
        self.queued: CardSlot | None = None
        sfx.play("whoosh")

    # ------------------------------------------------------------------ geometry

    def pack_rect(self) -> pygame.Rect:
        bob = math.sin(self.clock * 2.1) * 8 if self.state == "ready" else 0
        return pygame.Rect(CENTER[0] - PACK_W // 2, int(self.pack_y + bob), PACK_W, PACK_H)

    def tear_zone(self) -> pygame.Rect:
        r = self.pack_rect()
        return pygame.Rect(r.x - 60, r.y + TEAR_Y - 70, r.w + 120, 140)

    # ------------------------------------------------------------------ input

    def handle(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.state == "done":
                self._done()
            else:
                self._skip()
            return
        if self.btn_skip.handle(event):
            return
        if self.state in ("drop", "ready", "tearing"):
            self._handle_tear(event)
        elif self.state == "reveal":
            if self.btn_reveal_all.handle(event):
                return
            self._handle_reveal(event)
        elif self.state == "done":
            if self.btn_again.handle(event) or self.btn_back.handle(event):
                return
            for s in self.slots:
                if s.equip_btn and s.equip_btn.handle(event):
                    return
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self._again() if self._can_again() else self._done()

    def _handle_tear(self, event):
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_RETURN):
            self.auto_tear = True
            if self.state == "ready":
                self.state = "tearing"
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.tear_zone().collidepoint(event.pos) or self.pack_rect().collidepoint(event.pos):
                self.dragging, self.drag_x, self.drag_moved = True, event.pos[0], 0.0
                if self.state == "ready":
                    self.state = "tearing"
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            dx = abs(event.pos[0] - self.drag_x)
            self.drag_x = event.pos[0]
            self.drag_moved += dx
            if self.state == "tearing":
                self._tear(dx / PACK_W * 1.25)
                self.tear_speed = min(1.0, dx / 30)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.dragging:
            self.dragging = False
            if self.drag_moved < 10 and self.state == "tearing":
                self.auto_tear = True   # a plain tap rips it open for you

    def _handle_reveal(self, event):
        focused = next((s for s in self.slots if s.focus), None)
        if focused:
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1 or \
                    event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_RETURN):
                self._unfocus(focused)
            return
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            for s in self.slots:
                if not s.revealed and not s.busy and s.rect().collidepoint(event.pos):
                    if any(o.busy for o in self.slots):
                        self.queued = s   # flip it as soon as the current card is done
                    else:
                        self._start_reveal(s)
                    return
        if any(s.busy for s in self.slots):
            return
        elif event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_RETURN):
            nxt = next((s for s in self.slots if not s.revealed), None)
            if nxt:
                self._start_reveal(nxt)

    # ------------------------------------------------------------------ tearing

    def _tear(self, amount: float):
        if amount <= 0 or self.state != "tearing":
            return
        self.progress = min(1.0, self.progress + amount)
        r = self.pack_rect()
        tx = r.x + self.progress * PACK_W
        ty = r.y + TEAR_Y
        light = self.pack.colors[0]
        for _ in range(1 + int(amount * 40)):
            self.particles.append(Particle(tx + random.uniform(-6, 6), ty + random.uniform(-4, 4),
                                           random.uniform(-80, 160), random.uniform(-260, -60), random.uniform(0.4, 0.8),
                                           random.choice([(255, 255, 255), light, theme.lighten(light, 60)]),
                                           random.uniform(3, 6), "paper", grav=700, spin=random.uniform(-500, 500)))
        if random.random() < amount * 12:
            self.particles.append(Particle(tx, ty, random.uniform(-40, 40), random.uniform(-120, -20), 0.5,
                                           RARITY_COLORS[self.best], random.uniform(4, 8), "star", grav=-50))
        self.shake = max(self.shake, 3 + 5 * amount * 10)
        while self.progress >= self.next_rip:
            sfx.play(f"rip{self.rip_n % 4}")
            self.rip_n += 1
            self.next_rip += 0.14
        if self.progress >= 1.0:
            self._burst()

    def _burst(self):
        self.state, self.t = "burst", 0.0
        self.dragging = False
        r = self.pack_rect()
        self.strip_fly = [float(r.x), float(r.y), 260.0, -620.0, 0.0, -260.0]
        self.flash = 1.0
        self.shake = 18
        self.ray_center = (r.centerx, r.y + TEAR_Y)
        self.ray_strength = 1.0 + RANK[self.best] * 0.3
        self.ray_target = 0.6 + RANK[self.best] * 0.2
        sfx.play("burst")
        col = RARITY_COLORS[self.best]
        for _ in range(70):
            a = random.uniform(math.pi, 2 * math.pi)
            sp = random.uniform(200, 760)
            self.particles.append(Particle(r.centerx + random.uniform(-PACK_W / 2, PACK_W / 2), r.y + TEAR_Y,
                                           math.cos(a) * sp, math.sin(a) * sp, random.uniform(0.5, 1.2),
                                           random.choice([(255, 255, 255), col, theme.lighten(col, 50)]),
                                           random.uniform(3, 9), random.choice(["spark", "star"]), grav=500))
        for s in self.slots:
            s.x, s.y, s.scale = float(r.centerx), float(r.y + TEAR_Y + CH * 0.5 + 30), 1.0

    # ------------------------------------------------------------------ revealing

    def _start_reveal(self, s: CardSlot, quick: bool = False):
        self.banner = None
        if quick or CHARGE[s.rarity] == 0:
            s.flip = 0.0
            sfx.play("flip")
            return
        s.charging = 0.0
        sfx.play("charge" if s.rarity == LEGENDARY else "whoosh")
        if s.rarity == LEGENDARY:
            s.tx, s.ty, s.ts = CENTER[0], CENTER[1] - 10, 1.3
            self.dim_target = 0.75
            self.ray_center = (CENTER[0], CENTER[1] - 10)
            self.ray_color, self.ray_rainbow = RARITY_COLORS[LEGENDARY], False
            self.ray_target = 0.6
        else:
            s.ts = 1.12
            self.dim_target = 0.35

    def _on_revealed(self, s: CardSlot, quick: bool = False):
        s.revealed = True
        s.pop = 1.0
        col = RARITY_COLORS[s.rarity]
        if quick:
            return
        cx, cy = s.x, s.y
        n = {COMMON: 14, RARE: 40, EPIC: 70, LEGENDARY: 160}[s.rarity]
        for _ in range(n):
            a = random.uniform(0, 2 * math.pi)
            sp = random.uniform(120, 520) * (1.5 if s.rarity == LEGENDARY else 1)
            kind = "confetti" if s.rarity == LEGENDARY and random.random() < 0.6 else random.choice(["spark", "star"])
            color = (random.choice([(255, 80, 80), (80, 200, 255), (255, 220, 60), (120, 230, 120), (220, 120, 255)])
                     if kind == "confetti" else random.choice([(255, 255, 255), col, theme.lighten(col, 60)]))
            self.particles.append(Particle(cx, cy, math.cos(a) * sp, math.sin(a) * sp - 120,
                                           random.uniform(0.6, 1.6 if kind == "confetti" else 1.0), color,
                                           random.uniform(4, 10), kind, grav=380 if kind == "confetti" else 300,
                                           spin=random.uniform(-720, 720)))
        if s.rarity == COMMON:
            sfx.play("reveal_common")
            return
        if s.rarity == RARE:
            sfx.play("reveal_rare")
            sfx.play("sparkle")
            self.banner = ("RARE!", col, 0.0)
            self.dim_target = 0.0
            return
        self.flash = 0.8 if s.rarity == EPIC else 1.0
        self.shake = 10 if s.rarity == EPIC else 22
        self.ray_center, self.ray_color = (cx, cy), col
        self.ray_strength = 1.6 if s.rarity == EPIC else 2.2
        self.ray_target = 0.3 if s.rarity == EPIC else 1.0
        self.ray_rainbow = s.rarity == LEGENDARY
        self.banner = ("EPIC!" if s.rarity == EPIC else "LEGENDARY!", col, 0.0)
        sfx.play("reveal_epic" if s.rarity == EPIC else "reveal_legendary")
        sfx.play("sparkle")
        if s.rarity == EPIC:
            s.ts = 1.0
            self.dim_target = 0.0
        else:
            s.focus = True

    def _unfocus(self, s: CardSlot):
        s.focus = False
        s.tx, s.ty, s.ts = SLOT_X[s.index], CENTER[1], 1.0
        self.dim_target = 0.0
        self.ray_target = 0.0
        sfx.play("whoosh")

    def _reveal_all(self):
        self.reveal_all = True

    def _skip(self):
        """Jump straight to the results."""
        for s in self.slots:
            s.charging = s.flip = -1.0
            s.focus = False
            if not s.revealed:
                self._on_revealed(s, quick=True)
            s.x, s.y, s.scale = SLOT_X[s.index], CENTER[1], 1.0
            s.tx, s.ty, s.ts = s.x, s.y, 1.0
        self.dim_target = self.dim = 0.0
        self.ray_target = 0.0
        self.banner = None
        self._finish()

    def _finish(self):
        self.state, self.t = "done", 0.0
        self.banner = None
        for s in self.slots:
            r = pygame.Rect(0, 0, 150, 40)
            r.center = (SLOT_X[s.index], CENTER[1] + CH // 2 + 110)
            s.equip_btn = Button(r, "EQUIP", lambda s=s: self._equip(s), size=16, radius=8)

    def _equip(self, s: CardSlot):
        st = self.app.settings
        try:
            shop.equip(st, s.skin.id)
        except shop.ShopError:
            sfx.play("error")
            return
        st.save()
        theme.apply(st)
        sfx.play("select")

    def _can_again(self) -> bool:
        return self.app.settings.chip_bank >= self.pack.price

    def _again(self):
        if not self._can_again():
            sfx.play("error")
            return
        st = self.app.settings
        pulls = shop.buy_pack(st, self.pack.id)
        st.save()
        sfx.play("coin")
        self.app.go(PackOpenScene(self.app, self.pack.id, pulls, self._back))

    def _done(self):
        self.app.settings.save()
        if self._back:
            self._back()
        else:
            from .shop_scene import ShopScene
            self.app.go(ShopScene(self.app, tab="PACKS"))

    # ------------------------------------------------------------------ update

    def update(self, dt: float):
        super().update(dt)
        self.t += dt
        self.hint_t += dt
        self.sheen_t = (self.sheen_t + dt / 2.4) % 1.0
        self.flash = max(0.0, self.flash - dt * 2.6)
        self.shake = max(0.0, self.shake - dt * 40)
        self.dim += (self.dim_target - self.dim) * min(1.0, dt * 6)
        self.ray_strength += (self.ray_target - self.ray_strength) * min(1.0, dt * 3)
        self.ray_angle += dt * (0.5 + self.ray_strength * 0.4)
        if self.banner:
            text, col, age = self.banner
            self.banner = (text, col, age + dt) if age + dt < 2.2 else None
        self._update_particles(dt)

        if self.state == "drop":
            k = self.t / 0.75
            self.pack_y = -PACK_H + (CENTER[1] - PACK_H // 2 + PACK_H) * ease_out_back(k)
            if k >= 1:
                self.state, self.t = "ready", 0.0
                self.shake = 7
                sfx.play("pack_drop")
        elif self.state in ("ready", "tearing"):
            self.pack_y = CENTER[1] - PACK_H // 2
            if self.auto_tear and self.state == "tearing":
                self._tear(dt * 1.5)
            self.tear_speed = max(0.0, self.tear_speed - dt * 3)
        elif self.state == "burst":
            self._update_burst(dt)
        if self.state in ("burst", "reveal", "done"):
            self._update_cards(dt)
        if self.state == "reveal":
            idle = not any(s.busy or s.focus for s in self.slots)
            if self.queued and idle:
                if not self.queued.revealed:
                    self._start_reveal(self.queued)
                self.queued = None
            elif self.reveal_all and idle:
                nxt = next((s for s in self.slots if not s.revealed), None)
                if nxt:
                    self._start_reveal(nxt)
            if all(s.revealed and not s.busy and not s.focus for s in self.slots):
                self._finish()

    def _update_burst(self, dt: float):
        t = self.t
        if self.strip_fly:
            f = self.strip_fly
            f[3] += 1500 * dt
            f[0] += f[2] * dt
            f[1] += f[3] * dt
            f[4] += f[5] * dt
            if f[1] > theme.HEIGHT + 200:
                self.strip_fly = None
        base = CENTER[1] - PACK_H // 2
        # The cards rise out of the wrapper...
        rise = ease_out((t - 0.2) / 0.7)
        for s in self.slots:
            start = base + TEAR_Y + CH * 0.5 + 30
            s.y = start - rise * (start - 210 + s.index * 4) - (2 - s.index) * 6 * rise
            s.x = CENTER[0] + (s.index - 1) * 5 * rise
            s.angle = (s.index - 1) * 3 * rise
        # ...then the wrapper drops away...
        if t >= 0.95 and self.t - dt < 0.95:
            sfx.play("whoosh")
        self.pack_y = base + ease_in((t - 0.95) / 0.5) * (theme.HEIGHT + 100)
        if t >= 1.0:
            self.ray_target = 0.35 + RANK[self.best] * 0.15
        # ...and the cards deal out into a row.
        if t >= 1.45:
            self.state, self.t = "reveal", 0.0
            for s in self.slots:
                s.tx, s.ty, s.ts, s.ta = SLOT_X[s.index], CENTER[1], 1.0, 0.0
            sfx.play("shuffle")

    def _update_cards(self, dt: float):
        for s in self.slots:
            if self.state != "burst":
                k = min(1.0, dt * 9)
                s.x += (s.tx - s.x) * k
                s.y += (s.ty - s.y) * k
                s.scale += (s.ts - s.scale) * k
                s.angle += (s.ta - s.angle) * k
            s.pop = max(0.0, s.pop - dt * 3)
            s.shine = (s.shine + dt / 2.2) % 1.6
            if s.charging >= 0:
                s.charging += dt
                if s.rarity == LEGENDARY:
                    self.ray_target = 0.4 + s.charging
                    self.shake = max(self.shake, s.charging * 6)
                    if random.random() < dt * 30:
                        a = random.uniform(0, 2 * math.pi)
                        d = random.uniform(160, 260)
                        self.particles.append(Particle(s.x + math.cos(a) * d, s.y + math.sin(a) * d,
                                                       -math.cos(a) * d * 2.4, -math.sin(a) * d * 2.4, 0.4,
                                                       RARITY_COLORS[LEGENDARY], random.uniform(3, 6), "spark", grav=0))
                if s.charging >= CHARGE[s.rarity] * (0.4 if self.reveal_all else 1):
                    s.charging = -1.0
                    s.flip = 0.0
                    sfx.play("flip")
            elif s.flip >= 0:
                before = s.flip
                s.flip += dt
                if before < FLIP_TIME / 2 <= s.flip:
                    self._on_revealed(s)
                if s.flip >= FLIP_TIME:
                    s.flip = -1.0
                    if s.rarity == LEGENDARY and self.reveal_all and s.focus:
                        pass   # still wait for a tap so the big moment isn't missed
            # Unrevealed rare cards hint at what's coming.
            if not s.revealed and self.state == "reveal" and s.rarity != COMMON and random.random() < dt * (
                    4 * RANK[s.rarity]):
                r = s.rect()
                self.particles.append(Particle(random.uniform(r.left, r.right), r.bottom - 10, random.uniform(-15, 15),
                                               random.uniform(-90, -40), random.uniform(0.6, 1.1),
                                               RARITY_COLORS[s.rarity], random.uniform(3, 6), "star", grav=-20))

    def _update_particles(self, dt: float):
        alive = []
        for p in self.particles:
            p.life -= dt
            if p.life <= 0:
                continue
            p.vy += p.grav * dt
            drag = 0.9 if p.kind == "confetti" else 0.98
            p.vx *= drag ** (dt * 60)
            if p.kind == "confetti":
                p.vy = min(p.vy, 160)
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.angle += p.spin * dt
            alive.append(p)
        self.particles = alive[-900:]

    # ------------------------------------------------------------------ drawing

    def draw(self, surf):
        c = self.canvas
        backdrop(c, self.clock)
        shade = pygame.Surface((theme.WIDTH, theme.HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 0, 20, 120))
        c.blit(shade, (0, 0))
        c.blit(pack_art.glow(360, theme.darken(self.pack.colors[0], 40)), (CENTER[0] - 360, CENTER[1] - 360),
               special_flags=pygame.BLEND_RGB_ADD)
        pack_art.rays(c, self.ray_center, self.ray_color, self.ray_strength, self.ray_angle, rainbow=self.ray_rainbow)

        if self.state in ("drop", "ready", "tearing"):
            self._draw_pack(c)
        elif self.state == "burst":
            self._draw_cards(c)
            r = self.pack_rect()
            c.blit(self.body, r.topleft)
            if self.strip_fly:
                f = self.strip_fly
                img = pygame.transform.rotate(self.strip, f[4])
                c.blit(img, img.get_rect(center=(f[0] + PACK_W / 2, f[1] + TEAR_Y / 2)))
        else:
            self._draw_cards(c)
        self._draw_particles(c)
        if self.dim > 0.01:
            # Dim everything except the focused card, then draw it again on top.
            veil = pygame.Surface((theme.WIDTH, theme.HEIGHT), pygame.SRCALPHA)
            veil.fill((0, 0, 0, int(200 * self.dim)))
            c.blit(veil, (0, 0))
            pack_art.rays(c, self.ray_center, self.ray_color, self.ray_strength * self.dim, self.ray_angle,
                          rainbow=self.ray_rainbow)
            for s in self.slots:
                if s.focus or s.charging >= 0 or (s.flip >= 0 and s.rarity in (EPIC, LEGENDARY)):
                    self._draw_card(c, s)
            self._draw_particles(c)
        self._draw_banner(c)
        self._draw_hud(c)
        if self.flash > 0:
            fl = pygame.Surface((theme.WIDTH, theme.HEIGHT))
            fl.fill((255, 255, 255))
            fl.set_alpha(int(255 * min(1.0, self.flash)))
            c.blit(fl, (0, 0))
        ox = oy = 0
        if self.shake > 0.5:
            ox, oy = random.uniform(-1, 1) * self.shake, random.uniform(-1, 1) * self.shake
        surf.fill((0, 0, 0))
        surf.blit(c, (int(ox), int(oy)))

    def _draw_pack(self, c):
        r = self.pack_rect()
        jit = self.tear_speed * 3
        r = r.move(random.uniform(-jit, jit), random.uniform(-jit, jit)) if jit > 0.3 else r
        # A soft shadow under the floating pack.
        sh = pygame.Surface((PACK_W, 40), pygame.SRCALPHA)
        bob = math.sin(self.clock * 2.1) if self.state == "ready" else 0
        pygame.draw.ellipse(sh, (0, 0, 0, 80 - int(bob * 20)), sh.get_rect().inflate(-40 - bob * 30, -10))
        c.blit(sh, (r.x, CENTER[1] + PACK_H // 2 + 10))
        if self.progress <= 0:
            img = pack_art.pack_surface(self.pack)
            if self.state == "ready":
                img = pack_art.sheen(img, (self.clock / 2.2) % 1.0, alpha=110)
            angle = math.sin(self.clock * 1.3) * 2.5 if self.state == "ready" else 0
            if angle:
                img = pygame.transform.rotozoom(img, angle, 1)
            c.blit(img, img.get_rect(center=r.center))
            if self.state == "ready":
                self._draw_tear_hint(c, r)
            return
        tx = int(self.progress * PACK_W)
        c.blit(self.body, r.topleft)
        # Light leaking out of the rip.
        col = RARITY_COLORS[self.best]
        edge = pack_art.tear_edge()
        leak = pygame.Surface((PACK_W, TEAR_Y + 30))
        pts = [(x, y) for x, y in edge if x <= tx] + [(tx, TEAR_Y)]
        if len(pts) >= 2:
            pygame.draw.lines(leak, tuple(int(v * 0.9) for v in col), False, pts, 9)
            pygame.draw.lines(leak, (255, 255, 255), False, pts, 3)
            c.blit(leak, (r.x, r.y), special_flags=pygame.BLEND_RGB_ADD)
        g = pack_art.glow(int(60 + 60 * self.progress), col)
        c.blit(g, g.get_rect(center=(r.x + tx, r.y + TEAR_Y)), special_flags=pygame.BLEND_RGB_ADD)
        # The part of the strip still attached...
        if tx < PACK_W:
            c.blit(self.strip, (r.x + tx, r.y), area=pygame.Rect(tx, 0, PACK_W - tx, self.strip.get_height()))
        # ...and the torn part, peeling up around the tear point.
        if tx > 2:
            part = self.strip.subsurface((0, 0, tx, self.strip.get_height()))
            angle = 6 + 22 * self.progress
            pivot = pygame.math.Vector2(r.x + tx, r.y + TEAR_Y)
            offset = pygame.math.Vector2(tx / 2 - tx, self.strip.get_height() / 2 - TEAR_Y)
            rot = pygame.transform.rotate(part, angle)
            c.blit(rot, rot.get_rect(center=pivot + offset.rotate(-angle)))
        if not self.dragging and not self.auto_tear:
            theme.ptext(c, "KEEP GOING!", (CENTER[0], r.y - 30), 26, theme.ACCENT, anchor="center")

    def _draw_tear_hint(self, c, r):
        t = (self.hint_t % 1.6) / 1.2
        y = r.y + TEAR_Y
        if t <= 1:
            x = r.x - 20 + (PACK_W + 40) * ease_out(t)
            for k in range(8):
                xx = x - k * 14
                if xx > r.x - 20:
                    a = 1 - k / 8
                    pygame.draw.circle(c, tuple(int(v * a) for v in (255, 240, 160)), (int(xx), y), int(7 * a) + 1)
            g = pack_art.glow(46, (200, 180, 90))
            c.blit(g, g.get_rect(center=(int(x), y)), special_flags=pygame.BLEND_RGB_ADD)
            pygame.draw.circle(c, (255, 255, 255), (int(x), y), 11)
            pygame.draw.circle(c, theme.OUTLINE, (int(x), y), 11, 3)
        pulse = 0.5 + 0.5 * math.sin(self.clock * 5)
        theme.ptext(c, "SWIPE ACROSS THE TOP TO RIP IT OPEN!", (CENTER[0], r.y - 34), 26,
                    theme.lighten(theme.ACCENT, int(40 * pulse)), anchor="center")

    def _card_image(self, s: CardSlot) -> pygame.Surface:
        showing_front = s.revealed if s.flip < 0 else s.flip >= FLIP_TIME / 2
        if showing_front:
            img = s.front()
            if s.rarity != COMMON and s.shine < 1.0:
                img = pack_art.sheen(img, s.shine, alpha=90 + 30 * RANK[s.rarity])
        else:
            img = pack_art.mystery_back(self.pack, CW, CH)
        sx = abs(math.cos(math.pi * s.flip / FLIP_TIME)) if s.flip >= 0 else 1.0
        scale = s.scale * (1 + 0.12 * math.sin(s.pop * math.pi))
        w, h = max(2, int(CW * scale * sx)), max(2, int(CH * scale))
        if (w, h) != img.get_size():
            img = pygame.transform.smoothscale(img, (w, h))
        if s.angle:
            img = pygame.transform.rotozoom(img, s.angle, 1)
        return img

    def _draw_card(self, c, s: CardSlot):
        img = self._card_image(s)
        x, y = s.x, s.y
        if s.charging >= 0:
            amp = 2 + s.charging * (10 if s.rarity == LEGENDARY else 5)
            x += math.sin(self.clock * 70) * amp
            y += math.cos(self.clock * 53) * amp * 0.4
        elif not s.revealed and s.rarity == LEGENDARY and self.state == "reveal":
            x += math.sin(self.clock * 40) * 1.5
        hover = (self.state == "reveal" and not s.revealed and not s.busy
                 and s.rect().collidepoint(pygame.mouse.get_pos()))
        if hover:
            y -= 10
        rect = img.get_rect(center=(int(x), int(y)))
        # Glow behind cards that are (or are about to be) something special.
        if s.rarity != COMMON and self.state != "burst":
            pulse = 0.65 + 0.35 * math.sin(self.clock * (4 + 2 * RANK[s.rarity]))
            strength = pulse * (0.5 + 0.25 * RANK[s.rarity]) * (1.4 if s.revealed else 1.0)
            if s.charging >= 0:
                strength += s.charging
            col = tuple(int(min(255, v * strength)) for v in RARITY_COLORS[s.rarity])
            g = pack_art.card_glow(rect.w, rect.h, col)
            c.blit(g, g.get_rect(center=rect.center), special_flags=pygame.BLEND_RGB_ADD)
        shadow = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        pygame.draw.rect(shadow, (0, 0, 0, 90), shadow.get_rect(), border_radius=18)
        c.blit(shadow, rect.move(7, 9))
        c.blit(img, rect)
        if s.revealed and self.state in ("reveal", "done") and s.flip < 0:
            self._draw_label(c, s)

    def _draw_label(self, c, s: CardSlot):
        cx, top = int(s.x), int(s.y + CH * s.scale / 2 + 14)
        col = RARITY_COLORS[s.rarity]
        pill = pygame.Rect(0, 0, 130, 26)
        pill.center = (cx, top + 13)
        pygame.draw.rect(c, theme.darken(col, 90), pill.move(0, 3), border_radius=13)
        pygame.draw.rect(c, col, pill, border_radius=13)
        theme.ptext(c, s.rarity, pill.center, 16, (20, 20, 30), None, anchor="center")
        theme.ptext(c, s.skin.name, (cx, top + 44), 22, theme.TEXT, anchor="center")
        kind = "CARD FRONT" if s.skin.kind == "face" else "CARD BACK"
        theme.ptext(c, kind, (cx, top + 66), 14, theme.TEXT_DIM, anchor="center")
        r = s.rect()
        if s.pull.new:
            badge = pygame.transform.rotozoom(self._new_badge(), 14 + math.sin(self.clock * 4) * 4,
                                              1 + 0.05 * math.sin(self.clock * 6))
            c.blit(badge, badge.get_rect(center=(r.right - 6, r.top + 8)))
        else:
            theme.chip(c, (r.right - 70, r.top + 2), 11, theme.ACCENT)
            theme.ptext(c, f"+{s.pull.refund}", (r.right - 54, r.top + 2), 22, theme.ACCENT, anchor="midleft")
        if self.state == "done" and s.equip_btn:
            b = s.equip_btn
            on = shop.equipped(self.app.settings, s.skin)
            b.label, b.enabled = ("EQUIPPED", False) if on else ("EQUIP", True)
            b.draw(c)

    def _new_badge(self) -> pygame.Surface:
        surf = pygame.Surface((96, 96), pygame.SRCALPHA)
        pts = pack_art_star(48, 48, 46, 34, 12)
        pygame.draw.polygon(surf, theme.OUTLINE, [(x + 2, y + 3) for x, y in pts])
        pygame.draw.polygon(surf, (255, 70, 90), pts)
        pygame.draw.polygon(surf, (255, 255, 255), pts, 3)
        t = theme.pixel_surface("NEW!", 22, (255, 255, 255), theme.OUTLINE)
        surf.blit(t, t.get_rect(center=(48, 48)))
        return surf

    def _draw_cards(self, c):
        order = sorted(self.slots, key=lambda s: (s.focus or s.charging >= 0, s.index))
        for s in order:
            self._draw_card(c, s)

    def _draw_particles(self, c):
        for p in self.particles:
            a = max(0.0, min(1.0, p.life / p.max_life * 1.5))
            size = p.size * (0.3 + 0.7 * a)
            col = p.color
            if p.kind == "star":
                theme.star(c, (p.x, p.y), size * 1.4, col)
            elif p.kind == "spark":
                pygame.draw.circle(c, col, (int(p.x), int(p.y)), max(1, int(size / 2)))
            else:   # confetti and paper scraps: little spinning rectangles
                ang = math.radians(p.angle)
                w, h = size, size * 0.55 * abs(math.cos(ang * 1.7)) + 1
                ca, sa = math.cos(ang), math.sin(ang)
                pts = [(p.x + dx * ca - dy * sa, p.y + dx * sa + dy * ca)
                       for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))]
                pygame.draw.polygon(c, col, pts)

    def _draw_banner(self, c):
        if not self.banner:
            return
        text, col, age = self.banner
        size = {"RARE!": 46}.get(text, 72)
        k = ease_out_back(age / 0.35)
        fade = 1.0 if age < 1.7 else max(0.0, 1 - (age - 1.7) / 0.5)
        base = theme.logo_surface(text, size, 6, col)
        img = pygame.transform.rotozoom(base, math.sin(age * 3) * 2, max(0.05, k))
        img.set_alpha(int(255 * fade))
        y = 96 if text != "LEGENDARY!" else 92
        c.blit(img, img.get_rect(center=(CENTER[0], y)))

    def _draw_hud(self, c):
        st = self.app.settings
        theme.ptext(c, self.pack.name, (32, 26), 26, self.pack.colors[0])
        theme.chip(c, (44, 78), 11, theme.ACCENT)
        theme.ptext(c, f"{st.chip_bank:,}", (62, 78), 22, theme.ACCENT, anchor="midleft")
        if self.state != "done":
            self.btn_skip.draw(c)
        if self.state == "reveal":
            left = sum(not s.revealed for s in self.slots)
            focused = any(s.focus for s in self.slots)
            msg = "TAP TO CONTINUE" if focused else f"TAP A CARD TO FLIP IT  ({left} LEFT)" if left else ""
            if msg and not any(s.busy for s in self.slots):
                pulse = 0.5 + 0.5 * math.sin(self.clock * 4)
                theme.ptext(c, msg, (CENTER[0], 730 if not focused else 700), 22,
                            theme.lighten(theme.TEXT_DIM, int(40 * pulse)), anchor="center")
            if not focused and left > 1:
                self.btn_reveal_all.draw(c)
        if self.state == "done":
            new = sum(s.pull.new for s in self.slots)
            refund = sum(s.pull.refund for s in self.slots)
            parts = [f"{new} NEW SKIN{'S' if new != 1 else ''}"]
            if refund:
                parts.append(f"+{refund} CHIPS FROM DUPLICATES")
            theme.ptext(c, "  ·  ".join(parts), (CENTER[0], 96), 26, theme.ACCENT, anchor="center")
            owned, total = shop.collection(st)
            theme.ptext(c, f"COLLECTION {owned}/{total}", (CENTER[0], 128), 18, theme.TEXT_DIM, anchor="center")
            can = self._can_again()
            self.btn_again.label = f"OPEN ANOTHER  ({self.pack.price})"
            self.btn_again.color, self.btn_again.text_color = ("ACCENT", "OUTLINE") if can else ("PANEL_LIGHT",
                                                                                                "TEXT_DIM")
            self.btn_again.draw(c)
            self.btn_back.draw(c)


def pack_art_star(cx, cy, outer, inner, points):
    pts = []
    for k in range(points * 2):
        r = outer if k % 2 == 0 else inner
        a = -math.pi / 2 + k * math.pi / points
        pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    return pts
