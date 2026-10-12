"""The board and the card decks (the classic London board, prices in pounds).

The board layout, prices, rents and card decks follow monopyly by Richard
Shepherd (https://github.com/richard-shepherd/monopyly, MIT License).
"""

from __future__ import annotations

from dataclasses import dataclass

STARTING_CASH = 1500
GO_SALARY = 200
JAIL_FINE = 50
JAIL = 10
GO_TO_JAIL = 30
STATION_RENTS = (25, 50, 100, 200)

# Colour sets, in board order.
SETS = {
    "brown": (142, 84, 52),
    "light_blue": (150, 214, 248),
    "pink": (214, 56, 150),
    "orange": (247, 148, 29),
    "red": (232, 36, 44),
    "yellow": (250, 230, 20),
    "green": (24, 166, 84),
    "dark_blue": (0, 104, 184),
}


@dataclass(frozen=True)
class Square:
    index: int
    kind: str            # go, street, station, utility, tax, chance, chest, jail, parking, gotojail
    name: str
    price: int = 0
    group: str = ""      # colour set for streets ("station"/"utility" for those)
    house_price: int = 0
    rents: tuple = ()    # streets: (base, 1 house, 2, 3, 4, hotel)
    tax: int = 0

    @property
    def ownable(self) -> bool:
        return self.kind in ("street", "station", "utility")

    @property
    def mortgage(self) -> int:
        return self.price // 2

    @property
    def unmortgage_cost(self) -> int:
        return int(self.mortgage * 1.1)

    @property
    def short(self) -> str:
        return self.name.replace(" Station", "").replace("Street", "St.").replace("Road", "Rd.")


def _street(i, name, group, price, house, rents):
    return Square(i, "street", name, price, group, house, tuple(rents))


SQUARES: tuple[Square, ...] = (
    Square(0, "go", "GO"),
    _street(1, "Old Kent Road", "brown", 60, 50, [2, 10, 30, 90, 160, 250]),
    Square(2, "chest", "Community Chest"),
    _street(3, "Whitechapel Road", "brown", 60, 50, [4, 20, 60, 180, 320, 450]),
    Square(4, "tax", "Income Tax", tax=200),
    Square(5, "station", "Kings Cross Station", 200, "station"),
    _street(6, "The Angel Islington", "light_blue", 100, 50, [6, 30, 90, 270, 400, 550]),
    Square(7, "chance", "Chance"),
    _street(8, "Euston Road", "light_blue", 100, 50, [6, 30, 90, 270, 400, 550]),
    _street(9, "Pentonville Road", "light_blue", 120, 50, [8, 40, 100, 300, 450, 600]),
    Square(10, "jail", "Jail"),
    _street(11, "Pall Mall", "pink", 140, 100, [10, 50, 150, 450, 625, 750]),
    Square(12, "utility", "Electric Company", 150, "utility"),
    _street(13, "Whitehall", "pink", 140, 100, [10, 50, 150, 450, 625, 750]),
    _street(14, "Northumberland Avenue", "pink", 160, 100, [12, 60, 180, 500, 700, 900]),
    Square(15, "station", "Marylebone Station", 200, "station"),
    _street(16, "Bow Street", "orange", 180, 100, [14, 70, 200, 550, 750, 950]),
    Square(17, "chest", "Community Chest"),
    _street(18, "Marlborough Street", "orange", 180, 100, [14, 70, 200, 550, 750, 950]),
    _street(19, "Vine Street", "orange", 200, 100, [16, 80, 220, 600, 800, 1000]),
    Square(20, "parking", "Free Parking"),
    _street(21, "Strand", "red", 220, 150, [18, 90, 250, 700, 875, 1050]),
    Square(22, "chance", "Chance"),
    _street(23, "Fleet Street", "red", 220, 150, [18, 90, 250, 700, 875, 1050]),
    _street(24, "Trafalgar Square", "red", 240, 150, [20, 100, 300, 750, 925, 1100]),
    Square(25, "station", "Fenchurch Street Station", 200, "station"),
    _street(26, "Leicester Square", "yellow", 260, 150, [22, 110, 330, 800, 975, 1150]),
    _street(27, "Coventry Street", "yellow", 260, 150, [22, 110, 330, 800, 975, 1150]),
    Square(28, "utility", "Water Works", 150, "utility"),
    _street(29, "Piccadilly", "yellow", 280, 150, [22, 120, 360, 850, 1025, 1200]),
    Square(30, "gotojail", "Go To Jail"),
    _street(31, "Regent Street", "green", 300, 200, [26, 130, 390, 900, 1100, 1275]),
    _street(32, "Oxford Street", "green", 300, 200, [26, 130, 390, 900, 1100, 1275]),
    Square(33, "chest", "Community Chest"),
    _street(34, "Bond Street", "green", 320, 200, [28, 150, 450, 1000, 1200, 1400]),
    Square(35, "station", "Liverpool Street Station", 200, "station"),
    Square(36, "chance", "Chance"),
    _street(37, "Park Lane", "dark_blue", 350, 200, [35, 175, 500, 1100, 1300, 1500]),
    Square(38, "tax", "Super Tax", tax=100),
    _street(39, "Mayfair", "dark_blue", 400, 200, [50, 200, 600, 1400, 1700, 2000]),
)
assert len(SQUARES) == 40 and all(s.index == k for k, s in enumerate(SQUARES))


def group_members(group: str) -> list[int]:
    return [s.index for s in SQUARES if s.group == group]


GROUPS = {g: group_members(g) for g in list(SETS) + ["station", "utility"]}


@dataclass(frozen=True)
class Card:
    deck: str        # chance or chest
    text: str
    action: str      # money, move, back3, back_to, jail, repairs, goojf, birthday, fine_or_chance
    amount: int = 0
    target: int = 0
    hotel: int = 0   # repairs: per hotel (amount = per house)


def _c(text, action, amount=0, target=0, hotel=0):
    return Card("chance", text, action, amount, target, hotel)


def _cc(text, action, amount=0, target=0, hotel=0):
    return Card("chest", text, action, amount, target, hotel)


CHANCE: tuple[Card, ...] = (
    _c("Advance to Mayfair.", "move", target=39),
    _c("Advance to GO. Collect £200.", "move", target=0),
    _c("You are assessed for street repairs: £40 per house, £115 per hotel.", "repairs", 40, hotel=115),
    _c("Go to Jail. Move directly to Jail. Do not pass GO. Do not collect £200.", "jail"),
    _c("Bank pays you dividend of £50.", "money", 50),
    _c("Go back 3 spaces.", "back3"),
    _c("Pay school fees of £150.", "money", -150),
    _c("Make general repairs on all your houses: £25 per house, £100 per hotel.", "repairs", 25, hotel=100),
    _c("Speeding fine £15.", "money", -15),
    _c("You have won a crossword competition. Collect £100.", "money", 100),
    _c("Your building and loan matures. Collect £150.", "money", 150),
    _c("Get Out of Jail Free. Keep this card until needed.", "goojf"),
    _c("Advance to Trafalgar Square. If you pass GO, collect £200.", "move", target=24),
    _c("Take a trip to Marylebone Station. If you pass GO, collect £200.", "move", target=15),
    _c("Advance to Pall Mall. If you pass GO, collect £200.", "move", target=11),
    _c("\"Drunk in charge\" fine £20.", "money", -20),
)

CHEST: tuple[Card, ...] = (
    _cc("Income tax refund. Collect £20.", "money", 20),
    _cc("From sale of stock you get £50.", "money", 50),
    _cc("It is your birthday. Collect £10 from each player.", "birthday", 10),
    _cc("Receive interest on 7% preference shares: £25.", "money", 25),
    _cc("Get Out of Jail Free. Keep this card until needed.", "goojf"),
    _cc("Advance to GO. Collect £200.", "move", target=0),
    _cc("Pay hospital £100.", "money", -100),
    _cc("You have won second prize in a beauty contest. Collect £10.", "money", 10),
    _cc("Bank error in your favour. Collect £200.", "money", 200),
    _cc("You inherit £100.", "money", 100),
    _cc("Go to Jail. Move directly to Jail. Do not pass GO. Do not collect £200.", "jail"),
    _cc("Pay your insurance premium £50.", "money", -50),
    _cc("Pay a £10 fine or take a Chance.", "fine_or_chance", 10),
    _cc("Doctor's fee. Pay £50.", "money", -50),
    _cc("Go back to Old Kent Road.", "back_to", target=1),
    _cc("Annuity matures. Collect £100.", "money", 100),
)
