"""Cards Against Humanity rules.

  * Everyone holds 10 white (answer) cards. Each round one player is the Card Czar
  * The Czar turns over a black (question) card; everyone else plays as many
    white cards as it asks for (Pick 1, 2 or 3)
  * The answers are shown without names; the Czar picks the funniest, and that
    player scores a point. Hands refill and the Czar moves to the next player
  * First to the target score wins (or most points when the black cards run out)

House options (chosen before the game): which packs are in the deck, how many
blank white cards are shuffled in (you write your own answer when you play one),
and whether a blank card can carry a picture.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import random
from dataclasses import dataclass, field

HAND_SIZE = 10
MIN_PLAYERS = 3
MAX_BLANK_TEXT = 80
MAX_IMAGE_CHARS = 160_000      # base64 of a small picture
CHIPS_PER_POINT = 10


class RuleError(Exception):
    """An illegal move. The message is shown to the player."""


@dataclass
class CahOptions:
    packs: list[int] = field(default_factory=lambda: [0])
    blanks: int = 5
    images: bool = True
    points_to_win: int = 7


@dataclass(eq=False)
class WhiteCard:
    text: str
    id: int
    blank: bool = False


@dataclass(eq=False)
class BlackCard:
    text: str
    pick: int
    id: int


@dataclass
class Written:
    """What a player put on a blank card."""
    text: str = ""
    image: str | None = None       # base64 image data
    image_id: str | None = None    # short hash, so the network only sends each picture once


@dataclass
class Submission:
    id: int
    player: int
    cards: list[WhiteCard]
    written: dict[int, Written] = field(default_factory=dict)   # card id -> what was written on it

    def card_text(self, card: WhiteCard) -> str:
        w = self.written.get(card.id)
        return w.text if (card.blank and w) else card.text


@dataclass
class CahPlayer:
    name: str
    is_human: bool = False
    difficulty: str | None = None
    hand: list[WhiteCard] = field(default_factory=list)
    points: int = 0
    submitted: bool = False


@dataclass
class CahEvent:
    kind: str     # round_start, submit, judging, win, game_over, reshuffle
    player: int | None = None
    amount: int = 0
    text: str = ""


def image_id(data: str) -> str:
    return hashlib.sha1(data.encode()).hexdigest()[:16]


def clean_written(raw, images_allowed: bool) -> Written:
    """Check what a player wrote on a blank card (it may come from the network)."""
    if not isinstance(raw, dict):
        raise RuleError("Write something on your blank card.")
    text = raw.get("text", "")
    text = " ".join(text.split())[:MAX_BLANK_TEXT] if isinstance(text, str) else ""
    text = "".join(ch for ch in text if ch.isprintable())
    image = raw.get("image")
    if image is not None:
        if not images_allowed:
            raise RuleError("Pictures on blank cards are turned off for this game.")
        if not isinstance(image, str) or len(image) > MAX_IMAGE_CHARS:
            raise RuleError("That picture is too big.")
        try:
            base64.b64decode(image, validate=True)
        except (binascii.Error, ValueError):
            raise RuleError("That picture didn't come through.") from None
    if not text and image is None:
        raise RuleError("Write something on your blank card" + (" or add a picture." if images_allowed else "."))
    return Written(text, image, image_id(image) if image else None)


class CahGame:
    def __init__(self, players: list[CahPlayer], packs: list[dict], options: CahOptions | None = None,
                 rng: random.Random | None = None):
        if not MIN_PLAYERS <= len(players) <= 8:
            raise ValueError("Cards Against Humanity needs 3-8 players")
        self.players = players
        self.options = options or CahOptions()
        self.rng = rng or random.Random()
        chosen = [p for p in packs if p["id"] in set(self.options.packs)] or packs[:1]
        self.pack_names = [p["name"] for p in chosen]
        self._next_id = 1
        whites = list(dict.fromkeys(t for p in chosen for t in p["white"]))
        blacks = list({b["text"]: b for p in chosen for b in p["black"]}.values())
        self.white_deck = [self._white(t) for t in whites]
        self.white_deck += [self._white("", blank=True) for _ in range(max(0, self.options.blanks))]
        self.black_deck = [BlackCard(b["text"], b["pick"], self._new_id()) for b in blacks]
        if len(self.white_deck) < HAND_SIZE * len(players) + 10 or not self.black_deck:
            raise ValueError("Not enough cards in those packs - pick some more.")
        self.rng.shuffle(self.white_deck)
        self.rng.shuffle(self.black_deck)
        self.white_discard: list[WhiteCard] = []
        self.events: list[CahEvent] = []
        self.history: list[CahEvent] = []
        self.round = 0
        self.czar = self.rng.randrange(len(players)) - 1
        self.black: BlackCard | None = None
        self.phase = "picking"            # picking, judging, results, game_over
        self.submissions: dict[int, Submission] = {}     # player -> their answer
        self.order: list[Submission] = []                # shuffled answers, shown to the Czar
        self.winner: int | None = None
        self.winning: Submission | None = None
        self.game_over = False
        for k in range(len(players)):
            self._refill(k)
        self._start_round()

    # ------------------------------------------------------------------ helpers

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _white(self, text: str, blank: bool = False) -> WhiteCard:
        return WhiteCard(text, self._new_id(), blank)

    def _emit(self, ev: CahEvent) -> None:
        self.events.append(ev)
        self.history.append(ev)

    def pop_events(self) -> list[CahEvent]:
        ev, self.events = self.events, []
        return ev

    def _draw_white(self) -> WhiteCard | None:
        if not self.white_deck:
            if not self.white_discard:
                return None
            self.white_deck, self.white_discard = self.white_discard, []
            self.rng.shuffle(self.white_deck)
            self._emit(CahEvent("reshuffle"))
        return self.white_deck.pop()

    def _refill(self, i: int) -> None:
        hand = self.players[i].hand
        while len(hand) < HAND_SIZE:
            card = self._draw_white()
            if card is None:
                break
            hand.append(card)

    def players_to_answer(self) -> list[int]:
        return [k for k in range(len(self.players)) if k != self.czar]

    def waiting_on(self) -> list[int]:
        return [k for k in self.players_to_answer() if not self.players[k].submitted] if self.phase == "picking" \
            else []

    def standings(self) -> list[int]:
        return sorted(range(len(self.players)), key=lambda k: -self.players[k].points)

    def winners(self) -> list[int]:
        best = max(p.points for p in self.players)
        return [k for k, p in enumerate(self.players) if p.points == best]

    # ------------------------------------------------------------------ rounds

    def _start_round(self) -> None:
        if not self.black_deck:
            self._finish()
            return
        self.round += 1
        self.czar = (self.czar + 1) % len(self.players)
        self.black = self.black_deck.pop()
        self.phase = "picking"
        self.submissions = {}
        self.order = []
        self.winner = None
        self.winning = None
        for p in self.players:
            p.submitted = False
        self._emit(CahEvent("round_start", player=self.czar, amount=self.round, text=self.black.text))

    def _finish(self) -> None:
        self.phase = "game_over"
        self.game_over = True
        self._emit(CahEvent("game_over"))

    def submit(self, i: int, card_ids: list[int], written: dict | None = None) -> None:
        """Player i plays these white cards (in order). `written` maps a blank card's id to {"text", "image"}."""
        if self.phase != "picking":
            raise RuleError("Answers are closed for this round.")
        if i == self.czar:
            raise RuleError("You're the Card Czar this round - you judge, you don't answer.")
        p = self.players[i]
        if p.submitted:
            raise RuleError("You already played your cards.")
        pick = self.black.pick
        if not isinstance(card_ids, list) or len(card_ids) != pick or len(set(card_ids)) != pick:
            raise RuleError(f"Pick {pick} card{'s' if pick > 1 else ''}.")
        by_id = {c.id: c for c in p.hand}
        if not all(isinstance(cid, int) and cid in by_id for cid in card_ids):
            raise RuleError("Those cards aren't in your hand.")
        cards = [by_id[cid] for cid in card_ids]
        notes = {}
        written = written or {}
        for c in cards:
            if c.blank:
                raw = written.get(c.id, written.get(str(c.id)))
                notes[c.id] = clean_written(raw, self.options.images)
        p.hand = [c for c in p.hand if c.id not in set(card_ids)]
        p.submitted = True
        self.submissions[i] = Submission(self._new_id(), i, cards, notes)
        self._emit(CahEvent("submit", player=i))
        if not self.waiting_on():
            self.order = list(self.submissions.values())
            self.rng.shuffle(self.order)
            self.phase = "judging"
            self._emit(CahEvent("judging", player=self.czar))

    def judge(self, i: int, submission_id: int) -> None:
        if self.phase != "judging":
            raise RuleError("There's nothing to judge yet.")
        if i != self.czar:
            raise RuleError("Only the Card Czar picks the winner.")
        sub = next((s for s in self.order if s.id == submission_id), None)
        if sub is None:
            raise RuleError("Pick one of the answers.")
        self.winner, self.winning = sub.player, sub
        self.players[sub.player].points += 1
        self.phase = "results"
        self._emit(CahEvent("win", player=sub.player, amount=self.players[sub.player].points))

    def next_round(self) -> None:
        if self.phase != "results":
            raise RuleError("The round isn't over yet.")
        for sub in self.submissions.values():
            self.white_discard += sub.cards
        for k in range(len(self.players)):
            self._refill(k)
        if self.players[self.winner].points >= self.options.points_to_win:
            self._finish()
            return
        self._start_round()
