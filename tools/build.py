"""Build a standalone app with PyInstaller. No Python needed to run the result.

    python tools/build.py

Windows: dist/10Phases.exe (one file). macOS/Linux: dist/10Phases (one file).
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "packaging" / "build"
sys.path.insert(0, str(ROOT))

from ten_phases import __version__  # noqa: E402

NAME = "10Phases"


def windows_version_file() -> Path:
    """Version info shown in the exe's Properties > Details tab."""
    nums = (__version__.split(".") + ["0", "0", "0"])[:4]
    tup = ", ".join(str(int(n)) for n in nums)
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({tup}), prodvers=({tup}), mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', '10 Phases'),
      StringStruct('FileDescription', '10 Phases card game'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', '{NAME}'),
      StringStruct('OriginalFilename', '{NAME}.exe'),
      StringStruct('ProductName', '10 Phases'),
      StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    path = BUILD / "version_info.txt"
    path.write_text(text)
    return path


def main() -> None:
    subprocess.run([sys.executable, str(ROOT / "tools" / "make_icon.py")], check=True)
    args = [
        sys.executable, "-m", "PyInstaller", str(ROOT / "main.py"),
        "--name", NAME,
        "--onefile",
        "--windowed",            # no console window
        "--noconfirm", "--clean",
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(BUILD / "pyinstaller"),
        "--specpath", str(BUILD),
        "--icon", str(BUILD / ("icon.ico" if os.name == "nt" else "icon.png")),
        # The bundled pixel font (and its license) travel inside the exe.
        "--add-data", f"{ROOT / 'ten_phases' / 'assets'}{os.pathsep}ten_phases/assets",
        # Not used by the game; keeps the exe smaller.
        "--exclude-module", "numpy", "--exclude-module", "tkinter", "--exclude-module", "PIL",
    ]
    if os.name == "nt":
        args += ["--version-file", str(windows_version_file())]
    subprocess.run(args, check=True, cwd=ROOT)
    exe = ROOT / "dist" / (NAME + (".exe" if os.name == "nt" else ""))
    print(f"\nBuilt {exe} ({exe.stat().st_size / 1e6:.1f} MB), version {__version__}")


if __name__ == "__main__":
    main()
