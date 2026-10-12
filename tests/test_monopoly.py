"""Monopoly: the rules engine, the computer players, multiplayer and the table screen."""

import random
import time

import pygame
import pytest

from ten_phases.monopoly.ai import MonopolyAI
from ten_phases.monopoly.board import CHANCE, CHEST, GROUPS, SETS, SQUARES, STATION_RENTS
from ten_phases.monopoly.engine import TOKENS, MonopolyGame, MPlayer, RuleError

PHASES = ("pre_roll", "post_roll", "buy", "auction", "debt", "fine_or_chance", "game_over")


def new_game(n=3, rounds=40, seed=0):
    return MonopolyGame([MPlayer(f"P{k}", is_human=k == 0, difficulty="" if k == 0 else "Medium")
                         for k in range(n)], random.Random(seed), max_rounds=rounds)


def rig(g, *rolls):
    """The next dice rolls, in order (then random again)."""
    queue = list(rolls)
    g.dice = lambda: queue.pop(0) if queue else (g.rng.randint(1, 6), g.rng.randint(1, 6))


def check(g):
    """Things that must always be true, whatever happened."""
    for k, p in enumerate(g.players):
        assert p.cash >= 0
        if p.bankrupt:
            assert not g.props_of(k) and not p.goojf
    for sq in range(40):
        assert 0 <= g.houses[sq] <= 5
        if g.houses[sq]:
            s, o = SQUARES[sq], g.owner[sq]
            assert s.kind == "street" and o is not None and g.owns_set(o, s.group)
            assert not any(g.mortgaged[m] for m in GROUPS[s.group])
        if g.mortgaged[sq]:
            assert g.owner[sq] is not None
        if g.owner[sq] is not None:
            assert SQUARES[sq].ownable and not g.players[g.owner[sq]].bankrupt
    for members in GROUPS.values():
        houses = [g.houses[k] for k in members]
        assert max(houses) - min(houses) <= 1        # built evenly
    for deck, cards in (("chance", CHANCE), ("chest", CHEST)):
        held = sum(p.goojf.count(deck) for p in g.players)
        assert len(g.decks[deck]) + held == len(cards)   # no card is ever lost or copied
    if g.phase == "debt":
        assert g.debt and not g.players[g.debt["debtor"]].bankrupt
    assert g.phase in PHASES
    assert g.game_over or g.actor() is not None      # somebody always has a move


# --------------------------------------------------------------------------- the board


def test_board_and_decks():
    assert len(SQUARES) == 40
    assert sum(s.ownable for s in SQUARES) == 28
    assert [len(GROUPS[g]) for g in SETS] == [2, 3, 3, 3, 3, 3, 3, 2]
    assert len(GROUPS["station"]) == 4 and len(GROUPS["utility"]) == 2
    assert len(CHANCE) == len(CHEST) == 16
    assert SQUARES[39].name == "Mayfair" and SQUARES[39].rents[5] == 2000
    assert SQUARES[39].mortgage == 200 and SQUARES[39].unmortgage_cost == 220


def test_tokens_match_the_settings_choices():
    from ten_phases.settings import MONOPOLY_TOKENS
    assert tuple(MONOPOLY_TOKENS) == tuple(TOKENS)
    g = MonopolyGame([MPlayer("A", token="dog"), MPlayer("B", token="dog"), MPlayer("C", token="nope")])
    tokens = [p.token for p in g.players]
    assert tokens[0] == "dog" and len(set(tokens)) == 3 and all(t in TOKENS for t in tokens)


# --------------------------------------------------------------------------- rent


def test_rent_rules():
    g = new_game()
    g.owner[37] = 1
    assert g.rent(37) == 35
    g.owner[39] = 1
    assert g.rent(37) == 70                  # a full set doubles the base rent
    g.houses[37] = g.houses[39] = 3
    assert g.rent(37) == 1100 and g.rent(39) == 1400
    g.houses[39] = 5
    assert g.rent(39) == 2000                # hotel
    for n, k in enumerate((5, 15, 25, 35)):
        g.owner[k] = 2
        assert g.rent(5) == STATION_RENTS[n]
    g.owner[12] = 0
    assert g.rent(12, 7) == 28               # one utility: 4x dice
    g.owner[28] = 0
    assert g.rent(12, 7) == 70               # both: 10x dice


def test_landing_on_property_pays_rent_and_nothing_when_mortgaged():
    g = new_game()
    g.owner[3] = 1
    rig(g, (1, 2))
    g.act(0, "roll")
    assert g.players[0].pos == 3 and g.players[0].cash == 1496 and g.players[1].cash == 1504
    g2 = new_game()
    g2.owner[3], g2.mortgaged[3] = 1, True
    rig(g2, (1, 2))
    g2.act(0, "roll")
    assert g2.players[0].cash == 1500


# --------------------------------------------------------------------------- turns


def test_buy_then_end_turn():
    g = new_game()
    rig(g, (1, 2))
    g.act(0, "roll")
    assert g.phase == "buy" and g.legal(0) == ["buy", "auction"]
    with pytest.raises(RuleError):
        g.act(0, "end")
    g.act(0, "buy")
    assert g.owner[3] == 0 and g.players[0].cash == 1440 and g.phase == "post_roll"
    with pytest.raises(RuleError):
        g.act(1, "roll")                     # not their turn
    g.act(0, "end")
    assert g.current == 1 and g.phase == "pre_roll"


def test_passing_go_pays_200_and_go_to_jail_does_not():
    g = new_game()
    g.players[0].pos = 38
    rig(g, (1, 3))
    g.act(0, "roll")
    assert g.players[0].pos == 2 and g.players[0].cash >= 1700 - 200   # a chest card may change it
    assert any(e.kind == "pay" and e.text == "passed GO" for e in g.history)
    g = new_game()
    g.players[0].pos = 25
    rig(g, (2, 3))
    g.act(0, "roll")
    assert g.players[0].pos == 10 and g.players[0].in_jail and g.players[0].cash == 1500


def test_doubles_roll_again_and_three_doubles_is_jail():
    g = new_game()
    rig(g, (1, 1), (2, 2), (3, 3))
    for _ in range(3):
        g.act(0, "roll")
        if g.phase == "buy":
            g.act(0, "auction")
            while g.phase == "auction":
                g.act(g.actor(), "pass")
        if g.phase != "pre_roll":
            break
    assert g.players[0].in_jail and g.players[0].pos == 10 and g.phase == "post_roll"


def test_jail_doubles_pay_card_and_third_try():
    g = new_game()
    p = g.players[0]
    g._to_jail(0)
    rig(g, (1, 2))
    g.act(0, "roll")
    assert p.in_jail and p.pos == 10 and g.phase == "post_roll"     # no doubles: stay
    g.act(0, "end")
    g.current, g.phase = 0, "pre_roll"
    assert "jail_pay" in g.legal(0) and "jail_card" not in g.legal(0)
    g.act(0, "jail_pay")
    assert not p.in_jail and p.cash == 1450
    # Third failed try: pay £50 and move anyway.
    g = new_game()
    p = g.players[0]
    g._to_jail(0)
    p.jail_turns = 2
    rig(g, (1, 3))
    g.act(0, "roll")
    assert not p.in_jail and p.pos == 14 and p.cash == 1450 - 0 and g.phase == "buy"


def test_get_out_of_jail_free_card_leaves_and_returns_to_its_deck():
    g = new_game()
    card = next(c for c in g.decks["chest"] if c.action == "goojf")
    g.decks["chest"].remove(card)
    g.decks["chest"].insert(0, card)
    rig(g, (1, 1))
    g.act(0, "roll")                         # square 2: Community Chest
    assert g.players[0].goojf == ["chest"] and card not in g.decks["chest"]
    check(g)
    g._to_jail(0)
    g.phase = "pre_roll"
    g.act(0, "jail_card")
    assert not g.players[0].goojf and card in g.decks["chest"] and not g.players[0].in_jail
    check(g)


def test_chance_moves_and_birthday():
    g = new_game()
    card = next(c for c in g.decks["chance"] if c.text.startswith("Advance to Mayfair"))
    g.decks["chance"].remove(card)
    g.decks["chance"].insert(0, card)
    rig(g, (3, 4))
    g.act(0, "roll")
    assert g.players[0].pos == 39 and g.phase == "buy"
    g = new_game(4)
    card = next(c for c in g.decks["chest"] if c.action == "birthday")
    g.decks["chest"].remove(card)
    g.decks["chest"].insert(0, card)
    rig(g, (1, 1))
    g.act(0, "roll")
    assert g.players[0].cash == 1530 and all(p.cash == 1490 for p in g.players[1:])


# --------------------------------------------------------------------------- auctions


def test_auction_goes_to_the_highest_bidder():
    g = new_game()
    rig(g, (1, 2))
    g.act(0, "roll")
    g.act(0, "auction")
    assert g.phase == "auction" and g.actor() == 0
    g.act(0, "bid", amount=20)
    with pytest.raises(RuleError):
        g.act(1, "bid", amount=20)          # must beat the high bid
    g.act(1, "bid", amount=30)
    g.act(2, "pass")
    g.act(0, "pass")
    assert g.owner[3] == 1 and g.players[1].cash == 1470 and g.phase == "post_roll" and g.auction is None
    check(g)


def test_auction_nobody_bids_and_broke_players_drop_out():
    g = new_game()
    rig(g, (1, 2))
    g.act(0, "roll")
    g.act(0, "auction")
    for _ in range(3):
        g.act(g.actor(), "pass")
    assert g.owner[3] is None and g.phase == "post_roll"
    g = new_game()
    g.players[2].cash = 10
    rig(g, (1, 2))
    g.act(0, "roll")
    g.act(0, "auction")
    g.act(0, "bid", amount=50)
    assert g.actor() == 1                    # player 2 can't beat £50: skipped
    g.act(1, "pass")
    assert g.owner[3] == 0 and g.players[0].cash == 1450


# --------------------------------------------------------------------------- building and mortgages


def test_building_rules():
    g = new_game()
    g.owner[37] = 0
    assert "full colour set" in g.why_not_build(0, 37).lower() or g.why_not_build(0, 37)
    g.owner[39] = 0
    g.act(0, "build", sq=37)
    assert g.houses[37] == 1 and g.players[0].cash == 1300
    with pytest.raises(RuleError):
        g.act(0, "build", sq=37)             # build evenly
    g.act(0, "build", sq=39)
    with pytest.raises(RuleError):
        g.act(1, "build", sq=39)             # not theirs
    with pytest.raises(RuleError):
        g.act(0, "mortgage", sq=37)          # houses in the set
    g.act(0, "sell", sq=39)
    with pytest.raises(RuleError):
        g.act(0, "sell", sq=39)              # sell evenly too
    g.act(0, "sell", sq=37)
    assert g.players[0].cash == 1500 - 400 + 200
    g.act(0, "mortgage", sq=37)
    assert g.mortgaged[37] and g.players[0].cash == 1300 + 175
    with pytest.raises(RuleError):
        g.act(0, "build", sq=39)             # no building with a mortgage in the set
    g.act(0, "unmortgage", sq=37)
    assert not g.mortgaged[37] and g.players[0].cash == 1475 - 192
    check(g)


def test_building_only_on_your_own_turn():
    g = new_game()
    g.owner[1] = g.owner[3] = 1
    with pytest.raises(RuleError):
        g.act(1, "build", sq=1)
    g.act(0, "roll")
    while g.actor() != 0 or g.phase not in ("pre_roll", "post_roll"):
        g.act(g.actor(), "pass" if g.phase == "auction" else "auction" if g.phase == "buy" else
              "pay_fine" if g.phase == "fine_or_chance" else "pay")
    g.act(0, "end")
    if g.current == 1 and g.phase == "pre_roll":
        g.act(1, "build", sq=1)
        assert g.houses[1] == 1


# --------------------------------------------------------------------------- debt and bankruptcy


def test_debt_must_be_raised_then_paid():
    g = new_game()
    g.owner[6] = 0
    g.players[0].cash = 100
    g.players[0].pos = 1
    rig(g, (1, 2))                           # Income Tax £200
    g.act(0, "roll")
    assert g.phase == "debt" and g.debt["amount"] == 200 and g.actor() == 0
    assert "pay" not in g.legal(0) and "bankrupt" in g.legal(0)
    g.act(0, "mortgage", sq=6)
    with pytest.raises(RuleError):
        g.act(0, "pay")                      # still short: £150
    g.players[0].cash += 60
    g.act(0, "pay")
    assert g.phase == "post_roll" and g.players[0].cash == 10
    check(g)


def test_bankrupt_to_a_player_hands_over_everything():
    g = new_game()
    g.owner[1] = g.owner[3] = 0
    g.houses[1] = g.houses[3] = 1
    g.owner[39] = 1
    g.houses[39] = 0
    g.owner[37] = 1
    g.houses[37] = g.houses[39] = 5
    g.players[0].cash = 20
    g.players[0].goojf = ["chance"]
    g.decks["chance"] = [c for c in g.decks["chance"] if c.action != "goojf"]
    g.players[0].pos = 35
    rig(g, (2, 2))                           # Mayfair with a hotel: £2000
    g.act(0, "roll")
    assert g.phase == "debt"
    g.act(0, "bankrupt")
    p0, p1 = g.players[0], g.players[1]
    assert p0.bankrupt and not g.props_of(0) and g.owner[1] == g.owner[3] == 1
    assert g.houses[1] == g.houses[3] == 0 and p1.goojf == ["chance"]
    assert p1.cash == 1500 + 20 + 50          # cash plus houses sold back at half price
    assert g.current == 1 and g.phase == "pre_roll"
    check(g)


def test_bankrupt_to_the_bank_returns_property_and_last_one_standing_wins():
    g = new_game(2)
    g.owner[6] = 0
    g.mortgaged[6] = True
    g.players[0].cash = 10
    g.players[0].pos = 1
    rig(g, (1, 2))
    g.act(0, "roll")
    g.act(0, "bankrupt")
    assert g.owner[6] is None and not g.mortgaged[6]
    assert g.game_over and g.winner == 1 and g.phase == "game_over"
    check(g)


def test_game_ends_after_the_last_round_and_the_richest_wins():
    g = new_game(2, rounds=1)
    g.players[1].cash = 5000
    rig(g, (1, 2), (1, 2))
    g.act(0, "roll")
    g.act(0, "auction")
    while g.phase == "auction":
        g.act(g.actor(), "pass")
    g.act(0, "end")
    g.act(1, "roll")
    if g.phase == "buy":
        g.act(1, "auction")
        while g.phase == "auction":
            g.act(g.actor(), "pass")
    g.act(1, "end")
    assert g.game_over and g.winner == 1 and g.round == 1 and g.winners() == [1]


# --------------------------------------------------------------------------- trading


def test_trading():
    g = new_game()
    g.owner[1], g.owner[3], g.owner[6] = 0, 1, 1
    with pytest.raises(RuleError):
        g.act(1, "trade", to=0, give=[3], get=[1])           # only on your own turn
    with pytest.raises(RuleError):
        g.act(0, "trade", to=1, give=[3], get=[1])           # you don't own 3
    with pytest.raises(RuleError):
        g.act(0, "trade", to=1, give=[], get=[], give_cash=0)
    with pytest.raises(RuleError):
        g.act(0, "trade", to=1, give=[1], get=[3], give_cash=99999)
    with pytest.raises(RuleError):
        g.act(0, "trade", to=0, give=[1], get=[])            # not with yourself
    g.act(0, "trade", to=1, give=[1], get=[3, 6], give_cash=100)
    assert g.actor() == 1 and g.legal(1) == ["accept", "decline"]
    with pytest.raises(RuleError):
        g.act(0, "roll")                                     # waiting for an answer
    g.act(1, "accept")
    assert g.owner[1] == 1 and g.owner[3] == g.owner[6] == 0
    assert g.players[0].cash == 1400 and g.players[1].cash == 1600
    g.act(0, "trade", to=2, give=[3], get=[], get_cash=0, give_cash=0)
    g.act(2, "decline")
    assert g.owner[3] == 0
    g.act(0, "trade", to=2, give=[3], get=[])
    g.act(0, "cancel_trade")
    assert g.trade is None and g.owner[3] == 0
    g.owner[1] = 0
    g.houses[1] = g.houses[3] = 1
    with pytest.raises(RuleError):
        g.act(0, "trade", to=1, give=[3], get=[])            # houses in the set
    check(g)


def test_bad_moves_are_refused_not_crashes():
    g = new_game()
    for action, kw in [("bid", {"amount": "lots"}), ("build", {"sq": "x"}), ("build", {"sq": 99}),
                       ("trade", {"to": "x"}), ("trade", {"to": 1, "give": "x"}), ("trade", {"to": 1, "give": [None]}),
                       ("trade", {"to": 1, "give": [], "get": [], "give_cash": -5}), ("fly", {}), ("pay", {}),
                       ("accept", {}), ("cancel_trade", {}), ("sell", {"sq": True})]:
        with pytest.raises(RuleError):
            g.act(0, action, **kw)
    check(g)


# --------------------------------------------------------------------------- whole games


def random_move(g, me, rng):
    legal = g.legal(me)
    opts = [(a, {}) for a in legal if a not in ("bid", "trade", "bankrupt")]
    if "bid" in legal:
        high = g.auction["high"] + 1
        opts.append(("bid", {"amount": rng.randint(high, max(high, g.players[me].cash))}))
    for k in g.props_of(me):
        for a in ("build", "sell", "mortgage", "unmortgage"):
            opts.append((a, {"sq": k}))
    if "trade" in legal and rng.random() < 0.1:
        to = rng.choice([k for k in g.alive() if k != me])
        opts.append(("trade", {"to": to, "give": g.props_of(me)[:1], "get": g.props_of(to)[:1],
                               "give_cash": rng.randint(0, 50), "get_cash": 0}))
    if "bankrupt" in legal and (not opts or rng.random() < 0.3):
        opts.append(("bankrupt", {}))
    return rng.choice(opts)


@pytest.mark.parametrize("seed", range(60))
def test_whole_games_keep_every_rule(seed):
    """Computers of every level (plus some random button-mashers) play whole games; the rules always hold."""
    rng = random.Random(seed)
    n = rng.randint(2, 6)
    levels = ["Easy", "Medium", "Hard", "Expert"]
    g = MonopolyGame([MPlayer(f"P{k}", difficulty=rng.choice(levels)) for k in range(n)], random.Random(seed),
                     max_rounds=rng.choice([20, 40]))
    ais = [MonopolyAI(p.difficulty, random.Random(seed + k)) for k, p in enumerate(g.players)]
    mashers = {k for k in range(n) if rng.random() < 0.3}
    for _ in range(40000):
        if g.game_over:
            break
        me = g.actor()
        if me in mashers:
            action, kw = random_move(g, me, rng)
            try:
                g.act(me, action, **kw)
            except RuleError:
                pass
        else:
            action, kw = ais[me].choose(g, me)
            g.act(me, action, **kw)          # a computer's move is always legal
        check(g)
    assert g.game_over
    assert g.round <= g.max_rounds


def test_harder_computers_win_more():
    wins = {"Easy": 0, "Expert": 0}
    for seed in range(40):
        levels = ["Easy", "Expert", "Easy", "Expert"]
        rng = random.Random(seed)
        rng.shuffle(levels)
        g = MonopolyGame([MPlayer(f"P{k}", difficulty=d) for k, d in enumerate(levels)], random.Random(seed))
        ais = [MonopolyAI(d, random.Random(seed * 10 + k)) for k, d in enumerate(levels)]
        while not g.game_over:
            me = g.actor()
            action, kw = ais[me].choose(g, me)
            g.act(me, action, **kw)
        for w in g.winners():
            wins[levels[w]] += 1
    assert wins["Expert"] > wins["Easy"]


# --------------------------------------------------------------------------- multiplayer


def test_full_monopoly_game_over_localhost():
    from ten_phases.net.client import ClientSession
    from ten_phases.net.host import HostServer
    from test_net import wait_for

    server = HostServer("HOSTY", port=0, announce=False, game="MONOPOLY")
    server.token = "cat"
    try:
        guests = [ClientSession(n, "127.0.0.1", server.port, server.key, token=t)
                  for n, t in (("ANA", "dog"), ("BO", "cat"))]

        def pump_all():
            server.pump()
            for c in guests:
                c.poll()
        assert wait_for(lambda: all(c.status == "joined" and len(c.members) == 3 for c in guests), pump_all)
        guests.sort(key=lambda c: c.my_index)
        server.set_ai_count(1)
        server.monopoly_rounds = 20
        session = server.start_game()
        game = session.game
        assert game.max_rounds == 20
        tokens = {p.name: p.token for p in game.players}
        assert tokens["HOSTY"] == "cat" and tokens["ANA"] == "dog" and tokens["BO"] not in ("cat", "dog")
        assert wait_for(lambda: all(c.game is not None and c.game.players for c in guests), pump_all)
        assert all(type(c.game).__name__ == "RemoteMonopolyGame" for c in guests)
        host_ai = MonopolyAI("Hard", random.Random(1))
        guest_ai = [MonopolyAI("Hard", random.Random(2 + k)) for k in range(2)]
        for _ in range(400000):
            pump_all()
            if game.game_over:
                break
            seat = game.actor()
            if seat == 0 or seat in session.ais:
                ai = session.ais.get(seat) or host_ai
                action, kw = ai.choose(game, seat)
                game.act(seat, action, **kw)
                continue
            rg = guests[seat - 1].game
            if rg.pending or rg.actor() != 0 or rg.round != game.round:
                time.sleep(0.0005)
                continue
            action, kw = guest_ai[seat - 1].choose(rg, 0)
            try:
                rg.act(0, action, **kw)
            except RuleError:
                time.sleep(0.001)
        assert game.game_over
        assert wait_for(lambda: all(c.game.game_over for c in guests), pump_all)
        for c in guests:
            seat = 1 + guests.index(c)
            assert c.game.players[0].name == game.players[seat].name
            assert c.game.players[0].cash == game.players[seat].cash
            n = len(game.players)
            for k in range(40):        # owners are rotated so each guest is seat 0
                o = game.owner[k]
                assert c.game.owner[k] == (None if o is None else (o - seat) % n)
    finally:
        server.close()


def test_monopoly_guest_moves_are_checked_and_leavers_become_computers():
    from ten_phases.net.client import ClientSession
    from ten_phases.net.host import HostServer
    from test_net import wait_for

    server = HostServer("H", port=0, announce=False, game="MONOPOLY")
    try:
        guest = ClientSession("G", "127.0.0.1", server.port, server.key)

        def pump_all():
            server.pump()
            guest.poll()
        assert wait_for(lambda: guest.status == "joined", pump_all)
        session = server.start_game()
        game = session.game
        assert wait_for(lambda: guest.game and guest.game.players, pump_all)
        bad = [{"a": "roll", "x": 1},   # it's the host's turn, so none of these are allowed {"a": "build", "sq": "x"}, {"a": "bid", "amount": [1]}, {"a": 42},
               {"a": "trade", "to": "x"}, {"a": "trade", "to": 0, "give": [1, "x"]}, {"a": "end"},
               {"a": "trade", "to": True, "give": []}]
        for msg in bad:
            guest.send({"t": "act", **msg})
        errors = []
        assert wait_for(lambda: len(errors) >= len(bad),
                        lambda: (server.pump(), errors.extend(m for m in guest.poll() if m["t"] == "error")))
        check(game)
        guest.leave()
        assert wait_for(lambda: 1 in session.ais, server.pump)
        assert not game.players[1].is_human
    finally:
        server.close()


def test_guest_sees_events_rotated_to_their_seat():
    from ten_phases.monopoly.engine import MEvent
    from ten_phases.net.monopoly_net import RemoteMonopolyGame, mono_events_for, mono_snapshot_for

    g = new_game(3)
    g.owner[3] = 2
    rg = RemoteMonopolyGame(lambda msg: None)
    events = [MEvent("rent", 1, 3, 4, "", {"owner": 2}),
              MEvent("pay", 1, None, 4, "rent", {"to": 2, "cash": {"1": 1, "2": 9}})]
    rg.apply(mono_snapshot_for(g, 1), mono_events_for(events, 1, 3))
    assert rg.players[0].name == "P1" and rg.owner[3] == 1
    rent, pay = rg.pop_events()
    assert rent.player == 0 and rent.data["owner"] == 1
    assert pay.data["to"] == 1 and pay.data["cash"] == {"0": 1, "1": 9}


# --------------------------------------------------------------------------- the screens


def frames(app, scene, n, dt=1 / 20):
    for _ in range(n):
        scene.update(dt)
        scene.draw(app.screen)


def test_monopoly_table_plays_a_whole_game(app):
    from ten_phases.ui.monopoly_scene import MonopolyScene

    app.settings.opponents = 3
    app.settings.ai_speed = "Fast"
    bank = app.settings.chip_bank
    scene = MonopolyScene(app, max_rounds=8)
    app.go(scene)
    g = scene.game
    assert g.max_rounds == 8 and g.players[0].token == app.settings.monopoly_token
    me = MonopolyAI("Hard", random.Random(3))
    saw = set()
    for _ in range(60 * 60 * 10):
        scene.update(1 / 15)
        scene.draw(app.screen)
        if scene.cur:
            saw.add(scene.cur.ev.kind)
        if scene.overlay == "game":
            break
        if scene.my_move():
            assert scene.buttons, g.phase            # there's always something to press
            action, kw = me.choose(g, 0)
            scene.act(action, **kw)
    assert scene.overlay == "game"
    assert {"roll", "move", "turn"} <= saw
    worth = max(0, g.net_worth(0)) if not g.players[0].bankrupt else 0
    assert app.settings.chip_bank == bank + worth // 50


def test_table_actions_follow_the_animation(app):
    """The panel never shows what you landed on before your token gets there."""
    from ten_phases.ui.monopoly_scene import MonopolyScene

    scene = MonopolyScene(app)
    app.go(scene)
    scene.splash = None
    g = scene.game
    rig(g, (1, 2))
    frames(app, scene, 40)
    scene.act("roll")
    assert g.phase == "buy" and scene.animating and not scene.settled()
    scene.draw(app.screen)
    assert not any(b.label.startswith("BUY") for b in scene.buttons)
    frames(app, scene, 200)
    assert not scene.animating and scene.vpos[0] == 3
    scene.draw(app.screen)
    assert any(b.label.startswith("BUY") and b.enabled for b in scene.buttons)
    scene.primary()                         # Space/Enter buys
    assert g.owner[3] == 0
    frames(app, scene, 60)
    assert scene.vowner[3] == 0


def test_manage_popup_trade_window_and_admin(app):
    from ten_phases.ui import admin
    from ten_phases.ui.monopoly_scene import MonopolyScene

    scene = MonopolyScene(app)
    app.go(scene)
    scene.splash = None
    g = scene.game
    frames(app, scene, 40)
    g.owner[37] = g.owner[39] = 0
    g.owner[1] = 1
    scene.sync_view()
    click = lambda pos: (scene.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos)),  # noqa: E731
                         scene.handle(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos)))
    from ten_phases.ui import monopoly_art as art
    click(art.cell_rect(39).center)
    assert scene.selected_sq == 39
    scene.draw(app.screen)
    build = next(b for b in scene.manage_buttons if b.label.startswith("BUILD"))
    click(build.rect.center)
    assert g.houses[39] == 1
    frames(app, scene, 30)
    assert scene.vhouses[39] == 1
    scene.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode=""))
    assert scene.selected_sq is None
    scene.open_trade()
    assert scene.trade_ui is not None
    scene.trade_ui["to"] = 1
    scene.trade_ui["get"].add(1)
    scene.trade_ui["give_cash"] = 200
    scene.draw(app.screen)
    scene._propose()
    assert g.trade is None or g.trade["to"] == 1
    frames(app, scene, 120)
    assert g.trade is None                   # the computer answered
    # Admin: give money and a property.
    monkey_unlocked = admin._unlocked
    admin._unlocked = True
    try:
        scene.admin.open = True
        scene.admin._pick_target(2)
        cash = g.players[2].cash
        scene.admin._give_mono("cash500")
        assert g.players[2].cash == cash + 500
        owned = len(g.props_of(2))
        scene.admin._give_mono("property")
        assert len(g.props_of(2)) == owned + 1
        scene.admin._give_mono("jail_card")
        scene.draw(app.screen)
        check(g)
    finally:
        admin._unlocked = monkey_unlocked
        scene.admin.open = False


def test_setup_screen_saves_token_and_length(app):
    from ten_phases.ui.monopoly_scene import MonopolyScene
    from ten_phases.ui.monopoly_setup import MonopolySetupScene, token_rect

    scene = MonopolySetupScene(app)
    app.go(scene)
    scene.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=token_rect(2).center))
    assert app.settings.monopoly_token == "dog"
    scene.rounds.on_change("60")
    scene.draw(app.screen)
    scene._go()
    assert isinstance(app.scene, MonopolyScene)
    assert app.scene.game.max_rounds == 60 and app.scene.game.players[0].token == "dog"
    app.settings.monopoly_rounds, app.settings.monopoly_token = 40, "car"


def test_monopoly_settings_are_validated(tmp_path):
    import json

    from ten_phases.settings import Settings
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"monopoly_rounds": 7, "monopoly_token": "rocket", "game": "MONOPOLY"}))
    s = Settings.load(path)
    assert s.monopoly_rounds == 40 and s.monopoly_token == "car" and s.game == "MONOPOLY"


def test_pausing_as_the_game_ends_still_shows_the_results(app):
    from ten_phases.ui.monopoly_scene import MonopolyScene

    scene = MonopolyScene(app)
    app.go(scene)
    scene.splash = None
    frames(app, scene, 40)
    scene.game._finish()
    scene._consume_events()
    frames(app, scene, 1, 0.01)
    scene.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode=""))
    scene.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode=""))
    frames(app, scene, 30)
    assert scene.overlay == "game"
