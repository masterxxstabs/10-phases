import os
import time
from pathlib import Path

import pytest

from ten_phases import updater
from ten_phases.updater import UpdateInfo, Updater, is_newer, parse_version, whats_new


def test_version_compare():
    assert parse_version("v1.2.3") == (1, 2, 3)
    assert is_newer("v1.0.1", "1.0.0") and is_newer("2.0", "1.9.9") and is_newer("1.10.0", "1.9.0")
    assert not is_newer("v1.0.0", "1.0.0") and not is_newer("1.0", "1.0.0") and not is_newer("junk", "1.0.0")


def test_whats_new_reads_only_that_section():
    body = "## What's new\n\n- **Faster** AI\n- Bug fixes\n\n## Download\n- not this"
    assert whats_new(body) == ["Faster AI", "Bug fixes"]


def test_install_swaps_and_keeps_old_until_cleanup(tmp_path):
    exe = tmp_path / "10Phases.exe"
    exe.write_bytes(b"MZ old")
    new = updater.staged_path(exe)
    new.write_bytes(b"MZ new")
    updater.install(new, exe)
    assert exe.read_bytes() == b"MZ new" and not new.exists()
    assert exe.with_name("10Phases.exe.old").read_bytes() == b"MZ old"
    updater.cleanup(exe)
    assert not exe.with_name("10Phases.exe.old").exists()


def test_install_restores_old_exe_if_new_file_is_missing(tmp_path):
    exe = tmp_path / "10Phases.exe"
    exe.write_bytes(b"MZ old")
    with pytest.raises(OSError):
        updater.install(tmp_path / "missing.new", exe)
    assert exe.read_bytes() == b"MZ old"


INFO = UpdateInfo("9.9.9", "v9.9.9", ["New stuff"], "https://github.com/x/y/releases/latest",
                  "https://github.com/x/y/releases/download/v9.9.9/10Phases.exe", 6, None)


def wait_state(up, *states):
    for _ in range(300):
        if up.state in states:
            return up.state
        time.sleep(0.01)
    return up.state


def fake_download(info, dest, progress):
    progress(0.5)
    Path(dest).write_bytes(b"MZ new")
    progress(1.0)


def test_updater_downloads_then_installs_on_exit(tmp_path):
    exe = tmp_path / "10Phases.exe"
    exe.write_bytes(b"MZ old")
    up = Updater(exe=exe, check_fn=lambda: INFO, download_fn=fake_download)
    up.start()
    assert wait_state(up, "ready") == "ready" and up.progress == 1.0
    assert up.apply(restart=False)
    assert exe.read_bytes() == b"MZ new" and up.state == "installed"


def test_updater_states_for_no_update_errors_and_source_runs(tmp_path):
    exe = tmp_path / "10Phases.exe"
    exe.write_bytes(b"MZ")
    up = Updater(exe=exe, check_fn=lambda: None)
    up.start()
    assert wait_state(up, "current") == "current"

    def offline():
        raise OSError("no network")
    up = Updater(exe=exe, check_fn=offline)
    up.start()
    assert wait_state(up, "failed") == "failed" and up.error

    def bad_download(info, dest, progress):
        raise RuntimeError("checksum")
    up = Updater(exe=exe, check_fn=lambda: INFO, download_fn=bad_download)
    up.start()
    assert wait_state(up, "failed") == "failed" and not up.apply(restart=False)
    assert exe.read_bytes() == b"MZ"

    src = Updater(check_fn=lambda: INFO)  # running from source: no exe to replace
    if updater.running_exe() is None:
        src.start()
        assert wait_state(src, "available") == "available"


def test_download_refuses_non_github_urls(tmp_path):
    info = UpdateInfo(**{**INFO.__dict__, "asset_url": "https://evil.example/10Phases.exe"})
    with pytest.raises(RuntimeError):
        updater.download(info, tmp_path / "x.new")
    assert not list(tmp_path.iterdir())


@pytest.mark.skipif(os.environ.get("TEN_PHASES_ONLINE_TESTS") != "1", reason="set TEN_PHASES_ONLINE_TESTS=1")
def test_real_github_release(tmp_path):
    info = updater.check(local="0.0.1")
    assert info and info.asset_url and info.sha256
    updater.download(info, tmp_path / "10Phases.exe.new")
    assert (tmp_path / "10Phases.exe.new").stat().st_size == info.size
