# Project notes for Claude

## Rules from the owner

- **Every game gets multiplayer.** Any new game added to this project must support
  network multiplayer (host/join via invite code, nearby games, lobby, computer
  players filling seats) from the start, the same way 10 Phases and Go Fish do,
  unless the owner explicitly says otherwise for that game.
  - Exceptions the owner asked for: **Slots is single player** (it bets the real Chip Bank), and so is
    **Deep Dig** (`deepdig/engine.py` rules, `deepdig/save.py` its saved game, `ui/deepdig_scene.py`,
    `ui/deepdig_art.py`; inspired by Motherload, our own code and art). The world is endless: `make_chunk`
    makes it CHUNK rows at a time as you dig, and saves keep the rows made so far. Tile numbers are saved, so
    only ever add ores at the end of `ORES` (the core is tile 9; v1 saves had it at 20 and are migrated).
    The town is at negative columns (`TOWN_W`), outside the saved grid: `tile()` answers for it. Dig bots
    (`Bot`, `_step_bot`) live in the engine and are saved with the game. The Oil Field (`deepdig/oil.py`,
    `ui/oil_scene.py`) is bought at the OIL building; it lives on the game as `game.oil`, runs in `step_oil`
    every frame (in the mine too), spends `game.cash`, and its plots are made from the seed and plot number.
- Display: everything draws on a 1280x800 canvas and `pygame.SCALED` fits it to the window or screen (and maps
  the mouse). Fullscreen (`App.set_fullscreen`, F11, Alt+Enter, Settings > DISPLAY) toggles in place; never
  call `set_mode` again while running (it can leave a broken screen).
    Single-player games go in `SINGLE_PLAYER` in `ui/menus.py`.
- **Every game gets controller support.** Any new game (and any new screen) must be fully playable with a
  controller (Xbox, PlayStation, Switch Pro: anything SDL calls a game controller) from the start, no exceptions
  unless the owner says so. It comes from `ui/gamepad.py`, which the app runs for every screen:
  - Pointer screens work on their own: the left stick moves a pointer that `pygame.mouse.get_pos()` follows,
    A clicks (hold to drag), the D-pad is the arrow keys, the right stick scrolls, B and Start are Escape.
  - Give each table its shortcuts with a `pad_buttons` class attribute or property (button name -> pygame key,
    or "click"; names A B X Y LB RB LT RT START BACK LS RS), like `BlackjackScene` (X hit, Y stand...).
  - Action games set `pad_mode = "keys"` (a property can switch to "cursor" when a menu or shop is open), so the
    stick and D-pad are held arrow keys: see `DeepDigScene.pad_mode` / `pad_buttons`.
  - Anything you can only do by typing needs another way in, or a controller player gets stuck there.
  - Add a test that plays the new game's main actions with fake controller events (see `tests/test_gamepad.py`),
    and list its controls in the README's Controllers section.

## How the project fits together

- `ten_phases/` is the app. Games: 10 Phases, Go Fish, Blackjack, Poker, Cards Against Humanity (`cah/`,
  `ui/cah_scene.py`, `ui/cah_setup.py`, `net/cah_net.py`), Monopoly (`monopoly/`, `ui/monopoly_scene.py`,
  `ui/monopoly_setup.py`, `ui/monopoly_art.py`, `net/monopoly_net.py`), and Slots (single player). Each has a
  rules engine with no UI (`game.py`, `gofish/engine.py`, `blackjack/engine.py`, `poker/engine.py`), computer
  players (`ai.py`, `gofish/ai.py`, `blackjack/ai.py`, `poker/ai.py`) and a table scene in `ui/`
  (`game_scene.py`, `gofish_scene.py`, `blackjack_scene.py`, `poker_scene.py`). The main menu's arrows switch games
  (`ui/menus.py`, `GAMES`).
- Multiplayer lives in `net/`. The host's engine is the only real game; guests get
  per-player snapshots with seats rotated so they're seat 0, plus a "Remote…Game"
  mirror that sends moves to the host. To add a game: a snapshot/events function,
  a Remote mirror, a Host session (`handle_action`, `player_left`, `flush`), a lobby
  `GAMES` entry (host.py, menus.py, multiplayer.py picker), and a scene that accepts
  `host`/`session`/`client`. `net/fish_net.py`, `net/bj_net.py` and `net/poker_net.py` are good templates (poker
  shares its move rules with its guest mirror through `PokerRules`, Monopoly through `MonopolyRules`). Bump `VERSION` in `net/protocol.py` when the wire format
  changes.
- Chips: games bank chips into `settings.chip_bank`. The Card Shop (`shop.py`, `ui/shop_scene.py`)
  sells card packs (`ui/pack_open.py` is the rip-and-flip opening, `ui/pack_art.py` its art and
  effects). The skins live in `skins.py`; `ui/card_art.py` draws them (generated `g###`/`f###`
  skins via `ui/skin_gen.py`). A generated skin is rebuilt from its number, so never change the
  generator's output for an existing number: players own them and multiplayer relies on it.
- Skins in multiplayer: each player's (face, back) goes in the hello and in every snapshot
  (`player.skin`). Scenes draw other seats' cards through `ui/table_skins.py`.
- Cards Against Humanity cards are never committed: `cah/cards.py` downloads them from the REST
  Against Humanity API (the owner asked for `https://www.restagainsthumanity.com/gql/`) and caches
  them next to the settings file. Tests use made-up packs (`tests/test_cah.py:fake_packs`).
  Pictures on blank cards travel as base64 JPEG in "img" messages, once per guest.
- Admin panel (`ui/admin.py`): F12 at any card table, password-checked against the salted
  PBKDF2 hash in `admin_key.py` (set with `tools/set_admin_password.py`). Never put the
  plain password in the repo, release notes or tests. Each table scene creates `self.admin`,
  lets it handle events first, adds `admin.blocking` to `flow_blocked`, and draws it last.
- Look and feel: everything is drawn in code (`ui/theme.py`, `ui/card_art.py`) in a
  handheld DS style. Use the theme's color roles so Customize works. Text uses the
  bundled pixel font through `theme.ptext`.

## Releasing

- Bump `__version__` in `ten_phases/__init__.py` and add a section to `CHANGELOG.md`.
  Pushing to `master` builds the Windows exe in GitHub Actions, runs the tests and
  exe checks, and publishes a Release. Players' games update themselves from it.
- Before pushing, run `python -m pytest -q` and `python -m pyflakes ten_phases tests tools`.
  For UI changes, drive the real scenes headless (`SDL_VIDEODRIVER=dummy`) and look at
  screenshots.
- Monopoly: the engine runs instantly and emits `MEvent`s; `ui/monopoly_scene.py` replays them one at a time as
  animations, and the action panel waits (`settled()`) until moves and cards have played out. Board, rents and
  cards follow monopyly (MIT). Keep the whole-game invariant test in `tests/test_monopoly.py` passing.
- Profiles and levels: `profile.py` (catalog, buying, `my_profile`/`clean_profile`/`player_profile`), `levels.py`
  (XP table and curve), `ui/profile_art.py` (pictures, backgrounds, `seat_profile(scene, i)`), `ui/profile_scene.py`.
  Each table makes `self.xp = XpTracker(self, game)` (`ui/xp.py`), feeds it engine events, calls `game_end`, and
  draws it before the admin panel. Profiles travel like skins: "prof" in the hello and in every snapshot.
