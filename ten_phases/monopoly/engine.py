"""Monopoly rules, as a step-by-step state machine.

Everything a turn does (moving, paying, drawing cards) is queued as small
steps. When a step needs a decision (buy or auction, pay a debt, a Community
Chest choice, an auction bid) the queue pauses until the right player acts,
then carries on. The table screen replays the events this emits as animations.

Rules: the classic London board (see board.py). Roll doubles to go again (three
doubles in a row sends you to jail). Unbought properties you decline go to
auction. Build evenly across a full colour set; mortgage at half price and pay
it off plus 10%. In jail: pay £50, use a Get Out of Jail Free card, or try for
doubles (after three tries you must pay). Can't pay? Sell houses, mortgage or
trade, or go bankrupt (everything goes to whoever you owe). The game ends when
one player is left, or after the chosen number of rounds (richest wins).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .board import (CHANCE, CHEST, GO_SALARY, GROUPS, JAIL, JAIL_FINE, SETS, SQUARES, STARTING_CASH,
                    STATION_RENTS, Card)

DEFAULT_ROUNDS = 40
TOKENS = ("car", "hat", "dog", "ship", "boot", "cat")
MANAGE_PHASES = ("pre_roll", "post_roll")


class RuleError(Exception):
    """An illegal move. The message is shown to the player."""


@dataclass
class MPlayer:
    name: str
    is_human: bool = False
    difficulty: str | None = None
    token: str = "car"
    cash: int = STARTING_CASH
    pos: int = 0
    in_jail: bool = False
    jail_turns: int = 0
    goojf: list[str] = field(default_factory=list)   # which decks their Get Out of Jail Free cards came from
    bankrupt: bool = False


@dataclass
class MEvent:
    kind: str
    player: int | None = None
    sq: int | None = None
    amount: int = 0
    text: str = ""
    data: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- shared rules


class MonopolyRules:
    """Read-only rules worked out from the table state (shared with the guests' mirror)."""

    players: list[MPlayer]
    owner: list
    houses: list[int]
    mortgaged: list[bool]
    current: int
    phase: str
    debt: dict | None
    auction: dict | None
    trade: dict | None
    last_roll: tuple

    # ---- ownership

    def props_of(self, i: int) -> list[int]:
        return [k for k in range(40) if self.owner[k] == i]

    def owns_set(self, i: int, group: str) -> bool:
        return all(self.owner[k] == i for k in GROUPS[group])

    def rent(self, sq: int, dice: int | None = None) -> int:
        """What landing on this square costs right now (0 if unowned or mortgaged)."""
        s = SQUARES[sq]
        o = self.owner[sq]
        if o is None or self.mortgaged[sq] or not s.ownable:
            return 0
        if s.kind == "street":
            n = self.houses[sq]
            if n:
                return s.rents[n]
            full = self.owns_set(o, s.group) and not any(self.mortgaged[k] for k in GROUPS[s.group])
            return s.rents[0] * (2 if full else 1)
        if s.kind == "station":
            count = sum(1 for k in GROUPS["station"] if self.owner[k] == o)
            return STATION_RENTS[count - 1]
        count = sum(1 for k in GROUPS["utility"] if self.owner[k] == o)
        roll = dice if dice is not None else sum(self.last_roll or (0, 0))
        return (4 if count == 1 else 10) * roll

    def net_worth(self, i: int) -> int:
        p = self.players[i]
        if p.bankrupt:
            return 0
        total = p.cash
        for k in self.props_of(i):
            s = SQUARES[k]
            total += s.mortgage if self.mortgaged[k] else s.price
            total += self.houses[k] * s.house_price
        return total

    def houses_and_hotels(self, i: int) -> tuple[int, int]:
        houses = sum(self.houses[k] for k in self.props_of(i) if self.houses[k] < 5)
        hotels = sum(1 for k in self.props_of(i) if self.houses[k] == 5)
        return houses, hotels

    def alive(self) -> list[int]:
        return [k for k, p in enumerate(self.players) if not p.bankrupt]

    # ---- whose move is it?

    def actor(self) -> int | None:
        """The one player the game is waiting on (None while nothing can happen)."""
        if self.phase == "game_over":
            return None
        if self.trade:
            return self.trade["to"]
        if self.phase == "auction" and self.auction:
            return self.auction["active"][self.auction["turn"]] if self.auction["active"] else None
        if self.phase == "debt" and self.debt:
            return self.debt["debtor"]
        if self.phase in ("pre_roll", "post_roll", "buy", "fine_or_chance"):
            return self.current
        return None

    def managing(self, i: int) -> bool:
        """Can player i build/mortgage/trade right now?"""
        if self.trade or self.players[i].bankrupt:
            return False
        if self.phase in MANAGE_PHASES:
            return i == self.current
        return self.phase == "debt" and self.debt is not None and self.debt["debtor"] == i

    # ---- building and mortgages

    def why_not_build(self, i: int, sq: int) -> str | None:
        s = SQUARES[sq]
        if not self.managing(i) or self.phase == "debt":
            return "You can build on your own turn."
        if s.kind != "street" or self.owner[sq] != i:
            return "You can only build on your own streets."
        if not self.owns_set(i, s.group):
            return "You need the whole colour set first."
        if any(self.mortgaged[k] for k in GROUPS[s.group]):
            return "Pay off the mortgages in this set first."
        if self.houses[sq] >= 5:
            return "That street already has a hotel."
        if self.houses[sq] > min(self.houses[k] for k in GROUPS[s.group]):
            return "Build evenly: add houses to the other streets in the set first."
        if self.players[i].cash < s.house_price:
            return f"A house there costs £{s.house_price}."
        return None

    def why_not_sell(self, i: int, sq: int) -> str | None:
        s = SQUARES[sq]
        if not self.managing(i):
            return "Not right now."
        if s.kind != "street" or self.owner[sq] != i or self.houses[sq] == 0:
            return "There are no houses of yours to sell there."
        if self.houses[sq] < max(self.houses[k] for k in GROUPS[s.group]):
            return "Sell evenly: sell from the streets with the most houses first."
        return None

    def why_not_mortgage(self, i: int, sq: int) -> str | None:
        s = SQUARES[sq]
        if not self.managing(i):
            return "Not right now."
        if not s.ownable or self.owner[sq] != i:
            return "You don't own that."
        if self.mortgaged[sq]:
            return "It's already mortgaged."
        if s.kind == "street" and any(self.houses[k] for k in GROUPS[s.group]):
            return "Sell the houses in this set first."
        return None

    def why_not_unmortgage(self, i: int, sq: int) -> str | None:
        s = SQUARES[sq]
        if not self.managing(i) or self.phase == "debt":
            return "You can pay off mortgages on your own turn."
        if self.owner[sq] != i or not self.mortgaged[sq]:
            return "That isn't one of your mortgaged properties."
        if self.players[i].cash < s.unmortgage_cost:
            return f"Paying it off costs £{s.unmortgage_cost}."
        return None

    def raisable(self, i: int) -> int:
        """Cash player i could raise by selling every house and mortgaging everything."""
        total = 0
        for k in self.props_of(i):
            s = SQUARES[k]
            total += self.houses[k] * (s.house_price // 2)
            if not self.mortgaged[k]:
                total += s.mortgage
        return total

    def legal(self, i: int) -> list[str]:
        """The buttons player i may press now (building/mortgaging is checked per square)."""
        acts: list[str] = []
        p = self.players[i]
        if self.phase == "game_over" or p.bankrupt:
            return acts
        if self.trade:
            if self.trade["to"] == i:
                acts += ["accept", "decline"]
            if self.trade["from"] == i:
                acts.append("cancel_trade")
            return acts
        if self.phase == "auction" and self.actor() == i:
            acts.append("pass")
            if p.cash > self.auction["high"]:
                acts.append("bid")
            return acts
        if self.phase == "debt" and self.actor() == i:
            if p.cash >= self.debt["amount"]:
                acts.append("pay")
            acts += ["trade", "bankrupt"]
            return acts
        if i != self.current:
            return acts
        if self.phase == "pre_roll":
            acts += ["roll", "trade"]
            if p.in_jail:
                if p.cash >= JAIL_FINE:
                    acts.append("jail_pay")
                if p.goojf:
                    acts.append("jail_card")
        elif self.phase == "post_roll":
            acts += ["end", "trade"]
        elif self.phase == "buy":
            if p.cash >= SQUARES[p.pos].price:
                acts.append("buy")
            acts.append("auction")
        elif self.phase == "fine_or_chance":
            if p.cash >= 10:
                acts.append("pay_fine")
            acts.append("take_chance")
        return acts

    def standings(self) -> list[int]:
        return sorted(range(len(self.players)), key=lambda k: (self.players[k].bankrupt, -self.net_worth(k)))

    def winners(self) -> list[int]:
        alive = self.alive()
        if not alive:
            return []
        best = max(self.net_worth(k) for k in alive)
        return [k for k in alive if self.net_worth(k) == best]


# --------------------------------------------------------------------------- the game


class MonopolyGame(MonopolyRules):
    def __init__(self, players: list[MPlayer], rng: random.Random | None = None, max_rounds: int = DEFAULT_ROUNDS):
        if not 2 <= len(players) <= 6:
            raise ValueError("Monopoly seats 2-6 players")
        self.players = players
        for k, p in enumerate(players):
            if p.token not in TOKENS or any(q.token == p.token for q in players[:k]):
                p.token = next(t for t in TOKENS if all(q.token != t for q in players[:k]))
        self.rng = rng or random.Random()
        self.max_rounds = max_rounds
        self.owner: list[int | None] = [None] * 40
        self.houses = [0] * 40
        self.mortgaged = [False] * 40
        self.decks = {"chance": list(CHANCE), "chest": list(CHEST)}
        for d in self.decks.values():
            self.rng.shuffle(d)
        self.events: list[MEvent] = []
        self.history: list[MEvent] = []
        self.current = 0
        self.round = 1
        self.phase = "pre_roll"
        self.last_roll: tuple = (0, 0)
        self.doubles = 0
        self.roll_again = False
        self.debt: dict | None = None
        self.auction: dict | None = None
        self.trade: dict | None = None
        self.last_card: Card | None = None
        self.game_over = False
        self.winner: int | None = None
        self._steps: list = []
        self.dice = lambda: (self.rng.randint(1, 6), self.rng.randint(1, 6))
        self._emit("turn", self.current, data={"round": self.round})

    # ------------------------------------------------------------------ plumbing

    def _emit(self, kind: str, player: int | None = None, sq: int | None = None, amount: int = 0, text: str = "",
              data: dict | None = None) -> None:
        ev = MEvent(kind, player, sq, amount, text, data or {})
        self.events.append(ev)
        self.history.append(ev)

    def pop_events(self) -> list[MEvent]:
        ev, self.events = self.events, []
        return ev

    def _require(self, i: int, action: str) -> None:
        if action not in self.legal(i):
            raise RuleError({"roll": "You can't roll right now.", "end": "You can't end your turn yet.",
                             "buy": "You can't buy that right now.", "bid": "You can't bid that.",
                             "pay": "You still don't have enough cash to pay."}.get(action, "You can't do that now."))

    @property
    def waiting(self) -> bool:
        return self.phase in ("buy", "auction", "debt", "fine_or_chance", "game_over") or bool(self.trade)

    def _run(self) -> None:
        """Carry on with the queued steps until one needs a decision."""
        while self._steps and not self.waiting:
            self._steps.pop(0)()
        if not self.waiting and not self._steps and self.phase == "resolving":
            self._after_turn_steps()

    def _after_turn_steps(self) -> None:
        p = self.players[self.current]
        if p.bankrupt:
            self._next_turn()
        elif self.roll_again and not p.in_jail:
            self.phase = "pre_roll"
            self._emit("again", self.current)
        else:
            self.phase = "post_roll"

    # ------------------------------------------------------------------ money

    def _pay(self, i: int, to: int | None, amount: int, reason: str) -> None:
        """A payment that must happen. Pauses for a debt if they're short."""
        if amount <= 0 or self.players[i].bankrupt:
            return
        if self.players[i].cash >= amount:
            self._transfer(i, to, amount, reason)
            return
        self.debt = {"debtor": i, "creditor": to, "amount": amount, "reason": reason}
        self.phase = "debt"
        self._emit("debt", i, amount=amount, text=reason, data={"creditor": to})

    def _transfer(self, i: int | None, to: int | None, amount: int, reason: str) -> None:
        if i is not None:
            self.players[i].cash -= amount
        if to is not None:
            self.players[to].cash += amount
        self._emit("pay", i, amount=amount, text=reason, data={
            "to": to, "cash": {str(k): self.players[k].cash for k in (i, to) if k is not None}})

    def _receive(self, i: int, amount: int, reason: str) -> None:
        self._transfer(None, i, amount, reason)

    # ------------------------------------------------------------------ turns

    def roll(self, i: int) -> None:
        self._require(i, "roll")
        p = self.players[i]
        a, b = self.dice()
        self.last_roll = (a, b)
        double = a == b
        self._emit("roll", i, amount=a + b, data={"dice": [a, b]})
        self.phase = "resolving"
        self.roll_again = False
        if p.in_jail:
            if double:
                p.in_jail, p.jail_turns = False, 0
                self._emit("free", i, text="Rolled doubles!")
                self._steps = [lambda: self._move(i, a + b)]
            else:
                p.jail_turns += 1
                if p.jail_turns >= 3:
                    self._emit("free", i, text="Third try: pay £50 and go.")
                    self._steps = [lambda: self._pay(i, None, JAIL_FINE, "jail fine"),
                                   lambda: self._release(i), lambda: self._move(i, a + b)]
                else:
                    self._emit("stay", i, amount=p.jail_turns)
                    self._steps = []
        elif double and self.doubles == 2:
            self.doubles += 1
            self._emit("speeding", i)
            self._steps = [lambda: self._to_jail(i)]
        else:
            if double:
                self.doubles += 1
                self.roll_again = True
            self._steps = [lambda: self._move(i, a + b)]
        self._run()

    def _release(self, i: int) -> None:
        p = self.players[i]
        if not p.bankrupt:
            p.in_jail, p.jail_turns = False, 0

    def end_turn(self, i: int) -> None:
        self._require(i, "end")
        self._next_turn()

    def _next_turn(self) -> None:
        alive = self.alive()
        if len(alive) <= 1:
            self._finish()
            return
        n = len(self.players)
        k = self.current
        for _ in range(n):
            k = (k + 1) % n
            if not self.players[k].bankrupt:
                break
        if k <= self.current:   # back round to the start: a new round
            self.round += 1
            if self.max_rounds and self.round > self.max_rounds:
                self.round = self.max_rounds
                self._finish()
                return
        self.current = k
        self.doubles = 0
        self.roll_again = False
        self._steps = []
        self.phase = "pre_roll"
        self._emit("turn", k, data={"round": self.round})

    def _finish(self) -> None:
        self.phase = "game_over"
        self.game_over = True
        self._steps = []
        self.debt = self.auction = self.trade = None
        winners = self.winners()
        self.winner = winners[0] if len(winners) == 1 else None
        self._emit("game_over", self.winner)

    # ------------------------------------------------------------------ moving

    def _move(self, i: int, steps: int) -> None:
        p = self.players[i]
        path = [(p.pos + k) % 40 for k in range(1, steps + 1)]
        passed_go = p.pos + steps >= 40
        p.pos = path[-1]
        self._emit("move", i, sq=p.pos, data={"path": path, "how": "walk"})
        if passed_go:
            self._receive(i, GO_SALARY, "passed GO")
        self._land(i)

    def _move_to(self, i: int, target: int, how: str = "walk", collect: bool = True) -> None:
        p = self.players[i]
        if how == "walk":
            steps = (target - p.pos) % 40 or 40
            path = [(p.pos + k) % 40 for k in range(1, steps + 1)]
            passed_go = collect and p.pos + steps >= 40
        elif how == "back":
            steps = (p.pos - target) % 40
            path = [(p.pos - k) % 40 for k in range(1, steps + 1)]
            passed_go = False
        else:
            path, passed_go = [target], False
        p.pos = target
        self._emit("move", i, sq=target, data={"path": path, "how": how})
        if passed_go:
            self._receive(i, GO_SALARY, "passed GO")
        self._land(i)

    def _to_jail(self, i: int) -> None:
        p = self.players[i]
        p.pos, p.in_jail, p.jail_turns = JAIL, True, 0
        self.roll_again = False
        self._emit("jail", i, sq=JAIL)

    def _land(self, i: int) -> None:
        p = self.players[i]
        s = SQUARES[p.pos]
        self._emit("land", i, sq=p.pos)
        if s.ownable:
            owner = self.owner[p.pos]
            if owner is None:
                self.phase = "buy"
                self._emit("offer", i, sq=p.pos, amount=s.price)
            elif owner != i and not self.mortgaged[p.pos]:
                rent = self.rent(p.pos)
                self._emit("rent", i, sq=p.pos, amount=rent, data={"owner": owner})
                self._pay(i, owner, rent, f"rent for {s.name}")
        elif s.kind == "tax":
            self._pay(i, None, s.tax, s.name.lower())
        elif s.kind == "gotojail":
            self._to_jail(i)
        elif s.kind in ("chance", "chest"):
            self._draw(i, s.kind)

    # ------------------------------------------------------------------ cards

    def _draw(self, i: int, deck: str) -> None:
        card = self.decks[deck].pop(0)
        self.last_card = card
        self._emit("card", i, text=card.text, data={"deck": deck, "action": card.action})
        if card.action == "goojf":
            self.players[i].goojf.append(deck)   # kept out of the deck until it's used
            return
        self.decks[deck].append(card)
        a = card.action
        if a == "money":
            if card.amount > 0:
                self._receive(i, card.amount, "card")
            else:
                self._pay(i, None, -card.amount, "card")
        elif a == "move":
            self._steps.insert(0, lambda: self._move_to(i, card.target))
        elif a == "back3":
            self._steps.insert(0, lambda: self._move_to(i, (self.players[i].pos - 3) % 40, "back"))
        elif a == "back_to":
            self._steps.insert(0, lambda: self._move_to(i, card.target, "jump"))
        elif a == "jail":
            self._to_jail(i)
        elif a == "repairs":
            houses, hotels = self.houses_and_hotels(i)
            self._pay(i, None, houses * card.amount + hotels * card.hotel, "repairs")
        elif a == "birthday":
            others = [k for k in self.alive() if k != i]
            self._steps[0:0] = [(lambda k=k: self._pay(k, i, card.amount, "birthday present")) for k in others]
        elif a == "fine_or_chance":
            self.phase = "fine_or_chance"

    def pay_fine(self, i: int) -> None:
        self._require(i, "pay_fine")
        self.phase = "resolving"
        self._transfer(i, None, 10, "fine")
        self._run()

    def take_chance(self, i: int) -> None:
        self._require(i, "take_chance")
        self.phase = "resolving"
        self._steps.insert(0, lambda: self._draw(i, "chance"))
        self._run()

    # ------------------------------------------------------------------ jail

    def jail_pay(self, i: int) -> None:
        self._require(i, "jail_pay")
        self._transfer(i, None, JAIL_FINE, "jail fine")
        self.players[i].in_jail, self.players[i].jail_turns = False, 0
        self._emit("free", i, text="Paid £50.")

    def jail_card(self, i: int) -> None:
        self._require(i, "jail_card")
        deck = self.players[i].goojf.pop(0)
        card = next(c for c in (CHANCE if deck == "chance" else CHEST) if c.action == "goojf")
        self.decks[deck].append(card)
        self.players[i].in_jail, self.players[i].jail_turns = False, 0
        self._emit("free", i, text="Used a Get Out of Jail Free card.")

    # ------------------------------------------------------------------ buying and auctions

    def buy(self, i: int) -> None:
        self._require(i, "buy")
        sq = self.players[i].pos
        self._transfer(i, None, SQUARES[sq].price, f"bought {SQUARES[sq].name}")
        self.owner[sq] = i
        self._emit("buy", i, sq=sq, amount=SQUARES[sq].price)
        self.phase = "resolving"
        self._run()

    def start_auction(self, i: int) -> None:
        self._require(i, "auction")
        sq = self.players[i].pos
        n = len(self.players)
        order = [(i + k) % n for k in range(n)]
        active = [k for k in order if not self.players[k].bankrupt and self.players[k].cash > 0]
        self.auction = {"sq": sq, "high": 0, "bidder": None, "active": active, "turn": 0}
        self.phase = "auction"
        self._emit("auction", i, sq=sq)
        self._auction_check()

    def bid(self, i: int, amount: int) -> None:
        self._require(i, "bid")
        a = self.auction
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= a["high"]:
            raise RuleError(f"Bid more than £{a['high']}.")
        if amount > self.players[i].cash:
            raise RuleError(f"You only have £{self.players[i].cash}.")
        a["high"], a["bidder"] = amount, i
        self._emit("bid", i, sq=a["sq"], amount=amount)
        self._auction_advance()

    def pass_bid(self, i: int) -> None:
        self._require(i, "pass")
        a = self.auction
        k = a["active"].index(i)
        a["active"].pop(k)
        self._emit("bid_pass", i, sq=a["sq"])
        a["turn"] = k % len(a["active"]) if a["active"] else 0
        self._auction_check()

    def _auction_advance(self) -> None:
        a = self.auction
        a["turn"] = (a["turn"] + 1) % len(a["active"])
        self._auction_check()

    def _auction_check(self) -> None:
        """Move the auction on to the next player who can bid, or finish it."""
        a = self.auction
        while a["active"] and not (len(a["active"]) == 1 and a["active"][0] == a["bidder"]):
            k = a["active"][a["turn"]]
            if k == a["bidder"]:
                a["turn"] = (a["turn"] + 1) % len(a["active"])   # the high bidder waits for the others
                continue
            if self.players[k].cash > a["high"]:
                return   # their turn to bid or pass
            a["active"].pop(a["turn"])   # can't afford to outbid: out automatically
            self._emit("bid_pass", k, sq=a["sq"])
            if a["active"]:
                a["turn"] %= len(a["active"])
        sq, winner, price = a["sq"], a["bidder"], a["high"]
        self.auction = None
        if winner is not None:
            self._transfer(winner, None, price, f"won {SQUARES[sq].name}")
            self.owner[sq] = winner
        self._emit("auction_end", winner, sq=sq, amount=price)
        self.phase = "resolving"
        self._run()

    # ------------------------------------------------------------------ houses and mortgages

    def build(self, i: int, sq: int) -> None:
        why = self.why_not_build(i, sq)
        if why:
            raise RuleError(why)
        self.players[i].cash -= SQUARES[sq].house_price
        self.houses[sq] += 1
        self._emit("build", i, sq=sq, amount=SQUARES[sq].house_price,
                   data={"houses": self.houses[sq], "cash": self.players[i].cash})

    def sell(self, i: int, sq: int) -> None:
        why = self.why_not_sell(i, sq)
        if why:
            raise RuleError(why)
        value = SQUARES[sq].house_price // 2
        self.players[i].cash += value
        self.houses[sq] -= 1
        self._emit("sell", i, sq=sq, amount=value, data={"houses": self.houses[sq], "cash": self.players[i].cash})

    def mortgage(self, i: int, sq: int) -> None:
        why = self.why_not_mortgage(i, sq)
        if why:
            raise RuleError(why)
        self.mortgaged[sq] = True
        self.players[i].cash += SQUARES[sq].mortgage
        self._emit("mortgage", i, sq=sq, amount=SQUARES[sq].mortgage, data={"cash": self.players[i].cash})

    def unmortgage(self, i: int, sq: int) -> None:
        why = self.why_not_unmortgage(i, sq)
        if why:
            raise RuleError(why)
        self.mortgaged[sq] = False
        self.players[i].cash -= SQUARES[sq].unmortgage_cost
        self._emit("unmortgage", i, sq=sq, amount=SQUARES[sq].unmortgage_cost, data={"cash": self.players[i].cash})

    # ------------------------------------------------------------------ debts and bankruptcy

    def pay_debt(self, i: int) -> None:
        self._require(i, "pay")
        d = self.debt
        self.debt = None
        self.phase = "resolving"
        self._transfer(i, d["creditor"], d["amount"], d["reason"])
        self._run()

    def go_bankrupt(self, i: int) -> None:
        self._require(i, "bankrupt")
        d = self.debt
        self.debt = None
        p = self.players[i]
        to = d["creditor"]
        if to is not None and self.players[to].bankrupt:
            to = None
        cash = p.cash
        for k in self.props_of(i):
            cash += self.houses[k] * (SQUARES[k].house_price // 2)   # the bank buys back the buildings
            self.houses[k] = 0
            if to is None:
                self.owner[k], self.mortgaged[k] = None, False
            else:
                self.owner[k] = to
        if to is not None:
            self.players[to].cash += max(0, cash)
            self.players[to].goojf += p.goojf
        else:
            for deck in p.goojf:
                card = next(c for c in (CHANCE if deck == "chance" else CHEST) if c.action == "goojf")
                self.decks[deck].append(card)
        p.goojf = []
        p.cash, p.bankrupt, p.in_jail = 0, True, False
        self._emit("bankrupt", i, data={"to": to, "cash": {str(to): self.players[to].cash} if to is not None else {}})
        if self.trade and i in (self.trade["from"], self.trade["to"]):
            self.trade = None
        if len(self.alive()) <= 1:
            self._finish()
            return
        if i == self.current:
            self._steps = []
            self.phase = "resolving"
            self._next_turn()
        else:
            self.phase = "resolving"
            self._run()

    # ------------------------------------------------------------------ trading

    def propose_trade(self, i: int, to: int, give: list[int], get: list[int], give_cash: int = 0,
                      get_cash: int = 0) -> None:
        """Offer `give` properties (+ cash) for `get` properties (+ cash). The other player answers."""
        if "trade" not in self.legal(i):
            raise RuleError("You can trade on your own turn (or while raising money).")
        if not isinstance(to, int) or not 0 <= to < len(self.players) or to == i or self.players[to].bankrupt:
            raise RuleError("Pick someone to trade with.")
        for name, value in (("give", give), ("get", get)):
            if not isinstance(value, list) or not all(isinstance(k, int) and 0 <= k < 40 for k in value):
                raise RuleError("That trade doesn't make sense.")
        give, get = sorted(set(give)), sorted(set(get))
        if not all(isinstance(c, int) and not isinstance(c, bool) and c >= 0 for c in (give_cash, get_cash)):
            raise RuleError("Cash in a trade can't be negative.")
        if not (give or get or give_cash or get_cash):
            raise RuleError("Put something in the trade.")
        for k in give:
            if self.owner[k] != i:
                raise RuleError(f"You don't own {SQUARES[k].name}.")
        for k in get:
            if self.owner[k] != to:
                raise RuleError(f"They don't own {SQUARES[k].name}.")
        for k in give + get:
            if SQUARES[k].kind == "street" and any(self.houses[m] for m in GROUPS[SQUARES[k].group]):
                raise RuleError(f"Sell the houses in {SQUARES[k].name}'s set before trading it.")
        if give_cash > self.players[i].cash:
            raise RuleError(f"You only have £{self.players[i].cash}.")
        if get_cash > self.players[to].cash:
            raise RuleError(f"They only have £{self.players[to].cash}.")
        self.trade = {"from": i, "to": to, "give": give, "get": get, "give_cash": give_cash, "get_cash": get_cash}
        self._emit("trade_offer", i, data=dict(self.trade))

    def answer_trade(self, i: int, accept: bool) -> None:
        if not self.trade or self.trade["to"] != i:
            raise RuleError("There's no trade waiting for you.")
        t = self.trade
        self.trade = None
        a, b = t["from"], t["to"]
        ok = accept and self.players[a].cash >= t["give_cash"] and self.players[b].cash >= t["get_cash"] and \
            all(self.owner[k] == a for k in t["give"]) and all(self.owner[k] == b for k in t["get"])
        if ok:
            for k in t["give"]:
                self.owner[k] = b
            for k in t["get"]:
                self.owner[k] = a
            self.players[a].cash += t["get_cash"] - t["give_cash"]
            self.players[b].cash += t["give_cash"] - t["get_cash"]
        self._emit("trade_done", a, data={**t, "accepted": ok, "cash": {str(a): self.players[a].cash,
                                                                         str(b): self.players[b].cash}})

    def cancel_trade(self, i: int) -> None:
        if not self.trade or self.trade["from"] != i:
            raise RuleError("You have no trade waiting.")
        t = self.trade
        self.trade = None
        self._emit("trade_done", i, data={**t, "accepted": False, "cancelled": True})

    # ------------------------------------------------------------------ one entry point for moves

    def act(self, i: int, action: str, **kw) -> None:
        """Do a move by name (used by the network and the computers)."""
        simple = {"roll": self.roll, "end": self.end_turn, "buy": self.buy, "auction": self.start_auction,
                  "pass": self.pass_bid, "pay": self.pay_debt, "bankrupt": self.go_bankrupt,
                  "jail_pay": self.jail_pay, "jail_card": self.jail_card, "pay_fine": self.pay_fine,
                  "take_chance": self.take_chance, "accept": lambda k: self.answer_trade(k, True),
                  "decline": lambda k: self.answer_trade(k, False), "cancel_trade": self.cancel_trade}
        per_square = {"build": self.build, "sell": self.sell, "mortgage": self.mortgage,
                      "unmortgage": self.unmortgage}
        if action in simple:
            simple[action](i)
        elif action in per_square:
            sq = kw.get("sq")
            if not isinstance(sq, int) or isinstance(sq, bool) or not 0 <= sq < 40:
                raise RuleError("Pick a property.")
            per_square[action](i, sq)
        elif action == "bid":
            self.bid(i, kw.get("amount"))
        elif action == "trade":
            self.propose_trade(i, kw.get("to"), kw.get("give", []), kw.get("get", []), kw.get("give_cash", 0),
                               kw.get("get_cash", 0))
        else:
            raise RuleError("Unknown move.")


def set_color(sq: int):
    return SETS.get(SQUARES[sq].group)
