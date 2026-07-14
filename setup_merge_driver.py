"""One-time setup: registers merge_registry.py as the git merge driver for
lens_registry.json in *this* clone.

Run once, right after cloning (or after pulling this file for the first
time):
  python setup_merge_driver.py

Why every clone needs this: .gitattributes (tracked in the repo) names the
driver, but the driver's actual command is stored in local .git/config,
which git never syncs between clones. Everyone touching this repo needs to
run this script once.
"""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    driver_cmd = f'"{sys.executable}" merge_registry.py %O %A %B'
    subprocess.run(
        ["git", "config", "merge.lens-registry.name", "Lens registry per-code merge"],
        check=True,
    )
    subprocess.run(
        ["git", "config", "merge.lens-registry.driver", driver_cmd], check=True
    )
    print("Registered git merge driver 'lens-registry' for this clone.")
    print(f"driver command: {driver_cmd}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
