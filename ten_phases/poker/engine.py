"""Texas Hold'em, no limit.

  * 52 cards: 2-10, J, Q, K, A in four colours (the colours are the suits)
  * Everyone starts with 50 chips. Blinds start at 1/2 and double every 5 hands
  * 15 hands per game, or until one player has every chip. Most chips wins
  * Each player gets two cards; five shared cards come out as the flop (3), turn and river
  * Bet as much as you like (up to all your chips) on every betting round
  * Best five-card hand from your two cards plus the five shared ones wins the pot.
    Side pots handle players who are all in for less
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations

from ..cards import COLORS, Card, Kind

STARTING_CHIPS = 50
HANDS_PER_GAME = 15
BLIND_LEVELS = ((1, 2), (2, 4), (4, 8), (8, 16))
HANDS_PER_LEVEL = 5
STREETS = ("preflop", "flop", "turn", "river")


class RuleError(Exception):
    """An illegal move. The message is shown to the player."""


RANK_LABELS = {11: "J", 12: "Q", 13: "K", 14: "A"}
RANK_NAMES = {2: "TWO", 3: "THREE", 4: "FOUR", 5: "FIVE", 6: "SIX", 7: "SEVEN", 8: "EIGHT", 9: "NINE", 10: "TEN",
              11: "JACK", 12: "QUEEN", 13: "KING", 14: "ACE"}
PLURALS = {6: "SIXES"}


@dataclass(eq=False)
class PokerCard(Card):
    """A poker card: value 2-14 (2-10, J, Q, K, A); drawn with letters for J/Q/K/A."""

    @property
    def rank_label(self) -> str:
        return RANK_LABELS.get(self.value, str(self.value))

    def label(self) -> str:
        return f"{self.color.value.title()} {RANK_NAMES[self.value].title()}"


def poker_card(color, value: int) -> PokerCard:
    return PokerCard(Kind.NUMBER, color, value)


def build_deck(rng: random.Random) -> list[PokerCard]:
    deck = [poker_card(c, v) for c in COLORS for v in range(2, 15)]
    rng.shuffle(deck)
    return deck


# --------------------------------------------------------------------------- hand ranking

HIGH_CARD, PAIR, TWO_PAIR, TRIPS, STRAIGHT, FLUSH, FULL_HOUSE, QUADS, STRAIGHT_FLUSH = range(9)
CATEGORY_NAMES = ("HIGH CARD", "PAIR", "TWO PAIR", "THREE OF A KIND", "STRAIGHT", "FLUSH", "FULL HOUSE",
                  "FOUR OF A KIND", "STRAIGHT FLUSH")


def _straight_high(values) -> int:
    """Top card of the best straight in these values (0 if none). The ace also plays low (A-2-3-4-5)."""
    have = set(values)
    if 14 in have:
        have.add(1)
    for high in range(14, 4, -1):
        if all(high - k in have for k in range(5)):
            return high
    return 0


def evaluate(cards) -> tuple:
    """Score the best five-card hand among 5-7 cards. Bigger tuples are better hands."""
    vals = sorted((c.value for c in cards), reverse=True)
    suits: dict = {}
    for c in cards:
        suits.setdefault(c.color, []).append(c.value)
    flush = next((sorted(v, reverse=True) for v in suits.values() if len(v) >= 5), None)
    if flush:
        high = _straight_high(flush)
        if high:
            return (STRAIGHT_FLUSH, high)
    groups = sorted(Counter(vals).items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    if groups[0][1] == 4:
        quad = groups[0][0]
        return (QUADS, quad, max(v for v in vals if v != quad))
    trips = [v for v, n in groups if n == 3]
    pairs = [v for v, n in groups if n == 2]
    if trips and (len(trips) > 1 or pairs):
        return (FULL_HOUSE, trips[0], max(trips[1:] + pairs))
    if flush:
        return (FLUSH, *flush[:5])
    high = _straight_high(vals)
    if high:
        return (STRAIGHT, high)
    if trips:
        return (TRIPS, trips[0], *[v for v in vals if v != trips[0]][:2])
    if len(pairs) >= 2:
        a, b = pairs[0], pairs[1]
        return (TWO_PAIR, a, b, max(v for v in vals if v not in (a, b)))
    if pairs:
        return (PAIR, pairs[0], *[v for v in vals if v != pairs[0]][:3])
    return (HIGH_CARD, *vals[:5])


def best_five(cards) -> list:
    """The five cards that make the best hand among 5-7 cards."""
    cards = list(cards)
    if len(cards) <= 5:
        return cards
    return list(max(combinations(cards, 5), key=evaluate))


def key_cards(cards) -> list:
    """The cards that make the hand what it is (the pair, both pairs, the straight...), without kickers."""
    best = best_five(cards)
    if len(best) < 5:
        return []
    score = evaluate(best)
    cat = score[0]
    if cat in (PAIR, TRIPS, QUADS):
        values = {score[1]}
    elif cat in (TWO_PAIR, FULL_HOUSE):
        values = {score[1], score[2]}
    elif cat == HIGH_CARD:
        return [max(best, key=lambda c: c.value)]
    else:
        return best   # straights and flushes use all five
    return [c for c in best if c.value in values]


def plural(value: int) -> str:
    return PLURALS.get(value, RANK_NAMES[value] + "S")


def describe(score: tuple) -> str:
    """'PAIR OF SEVENS', 'FLUSH', 'ACE HIGH'..."""
    cat = score[0]
    if cat == STRAIGHT_FLUSH:
        return "ROYAL FLUSH" if score[1] == 14 else "STRAIGHT FLUSH"
    if cat == QUADS:
        return f"FOUR {plural(score[1])}"
    if cat == FULL_HOUSE:
        return f"FULL HOUSE, {plural(score[1])} FULL"
    if cat == FLUSH:
        return f"FLUSH, {RANK_NAMES[score[1]]} HIGH"
    if cat == STRAIGHT:
        return f"STRAIGHT TO THE {RANK_NAMES[score[1]]}" if score[1] > 5 else "STRAIGHT TO THE FIVE"
    if cat == TRIPS:
        return f"THREE {plural(score[1])}"
    if cat == TWO_PAIR:
        return f"TWO PAIR, {plural(score[1])} AND {plural(score[2])}"
    if cat == PAIR:
        return f"PAIR OF {plural(score[1])}"
    return f"{RANK_NAMES[score[1]]} HIGH"


# --------------------------------------------------------------------------- players and events


@dataclass
class PokerPlayer:
    name: str
    is_human: bool = False
    difficulty: str | None = None
    chips: int = STARTING_CHIPS
    hole: list[PokerCard] = field(default_factory=list)
    bet: int = 0               # put in on the current betting round
    total_in: int = 0          # put in this hand, all rounds
    folded: bool = False
    all_in: bool = False
    acted: bool = False        # has acted since the last raise
    in_hand: bool = False      # was dealt in this hand
    net: int = 0               # chips won or lost this game
    results: list[str] = field(default_factory=list)   # per hand: won, lost, fold, split
    last_action: str = ""

    @property
    def live(self) -> bool:
        """Still in the hand (dealt in and hasn't folded)."""
        return self.in_hand and not self.folded

    @property
    def can_act(self) -> bool:
        return self.live and not self.all_in


@dataclass
class PokerEvent:
    kind: str     # round_start, blind, deal, turn, fold, check, call, bet, raise, board, showdown, win,
                  # refund, settled, game_over
    player: int | None = None
    cards: list[PokerCard] = field(default_factory=list)
    amount: int = 0
    name: str = ""            # hand name for showdown/win, street name for board
    hidden: bool = False      # a face-down deal (only its owner sees the cards)


# --------------------------------------------------------------------------- shared rules (engine + network mirror)


class PokerRules:
    """Move legality, worked out from table state alone, so the guests' mirror can share it."""

    players: list[PokerPlayer]
    current: int | None
    current_bet: int
    min_raise: int
    blinds: tuple[int, int]
    phase: str

    def to_call(self, i: int) -> int:
        p = self.players[i]
        return max(0, min(self.current_bet - p.bet, p.chips))

    def pot_total(self) -> int:
        return sum(p.total_in for p in self.players)

    def raise_range(self, i: int) -> tuple[int, int] | None:
        """(smallest, largest) 'raise to' totals for this betting round, or None if raising isn't allowed.

        The largest is always all in. When a player can't afford a full raise, all in is the only raise."""
        p = self.players[i]
        if p.chips <= self.current_bet - p.bet:
            return None   # calling already puts them all in
        if not any(k != i and q.can_act for k, q in enumerate(self.players)):
            return None   # everyone else is all in or folded: nobody could call a raise
        most = p.bet + p.chips
        least = max(self.current_bet + self.min_raise, self.blinds[1]) if self.current_bet else self.blinds[1]
        least = min(least, most)
        return least, most

    def legal_actions(self, i: int) -> list[str]:
        if self.phase != "playing" or self.current != i:
            return []
        acts = ["fold"]
        acts.append("call" if self.to_call(i) > 0 else "check")
        if self.raise_range(i):
            acts.append("raise")
        return acts

    def standings(self) -> list[int]:
        return sorted(range(len(self.players)), key=lambda k: -self.players[k].chips)

    def winners(self) -> list[int]:
        best = max(p.chips for p in self.players)
        return [k for k, p in enumerate(self.players) if p.chips == best]


# --------------------------------------------------------------------------- the game


class PokerGame(PokerRules):
    def __init__(self, players: list[PokerPlayer], rng: random.Random | None = None,
                 hands_per_game: int = HANDS_PER_GAME):
        if not 2 <= len(players) <= 6:
            raise ValueError("Poker seats 2-6 players")
        self.players = players
        self.rng = rng or random.Random()
        self.hands_per_game = hands_per_game
        self.events: list[PokerEvent] = []
        self.history: list[PokerEvent] = []
        self.deck: list[PokerCard] = []
        self.board: list[PokerCard] = []
        self.round = 0
        self.button = self.rng.randrange(len(players)) - 1   # moves on to a real seat when the first hand starts
        self.sb_seat: int | None = None
        self.bb_seat: int | None = None
        self.blinds = BLIND_LEVELS[0]
        self.street = "preflop"
        self.phase = "playing"       # playing, settled, game_over
        self.current: int | None = None
        self.current_bet = 0
        self.min_raise = self.blinds[1]
        self.revealed: set[int] = set()
        self.last_wins: list[dict] = []   # {"player", "amount", "hand"} for the hand just finished
        self.game_over = False
        self._start_round()

    # ------------------------------------------------------------------ helpers

    def _emit(self, ev: PokerEvent) -> None:
        self.events.append(ev)
        self.history.append(ev)

    def pop_events(self) -> list[PokerEvent]:
        ev, self.events = self.events, []
        return ev

    def seated(self) -> list[int]:
        """Players who still have chips (or are in the current hand)."""
        return [k for k, p in enumerate(self.players) if p.chips > 0 or p.in_hand]

    def _next_seat(self, start: int, ok) -> int | None:
        n = len(self.players)
        for step in range(1, n + 1):
            k = (start + step) % n
            if ok(k):
                return k
        return None

    def _put_in(self, i: int, amount: int) -> int:
        p = self.players[i]
        amount = max(0, min(amount, p.chips))
        p.chips -= amount
        p.bet += amount
        p.total_in += amount
        if p.chips == 0:
            p.all_in = True
        return amount

    def hand_score(self, i: int) -> tuple:
        return evaluate(self.players[i].hole + self.board)

    # ------------------------------------------------------------------ hands

    def _start_round(self) -> None:
        self.round += 1
        with_chips = [k for k, p in enumerate(self.players) if p.chips > 0]
        if self.round > self.hands_per_game or len(with_chips) < 2:
            self._finish()
            return
        self.blinds = BLIND_LEVELS[min(len(BLIND_LEVELS) - 1, (self.round - 1) // HANDS_PER_LEVEL)]
        self.phase = "playing"
        self.street = "preflop"
        self.board = []
        self.revealed = set()
        self.last_wins = []
        self.deck = build_deck(self.rng)
        for k, p in enumerate(self.players):
            p.hole, p.bet, p.total_in = [], 0, 0
            p.folded = p.all_in = p.acted = False
            p.in_hand = p.chips > 0
            p.last_action = ""
        has_chips = lambda k: self.players[k].in_hand  # noqa: E731
        self.button = self._next_seat(self.button, has_chips)
        if len(with_chips) == 2:   # heads up: the button posts the small blind and acts first before the flop
            self.sb_seat = self.button
        else:
            self.sb_seat = self._next_seat(self.button, has_chips)
        self.bb_seat = self._next_seat(self.sb_seat, has_chips)
        self._emit(PokerEvent("round_start", player=self.button, amount=self.round))
        small, big = self.blinds
        for seat, amount, label in ((self.sb_seat, small, "small"), (self.bb_seat, big, "big")):
            paid = self._put_in(seat, amount)
            self.players[seat].last_action = f"{label.upper()} BLIND"
            self._emit(PokerEvent("blind", player=seat, amount=paid, name=label))
        self.current_bet = big
        self.min_raise = big
        order = [self._next_seat(self.sb_seat - 1, has_chips)]
        while len(order) < len(with_chips):
            order.append(self._next_seat(order[-1], has_chips))
        for _ in range(2):
            for k in order:
                self.players[k].hole.append(self.deck.pop())
        for k in order:
            self._emit(PokerEvent("deal", player=k, cards=list(self.players[k].hole), hidden=True))
        self.current = self.bb_seat
        self._advance()

    def _finish(self) -> None:
        self.round = min(self.round, self.hands_per_game)
        self.phase = "game_over"
        self.game_over = True
        self.current = None
        for p in self.players:
            p.in_hand = False
        self._emit(PokerEvent("game_over"))

    def next_round(self) -> None:
        if self.phase != "settled":
            raise RuleError("The hand isn't over yet.")
        self._start_round()

    def end_now(self) -> None:
        """Stop after the current hand (a solo player who's out of chips doesn't have to watch)."""
        if self.phase == "settled":
            self._finish()

    # ------------------------------------------------------------------ betting

    def act(self, i: int, action: str, amount: int = 0) -> None:
        """action: fold, check, call or raise (amount = the total to raise to on this betting round)."""
        if action not in self.legal_actions(i):
            if self.phase != "playing" or self.current != i:
                raise RuleError("It isn't your turn.")
            raise RuleError({"check": "You can't check - there's a bet to call.",
                             "call": "There's nothing to call - you can check.",
                             "raise": "You can't raise right now."}.get(action, "You can't do that."))
        p = self.players[i]
        if action == "fold":
            p.folded = True
            p.last_action = "FOLD"
            self._emit(PokerEvent("fold", player=i))
        elif action == "check":
            p.last_action = "CHECK"
            self._emit(PokerEvent("check", player=i))
        elif action == "call":
            paid = self._put_in(i, self.current_bet - p.bet)
            p.last_action = "ALL IN" if p.all_in else f"CALL {paid}"
            self._emit(PokerEvent("call", player=i, amount=paid))
        else:
            least, most = self.raise_range(i)
            if not isinstance(amount, int) or not (least <= amount <= most):
                raise RuleError(f"Raise to between {least} and {most} chips." if least < most
                                else f"You can only go all in ({most}).")
            kind = "raise" if self.current_bet else "bet"
            raise_by = amount - self.current_bet
            self._put_in(i, amount - p.bet)
            if raise_by >= self.min_raise:
                self.min_raise = raise_by
            self.current_bet = max(self.current_bet, amount)
            for k, q in enumerate(self.players):
                if k != i and q.can_act:
                    q.acted = False
            p.last_action = "ALL IN" if p.all_in else (f"RAISE TO {amount}" if kind == "raise" else f"BET {amount}")
            self._emit(PokerEvent(kind, player=i, amount=amount))
        p.acted = True
        self._advance()

    def _advance(self) -> None:
        live = [k for k, p in enumerate(self.players) if p.live]
        if len(live) == 1:
            self._award_uncontested(live[0])
            return
        nxt = self._next_seat(self.current, lambda k: self.players[k].can_act and (
            not self.players[k].acted or self.players[k].bet < self.current_bet))
        if nxt is not None:
            self.current = nxt
            self._emit(PokerEvent("turn", player=nxt))
            return
        self._end_street()

    def _end_street(self) -> None:
        for p in self.players:
            p.bet = 0
            p.acted = False
        self.current_bet = 0
        self.min_raise = self.blinds[1]
        if self.street == "river":
            self._showdown()
            return
        self.street = STREETS[STREETS.index(self.street) + 1]
        cards = [self.deck.pop() for _ in range(3 if self.street == "flop" else 1)]
        self.board += cards
        self._emit(PokerEvent("board", cards=cards, name=self.street))
        can_act = [k for k, p in enumerate(self.players) if p.can_act]
        if len(can_act) < 2:
            # Everyone (or everyone but one) is all in: show the hands and run out the board.
            self._reveal_live()
            self._end_street()
            return
        self.current = self.button
        self._advance()

    def _reveal_live(self) -> None:
        new = [k for k, p in enumerate(self.players) if p.live and k not in self.revealed]
        for k in new:
            self.revealed.add(k)
            self._emit(PokerEvent("showdown", player=k, cards=list(self.players[k].hole),
                                  name=describe(evaluate(self.players[k].hole + self.board))
                                  if len(self.board) >= 3 else ""))

    # ------------------------------------------------------------------ paying out

    def _award_uncontested(self, winner: int) -> None:
        pot = self.pot_total()
        self.players[winner].chips += pot
        self.last_wins = [{"player": winner, "amount": pot, "hand": ""}]
        self._emit(PokerEvent("win", player=winner, amount=pot))
        self._settle({winner})

    def _showdown(self) -> None:
        self.current = None
        self._reveal_live()
        scores = {k: evaluate(p.hole + self.board) for k, p in enumerate(self.players) if p.live}
        levels = sorted({p.total_in for p in self.players if p.total_in > 0})
        prev = carry = 0
        won: dict[int, int] = {}
        for level in levels:
            contributors = [k for k, p in enumerate(self.players) if p.total_in >= level]
            amount = (level - prev) * len(contributors) + carry
            prev, carry = level, 0
            eligible = [k for k in contributors if k in scores]
            if not eligible:
                carry = amount   # only folded players put this much in: it joins the next pot up
                continue
            if len(contributors) == 1:
                # Nobody matched this part of the bet: it goes straight back.
                self.players[eligible[0]].chips += amount
                self._emit(PokerEvent("refund", player=eligible[0], amount=amount))
                continue
            best = max(scores[k] for k in eligible)
            top = [k for k in eligible if scores[k] == best]
            share, odd = divmod(amount, len(top))
            # Odd chips go to the first winner after the button.
            order = sorted(top, key=lambda k: (k - self.button - 1) % len(self.players))
            for n, k in enumerate(order):
                won[k] = won.get(k, 0) + share + (1 if n < odd else 0)
        if carry:   # (can't really happen, but never lose chips)
            best = max(scores, key=lambda k: scores[k])
            won[best] = won.get(best, 0) + carry
        self.last_wins = []
        for k, amount in won.items():
            self.players[k].chips += amount
            name = describe(scores[k])
            self.last_wins.append({"player": k, "amount": amount, "hand": name})
            self._emit(PokerEvent("win", player=k, amount=amount, name=name))
        self._settle(set(won))

    def _settle(self, winners: set[int]) -> None:
        self.phase = "settled"
        self.current = None
        split = len(winners) > 1
        for k, p in enumerate(self.players):
            p.net = p.chips - STARTING_CHIPS
            if not p.in_hand:
                continue
            p.results.append("split" if k in winners and split else "won" if k in winners
                             else "fold" if p.folded else "lost")
        self._emit(PokerEvent("settled"))
