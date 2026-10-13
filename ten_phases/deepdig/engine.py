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

from .oil import OilField

W = 36                 # tiles across
H = 420                # the Heart of the Earth's layer; the ground goes on forever below it
CHUNK = 60             # the world is made this many rows at a time, as you dig down to it
DEEP_ORE_ROW = 400     # below here every ore keeps its mix from this row (and gets more common)
FEET_PER_ROW = 12.5    # for the depth readout

# --------------------------------------------------------------------------- tiles

AIR, DIRT, ROCK, GAS, LAVA, BEDROCK, CONCRETE = range(7)
CORE = 9    # the Heart of the Earth, waiting at the very bottom
ORE0 = 10   # ore kinds start here (new ores only ever go on the end, so saved worlds keep their ore)


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
    Ore("COAL", 20, 1, 12, 0.070, (58, 58, 66)),
    Ore("QUARTZ", 90, 20, 70, 0.035, (255, 205, 232)),
    Ore("AMBER", 450, 100, 165, 0.022, (255, 150, 10)),
    Ore("TITANIUM", 1200, 150, 260, 0.016, (120, 132, 156)),
    Ore("AMETHYST", 3500, 200, 300, 0.012, (150, 70, 200)),
    Ore("SAPPHIRE", 9000, 240, 345, 0.009, (40, 80, 230)),
    Ore("METEORITE", 80000, 340, 404, 0.004, (90, 255, 210)),
)
ORE_END = ORE0 + len(ORES)
OLD_CORE = 20                    # where saves from before v2 kept the core
CORE_VALUE = 1_000_000
SOLID = {DIRT, ROCK, GAS, LAVA, BEDROCK, CONCRETE}
UNDRILLABLE = {ROCK, BEDROCK, CONCRETE}


def is_ore(t: int) -> bool:
    return ORE0 <= t < ORE_END or t == CORE


def ore_of(t: int) -> Ore | None:
    if ORE0 <= t < ORE_END:
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

# The town sits on solid foundations to the left of the mine (columns -TOWN_W to -1): you can't dig there.
TOWN_W = 63
BUILDINGS = {   # name: (first column, last column)
    "BANK": (-61, -56),
    "OIL": (-54, -49),
    "BOTS": (-46, -41),
    "FUEL": (-38, -34),
    "SELL": (-31, -26),
    "SHOP": (-23, -18),
    "LAB": (-15, -10),
    "REPAIR": (-7, -4),
}
OIL_PRICE = 20000      # buying into the oil business (the Oil Field mini-game)
BANK_RATE = 2500       # $ per Chip Bank chip at the bank
START_X = -1.5         # where you start, and where the tow truck drops you: the town's edge, by the mine

# --------------------------------------------------------------------------- upgrades and items

UPGRADES = {
    # name: (values per level, prices to reach each level)
    "DRILL": ((1.0, 1.45, 2.0, 2.8, 3.8, 5.2, 7.0, 9.5),
              (0, 750, 2500, 7500, 25000, 90000, 250000, 600000)),
    "HULL": ((100, 150, 220, 320, 460, 650, 900, 1250),
             (0, 750, 2500, 7500, 25000, 90000, 250000, 600000)),
    "ENGINE": ((1.0, 1.2, 1.45, 1.75, 2.1, 2.5, 2.9, 3.4),
               (0, 750, 2500, 7500, 25000, 90000, 250000, 600000)),
    "FUEL TANK": ((15, 24, 36, 52, 76, 115, 160, 220),
                  (0, 750, 2000, 6000, 20000, 70000, 200000, 500000)),
    "CARGO": ((8, 15, 25, 40, 65, 100, 140, 200),
              (0, 750, 2000, 6000, 20000, 70000, 200000, 500000)),
    "RADIATOR": ((0.0, 0.25, 0.45, 0.65, 0.8, 0.92, 0.96, 0.99),
                 (0, 1000, 3500, 10000, 30000, 100000, 250000, 600000)),
    "SHOCKS": ((8.0, 9.5, 11.0, 12.5, 14.0, 15.0, 16.0, 17.0),     # how fast you can land without damage
               (0, 600, 2000, 6000, 15000, 40000, 100000, 250000)),
    "LAMP": ((7.5, 9.5, 11.5, 14.0, 17.0, 20.5, 24.5, 29.0),       # light radius, in tiles
             (0, 500, 1500, 4000, 10000, 25000, 60000, 150000)),
    "SCANNER": ((0, 3, 5, 7, 9, 12, 15, 20),                       # ore shows through the dark this many tiles away
                (0, 1000, 3000, 8000, 20000, 50000, 120000, 300000)),
    "TOP DRILL": ((0, 1), (0, 12000)),                             # lets you drill upward
    "ARMOR": ((0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7),            # less damage from gas, lava and blasts
              (0, 1500, 4000, 10000, 25000, 60000, 150000, 350000)),
    "REFINERY": ((1.0, 1.05, 1.1, 1.15, 1.2, 1.3, 1.4, 1.5),       # ore sells for more
                 (0, 2000, 6000, 15000, 40000, 100000, 250000, 600000)),
    "RESCUE": ((0.0, 0.15, 0.3, 0.45, 0.55, 0.65, 0.75, 0.85),     # when towed: cargo kept, and less fee
               (0, 1000, 3000, 8000, 20000, 50000, 120000, 300000)),
    "DIG BOTS": ((0, 1, 2, 3), (0, 4000, 12000, 30000)),            # little robots that mine for you
    "BOT LEVEL": ((0, 1, 2, 3, 4, 5, 6, 7),                         # how good they are (see BOT_SPEED and friends)
                  (0, 3000, 8000, 20000, 50000, 120000, 280000, 600000)),
}
MAX_BOTS = 3
BOT_SPEED = (1.0, 1.3, 1.6, 2.0, 2.5, 3.0, 3.6, 4.3)     # by BOT LEVEL
BOT_CARRY = (3, 4, 5, 6, 8, 10, 12, 15)
BOT_DEPTH = (40, 80, 130, 180, 240, 300, 380, 470)     # the deepest row they'll go to
BOT_LOOK = 6                                           # how far (in tiles) a bot spots ore
# Which building sells which upgrade: pod parts at the garage, gadgets (and items) at the lab.
UPGRADE_SHOP = {name: "SHOP" for name in ("DRILL", "TOP DRILL", "HULL", "ENGINE", "FUEL TANK", "CARGO", "RADIATOR",
                                          "SHOCKS")}
UPGRADE_SHOP.update({name: "LAB" for name in ("LAMP", "SCANNER", "ARMOR", "REFINERY", "RESCUE")})
UPGRADE_SHOP.update({"DIG BOTS": "BOTS", "BOT LEVEL": "BOTS"})
UPGRADE_INFO = {
    "DRILL": "Drill faster through everything",
    "HULL": "More armour before you break",
    "ENGINE": "Fly faster and carry heavy loads",
    "FUEL TANK": "Stay down longer",
    "CARGO": "Carry more ore",
    "RADIATOR": "Stay cool in the hot depths",
    "SHOCKS": "Land harder without denting the hull",
    "LAMP": "A brighter light in the dark",
    "SCANNER": "Spot ore through the dark",
    "TOP DRILL": "A roof drill: hold UP against a ceiling to dig up",
    "ARMOR": "Take less damage from gas, lava and blasts",
    "REFINERY": "Your ore sells for more",
    "RESCUE": "Keep cargo (and pay less) when you're towed",
    "DIG BOTS": "Little robots that dig ore and sell it for you",
    "BOT LEVEL": "Faster bots that carry more and dig deeper",
}


def upgrade_text(name: str, level: int) -> str:
    """What an upgrade level does, in a few characters."""
    v = UPGRADES[name][0][level]
    text = {   # each is only worked out for its own upgrade
        "DRILL": lambda: f"x{v:g} SPEED", "HULL": lambda: f"{v} HP", "ENGINE": lambda: f"x{v:g} POWER",
        "FUEL TANK": lambda: f"{v} L", "CARGO": lambda: f"{v} SLOTS", "RADIATOR": lambda: f"{round(v * 100)}% COOLER",
        "SHOCKS": lambda: "NO FALL DAMAGE" if v > MAX_FALL else f"SAFE TO {v:g}",
        "LAMP": lambda: f"{v:g} TILES", "SCANNER": lambda: f"{v} TILES" if v else "NONE",
        "TOP DRILL": lambda: "DIGS UP" if v else "NO ROOF DRILL", "ARMOR": lambda: f"-{round(v * 100)}% DAMAGE",
        "REFINERY": lambda: f"+{round((v - 1) * 100)}% PRICE", "RESCUE": lambda: f"KEEP {round(v * 100)}%",
        "DIG BOTS": lambda: (f"{v} BOT{'S' if v != 1 else ''}" if v else "NO BOTS"),
        "BOT LEVEL": lambda: f"x{BOT_SPEED[v]:g} SPEED, {BOT_CARRY[v]} ORE",
    }
    return text[name]()
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
BURN = {"idle": 0.02, "move": 0.08, "thrust": 0.26, "drill": 0.24}
HEAT_START = 140     # rows below which it starts getting hot


class DigError(Exception):
    """Something you can't do right now; the message is shown to the player."""


@dataclass
class Bot:
    """A little digging robot. It moves a tile at a time: from (col, row) to (to_col, to_row) over `dur` seconds,
    drilling the tile first if it's solid. It carries ore up to the surface, where it's sold for you."""
    col: int
    row: int
    to_col: int = 0
    to_row: int = 0
    t: float = 0.0
    dur: float = 0.0
    state: str = "dig"           # dig (looking for ore), home (carrying it up), wait
    carry: list = None
    stuck: float = 0.0
    seed: int = 0

    def __post_init__(self):
        self.carry = list(self.carry or [])
        self.to_col, self.to_row = self.col, self.row

    @property
    def pos(self) -> tuple[float, float]:
        """Where it is now (the middle of the tile it's on, sliding to the next)."""
        k = min(1.0, self.t / self.dur) if self.dur else 1.0
        return (self.col + (self.to_col - self.col) * k + 0.5, self.row + (self.to_row - self.row) * k + 0.5)

    @property
    def moving(self) -> bool:
        return (self.to_col, self.to_row) != (self.col, self.row)


@dataclass
class Drill:
    col: int
    row: int
    t: float
    dur: float
    start: tuple
    end: tuple
    way: str = "down"      # down, left, right or up


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
        self.bots: list[Bot] = []
        self.bot_earned = 0        # $ the bots have made, all time
        self.oil: OilField | None = None   # the oil business, once you've bought it

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
        """What the hold sells for (with the refinery's bonus)."""
        return int(sum(tile_value(t) for t in self.cargo) * self.stat("REFINERY"))

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
        if not (self.on_surface and self.grounded and self.drill is None and self.x < 0):
            return None
        for name, (a, b) in BUILDINGS.items():
            if a <= self.x <= b + 1:
                return name
        return None

    def heat(self) -> float:
        """0 (cool), 1 (scorching, at the Heart's depth) up to 3 far below it."""
        return max(0.0, min(3.0, (self.y - HEAT_START) / (H - HEAT_START)))   # keeps rising past the Heart

    # ---------------------------------------------------------------- the grid

    def tile(self, col: int, row: int) -> int:
        if -TOWN_W <= col < 0:               # the town: open sky, on foundations you can't dig
            return AIR if row < 0 else CONCRETE if row < 3 else BEDROCK
        if col < -TOWN_W or col >= W:
            return BEDROCK
        if row < 0:
            return AIR
        if row >= len(self.grid):
            self._grow(row)
        return self.grid[row][col]

    def set_tile(self, col: int, row: int, t: int) -> None:
        if 0 <= col < W and row >= 0:
            if row >= len(self.grid):
                self._grow(row)
            self.grid[row][col] = t

    def _grow(self, row: int) -> None:
        """Make the ground down to this row (each chunk comes out the same for a seed, whenever it's made)."""
        while len(self.grid) <= row:
            self.grid.extend(make_chunk(self.seed, len(self.grid) // CHUNK))

    def _hits(self, x: float, y: float) -> bool:
        """Does a pod at (x, y) overlap anything solid?"""
        for col in range(int(math.floor(x - HALF + 1e-6)), int(math.floor(x + HALF - 1e-6)) + 1):
            for row in range(int(math.floor(y - HALF + 1e-6)), int(math.floor(y + HALF - 1e-6)) + 1):
                if solid(self.tile(col, row)):
                    return True
        return False

    # ---------------------------------------------------------------- a frame

    def step(self, dt: float, left=False, right=False, up=False, down=False) -> None:
        """Advance by dt seconds (in small slices, so a slow frame doesn't slow the game or skip walls)."""
        dt = max(0.0, min(dt, 0.25))
        while dt > 1e-9:
            part = min(dt, 1 / 30)
            self._step(part, left, right, up, down)
            dt -= part

    def _step(self, dt: float, left: bool, right: bool, up: bool, down: bool) -> None:
        self.clock += dt
        self.step_oil(dt)
        for i, bot in enumerate(self.bots):
            self._step_bot(i, bot, dt)
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
        # Start drilling: up into the ceiling (with the roof drill), down when standing on something, or
        # sideways into a wall.
        if up and self.fuel > 0 and self.stat("TOP DRILL") and self._hits(self.x, self.y - 0.06):
            col, row = int(math.floor(self.x)), int(math.floor(self.y - HALF - 0.05))
            if solid(self.tile(col, row)):
                self._try_drill(col, row, way="up")
        elif self.grounded and self.fuel > 0:
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
                    self._try_drill(int(math.floor(edge)), int(math.floor(self.y)), way="left" if left else "right")
        self._environment(dt)

    def _move(self, dt: float) -> None:
        # Horizontal, then vertical, each stopped by solid tiles.
        nx = self.x + self.vx * dt
        if self._hits(nx, self.y):
            self.vx = 0.0
        else:
            self.x = max(-TOWN_W + HALF, min(W - HALF, nx))
        ny = self.y + self.vy * dt
        was_falling = self.vy
        if self._hits(self.x, ny):
            if self.vy > 0:   # landed
                self.y = math.floor(ny + HALF) - HALF
                safe = self.stat("SHOCKS")
                if was_falling > safe:
                    self._hurt((was_falling - safe) * 7, "landed too hard")
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
        """Rescued: towed back up for a fee. The cargo is lost (rescue insurance keeps some, best first)."""
        keep = self.stat("RESCUE")
        fee = min(self.cash, int((150 + self.cash // 10) * (1 - keep)))
        self.cash -= fee
        kept = sorted(self.cargo, key=tile_value, reverse=True)[:int(len(self.cargo) * keep)]
        lost = len(self.cargo) - len(kept)
        self.cargo = kept
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
        return base * min(4.0, 1 + 1.6 * row / H) / self.stat("DRILL")

    def _try_drill(self, col: int, row: int, way: str = "down") -> None:
        t = self.tile(col, row)
        if -TOWN_W <= col < 0 and row >= 0:                # the town's foundations
            if not any(e[0] == "town" for e in self.events):
                self.events.append(("town",))
            return
        if row < 0 or not solid(t) or not 0 <= col < W:   # (the world's edge is just a wall)
            return
        if t == CORE and len(self.cargo) >= self.cargo_space:
            if not any(e[0] == "full" for e in self.events):
                self.events.append(("full", t))
            return
        if t in UNDRILLABLE:
            if not any(e[0] == "rock" for e in self.events):
                self.events.append(("rock", col, row))
            return
        dur = self.drill_time(t, row)
        if way == "down":
            end = (col + 0.5, row + 1 - HALF)
        elif way == "up":
            end, dur = (col + 0.5, row + 0.5), dur * 1.25       # digging up is slower
        else:
            end = (col + 0.5, self.y)
            self.facing = 1 if way == "right" else -1
        self.drill = Drill(col, row, 0.0, dur, (self.x, self.y), end, way)
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
        depth = min(6.0, 1 + 2 * row / H) * (1 - self.stat("ARMOR"))
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
        self._hurt(4 * radius * (1 - self.stat("ARMOR")), "your own blast")

    # ---------------------------------------------------------------- the buildings

    def _need(self, name: str) -> None:
        if self.building() != name:
            label = {"SHOP": "Garage", "LAB": "Tech Lab", "SELL": "Ore Buyer", "OIL": "Oil Refinery",
                     "BOTS": "Robotics", "BANK": "Bank"}.get(name, name.title())
            raise DigError(f"Park at the {label} first.")

    def refuel_cost(self) -> int:
        return int(math.ceil((self.max_fuel - self.fuel) * FUEL_PRICE))

    def emergency_fuel(self) -> bool:
        """Broke (can't buy a single litre) and nearly empty: the next fill-up is free."""
        return self.cash < FUEL_PRICE and self.fuel < 0.25 * self.max_fuel

    def refuel(self) -> int:
        self._need("FUEL")
        need = self.max_fuel - self.fuel
        if need <= 0.01:
            raise DigError("Your tank is already full.")
        afford = min(need, self.cash / FUEL_PRICE)
        if self.emergency_fuel():
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
        chips = self._bank(total)
        counts: dict[int, int] = {}
        for t in self.cargo:
            counts[t] = counts.get(t, 0) + 1
        self.cargo = []
        self.events.append(("sell", total, chips, counts))
        return total, chips

    # ---------------------------------------------------------------- the bank

    def can_exchange(self) -> int:
        """How many chips your cash would buy at the bank."""
        return self.cash // BANK_RATE

    def exchange(self, chips: int) -> int:
        """Turn cash into Chip Bank chips. Returns the chips (the screen puts them in the Chip Bank)."""
        self._need("BANK")
        if not isinstance(chips, int) or chips <= 0:
            raise DigError("Pick how many chips you want.")
        cost = chips * BANK_RATE
        if self.cash < cost:
            raise DigError(f"You need ${cost - self.cash:,} more for {chips} chip{'s' if chips != 1 else ''}.")
        self.cash -= cost
        self.events.append(("exchange", chips, cost))
        return chips

    # ---------------------------------------------------------------- the oil business

    def buy_oil(self) -> None:
        self._need("OIL")
        if self.oil is not None:
            raise DigError("You already own the oil business.")
        if self.cash < OIL_PRICE:
            raise DigError(f"You need ${OIL_PRICE - self.cash:,} more.")
        self.cash -= OIL_PRICE
        self.oil = OilField(self.seed + 17, self)
        self.events.append(("oil_bought",))

    def step_oil(self, dt: float) -> list[tuple]:
        """The oil field runs all the time (even while you dig). Its sales are banked here, and its other
        events are handed back for the Oil Field screen to show."""
        if self.oil is None:
            return []
        self.oil.step(dt)
        out = []
        for ev in self.oil.pop_events():
            if ev[0] == "sell":
                chips = self._bank(ev[1])
                self.events.append(("oil_sell", ev[1], chips, ev[2]))
            out.append(ev)
        return out

    def _bank(self, total: int) -> int:
        """Money from ore: cash, the all-time total, and chips for the Chip Bank (returned)."""
        self.cash += total
        self.earned += total
        self.chip_progress += total
        chips, self.chip_progress = divmod(self.chip_progress, CHIP_EVERY)
        return chips

    # ---------------------------------------------------------------- the dig bots

    def _bot_blocked(self, col: int, row: int, bot: Bot) -> bool:
        """Tiles a bot won't go into: rock, hazards, the Heart (that's yours), the town, off the map."""
        if not 0 <= col < W:
            return True
        if row < 0:
            return bot.state != "home"
        if row > BOT_DEPTH[self.levels["BOT LEVEL"]] and bot.state == "dig":
            return True
        t = self.tile(col, row)
        if is_ore(t) and len(bot.carry) >= BOT_CARRY[self.levels["BOT LEVEL"]]:
            return True                       # full: leave the ore for next time
        return t in UNDRILLABLE or t in (GAS, LAVA, CORE)

    def _bot_target(self, bot: Bot) -> tuple[int, int] | None:
        """The nearest ore it can see."""
        best, best_d = None, None
        for row in range(max(0, bot.row - BOT_LOOK), bot.row + BOT_LOOK + 1):
            for col in range(max(0, bot.col - BOT_LOOK), min(W - 1, bot.col + BOT_LOOK) + 1):
                t = self.tile(col, row)
                if t != CORE and is_ore(t) and not self._bot_blocked(col, row, bot):
                    d = abs(col - bot.col) + abs(row - bot.row)
                    if best_d is None or d < best_d:
                        best, best_d = (col, row), d
        return best

    def _step_bot(self, i: int, bot: Bot, dt: float) -> None:
        lvl = self.levels["BOT LEVEL"]
        if bot.moving:
            bot.t += dt
            if bot.t < bot.dur:
                return
            t = self.tile(bot.to_col, bot.to_row)
            if bot.to_row >= 0 and solid(t):        # the drilling's done
                self.set_tile(bot.to_col, bot.to_row, AIR)
                if is_ore(t):
                    bot.carry.append(t)
                    self.events.append(("bot_ore", i, t, bot.to_col, bot.to_row))
            bot.col, bot.row, bot.t, bot.dur = bot.to_col, bot.to_row, 0.0, 0.0
            if bot.row < 0 and bot.state == "home":
                self._bot_sell(i, bot)
            return
        if bot.state == "dig" and len(bot.carry) >= BOT_CARRY[lvl]:
            bot.state = "home"
        rng = random.Random(bot.seed * 7919 + int(self.clock * 10) * 31 + bot.col * 3 + bot.row)
        if bot.state == "home":
            goal = (bot.col, -1)
        else:
            goal = self._bot_target(bot) or (bot.col + rng.choice((-3, 3)), bot.row + 3)
        dx, dy = goal[0] - bot.col, goal[1] - bot.row
        moves = []
        if dy:
            moves.append((0, 1 if dy > 0 else -1))
        if dx:
            moves.append((1 if dx > 0 else -1, 0))
        rest = [m for m in ((0, 1), (1, 0), (-1, 0), (0, -1)) if m not in moves]
        rng.shuffle(rest)
        if bot.state == "home":              # going up: sideways around rock before going down again
            rest.sort(key=lambda m: m[1])
        for mx, my in moves + rest:
            col, row = bot.col + mx, bot.row + my
            if self._bot_blocked(col, row, bot):
                continue
            t = self.tile(col, row)
            speed = BOT_SPEED[lvl]
            if row >= 0 and solid(t):
                base = 0.9 + 0.06 * (t - ORE0) if is_ore(t) else 0.8
                dur = base * min(4.0, 1 + 1.6 * row / H) / speed
            else:
                dur = 0.28 / speed
            bot.to_col, bot.to_row, bot.t, bot.dur = col, row, 0.0, dur
            bot.stuck = 0.0
            return
        bot.stuck += dt                       # boxed in: after a moment it beams home
        if bot.stuck > 3.0:
            bot.col, bot.row = self._bot_spawn_col(i), -1
            bot.to_col, bot.to_row = bot.col, bot.row
            bot.stuck = 0.0
            self._bot_sell(i, bot)

    def _bot_sell(self, i: int, bot: Bot) -> None:
        """Back at the surface: the haul is sold (refinery bonus and all), and back down it goes."""
        if bot.carry:
            total = int(sum(tile_value(t) for t in bot.carry) * self.stat("REFINERY"))
            chips = self._bank(total)
            self.bot_earned += total
            self.events.append(("bot_sell", i, total, chips, len(bot.carry)))
            bot.carry = []
        bot.state = "dig"

    def _bot_spawn_col(self, i: int) -> int:
        return (5 + i * 12 + int(self.clock)) % (W - 4) + 2

    def _sync_bots(self) -> None:
        """One bot per DIG BOTS level; new ones start at the top of the mine."""
        want = self.stat("DIG BOTS")
        while len(self.bots) < want:
            i = len(self.bots)
            self.bots.append(Bot(self._bot_spawn_col(i), -1, seed=self.seed + i * 101))
        del self.bots[want:]

    def upgrade_price(self, name: str) -> int | None:
        lvl = self.levels[name]
        prices = UPGRADES[name][1]
        return prices[lvl + 1] if lvl + 1 < len(prices) else None

    def buy_upgrade(self, name: str) -> None:
        self._need(UPGRADE_SHOP[name])
        price = self.upgrade_price(name)
        if price is None:
            raise DigError(f"Your {name.lower()} is already the best there is.")
        if self.cash < price:
            raise DigError(f"You need ${price - self.cash:,} more.")
        self.cash -= price
        full_fuel, full_hull = self.fuel >= self.max_fuel - 0.01, self.hull >= self.max_hull - 0.01
        self.levels[name] += 1
        self._sync_bots()
        if name == "FUEL TANK" and full_fuel:
            self.fuel = self.max_fuel
        if name == "HULL" and full_hull:
            self.hull = self.max_hull
        self.events.append(("upgrade", name, self.levels[name]))

    def buy_item(self, name: str) -> None:
        self._need("LAB")
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
            "v": 3, "seed": self.seed, "grid": ["".join(chr(48 + t) for t in row) for row in self.grid],
            "x": x, "y": y, "levels": self.levels, "fuel": self.fuel, "hull": self.hull,
            "cash": self.cash, "cargo": self.cargo, "items": self.items, "deepest": self.deepest,
            "earned": self.earned, "chip_progress": self.chip_progress, "won": self.won,
            "bots": [[b.col, b.row, b.state, b.carry] for b in self.bots], "bot_earned": self.bot_earned,
            "oil": self.oil.to_dict() if self.oil else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DeepDig":
        """Load a saved game (anything broken falls back to safe values)."""
        g = cls(seed=int(d.get("seed", 1)))
        version = d.get("v", 1)
        old = version == 1                # saved before the core moved to its own tile number
        rows = d.get("grid")
        if (isinstance(rows, list) and rows and len(rows) % CHUNK == 0 and len(rows) <= 2000 * CHUNK
                and all(isinstance(r, str) and len(r) == W for r in rows)):
            valid = set(range(7)) | {CORE} | set(range(ORE0, ORE_END))
            grid = [[ord(ch) - 48 for ch in r] for r in rows]
            if old:   # the old world had a bedrock floor under the core: open it up
                grid = [[CORE if t == OLD_CORE else t for t in r] for r in grid]
                for row in range(max(0, len(grid) - 3), len(grid)):
                    grid[row] = [t if abs(c - W // 2) <= 3 and row == len(grid) - 3 else (DIRT if t == BEDROCK else t)
                                 for c, t in enumerate(grid[row])]
            if version in (1, 2):         # the town used to stand on the mine: its foundations go
                grid[0] = [DIRT if t == CONCRETE else t for t in grid[0]]
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
        g.x = float(num("x", -TOWN_W + HALF, W - HALF, START_X))
        g.y = float(num("y", -HALF, len(g.grid) - 1, -HALF))
        g.fuel = float(num("fuel", 0, g.max_fuel, g.max_fuel))
        g.hull = float(num("hull", 1, g.max_hull, g.max_hull))
        g.cash = int(num("cash", 0, 10 ** 12, 0))
        g.deepest = int(num("deepest", 0, len(g.grid), 0))
        g.earned = int(num("earned", 0, 10 ** 12, 0))
        g.chip_progress = int(num("chip_progress", 0, CHIP_EVERY - 1, 0))
        g.won = bool(d.get("won", False))
        g.bot_earned = int(num("bot_earned", 0, 10 ** 12, 0))
        if isinstance(d.get("oil"), dict):
            try:
                g.oil = OilField.from_dict(d["oil"], g)
            except (TypeError, ValueError, KeyError):
                g.oil = OilField(g.seed + 17, g)     # owned, but the save was broken: a fresh field
        g._sync_bots()
        saved = d.get("bots")
        for bot, b in zip(g.bots, saved if isinstance(saved, list) else []):
            try:
                col, row, state, carry = b
                col, row = int(col), int(row)
            except (TypeError, ValueError):
                continue
            if 0 <= col < W and -1 <= row < len(g.grid) and (row < 0 or not solid(g.tile(col, row))):
                bot.col, bot.row = bot.to_col, bot.to_row = col, row
            bot.state = state if state in ("dig", "home") else "dig"
            if isinstance(carry, list):
                bot.carry = [t for t in carry if isinstance(t, int) and not isinstance(t, bool)
                             and is_ore(t) and t != CORE][:BOT_CARRY[-1]]
        cargo = d.get("cargo", [])
        if not isinstance(cargo, list):
            cargo = []
        if old:
            cargo = [CORE if t == OLD_CORE else t for t in cargo]
        g.cargo = [t for t in cargo if isinstance(t, int) and not isinstance(t, bool) and is_ore(t)][:g.cargo_space]
        if g._hits(g.x, g.y):   # saved inside rock somehow: back to the surface
            g.x, g.y = START_X, -HALF
        g.grounded = g._hits(g.x, g.y + 0.06)
        return g


# --------------------------------------------------------------------------- making the world


def generate(seed: int, rows: int = H) -> list[list[int]]:
    """The first `rows` rows of a world (rounded up to whole chunks)."""
    grid: list[list[int]] = []
    while len(grid) < rows:
        grid.extend(make_chunk(seed, len(grid) // CHUNK))
    return grid


def make_chunk(seed: int, chunk: int) -> list[list[int]]:
    """CHUNK rows of underground: dirt, rocks, caves, hazards and ore, richer and nastier the deeper you go.

    Below the Heart of the Earth it never ends: the deep ores stay, get more common, and so do the hazards.
    """
    rng = random.Random(seed * 1_000_003 + chunk * 7919)
    top = chunk * CHUNK
    grid = [[DIRT] * W for _ in range(CHUNK)]
    for i in range(CHUNK):
        row = top + i
        depth = row / H
        ore_row = min(row, DEEP_ORE_ROW)
        richer = 1 + min(2.0, max(0, row - H) / 600)        # past the Heart, ore keeps getting more common
        for col in range(W):
            if row == 0:
                continue
            r = rng.random()
            if r < min(0.30, 0.02 + 0.10 * depth) and row > 3:
                grid[i][col] = ROCK
                continue
            r = rng.random()
            if row > 25 and r < min(0.035, 0.012 + 0.01 * depth):
                grid[i][col] = GAS
                continue
            if row > 150 and r < min(0.08, 0.03 * depth):
                grid[i][col] = LAVA
                continue
            for k, ore in enumerate(ORES):
                if row < ore.top:
                    continue
                spread = max(20.0, (ore.peak - ore.top) * 1.2)
                chance = ore.rarity * math.exp(-((ore_row - ore.peak) / spread) ** 2)
                if rng.random() < chance * richer:
                    grid[i][col] = ORE0 + k
                    break
    # Caves: little air pockets to fall into (kept inside this chunk).
    for _ in range(20):
        cx, cy = rng.randrange(W), rng.randrange(CHUNK)
        for _ in range(rng.randint(3, 12)):
            if 0 <= cx < W and 0 <= cy < CHUNK and top + cy >= 12:
                grid[cy][cx] = AIR
            cx += rng.choice((-1, 1, 0))
            cy += rng.choice((0, 0, 1, -1))
    if top <= H - 5 < top + CHUNK:   # the Heart of the Earth, in a chamber on a bedrock plinth
        mid = W // 2
        for col in range(mid - 3, mid + 4):
            grid[H - 5 - top][col] = DIRT
            grid[H - 4 - top][col] = AIR
            grid[H - 3 - top][col] = BEDROCK
        grid[H - 4 - top][mid] = CORE
    return grid
