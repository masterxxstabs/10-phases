"""The rules engine. Knows nothing about drawing or AI decisions."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .cards import Card, Deck
from .phases import NUM_PHASES, PHASES, GroupType, Requirement, arrange_group, is_valid_group, match_groups, partition_for_phase

HAND_SIZE = 10
STARTING_CHIPS = 24
ANTE = 1


class RuleError(Exception):
    """Raised when a player attempts an illegal move. The message is shown to the user."""


@dataclass
class Player:
    name: str
    is_human: bool = False
    difficulty: str | None = None
    hand: list[Card] = field(default_factory=list)
    phase: int = 0          # index into PHASES; NUM_PHASES means all done
    score: int = 0
    chips: int = STARTING_CHIPS
    laid_down: bool = False
    skips_pending: int = 0
    completed_this_round: bool = False

    @property
    def finished_all(self) -> bool:
        return self.phase >= NUM_PHASES

    @property
    def requirements(self) -> tuple[Requirement, ...]:
        return PHASES[min(self.phase, NUM_PHASES - 1)]


@dataclass
class Meld:
    id: int
    owner: int
    type: GroupType
    min_size: int
    cards: list[Card]

    def accepts(self, card: Card) -> bool:
        return is_valid_group(self.type, self.cards + [card], self.min_size)

    def ordered(self) -> list[Card]:
        return arrange_group(self.type, self.cards)


@dataclass
class Event:
    kind: str           # draw, discard, lay, hit, skip, skipped, reshuffle, round_end, game_over
    player: int | None = None
    card: Card | None = None
    source: str | None = None
    target: int | None = None
    meld: int | None = None


class Game:
    def __init__(self, players: list[Player], rng: random.Random | None = None):
        if not 2 <= len(players) <= 6:
            raise ValueError("Phase 10 needs 2-6 players")
        self.players = players
        self.rng = rng or random.Random()
        self.dealer = self.rng.randrange(len(players))
        self.round = 0
        self.events: list[Event] = []
        self.game_over = False
        self.winner: int | None = None
        self.pot = 0
        # Public memory every player could have, used by the smarter AIs.
        self.picked_from_discard: dict[int, list[Card]] = {}
        self.start_round()

    # ------------------------------------------------------------------ round setup

    def start_round(self) -> None:
        self.round += 1
        self.dealer = (self.dealer + 1) % len(self.players)
        self.deck = Deck(self.rng)
        self.discard_pile: list[Card] = []
        self.melds: list[Meld] = []
        self._meld_ids = 0
        self.round_over = False
        self.round_points: dict[int, int] = {}
        self.round_chips: dict[int, int] = {}
        self.picked_from_discard = {i: [] for i in range(len(self.players))}
        for p in self.players:
            p.hand = []
            p.laid_down = False
            p.skips_pending = 0
            p.completed_this_round = False
        # Everyone antes into the pot; whoever goes out wins it.
        for i, p in enumerate(self.players):
            paid = min(ANTE, p.chips)
            p.chips -= paid
            self.pot += paid
            self.round_chips[i] = -paid
        for _ in range(HAND_SIZE):
            for p in self.players:
                p.hand.append(self.deck.draw())
        self.discard_pile.append(self.deck.draw())
        self.current = (self.dealer + 1) % len(self.players)
        self.has_drawn = False
        self.turn_number = 0
        if self.discard_pile[-1].is_skip:
            # A skip turned up as the first discard skips the first player.
            self.events.append(Event("skipped", player=self.current))
            self.current = self._next_index(self.current)
        self.events.append(Event("round_start"))

    # ------------------------------------------------------------------ helpers

    @property
    def player(self) -> Player:
        return self.players[self.current]

    @property
    def top_discard(self) -> Card | None:
        return self.discard_pile[-1] if self.discard_pile else None

    def _next_index(self, i: int) -> int:
        return (i + 1) % len(self.players)

    def _require_turn(self, player_index: int) -> None:
        if self.round_over or self.game_over:
            raise RuleError("The round is over.")
        if player_index != self.current:
            raise RuleError("It's not your turn.")

    def _require_drawn(self) -> None:
        if not self.has_drawn:
            raise RuleError("Draw a card first.")

    def _card_in_hand(self, p: Player, card: Card) -> None:
        if card not in p.hand:
            raise RuleError("That card isn't in your hand.")

    def meld_by_id(self, meld_id: int) -> Meld:
        for m in self.melds:
            if m.id == meld_id:
                return m
        raise RuleError("No such group on the table.")

    def opponents_of(self, index: int) -> list[int]:
        return [i for i in range(len(self.players)) if i != index]

    # ------------------------------------------------------------------ actions

    def draw_from_deck(self, player_index: int) -> Card:
        self._require_turn(player_index)
        if self.has_drawn:
            raise RuleError("You already drew this turn.")
        if not self.deck.cards:
            self._reshuffle()
        card = self.deck.draw()
        self.player.hand.append(card)
        self.has_drawn = True
        self.events.append(Event("draw", player=player_index, card=card, source="deck"))
        return card

    def draw_from_discard(self, player_index: int) -> Card:
        self._require_turn(player_index)
        if self.has_drawn:
            raise RuleError("You already drew this turn.")
        top = self.top_discard
        if top is None:
            raise RuleError("The discard pile is empty.")
        if top.is_skip:
            raise RuleError("You can't pick up a Skip.")
        self.discard_pile.pop()
        self.player.hand.append(top)
        self.has_drawn = True
        self.picked_from_discard[player_index].append(top)
        self.events.append(Event("draw", player=player_index, card=top, source="discard"))
        return top

    def _reshuffle(self) -> None:
        top = self.discard_pile.pop()
        if not self.discard_pile:
            raise RuleError("No cards left to draw.")
        self.deck.refill(self.discard_pile)
        self.discard_pile = [top]
        self.events.append(Event("reshuffle"))

    def lay_down(self, player_index: int, groups: list[list[Card]]) -> list[Meld]:
        """Lay down the current phase as explicit groups."""
        self._require_turn(player_index)
        self._require_drawn()
        p = self.player
        if p.laid_down:
            raise RuleError("You've already completed your phase this round.")
        cards = [c for g in groups for c in g]
        if len({c.id for c in cards}) != len(cards):
            raise RuleError("A card can only be used once.")
        for c in cards:
            self._card_in_hand(p, c)
        matched = match_groups(p.requirements, groups)
        if matched is None:
            raise RuleError("Those cards don't complete your phase.")
        new = []
        for req, g in zip(matched, groups):
            self._meld_ids += 1
            meld = Meld(self._meld_ids, player_index, req.type, req.size, list(g))
            self.melds.append(meld)
            new.append(meld)
        for c in cards:
            p.hand.remove(c)
        p.laid_down = True
        p.completed_this_round = True
        self.events.append(Event("lay", player=player_index))
        self._check_out(player_index)
        return new

    def lay_down_auto(self, player_index: int, cards: list[Card]) -> list[Meld]:
        """Lay down the phase from a selection of cards, working out the groups."""
        self._require_turn(player_index)
        self._require_drawn()
        p = self.player
        if p.laid_down:
            raise RuleError("You've already completed your phase this round.")
        need = sum(r.size for r in p.requirements)
        if len(cards) < need:
            raise RuleError(f"Your phase needs at least {need} cards.")
        if any(c.is_skip for c in cards):
            raise RuleError("Skips can't be part of a phase.")
        split = partition_for_phase(p.requirements, cards)
        if split is None:
            raise RuleError("Those cards don't complete your phase.")
        return self.lay_down(player_index, [g for _, g in split])

    def hit(self, player_index: int, card: Card, meld_id: int) -> None:
        self._require_turn(player_index)
        self._require_drawn()
        p = self.player
        if not p.laid_down:
            raise RuleError("Complete your own phase before adding to others.")
        self._card_in_hand(p, card)
        meld = self.meld_by_id(meld_id)
        if not meld.accepts(card):
            raise RuleError(f"{card.label()} doesn't fit that group.")
        p.hand.remove(card)
        meld.cards.append(card)
        self.events.append(Event("hit", player=player_index, card=card, meld=meld_id))
        self._check_out(player_index)

    def discard(self, player_index: int, card: Card, skip_target: int | None = None) -> None:
        self._require_turn(player_index)
        self._require_drawn()
        p = self.player
        self._card_in_hand(p, card)
        if card.is_skip:
            if skip_target is None:
                skip_target = self.default_skip_target(player_index)
            if skip_target == player_index or not 0 <= skip_target < len(self.players):
                raise RuleError("Choose another player to skip.")
        p.hand.remove(card)
        self.discard_pile.append(card)
        self.events.append(Event("discard", player=player_index, card=card))
        if card.is_skip:
            self.players[skip_target].skips_pending += 1
            self.events.append(Event("skip", player=player_index, target=skip_target))
        if not self._check_out(player_index):
            self._advance()

    def default_skip_target(self, player_index: int) -> int:
        return self._next_index(player_index)

    # ------------------------------------------------------------------ turn flow

    def _advance(self) -> None:
        self.has_drawn = False
        self.turn_number += 1
        nxt = self._next_index(self.current)
        # Skipped players lose their turn. Guard against everyone being skipped.
        for _ in range(len(self.players) * 4):
            target = self.players[nxt]
            if target.skips_pending > 0:
                target.skips_pending -= 1
                self.events.append(Event("skipped", player=nxt))
                nxt = self._next_index(nxt)
                continue
            break
        self.current = nxt
        self.events.append(Event("turn", player=nxt))

    def _check_out(self, player_index: int) -> bool:
        if self.players[player_index].hand:
            return False
        self._end_round(player_index)
        return True

    def _end_round(self, went_out: int) -> None:
        self.round_over = True
        self.went_out = went_out
        for i, p in enumerate(self.players):
            pts = sum(c.points for c in p.hand)
            self.round_points[i] = pts
            p.score += pts
            if p.completed_this_round:
                p.phase += 1
        winnings, self.pot = self.pot, 0
        self.players[went_out].chips += winnings
        self.round_chips[went_out] = self.round_chips.get(went_out, 0) + winnings
        self.events.append(Event("round_end", player=went_out))
        finished = [i for i, p in enumerate(self.players) if p.finished_all]
        if finished:
            self.game_over = True
            self.winner = min(finished, key=lambda i: (self.players[i].score, -self.players[i].chips))
            self.events.append(Event("game_over", player=self.winner))

    def next_round(self) -> None:
        if not self.round_over or self.game_over:
            raise RuleError("The round isn't over yet.")
        self.start_round()

    def standings(self) -> list[int]:
        """Player indices from best to worst: highest phase, then lowest score, then most chips."""
        return sorted(range(len(self.players)),
                      key=lambda i: (-self.players[i].phase, self.players[i].score, -self.players[i].chips))

    def pop_events(self) -> list[Event]:
        ev, self.events = self.events, []
        return ev
