# 10 Phases

A Phase 10–style card game in Python. You play against 1–5 computer opponents at the difficulty you choose.

The look is inspired by handheld card games like UNO 52 on the Nintendo DS:
- a bright blue sparkle table split into two "screens"
- opponents in outlined boxes along the top, each showing their cards, chips, phase and laid-down groups
- the piles in the middle with orange turn arrows and a tilted logo
- pixel lettering and a black status bar
- bright cards with a white border and a tilted oval

## Download (Windows)

Get **`10Phases.exe`** from the [Releases page](../../releases/latest) and double-click it. It's a single file, so there's nothing to install and no Python needed. Share the same file with friends for multiplayer.

- **"Windows protected your PC":** the exe isn't code-signed, so Windows shows this warning. Click **More info**, then **Run anyway**.
- **Firewall prompt the first time you host:** allow it on private networks so friends can connect.
- **Startup:** the game unpacks itself for a couple of seconds when it starts.

## Build the exe yourself

GitHub Actions builds `10Phases.exe` on Windows for every push to `master` (download it from the run's **Artifacts**). Pushing a tag such as `v1.0.1` also publishes the exe on a Release. To build locally:

```bash
pip install -r requirements.txt pyinstaller pillow
python tools/build.py        # -> dist/10Phases.exe on Windows (dist/10Phases on macOS/Linux)
dist/10Phases.exe --smoke-test   # opens the game briefly and exits; exit code 0 means OK
```

Builds are per-OS, so build on Windows to get a Windows exe. The version number lives in `ten_phases/__init__.py`.

## Run from source

```bash
pip install -r requirements.txt
python main.py          # or: python -m ten_phases
```

Requires Python 3.10+.

## Multiplayer

Play with up to 5 friends, and fill any empty seats with computer players. There's no server to run, because one player's game hosts the table.

**Host:** choose **MULTIPLAYER**, enter your name, then **HOST A GAME**.
- You get an invite code like `DAAAA-SCZH7-RE8PR`. **COPY CODE** puts it on your clipboard so you can send it to friends.
- Choose how many computer players to add and their level, then press **START GAME** once your friends are in.
- **KICK** removes a player from the lobby.

**Join:** choose **MULTIPLAYER**, enter your name, then either:
- **Same Wi-Fi:** the host's game appears under **GAMES NEARBY**. Press **JOIN**.
- **Code:** paste the invite code (Ctrl+V or the **PASTE** button) and press **JOIN**.

**Playing over the internet.** The invite code contains the host's address, so friends outside your network need a way to reach your computer. Pick one:
1. **A free VPN like [Tailscale](https://tailscale.com) or ZeroTier (easiest).** Everyone installs it and joins the same network. In the lobby, the host presses **OTHER ADDRESS** until it shows the `100.x.x.x` VPN address, then sends that code.
2. **Port forwarding.** On the host's router, forward **TCP port 47610** to the host's computer. In the lobby, type your public IP (search "what is my IP") into **PUBLIC IP**, press **USE IP**, and send that code.

The first time you host, your firewall (for example Windows Defender Firewall) may ask whether to allow 10 Phases. Allow it on private networks, or friends won't be able to connect.

**How it works**
- The host's game is the only real copy of the game. Guests send their moves, and the host checks every one against the rules.
- Each player only receives their own hand. Opponents' hands are sent as card counts.
- If a guest disconnects mid-game, a Medium computer player takes over their seat.
- If the host leaves, guests are told and sent back to the menu.
- When a game ends, the host can take everyone **BACK TO LOBBY** to play again.
- The pause menu doesn't stop a network game.
- Invite codes contain a random room key and change every time you host.

## Customize the look

Choose **CUSTOMIZE** from the main menu, or from the pause menu during a game to come back to the same hand. Changes show up right away in a live preview and across the whole game.

| Option | Choices |
|---|---|
| Table color | 9 presets (Classic Blue, Midnight, Felt Green, Cherry, Grape, Sunset, Teal, Bubblegum, Slate), or any color from the rainbow bar |
| Accent | Yellow, Orange, Pink, Cyan, Lime, White (highlights, buttons, titles) |
| Card back | Red, Blue, Green, Purple, Orange, Black |
| Card colors | Classic, Pastel, Colorblind (Okabe-Ito colors that are easier to tell apart) |
| Text | Pixel or Smooth |
| Sparkles | On / Off |

Every panel, outline and shadow is generated from your table color, so any color you pick looks consistent. **RESET LOOK** puts everything back to the default blue.

## Knowing your phase

- **Your Phase board** (middle right) shows your phase in big letters and a 10-step tracker. It has a slot for each group you need, such as "SET OF 3". With Hints on, each slot fills with the cards you already have toward it and shows your progress (for example "2/3"). Once you lay down, your groups sit in those slots, and you can click them to add more cards.
- A **"PHASE N" banner** introduces each round, and a "PHASE COMPLETE!" banner appears when you lay down.
- Every opponent's box shows their phase, what it needs, and the groups they've laid down.

## Sound effects

Retro chiptune sound effects play for:
- button clicks and selecting cards
- drawing, discarding, laying down and adding to groups
- skips, your turn, mistakes, reshuffles and the phase banner
- winning the pot, and the end of a round or game

They're generated in code when the game starts, so there are no audio files. You can set the volume to Off, Low, Medium or High in Settings. There's no music.

## Chips

Everyone starts with 24 chips. At the start of each round, every player antes 1 chip into the pot, and whoever goes out wins the whole pot. Chips break ties after phases and penalty points.

## How to play

- On your turn, click the **deck** or the **discard pile** to draw (Space draws from the deck).
- To complete your phase, select its cards and press **Lay Down**. The game works out how to split them into sets and runs.
- After you've laid down, select cards and click any group to add to it. Groups are in the opponent boxes and on your Phase board.
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

Penalty points for cards left in hand: 1–9 = 5, 10–12 = 10, Skip = 15, Wild = 25. The first player to complete phase 10 wins. If several players finish phase 10 in the same round, the lowest score wins, then the most chips.

## Settings

| Setting | Options |
|---|---|
| AI difficulty | Easy, Medium, Hard, Expert, Mixed (one of each, easiest first) |
| Opponents | 1–5 |
| AI speed | Slow, Normal, Fast |
| Hints | On / Off (Hint button and progress on your Phase board) |
| Sort hand by | Number / Color |
| Sound FX | Off, Low, Medium, High |

Settings and your custom look are saved to `~/.ten_phases_settings.json`.

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
tools/          make_icon.py (app icon from the card art), build.py (PyInstaller one-file build)
.github/        workflow that builds and publishes the Windows exe
  net/          multiplayer: invite codes and connections (protocol.py), LAN discovery,
                host lobby and game session (host.py), guest connection (client.py),
                per-player views and the guest's mirror of the game (snapshot.py)
  ui/           pygame front end (theme, card art, widgets, menus, game table)
                all art and sound is generated in code (ui/sfx.py), so there are no asset files
tests/          pytest suite for the rules and the AI
```

Run the tests with `python -m pytest`.
