"""Whose skin is each card drawn in?

Your own cards always use the skins you have equipped. Everyone else's cards
use theirs: the backs of the cards in their hand, and the fronts of the cards
they lay down, discard, or show. A card takes the skin of the last player who
held it.
"""

from __future__ import annotations

from ..skins import player_skin


class TableSkins:
    def __init__(self, scene):
        self.scene = scene
        self.owner: dict[int, int] = {}   # card id -> seat of the last player who held it

    def seat(self, i: int | None) -> tuple[str | None, str | None]:
        """(face, back) for a seat; None means "whatever you have equipped"."""
        players = self.scene.game.players
        if i is None or i == 0 or not 0 <= i < len(players):
            return None, None
        return player_skin(players[i])

    def face(self, i: int | None) -> str | None:
        return self.seat(i)[0]

    def back(self, i: int | None) -> str | None:
        return self.seat(i)[1]

    def own(self, card, seat: int | None) -> None:
        if card is not None and seat is not None and getattr(card, "id", -1) >= 0:
            self.owner[card.id] = seat

    def card_face(self, card, default: int | None = None) -> str | None:
        return self.face(self.owner.get(card.id, default))

    def reset(self) -> None:
        self.owner.clear()
