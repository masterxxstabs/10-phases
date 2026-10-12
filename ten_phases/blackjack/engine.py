"""Blackjack rules.

A computer dealer plays against every player at the table.
  * 4-deck shoe: A, 2-10, J, Q, K in four colours (the colours are the suits)
  * Bet 1-10 chips each hand; everyone starts with 50 chips; 10 hands per game
  * Blackjack pays 3:2, other wins pay 1:1, ties push
  * Dealer peeks for blackjack, hits soft 16 and below, stands on all 17s
  * Double down on any first two cards; split a pair once (split aces get one card each)
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from ..cards import COLORS, Card, Kind

STARTING_CHIPS = 50
MIN_BET, MAX_BET = 1, 10
HANDS_PER_GAME = 10
DECKS = 4
RESHUFFLE_AT = 0.25    # reshuffle when this share of the shoe is left


class RuleError(Exception):
    """An illegal move. The message is shown to the player."""


RANK_LABELS = {1: "A", 11: "J", 12: "Q", 13: "K"}


@dataclass(eq=False)
class BJCard(Card):
    """A blackjack card: value 1-13 (A, 2-10, J, Q, K); drawn with letters for A/J/Q/K."""

    @property
    def rank_label(self) -> str:
        return RANK_LABELS.get(self.value, str(self.value))

    @property
    def points(self) -> int:  # blackjack value; aces count 1 here (see hand_value)
        return min(self.value, 10)

    def label(self) -> str:
        names = {1: "Ace", 11: "Jack", 12: "Queen", 13: "King"}
        return f"{self.color.value.title()} {names.get(self.value, self.value)}"


def bj_card(color, value: int) -> BJCard:
    return BJCard(Kind.NUMBER, color, value)


def hand_value(cards) -> tuple[int, bool]:
    """(best total, soft?) — soft means an ace is counting as 11."""
    total = sum(min(c.value, 10) for c in cards)
    if any(c.value == 1 for c in cards) and total + 10 <= 21:
        return total + 10, True
    return total, False


def is_blackjack(cards) -> bool:
    return len(cards) == 2 and hand_value(cards)[0] == 21


@dataclass
class Hand:
    cards: list[BJCard] = field(default_factory=list)
    bet: int = 0
    doubled: bool = False
    split: bool = False        # came from a split (so a 21 isn't a blackjack)
    stood: bool = False
    result: str | None = None  # win, blackjack, push, lose, bust
    payout: int = 0            # chips returned (bet included)

    @property
    def value(self) -> int:
        return hand_value(self.cards)[0]

    @property
    def soft(self) -> bool:
        return hand_value(self.cards)[1]

    @property
    def busted(self) -> bool:
        return self.value > 21

    @property
    def natural(self) -> bool:
        return not self.split and is_blackjack(self.cards)

    @property
    def done(self) -> bool:
        return self.stood or self.busted or self.value == 21


@dataclass
class BJPlayer:
    name: str
    is_human: bool = False
    difficulty: str | None = None
    chips: int = STARTING_CHIPS
    hands: list[Hand] = field(default_factory=list)
    bet: int | None = None     # chosen for the coming hand
    net: int = 0               # chips won/lost this game
    results: list[str] = field(default_factory=list)

    @property
    def out(self) -> bool:
        return self.chips < MIN_BET and not self.hands


@dataclass
class BJEvent:
    kind: str          # bet, deal, hit, double, split, stand, bust, blackjack, turn, reveal, dealer_hit,
                       # settle, round_start, shuffle, game_over
    player: int | None = None   # None = dealer
    hand: int = 0
    card: BJCard | None = None
    hidden: bool = False        # dealer's hole card
    amount: int = 0
    result: str | None = None


def build_shoe(rng: random.Random) -> list[BJCard]:
    shoe = [bj_card(c, v) for _ in range(DECKS) for c in COLORS for v in range(1, 14)]
    rng.shuffle(shoe)
    return shoe


class BlackjackGame:
    def __init__(self, players: list[BJPlayer], rng: random.Random | None = None, hands_per_game: int = HANDS_PER_GAME):
        if not 1 <= len(players) <= 6:
            raise ValueError("Blackjack seats 1-6 players")
        self.players = players
        self.rng = rng or random.Random()
        self.shoe = build_shoe(self.rng)
        self.seen: list[BJCard] = []     # face-up cards since the last shuffle (for card counters)
        self.dealer: list[BJCard] = []
        self.hole_hidden = True
        self.events: list[BJEvent] = []
        self.history: list[BJEvent] = []
        self.hands_per_game = hands_per_game
        self.round = 0
        self.phase = "betting"           # betting, playing, settled, game_over
        self.turn: tuple[int, int] | None = None
        self.game_over = False
        self._start_round()

    # ------------------------------------------------------------------ helpers

    def _emit(self, ev: BJEvent) -> None:
        self.events.append(ev)
        self.history.append(ev)

    def pop_events(self) -> list[BJEvent]:
        ev, self.events = self.events, []
        return ev

    def active(self) -> list[int]:
        """Players who can still play (have chips for at least the minimum bet)."""
        return [i for i, p in enumerate(self.players) if p.chips >= MIN_BET or p.hands]

    def _draw(self, face_up: bool = True) -> BJCard:
        if not self.shoe:
            self._reshuffle()
        card = self.shoe.pop()
        if face_up:
            self.seen.append(card)
        return card

    def _reshuffle(self) -> None:
        self.shoe = build_shoe(self.rng)
        self.seen = []
        self._emit(BJEvent("shuffle"))

    @property
    def dealer_up(self) -> BJCard | None:
        return self.dealer[0] if self.dealer else None

    def standings(self) -> list[int]:
        return sorted(range(len(self.players)), key=lambda i: -self.players[i].chips)

    def winners(self) -> list[int]:
        best = max(p.chips for p in self.players)
        return [i for i, p in enumerate(self.players) if p.chips == best]

    def max_bet(self, i: int) -> int:
        return max(0, min(MAX_BET, self.players[i].chips))

    # ------------------------------------------------------------------ rounds

    def _start_round(self) -> None:
        self.round += 1
        if self.round > self.hands_per_game or not any(p.chips >= MIN_BET for p in self.players):
            self._finish()
            return
        if len(self.shoe) < DECKS * 52 * RESHUFFLE_AT:
            self._reshuffle()
        self.phase = "betting"
        self.dealer = []
        self.hole_hidden = True
        self.turn = None
        for p in self.players:
            p.hands = []
            p.bet = None
        self._emit(BJEvent("round_start", amount=self.round))

    def _finish(self) -> None:
        self.round = min(self.round, self.hands_per_game)
        self.phase = "game_over"
        self.game_over = True
        self._emit(BJEvent("game_over"))

    def place_bet(self, i: int, amount: int) -> None:
        if self.phase != "betting":
            raise RuleError("Bets are closed for this hand.")
        p = self.players[i]
        if p.chips < MIN_BET:
            raise RuleError("You're out of chips.")
        if p.bet is not None:
            raise RuleError("You've already bet.")
        if not MIN_BET <= amount <= self.max_bet(i):
            raise RuleError(f"Bet between {MIN_BET} and {self.max_bet(i)} chips.")
        p.bet = amount
        p.chips -= amount
        self._emit(BJEvent("bet", player=i, amount=amount))
        if all(q.bet is not None for q in self.players if q.chips + (q.bet or 0) >= MIN_BET):
            self._deal()

    def waiting_for_bets(self) -> list[int]:
        return [i for i, p in enumerate(self.players) if self.phase == "betting" and p.bet is None
                and p.chips >= MIN_BET]

    def _deal(self) -> None:
        self.phase = "playing"
        seated = [i for i, p in enumerate(self.players) if p.bet is not None]
        for i in seated:
            self.players[i].hands = [Hand(bet=self.players[i].bet)]
        for rnd in range(2):
            for i in seated:
                card = self._draw()
                self.players[i].hands[0].cards.append(card)
                self._emit(BJEvent("deal", player=i, card=card))
            hole = rnd == 1
            card = self._draw(face_up=not hole)
            self.dealer.append(card)
            self._emit(BJEvent("deal", player=None, card=None if hole else card, hidden=hole))
        for i in seated:
            if self.players[i].hands[0].natural:
                self._emit(BJEvent("blackjack", player=i))
        # Dealer peeks under an ace or ten-card; a dealer blackjack ends the hand at once.
        if self.dealer_up.value in (1, 10, 11, 12, 13) and is_blackjack(self.dealer):
            self._reveal()
            self._emit(BJEvent("blackjack", player=None))
            self._settle()
            return
        self.turn = None
        self._advance()

    def _advance(self) -> None:
        """Move to the next hand that still needs decisions, or let the dealer play."""
        order = [(i, h) for i, p in enumerate(self.players) for h in range(len(p.hands))]
        start = 0 if self.turn is None else order.index(self.turn) + 1
        for i, h in order[start:]:
            hand = self.players[i].hands[h]
            if not hand.done and not hand.natural:
                self.turn = (i, h)
                self._emit(BJEvent("turn", player=i, hand=h))
                return
            if not hand.stood:
                hand.stood = True
        self.turn = None
        self._dealer_play()

    def _current(self, i: int) -> Hand:
        if self.phase != "playing" or self.turn is None or self.turn[0] != i:
            raise RuleError("It's not your turn.")
        return self.players[i].hands[self.turn[1]]

    def legal_actions(self, i: int) -> list[str]:
        try:
            hand = self._current(i)
        except RuleError:
            return []
        p = self.players[i]
        acts = ["hit", "stand"]
        if len(hand.cards) == 2 and p.chips >= hand.bet:
            acts.append("double")
            if len(p.hands) == 1 and min(hand.cards[0].value, 10) == min(hand.cards[1].value, 10):
                acts.append("split")
        return acts

    def hit(self, i: int) -> None:
        hand = self._current(i)
        card = self._draw()
        hand.cards.append(card)
        self._emit(BJEvent("hit", player=i, hand=self.turn[1], card=card))
        if hand.busted:
            self._emit(BJEvent("bust", player=i, hand=self.turn[1]))
        if hand.done:
            self._advance()

    def stand(self, i: int) -> None:
        hand = self._current(i)
        hand.stood = True
        self._emit(BJEvent("stand", player=i, hand=self.turn[1]))
        self._advance()

    def double(self, i: int) -> None:
        if "double" not in self.legal_actions(i):
            raise RuleError("You can only double on your first two cards, with enough chips.")
        hand = self._current(i)
        p = self.players[i]
        p.chips -= hand.bet
        hand.bet *= 2
        hand.doubled = True
        card = self._draw()
        hand.cards.append(card)
        self._emit(BJEvent("double", player=i, hand=self.turn[1], card=card, amount=hand.bet))
        if hand.busted:
            self._emit(BJEvent("bust", player=i, hand=self.turn[1]))
        hand.stood = True
        self._advance()

    def split(self, i: int) -> None:
        if "split" not in self.legal_actions(i):
            raise RuleError("You can split a pair once, with enough chips.")
        p = self.players[i]
        first = p.hands[0]
        p.chips -= first.bet
        second = Hand(cards=[first.cards.pop()], bet=first.bet, split=True)
        first.split = True
        p.hands.append(second)
        aces = first.cards[0].value == 1
        for h, hand in enumerate(p.hands):
            card = self._draw()
            hand.cards.append(card)
            self._emit(BJEvent("split" if h == 0 else "hit", player=i, hand=h, card=card))
            if aces:
                hand.stood = True  # split aces get one card each
        self.turn = (i, 0)
        if p.hands[0].done or aces:
            self._advance()
        else:
            self._emit(BJEvent("turn", player=i, hand=0))

    def _reveal(self) -> None:
        if self.hole_hidden:
            self.hole_hidden = False
            self.seen.append(self.dealer[1])
            self._emit(BJEvent("reveal", player=None, card=self.dealer[1]))

    def _dealer_play(self) -> None:
        self._reveal()
        live = any(not h.busted for p in self.players for h in p.hands)
        while live and hand_value(self.dealer)[0] < 17:
            card = self._draw()
            self.dealer.append(card)
            self._emit(BJEvent("dealer_hit", player=None, card=card))
        self._settle()

    def _settle(self) -> None:
        dealer_total = hand_value(self.dealer)[0]
        dealer_bj = is_blackjack(self.dealer)
        for i, p in enumerate(self.players):
            for h, hand in enumerate(p.hands):
                if hand.busted:
                    hand.result, hand.payout = "bust", 0
                elif dealer_bj:
                    hand.result, hand.payout = ("push", hand.bet) if hand.natural else ("lose", 0)
                elif hand.natural:
                    hand.result, hand.payout = "blackjack", hand.bet + hand.bet * 3 // 2
                elif dealer_total > 21 or hand.value > dealer_total:
                    hand.result, hand.payout = "win", hand.bet * 2
                elif hand.value == dealer_total:
                    hand.result, hand.payout = "push", hand.bet
                else:
                    hand.result, hand.payout = "lose", 0
                p.chips += hand.payout
                p.net += hand.payout - hand.bet
                p.results.append(hand.result)
                self._emit(BJEvent("settle", player=i, hand=h, amount=hand.payout - hand.bet, result=hand.result))
        self.phase = "settled"
        self.turn = None

    def next_round(self) -> None:
        if self.phase != "settled":
            raise RuleError("The hand isn't finished.")
        self._start_round()
