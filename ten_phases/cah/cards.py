"""Cards Against Humanity card data, fetched from the REST Against Humanity API.

The cards (CC BY-NC-SA, Cards Against Humanity LLC) aren't shipped with the game:
the first time you play, every pack is downloaded in one request and saved next
to your settings, so later games (and offline play) use the saved copy.

Only the host's copy needs the cards. Guests get the text of the cards in play
from the host.

The data, after `normalize`, is a list of packs:
    {"id": 0, "name": "CAH Base Set", "white": ["...", ...], "black": [{"text": "...", "pick": 1}, ...]}
"""

from __future__ import annotations

import json
import threading
import urllib.parse
import urllib.request
from pathlib import Path

from .. import __version__

GQL_URLS = ("https://www.restagainsthumanity.com/gql/", "https://www.restagainsthumanity.com/api/graphql")
REST_URL = "https://www.restagainsthumanity.com/api/v2"
QUERY = "{ packs { id name white { text } black { text pick } } }"
USER_AGENT = f"10Phases/{__version__}"
CACHE_NAME = ".ten_phases_cah_cards.json"
MAX_TEXT = 300


class CardDataError(Exception):
    """The cards couldn't be loaded; the message is shown to the player."""


def cache_path() -> Path:
    from .. import settings
    return Path(settings.SETTINGS_PATH).parent / CACHE_NAME


def _clean(text) -> str:
    return " ".join(str(text).split())[:MAX_TEXT]


def normalize(raw) -> list[dict]:
    """Accept the API's shapes (GraphQL or REST) and return tidy packs. Bad entries are skipped."""
    if isinstance(raw, dict):
        raw = (raw.get("data") or {}).get("packs", raw.get("packs"))
    if not isinstance(raw, list):
        raise CardDataError("The card server sent something unexpected.")
    packs = []
    for k, p in enumerate(raw):
        if not isinstance(p, dict) or not isinstance(p.get("name"), str):
            continue
        white = [_clean(c["text"] if isinstance(c, dict) else c) for c in p.get("white") or []
                 if (isinstance(c, dict) and isinstance(c.get("text"), str)) or isinstance(c, str)]
        black = []
        for c in p.get("black") or []:
            if isinstance(c, dict) and isinstance(c.get("text"), str):
                pick = c.get("pick", 1)
                pick = pick if isinstance(pick, int) and 1 <= pick <= 3 else max(1, min(3, c["text"].count("_") or 1))
                black.append({"text": _clean(c["text"]), "pick": pick})
        pid = p.get("id") if isinstance(p.get("id"), int) else k
        packs.append({"id": pid, "name": _clean(p["name"]), "white": [w for w in white if w],
                      "black": [b for b in black if b["text"]]})
    if not packs:
        raise CardDataError("The card server didn't send any packs.")
    return packs


def _request(url: str, body: bytes | None = None, timeout: float = 20.0):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_packs(timeout: float = 20.0) -> list[dict]:
    """Download every pack. Tries the GraphQL API first, then the REST one."""
    errors = []
    body = json.dumps({"query": QUERY}).encode()
    for url in GQL_URLS:
        try:
            data = _request(url, body, timeout)
            if isinstance(data, dict) and data.get("errors") and not data.get("data"):
                raise CardDataError(str(data["errors"])[:200])
            return normalize(data)
        except Exception as e:   # noqa: BLE001 - any failure means "try the next way"
            errors.append(f"{url}: {e}")
    try:   # REST: the pack names, then each pack's cards
        names = _request(f"{REST_URL}/packs", timeout=timeout)
        packs = []
        for k, name in enumerate(names):
            q = urllib.parse.urlencode({"packs": name})
            deck = _request(f"{REST_URL}/cards?{q}", timeout=timeout)
            packs.append({"id": k, "name": name, "white": deck.get("white", []), "black": deck.get("black", [])})
        return normalize(packs)
    except Exception as e:   # noqa: BLE001
        errors.append(f"{REST_URL}: {e}")
    raise CardDataError("Couldn't download the cards. Check your internet connection and try again.")


def save_cache(packs: list[dict], path: Path | None = None) -> None:
    path = path or cache_path()
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(packs))
        tmp.replace(path)
    except OSError:
        pass


def load_cache(path: Path | None = None) -> list[dict] | None:
    path = path or cache_path()
    try:
        return normalize(json.loads(path.read_text()))
    except (OSError, ValueError, CardDataError):
        return None


class CardLibrary:
    """Loads the packs in the background so the screen never freezes."""

    def __init__(self, fetch=fetch_packs):
        self._fetch = fetch
        self.packs: list[dict] | None = load_cache()
        self.status = "ready" if self.packs else "idle"   # idle, loading, ready, failed
        self.error = ""

    def refresh(self) -> None:
        if self.status == "loading":
            return
        self.status = "loading"
        self.error = ""
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        try:
            packs = self._fetch()
        except Exception as e:   # noqa: BLE001
            self.error = str(e) if isinstance(e, CardDataError) else "Couldn't download the cards."
            self.status = "ready" if self.packs else "failed"
            return
        save_cache(packs)
        self.packs = packs
        self.status = "ready"

    def by_id(self) -> dict[int, dict]:
        return {p["id"]: p for p in self.packs or []}


_library: CardLibrary | None = None


def library() -> CardLibrary:
    """The shared card library for this run of the game."""
    global _library
    if _library is None:
        _library = CardLibrary()
    return _library
