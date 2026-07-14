"""Custom git merge driver for lens_registry.json.

Plain git merges this file line-by-line, which is fragile for JSON: two
people editing different LE codes usually merges fine by luck (each code is
its own block of lines), but there's no guarantee, and if you both touch the
*same* code differently git drops raw <<<<<<< conflict markers into the
file, which breaks json.loads() until someone edits it back to valid JSON.

This driver instead merges per LE code:
  - a code changed on only one side (relative to the common ancestor) ->
    that side wins, no conflict, regardless of how many other codes changed
  - a code changed identically on both sides -> no conflict
  - a code changed differently on both sides -> real conflict. The merge
    still produces valid JSON: that entry is replaced with a
    {"MERGE_CONFLICT": true, "base": ..., "ours": ..., "theirs": ...} block,
    and the driver exits non-zero so git still stops the merge and asks you
    to resolve it (lens_tracker.py also refuses to touch a conflicted code
    until it's fixed).

One-time setup (each teammate runs this once per clone — git merge drivers
are registered in local .git/config, not shared through the repo):
  python setup_merge_driver.py

To resolve a conflict: open lens_registry.json, find the entry with
"MERGE_CONFLICT": true, decide which of "ours"/"theirs" (or a hand-edited
mix) is correct, replace the whole block with that entry, save, then
`git add lens_registry.json` and continue the merge/rebase.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _load(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    text = p.read_text(encoding="utf-8").strip()
    return json.loads(text) if text else {}


def merge(base: dict, ours: dict, theirs: dict) -> tuple[dict, list[str]]:
    result: dict = {}
    conflicts: list[str] = []
    for code in sorted(set(base) | set(ours) | set(theirs)):
        b, o, t = base.get(code), ours.get(code), theirs.get(code)
        if o == t:
            if o is not None:
                result[code] = o
        elif o == b:
            if t is not None:
                result[code] = t
        elif t == b:
            if o is not None:
                result[code] = o
        else:
            conflicts.append(code)
            result[code] = {"MERGE_CONFLICT": True, "base": b, "ours": o, "theirs": t}
    return result, conflicts


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: merge_registry.py <base> <ours> <theirs>", file=sys.stderr)
        return 2
    base_path, ours_path, theirs_path = argv

    merged, conflicts = merge(_load(base_path), _load(ours_path), _load(theirs_path))
    Path(ours_path).write_text(
        json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    if conflicts:
        print(
            f"lens_registry.json: {len(conflicts)} lens(es) were reassigned "
            f"differently on both sides:",
            file=sys.stderr,
        )
        for code in conflicts:
            print(f"  {code}", file=sys.stderr)
        print(
            "\nEach is left in the file as a MERGE_CONFLICT block "
            "(base/ours/theirs) instead of broken JSON. Pick the right one, "
            "replace the block with that entry, then `git add "
            "lens_registry.json` and continue the merge.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
