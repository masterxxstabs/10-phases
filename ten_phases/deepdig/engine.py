"""Deep Dig rules: the underground world, the drill pod's physics, and the shops on the surface.

No drawing here. Distances are in tiles: x runs left to right, y runs downward, and the
ground starts at y = 0 (row 0 is the topsoil). The sky is y < 0.

Each frame the screen calls `step(dt, left, right, up, down)`. The engine moves the pod,
drills, burns fuel, and records what happened in `events` for the screen to animate.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

W = 36                 # tiles across
H = 420                # rows of ground (the core is at the bottom)
FEET_PER_ROW = 12.5    # for the depth readout

# --------------------------------------------------------------------------- tiles

AIR, DIRT, ROCK, GAS, LAVA, BEDROCK, CONCRETE = range(7)
ORE0 = 10   # ore kinds start here


@dataclass(frozen=True)
class Ore:
    name: str
    value: int
    top: int          # first row it can appear in
    peak: int         # row where it's most common
    rarity: float     # chance per tile at its peak
    color: tuple


ORES = (
    Ore("IRON", 30, 1, 40, 0.100, (176, 120, 96)),
    Ore("COPPER", 60, 10, 90, 0.070, (222, 128, 60)),
    Ore("SILVER", 120, 40, 140, 0.050, (210, 214, 226)),
    Ore("GOLD", 300, 80, 190, 0.028, (255, 206, 40)),
    Ore("PLATINUM", 800, 130, 240, 0.020, (170, 230, 240)),
    Ore("URANIUM", 2000, 180, 290, 0.016, (120, 240, 90)),
    Ore("EMERALD", 5000, 220, 330, 0.012, (40, 200, 110)),
    Ore("RUBY", 15000, 270, 370, 0.009, (235, 40, 70)),
    Ore("DIAMOND", 50000, 320, 405, 0.006, (190, 240, 255)),
    Ore("RELIC", 150000, 360, 412, 0.003, (200, 120, 255)),
)
CORE = ORE0 + len(ORES)          # the Heart of the Earth, waiting at the very bottom
CORE_VALUE = 1_000_000
SOLID = {DIRT, ROCK, GAS, LAVA, BEDROCK, CONCRETE}
UNDRILLABLE = {ROCK, BEDROCK, CONCRETE}


def is_ore(t: int) -> bool:
    return ORE0 <= t <= CORE


def ore_of(t: int) -> Ore | None:
    if ORE0 <= t < CORE:
        return ORES[t - ORE0]
    return None


def tile_value(t: int) -> int:
    if t == CORE:
        return CORE_VALUE
    o = ore_of(t)
    return o.value if o else 0


def tile_name(t: int) -> str:
    if t == CORE:
        return "HEART OF THE EARTH"
    o = ore_of(t)
    return o.name if o else ""


def solid(t: int) -> bool:
    return t in SOLID or is_ore(t)


# --------------------------------------------------------------------------- the surface

BUILDINGS = {   # name: (first column, last column)
    "FUEL": (2, 5),
    "SELL": (10, 14),
    "SHOP": (19, 24),
    "REPAIR": (29, 32),
}
START_X = 16.5

# --------------------------------------------------------------------------- upgrades and items

UPGRADES = {
    # name: (values per level, prices to reach each level)
    "DRILL": ((1.0, 1.45, 2.0, 2.8, 3.8, 5.2), (0, 750, 2500, 7500, 25000, 90000)),
    "HULL": ((100, 150, 220, 320, 460, 650), (0, 750, 2500, 7500, 25000, 90000)),
    "ENGINE": ((1.0, 1.2, 1.45, 1.75, 2.1, 2.5), (0, 750, 2500, 7500, 25000, 90000)),
    "FUEL TANK": ((15, 24, 36, 52, 76, 115), (0, 750, 2000, 6000, 20000, 70000)),
    "CARGO": ((8, 15, 25, 40, 65, 100), (0, 750, 2000, 6000, 20000, 70000)),
    "RADIATOR": ((0.0, 0.25, 0.45, 0.65, 0.8, 0.92), (0, 1000, 3500, 10000, 30000, 100000)),
}
UPGRADE_INFO = {
    "DRILL": "Drill faster through everything",
    "HULL": "More armour before you break",
    "ENGINE": "Fly faster and carry heavy loads",
    "FUEL TANK": "Stay down longer",
    "CARGO": "Carry more ore",
    "RADIATOR": "Stay cool in the hot depths",
}
ITEMS = {
    # name: (price, what it does)
    "REPAIR KIT": (1500, "Fix 35% of your hull anywhere"),
    "FUEL CAN": (1500, "Refill 40% of your tank anywhere"),
    "DYNAMITE": (2000, "Blast the tiles around you (even rock)"),
    "MEGA BLAST": (6000, "A huge blast that clears a big hole"),
    "TELEPORTER": (3000, "Beam straight back to the surface"),
}
ITEM_KEYS = ("REPAIR KIT", "FUEL CAN", "DYNAMITE", "MEGA BLAST", "TELEPORTER")
FUEL_PRICE = 2       # $ per litre
REPAIR_PRICE = 4     # $ per hull point
CHIP_EVERY = 500     # $ of ore sold per Chip Bank chip

# --------------------------------------------------------------------------- physics

HALF = 0.4           # the pod is a 0.8 x 0.8 box
GRAVITY = 15.0
THRUST = 24.0        # upward acceleration at engine level 0 (before gravity)
ACCEL = 20.0
MAX_RUN = 5.0
MAX_RISE = 6.0
MAX_FALL = 16.0
SAFE_LANDING = 8.0   # landing faster than this hurts
BURN = {"idle": 0.02, "move": 0.08, "thrust": 0.26, "drill": 0.24}
HEAT_START = 140     # rows below which it starts getting hot


class DigError(Exception):
    """Something you can't do right now; the message is shown to the player."""


@dataclass
class Drill:
    col: int
    row: int
    t: float
    dur: float
    start: tuple
    end: tuple


class DeepDig:
    def __init__(self, seed: int | None = None):
        self.seed = seed if seed is not None else random.randrange(1, 10 ** 9)
        self.grid = generate(self.seed)
        self.x, self.y = START_X, -HALF
        self.vx = self.vy = 0.0
        self.grounded = True
        self.facing = 1
        self.drill: Drill | None = None
        self.levels = {k: 0 for k in UPGRADES}
        self.fuel = self.max_fuel
        self.hull = self.max_hull
        self.cash = 0
        self.cargo: list[int] = []
        self.items = {k: 0 for k in ITEMS}
        self.deepest = 0
        self.earned = 0            # $ from ore, all time
        self.chip_progress = 0     # $ toward the next Chip Bank chip
        self.won = False
        self.events: list[tuple] = []
        self.thrusting = False
        self.clock = 0.0

    # ---------------------------------------------------------------- stats

    def stat(self, name: str):
        return UPGRADES[name][0][self.levels[name]]

    @property
    def max_fuel(self) -> float:
        return float(self.stat("FUEL TANK"))

    @property
    def max_hull(self) -> float:
        return float(self.stat("HULL"))

    @property
    def cargo_space(self) -> int:
        return int(self.stat("CARGO"))

    @property
    def cargo_value(self) -> int:
        return sum(tile_value(t) for t in self.cargo)

    @property
    def row(self) -> int:
        return int(math.floor(self.y))

    @property
    def depth_ft(self) -> int:
        return max(0, int(self.y * FEET_PER_ROW))

    @property
    def on_surface(self) -> bool:
        return self.y < 0

    def building(self) -> str | None:
        """The building the pod is parked at (on the surface), if any."""
        if not (self.on_surface and self.grounded and self.drill is None):
            return None
        for name, (a, b) in BUILDINGS.items():
            if a <= self.x <= b + 1:
                return name
        return None

    def heat(self) -> float:
        """0 (cool) to 1 (scorching), by depth."""
        return max(0.0, min(1.0, (self.y - HEAT_START) / (H - HEAT_START)))

    # ---------------------------------------------------------------- the grid

    def tile(self, col: int, row: int) -> int:
        if col < 0 or col >= W or row >= H:
            return BEDROCK
        if row < 0:
            return AIR
        return self.grid[row][col]

    def set_tile(self, col: int, row: int, t: int) -> None:
        if 0 <= col < W and 0 <= row < H:
            self.grid[row][col] = t

    def _hits(self, x: float, y: float) -> bool:
        """Does a pod at (x, y) overlap anything solid?"""
        for col in range(int(math.floor(x - HALF + 1e-6)), int(math.floor(x + HALF - 1e-6)) + 1):
            for row in range(int(math.floor(y - HALF + 1e-6)), int(math.floor(y + HALF - 1e-6)) + 1):
                if solid(self.tile(col, row)):
                    return True
        return False

    # ---------------------------------------------------------------- a frame

    def step(self, dt: float, left=False, right=False, up=False, down=False) -> None:
        dt = min(dt, 0.05)
        self.clock += dt
        self.thrusting = False
        if self.drill:
            self._step_drill(dt)
            return
        burn = BURN["idle"]
        eng = self.stat("ENGINE")
        load = 1.0 + 0.4 * len(self.cargo) / max(1, self.cargo_space)   # a full hold is heavier
        if self.fuel > 0 or (self.on_surface and self.grounded):   # you can always roll along the surface
            if left != right:
                self.facing = -1 if left else 1
                self.vx += (1 if right else -1) * ACCEL * eng * dt
                burn = max(burn, BURN["move"])
            if up and self.fuel > 0:
                self.vy -= THRUST * eng / load * dt
                self.thrusting = True
                burn = BURN["thrust"]
        if left == right or (self.fuel <= 0 and not self.on_surface):
            self.vx *= max(0.0, 1 - (10 if self.grounded else 1.5) * dt)
        self.vy += GRAVITY * dt
        top = MAX_RUN * eng
        self.vx = max(-top, min(top, self.vx))
        self.vy = max(-MAX_RISE * eng, min(MAX_FALL, self.vy))
        self._move(dt)
        self._burn(burn * dt)
        # Start drilling: down when standing on something, or sideways into a wall.
        if self.grounded and self.fuel > 0:
            if down:
                row = int(math.floor(self.y + HALF + 0.05))
                col = int(math.floor(self.x))
                if solid(self.tile(col, row)):
                    self._try_drill(col, row)
                else:                                     # hanging over a hole off a ledge's edge: slide into it
                    goal = col + 0.5
                    nx = self.x + max(-3 * dt, min(3 * dt, goal - self.x))
                    if not self._hits(nx, self.y):
                        self.x = nx
            elif (left or right) and left != right:
                d = -1 if left else 1
                edge = self.x + d * (HALF + 0.05)
                if self._hits(self.x + d * 0.06, self.y):
                    self._try_drill(int(math.floor(edge)), int(math.floor(self.y)), sideways=True)
        self._environment(dt)

    def _move(self, dt: float) -> None:
        # Horizontal, then vertical, each stopped by solid tiles.
        nx = self.x + self.vx * dt
        if self._hits(nx, self.y):
            self.vx = 0.0
        else:
            self.x = max(HALF, min(W - HALF, nx))
        ny = self.y + self.vy * dt
        was_falling = self.vy
        if self._hits(self.x, ny):
            if self.vy > 0:   # landed
                self.y = math.floor(ny + HALF) - HALF
                if was_falling > SAFE_LANDING:
                    self._hurt((was_falling - SAFE_LANDING) * 7, "landed too hard")
                    self.events.append(("bump", was_falling))
                if not self.grounded:
                    self.events.append(("land", was_falling))
                self.grounded = True
            else:             # hit the ceiling
                self.y = math.floor(ny - HALF) + 1 + HALF
                self.grounded = False
            self.vy = 0.0
        else:
            self.y = ny
            self.grounded = self._hits(self.x, self.y + 0.06)
        self.y = max(-12.0, self.y)
        if self.row > self.deepest:
            self.deepest = self.row
            if self.deepest % 50 == 0:
                self.events.append(("depth", self.deepest))

    def _burn(self, litres: float) -> None:
        if self.fuel <= 0:
            return
        self.fuel = max(0.0, self.fuel - litres)
        if self.fuel == 0:
            if self.on_surface:
                self.events.append(("empty", 0))
            else:
                self._tow("You ran out of fuel")

    def _environment(self, dt: float) -> None:
        h = self.heat()
        if h > 0:
            dmg = h * 6.0 * (1 - self.stat("RADIATOR")) * dt
            if dmg > 0:
                self._hurt(dmg, "overheated", quiet=True)

    def _hurt(self, amount: float, why: str, quiet: bool = False) -> None:
        if amount <= 0:
            return
        self.hull = max(0.0, self.hull - amount)
        if not quiet:
            self.events.append(("hurt", round(amount), why))
        if self.hull <= 0:
            self._tow(f"Your pod broke down ({why})")

    def _tow(self, why: str) -> None:
        """Rescued: towed back up for a fee. The cargo is lost."""
        fee = min(self.cash, 150 + self.cash // 10)
        self.cash -= fee
        lost = len(self.cargo)
        self.cargo = []
        self.drill = None
        self.x, self.y = START_X, -HALF
        self.vx = self.vy = 0.0
        self.grounded = True
        self.hull = self.max_hull
        self.fuel = self.max_fuel
        self.events.append(("tow", why, fee, lost))

    # ---------------------------------------------------------------- drilling

    def drill_time(self, t: int, row: int) -> float:
        base = {DIRT: 0.42, GAS: 0.42, LAVA: 0.5}.get(t)
        if base is None:
            base = 0.55 + 0.05 * (t - ORE0) if is_ore(t) else 0.42
        return base * (1 + 1.6 * row / H) / self.stat("DRILL")

    def _try_drill(self, col: int, row: int, sideways: bool = False) -> None:
        t = self.tile(col, row)
        if row < 0 or not solid(t):
            return
        if t == CORE and len(self.cargo) >= self.cargo_space:
            if not any(e[0] == "full" for e in self.events):
                self.events.append(("full", t))
            return
        if t in UNDRILLABLE:
            if not any(e[0] == "rock" for e in self.events):
                self.events.append(("rock", col, row))
            return
        end = (col + 0.5, row + 0.5 if not sideways else self.y)
        if not sideways:
            end = (col + 0.5, row + 1 - HALF)
        self.drill = Drill(col, row, 0.0, self.drill_time(t, row), (self.x, self.y), end)
        self.facing = (1 if col > self.x else -1) if sideways else self.facing
        self.vx = self.vy = 0.0
        self.events.append(("drill", col, row, t))

    def _step_drill(self, dt: float) -> None:
        d = self.drill
        d.t += dt
        k = min(1.0, d.t / d.dur)
        self.x = d.start[0] + (d.end[0] - d.start[0]) * k
        self.y = d.start[1] + (d.end[1] - d.start[1]) * k
        self._burn(BURN["drill"] * dt)
        if self.drill is None:   # towed (out of fuel)
            return
        self._environment(dt)
        if self.drill is None:
            return
        if k >= 1.0:
            self.drill = None
            self._dug(d.col, d.row)
            self.grounded = self._hits(self.x, self.y + 0.06)
            if self.row > self.deepest:
                self.deepest = self.row
                if self.deepest % 50 == 0:
                    self.events.append(("depth", self.deepest))

    def _dug(self, col: int, row: int) -> None:
        t = self.tile(col, row)
        self.set_tile(col, row, AIR)
        depth = 1 + 2 * row / H
        if t == GAS:
            self.events.append(("boom", col, row, "gas"))
            self._hurt(18 * depth, "a gas pocket exploded")
        elif t == LAVA:
            self.events.append(("lava", col, row))
            self._hurt(30 * depth, "you hit lava")
        elif is_ore(t):
            if len(self.cargo) >= self.cargo_space:
                self.events.append(("full", t))
            else:
                self.cargo.append(t)
                self.events.append(("ore", t, col, row))
                if t == CORE and not self.won:
                    self.won = True
                    self.events.append(("core",))

    # ---------------------------------------------------------------- items

    def use_item(self, name: str) -> None:
        if self.items.get(name, 0) <= 0:
            raise DigError(f"You have no {name.lower()}s. Buy them at the shop.")
        if name == "REPAIR KIT":
            if self.hull >= self.max_hull:
                raise DigError("Your hull is already fine.")
            self.hull = min(self.max_hull, self.hull + 0.35 * self.max_hull)
        elif name == "FUEL CAN":
            if self.fuel >= self.max_fuel:
                raise DigError("Your tank is already full.")
            self.fuel = min(self.max_fuel, self.fuel + 0.4 * self.max_fuel)
        elif name in ("DYNAMITE", "MEGA BLAST"):
            if self.on_surface:
                raise DigError("Not up here! Use it underground.")
            self._blast(1 if name == "DYNAMITE" else 2)
        elif name == "TELEPORTER":
            if self.on_surface:
                raise DigError("You're already on the surface.")
            self.drill = None
            self.x, self.y, self.vx, self.vy = START_X, -HALF, 0.0, 0.0
            self.grounded = True
            self.events.append(("teleport",))
        self.items[name] -= 1
        self.events.append(("item", name))

    def _blast(self, radius: int) -> None:
        cx, cy = int(math.floor(self.x)), int(math.floor(self.y))
        for row in range(cy - radius, cy + radius + 1):
            for col in range(cx - radius, cx + radius + 1):
                t = self.tile(col, row)
                if row >= 0 and t not in (BEDROCK, CONCRETE, AIR) and t != CORE:
                    self.set_tile(col, row, AIR)   # ore in the blast is lost
        self.drill = None
        self.grounded = self._hits(self.x, self.y + 0.06)
        self.events.append(("boom", cx, cy, "blast"))
        self._hurt(4 * radius, "your own blast")

    # ---------------------------------------------------------------- the buildings

    def _need(self, name: str) -> None:
        if self.building() != name:
            raise DigError(f"Park at the {name.title()} building first.")

    def refuel_cost(self) -> int:
        return int(math.ceil((self.max_fuel - self.fuel) * FUEL_PRICE))

    def refuel(self) -> int:
        self._need("FUEL")
        need = self.max_fuel - self.fuel
        if need <= 0.01:
            raise DigError("Your tank is already full.")
        afford = min(need, self.cash / FUEL_PRICE)
        if afford <= 0 and self.fuel < 0.25 * self.max_fuel:
            # Broke and empty: the station gives you enough to go and dig something up.
            self.fuel = 0.3 * self.max_fuel
            self.events.append(("refuel", 0))
            return 0
        if afford <= 0:
            raise DigError("You can't afford any fuel. Sell some ore first.")
        cost = int(math.ceil(afford * FUEL_PRICE))
        self.cash -= min(self.cash, cost)
        self.fuel += afford
        self.events.append(("refuel", cost))
        return cost

    def repair_cost(self) -> int:
        return int(math.ceil((self.max_hull - self.hull) * REPAIR_PRICE))

    def repair(self) -> int:
        self._need("REPAIR")
        need = self.max_hull - self.hull
        if need <= 0.01:
            raise DigError("Your hull is already in perfect shape.")
        afford = min(need, self.cash / REPAIR_PRICE)
        if afford <= 0:
            raise DigError("You can't afford repairs. Sell some ore first.")
        cost = int(math.ceil(afford * REPAIR_PRICE))
        self.cash -= min(self.cash, cost)
        self.hull += afford
        self.events.append(("repair", cost))
        return cost

    def sell(self) -> tuple[int, int]:
        """Sell the whole hold. Returns ($ earned, Chip Bank chips earned)."""
        self._need("SELL")
        if not self.cargo:
            raise DigError("Your cargo hold is empty. Go dig!")
        total = self.cargo_value
        self.cash += total
        self.earned += total
        self.chip_progress += total
        chips, self.chip_progress = divmod(self.chip_progress, CHIP_EVERY)
        counts: dict[int, int] = {}
        for t in self.cargo:
            counts[t] = counts.get(t, 0) + 1
        self.cargo = []
        self.events.append(("sell", total, chips, counts))
        return total, chips

    def upgrade_price(self, name: str) -> int | None:
        lvl = self.levels[name]
        prices = UPGRADES[name][1]
        return prices[lvl + 1] if lvl + 1 < len(prices) else None

    def buy_upgrade(self, name: str) -> None:
        self._need("SHOP")
        price = self.upgrade_price(name)
        if price is None:
            raise DigError(f"Your {name.lower()} is already the best there is.")
        if self.cash < price:
            raise DigError(f"You need ${price - self.cash:,} more.")
        self.cash -= price
        full_fuel, full_hull = self.fuel >= self.max_fuel - 0.01, self.hull >= self.max_hull - 0.01
        self.levels[name] += 1
        if name == "FUEL TANK" and full_fuel:
            self.fuel = self.max_fuel
        if name == "HULL" and full_hull:
            self.hull = self.max_hull
        self.events.append(("upgrade", name, self.levels[name]))

    def buy_item(self, name: str) -> None:
        self._need("SHOP")
        price = ITEMS[name][0]
        if self.cash < price:
            raise DigError(f"You need ${price - self.cash:,} more.")
        self.cash -= price
        self.items[name] += 1
        self.events.append(("buy", name))

    def pop_events(self) -> list[tuple]:
        ev, self.events = self.events, []
        return ev

    # ---------------------------------------------------------------- saving

    def to_dict(self) -> dict:
        x, y = self.drill.start if self.drill else (self.x, self.y)    # mid-drill, save where the drill began
        return {
            "v": 1, "seed": self.seed, "grid": ["".join(chr(48 + t) for t in row) for row in self.grid],
            "x": x, "y": y, "levels": self.levels, "fuel": self.fuel, "hull": self.hull,
            "cash": self.cash, "cargo": self.cargo, "items": self.items, "deepest": self.deepest,
            "earned": self.earned, "chip_progress": self.chip_progress, "won": self.won,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DeepDig":
        """Load a saved game (anything broken falls back to safe values)."""
        g = cls(seed=int(d.get("seed", 1)))
        rows = d.get("grid")
        if isinstance(rows, list) and len(rows) == H and all(isinstance(r, str) and len(r) == W for r in rows):
            valid = set(range(7)) | set(range(ORE0, CORE + 1))
            grid = [[ord(ch) - 48 for ch in r] for r in rows]
            if all(t in valid for r in grid for t in r):
                g.grid = grid
        for name in UPGRADES:
            lvl = d.get("levels", {}).get(name, 0)
            g.levels[name] = lvl if isinstance(lvl, int) and 0 <= lvl < len(UPGRADES[name][0]) else 0
        for name in ITEMS:
            n = d.get("items", {}).get(name, 0)
            g.items[name] = max(0, n) if isinstance(n, int) else 0

        def num(key, lo, hi, default):
            v = d.get(key, default)
            return max(lo, min(hi, v)) if isinstance(v, (int, float)) and not isinstance(v, bool) else default
        g.x = float(num("x", HALF, W - HALF, START_X))
        g.y = float(num("y", -HALF, H - 1, -HALF))
        g.fuel = float(num("fuel", 0, g.max_fuel, g.max_fuel))
        g.hull = float(num("hull", 1, g.max_hull, g.max_hull))
        g.cash = int(num("cash", 0, 10 ** 12, 0))
        g.deepest = int(num("deepest", 0, H, 0))
        g.earned = int(num("earned", 0, 10 ** 12, 0))
        g.chip_progress = int(num("chip_progress", 0, CHIP_EVERY - 1, 0))
        g.won = bool(d.get("won", False))
        cargo = d.get("cargo", [])
        g.cargo = [t for t in cargo if isinstance(t, int) and is_ore(t)][:g.cargo_space] if isinstance(cargo, list) else []
        if g._hits(g.x, g.y):   # saved inside rock somehow: back to the surface
            g.x, g.y = START_X, -HALF
        g.grounded = g._hits(g.x, g.y + 0.06)
        return g


# --------------------------------------------------------------------------- making the world


def generate(seed: int) -> list[list[int]]:
    """The underground: dirt, rocks, caves, hazards and ore, richer and nastier the deeper you go."""
    rng = random.Random(seed)
    grid = [[DIRT] * W for _ in range(H)]
    for row in range(H):
        depth = row / H
        for col in range(W):
            if row == 0:
                continue
            r = rng.random()
            if r < 0.02 + 0.10 * depth and row > 3:
                grid[row][col] = ROCK
                continue
            r = rng.random()
            if row > 25 and r < 0.012 + 0.01 * depth:
                grid[row][col] = GAS
                continue
            if row > 150 and r < 0.03 * depth:
                grid[row][col] = LAVA
                continue
            for k, ore in enumerate(ORES):
                if row < ore.top:
                    continue
                spread = max(20.0, (ore.peak - ore.top) * 1.2)
                chance = ore.rarity * math.exp(-((row - ore.peak) / spread) ** 2)
                if rng.random() < chance:
                    grid[row][col] = ORE0 + k
                    break
    # Caves: little air pockets to fall into.
    for _ in range(140):
        cx, cy = rng.randrange(W), rng.randrange(12, H - 10)
        for _ in range(rng.randint(3, 12)):
            if 0 <= cx < W and 12 <= cy < H - 6:
                grid[cy][cx] = AIR
            cx += rng.choice((-1, 1, 0))
            cy += rng.choice((0, 0, 1, -1))
    # Under the buildings: concrete foundations.
    for a, b in BUILDINGS.values():
        for col in range(a, b + 1):
            grid[0][col] = CONCRETE
    # The bottom: bedrock, with the core in a chamber in the middle.
    for row in range(H - 3, H):
        for col in range(W):
            grid[row][col] = BEDROCK
    mid = W // 2
    for col in range(mid - 3, mid + 4):
        grid[H - 4][col] = AIR
        grid[H - 5][col] = DIRT
    grid[H - 4][mid] = CORE
    grid[H - 3][mid] = BEDROCK
    return grid
