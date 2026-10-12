"""Computer players for Monopoly. Each call to `choose` returns exactly one move.

  Easy    - buys on a whim, bids low, rarely builds, never starts trades
  Medium  - keeps a cash cushion, builds on full sets, trades only when asked
  Hard    - values colour sets properly, builds to three houses, offers cash for missing set pieces
  Expert  - like Hard, but watches the board's biggest rents when keeping cash, and bargains harder

Strategy ideas follow the sample AIs from monopyly (github.com/richard-shepherd/monopyly).
"""

from __future__ import annotations

import random

from .board import GROUPS, JAIL_FINE, SQUARES
from .engine import MonopolyRules

RESERVE = {"Easy": 40, "Medium": 150, "Hard": 160, "Expert": 150}


class MonopolyAI:
    def __init__(self, difficulty: str = "Medium", rng: random.Random | None = None):
        self.difficulty = difficulty if difficulty in RESERVE else "Medium"
        self.rng = rng or random.Random()
        self._traded: set = set()
        self._tried: dict = {}

    # ------------------------------------------------------------------ judging value

    def reserve(self, g: MonopolyRules, me: int) -> int:
        base = RESERVE[self.difficulty]
        if self.difficulty == "Expert":
            # Keep enough to survive the nastiest rent an opponent could charge.
            worst = max((g.rent(k, 7) for k in range(40) if g.owner[k] not in (None, me)), default=0)
            base = max(base, min(450, worst // 3))
        return base

    def value(self, g: MonopolyRules, me: int, sq: int, owner_after: int | None = None) -> float:
        """How much a property is worth to `me` (bigger when it completes or blocks a set)."""
        s = SQUARES[sq]
        v = float(s.price)
        if self.difficulty == "Easy":
            return v
        group = GROUPS[s.group]
        mine = sum(1 for k in group if g.owner[k] == me or k == sq)
        if mine == len(group):
            v *= 2.2 if s.kind == "street" else 1.4
        elif mine == len(group) - 1:
            v *= 1.3
        others = {g.owner[k] for k in group if k != sq and g.owner[k] not in (None, me)}
        if len(others) == 1 and all(g.owner[k] in others for k in group if k != sq):
            v *= 1.6   # buying this stops someone else completing the set
        return v

    # ------------------------------------------------------------------ the one entry point

    def choose(self, g: MonopolyRules, me: int) -> tuple[str, dict]:
        legal = g.legal(me)
        if g.trade and g.trade["to"] == me:
            return ("accept" if self.likes_trade(g, me, g.trade) else "decline"), {}
        if "bid" in legal or ("pass" in legal and g.phase == "auction"):
            return self._auction(g, me, legal)
        if g.phase == "debt":
            return self._debt(g, me, legal)
        if g.phase == "buy":
            return self._buy(g, me, legal)
        if g.phase == "fine_or_chance":
            fine = "pay_fine" in legal and (self.difficulty != "Easy" or self.rng.random() < 0.5)
            return ("pay_fine" if fine else "take_chance"), {}
        if g.phase in ("pre_roll", "post_roll"):
            move = self._manage(g, me)
            if move:
                return move
            if g.phase == "pre_roll":
                p = g.players[me]
                if p.in_jail:
                    unowned = sum(1 for k in range(40) if SQUARES[k].ownable and g.owner[k] is None)
                    early = unowned > 8
                    if "jail_card" in legal and (early or self.difficulty == "Easy"):
                        return "jail_card", {}
                    if "jail_pay" in legal and early and p.cash - JAIL_FINE >= self.reserve(g, me):
                        return "jail_pay", {}
                return "roll", {}
            return "end", {}
        return ("pass", {}) if "pass" in legal else (legal[0], {}) if legal else ("end", {})

    # ------------------------------------------------------------------ decisions

    def _buy(self, g, me, legal):
        p = g.players[me]
        sq = p.pos
        price = SQUARES[sq].price
        if "buy" not in legal:
            return "auction", {}
        if self.difficulty == "Easy":
            return ("buy" if self.rng.random() < 0.75 else "auction"), {}
        worth = self.value(g, me, sq)
        spare = p.cash - price
        if spare >= self.reserve(g, me) or (worth > price * 1.25 and spare >= 40):
            return "buy", {}
        return "auction", {}

    def _auction(self, g, me, legal):
        a = g.auction
        p = g.players[me]
        sq = a["sq"]
        factor = {"Easy": 0.7, "Medium": 1.0, "Hard": 1.15, "Expert": 1.25}[self.difficulty]
        limit = int(self.value(g, me, sq) * factor)
        limit = min(limit, p.cash - (0 if self.difficulty == "Easy" else self.reserve(g, me) // 2))
        if self.difficulty == "Easy":
            limit = int(limit * self.rng.uniform(0.6, 1.1))
        limit = min(limit, p.cash)
        step = 10 if a["high"] < 100 else 20
        if "bid" in legal and a["high"] + 1 <= limit:
            return "bid", {"amount": min(limit, a["high"] + step)}
        return "pass", {}

    def _debt(self, g, me, legal):
        d = g.debt
        p = g.players[me]
        if "pay" in legal:
            return "pay", {}
        if p.cash + g.raisable(me) < d["amount"]:
            return "bankrupt", {}
        # Sell houses on the cheapest sets first, then mortgage what hurts least.
        sells = [k for k in g.props_of(me) if not g.why_not_sell(me, k)]
        if sells:
            return "sell", {"sq": min(sells, key=lambda k: (SQUARES[k].house_price, -g.houses[k]))}
        morts = [k for k in g.props_of(me) if not g.why_not_mortgage(me, k)]
        if morts:
            return "mortgage", {"sq": min(morts, key=lambda k: self.value(g, me, k))}
        return "bankrupt", {}

    def _manage(self, g, me):
        """Unmortgage, build, or offer a trade. None when there's nothing worth doing."""
        p = g.players[me]
        reserve = self.reserve(g, me)
        d = self.difficulty
        # Pay off mortgages on sets we could build on.
        for k in g.props_of(me):
            if g.mortgaged[k] and not g.why_not_unmortgage(me, k) and \
                    p.cash - SQUARES[k].unmortgage_cost >= reserve + (100 if d == "Easy" else 0):
                if SQUARES[k].kind != "street" or g.owns_set(me, SQUARES[k].group) or p.cash > 900:
                    return "unmortgage", {"sq": k}
        # Build, evenly, on the best set we can afford.
        if d != "Easy" or self.rng.random() < 0.3:
            cap = 5 if d in ("Hard", "Expert") and p.cash > 1200 else 3 if d != "Expert" else 4
            options = [k for k in g.props_of(me) if not g.why_not_build(me, k) and g.houses[k] < cap
                       and p.cash - SQUARES[k].house_price >= reserve]
            if options:
                return "build", {"sq": max(options, key=lambda k: (SQUARES[k].rents[3], -g.houses[k]))}
        # Offer cash for the last piece of a set (once per turn).
        if d in ("Hard", "Expert") and "trade" in g.legal(me):
            key = (getattr(g, "round", 0), me)
            if key not in self._traded:
                self._traded.add(key)
                offer = self._trade_offer(g, me)
                if offer:
                    return "trade", offer
        return None

    def _trade_offer(self, g, me):
        """Try for the last piece of a colour set: a swap that completes a set for both of us, or cash."""
        p = g.players[me]
        rnd = getattr(g, "round", 0)
        for group, members in GROUPS.items():
            if group in ("station", "utility"):
                continue
            missing = [k for k in members if g.owner[k] != me]
            if len(missing) != 1:
                continue
            k = missing[0]
            other = g.owner[k]
            if other is None or g.players[other].bankrupt or g.mortgaged[k] or any(g.houses[m] for m in members):
                continue
            if rnd - self._tried.get((group, other), -99) < 6:
                continue   # don't nag: ask the same player for the same set at most every few rounds
            self._tried[(group, other)] = rnd
            # A swap: something of ours that completes one of *their* sets.
            for m in g.props_of(me):
                sm = SQUARES[m]
                if sm.kind != "street" or g.mortgaged[m] or any(g.houses[x] for x in GROUPS[sm.group]):
                    continue
                if all(g.owner[x] == other or x == m for x in GROUPS[sm.group]):
                    extra = max(0, SQUARES[k].price - sm.price + 20)
                    if p.cash - extra >= self.reserve(g, me) // 2:
                        return {"to": other, "give": [m], "get": [k], "give_cash": extra, "get_cash": 0}
            price = int(SQUARES[k].price * (2.3 if self.difficulty == "Expert" else 2.1))
            if p.cash - price >= self.reserve(g, me) // 2:
                return {"to": other, "give": [], "get": [k], "give_cash": price, "get_cash": 0}
        return None

    def _trade_value(self, g, me: int, them: int, k: int, giving: bool, swapped: list[int]) -> float:
        """What a property in a trade is worth to `me` (simpler than `value`: just the set effects)."""
        s = SQUARES[k]
        v = float(s.price) if not g.mortgaged[k] else s.price * 0.45
        group = GROUPS[s.group]
        if giving:
            if all(g.owner[m] == them or m == k or m in swapped for m in group) and s.kind == "street":
                v *= 2.0                 # it completes a set for them
            elif sum(1 for m in group if g.owner[m] == me) >= len(group) - 1:
                v *= 1.5                 # it breaks up a set we nearly have
        elif all(g.owner[m] == me or m == k or m in swapped for m in group):
            v *= 2.0 if s.kind == "street" else 1.3   # it completes a set for us
        return v

    def likes_trade(self, g, me: int, t: dict) -> bool:
        """Would `me` accept trade t (where me is t["to"])?"""
        them = t["from"]
        if g.players[me].cash + t["give_cash"] - t["get_cash"] < 0:
            return False
        gain = t["give_cash"] - t["get_cash"]
        gain += sum(self._trade_value(g, me, them, k, False, t["give"]) for k in t["give"])
        gain -= sum(self._trade_value(g, me, them, k, True, t["get"]) for k in t["get"])
        if self.difficulty == "Easy":
            return gain > -40 * self.rng.random()
        need = {"Medium": 0, "Hard": 20, "Expert": 40}[self.difficulty]
        return gain > need
