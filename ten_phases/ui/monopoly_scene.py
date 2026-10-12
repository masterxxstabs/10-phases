"""The Monopoly table.

The rules engine moves instantly; this screen replays its events one at a time
as animations (dice tumbling, tokens hopping square by square, cards flipping,
coins flying, houses popping up). Nobody can act until the animations catch up,
so what you see is always what just happened.

  left    the board
  right   the players (with animated cash), then whatever you can do right now
"""

from __future__ import annotations

import math
import random

import pygame

from ..monopoly.ai import MonopolyAI
from ..monopoly.board import GO_SALARY, GROUPS, JAIL, JAIL_FINE, SETS, SQUARES
from ..monopoly.engine import MonopolyGame, MPlayer, RuleError
from ..names import pick_ai_names
from . import monopoly_art as art
from . import sfx, theme
from .admin import AdminPanel
from .game_scene import DIFF_COLORS
from .menus import Scene, status_bar
from .table_skins import TableSkins
from .widgets import Button

HUMAN = 0
PANEL = pygame.Rect(784, 10, 482, 756)
PLAYERS_BOX = pygame.Rect(784, 10, 482, 398)
ACTION_BOX = pygame.Rect(784, 418, 482, 348)
SPEED = {"Slow": 1.35, "Normal": 1.0, "Fast": 0.62}
CHIPS_PER = 50   # chips banked per £ of net worth
# Events that tell the story of a roll; the action panel waits for these to finish.
MOTION = {"turn", "roll", "move", "jail", "card", "land", "offer", "rent", "pay", "debt", "again", "free", "stay",
          "speeding", "bankrupt"}


def _ink(color) -> tuple:
    """A theme colour darkened enough to read on the pale board."""
    r, g, b = color[:3]
    k = 0.55 if r + g + b > 330 else 0.8
    return int(r * k), int(g * k), int(b * k)


def _fit(text: str, font, width: int) -> str:
    """Trim text with an ellipsis until it fits."""
    if font.size(text)[0] <= width:
        return text
    while text and font.size(text + "...")[0] > width:
        text = text[:-1]
    return text.rstrip() + "..."


def ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


class Anim:
    def __init__(self, ev, dur: float):
        self.ev, self.dur, self.t = ev, dur, 0.0
        self.data: dict = {}

    @property
    def k(self) -> float:
        return min(1.0, self.t / self.dur) if self.dur > 0 else 1.0


class Floater:
    def __init__(self, text, pos, color, size=22, ttl=1.3, vy=-38):
        self.text, self.pos, self.color, self.size, self.ttl, self.vy = text, list(pos), color, size, ttl, vy
        self.max_ttl = ttl


class Spark:
    """A bit of glitter (or confetti) thrown out when something good happens."""

    def __init__(self, pos, vel, color, size, ttl, grav=420, confetti=False):
        self.x, self.y = pos
        self.vx, self.vy = vel
        self.color, self.size, self.ttl, self.max_ttl = color, size, ttl, ttl
        self.grav, self.confetti = grav, confetti
        self.spin = random.uniform(0, 360)


class Coin:
    def __init__(self, start, end, delay, dur=0.55):
        self.start, self.end, self.t, self.dur = start, end, -delay, dur


class MonopolyScene(Scene):
    """Local by default; pass `host` + `session` to host a network game, or `client` to join one."""

    def __init__(self, app, host=None, session=None, client=None, max_rounds: int | None = None):
        super().__init__(app)
        s = app.settings
        self.host, self.session, self.client = host, session, client
        if session is not None:
            self.game, self.ais = session.game, session.ais
        elif client is not None:
            self.game, self.ais = client.game, {}
        else:
            diffs = s.opponent_difficulties()
            names = pick_ai_names(len(diffs), taken=["YOU", s.player_name])
            players = [MPlayer("YOU", is_human=True, token=s.monopoly_token)]
            players += [MPlayer(n, difficulty=d) for n, d in zip(names, diffs)]
            rounds = max_rounds if max_rounds is not None else s.monopoly_rounds
            self.game = MonopolyGame(players, max_rounds=rounds)
            self.ais = {i + 1: MonopolyAI(d) for i, d in enumerate(diffs)}
        self.skins = TableSkins(self)
        self.admin = AdminPanel(self)
        self.speed = SPEED.get(s.ai_speed, 1.0)
        self.rng = random.Random()
        g = self.game
        n = len(g.players)
        # What's on screen (catches up with the engine as events play).
        self.vpos = [p.pos for p in g.players]
        self.vjail = [p.in_jail for p in g.players]
        self.vcash = [float(p.cash) for p in g.players]
        self.tcash = [p.cash for p in g.players]
        self.vowner = list(g.owner)
        self.vhouses = list(g.houses)
        self.vmort = list(g.mortgaged)
        self.vbankrupt = [p.bankrupt for p in g.players]
        self.cash_flash = [0.0] * n
        self.dice = list(g.last_roll) if any(g.last_roll) else [1, 1]
        self.dice_shown = False
        self.queue: list = []
        self.cur: Anim | None = None
        self.floaters: list[Floater] = []
        self.coins: list[Coin] = []
        self.sparks: list[Spark] = []
        self.banners: list[list] = []          # [text, color, ttl, total]
        self.pops: dict[int, float] = {}       # square -> time left on its "something changed" bounce
        self.log: list[tuple[str, tuple]] = []
        self.flash: tuple[str, float] | None = None
        self.overlay: str | None = None
        self._pending_overlay = False
        self._banked: int | None = None
        self.ai_timer = 0.6
        self.splash: tuple | None = ("MONOPOLY", f"{g.max_rounds} ROUNDS - RICHEST WINS" if g.max_rounds else
                                     "LAST ONE STANDING WINS", 1.8, 1.8)
        self.selected_sq: int | None = None    # a property you clicked to manage
        self.trade_ui: dict | None = None      # the trade window, when open
        self.confirm_bankrupt = 0.0
        self.overlay_buttons: list[Button] = []
        self.buttons: list[Button] = []
        self.manage_buttons: list[Button] = []
        self._button_cache: dict = {}
        self._consume_events()
        sfx.play("shuffle")

    # ================================================================== helpers

    @property
    def me(self) -> MPlayer:
        return self.game.players[HUMAN]

    @property
    def networked(self) -> bool:
        return self.host is not None or self.client is not None

    @property
    def animating(self) -> bool:
        return self.cur is not None or bool(self.queue)

    @property
    def flow_blocked(self) -> bool:
        if self.admin.blocking or self.animating or self.splash is not None:
            return True
        return self.overlay is not None and not (self.overlay == "pause" and self.networked)

    def settled(self) -> bool:
        """False while a roll, a move or a card is still playing out (so the panel doesn't give away the result)."""
        evs = ([self.cur.ev] if self.cur else []) + self.queue
        return not any(e.kind in MOTION for e in evs)

    def my_move(self) -> bool:
        return not self.animating and self.overlay is None and self.splash is None and \
            self.game.actor() == HUMAN and not getattr(self.game, "pending", False)

    def name(self, i) -> str:
        if i is None:
            return "THE BANK"
        return "YOU" if i == HUMAN else self.game.players[i].name

    def verb(self, i, word: str) -> str:
        """'owe' for YOU, 'owes' for anyone else."""
        return word if i == HUMAN else word + ("S" if word.isupper() else "s")

    def color(self, i: int):
        return art.TOKEN_COLORS.get(self.game.players[i].token, art.PLAYER_COLORS[i % 6])

    def say(self, text: str, color=theme.TEXT):
        self.log.append((text, color))
        self.log = self.log[-6:]

    def banner(self, text: str, color=theme.ACCENT, ttl: float = 1.4):
        self.banners = [b for b in self.banners if b[2] > 0.3][-1:]
        self.banners.append([text, color, ttl, ttl])

    def burst(self, pos, colors, n: int = 16, speed: float = 190):
        for _ in range(n):
            a = self.rng.uniform(0, 2 * math.pi)
            v = self.rng.uniform(0.35, 1.0) * speed
            self.sparks.append(Spark(pos, (math.cos(a) * v, math.sin(a) * v - speed * 0.45),
                                     self.rng.choice(colors), self.rng.uniform(3, 6), self.rng.uniform(0.5, 0.9)))

    def confetti(self, n: int = 3):
        colors = art.PLAYER_COLORS + [theme.ACCENT]
        for _ in range(n):
            self.sparks.append(Spark((self.rng.uniform(0, theme.WIDTH), -10),
                                     (self.rng.uniform(-40, 40), self.rng.uniform(60, 160)),
                                     self.rng.choice(colors), self.rng.uniform(5, 9), 4.0, 60, True))

    def error(self, msg: str):
        self.flash = (msg, 2.8)
        sfx.play("error")

    def row_rect(self, i: int) -> pygame.Rect:
        n = len(self.game.players)
        h = min(92, (PLAYERS_BOX.h - 8 - (n - 1) * 6) // n)
        return pygame.Rect(PLAYERS_BOX.x, PLAYERS_BOX.y + i * (h + 6), PLAYERS_BOX.w, h)

    def cash_pos(self, i: int | None) -> tuple[int, int]:
        if i is None:
            return art.INNER.center
        r = self.row_rect(i)
        return r.right - 70, r.y + 40

    def token_pos(self, i: int) -> tuple[float, float]:
        """Where player i's token is drawn right now (moving tokens follow their animation)."""
        a = self.cur
        if a and a.data.get("mover") == i and "xy" in a.data:
            return a.data["xy"]
        k = self.vpos[i]
        here = [j for j in range(len(self.game.players)) if not self.vbankrupt[j] and self.vpos[j] == k
                and not (a and a.data.get("mover") == j) and (k != JAIL or self.vjail[j] == self.vjail[i])]
        slot = here.index(i) if i in here else 0
        return art.spot(k, slot, len(here), jailed=k == JAIL and self.vjail[i])

    def sync_view(self):
        """Snap the screen to the engine (called whenever the animations run dry)."""
        g = self.game
        self.vpos = [p.pos for p in g.players]
        self.vjail = [p.in_jail for p in g.players]
        self.tcash = [p.cash for p in g.players]
        self.vowner, self.vhouses, self.vmort = list(g.owner), list(g.houses), list(g.mortgaged)
        self.vbankrupt = [p.bankrupt for p in g.players]

    # ================================================================== events -> animations

    def _consume_events(self):
        self.queue += self.game.pop_events()

    def _start(self, ev) -> Anim:
        k, i = ev.kind, ev.player
        sp = self.speed
        if k == "turn":
            a = Anim(ev, 0.45 * sp)
            self.dice_shown = False
            if i == HUMAN:
                self.banner("YOUR TURN!", theme.ACCENT, 1.2)
                sfx.play("turn")
            else:
                self.banner(f"{self.name(i)}'S TURN", self.color(i), 0.9)
            self.selected_sq = None
            return a
        if k == "roll":
            a = Anim(ev, 1.05 * sp)
            a.data["dice"] = ev.data.get("dice", [1, 1])
            a.data["spin"] = [self.rng.uniform(300, 700) * self.rng.choice((-1, 1)) for _ in range(2)]
            self.dice_shown = True
            sfx.play("shuffle")
            return a
        if k == "move":
            path = list(ev.data.get("path") or [ev.sq])
            how = ev.data.get("how", "walk")
            a = Anim(ev, 0)
            a.data.update(mover=i, path=path, how=how, start=self.vpos[i], hop=-1)
            if how == "jump":
                a.dur = 0.75 * sp
                a.data["from_xy"] = self.token_pos(i)
            else:
                hop = max(0.09, min(0.2, 2.6 / max(1, len(path)))) * sp
                a.dur = hop * len(path)
            if i is not None and 0 <= i < len(self.vjail):
                self.vjail[i] = False
            return a
        if k == "jail":
            a = Anim(ev, 0.85 * sp)
            a.data.update(mover=i, how="jail", from_xy=self.token_pos(i))
            self.banner("GO TO JAIL!", theme.DANGER, 1.4)
            sfx.play("skip")
            self.say(f"{self.name(i)} went to jail", theme.DANGER)
            return a
        if k == "pay":
            to = ev.data.get("to")
            a = Anim(ev, 0.55 * sp)
            src = self._money_point(i, ev)
            dst = self._money_point(to, ev, receiving=True)
            for n in range(min(7, 2 + ev.amount // 60)):
                self.coins.append(Coin(src, dst, n * 0.06 * sp, 0.5 * sp))
            for key, cash in (ev.data.get("cash") or {}).items():
                j = int(key)
                if 0 <= j < len(self.tcash):
                    self.tcash[j] = cash
                    self.cash_flash[j] = 0.8
            if i is not None:
                self.floaters.append(Floater(f"-£{ev.amount}", self.cash_pos(i), theme.DANGER, 22))
            if to is not None:
                self.floaters.append(Floater(f"+£{ev.amount}", self.cash_pos(to), theme.SUCCESS, 22))
            if ev.text == "passed GO":
                self.floaters.append(Floater(f"+£{GO_SALARY}", art.cell_rect(0).center, theme.SUCCESS, 26))
                self.burst(art.cell_rect(0).center, [theme.ACCENT, theme.SUCCESS, (255, 255, 255)], 18)
                self.say(f"{self.name(to)} passed GO: +£{GO_SALARY}", theme.SUCCESS)
            elif i is not None:
                self.say(f"{self.name(i)} paid £{ev.amount} ({ev.text})"
                         + (f" to {self.name(to)}" if to is not None else ""), theme.TEXT_DIM)
            else:
                self.say(f"{self.name(to)} got £{ev.amount} ({ev.text})", theme.TEXT_DIM)
            sfx.play("coin")
            return a
        if k == "rent":
            owner = ev.data.get("owner")
            self.pops[ev.sq] = 0.5
            self.floaters.append(Floater(f"RENT £{ev.amount}", art.cell_rect(ev.sq).center, theme.DANGER, 20, 1.6))
            self.say(f"{self.name(i)} {self.verb(i, 'owe')} {self.name(owner)} £{ev.amount} rent", theme.DANGER)
            return Anim(ev, 0.35 * sp)
        if k == "card":
            a = Anim(ev, 2.6 * sp)
            a.data["deck"] = ev.data.get("deck", "chance")
            sfx.play("flip")
            self.say(ev.text, theme.INFO)
            return a
        if k == "buy" or k == "auction_end":
            a = Anim(ev, 0.75 * sp)
            if i is not None:
                self.vowner[ev.sq] = i
                self.pops[ev.sq] = 0.6
                a.data["deed"] = True
                sfx.play("lay")
                col = SETS.get(SQUARES[ev.sq].group, theme.ACCENT)
                self.burst(art.cell_rect(ev.sq).center, [col, theme.ACCENT, (255, 255, 255)], 20)
                self.say(f"{self.name(i)} bought {SQUARES[ev.sq].name} for £{ev.amount}", theme.SUCCESS)
                if k == "auction_end":
                    self.banner(f"SOLD TO {self.name(i)}!", theme.SUCCESS, 1.6)
            else:
                self.banner("NO BIDS - IT STAYS WITH THE BANK", theme.TEXT_DIM, 1.4)
            return a
        if k == "auction":
            self.banner(f"AUCTION: {SQUARES[ev.sq].name.upper()}", theme.ACCENT, 1.6)
            self.say(f"{SQUARES[ev.sq].name} goes to auction", theme.ACCENT)
            sfx.play("phase")
            return Anim(ev, 0.6 * sp)
        if k == "bid":
            self.floaters.append(Floater(f"£{ev.amount}", self.cash_pos(i), theme.ACCENT, 24, 1.0))
            sfx.play("click")
            return Anim(ev, 0.3 * sp)
        if k == "bid_pass":
            self.floaters.append(Floater("PASS", self.cash_pos(i), theme.TEXT_DIM, 18, 0.9))
            return Anim(ev, 0.12 * sp)
        if k in ("build", "sell"):
            self.vhouses[ev.sq] = ev.data.get("houses", self.vhouses[ev.sq])
            self.tcash[i] = ev.data.get("cash", self.tcash[i])
            self.cash_flash[i] = 0.6
            self.pops[ev.sq] = 0.6
            if k == "build":
                self.burst(art.band_rect(ev.sq).center, [(40, 170, 70), (220, 30, 40), (255, 255, 255)],
                           22 if self.vhouses[ev.sq] == 5 else 12, 150)
            sign = "-" if k == "build" else "+"
            self.floaters.append(Floater(f"{sign}£{ev.amount}", self.cash_pos(i),
                                         theme.DANGER if k == "build" else theme.SUCCESS, 20))
            what = "a hotel" if self.vhouses[ev.sq] == 5 and k == "build" else "a house"
            self.say(f"{self.name(i)} {'built' if k == 'build' else 'sold'} {what} on {SQUARES[ev.sq].name}",
                     theme.SUCCESS if k == "build" else theme.TEXT_DIM)
            sfx.play("select" if k == "build" else "deselect")
            return Anim(ev, 0.32 * sp)
        if k in ("mortgage", "unmortgage"):
            self.vmort[ev.sq] = k == "mortgage"
            self.tcash[i] = ev.data.get("cash", self.tcash[i])
            self.cash_flash[i] = 0.6
            self.pops[ev.sq] = 0.6
            self.say(f"{self.name(i)} {k}d {SQUARES[ev.sq].name}", theme.TEXT_DIM)
            sfx.play("deselect" if k == "mortgage" else "select")
            return Anim(ev, 0.35 * sp)
        if k == "trade_offer":
            to = ev.data.get("to")
            self.banner(f"{self.name(i)} {self.verb(i, 'OFFER')} {self.name(to)} A DEAL", theme.INFO, 1.5)
            sfx.play("turn" if to == HUMAN else "click")
            return Anim(ev, 0.5 * sp)
        if k == "trade_done":
            d = ev.data
            if d.get("accepted"):
                for sq in d.get("give", []):
                    self.vowner[sq] = d.get("to")
                    self.pops[sq] = 0.6
                for sq in d.get("get", []):
                    self.vowner[sq] = d.get("from")
                    self.pops[sq] = 0.6
                for key, cash in (d.get("cash") or {}).items():
                    j = int(key)
                    if 0 <= j < len(self.tcash):
                        self.tcash[j] = cash
                        self.cash_flash[j] = 0.8
                self.banner("DEAL!", theme.SUCCESS, 1.3)
                self.burst(art.INNER.center, [theme.SUCCESS, theme.ACCENT, (255, 255, 255)], 30, 260)
                self.say(f"{self.name(d.get('from'))} and {self.name(d.get('to'))} made a deal", theme.SUCCESS)
                sfx.play("round_win")
            else:
                self.banner("NO DEAL" if not d.get("cancelled") else "OFFER WITHDRAWN", theme.TEXT_DIM, 1.1)
                sfx.play("deselect")
            return Anim(ev, 0.7 * sp)
        if k == "debt":
            self.banner(f"{self.name(i)} MUST RAISE £{ev.amount}", theme.DANGER, 1.6)
            sfx.play("error")
            return Anim(ev, 0.5 * sp)
        if k == "bankrupt":
            if i is not None and 0 <= i < len(self.vpos):
                self.burst(self.token_pos(i), [(90, 90, 100), (160, 160, 170), theme.DANGER], 24, 200)
                # Everything they owned goes to the creditor (or back to the bank); their token fades out.
                to = ev.data.get("to")
                for sq in range(40):
                    if self.vowner[sq] == i:
                        self.vowner[sq], self.vhouses[sq] = to, 0
                        self.vmort[sq] = self.vmort[sq] and to is not None
                        self.pops[sq] = 0.6
                for key, cash in (ev.data.get("cash") or {}).items():
                    j = int(key)
                    if 0 <= j < len(self.tcash):
                        self.tcash[j] = cash
                        self.cash_flash[j] = 0.8
                self.tcash[i] = 0
                self.vbankrupt[i] = True
            self.banner("YOU'RE BANKRUPT!" if i == HUMAN else f"{self.name(i)} IS BANKRUPT!", theme.DANGER, 2.0)
            self.say(f"{self.name(i)} went bankrupt", theme.DANGER)
            sfx.play("game_lose")
            return Anim(ev, 1.3 * sp)
        if k == "free":
            self.vjail[i] = False
            self.banner("OUT OF JAIL!", theme.SUCCESS, 1.0)
            self.say(f"{self.name(i)}: {ev.text}", theme.SUCCESS)
            sfx.play("coin")
            return Anim(ev, 0.45 * sp)
        if k == "stay":
            self.banner("STILL IN JAIL", theme.TEXT_DIM, 1.0)
            return Anim(ev, 0.4 * sp)
        if k == "speeding":
            self.banner("THREE DOUBLES - SPEEDING!", theme.DANGER, 1.4)
            return Anim(ev, 0.5 * sp)
        if k == "again":
            self.banner("DOUBLES! ROLL AGAIN", theme.ACCENT, 1.2)
            sfx.play("phase")
            return Anim(ev, 0.45 * sp)
        if k == "land":
            self.pops[ev.sq] = 0.35
            return Anim(ev, 0.1 * sp)
        if k == "offer":
            return Anim(ev, 0.25 * sp)
        if k == "game_over":
            self._pending_overlay = True
            return Anim(ev, 0.3)
        return Anim(ev, 0.05)

    def _money_point(self, i, ev, receiving=False):
        if i is None:
            return art.cell_rect(0).center if ev.text == "passed GO" else art.INNER.center
        if not receiving:
            return self.token_pos(i)
        return self.cash_pos(i)

    def _tick(self, a: Anim):
        ev = a.ev
        if ev.kind == "move":
            path, how, i = a.data["path"], a.data["how"], a.data["mover"]
            if how == "jump":
                start = a.data["from_xy"]
                end = art.spot(path[-1])
                k = ease_in_out(a.k)
                x = start[0] + (end[0] - start[0]) * k
                y = start[1] + (end[1] - start[1]) * k - 140 * math.sin(math.pi * a.k)
                a.data["xy"] = (x, y)
                a.data["scale"] = 1 + 0.6 * math.sin(math.pi * a.k)
                return
            steps = len(path)
            p = a.k * steps
            h = min(steps - 1, int(p))
            frac = p - h
            prev = a.data["start"] if h == 0 else path[h - 1]
            x1, y1 = art.spot(prev)
            x2, y2 = art.spot(path[h])
            e = ease_in_out(frac)
            a.data["xy"] = (x1 + (x2 - x1) * e, y1 + (y2 - y1) * e - 22 * math.sin(math.pi * frac))
            a.data["scale"] = 1 + 0.12 * math.sin(math.pi * frac)
            if h != a.data["hop"]:
                if a.data["hop"] >= 0:
                    sfx.play("select")
                    self.pops[path[a.data["hop"]]] = 0.18
                a.data["hop"] = h
        elif ev.kind == "jail":
            i = a.data["mover"]
            start = a.data["from_xy"]
            end = art.spot(JAIL, 0, 1, jailed=True)
            k = ease_in_out(a.k)
            a.data["xy"] = (start[0] + (end[0] - start[0]) * k, start[1] + (end[1] - start[1]) * k
                            - 160 * math.sin(math.pi * a.k))
            a.data["scale"] = 1 + 0.5 * math.sin(math.pi * a.k)
            a.data["spin"] = 720 * a.k
            if i is not None:
                self.vjail[i] = True

    def _finish(self, a: Anim):
        ev = a.ev
        if ev.kind == "move":
            i = a.data["mover"]
            self.vpos[i] = a.data["path"][-1]
            sfx.play("lay" if a.data["how"] == "jump" else "draw")
        elif ev.kind == "jail":
            i = a.data["mover"]
            self.vpos[i], self.vjail[i] = JAIL, True
            sfx.play("discard")
        elif ev.kind == "roll":
            self.dice = list(a.data["dice"])
            d = self.dice
            self.floaters.append(Floater(str(sum(d)), (art.INNER.centerx, art.INNER.centery - 60), theme.ACCENT, 34, 1.0))
            if d[0] == d[1]:
                self.burst((art.INNER.centerx, art.INNER.centery + 10), [theme.ACCENT, (255, 255, 255)], 18, 220)
                self.floaters.append(Floater("DOUBLES!", (art.INNER.centerx, art.INNER.centery - 100), theme.ACCENT,
                                             28, 1.2))
            sfx.play("draw")
            self.say(f"{self.name(ev.player)} rolled {d[0]} + {d[1]} = {sum(d)}", theme.TEXT)

    # ================================================================== actions (yours)

    def act(self, action: str, **kw):
        if not self.my_move() and action not in ("build", "sell", "mortgage", "unmortgage"):
            return
        try:
            self.game.act(HUMAN, action, **kw)
        except RuleError as e:
            self.error(str(e))
            return
        if action in ("roll", "end", "buy", "auction", "pay", "jail_pay", "jail_card", "pay_fine", "take_chance"):
            self.selected_sq = None
        self._consume_events()
        self.ai_timer = 0.35 * self.speed

    def primary(self):
        legal = self.game.legal(HUMAN) if self.my_move() else []
        for action in ("roll", "pay", "buy", "end", "accept"):
            if action in legal:
                self.act(action)
                return

    def run_ai(self, dt: float):
        g = self.game
        who = g.actor()
        if who is None or who not in self.ais:
            return
        self.ai_timer -= dt
        if self.ai_timer > 0:
            return
        action, kw = self.ais[who].choose(g, who)
        try:
            g.act(who, action, **kw)
        except RuleError:
            # Should never happen; never let a computer jam the table.
            legal = g.legal(who)
            for fallback in ("pass", "end", "roll", "auction", "take_chance", "decline", "bankrupt"):
                if fallback in legal:
                    g.act(who, fallback)
                    break
        self._consume_events()
        pace = 0.55 if action in ("build", "sell", "mortgage", "unmortgage", "bid", "pass") else 0.8
        self.ai_timer = pace * self.speed

    # ================================================================== network

    def _pump_network(self):
        if self.host is not None:
            self.host.pump()
            while self.session.notices:
                self.banner(self.session.notices.pop(0).upper(), theme.DANGER, 2.0)
                sfx.play("skip")
        if self.client is not None:
            for msg in self.client.poll():
                t = msg["t"]
                if t == "error":
                    self.error(msg.get("msg", "That move wasn't allowed."))
                elif t == "notice":
                    self.banner(msg.get("msg", "").upper(), theme.DANGER, 2.0)
                    sfx.play("skip")
                elif t == "to_lobby":
                    self.client.game = None
                    from .multiplayer import GuestLobbyScene
                    self.app.go(GuestLobbyScene(self.app, self.client))
                    return
            if self.client.status in ("closed", "failed") and self.overlay != "disconnected":
                self._set_overlay("disconnected")

    def leave_network(self):
        if self.host is not None:
            self.host.close()
        if self.client is not None:
            self.client.leave()

    def to_lobby(self):
        from .multiplayer import HostLobbyScene
        self.host.back_to_lobby()
        self.app.go(HostLobbyScene(self.app, self.host))

    # ================================================================== overlays

    def _set_overlay(self, kind: str | None):
        self.overlay = kind
        if kind == "game":
            self._pending_overlay = False
        cx = theme.WIDTH // 2
        primary = dict(color="ACCENT", text_color="OUTLINE")
        restart = lambda: self.app.go(MonopolyScene(self.app))  # noqa: E731
        if kind == "game":
            sfx.play("game_win" if HUMAN in self.game.winners() else "game_lose")
            if self._banked is None:
                self._banked = max(0, self.game.net_worth(HUMAN)) // CHIPS_PER
                self.app.settings.chip_bank += self._banked
                self.app.settings.save()
            if self.host is not None:
                again = Button((cx - 290, 680, 270, 58), "BACK TO LOBBY", self.to_lobby, size=20, **primary)
            elif self.client is not None:
                again = Button((cx - 290, 680, 270, 58), "WAIT FOR HOST", lambda: None, size=18)
                again.enabled = False
            else:
                again = Button((cx - 290, 680, 270, 58), "PLAY AGAIN", restart, size=22, **primary)
            self.overlay_buttons = [again, Button((cx + 20, 680, 270, 58), "MAIN MENU", self.to_menu, size=22)]
        elif kind == "disconnected":
            sfx.play("error")
            self.overlay_buttons = [Button((cx - 140, 470, 280, 58), "MAIN MENU", self.to_menu, size=22, **primary)]
        elif kind == "pause":
            resume = lambda: self._set_overlay(None)  # noqa: E731
            if self.host is not None:
                options = [("RESUME", resume), ("END GAME", self.to_menu)]
            elif self.client is not None:
                options = [("RESUME", resume), ("LEAVE GAME", self.to_menu)]
            else:
                options = [("RESUME", resume), ("RESTART", restart), ("MAIN MENU", self.to_menu)]
            self.overlay_buttons = [Button((cx - 140, 300 + k * 68, 280, 56), label, fn, size=22 if k == 0 else 20,
                                           **(primary if k == 0 else {})) for k, (label, fn) in enumerate(options)]
        else:
            self.overlay_buttons = []

    def to_menu(self):
        self.leave_network()
        from .menus import MenuScene
        self.app.go(MenuScene(self.app))

    # ================================================================== the action panel (buttons)

    def _button(self, key, rect, label, fn, primary=False, size=18, color=None):
        b = self._button_cache.get(key)
        if b is None:
            b = self._button_cache[key] = Button(rect, label, fn, size=size)
        b.rect = pygame.Rect(rect)
        b.label, b.on_click, b.size = label, fn, size
        b.color, b.text_color = ("ACCENT", "OUTLINE") if primary else (color or "PANEL_LIGHT", "TEXT")
        b.enabled = True
        b.visible = True
        return b

    def build_buttons(self) -> list[Button]:
        """The buttons for whatever you can do right now (rebuilt every frame from the rules)."""
        g = self.game
        out: list[Button] = []
        x, y, w = ACTION_BOX.x + 20, ACTION_BOX.y + 70, ACTION_BOX.w - 40
        if self.overlay or self.splash:
            return out
        out.append(self._button("menu", (ACTION_BOX.right - 108, ACTION_BOX.bottom - 52, 92, 40), "MENU",
                                lambda: self._set_overlay("pause"), size=14))
        if self.trade_ui:
            return out
        self.manage_buttons = self._manage_buttons()
        if not self.settled():
            return out
        legal = g.legal(HUMAN) if self.my_move() else []
        busy = not self.my_move()
        if g.trade and g.trade.get("to") == HUMAN:
            out.append(self._button("accept", (x, y + 140, w // 2 - 6, 50), "ACCEPT", lambda: self.act("accept"), True))
            out.append(self._button("decline", (x + w // 2 + 6, y + 140, w // 2 - 6, 50), "DECLINE",
                                    lambda: self.act("decline")))
        elif g.trade and g.trade.get("from") == HUMAN:
            out.append(self._button("cancel", (x, y + 140, w, 50), "WITHDRAW OFFER", lambda: self.act("cancel_trade")))
        elif g.phase == "auction" and g.auction:
            high = g.auction["high"]
            for n, inc in enumerate((1, 10, 50, 100)):
                amount = high + inc
                b = self._button(f"bid{inc}", (x + n * (w // 4), y + 112, w // 4 - 8, 48), f"£{amount}",
                                 lambda a=amount: self.act("bid", amount=a), n == 1, 16)
                b.enabled = "bid" in legal and self.me.cash >= amount
                out.append(b)
            b = self._button("pass", (x, y + 168, w - 8, 44), "PASS", lambda: self.act("pass"), size=16)
            b.enabled = "pass" in legal
            out.append(b)
        elif g.phase == "debt" and g.debt and g.debt.get("debtor") == HUMAN:
            amount = g.debt["amount"]
            b = self._button("pay", (x, y + 120, w, 52), f"PAY £{amount}", lambda: self.act("pay"), True, 20)
            b.enabled = "pay" in legal
            out.append(b)
            t = self._button("trade", (x, y + 180, w // 2 - 6, 44), "TRADE", self.open_trade, size=15)
            t.enabled = "trade" in legal
            out.append(t)
            label = "REALLY? CLICK AGAIN" if self.confirm_bankrupt > 0 else "GO BANKRUPT"
            out.append(self._button("bankrupt", (x + w // 2 + 6, y + 180, w // 2 - 6, 44), label, self._bankrupt,
                                    size=13, color="DANGER"))
        elif g.current == HUMAN and g.phase == "buy":
            price = SQUARES[self.me.pos].price
            b = self._button("buy", (x, y + 150, w // 2 - 6, 56), f"BUY £{price}", lambda: self.act("buy"), True, 20)
            b.enabled = "buy" in legal
            out.append(b)
            out.append(self._button("auction", (x + w // 2 + 6, y + 150, w // 2 - 6, 56), "AUCTION",
                                    lambda: self.act("auction")))
            out[-1].enabled = "auction" in legal
        elif g.current == HUMAN and g.phase == "fine_or_chance":
            b = self._button("fine", (x, y + 140, w // 2 - 6, 52), "PAY £10", lambda: self.act("pay_fine"), True)
            b.enabled = "pay_fine" in legal
            out.append(b)
            out.append(self._button("chance", (x + w // 2 + 6, y + 140, w // 2 - 6, 52), "TAKE A CHANCE",
                                    lambda: self.act("take_chance"), size=15))
        elif g.current == HUMAN and g.phase in ("pre_roll", "post_roll"):
            if g.phase == "pre_roll":
                b = self._button("roll", (x, y + 90, w, 64), "ROLL DICE", lambda: self.act("roll"), True, 26)
                b.enabled = "roll" in legal
                out.append(b)
                if self.me.in_jail:
                    j = self._button("jail_pay", (x, y + 164, w // 2 - 6, 44), f"PAY £{JAIL_FINE}",
                                     lambda: self.act("jail_pay"), size=15)
                    j.enabled = "jail_pay" in legal
                    out.append(j)
                    c = self._button("jail_card", (x + w // 2 + 6, y + 164, w // 2 - 6, 44), "USE FREE CARD",
                                     lambda: self.act("jail_card"), size=14)
                    c.enabled = "jail_card" in legal
                    out.append(c)
            else:
                b = self._button("end", (x, y + 90, w, 64), "END TURN", lambda: self.act("end"), True, 24)
                b.enabled = "end" in legal
                out.append(b)
            t = self._button("trade", (x, ACTION_BOX.bottom - 52, 160, 40), "TRADE", self.open_trade, size=15)
            t.enabled = "trade" in legal
            out.append(t)
        if busy:
            for b in out:
                if b.label != "MENU":
                    b.enabled = False
        return out

    def _manage_buttons(self) -> list[Button]:
        """The buttons on the popup for a property you clicked on the board."""
        g = self.game
        sq = self.selected_sq
        if sq is None or not g.managing(HUMAN) or self.animating:
            return []
        s = SQUARES[sq]
        r = self.manage_rect()
        x, w = r.x + 236, r.w - 250
        out = []
        rows = [("mortgage", f"MORTGAGE +£{s.mortgage}", g.why_not_mortgage),
                ("unmortgage", f"PAY OFF -£{s.unmortgage_cost}", g.why_not_unmortgage)]
        if s.kind == "street":
            rows = [("build", f"BUILD -£{s.house_price}", g.why_not_build),
                    ("sell", f"SELL HOUSE +£{s.house_price // 2}", g.why_not_sell)] + rows
        for n, (action, label, check) in enumerate(rows):
            b = self._button(f"m_{action}", (x, r.y + 132 + n * 48, w, 42), label,
                             lambda a=action: self.act(a, sq=sq), action in ("build", "unmortgage"), 14)
            b.enabled = check(HUMAN, sq) is None
            out.append(b)
        out.append(self._button("m_close", (r.right - 38, r.y + 8, 30, 30), "X", self._close_manage, size=13))
        return out

    def _close_manage(self):
        self.selected_sq = None

    def _bankrupt(self):
        if self.confirm_bankrupt > 0:
            self.confirm_bankrupt = 0
            self.act("bankrupt")
        else:
            self.confirm_bankrupt = 2.5
            sfx.play("error")

    def manage_rect(self) -> pygame.Rect:
        return pygame.Rect(art.INNER.centerx - 225, art.INNER.y + 24, 450, art.deed_height(39, 210) + 24)

    # ================================================================== trading window

    def open_trade(self):
        if "trade" not in self.game.legal(HUMAN):
            self.error("You can trade on your own turn.")
            return
        others = [k for k in self.game.alive() if k != HUMAN]
        if not others:
            return
        self.trade_ui = {"to": others[0], "give": set(), "get": set(), "give_cash": 0, "get_cash": 0}
        sfx.play("select")

    def trade_rects(self):
        box = pygame.Rect(90, 70, 1100, 640)
        return box

    def _trade_buttons(self) -> list[Button]:
        t = self.trade_ui
        g = self.game
        box = self.trade_rects()
        out = []
        others = [k for k in g.alive() if k != HUMAN]
        for n, k in enumerate(others):
            b = self._button(f"t_to{k}", (box.x + 300 + n * 150, box.y + 20, 140, 40), self.name(k)[:10],
                             lambda k=k: self._trade_to(k), t["to"] == k, 14)
            out.append(b)
        for side, who, x in (("give", HUMAN, box.x + 30), ("get", t["to"], box.x + 570)):
            key = f"{side}_cash"
            for n, step in enumerate((-50, -10, 10, 50)):
                label = f"{'+' if step > 0 else '-'}{abs(step)}"
                out.append(self._button(f"t_{side}{step}", (x + 210 + n * 66, box.bottom - 120, 60, 36), label,
                                        lambda s=step, kk=key, w=who: self._trade_cash(kk, s, w), size=13))
        out.append(self._button("t_propose", (box.centerx + 10, box.bottom - 64, 260, 50), "PROPOSE DEAL",
                                self._propose, True, 18))
        out.append(self._button("t_cancel", (box.centerx - 270, box.bottom - 64, 260, 50), "CANCEL",
                                self._close_trade, size=18))
        return out

    def _trade_to(self, k):
        self.trade_ui.update(to=k, get=set(), get_cash=0)
        sfx.play("select")

    def _trade_cash(self, key, step, who):
        t = self.trade_ui
        t[key] = max(0, min(self.game.players[who].cash, t[key] + step))
        sfx.play("select")

    def _trade_chips(self, side: str):
        """(square, rect) for each tradable property on one side of the trade window."""
        t = self.trade_ui
        g = self.game
        box = self.trade_rects()
        who = HUMAN if side == "give" else t["to"]
        x0 = box.x + 30 if side == "give" else box.x + 570
        props = sorted(g.props_of(who), key=lambda k: (list(SETS).index(SQUARES[k].group) if SQUARES[k].group in SETS
                                                       else 9, k))
        out = []
        for n, k in enumerate(props):
            r = pygame.Rect(x0 + (n % 2) * 250, box.y + 110 + (n // 2) * 34, 240, 30)
            out.append((k, r))
        return out

    def _has_houses(self, k: int) -> bool:
        return SQUARES[k].kind == "street" and any(self.game.houses[m] for m in GROUPS[SQUARES[k].group])

    def _close_trade(self):
        self.trade_ui = None

    def _propose(self):
        t = self.trade_ui
        if not (t["give"] or t["get"] or t["give_cash"] or t["get_cash"]):
            self.error("Pick something to swap first.")
            return
        self.trade_ui = None
        self.act("trade", to=t["to"], give=sorted(t["give"]), get=sorted(t["get"]), give_cash=t["give_cash"],
                 get_cash=t["get_cash"])

    # ================================================================== input

    def handle(self, event):
        if self.admin.handle(event):
            return
        if self.overlay:
            for b in self.overlay_buttons:
                if b.handle(event):
                    return
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and self.overlay == "pause":
                self._set_overlay(None)
            return
        if self.splash and event.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN):
            self.splash = None
            return
        if self.trade_ui:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._close_trade()
                return
            for b in self._trade_buttons():
                if b.handle(event):
                    return
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                for side in ("give", "get"):
                    for k, r in self._trade_chips(side):
                        if r.collidepoint(event.pos):
                            if self._has_houses(k):
                                self.error("Sell the houses on that colour set before trading it.")
                                return
                            chosen = self.trade_ui[side]
                            chosen.symmetric_difference_update({k})
                            sfx.play("select" if k in chosen else "deselect")
                            return
            return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.selected_sq is not None:
                    self.selected_sq = None
                else:
                    self._set_overlay("pause")
            elif event.key in (pygame.K_RETURN, pygame.K_r) or (event.key == pygame.K_SPACE and not self.animating):
                self.primary()
            return
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.cur and self.cur.ev.kind == "card":
            self.cur.t = max(self.cur.t, self.cur.dur - 0.35 * self.speed)   # click to skip the card
        for b in self.manage_buttons + self.buttons:
            if b.visible and b.handle(event):
                return
        if self.selected_sq is not None and event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP) \
                and self.manage_rect().collidepoint(event.pos):
            return
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and art.BOARD.collidepoint(event.pos):
            for k in range(40):
                if art.cell_rect(k).collidepoint(event.pos):
                    if self.game.owner[k] == HUMAN and self.game.managing(HUMAN):
                        self.selected_sq = None if self.selected_sq == k else k
                        sfx.play("select")
                    elif self.game.owner[k] == HUMAN:
                        self.error("You can build or mortgage on your own turn.")
                    return
            if self.selected_sq is not None and not self.manage_rect().collidepoint(event.pos):
                self.selected_sq = None

    # ================================================================== update

    def update(self, dt: float):
        super().update(dt)
        self.admin.update(dt)
        self._pump_network()
        if self.game.events:
            self._consume_events()
        fast = 3.0 if pygame.key.get_pressed()[pygame.K_SPACE] and self.animating else 1.0
        step = dt * fast
        if self.splash:
            t, s, left, total = self.splash
            self.splash = (t, s, left - dt, total) if left > dt else None
        # Play the event queue, one animation at a time.
        if not self.splash:
            budget = step
            while budget > 0:
                if self.cur is None:
                    if not self.queue:
                        break
                    self.cur = self._start(self.queue.pop(0))
                left = max(0.0, self.cur.dur - self.cur.t)
                if budget >= left:
                    self.cur.t = self.cur.dur      # exactly, so rounding can never leave it a hair short
                    budget -= left
                else:
                    self.cur.t += budget
                    budget = 0.0
                self._tick(self.cur)
                if self.cur.t >= self.cur.dur:
                    self._finish(self.cur)
                    self.cur = None
                    if budget <= 0:
                        break
                else:
                    break
            if not self.animating:
                self.sync_view()
        # Effects.
        for j in range(len(self.vcash)):
            diff = self.tcash[j] - self.vcash[j]
            self.vcash[j] += diff * min(1.0, dt * 6) if abs(diff) > 1 else diff
            self.cash_flash[j] = max(0.0, self.cash_flash[j] - dt)
        for f in self.floaters:
            f.ttl -= dt
            f.pos[1] += f.vy * dt
        self.floaters = [f for f in self.floaters if f.ttl > 0]
        for sp in self.sparks:
            sp.vy += sp.grav * dt
            if sp.confetti:
                sp.vx += math.sin(self.clock * 3 + sp.spin) * 30 * dt
            sp.x += sp.vx * dt
            sp.y += sp.vy * dt
            sp.ttl -= dt
            sp.spin += 300 * dt
        self.sparks = [sp for sp in self.sparks if sp.ttl > 0 and sp.y < theme.HEIGHT + 20]
        if self.overlay == "game" and HUMAN in self.game.winners() and not self.me.bankrupt:
            self.confetti(1 if self.rng.random() < 0.5 else 2)
        for c in self.coins:
            c.t += step
        done = [c for c in self.coins if c.t >= c.dur]
        if done:
            sfx.play("click")
        self.coins = [c for c in self.coins if c.t < c.dur]
        for b in self.banners:
            b[2] -= dt
        self.banners = [b for b in self.banners if b[2] > 0]
        for sq in list(self.pops):
            self.pops[sq] -= dt
            if self.pops[sq] <= 0:
                del self.pops[sq]
        if self.flash:
            self.flash = (self.flash[0], self.flash[1] - dt) if self.flash[1] > dt else None
        self.confirm_bankrupt = max(0.0, self.confirm_bankrupt - dt)
        if (self._pending_overlay or self.game.game_over) and not self.animating and self.overlay in (None, "pause"):
            self._set_overlay("game")   # (even if someone paused just as it ended)
            return
        if self.me.bankrupt and not self.networked and not self.animating and self.overlay is None:
            self._set_overlay("game")   # you're out: no need to watch the computers finish
            return
        if self.selected_sq is not None and not self.game.managing(HUMAN):
            self.selected_sq = None
        if self.trade_ui and "trade" not in self.game.legal(HUMAN):
            self.trade_ui = None
        if not self.flow_blocked and not self.game.game_over:
            self.run_ai(dt)

    # ================================================================== drawing

    def draw(self, surf):
        surf.fill(theme.BG_DARK)
        theme.twinkle(surf, self.clock) if theme.SPARKLES else None
        surf.blit(art.board_surface(), art.BOARD.topleft)
        self._draw_board_state(surf)
        self._draw_center(surf)
        self._draw_tokens(surf)
        self._draw_effects(surf)
        self._draw_players(surf)
        self._draw_actions(surf)
        self.buttons = self.build_buttons()
        for b in self.buttons:
            b.draw(surf)
        if self.selected_sq is not None and self.manage_buttons:
            self._draw_manage(surf)
            for b in self.manage_buttons:
                b.draw(surf)
        self._draw_hover(surf)
        if self.trade_ui:
            self._draw_trade(surf)
        status_bar(surf, self.flash[0] if self.flash else self._status())
        if self.splash:
            self._draw_splash(surf)
        if self.overlay:
            self._draw_overlay(surf)
            self._draw_sparks(surf, True)
        self.admin.draw(surf)

    def _status(self) -> str:
        g = self.game
        if g.game_over:
            return "Game over!"
        if self.animating:
            return "Hold SPACE to speed things up."
        who = g.actor()
        if who == HUMAN:
            if g.trade and g.trade.get("to") == HUMAN:
                return "Someone wants to trade with you: ACCEPT or DECLINE."
            return {"pre_roll": "Your turn: ROLL DICE (Space). Click your properties to build or mortgage.",
                    "post_roll": "Build, trade, or END TURN (Space).",
                    "buy": "Buy it, or put it up for auction.",
                    "auction": "Bid on it, or PASS.",
                    "debt": "Raise the money: click your properties to sell houses or mortgage, or trade.",
                    "fine_or_chance": "Pay £10, or take a Chance card."}.get(g.phase, "")
        if g.trade and g.trade.get("from") == HUMAN:
            return f"Waiting for {self.name(g.trade['to'])} to answer your offer..."
        if who is not None:
            return f"{self.name(who)} is thinking..."
        return ""

    def _draw_board_state(self, surf):
        """Owners, mortgages, houses and the little bounces when something changes."""
        for k in range(40):
            s = SQUARES[k]
            if not s.ownable:
                continue
            o = self.vowner[k]
            pop = self.pops.get(k, 0.0)
            if o is not None and o < len(self.game.players):
                r = art.owner_rect(k)
                if pop > 0:
                    r = r.inflate(4 * math.sin(pop * 12), 4 * math.sin(pop * 12))
                pygame.draw.rect(surf, theme.OUTLINE, r.move(1, 1), border_radius=3)
                pygame.draw.rect(surf, self.color(o), r, border_radius=3)
            if self.vmort[k]:
                cr = art.cell_rect(k)
                shade = pygame.Surface(cr.size, pygame.SRCALPHA)
                shade.fill((40, 40, 50, 120))
                surf.blit(shade, cr)
                img = theme.font(11, True, heavy=True).render("M", True, (255, 255, 255))
                surf.blit(img, img.get_rect(center=cr.center))
            h = self.vhouses[k]
            if h:
                br = art.band_rect(k)
                scale = 1 + 0.5 * max(0.0, math.sin(pop * 10)) if pop > 0 else 1
                if h == 5:
                    img = art.house(int((11 if br.h > br.w else 16) * scale), hotel=True)
                    surf.blit(img, img.get_rect(center=br.center))
                else:
                    vertical = br.h > br.w
                    for n in range(h):
                        img = art.house(int(11 * scale))
                        if vertical:
                            c = (br.centerx, br.y + br.h * (n + 0.5) / 4)
                        else:
                            c = (br.x + br.w * (n + 0.5) / 4, br.centery)
                        surf.blit(img, img.get_rect(center=(int(c[0]), int(c[1]))))
            if pop > 0 and o is None:
                cr = art.cell_rect(k)
                pygame.draw.rect(surf, theme.ACCENT, cr, 2)

    def _draw_center(self, surf):
        g = self.game
        inner = art.INNER
        # Dice: tumbling while rolling, resting afterwards.
        a = self.cur
        if a and a.ev.kind == "roll":
            k = a.k
            for n in range(2):
                sx, sy = inner.right - 70 + n * 30, inner.bottom - 80
                ex, ey = inner.centerx - 34 + n * 68, inner.centery + 10
                e = ease_out(k)
                bounce = abs(math.sin(k * math.pi * 3.2)) * 70 * (1 - k)
                x, y = sx + (ex - sx) * e, sy + (ey - sy) * e - bounce
                face = a.data["dice"][n] if k > 0.78 else 1 + int(self.clock * 23 + n * 3) % 6
                img = art.die(face, 52)
                img = pygame.transform.rotate(img, a.data["spin"][n] * (1 - e))
                surf.blit(img, img.get_rect(center=(int(x), int(y))))
        elif self.dice_shown:
            for n in range(2):
                img = art.die(self.dice[n], 48)
                surf.blit(img, img.get_rect(center=(inner.centerx - 32 + n * 64, inner.centery + 10)))
        # The log along the bottom of the middle.
        y = inner.bottom - 20 - 16 * len(self.log[-5:])
        for n, (text, color) in enumerate(self.log[-5:]):
            dim = color == theme.TEXT_DIM
            ink = (60, 80, 70) if dim else (30, 50, 40) if color == theme.TEXT else _ink(color)
            img = theme.font(13, not dim).render(_fit(text, theme.font(13, not dim), inner.w - 24), True, ink)
            if n < len(self.log[-5:]) - 2:
                img.set_alpha(150 + 30 * n)
            surf.blit(img, img.get_rect(midtop=(inner.centerx, y)))
            y += 16
        # Cards being drawn.
        if a and a.ev.kind == "card":
            self._draw_card(surf, a)
        # A property up for grabs (or auction): its deed in the middle.
        offer_sq = None
        if g.phase == "buy" and not self.animating:
            offer_sq = g.players[g.current].pos
        elif g.phase == "auction" and g.auction and not self.animating:
            offer_sq = g.auction["sq"]
        if offer_sq is not None and self.selected_sq is None:
            img = art.deed(offer_sq, 220)
            bob = math.sin(self.clock * 2.5) * 3
            surf.blit(img, img.get_rect(center=(inner.centerx, inner.centery - 40 + bob)))
        # Deeds flying to their new owner.
        if a and a.data.get("deed") and a.ev.player is not None:
            start = art.cell_rect(a.ev.sq).center
            end = self.row_rect(a.ev.player).center
            k = ease_in_out(a.k)
            x = start[0] + (end[0] - start[0]) * k
            y = start[1] + (end[1] - start[1]) * k - 80 * math.sin(math.pi * a.k)
            img = pygame.transform.rotozoom(art.deed(a.ev.sq, 220), 10 * (1 - a.k), 0.25 + 0.4 * math.sin(math.pi * a.k))
            surf.blit(img, img.get_rect(center=(int(x), int(y))))

    def _draw_card(self, surf, a: Anim):
        deck = a.data["deck"]
        start = art.deck_center(deck)
        end = (art.INNER.centerx, art.INNER.centery - 30)
        t = a.t / max(0.001, self.speed)
        if t < 0.35:
            k = ease_out(t / 0.35)
            pos = (start[0] + (end[0] - start[0]) * k, start[1] + (end[1] - start[1]) * k)
            img = pygame.transform.rotozoom(art.card_back(deck), 45 * (1 - k), 0.45 + 0.55 * k)
        elif t < 0.6:
            k = (t - 0.35) / 0.25
            pos = end
            sx = abs(math.cos(math.pi * k))
            base = art.card_back(deck) if k < 0.5 else art.card_face(deck, a.ev.text)
            img = pygame.transform.smoothscale(base, (max(2, int(base.get_width() * sx)), base.get_height()))
        else:
            pos = end
            img = art.card_face(deck, a.ev.text)
            fade = min(1.0, (a.dur - a.t) / (0.3 * self.speed))
            if fade < 1:
                img = img.copy()
                img.set_alpha(int(255 * max(0.0, fade)))
        surf.blit(img, img.get_rect(center=(int(pos[0]), int(pos[1]))))

    def _draw_tokens(self, surf):
        g = self.game
        a = self.cur
        order = sorted(range(len(g.players)), key=lambda j: (a is not None and a.data.get("mover") == j))
        for j in order:
            if self.vbankrupt[j] and not (a and a.ev.kind == "bankrupt" and a.ev.player == j):
                continue
            x, y = self.token_pos(j)
            moving = a is not None and a.data.get("mover") == j
            scale = a.data.get("scale", 1.0) if moving else 1.0
            active = g.current == j and not g.game_over
            size = int(30 * scale) if not moving else int(30 * scale)
            bob = 0 if moving else (math.sin(self.clock * 5) * 2.5 if active else 0)
            if active and not moving:
                ring = pygame.Surface((44, 44), pygame.SRCALPHA)
                alpha = int(110 + 70 * math.sin(self.clock * 5))
                pygame.draw.circle(ring, (*self.color(j), max(0, alpha)), (22, 22), 18, 3)
                surf.blit(ring, ring.get_rect(center=(int(x), int(y) + 6)))
            sh = pygame.Surface((30, 12), pygame.SRCALPHA)
            pygame.draw.ellipse(sh, (0, 0, 0, 70 if not moving else 40), sh.get_rect())
            surf.blit(sh, sh.get_rect(center=(int(x), int(y) + 12)))
            img = art.token(g.players[j].token, self.color(j), size)
            if moving and a.data.get("spin"):
                img = pygame.transform.rotate(img, a.data["spin"])
            if self.vbankrupt[j]:
                img = img.copy()
                img.set_alpha(int(255 * (1 - (a.k if a else 1))))
            surf.blit(img, img.get_rect(center=(int(x), int(y - 4 + bob))))

    def _draw_sparks(self, surf, confetti: bool):
        for sp in self.sparks:
            if sp.confetti != confetti:
                continue
            fade = min(1.0, sp.ttl / (0.3 * sp.max_ttl))
            if confetti:
                w = max(1, int(sp.size * abs(math.cos(math.radians(sp.spin)))))
                pygame.draw.rect(surf, sp.color, (int(sp.x - w / 2), int(sp.y - sp.size / 2), w, int(sp.size)))
            else:
                r = max(1, int(sp.size * fade))
                pygame.draw.circle(surf, sp.color, (int(sp.x), int(sp.y)), r)
                if r > 2:
                    pygame.draw.circle(surf, (255, 255, 255), (int(sp.x), int(sp.y)), r // 2)

    def _draw_effects(self, surf):
        self._draw_sparks(surf, False)
        for c in self.coins:
            if c.t < 0:
                continue
            k = ease_in_out(c.t / c.dur)
            x = c.start[0] + (c.end[0] - c.start[0]) * k
            y = c.start[1] + (c.end[1] - c.start[1]) * k - 60 * math.sin(math.pi * k)
            theme.chip(surf, (int(x), int(y)), 9, theme.ACCENT)
        for f in self.floaters:
            img = theme.pixel_surface(f.text, f.size, f.color)
            if f.ttl < 0.4:
                img = img.copy()
                img.set_alpha(int(255 * f.ttl / 0.4))
            rect = img.get_rect(center=(int(f.pos[0]), int(f.pos[1])))
            rect.top = max(rect.top, 4)
            surf.blit(img, rect)
        if self.banners:
            text, color, ttl, total = self.banners[-1]
            age = total - ttl
            k = ease_out(age / 0.25) if age < 0.25 else 1.0
            img = theme.logo_surface(text, 34, 3, color)
            if ttl < 0.3:
                img = img.copy()
                img.set_alpha(int(255 * ttl / 0.3))
            img = pygame.transform.rotozoom(img, 0, 0.6 + 0.4 * k)
            surf.blit(img, img.get_rect(center=(art.INNER.centerx, art.INNER.y + 40)))

    def _draw_players(self, surf):
        g = self.game
        for j, p in enumerate(g.players):
            r = self.row_rect(j)
            active = g.current == j and not g.game_over
            acting = g.actor() == j and not self.animating
            edge = theme.ACCENT if active else theme.PANEL_EDGE
            theme.panel(surf, r, fill="PANEL_HOVER" if acting else "PANEL", edge=edge, edge_w=3 if active else 2)
            pygame.draw.circle(surf, theme.OUTLINE, (r.x + 32, r.centery + 2), 24)
            pygame.draw.circle(surf, theme.lighten(self.color(j), 30), (r.x + 32, r.centery), 24)
            img = art.token(p.token, self.color(j), 34)
            surf.blit(img, img.get_rect(center=(r.x + 32, r.centery - 1)))
            name_r = theme.ptext(surf, self.name(j), (r.x + 64, r.y + 6), 18,
                                 theme.TEXT if not p.bankrupt else theme.TEXT_FAINT)
            if p.difficulty:
                theme.ptext(surf, p.difficulty.upper(), (r.x + 64, r.y + 30), 11, DIFF_COLORS.get(p.difficulty,
                                                                                                   theme.TEXT_DIM))
            elif j != HUMAN:
                theme.ptext(surf, "PLAYER", (r.x + 64, r.y + 30), 11, theme.TEXT_DIM)
            if p.bankrupt:
                theme.ptext(surf, "BANKRUPT", (r.right - 16, r.y + 8), 20, theme.DANGER, anchor="topright")
                continue
            flash = self.cash_flash[j]
            cash = int(round(self.vcash[j]))
            color = theme.ACCENT
            if flash > 0:
                color = theme.SUCCESS if self.tcash[j] >= self.vcash[j] - 0.5 else theme.DANGER
            theme.ptext(surf, f"£{cash:,}", (r.right - 16, r.y + 6), 22, color, anchor="topright")
            if acting and j != HUMAN:
                dots = "." * (1 + int(self.clock * 3) % 3)
                theme.ptext(surf, f"THINKING{dots}", (r.right - 16, r.y + 34), 12, theme.TEXT_DIM, anchor="topright")
            elif r.h >= 80:
                theme.ptext(surf, f"WORTH £{g.net_worth(j):,}", (r.right - 16, r.y + 34), 11, theme.TEXT_DIM,
                            anchor="topright")
            # Little coloured squares for what they own, grouped by set (a dot for each house).
            tall = r.h >= 80
            x = r.x + (64 if tall else 150)
            for group in list(SETS) + ["station", "utility"]:
                owned = [k for k in GROUPS[group] if self.vowner[k] == j]
                if not owned:
                    continue
                col = SETS.get(group, (40, 40, 48) if group == "station" else (200, 200, 210))
                for k in owned:
                    box = pygame.Rect(x, r.bottom - (24 if tall else 20), 11 if tall else 10, 16 if tall else 14)
                    pygame.draw.rect(surf, col, box)
                    pygame.draw.rect(surf, theme.OUTLINE, box, 1)
                    if self.vmort[k]:
                        pygame.draw.line(surf, theme.OUTLINE, box.topleft, box.bottomright, 2)
                    elif self.vhouses[k]:
                        dot = (220, 30, 40) if self.vhouses[k] == 5 else (40, 170, 70)
                        pygame.draw.circle(surf, theme.OUTLINE, box.center, 4)
                        pygame.draw.circle(surf, dot, box.center, 3)
                    x += box.w + 1
                x += 5
            tags = []
            if p.in_jail and self.vjail[j]:
                tags.append(("JAIL", theme.DANGER))
            if p.goojf:
                tags.append((f"FREE x{len(p.goojf)}", theme.INFO))
            tx = name_r.right + 10
            for text, col in tags:
                img = theme.pixel_surface(text, 11, theme.OUTLINE, None)
                box = pygame.Rect(tx, r.y + 8, img.get_width() + 10, img.get_height() + 2)
                theme.rounded(surf, col, box, 6)
                surf.blit(img, img.get_rect(center=box.center))
                tx += box.w + 6

    def _draw_actions(self, surf):
        g = self.game
        box = ACTION_BOX
        theme.panel(surf, box)
        rounds = f"ROUND {g.round}" + (f" OF {g.max_rounds}" if g.max_rounds else "")
        theme.ptext(surf, rounds, (box.x + 20, box.bottom - 46), 14, theme.TEXT_DIM)
        x, y = box.x + 20, box.y + 16
        who = g.actor()
        if g.game_over:
            theme.ptext(surf, "GAME OVER", (x, y), 26, theme.ACCENT)
            return
        if not self.settled():
            cur = g.current
            heading = "YOUR TURN" if cur == HUMAN else f"{self.name(cur)}'S TURN"
            theme.ptext(surf, heading, (x, y), 26, theme.ACCENT if cur == HUMAN else self.color(cur))
            return
        if g.trade:
            t = g.trade
            title = "A DEAL FOR YOU!" if t.get("to") == HUMAN else \
                f"{self.name(t.get('from'))} {self.verb(t.get('from'), 'OFFER')} {self.name(t.get('to'))}:"
            theme.ptext(surf, title, (x, y), 22, theme.ACCENT)
            self._trade_summary(surf, t, x, y + 36, box.w - 40)
            return
        if g.phase == "auction" and g.auction:
            au = g.auction
            theme.ptext(surf, "AUCTION", (x, y), 24, theme.ACCENT)
            theme.ptext(surf, SQUARES[au["sq"]].name.upper(), (x, y + 32), 18)
            high = f"HIGH BID £{au['high']} - {self.name(au['bidder'])}" if au["bidder"] is not None else "NO BIDS YET"
            theme.ptext(surf, high, (x, y + 64), 20, theme.SUCCESS if au["bidder"] is not None else theme.TEXT_DIM)
            turn = self.name(who) if who is not None else ""
            theme.ptext(surf, f"{turn} TO BID" if who != HUMAN else "YOUR BID:", (x, y + 98), 16, theme.TEXT_DIM)
            theme.ptext(surf, f"Still bidding: {', '.join(self.name(k) for k in au['active'])}", (x, y + 124), 12,
                        theme.TEXT_FAINT)
            return
        if g.phase == "debt" and g.debt:
            d = g.debt
            debtor = d["debtor"]
            theme.ptext(surf, f"{self.name(debtor)} {'OWE' if debtor == HUMAN else 'OWES'} £{d['amount']}", (x, y), 24,
                        theme.DANGER)
            theme.ptext(surf, f"TO {self.name(d.get('creditor'))} ({d['reason']})", (x, y + 34), 14, theme.TEXT_DIM)
            if debtor == HUMAN:
                theme.text(surf, "Click your properties on the board to sell houses", (x, y + 62), 14, theme.TEXT,
                           bold=False)
                theme.text(surf, "or mortgage them, then PAY.", (x, y + 80), 14, theme.TEXT, bold=False)
                theme.ptext(surf, f"You could raise £{g.raisable(HUMAN)} more.", (x, y + 102), 13, theme.TEXT_DIM)
            return
        cur = g.current
        if cur == HUMAN:
            heading = {"pre_roll": "YOUR TURN", "post_roll": "YOUR TURN", "buy": "FOR SALE!",
                       "fine_or_chance": "YOUR CHOICE"}.get(g.phase, "YOUR TURN")
        else:
            heading = f"{self.name(cur)}'S TURN"
        theme.ptext(surf, heading, (x, y), 26, theme.ACCENT if cur == HUMAN else self.color(cur))
        if cur == HUMAN and g.phase == "buy":
            sq = self.me.pos
            theme.ptext(surf, SQUARES[sq].name.upper(), (x, y + 36), 18)
            theme.ptext(surf, f"£{SQUARES[sq].price}  -  you have £{self.me.cash:,}", (x, y + 62), 16, theme.TEXT_DIM)
        elif cur == HUMAN and g.phase == "pre_roll" and self.me.in_jail:
            theme.ptext(surf, f"IN JAIL - try {3 - self.me.jail_turns} more time(s) for doubles", (x, y + 36), 14,
                        theme.DANGER)
        elif cur == HUMAN and g.phase in ("pre_roll", "post_roll"):
            theme.text(surf, "Click your properties to build houses or mortgage.", (x, y + 40), 14, theme.TEXT_DIM,
                       bold=False)
        elif cur == HUMAN and g.phase == "fine_or_chance":
            theme.text(surf, "Pay a £10 fine, or take a Chance card?", (x, y + 40), 15, theme.TEXT, bold=False)

    def _trade_summary(self, surf, t, x, y, w):
        give = [SQUARES[k].name for k in t.get("give", [])]
        get = [SQUARES[k].name for k in t.get("get", [])]
        a, b = self.name(t.get("from")), self.name(t.get("to"))
        lines = [(f"{a} GIVE{'' if t.get('from') == HUMAN else 'S'}:", theme.ACCENT)]
        lines += [(f"  {n}", theme.TEXT) for n in give] + ([(f"  £{t['give_cash']}", theme.TEXT)] if t.get("give_cash")
                                                           else [])
        if not give and not t.get("give_cash"):
            lines.append(("  nothing", theme.TEXT_FAINT))
        lines.append((f"{b} GIVE{'' if t.get('to') == HUMAN else 'S'}:", theme.ACCENT))
        lines += [(f"  {n}", theme.TEXT) for n in get] + ([(f"  £{t['get_cash']}", theme.TEXT)] if t.get("get_cash")
                                                          else [])
        if not get and not t.get("get_cash"):
            lines.append(("  nothing", theme.TEXT_FAINT))
        for text, color in lines[:9]:
            theme.ptext(surf, text, (x, y), 14, color)
            y += 18

    def _draw_manage(self, surf):
        g = self.game
        sq = self.selected_sq
        s = SQUARES[sq]
        r = self.manage_rect()
        theme.panel(surf, r, edge=theme.ACCENT, edge_w=3)
        full = s.kind == "street" and g.owns_set(HUMAN, s.group)
        img = art.deed(sq, 210, "YOU", g.houses[sq], g.mortgaged[sq], full)
        surf.blit(img, (r.x + 12, r.y + 12))
        x, w = r.x + 236, r.w - 250
        theme.ptext(surf, "MANAGE", (x, r.y + 14), 22, theme.ACCENT)
        h = g.houses[sq]
        if g.mortgaged[sq]:
            state, col = "MORTGAGED - NO RENT", theme.DANGER
        elif s.kind != "street":
            state, col = "RENT " + (f"£{g.rent(sq)}" if s.kind == "station" else
                                    f"{'10' if g.rent(sq, 1) == 10 else '4'} x DICE"), theme.SUCCESS
        else:
            state = ("A HOTEL" if h == 5 else f"{h} HOUSE{'S' if h != 1 else ''}") if h else \
                ("FULL SET!" if full else "NO HOUSES")
            col = theme.SUCCESS if h or full else theme.TEXT
        theme.ptext(surf, state, (x, r.y + 48), 15, col)
        if not g.mortgaged[sq] and s.kind == "street":
            theme.ptext(surf, f"RENT NOW £{g.rent(sq)}", (x, r.y + 70), 15, theme.ACCENT)
        # Why you can't build yet (the most common question).
        why = g.why_not_build(HUMAN, sq) if s.kind == "street" and g.phase != "debt" else None
        if why and not g.mortgaged[sq]:
            ty = r.y + 94
            for line in art.wrap(why, theme.font(12, False), w)[:3]:
                theme.text(surf, line, (x, ty), 12, theme.TEXT_DIM, bold=False)
                ty += 15
        theme.ptext(surf, f"CASH £{self.me.cash:,}", (x, r.bottom - 30), 15, theme.TEXT_DIM)

    def _draw_hover(self, surf):
        if self.trade_ui or self.overlay or self.selected_sq is not None or (self.cur and self.cur.ev.kind == "card"):
            return
        mouse = pygame.mouse.get_pos()
        if not art.BOARD.collidepoint(mouse) or art.INNER.collidepoint(mouse):
            return
        g = self.game
        for k in range(40):
            if art.cell_rect(k).collidepoint(mouse):
                pygame.draw.rect(surf, theme.ACCENT, art.cell_rect(k), 3)
                if SQUARES[k].ownable:
                    o = g.owner[k]
                    full = SQUARES[k].kind == "street" and o is not None and g.owns_set(o, SQUARES[k].group)
                    img = art.deed(k, 210, self.name(o) if o is not None else None, g.houses[k], g.mortgaged[k], full)
                    rent = g.rent(k, 7) if o is not None else 0
                    pos = (art.INNER.centerx, art.INNER.centery - 20)
                    surf.blit(img, img.get_rect(center=pos))
                    if o is not None and not g.mortgaged[k]:
                        label = f"RENT NOW: £{rent}" if SQUARES[k].kind != "utility" else "RENT: DICE x " + \
                            ("10" if g.rent(k, 1) == 10 else "4")
                        theme.ptext(surf, label, (pos[0], img.get_rect(center=pos).bottom + 16), 16, theme.ACCENT,
                                    anchor="center")
                return

    def _draw_trade(self, surf):
        t = self.trade_ui
        g = self.game
        shade = pygame.Surface((theme.WIDTH, theme.HEIGHT), pygame.SRCALPHA)
        shade.fill((*theme.OUTLINE, 190))
        surf.blit(shade, (0, 0))
        box = self.trade_rects()
        theme.panel(surf, box, edge=theme.ACCENT, edge_w=3)
        theme.ptext(surf, "MAKE A DEAL", (box.x + 30, box.y + 26), 26, theme.ACCENT)
        for side, who, x in (("give", HUMAN, box.x + 30), ("get", t["to"], box.x + 570)):
            title = "YOU GIVE" if side == "give" else f"{self.name(who)} GIVES"
            theme.ptext(surf, title, (x, box.y + 80), 18, theme.ACCENT)
            chips = self._trade_chips(side)
            for k, r in chips:
                on = k in t[side]
                blocked = self._has_houses(k)
                theme.rounded(surf, theme.SUCCESS if on else theme.INNER, r, 6)
                col = SETS.get(SQUARES[k].group, (40, 40, 48) if SQUARES[k].kind == "station" else (200, 200, 210))
                pygame.draw.rect(surf, col, (r.x + 4, r.y + 5, 14, r.h - 10))
                label = SQUARES[k].name + (" (M)" if g.mortgaged[k] else "") + (" - has houses" if blocked else "")
                theme.text(surf, label[:30], (r.x + 24, r.y + 6), 14, theme.OUTLINE if on else
                           theme.TEXT_FAINT if blocked else theme.TEXT, bold=on)
            if not chips:
                theme.ptext(surf, "No properties", (x, box.y + 116), 16, theme.TEXT_FAINT)
            cash = t[f"{side}_cash"]
            theme.ptext(surf, f"CASH: £{cash}", (x, box.bottom - 114), 20, theme.ACCENT)
            theme.ptext(surf, f"(has £{g.players[who].cash:,})", (x, box.bottom - 88), 13, theme.TEXT_DIM)
        for b in self._trade_buttons():
            b.draw(surf)

    def _draw_splash(self, surf):
        title, sub, t, total = self.splash
        k = min(1.0, (total - t) / 0.25, t / 0.3)
        band = pygame.Rect(0, 300, theme.WIDTH, 170)
        shade = pygame.Surface(band.size, pygame.SRCALPHA)
        shade.fill((*theme.OUTLINE, int(200 * k)))
        surf.blit(shade, band)
        theme.logo(surf, title, (theme.WIDTH // 2 + int((1 - k) * -300), band.y + 70), 70, angle=6)
        theme.ptext(surf, sub, (theme.WIDTH // 2, band.bottom - 26), 20, anchor="center")

    def _draw_overlay(self, surf):
        shade = pygame.Surface((theme.WIDTH, theme.HEIGHT), pygame.SRCALPHA)
        shade.fill((*theme.OUTLINE, 190))
        surf.blit(shade, (0, 0))
        cx = theme.WIDTH // 2
        g = self.game
        if self.overlay == "pause":
            theme.panel(surf, (cx - 200, 200, 400, 120 + 68 * len(self.overlay_buttons)))
            theme.logo(surf, "PAUSED", (cx, 250), 40, angle=4)
        elif self.overlay == "disconnected":
            theme.panel(surf, (cx - 330, 250, 660, 300))
            theme.logo(surf, "DISCONNECTED", (cx, 320), 44, angle=4)
            reason = (self.client.error if self.client else None) or "The connection was lost."
            theme.ptext(surf, reason, (cx, 400), 16, anchor="center")
        else:
            panel = pygame.Rect(cx - 420, 70, 840, 690)
            theme.panel(surf, panel)
            winners = g.winners()
            if self.me.bankrupt:
                title = "YOU WENT BANKRUPT!"
            elif len(winners) > 1:
                title = "YOU TIED FOR FIRST!" if HUMAN in winners else "IT'S A TIE!"
            elif winners:
                title = "YOU WIN!" if winners[0] == HUMAN else f"{g.players[winners[0]].name} WINS!"
            else:
                title = "GAME OVER"
            theme.logo(surf, title, (cx, 130), 52, angle=4)
            bank = f"+{self._banked or 0} CHIPS BANKED   BANK: {self.app.settings.chip_bank:,}"
            r_ = theme.ptext(surf, bank, (cx + 12, 190), 18, theme.ACCENT, anchor="center")
            theme.chip(surf, (r_.x - 16, r_.centery + 2), 10, theme.ACCENT)
            for k, i in enumerate(g.standings()):
                p = g.players[i]
                row = pygame.Rect(panel.x + 30, 220 + k * 70, panel.w - 60, 62)
                theme.rounded(surf, theme.PANEL_HOVER if i == HUMAN else theme.INNER, row, 10)
                img = art.token(p.token, self.color(i), 40)
                surf.blit(img, img.get_rect(center=(row.x + 36, row.centery)))
                theme.ptext(surf, self.name(i), (row.x + 70, row.centery), 22, anchor="midleft")
                if p.bankrupt:
                    theme.ptext(surf, "BANKRUPT", (row.right - 20, row.centery), 20, theme.DANGER, anchor="midright")
                    continue
                theme.ptext(surf, f"£{p.cash:,} CASH", (row.x + 330, row.centery), 16, theme.TEXT_DIM, anchor="midleft")
                theme.ptext(surf, f"{len(g.props_of(i))} PROPERT{'Y' if len(g.props_of(i)) == 1 else 'IES'}", (row.x + 500, row.centery), 16, theme.TEXT_DIM,
                            anchor="midleft")
                theme.ptext(surf, f"£{g.net_worth(i):,}", (row.right - 20, row.centery), 22, theme.ACCENT,
                            anchor="midright")
        for b in self.overlay_buttons:
            b.draw(surf)
