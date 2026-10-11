"""Exact "cards still missing" for a hand: tries every target and does max matching. Used to check the AI planner."""
import itertools
from ten_phases.cards import COLORS
from ten_phases.phases import GroupType

INF = 99

def targets(req):
    n = req.size
    if req.type is GroupType.SET:
        return [("set", v, n) for v in range(1, 13)]
    if req.type is GroupType.COLOR:
        return [("color", c, n) for c in COLORS]
    return [("run", s, n) for s in range(1, 14 - n)]

def slots_for(t):
    kind, key, n = t
    if kind == "run":
        return [("v", key + i) for i in range(n)]
    return [(kind, key)] * n

def fits(card, slot):
    k, key = slot
    if k == "v" or k == "set":
        return card.value == key
    return card.color == key

def max_match(cards, slots, forced=()):
    # simple augmenting-path bipartite matching; forced = [(card_idx, slot_idx)]
    match_slot = {}
    used_cards = set()
    for ci, si in forced:
        match_slot[si] = ci; used_cards.add(ci)
    def try_card(ci, seen):
        for si, s in enumerate(slots):
            if si in seen or not fits(cards[ci], s):
                continue
            if any(si == fsi for _, fsi in forced):
                continue
            seen.add(si)
            if si not in match_slot or try_card(match_slot[si], seen):
                match_slot[si] = ci
                return True
        return False
    for ci in range(len(cards)):
        if ci not in used_cards:
            try_card(ci, set())
    return match_slot

def exact_deficit(reqs, hand):
    nat = [c for c in hand if c.is_number]
    wild = sum(1 for c in hand if c.is_wild)
    best = INF
    for combo in itertools.product(*[targets(r) for r in reqs]):
        slots, owner = [], []
        for gi, t in enumerate(combo):
            s = slots_for(t)
            slots += s; owner += [gi] * len(s)
        m = max_match(nat, slots)
        groups_hit = {owner[si] for si in m}
        if len(groups_hit) < len(reqs):
            # try forcing one natural into each empty group
            ok = False
            empty = [g for g in range(len(reqs)) if g not in groups_hit]
            options = []
            for g in empty:
                options.append([(ci, si) for si in range(len(slots)) if owner[si] == g
                                for ci in range(len(nat)) if fits(nat[ci], slots[si])])
            for forced in itertools.product(*options):
                if len({ci for ci, _ in forced}) < len(forced):
                    continue
                m2 = max_match(nat, slots, forced)
                if {owner[si] for si in m2} >= set(range(len(reqs))):
                    if not ok or len(m2) > len(m):
                        m = m2; ok = True
            if not ok:
                continue
        need = len(slots) - len(m)
        best = min(best, max(0, need - wild))
    return best
