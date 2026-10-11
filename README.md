# 10 Phases

A Phase 10–style card game in Python. You play against 1–5 computer opponents at the difficulty you choose. The UI is flat, and the cards are bright with a white border and a tilted oval, in the style of classic shedding card games.

## Run it

```bash
pip install -r requirements.txt
python main.py          # or: python -m ten_phases
```

Requires Python 3.10+.

## How to play

- On your turn, click the **deck** or the **discard pile** to draw (Space draws from the deck).
- To complete your phase, select its cards and press **Lay Down**. The game works out how to split them into sets and runs.
- After you've laid down, select cards and click any group on the **table** to add to it.
- To discard, select one card and press **Discard** or click the discard pile. You can also double-click or right-click a card.
- Discarding a **Skip** with more than one opponent lets you click the opponent to skip.
- **Hint** suggests a move (you can turn it off in Settings). **Sort** switches between sorting by number and by color.

| Phase | Requirement |
|---|---|
| 1 | 2 sets of 3 |
| 2 | 1 set of 3 + 1 run of 4 |
| 3 | 1 set of 4 + 1 run of 4 |
| 4 | 1 run of 7 |
| 5 | 1 run of 8 |
| 6 | 1 run of 9 |
| 7 | 2 sets of 4 |
| 8 | 7 cards of one color |
| 9 | 1 set of 5 + 1 set of 2 |
| 10 | 1 set of 5 + 1 set of 3 |

Penalty points for cards left in hand: 1–9 = 5, 10–12 = 10, Skip = 15, Wild = 25. The first player to complete phase 10 wins. If several players finish phase 10 in the same round, the lowest score wins.

## Settings

| Setting | Options |
|---|---|
| AI difficulty | Easy, Medium, Hard, Expert, Mixed (one of each, easiest first) |
| Opponents | 1–5 |
| AI speed | Slow, Normal, Fast |
| Hints | On / Off |
| Sort hand by | Number / Color |

Settings are saved to `~/.ten_phases_settings.json`.

### What the difficulty levels do

The AIs only use information a real player has: their own hand, the discard pile, the table, and what other players have picked up.

- **Easy**: greedy and short-sighted. It makes random discards, misses plays and sometimes doesn't notice it has its phase.
- **Medium**: plans toward its phase and counts which draws would help. It rarely slips up.
- **Hard**: avoids discarding cards the next player wants, aims Skips at the player most likely to win, and dumps high-point cards when someone is about to go out.
- **Expert**: everything Hard does, plus card counting (it tracks every card it has seen) and stronger defense.

In simulated 2-player matches, Medium beats Easy about 90% of the time. Hard and Expert each beat Medium about 80% of the time.

## Project layout

```
ten_phases/
  cards.py      cards and deck
  phases.py     phase definitions, set/run/color validation
  game.py       rules engine (turns, laying down, hitting, skips, scoring)
  ai.py         computer players and difficulty profiles
  settings.py   persisted settings
  ui/           pygame front end (theme, card art, widgets, menus, game table)
tests/          pytest suite for the rules and the AI
```

Run the tests with `python -m pytest`.
