import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # lets tests import helpers like exact_planner


import pytest  # noqa: E402


@pytest.fixture(scope="session")
def app(tmp_path_factory):
    """One window for the whole test run: pygame can't recreate a scaled window headless, and
    cached fonts belong to the running session."""
    import os
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    import ten_phases.settings as settings_module
    from ten_phases.ui.app import App

    original = settings_module.SETTINGS_PATH
    settings_module.SETTINGS_PATH = tmp_path_factory.mktemp("cfg") / "settings.json"
    yield App(check_updates=False)
    settings_module.SETTINGS_PATH = original
