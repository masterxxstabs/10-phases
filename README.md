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

## Updates

The game keeps itself up to date:

1. When it starts, it checks this repo's latest GitHub Release. Your version is shown in the bottom-left corner of the main menu and in Settings.
2. If there's a newer `10Phases.exe`, it downloads in the background. The game checks the file's size, its SHA-256 checksum (as reported by GitHub) and that it's a Windows program.
3. The menu shows **UPDATE READY!** with what's new:
   - **RESTART NOW** installs the update and reopens the game.
   - **LATER** installs it when you quit, so your next launch is the new version.

To update, the game renames the running `10Phases.exe` to `10Phases.exe.old` (Windows allows renaming a running program, just not overwriting it) and moves the new file into its place. Leftover files are cleaned up on the next start. If the exe sits in a folder the game can't write to, or you run from source, the menu links to the download instead.

You can turn this off with **Settings → Updates → Off**. In multiplayer, if you and the host are on different versions, the game tells you which ones.

**Publishing an update:** bump `__version__` in `ten_phases/__init__.py`, add a section to `CHANGELOG.md`, and push to `master`. GitHub Actions then does the rest:
- tests and builds the exe on Windows
- checks that the exe starts, and that swapping and restarting it works
- publishes a Release whose notes come from the changelog

Everyone's game picks the update up the next time it opens.

## Build the exe yourself

GitHub Actions builds `10Phases.exe` on Windows for every push to `master`; you can download it from the run's **Artifacts**. When the version in `ten_phases/__init__.py` hasn't been released yet, the workflow also tags the commit and publishes a Release with the exe, so to put out an update you just bump the version. To build locally:

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

**Host:** choose **MULTIPLAYER**, enter your name, then **HOST A GAME**. Pick **10 PHASES**, **GO FISH**, **BLACKJACK** or **POKER** under **GAME** in the lobby; it defaults to whichever game the main menu was showing.
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
- Each player only receives their own hand. Opponents' hands are sent as card counts. In Go Fish, a card someone fishes stays hidden unless it was the number they asked for. In Poker, nobody sees anyone else's two cards until a showdown.
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
| Text | Pixel (the bundled [Jersey 10](https://fonts.google.com/specimen/Jersey+10) font, SIL Open Font License) or Smooth |
| Sparkles | On / Off |

Every panel, outline and shadow is generated from your table color, so any color you pick looks consistent. **RESET LOOK** puts everything back to the default blue.

## Go Fish

The main menu has arrows on both sides of the card fan (or use the **Left/Right** arrow keys) to switch between **10 PHASES** and **GO FISH**. The game remembers which one you picked last.

Go Fish uses the same table, cards and look:
- **Deck:** 48 cards, numbers 1–12 in four colors. A **book** is all four colors of one number.
- **Your turn:** click a card in your hand, then click a player to ask them for that number.
  - If they have any, they hand them all over and you go again.
  - If not: **"GO FISH!"** You draw from the pond, and if you draw the number you asked for, you go again.
- **Books** go down automatically. When all 12 are made, the most books wins, and each book adds 5 chips to your Chip Bank.
- **Computer players** remember what's been asked out loud. Easy forgets quickly, Medium remembers a few turns, Hard remembers everything and weighs the odds, and Expert also tracks who said "go fish". In simulated 4-player games, the win rates were Easy 11%, Medium 22%, Hard 26% and Expert 40%.
- **Helpers:** speech bubbles show every question and answer, the **BOOKS** board shows all 12 books and who made each, and **HINT** suggests who to ask for what.
- **Hover:** hovering a player shows their books and, with Hints on, what they've asked for.

Settings (opponents, AI level, speed, sounds, hints) and Customize apply to both games. All three games work in multiplayer: the host picks the game in the lobby.

## Blackjack

The third game on the main menu. You and the other players each play against a computer dealer for 10 hands:
- **Cards:** a 4-deck shoe of A, 2–10, J, Q and K in the four colors (the colors act as suits). J, Q and K count 10; an Ace counts 1 or 11.
- **Betting:** everyone starts with 50 chips. Pick a bet of 1–10 with **−/+** and press **DEAL**.
- **Your turn:** **HIT**, **STAND**, **DOUBLE** (double your bet for exactly one more card) or **SPLIT** a pair, once per hand. Split aces get one card each. Keys: H, S, D, P.
- **The dealer** checks for blackjack under an Ace or 10-value card, then hits until 17 or more. Wins pay 1:1, blackjack pays 3:2, and ties push.
- **Winning:** after 10 hands, the most chips wins. The chips you finish with go into your Chip Bank.
- **Hint** shows the basic-strategy move and why ("16 against 10: the dealer is likely to make 17+, so hit").

**Computer players:**
- **Easy** plays by feel.
- **Medium** copies the dealer.
- **Hard** plays perfect basic strategy.
- **Expert** adds Hi-Lo card counting, which changes its bets and a few plays.

Return per chip bet over 20,000 simulated hands: Easy −6.7%, Medium −4.6%, Hard −0.2%, Expert +0.7%.

Hovering a seat shows that player's chips, net for the game, current hands and recent results.

## Poker

The fourth game on the main menu: no-limit Texas Hold'em for 2-6 players.
- **Cards:** 52 cards, 2-10, J, Q, K and A in the four colors (the colors are the suits). Make the best five-card hand from your two cards and the five shared ones.
- **Chips:** everyone starts with 50. The blinds start at 1/2 and double every 5 hands.
- **Betting:** four rounds (before the flop, the flop, the turn, the river). **FOLD**, **CHECK** or **CALL**, or **RAISE** any amount you like.
- **Choosing your bet:** drag the chip along the slider, nudge it with **-/+** (or the arrow keys and mouse wheel), or tap **MIN**, **1/2 POT**, **POT** or **ALL IN**. The raise button always shows exactly what you'll put in.
- **Winning:** after 15 hands (or when one player has every chip), the most chips wins. The chips you finish with go into your Chip Bank. Side pots are handled automatically when someone is all in.
- **Hint** estimates your chance to win and compares it with the price of calling. Keys: F fold, C check/call, R raise.

**Computer players** only ever see their own cards and the board:
- **Easy** calls too much and never bluffs.
- **Medium** plays by pot odds.
- **Hard** sizes its bets to the pot and bluffs now and then.
- **Expert** adds position, semi-bluffs, blind steals and varied bet sizes.

## Card Shop

The **SHOP** button under your Chip Bank opens the shop. Spend chips on card packs, then equip the skins you find:

| Pack | Price | What's inside |
|---|---|---|
| **Basic** | 75 | 3 skins, anything can happen |
| **Premium** | 200 | 3 skins, the last one Rare or better |
| **Legendary** | 500 | 3 skins, the last one Epic or better |

- Open a pack by swiping across the top to rip it (or tap it / press SPACE), then flip the cards one at a time. Rare cards glow before you flip them.
- Skins come in Common, Rare, Epic and Legendary. The shop shows each pack's odds.
- Duplicates pay back chips: 10 / 25 / 60 / 150 by rarity.
- Free for everyone, and never in packs: Classic, Bubble and Minimal fronts; Classic, Checker and Racing Stripes backs.
- There are almost 300 skins: hand-made ones like Neon, Holo Foil and the Koi Pond set, plus a big generated collection with lots of foil finishes. CARD FRONTS and CARD BACKS show your collection page by page.
- Skins work in every game and in multiplayer: other players see your fronts on the cards you play and your backs on the cards in your hand. Computer players get random skins.

## Slots

**LUCKY 10 SLOTS** is the 4th stop on the main menu. Unlike the other games it's **single player** on purpose, and it plays with your real Chip Bank:
- **Betting:** bet 1, 5, 10 or 25, then pull the lever, press **SPIN** or hit Space.
- **Winning:** match three symbols on the payline. **WILD** counts as any symbol except the jackpot, and three **10 PHASES** cards pay **300×**.
- **Small wins:** two cherries pay 2×, and a cherry on the first reel gives your bet back.
- **Odds:** the machine returns 95.0% of what's bet over time (the exact figure is computed over every reel combination). About 37% of spins win something.

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

When a game ends, the chips you finished with go into your **Chip Bank**, which is shown in the top-left of the main menu and saved between sessions.

## Player info on hover

Hover over any player's box to open their info card:
- their phase on a 10-step tracker, and what that phase needs
- their card count, chips, points, and whether they've laid down
- their groups on the table at full card size, labelled like "SET OF 4 · ALL 9s" or "RUN OF 4 · 3 TO 6"
- the cards they picked up from the discard pile this round
- their last few moves

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
  gofish/       Go Fish rules (engine.py) and computer players (ai.py)
  blackjack/    Blackjack rules (engine.py), computer players, basic strategy and the Hint (ai.py)
  poker/        Texas Hold'em rules, hand ranking and side pots (engine.py), computer players and the Hint (ai.py)
  slots/        the slot machine: reels, payouts and its exact return-to-player (engine.py)
  skins.py      every card skin and its rarity, including the generated ones
  shop.py       card packs (odds, opening, duplicates) and equipping skins
  names.py      computer player names
  settings.py   persisted settings
  updater.py    checks GitHub Releases, downloads, verifies and installs new versions
tools/          make_icon.py (app icon), build.py (PyInstaller one-file build),
                check_update.py (self-update check on the real exe), release_notes.py (from CHANGELOG.md)
.github/        workflow that builds and publishes the Windows exe
  net/          multiplayer: invite codes and connections (protocol.py), LAN discovery,
                host lobby and game session (host.py), guest connection (client.py),
                per-player views and the guest's mirror of the game (snapshot.py)
  ui/           pygame front end (theme, card art, widgets, menus, game table)
                all art and sound is generated in code (ui/sfx.py), so there are no asset files
tests/          pytest suite for the rules and the AI
```

Run the tests with `python -m pytest`.
