"""Check that self-updating works with the real packaged exe (run on Windows CI after building).

1. Start dist/10Phases.exe from a temp folder and keep it running.
2. While it runs, swap a "new" copy into place the way the updater does.
3. The running copy must still finish cleanly, the swapped-in copy must start,
   and the leftover .old file must be cleaned up.
4. --relaunch-test: the exe restarts itself the way "Restart now" does and quits;
   the fresh copy must run to the end on its own.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ten_phases import updater  # noqa: E402


def main() -> None:
    built = ROOT / "dist" / ("10Phases.exe" if os.name == "nt" else "10Phases")
    env = {**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}
    with tempfile.TemporaryDirectory() as tmp:
        exe = Path(tmp) / built.name
        shutil.copy2(built, exe)
        new = updater.staged_path(exe)
        shutil.copy2(built, new)

        running = subprocess.Popen([str(exe), "--smoke-test", "--smoke-frames", "900"], env=env)
        time.sleep(5)
        assert running.poll() is None, "the game should still be running"
        updater.install(new, exe)
        assert exe.exists() and exe.with_name(exe.name + ".old").exists() and not new.exists()
        print("swapped the exe while it was running")
        assert running.wait(120) == 0, "the running copy should still exit cleanly"

        assert subprocess.run([str(exe), "--smoke-test"], env=env, timeout=120).returncode == 0
        print("the swapped-in exe starts")
        updater.cleanup(exe)
        assert not exe.with_name(exe.name + ".old").exists(), "leftover .old should be removed"

        marker = Path(tmp) / "relaunched.txt"
        parent = subprocess.run([str(exe), "--relaunch-test"], env={**env, "TEN_PHASES_SMOKE_MARKER": str(marker)},
                                timeout=60)
        assert parent.returncode == 0
        for _ in range(120):
            if marker.exists():
                break
            time.sleep(1)
        assert marker.read_text() == "ok", "the restarted copy should run on its own"
        print("restart after update works")
        time.sleep(2)  # let the child finish before the temp folder is removed


if __name__ == "__main__":
    main()
