"""The Oil Field: Deep Dig's oil business, a Turmoil-style game that never ends.

A strip of land seen from the side. Underground (ROWS deep) there are oil pockets, gas pockets and rock, all
hidden until scanned or drilled. You put rigs on the surface and lay pipes down to the oil; rigs pump it into
their tanks; trucks haul it along the road to two buyers, one at each end, whose prices keep moving (and drop a
little when you flood them). There are no rounds: buy the next plot of land to the right whenever you like,
and each one is a bit richer than the last.

No drawing here. Columns run left to right from 0 (land you own is 0 .. width-1); rows run down from 0 (just
under the surface). Money is the Deep Dig game's cash: the field spends it, and its sales come back as
("sell", total) events for the game to bank.
"""

from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass, field

ROWS = 18
PLOT = 8                 # columns in a plot of land
START_PLOTS = 3
DIRT, ROCK, GAS, OIL = range(4)

# Upgrades: name -> (value per level, price to reach each level)
OIL_UPGRADES = {
    "PUMPS": ((4, 7, 11, 16, 24, 35, 50, 70), (0, 2000, 5000, 12000, 30000, 70000, 160000, 350000)),
    "TANKS": ((300, 500, 800, 1200, 1800, 2700, 4000, 6000), (0, 1500, 4000, 10000, 25000, 60000, 140000, 300000)),
    "TRUCK SIZE": ((200, 350, 550, 800, 1200, 1800, 2600, 3800),
                   (0, 1500, 4000, 10000, 25000, 60000, 140000, 300000)),
    "TRUCK SPEED": ((2.5, 3.2, 4.0, 5.0, 6.0, 7.5, 9.0, 11.0),
                    (0, 1200, 3500, 9000, 22000, 50000, 120000, 260000)),
    "DRILL BITS": ((3, 4.5, 6, 8, 11, 15, 20, 28), (0, 1000, 3000, 8000, 20000, 45000, 100000, 220000)),
    "ROCK BIT": ((0, 1), (0, 20000)),          # pipes can go through rock
    "DISPATCHER": ((0, 1), (0, 15000)),        # trucks drive themselves
}
OIL_INFO = {
    "PUMPS": "Barrels a second each rig pumps",
    "TANKS": "How much oil a rig's tank holds",
    "TRUCK SIZE": "How much oil a truck carries",
    "TRUCK SPEED": "How fast trucks drive",
    "DRILL BITS": "How fast pipes are laid",
    "ROCK BIT": "Pipes can drill straight through rock",
    "DISPATCHER": "Trucks pick their own jobs and buyers",
}
SCAN_PRICE = 250
SCAN_RADIUS = 3
PIPE_PRICE = 6           # $ per cell of pipe
RIG_PRICE = 1500         # the first; each one after costs RIG_STEP more
RIG_STEP = 500
TRUCK_PRICE = 2000       # the first extra truck; each one after costs more (x1.5)
MAX_TRUCKS = 10
LAND_PRICE = 3000        # the 4th plot; each one after costs x1.4
LOAD_RATE = 60           # barrels a second into or out of a truck
BUYER_W = 4              # the buyers' yards, just past each end of the road
BUYERS = ("L", "R")
BUYER_NAMES = {"L": "ACME OIL", "R": "PETRO CO"}


class OilError(Exception):
    """Something you can't do right now; the message is shown to the player."""


@dataclass
class Pocket:
    id: int
    kind: int                # OIL or GAS
    cells: list
    amount: float = 0.0      # barrels left (oil)
    start: float = 0.0


@dataclass
class Rig:
    col: int
    pipe: list = field(default_factory=list)       # cells, in the order they were drilled (from the top)
    queue: list = field(default_factory=list)      # cells still to drill
    dig: float = 0.0
    tank: float = 0.0
    paid: int = 0                                  # $ prepaid for the queue (refunded if it's cut short)


@dataclass
class Truck:
    x: float
    load: float = 0.0
    goal: tuple | None = None                      # ("rig", index) or ("buyer", "L"/"R")
    auto: bool = True
    earning: float = 0.0                           # $ for the oil it's unloading (paid when it's done)


class OilField:
    def __init__(self, seed: int, wallet=None):
        self.seed = seed
        self.wallet = wallet                       # the Deep Dig game: its cash is our money
        self.plots = START_PLOTS
        self.levels = {k: 0 for k in OIL_UPGRADES}
        self.tiles: dict[tuple[int, int], int] = {}
        self.pocket_at: dict[tuple[int, int], int] = {}
        self.pockets: dict[int, Pocket] = {}
        self.revealed: set[tuple[int, int]] = set()
        self.rigs: list[Rig] = []
        self.trucks: list[Truck] = [Truck(x=1.0)]
        self.prices = {"L": 3.0, "R": 3.0}
        self.trend = {"L": 3.0, "R": 3.0}
        self.history = {"L": [3.0] * 60, "R": [3.0] * 60}
        self.sold = 0.0                            # barrels, all time
        self.earned = 0                            # $, all time
        self.clock = 0.0
        self._hist_t = 0.0
        self.made: set[int] = set()                # every pocket the land started with
        self.events: list[tuple] = []
        self.rng = random.Random(seed * 31 + 7)
        self.generated = 0
        self._generate_to(self.plots + 1)          # the next plot shows (locked) past the fence

    # ---------------------------------------------------------------- money

    @property
    def cash(self) -> int:
        return self.wallet.cash if self.wallet is not None else 0

    def _spend(self, price: int) -> None:
        if self.wallet is None or self.cash < price:
            raise OilError(f"You need ${price - self.cash:,} more.")
        self.wallet.cash -= price

    def _refund(self, amount: int) -> None:
        if amount > 0 and self.wallet is not None:
            self.wallet.cash += amount

    def stat(self, name: str):
        return OIL_UPGRADES[name][0][self.levels[name]]

    # ---------------------------------------------------------------- the land

    @property
    def width(self) -> int:
        return self.plots * PLOT

    def owned(self, col: int) -> bool:
        return 0 <= col < self.width

    def tile(self, col: int, row: int) -> int:
        return self.tiles.get((col, row), DIRT)

    def _generate_to(self, plots: int) -> None:
        while self.generated < plots:
            self._generate_plot(self.generated)
            self.generated += 1

    def _generate_plot(self, p: int) -> None:
        """Each plot is made from the seed and its number, so it's the same whenever it's made. Further right
        means more oil, deeper down."""
        rng = random.Random(self.seed * 7_777 + p * 131)
        x0 = p * PLOT
        rich = 1 + 0.18 * p
        for c in range(x0, x0 + PLOT):
            for r in range(1, ROWS):
                if rng.random() < 0.05 + 0.006 * r + min(0.06, 0.004 * p):
                    self.tiles[(c, r)] = ROCK

        def blob(kind, size, lo, hi):
            c = rng.randrange(x0, x0 + PLOT)
            r = rng.randrange(lo, hi)
            cells = []
            for _ in range(size * 3):
                if len(cells) >= size:
                    break
                if x0 <= c < x0 + PLOT and 2 <= r < ROWS and (c, r) not in self.pocket_at and (c, r) not in cells:
                    cells.append((c, r))
                c += rng.choice((-1, 0, 1))
                r += rng.choice((-1, 0, 0, 1))
                c = max(x0, min(x0 + PLOT - 1, c))
                r = max(2, min(ROWS - 1, r))
            return cells

        n = 0
        for _ in range(rng.randint(2, 3)):                      # oil
            size = rng.randint(5, 14) + p // 2
            cells = blob(OIL, size, 4, ROWS - 1)
            if len(cells) < 3:
                continue
            depth = sum(r for _, r in cells) / len(cells) / ROWS
            amount = round(sum(rng.uniform(70, 130) for _ in cells) * rich * (0.8 + depth))
            self._add_pocket(p * 100 + n, OIL, cells, amount)
            n += 1
        for _ in range(rng.randint(0, 2)):                      # gas
            cells = blob(GAS, rng.randint(2, 5), 3, ROWS - 1)
            if cells:
                self._add_pocket(p * 100 + n, GAS, cells, 0)
                n += 1

    def _add_pocket(self, pid: int, kind: int, cells: list, amount: float) -> None:
        self.pockets[pid] = Pocket(pid, kind, cells, amount, amount)
        self.made.add(pid)
        for cell in cells:
            self.tiles[cell] = kind
            self.pocket_at[cell] = pid

    def land_price(self) -> int:
        return int(LAND_PRICE * 1.4 ** (self.plots - START_PLOTS))

    def buy_land(self) -> None:
        self._spend(self.land_price())
        self.plots += 1
        self._generate_to(self.plots + 1)
        for t in self.trucks:                       # (the right-hand buyer moved along: nobody drives into it)
            t.x = min(t.x, self.width + 0.5)
        self.events.append(("land", self.plots))

    # ---------------------------------------------------------------- scanning

    def scan(self, col: int, row: int) -> None:
        if not self.owned(col) or not 0 <= row < ROWS:
            raise OilError("Scan your own land (buy more to the right).")
        self._spend(SCAN_PRICE)
        found = 0
        for c in range(col - SCAN_RADIUS, col + SCAN_RADIUS + 1):
            for r in range(row - SCAN_RADIUS, row + SCAN_RADIUS + 1):
                if self.owned(c) and 0 <= r < ROWS and (c - col) ** 2 + (r - row) ** 2 <= SCAN_RADIUS ** 2 + 1:
                    if (c, r) not in self.revealed:
                        self.revealed.add((c, r))
                        found += self.tile(c, r) == OIL
        self.events.append(("scan", col, row, found))

    # ---------------------------------------------------------------- rigs and pipes

    def rig_price(self) -> int:
        return RIG_PRICE + RIG_STEP * len(self.rigs)

    def rig_at(self, col: int) -> int | None:
        for i, rig in enumerate(self.rigs):
            if rig.col == col:
                return i
        return None

    def place_rig(self, col: int) -> int:
        if not self.owned(col):
            raise OilError("You can only build on land you own.")
        if any(abs(r.col - col) < 2 for r in self.rigs):
            raise OilError("Too close to another rig.")
        if (col, 0) in self.pipe_owner():
            raise OilError("There's a pipe in the way.")
        if self.tile(col, 0) == ROCK and not self.stat("ROCK BIT"):
            raise OilError("Rock right under the surface here.")
        self._spend(self.rig_price())
        self.rigs.append(Rig(col))
        self.rigs[-1].queue = [(col, 0)]            # the first bit of pipe goes in by itself
        self.events.append(("rig", col))
        return len(self.rigs) - 1

    def pipe_owner(self) -> dict[tuple[int, int], int]:
        out = {}
        for i, rig in enumerate(self.rigs):
            for cell in rig.pipe + rig.queue:
                out[cell] = i
        return out

    def _blocked(self, cell, owners, me: int) -> bool:
        c, r = cell
        if not self.owned(c) or not 0 <= r < ROWS:
            return True
        if owners.get(cell, me) != me:
            return True
        known_rock = cell in self.revealed and self.tile(c, r) == ROCK
        return known_rock and not self.stat("ROCK BIT")

    def plan_pipe(self, col: int, row: int, rig: int | None = None) -> tuple[int, list] | None:
        """The shortest new pipe to this cell from that rig's pipe (or any rig's), around rock you know about.
        Returns (rig index, cells to drill) or None."""
        owners = self.pipe_owner()
        if (col, row) in owners or not self.owned(col) or not 0 <= row < ROWS:
            return None
        best = None
        for i, r in enumerate(self.rigs):
            ends = r.pipe + r.queue
            if not ends or (rig is not None and i != rig):
                continue
            prev = {cell: None for cell in ends}
            todo = deque(ends)
            while todo:
                cell = todo.popleft()
                if cell == (col, row):
                    break
                c, r = cell
                for nxt in ((c, r + 1), (c - 1, r), (c + 1, r), (c, r - 1)):
                    if nxt not in prev and not self._blocked(nxt, owners, i):
                        prev[nxt] = cell
                        todo.append(nxt)
            if (col, row) not in prev:
                continue
            path = []
            cell = (col, row)
            while prev[cell] is not None:
                path.append(cell)
                cell = prev[cell]
            path.reverse()
            if path and (best is None or len(path) < len(best[1])):
                best = (i, path)
        return best

    def lay_pipe(self, col: int, row: int, rig: int | None = None) -> int:
        """Pay for and start drilling a pipe to this cell. Returns how many cells long it is."""
        plan = self.plan_pipe(col, row, rig)
        if plan is None:
            if not self.rigs:
                raise OilError("Build a rig first.")
            raise OilError("No way to pipe there.")
        i, path = plan
        cost = PIPE_PRICE * len(path)
        self._spend(cost)
        rig = self.rigs[i]
        rig.queue += path
        rig.paid += cost
        self.events.append(("pipe", i, len(path)))
        return len(path)

    def _cut_queue(self, rig: Rig, why: str, i: int) -> None:
        refund = PIPE_PRICE * len(rig.queue)
        refund = min(refund, rig.paid)
        self._refund(refund)
        rig.paid -= refund
        rig.queue = []
        rig.dig = 0.0
        self.events.append(("stopped", i, why, refund))

    def _dig(self, i: int, rig: Rig, dt: float) -> None:
        if not rig.queue:
            return
        rig.dig += dt * self.stat("DRILL BITS")
        while rig.dig >= 1.0 and rig.queue:
            rig.dig -= 1.0
            cell = rig.queue[0]
            t = self.tile(*cell)
            self.revealed.add(cell)
            if t == ROCK and not self.stat("ROCK BIT"):
                self._cut_queue(rig, "rock", i)
                return
            rig.queue.pop(0)
            rig.paid = max(0, rig.paid - PIPE_PRICE)
            if t == GAS:                     # boom: the gas goes, and so does the tip of the pipe
                pid = self.pocket_at.get(cell)
                pocket = self.pockets.pop(pid, None)
                for gcell in (pocket.cells if pocket else [cell]):
                    self.tiles.pop(gcell, None)
                    self.pocket_at.pop(gcell, None)
                    self.revealed.add(gcell)
                lost = rig.pipe[-2:] if len(rig.pipe) > 1 else []
                rig.pipe = rig.pipe[:len(rig.pipe) - len(lost)]
                self._cut_queue(rig, "gas", i)
                self.events.append(("boom", cell))
                return
            new = t == OIL and self.pockets[self.pocket_at[cell]] not in self.rig_pockets(rig)
            rig.pipe.append(cell)
            if new:
                pid = self.pocket_at[cell]
                self.events.append(("strike", i, pid))
                for ocell in self.pockets[pid].cells:      # striking oil shows the whole pocket
                    self.revealed.add(ocell)

    def rig_pockets(self, rig: Rig) -> list[Pocket]:
        seen, out = set(), []
        for cell in rig.pipe:
            pid = self.pocket_at.get(cell)
            if pid is not None and pid not in seen and self.pockets[pid].kind == OIL:
                seen.add(pid)
                out.append(self.pockets[pid])
        return out

    def _pump(self, i: int, rig: Rig, dt: float) -> None:
        room = self.stat("TANKS") - rig.tank
        if room <= 0:
            return
        live = [p for p in self.rig_pockets(rig) if p.amount > 0]
        if not live:
            return
        want = min(room, self.stat("PUMPS") * dt)
        each = want / len(live)
        for p in live:
            take = min(each, p.amount)
            p.amount -= take
            rig.tank += take
            if p.amount <= 1e-6:
                p.amount = 0.0
                self.events.append(("dry", i, p.id))

    # ---------------------------------------------------------------- trucks and buyers

    def truck_price(self) -> int:
        return int(TRUCK_PRICE * 1.5 ** (len(self.trucks) - 1))

    def buy_truck(self) -> None:
        if len(self.trucks) >= MAX_TRUCKS:
            raise OilError(f"That's the most trucks the road can take ({MAX_TRUCKS}).")
        self._spend(self.truck_price())
        self.trucks.append(Truck(x=0.5, auto=bool(self.stat("DISPATCHER"))))
        self.events.append(("truck", len(self.trucks)))

    def buyer_x(self, side: str) -> float:
        return -BUYER_W / 2 if side == "L" else self.width + BUYER_W / 2

    def send(self, t: int, goal: tuple) -> None:
        """Send a truck to a rig (("rig", i)) or a buyer (("buyer", "L"/"R")). Doing it by hand stops autopilot."""
        truck = self.trucks[t]
        if goal[0] == "rig" and not 0 <= goal[1] < len(self.rigs):
            raise OilError("No such rig.")
        truck.goal = goal
        truck.auto = False

    def set_auto(self, t: int, on: bool) -> None:
        if on and not self.stat("DISPATCHER"):
            raise OilError("Buy the DISPATCHER upgrade and trucks can drive themselves.")
        self.trucks[t].auto = on
        if on:
            self.trucks[t].goal = None

    def _goal_x(self, goal: tuple) -> float:
        if goal[0] == "rig":
            return self.rigs[goal[1]].col + 0.5
        return self.buyer_x(goal[1])

    def pumping(self, rig: Rig) -> bool:
        return any(p.amount > 0 for p in self.rig_pockets(rig))

    def _dispatch(self, t: int, truck: Truck) -> None:
        """Autopilot: sell when (nearly) full or nothing's left to fetch; otherwise go to the rig with the most
        oil waiting (a rig that's still pumping counts for a bit more), one truck per rig."""
        cap = self.stat("TRUCK SIZE")
        taken = {tr.goal[1] for k, tr in enumerate(self.trucks) if k != t and tr.goal and tr.goal[0] == "rig"}
        rigs = [(rig.tank + (cap / 4 if self.pumping(rig) else 0), i) for i, rig in enumerate(self.rigs)
                if (rig.tank > 10 or self.pumping(rig)) and i not in taken]
        if truck.load >= cap * 0.8 or (truck.load > 0 and not rigs):
            speed = self.stat("TRUCK SPEED")
            # The better buyer, after a little for the time it takes to drive there.
            truck.goal = ("buyer", max(BUYERS, key=lambda s: self.prices[s] - 0.02 * abs(self.buyer_x(s) - truck.x)
                                       / speed))
        elif rigs:
            truck.goal = ("rig", max(rigs)[1])

    def _drive(self, t: int, truck: Truck, dt: float) -> None:
        if truck.auto and self.stat("DISPATCHER") and truck.goal is None:
            self._dispatch(t, truck)
        if truck.goal is None:
            return
        gx = self._goal_x(truck.goal)
        step = self.stat("TRUCK SPEED") * dt
        if abs(gx - truck.x) > step:
            truck.x += step if gx > truck.x else -step
            return
        truck.x = gx
        cap = self.stat("TRUCK SIZE")
        if truck.goal[0] == "rig":
            rig = self.rigs[truck.goal[1]]
            move = min(LOAD_RATE * dt, rig.tank, cap - truck.load)
            rig.tank -= move
            truck.load += move
            if truck.load >= cap - 1e-6:
                truck.goal = None              # full: off to sell
            elif truck.auto and rig.tank <= 1e-6 and (truck.load >= cap * 0.8 or not self.pumping(rig)):
                truck.goal = None              # nearly full, or this rig's run dry: what next?
        else:
            side = truck.goal[1]
            move = min(LOAD_RATE * dt, truck.load)
            if move > 0:
                truck.earning += self._sell(side, move)
                truck.load -= move
            if truck.load <= 1e-6:                 # unloaded: paid for the whole delivery at once
                truck.load = 0.0
                truck.goal = None
                self._pay(t, truck)

    def _sell(self, side: str, barrels: float) -> float:
        """Oil into a buyer's tanks. Returns what it's worth; flooding a buyer drops its price."""
        total = barrels * self.prices[side]
        self.prices[side] = max(0.5, self.prices[side] - barrels * 0.0006)
        self.sold += barrels
        return total

    def _pay(self, t: int, truck: Truck) -> None:
        whole = int(round(truck.earning))
        truck.earning = 0.0
        if whole > 0:
            self.earned += whole
            side = "L" if truck.x < self.width / 2 else "R"
            self.events.append(("sell", whole, side, t))

    def _market(self, dt: float) -> None:
        """Prices wander toward a target that drifts slowly, so there's always a better time and side to sell."""
        for k, side in enumerate(BUYERS):
            wave = 3.2 + 1.6 * math.sin(self.clock / (70 + 25 * k) + k * 2.1) + 0.6 * math.sin(self.clock / 23 + k)
            self.trend[side] += (wave - self.trend[side]) * min(1.0, 0.2 * dt) + self.rng.gauss(0, 0.25) * dt
            self.prices[side] += (self.trend[side] - self.prices[side]) * min(1.0, 0.15 * dt)
            self.prices[side] = max(0.5, min(8.0, self.prices[side]))
        self._hist_t += dt
        if self._hist_t >= 1.0:
            self._hist_t = 0.0
            for side in BUYERS:
                self.history[side] = self.history[side][1:] + [round(self.prices[side], 3)]

    # ---------------------------------------------------------------- time

    def step(self, dt: float) -> None:
        dt = max(0.0, min(dt, 0.25))
        while dt > 1e-9:
            part = min(dt, 1 / 20)
            self.clock += part
            self._market(part)
            for i, rig in enumerate(self.rigs):
                self._dig(i, rig, part)
                self._pump(i, rig, part)
            for t, truck in enumerate(self.trucks):
                self._drive(t, truck, part)
            dt -= part

    def pop_events(self) -> list[tuple]:
        ev, self.events = self.events, []
        return ev

    # ---------------------------------------------------------------- upgrades

    def upgrade_price(self, name: str) -> int | None:
        lvl = self.levels[name]
        prices = OIL_UPGRADES[name][1]
        return prices[lvl + 1] if lvl + 1 < len(prices) else None

    def buy_upgrade(self, name: str) -> None:
        price = self.upgrade_price(name)
        if price is None:
            raise OilError("That's as good as it gets.")
        self._spend(price)
        self.levels[name] += 1
        if name == "DISPATCHER":
            for truck in self.trucks:
                truck.auto = True
        self.events.append(("upgrade", name, self.levels[name]))

    # ---------------------------------------------------------------- saving

    def to_dict(self) -> dict:
        return {
            "seed": self.seed, "plots": self.plots, "levels": self.levels,
            "revealed": sorted([c, r] for c, r in self.revealed),
            "pockets": {str(pid): round(p.amount, 2) for pid, p in self.pockets.items() if p.kind == OIL},
            "gone": sorted(self.made - set(self.pockets)),
            "rigs": [{"col": r.col, "pipe": r.pipe, "queue": r.queue, "tank": round(r.tank, 2), "paid": r.paid}
                     for r in self.rigs],
            "trucks": [{"x": round(t.x, 3), "load": round(t.load, 2), "auto": t.auto, "earning": round(t.earning, 2),
                        "goal": list(t.goal) if t.goal else None} for t in self.trucks],
            "prices": self.prices, "sold": round(self.sold, 2), "earned": self.earned, "clock": round(self.clock, 2),
        }

    @classmethod
    def from_dict(cls, d: dict, wallet=None) -> "OilField":
        """Load a saved field (anything broken falls back to something safe)."""
        f = cls(int(d.get("seed", 1)), wallet)
        plots = d.get("plots", START_PLOTS)
        f.plots = max(START_PLOTS, min(500, plots)) if isinstance(plots, int) else START_PLOTS
        f._generate_to(f.plots + 1)
        for name in OIL_UPGRADES:
            lvl = d.get("levels", {}).get(name, 0) if isinstance(d.get("levels"), dict) else 0
            f.levels[name] = lvl if isinstance(lvl, int) and 0 <= lvl < len(OIL_UPGRADES[name][0]) else 0

        def cell(x):
            if isinstance(x, (list, tuple)) and len(x) == 2 and all(isinstance(v, int) for v in x):
                if f.owned(x[0]) and 0 <= x[1] < ROWS:
                    return (x[0], x[1])
            return None

        f.revealed = {c for c in map(cell, d.get("revealed") or []) if c}
        for pid in d.get("gone") or []:
            pocket = f.pockets.pop(pid, None) if isinstance(pid, int) else None
            for gcell in (pocket.cells if pocket else []):
                f.tiles.pop(gcell, None)
                f.pocket_at.pop(gcell, None)
        for key, amount in (d.get("pockets") or {}).items():
            try:
                pid = int(key)
            except ValueError:
                continue
            if pid in f.pockets and isinstance(amount, (int, float)):
                f.pockets[pid].amount = max(0.0, min(f.pockets[pid].start, float(amount)))
        taken: set = set()
        for r in d.get("rigs") or []:
            if not isinstance(r, dict) or not isinstance(r.get("col"), int) or not f.owned(r["col"]):
                continue
            if any(abs(o.col - r["col"]) < 2 for o in f.rigs):
                continue
            rig = Rig(r["col"])
            for name in ("pipe", "queue"):
                cells = [c for c in map(cell, r.get(name) or []) if c and c not in taken]
                taken.update(cells)
                setattr(rig, name, cells)
            tank = r.get("tank", 0)
            rig.tank = max(0.0, min(f.stat("TANKS"), float(tank))) if isinstance(tank, (int, float)) else 0.0
            paid = r.get("paid", 0)
            rig.paid = max(0, int(paid)) if isinstance(paid, (int, float)) else 0
            f.rigs.append(rig)
        trucks = []
        for t in (d.get("trucks") or [])[:MAX_TRUCKS]:
            if not isinstance(t, dict):
                continue
            x, load = t.get("x", 0.5), t.get("load", 0)
            truck = Truck(x=max(-BUYER_W, min(f.width + BUYER_W, float(x))) if isinstance(x, (int, float)) else 0.5)
            truck.load = max(0.0, min(f.stat("TRUCK SIZE"), float(load))) if isinstance(load, (int, float)) else 0.0
            truck.auto = bool(t.get("auto", True))
            earning = t.get("earning", 0)
            truck.earning = max(0.0, min(1e9, float(earning))) if isinstance(earning, (int, float)) else 0.0
            goal = t.get("goal")
            if isinstance(goal, list) and len(goal) == 2:
                if goal[0] == "rig" and isinstance(goal[1], int) and 0 <= goal[1] < len(f.rigs):
                    truck.goal = ("rig", goal[1])
                elif goal[0] == "buyer" and goal[1] in BUYERS:
                    truck.goal = ("buyer", goal[1])
            trucks.append(truck)
        f.trucks = trucks or [Truck(x=1.0)]
        prices = d.get("prices") or {}
        for side in BUYERS:
            v = prices.get(side, 3.0) if isinstance(prices, dict) else 3.0
            f.prices[side] = f.trend[side] = max(0.5, min(8.0, float(v))) if isinstance(v, (int, float)) else 3.0
            f.history[side] = [f.prices[side]] * 60
        for key in ("sold", "clock"):
            v = d.get(key, 0)
            setattr(f, key, max(0.0, float(v)) if isinstance(v, (int, float)) else 0.0)
        earned = d.get("earned", 0)
        f.earned = max(0, int(earned)) if isinstance(earned, (int, float)) else 0
        return f
