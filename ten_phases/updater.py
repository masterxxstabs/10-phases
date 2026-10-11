"""Self-updating from GitHub Releases.

On start the game asks GitHub for the latest release. If it's newer than this
copy, the new 10Phases.exe is downloaded next to the running one in the
background and checked against the SHA-256 that GitHub reports. Then:

  * "Restart now": the running exe is renamed to 10Phases.exe.old (Windows
    allows renaming a running program, just not overwriting it), the new file
    takes its place, the new version is launched and this one quits.
  * "Later": the same swap happens when you quit, so the next launch is new.

Leftover .old/.part/.new files are cleaned up on the next start. Self-install
only happens for the packaged Windows exe; running from source just says that a
new version is out and links to it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import __version__

REPO = "masterxxstabs/10-phases"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
ASSET_NAME = "10Phases.exe"
USER_AGENT = f"10Phases-updater/{__version__}"
MAX_SIZE = 200 * 1024 * 1024


def parse_version(text: str) -> tuple[int, ...]:
    """'v1.2.3' -> (1, 2, 3). Anything unparseable sorts lowest."""
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums[:4]) if nums else (0,)


def is_newer(remote: str, local: str = __version__) -> bool:
    r, l_ = parse_version(remote), parse_version(local)
    width = max(len(r), len(l_))
    return r + (0,) * (width - len(r)) > l_ + (0,) * (width - len(l_))


def whats_new(body: str, limit: int = 4) -> list[str]:
    """Bullet points from the release notes' "What's new" section."""
    lines, inside = [], False
    for raw in (body or "").splitlines():
        line = raw.strip()
        if line.startswith("#"):
            if inside:
                break
            inside = "new" in line.lower()
            continue
        if inside and line.startswith(("-", "*")):
            text = re.sub(r"[*_`]", "", line.lstrip("-* ")).strip()
            if text:
                lines.append(text)
    return lines[:limit]


@dataclass
class UpdateInfo:
    version: str
    tag: str
    notes: list[str]
    page_url: str
    asset_url: str | None
    size: int
    sha256: str | None


def _get(url: str, timeout: float):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout)


def check(timeout: float = 8.0, local: str = __version__) -> UpdateInfo | None:
    """Return info about a newer release, or None if this copy is up to date."""
    with _get(LATEST_URL, timeout) as resp:
        data = json.loads(resp.read(2_000_000).decode("utf-8"))
    tag = str(data.get("tag_name", ""))
    if not tag or not is_newer(tag, local) or data.get("draft") or data.get("prerelease"):
        return None
    asset = next((a for a in data.get("assets", []) if a.get("name") == ASSET_NAME), None)
    digest = (asset or {}).get("digest") or ""
    return UpdateInfo(
        version=tag.lstrip("vV"), tag=tag, notes=whats_new(data.get("body", "")),
        page_url=data.get("html_url") or RELEASES_PAGE,
        asset_url=(asset or {}).get("browser_download_url"),
        size=int((asset or {}).get("size") or 0),
        sha256=digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else None,
    )


def download(info: UpdateInfo, dest: Path, progress=None, timeout: float = 30.0) -> Path:
    """Download the new exe to `dest`, verifying size and SHA-256. Raises on any problem."""
    if not info.asset_url or not info.asset_url.startswith("https://github.com/"):
        raise RuntimeError("This release has no Windows download.")
    if not 0 < info.size <= MAX_SIZE:
        raise RuntimeError("The download size looks wrong.")
    part = dest.with_name(dest.name + ".part")
    sha = hashlib.sha256()
    got = 0
    try:
        with _get(info.asset_url, timeout) as resp, open(part, "wb") as out:
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                got += len(chunk)
                if got > info.size:
                    raise RuntimeError("The download is bigger than expected.")
                sha.update(chunk)
                out.write(chunk)
                if progress:
                    progress(got / info.size)
        if got != info.size:
            raise RuntimeError("The download was cut short.")
        if info.sha256 and sha.hexdigest() != info.sha256:
            raise RuntimeError("The download didn't match its checksum.")
        with open(part, "rb") as f:
            if f.read(2) != b"MZ":
                raise RuntimeError("The download isn't a Windows program.")
        os.replace(part, dest)
        return dest
    except BaseException:
        try:
            part.unlink()
        except OSError:
            pass
        raise


# --------------------------------------------------------------------------- installing


def running_exe() -> Path | None:
    """The packaged exe we're running from, or None when running from source."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return None


def can_self_update(exe: Path | None = None) -> bool:
    exe = exe or running_exe()
    if exe is None or os.name != "nt":
        return False
    return os.access(exe.parent, os.W_OK)


def staged_path(exe: Path) -> Path:
    return exe.with_name(exe.name + ".new")


def cleanup(exe: Path | None = None) -> None:
    """Delete files left over from a previous update."""
    exe = exe or running_exe()
    if exe is None:
        return
    for suffix in (".old", ".new", ".new.part"):
        try:
            exe.with_name(exe.name + suffix).unlink()
        except OSError:
            pass


def install(new_file: Path, exe: Path) -> None:
    """Swap the new exe into place. Works while `exe` is running (it gets renamed, not overwritten)."""
    old = exe.with_name(exe.name + ".old")
    try:
        old.unlink()
    except OSError:
        pass
    os.replace(exe, old)
    try:
        os.replace(new_file, exe)
    except OSError:
        os.replace(old, exe)  # put the working version back
        raise


def relaunch(exe: Path, args: list[str] | None = None) -> subprocess.Popen:
    """Start a fresh copy of the (new) exe, fully independent of this process."""
    env = dict(os.environ)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"  # the child must unpack itself, not reuse our files
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen([str(exe), *(args or [])], env=env, cwd=str(exe.parent), close_fds=True,
                            creationflags=flags)


# --------------------------------------------------------------------------- background updater


class Updater:
    """Runs the check and download on a background thread; the menu reads `state`.

    States: idle, checking, current, available (can't self-install), downloading,
    ready (downloaded, waiting for a restart), installed, failed.
    """

    def __init__(self, exe: Path | None = None, check_fn=check, download_fn=download):
        self.exe = exe if exe is not None else running_exe()
        self.check_fn = check_fn
        self.download_fn = download_fn
        self.state = "idle"
        self.info: UpdateInfo | None = None
        self.progress = 0.0
        self.error: str | None = None
        self.self_update = can_self_update(self.exe) if exe is None else os.access(self.exe.parent, os.W_OK)
        self._lock = threading.Lock()

    def start(self) -> None:
        if self.state != "idle":
            return
        cleanup(self.exe)
        self.state = "checking"
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        try:
            info = self.check_fn()
        except (urllib.error.URLError, OSError, ValueError, KeyError, TimeoutError) as e:
            self._fail("Couldn't check for updates", e)
            return
        if info is None:
            self.state = "current"
            return
        self.info = info
        if not (self.self_update and self.exe and info.asset_url):
            self.state = "available"
            return
        self.state = "downloading"
        try:
            self.download_fn(info, staged_path(self.exe), self._on_progress)
        except Exception as e:  # noqa: BLE001 - any failure just means "update later"
            self._fail("The update didn't download", e)
            return
        self.state = "ready"

    def _on_progress(self, fraction: float) -> None:
        self.progress = max(0.0, min(1.0, fraction))

    def _fail(self, what: str, err: Exception) -> None:
        self.error = what
        self.state = "failed"
        print(f"[updater] {what}: {err}", file=sys.stderr)

    def apply(self, restart: bool) -> bool:
        """Install a downloaded update. With restart=True, launch it (the caller then quits)."""
        with self._lock:
            if self.state != "ready" or self.exe is None:
                return False
            try:
                install(staged_path(self.exe), self.exe)
            except OSError as e:
                self._fail("The update couldn't be installed", e)
                return False
            self.state = "installed"
        if restart:
            try:
                relaunch(self.exe)
            except OSError as e:
                self._fail("Updated, but couldn't restart. Start the game again", e)
                return False
        return True
