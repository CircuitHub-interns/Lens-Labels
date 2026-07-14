"""Lens assignment tracker — Circuit Hub LE series.

Owns lens_registry.json, the shared record of every label printed by
lens_label.py and every labeled lens installed afterwards.

Each LE code is one physical lens. An assignment records which camera
MODEL it was installed on (cameras have no serial numbers, so the model
number like 33-306 is the identifier — many lenses can share one model)
plus where that camera lives.

Registry entry shape (one per LE code):
  {
    "printed_at":   "2026-07-06T14:02:11",   # first print
    "reprints":     0,                        # times re-printed after that
    "model":        "33-306" | null,          # camera model the lens went on
    "location":     "SM3 QR" | null,          # where that camera is
    "assigned_at":  "2026-07-06T15:40:00" | null,
    "assigned_by":  "Jonathan" | null,
    "note":         "spare from bin 4" | null
  }

Usage:
  python lens_tracker.py list
  python lens_tracker.py assign LE001 33-306 --by Jonathan --location "SM1 QR"
  python lens_tracker.py assign LE002 33-306 --location "SM3 QR" --note "replacement"
  python lens_tracker.py relocate LE031-LE036 --to "Idle"   # mass location fix
  python lens_tracker.py unassign LE001                # undo a mistake
  python lens_tracker.py report                        # copy-paste message for supervisor
  python lens_tracker.py report --md report.md         # also write a markdown table
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

REGISTRY_PATH = Path(__file__).parent / "lens_registry.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_registry() -> dict:
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {}


def save_registry(reg: dict) -> None:
    REGISTRY_PATH.write_text(
        json.dumps(reg, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def register_print(code: str) -> None:
    """Called by lens_label.py each time a label is generated."""
    reg = load_registry()
    if code in reg:
        reg[code]["reprints"] = reg[code].get("reprints", 0) + 1
    else:
        reg[code] = {
            "printed_at": _now(),
            "reprints": 0,
            "model": None,
            "location": None,
            "assigned_at": None,
            "assigned_by": None,
            "note": None,
        }
    save_registry(reg)


# ---------------------------------------------------------------- commands
def cmd_assign(args: argparse.Namespace) -> int:
    reg = load_registry()
    code = args.code.upper()
    if code not in reg:
        print(
            f"error: {code} has never been printed (no registry entry). "
            f"Print it first with lens_label.py.",
            file=sys.stderr,
        )
        return 1
    entry = reg[code]
    if entry["model"]:
        print(
            f"error: {code} is already installed on a {entry['model']}"
            + (f" at {entry['location']}" if entry["location"] else "")
            + f" (assigned {entry['assigned_at']}). "
            f"Run 'unassign {code}' first if it was moved.",
            file=sys.stderr,
        )
        return 1
    entry.update(
        model=args.model,
        location=args.location,
        assigned_at=_now(),
        assigned_by=args.by,
        note=args.note,
    )
    save_registry(reg)
    line = f"{code} -> {args.model}"
    if args.location:
        line += f" @ {args.location}"
    if args.by:
        line += f" (by {args.by})"
    print(line)
    return 0


def _expand_codes(tokens: list[str]) -> list[str]:
    """Expand codes and ranges: ['LE005', 'LE031-LE036'] -> LE005, LE031..LE036."""
    codes = []
    for tok in tokens:
        tok = tok.upper()
        m = re.match(r"^LE(\d+)-LE(\d+)$", tok)
        if m:
            lo, hi = m.group(1), m.group(2)
            if int(lo) > int(hi):
                raise ValueError(f"range {tok} runs backwards")
            width = len(lo)
            codes += [f"LE{n:0{width}d}" for n in range(int(lo), int(hi) + 1)]
        else:
            codes.append(tok)
    return codes


def cmd_relocate(args: argparse.Namespace) -> int:
    reg = load_registry()
    try:
        codes = _expand_codes(args.codes)
    except ValueError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    missing = [c for c in codes if c not in reg]
    unassigned = [c for c in codes if c in reg and not reg[c]["model"]]
    if missing or unassigned:
        if missing:
            print(f"error: not in registry: {', '.join(missing)}", file=sys.stderr)
        if unassigned:
            print(
                f"error: not assigned yet (use 'assign' instead): "
                f"{', '.join(unassigned)}",
                file=sys.stderr,
            )
        print("no changes made.", file=sys.stderr)
        return 1

    for code in codes:
        old = reg[code].get("location") or "-"
        reg[code]["location"] = args.to
        print(f"{code}: {old} -> {args.to}")
    save_registry(reg)
    print(f"\n{len(codes)} lens(es) relocated.")
    return 0


def cmd_unassign(args: argparse.Namespace) -> int:
    reg = load_registry()
    code = args.code.upper()
    if code not in reg or not reg[code]["model"]:
        print(f"error: {code} is not assigned to anything.", file=sys.stderr)
        return 1
    was = reg[code]["model"]
    reg[code].update(
        model=None, location=None, assigned_at=None, assigned_by=None, note=None
    )
    save_registry(reg)
    print(f"{code} unassigned (was on a {was})")
    return 0


def _rows(reg: dict) -> list[tuple[str, str, str, str, str, str]]:
    rows = []
    for code in sorted(reg):
        e = reg[code]
        rows.append((
            code,
            e["model"] or "-",
            e.get("location") or "",
            (e["assigned_at"] or "")[:16].replace("T", " "),
            e["assigned_by"] or "",
            e["note"] or "",
        ))
    return rows


def cmd_list(args: argparse.Namespace) -> int:
    reg = load_registry()
    if not reg:
        print("Registry is empty — print some labels first.")
        return 0
    header = ("LENS", "MODEL", "LOCATION", "ASSIGNED", "BY", "NOTE")
    rows = _rows(reg)
    widths = [max(len(r[i]) for r in [header, *rows]) for i in range(len(header))]
    for r in [header, *rows]:
        print("  ".join(cell.ljust(w) for cell, w in zip(r, widths)).rstrip())
    assigned = sum(1 for e in reg.values() if e["model"])
    print(f"\n{assigned} of {len(reg)} lenses installed.")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    reg = load_registry()
    if not reg:
        print("Registry is empty — nothing to report.")
        return 0

    assigned = {c: e for c, e in reg.items() if e["model"]}
    pending = sorted(c for c, e in reg.items() if not e["model"])
    today = datetime.now().strftime("%b %d, %Y")

    lines = [f"Lens installation update - {today}", ""]
    lines.append(f"Installed ({len(assigned)} of {len(reg)} printed lenses):")
    for code in sorted(assigned):
        e = assigned[code]
        detail = f"  {code} -> {e['model']}"
        if e.get("location"):
            detail += f" @ {e['location']}"
        detail += f" ({e['assigned_at'][:10]}"
        if e["assigned_by"]:
            detail += f", {e['assigned_by']}"
        detail += ")"
        if e["note"]:
            detail += f" - {e['note']}"
        lines.append(detail)
    if pending:
        lines.append("")
        lines.append(f"Printed, awaiting installation ({len(pending)}): "
                     + ", ".join(pending))
    message = "\n".join(lines)
    print(message)

    if args.md:
        md = [f"# Lens installation update - {today}", ""]
        md.append("| Lens | Model | Location | Assigned | By | Note |")
        md.append("|---|---|---|---|---|---|")
        for r in _rows(reg):
            md.append("| " + " | ".join(cell or " " for cell in r) + " |")
        md.append("")
        md.append(f"**{len(assigned)} of {len(reg)}** lenses installed.")
        Path(args.md).write_text("\n".join(md) + "\n", encoding="utf-8")
        print(f"\nwrote {args.md}")
    return 0


# --------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Track which labeled lens is installed on which camera model."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("assign", help="record a lens installed on a camera model")
    p.add_argument("code", help="lens code, e.g. LE001")
    p.add_argument("model", help="camera model number, e.g. 33-306")
    p.add_argument("--location", help="where the camera is, e.g. 'SM3 QR'")
    p.add_argument("--by", help="who installed it")
    p.add_argument("--note", help="anything else worth recording")
    p.set_defaults(func=cmd_assign)

    p = sub.add_parser("relocate", help="change location on already-assigned lenses")
    p.add_argument("codes", nargs="+", metavar="CODE",
                   help="codes and/or ranges, e.g. LE005 LE031-LE036")
    p.add_argument("--to", required=True, metavar="LOCATION",
                   help="new location, e.g. 'Idle'")
    p.set_defaults(func=cmd_relocate)

    p = sub.add_parser("unassign", help="undo an assignment")
    p.add_argument("code")
    p.set_defaults(func=cmd_unassign)

    p = sub.add_parser("list", help="status table of every printed lens")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("report", help="print a supervisor-ready summary")
    p.add_argument("--md", metavar="FILE", help="also write a markdown table")
    p.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
