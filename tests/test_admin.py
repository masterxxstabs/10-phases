"""The password-locked admin panel: unlocking, giving cards in every game, and kicking guests."""

import os
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

from ten_phases.cards import COLORS  # noqa: E402
from ten_phases.ui import admin  # noqa: E402


@pytest.fixture
def unlocked(monkeypatch):
    monkeypatch.setattr(admin, "_unlocked", True)
    yield
    admin.lock()


def test_password_is_checked_against_the_hash_only():
    import ten_phases.admin_key as key
    assert len(key.HASH) == 64 and len(key.SALT) == 32
    assert not admin.check_password("")
    assert not admin.check_password("password")
    assert not admin.check_password(key.HASH)


def test_wrong_passwords_lock_you_out(app):
    from ten_phases.ui.game_scene import GameScene
    admin.lock()
    scene = GameScene(app)
    panel = scene.admin
    for _ in range(admin.MAX_TRIES):
        panel.password.value = "nope"
        panel._try_unlock()
    assert not admin.is_unlocked() and panel.lockout > 0
    panel.password.value = "still nope"
    panel._try_unlock()
    assert "Wait" in panel.flash


def _scene(app, name):
    from ten_phases.ui.blackjack_scene import BlackjackScene
    from ten_phases.ui.game_scene import GameScene
    from ten_phases.ui.gofish_scene import GoFishScene
    from ten_phases.ui.poker_scene import PokerScene
    return {"phases": GameScene, "fish": GoFishScene, "blackjack": BlackjackScene, "poker": PokerScene}[name](app)


@pytest.mark.parametrize("kind", ["phases", "fish", "blackjack", "poker"])
def test_giving_cards_in_every_game(app, unlocked, kind):
    scene = _scene(app, kind)
    app.go(scene)
    g = scene.game
    if kind == "blackjack":   # wait for the deal
        for i in g.waiting_for_bets():
            g.place_bet(i, 1)
        scene._consume_events()
    scene.admin.toggle()
    scene.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(640, 400), button=1))   # the panel eats clicks
    assert scene.admin.open and scene.admin.blocking and scene.flow_blocked
    before = admin.player_cards(scene, 1)
    scene.admin._pick_target(1)
    color, value = COLORS[2], 9
    if kind == "poker":   # only one of each card exists: use one that's still in the deck
        color, value = g.deck[0].color, g.deck[0].value
    scene.admin.color_k, scene.admin.value = COLORS.index(color), value
    scene.admin._give()
    after = admin.player_cards(scene, 1)
    if kind == "poker":
        assert len(after) == 2 and (after[0].color, after[0].value) == (color, value)
        scene.admin._give()   # the same card again: refused, there's only one in the deck
        assert "already in play" in scene.admin.flash
    elif kind == "fish" and len(after) < len(before):
        assert 9 in g.players[1].books   # it completed a book
    else:
        assert len(after) == len(before) + 1 and after[-1].value == value
    scene.draw(app.screen)
    scene.admin.close()
    assert not scene.flow_blocked or scene.anims or scene.splash


def test_chip_bank_button(app, unlocked):
    from ten_phases.ui.game_scene import GameScene
    scene = GameScene(app)
    app.settings.chip_bank = 5
    scene.admin.open = True
    scene.admin._chips()
    assert app.settings.chip_bank == 105


def test_host_can_kick_a_guest_and_guests_cannot_edit(app, unlocked):
    from ten_phases.net.client import ClientSession
    from ten_phases.net.host import HostServer
    from ten_phases.ui.poker_scene import PokerScene

    server = HostServer("HOST", port=0, announce=False, game="POKER")
    try:
        guest = ClientSession("PAL", "127.0.0.1", server.port, server.key)
        end = time.monotonic() + 5
        while guest.status != "joined" and time.monotonic() < end:
            server.pump()
            guest.poll()
            time.sleep(0.01)
        server.set_ai_count(1)
        session = server.start_game()
        while not (guest.game and guest.game.players) and time.monotonic() < end:
            server.pump()
            guest.poll()
            time.sleep(0.01)
        host_scene = PokerScene(app, host=server, session=session)
        guest_scene = PokerScene(app, client=guest)
        assert not guest_scene.admin.can_edit
        guest_scene.admin.target = 0
        guest_scene.admin._layout()
        assert not guest_scene.admin.picker[-1].enabled

        # The host swaps a card into the guest's hand; the guest sees it.
        host_scene.admin._pick_target(1)
        free = next(c for c in session.game.deck)
        host_scene.admin.color_k, host_scene.admin.value = COLORS.index(free.color), free.value
        host_scene.admin._give()
        while time.monotonic() < end:
            guest.poll()
            mine = guest.game.players[0].hole
            if any((c.color, c.value) == (free.color, free.value) for c in mine):
                break
            time.sleep(0.01)
        else:
            pytest.fail("the guest never saw the new card")

        host_scene.admin._layout()
        _, kick = host_scene.admin.row_buttons[1]
        assert kick is not None
        host_scene.admin._kick(1)
        assert not server.guests and session.game.players[1].is_human is False
        while guest.status not in ("closed", "failed") and time.monotonic() < end + 5:
            guest.poll()
            time.sleep(0.01)
        assert guest.status == "closed" and "removed" in (guest.error or "")
    finally:
        server.close()
