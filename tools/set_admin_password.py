"""Set the password for the in-game admin panel.

    python tools/set_admin_password.py            # makes up a new random password and prints it
    python tools/set_admin_password.py my-secret  # uses the one you give

Only a salted PBKDF2 hash is stored (in ten_phases/admin_key.py), so the password
can't be read back out of the source code or the exe. Commit the file and push to
ship it in the next release.
"""

from __future__ import annotations

import hashlib
import secrets
import sys
from pathlib import Path

ITERATIONS = 200_000
KEY_FILE = Path(__file__).resolve().parent.parent / "ten_phases" / "admin_key.py"
WORDS = ("ace", "blitz", "comet", "delta", "ember", "frost", "glide", "haze", "ivory", "jolt", "koi", "lunar",
         "mango", "nova", "onyx", "pixel", "quartz", "rally", "solar", "tango", "ultra", "vivid", "wave", "zest")


def main() -> None:
    password = sys.argv[1] if len(sys.argv) > 1 else \
        "-".join(secrets.choice(WORDS) for _ in range(3)) + "-" + str(secrets.randbelow(9000) + 1000)
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    KEY_FILE.write_text(
        '"""Admin panel password (a salted hash only). Change it with tools/set_admin_password.py."""\n\n'
        f'SALT = "{salt}"\nHASH = "{digest}"\nITERATIONS = {ITERATIONS}\n')
    print(f"Admin password set to: {password}")


if __name__ == "__main__":
    main()
