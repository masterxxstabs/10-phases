# Project notes for Claude

## Rules from the owner

- **Every game gets multiplayer.** Any new game added to this project must support
  network multiplayer (host/join via invite code, nearby games, lobby, computer
  players filling seats) from the start, the same way 10 Phases and Go Fish do,
  unless the owner explicitly says otherwise for that game.
  - Exception the owner asked for: **Slots is single player** (it bets the real Chip Bank).
    Single-player games go in `SINGLE_PLAYER` in `ui/menus.py`.

## How the project fits together

- `ten_phases/` is the app. Games: 10 Phases, Go Fish, Blackjack, Poker, and Slots (single player). Each has a
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
  shares its move rules with its guest mirror through `PokerRules`). Bump `VERSION` in `net/protocol.py` when the wire format
  changes.
- Chips: games bank chips into `settings.chip_bank`. The Card Shop (`shop.py`, `ui/shop_scene.py`)
  sells card packs (`ui/pack_open.py` is the rip-and-flip opening, `ui/pack_art.py` its art and
  effects). The skins live in `skins.py`; `ui/card_art.py` draws them (generated `g###`/`f###`
  skins via `ui/skin_gen.py`). A generated skin is rebuilt from its number, so never change the
  generator's output for an existing number: players own them and multiplayer relies on it.
- Skins in multiplayer: each player's (face, back) goes in the hello and in every snapshot
  (`player.skin`). Scenes draw other seats' cards through `ui/table_skins.py`.
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
