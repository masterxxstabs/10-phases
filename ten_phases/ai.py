"""Computer opponents.

Every AI only looks at information a real player would have: its own hand, the
discard pile, the groups on the table, and what other players picked up from
the discard pile. Difficulty changes how well that information is used.

  Easy    - greedy, short-sighted, makes regular mistakes, misses plays.
  Medium  - plays solidly towards its phase, rarely slips up.
  Hard    - weighs which draws would help ("outs"), avoids feeding the next
            player, aims Skips at the leader, dumps points when someone is close.
  Expert  - all of the above plus card counting (tracks every card it has seen)
            and stronger defence.
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass

from .cards import COLORS, MAX_VALUE, MIN_VALUE, Card, Color, Kind
from .game import Game, Player
from .phases import GroupType, Requirement

DIFFICULTIES = ("Easy", "Medium", "Hard", "Expert")


@dataclass(frozen=True)
class Profile:
    mistake_rate: float      # chance to make a random discard
    miss_hit_rate: float     # chance to overlook a hit
    miss_laydown_rate: float # chance to not notice a completed phase this turn
    use_outs: bool           # consider which future draws help
    card_counting: bool      # weight outs by cards not yet seen
    defense: float           # how much to avoid helping the next player (0 = none)
    smart_skips: bool        # aim skips at the most dangerous opponent
    smart_draw: bool         # evaluate discard-pile pickups fully


PROFILES = {
    "Easy": Profile(0.30, 0.35, 0.25, False, False, 0.0, False, False),
    "Medium": Profile(0.05, 0.05, 0.0, True, False, 0.0, False, True),
    "Hard": Profile(0.0, 0.0, 0.0, True, False, 1.0, True, True),
    "Expert": Profile(0.0, 0.0, 0.0, True, True, 2.0, True, True),
}


# --------------------------------------------------------------------------- planning


@dataclass
class Plan:
    need: int                                   # natural cards still missing
    groups: list[tuple[Requirement, list[Card]]]
    wilds: list[Card]
    valid: bool                                 # every group has a natural card

    @property
    def deficit(self) -> int:
        return max(0, self.need - len(self.wilds)) + (0 if self.valid else 1)

    @property
    def complete(self) -> bool:
        return self.valid and self.need <= len(self.wilds)

    def used_ids(self) -> set[int]:
        return {c.id for _, g in self.groups for c in g}


def _candidates(req: Requirement, pool: list[Card]):
    n = req.size
    if req.type is GroupType.SET:
        by: dict[int, list[Card]] = defaultdict(list)
        for c in pool:
            by[c.value].append(c)
        for cards in by.values():
            yield cards[:n]
    elif req.type is GroupType.COLOR:
        byc: dict[Color, list[Card]] = defaultdict(list)
        for c in pool:
            byc[c.color].append(c)
        for cards in byc.values():
            yield cards[:n]
    else:
        first: dict[int, Card] = {}
        for c in pool:
            first.setdefault(c.value, c)
        seen = set()
        for s in range(MIN_VALUE, MAX_VALUE - n + 2):
            take = [first[v] for v in range(s, s + n) if v in first]
            key = tuple(c.id for c in take)
            if take and key not in seen:
                seen.add(key)
                yield take


def _search(reqs: tuple[Requirement, ...], pool: list[Card]) -> tuple[int, list, bool]:
    if not reqs:
        return 0, [], True
    req, rest = reqs[0], reqs[1:]
    best = None
    for take in _candidates(req, pool):
        ids = {c.id for c in take}
        remaining = [c for c in pool if c.id not in ids]
        sub_need, sub_groups, sub_valid = _search(rest, remaining)
        total = req.size - len(take) + sub_need
        if best is None or total < best[0] or (total == best[0] and sub_valid and not best[2]):
            best = (total, [(req, take)] + sub_groups, sub_valid)
    if best is None:
        sub_need, sub_groups, _ = _search(rest, pool)
        return req.size + sub_need, [(req, [])] + sub_groups, False
    return best


def plan_phase(reqs: tuple[Requirement, ...], hand: list[Card]) -> Plan:
    naturals = [c for c in hand if c.is_number]
    wilds = [c for c in hand if c.is_wild]
    need, groups, valid = _search(reqs, naturals)
    return Plan(need, groups, wilds, valid)


def build_groups(plan: Plan) -> list[list[Card]]:
    """Turn a complete plan into concrete groups, filling gaps with wilds."""
    wilds = list(plan.wilds)
    out = []
    for req, take in plan.groups:
        group = list(take)
        while len(group) < req.size:
            group.append(wilds.pop())
        out.append(group)
    return out


# --------------------------------------------------------------------------- the AI


class AIPlayer:
    def __init__(self, difficulty: str = "Medium", rng: random.Random | None = None):
        self.difficulty = difficulty
        self.profile = PROFILES[difficulty]
        self.rng = rng or random.Random()

    # ---------------------------------------------------------------- public API

    def next_action(self, game: Game, me: int):
        """Decide the next single action for player `me` on their turn.

        Returns one of:
          ("draw", "deck" | "discard")
          ("lay", groups)
          ("hit", card, meld_id)
          ("discard", card, skip_target_or_None)
        """
        p = game.players[me]
        if not game.has_drawn:
            return ("draw", self.choose_draw(game, me))
        if not p.laid_down:
            plan = plan_phase(p.requirements, p.hand)
            if plan.complete and self.rng.random() >= self.profile.miss_laydown_rate:
                return ("lay", build_groups(plan))
        else:
            hit = self.choose_hit(game, me)
            if hit:
                return ("hit",) + hit
        card = self.choose_discard(game, me)
        target = self.choose_skip_target(game, me) if card.is_skip else None
        return ("discard", card, target)

    # ---------------------------------------------------------------- drawing

    def choose_draw(self, game: Game, me: int) -> str:
        p = game.players[me]
        top = game.top_discard
        if top is None or top.is_skip:
            return "deck"
        if top.is_wild:
            return "discard"
        if p.laid_down:
            return "discard" if any(m.accepts(top) for m in game.melds) else "deck"

        if not self.profile.smart_draw:
            # Easy: grab it if it obviously matches something in hand.
            if game.players[me].requirements[0].type is GroupType.COLOR:
                match = sum(1 for c in p.hand if c.is_number and c.color == top.color) >= 2
            else:
                match = any(c.is_number and abs(c.value - top.value) <= (0 if self._set_only(p) else 1) for c in p.hand)
            return "discard" if match and self.rng.random() < 0.7 else "deck"

        current = self._evaluate(game, me, p.hand)
        best_with = min(self._evaluate(game, me, [c for c in p.hand + [top] if c is not d])
                        for d in p.hand + [top] if d is not top)
        return "discard" if best_with < current - 0.5 else "deck"

    def _set_only(self, p: Player) -> bool:
        return all(r.type is GroupType.SET for r in p.requirements)

    # ---------------------------------------------------------------- hitting

    def choose_hit(self, game: Game, me: int):
        p = game.players[me]
        # Prefer natural cards first and save wilds until the end.
        for card in sorted(p.hand, key=lambda c: c.is_wild):
            if card.is_skip:
                continue
            options = [m for m in game.melds if m.accepts(card)]
            if not options:
                continue
            if self.rng.random() < self.profile.miss_hit_rate:
                continue
            # Wilds go on sets where they can't block a run's ends.
            options.sort(key=lambda m: (m.type is GroupType.RUN, m.owner != me))
            return (card, options[0].id)
        return None

    # ---------------------------------------------------------------- discarding

    def choose_discard(self, game: Game, me: int) -> Card:
        p = game.players[me]
        hand = p.hand
        if len(hand) == 1:
            return hand[0]
        if self.rng.random() < self.profile.mistake_rate:
            pool = [c for c in hand if not c.is_wild] or hand
            return self.rng.choice(pool)

        threat = self._threat_level(game, me)
        nxt = self._next_player(game, me)
        best, best_score = None, None
        seen_types = set()
        for card in hand:
            key = (card.kind, card.color, card.value)
            if key in seen_types:
                continue
            seen_types.add(key)
            rest = [c for c in hand if c is not card]
            if p.laid_down:
                score = 0.0
                # Keep cards we can still play; dump the most points otherwise.
                if any(m.accepts(card) for m in game.melds):
                    score += 50
            else:
                score = self._evaluate(game, me, rest)
            if card.is_wild:
                score += 100
            if card.is_skip:
                score -= 3 + 3 * threat
            # Unload points when someone looks close to going out.
            weight = 0.02 + 0.08 * threat if self.profile.defense else 0.02
            score -= card.points * weight
            if self.profile.defense and nxt is not None:
                score += self.profile.defense * self._helps_player(game, nxt, card)
            if best_score is None or score < best_score:
                best, best_score = card, score
        return best

    # ---------------------------------------------------------------- skips

    def choose_skip_target(self, game: Game, me: int) -> int:
        others = game.opponents_of(me)
        if not self.profile.smart_skips:
            if self.profile.mistake_rate > 0.2:
                return self.rng.choice(others)
            return self._next_player(game, me) or others[0]

        def danger(i: int) -> float:
            o = game.players[i]
            d = o.phase * 3 - len(o.hand) + (8 if o.laid_down else 0) - o.score / 50
            return d - 6 * o.skips_pending
        return max(others, key=danger)

    # ---------------------------------------------------------------- evaluation

    def _evaluate(self, game: Game, me: int, hand: list[Card]) -> float:
        """Lower is better: how far the hand is from completing the phase."""
        reqs = game.players[me].requirements
        plan = plan_phase(reqs, hand)
        score = plan.deficit * 10.0
        if plan.complete:
            return score - 5
        if self.profile.use_outs:
            score -= self._outs(game, me, reqs, hand, plan.deficit)
        return score

    def _outs(self, game: Game, me: int, reqs, hand: list[Card], deficit: int) -> float:
        """Weighted share of the unseen cards that would improve this hand."""
        counts = self._unseen_counts(game, me) if self.profile.card_counting else None
        color_phase = reqs[0].type is GroupType.COLOR
        total = good = 0.0
        if color_phase:
            probes = [(Card(Kind.NUMBER, col, 5), [(v, col) for v in range(1, 13)]) for col in COLORS]
        else:
            probes = [(Card(Kind.NUMBER, COLORS[0], v), [(v, col) for col in COLORS]) for v in range(1, 13)]
        probes.append((Card(Kind.WILD), [("wild", None)]))
        for probe, keys in probes:
            weight = sum(counts[k] for k in keys) if counts else sum(8 if k[0] == "wild" else 2 for k in keys)
            total += weight
            if weight and plan_phase(reqs, hand + [probe]).deficit < deficit:
                good += weight
        return 8.0 * good / total if total else 0.0

    def _unseen_counts(self, game: Game, me: int) -> dict:
        counts = {(v, c): 2 for v in range(1, 13) for c in COLORS}
        counts[("wild", None)] = 8
        seen = list(game.players[me].hand) + list(game.discard_pile)
        for m in game.melds:
            seen += m.cards
        for c in seen:
            key = ("wild", None) if c.is_wild else (c.value, c.color) if c.is_number else None
            if key in counts and counts[key] > 0:
                counts[key] -= 1
        return counts

    # ---------------------------------------------------------------- opponents

    def _next_player(self, game: Game, me: int) -> int | None:
        n = len(game.players)
        for step in range(1, n):
            i = (me + step) % n
            if game.players[i].skips_pending == 0:
                return i
        return None

    def _threat_level(self, game: Game, me: int) -> float:
        """0..1 - how likely it is that the round ends soon."""
        worst = 0.0
        for i in game.opponents_of(me):
            o = game.players[i]
            if o.laid_down:
                worst = max(worst, 1.0 if len(o.hand) <= 3 else 0.6)
        return worst

    def _helps_player(self, game: Game, i: int, card: Card) -> float:
        """Rough guess at how much handing `card` to player i would help them."""
        o = game.players[i]
        if card.is_skip:
            return 0.0
        if card.is_wild:
            return 10.0
        if o.laid_down:
            return 8.0 if any(m.accepts(card) for m in game.melds) else 0.0
        picked = [c for c in game.picked_from_discard.get(i, []) if c.is_number]
        help_ = 0.0
        for req in o.requirements:
            for c in picked:
                if req.type is GroupType.SET and c.value == card.value:
                    help_ += 4.0
                elif req.type is GroupType.RUN and 0 < abs(c.value - card.value) <= 3:
                    help_ += 1.5
                elif req.type is GroupType.COLOR and c.color == card.color:
                    help_ += 2.0
        return min(help_, 8.0)
