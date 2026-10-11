"""Print the GitHub Release text for a version, from CHANGELOG.md.

    python tools/release_notes.py 1.1.0 > notes.md
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DOWNLOAD = """## Download

**Get `10Phases.exe` below and double-click it.** No install or Python needed.
Already have the game? It updates itself the next time you open it.

Windows may show "Windows protected your PC" because the exe isn't code-signed:
click **More info** then **Run anyway**. The first time you host a multiplayer game,
allow it through the firewall on private networks so friends can connect.
"""


def notes_for(version: str, changelog: str) -> list[str]:
    lines, inside = [], False
    for line in changelog.splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = re.sub(r"^v", "", line[3:].strip()) == version
            continue
        if inside and line.strip():
            lines.append(line.rstrip())
    return lines


def main() -> None:
    version = sys.argv[1].lstrip("vV")
    notes = notes_for(version, (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    body = "## What's new\n\n" + ("\n".join(notes) if notes else "- Improvements and fixes") + "\n\n" + DOWNLOAD
    sys.stdout.write(body)


if __name__ == "__main__":
    main()
