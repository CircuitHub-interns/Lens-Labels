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
    "note":         "spare from bin 4" | null,
    "attachment":   false | true | "331456"   # false = none, true = present
                                               # but unidentified, string = its ID
  }

KNOWN_LOCATIONS / KNOWN_MODELS below are just a typo-check reference list —
whatever you actually type into --location/--model at assign time is what
gets recorded regardless of whether it matches the list, since that's the
ground truth of what's physically installed.

Usage:
  python lens_tracker.py list
  python lens_tracker.py locations                      # known locations + how many lenses are there
  python lens_tracker.py cameras                        # known camera models + how many lenses are on each
  python lens_tracker.py assign LE001 33-306 --by Jonathan --location "SM1 QR"
  python lens_tracker.py assign LE002 33-306 --location "SM3 QR" --note "replacement"
  python lens_tracker.py assign LE003 33-306 --location "SM3 QR" --attachment
  python lens_tracker.py assign LE004 33-306 --location "SM3 QR" --attachment 331456
  python lens_tracker.py relocate LE031-LE036 --to "Idle"   # mass location fix
  python lens_tracker.py credit LE001-LE005 --by "Jonathan" # fix who, forgot at assign time
  python lens_tracker.py unassign LE001                # undo a mistake
  python lens_tracker.py unassign-all --yes             # clear every assignment for re-verification
  python lens_tracker.py report                        # copy-paste message + refreshes report.md
  python lens_tracker.py report --md other.md          # write the markdown table elsewhere instead

Two people editing lens_registry.json in parallel (see merge_registry.py /
setup_merge_driver.py) merge cleanly as long as they touch different LE
codes; if you both reassign the *same* code differently, the merge fails
loudly and flags that code instead of silently corrupting the file.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

REGISTRY_PATH = Path(__file__).parent / "lens_registry.json"

# Reference lists only (see docstring above) — not enforced, just typo-checked.
KNOWN_LOCATIONS = {
    "Idle",
    "SM1 EE",
    "SM3 EE",
    "SM3 Inside 1",
    "SM3 Inside 2",
    "SM3 Overview",
    "SM3 QR Code",
    "SM3 Declamper Overhead",
    "SM4 EE",
    "SM4 QR",
    "SM4 Declamper Overhead",
    "Tiles - Beyond SM4",
    "Tiles - Behind G1",
    "Tiles - Between G1 and G2/G3 Corridor",
    "Tiles - Leading to SM1",
    "Flipper Pusher Close Up",
    "JP TU",
    "Oven TU",
    "G1 Overview",
    "G2 Overview",
    "G2 Pallet",
    "G3 Nozzle",
    "G4 Nozzle",
    "G5 Nozzle",
    "G4 and G5 Overview",
}

KNOWN_MODELS = {
    "33-300", "33-301", "33-303", "33-304", "33-305", "33-306",
    "58-001",
    "59-870", "59-871", "59-872", "59-873",
    "67-709",
    "86-569", "86-570", "86-571", "86-573", "86-900",
    "89-410",
}


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
            "attachment": False,
        }
    save_registry(reg)


def _is_conflicted(entry) -> bool:
    return isinstance(entry, dict) and entry.get("MERGE_CONFLICT")


def _fmt_attachment(v) -> str:
    if not v:
        return "-"
    if v is True:
        return "yes (ID unknown)"
    return str(v)


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
    if _is_conflicted(entry):
        print(
            f"error: {code} has an unresolved merge conflict in "
            f"lens_registry.json — fix that entry by hand before assigning.",
            file=sys.stderr,
        )
        return 1
    if entry["model"]:
        print(
            f"error: {code} is already installed on a {entry['model']}"
            + (f" at {entry['location']}" if entry["location"] else "")
            + f" (assigned {entry['assigned_at']}). "
            f"Run 'unassign {code}' first if it was moved.",
            file=sys.stderr,
        )
        return 1
    if args.location and args.location not in KNOWN_LOCATIONS:
        print(
            f"note: '{args.location}' isn't in the known-locations list "
            f"(recorded as typed — that's still the source of truth).",
            file=sys.stderr,
        )
    if args.model not in KNOWN_MODELS:
        print(
            f"note: '{args.model}' isn't in the known-models list "
            f"(recorded as typed — that's still the source of truth).",
            file=sys.stderr,
        )
    entry.update(
        model=args.model,
        location=args.location,
        assigned_at=_now(),
        assigned_by=args.by,
        note=args.note,
        attachment=args.attachment,
    )
    save_registry(reg)
    line = f"{code} -> {args.model}"
    if args.location:
        line += f" @ {args.location}"
    if args.by:
        line += f" (by {args.by})"
    if args.attachment:
        line += f" [attachment: {_fmt_attachment(args.attachment)}]"
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


def _validate_assigned_codes(
    reg: dict, codes: list[str]
) -> tuple[list[str], list[str], list[str]]:
    """Split codes into (missing, conflicted, unassigned) — empty of all
    three means every code is a valid, already-assigned entry."""
    missing = [c for c in codes if c not in reg]
    conflicted = [c for c in codes if c in reg and _is_conflicted(reg[c])]
    unassigned = [
        c for c in codes
        if c in reg and not _is_conflicted(reg[c]) and not reg[c]["model"]
    ]
    return missing, conflicted, unassigned


def _report_assigned_code_errors(
    missing: list[str], conflicted: list[str], unassigned: list[str]
) -> None:
    if missing:
        print(f"error: not in registry: {', '.join(missing)}", file=sys.stderr)
    if conflicted:
        print(
            f"error: unresolved merge conflicts, fix by hand first: "
            f"{', '.join(conflicted)}",
            file=sys.stderr,
        )
    if unassigned:
        print(
            f"error: not assigned yet (use 'assign' instead): "
            f"{', '.join(unassigned)}",
            file=sys.stderr,
        )
    print("no changes made.", file=sys.stderr)


def cmd_relocate(args: argparse.Namespace) -> int:
    reg = load_registry()
    try:
        codes = _expand_codes(args.codes)
    except ValueError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    missing, conflicted, unassigned = _validate_assigned_codes(reg, codes)
    if missing or conflicted or unassigned:
        _report_assigned_code_errors(missing, conflicted, unassigned)
        return 1

    for code in codes:
        old = reg[code].get("location") or "-"
        reg[code]["location"] = args.to
        print(f"{code}: {old} -> {args.to}")
    save_registry(reg)
    print(f"\n{len(codes)} lens(es) relocated.")
    return 0


def cmd_credit(args: argparse.Namespace) -> int:
    """Fix who/note on already-assigned lenses without touching model/location."""
    if args.by is None and args.note is None:
        print("error: pass --by and/or --note — nothing to update.", file=sys.stderr)
        return 1

    reg = load_registry()
    try:
        codes = _expand_codes(args.codes)
    except ValueError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    missing, conflicted, unassigned = _validate_assigned_codes(reg, codes)
    if missing or conflicted or unassigned:
        _report_assigned_code_errors(missing, conflicted, unassigned)
        return 1

    for code in codes:
        changes = []
        if args.by is not None:
            old_by = reg[code].get("assigned_by") or "-"
            reg[code]["assigned_by"] = args.by
            changes.append(f"by: {old_by} -> {args.by}")
        if args.note is not None:
            old_note = reg[code].get("note") or "-"
            reg[code]["note"] = args.note
            changes.append(f"note: {old_note!r} -> {args.note!r}")
        print(f"{code}: " + ", ".join(changes))
    save_registry(reg)
    print(f"\n{len(codes)} lens(es) updated.")
    return 0


def cmd_unassign(args: argparse.Namespace) -> int:
    reg = load_registry()
    code = args.code.upper()
    if code not in reg or _is_conflicted(reg[code]) or not reg[code]["model"]:
        print(f"error: {code} is not assigned to anything.", file=sys.stderr)
        return 1
    was = reg[code]["model"]
    reg[code].update(
        model=None, location=None, assigned_at=None, assigned_by=None, note=None,
        attachment=False,
    )
    save_registry(reg)
    print(f"{code} unassigned (was on a {was})")
    return 0


def cmd_unassign_all(args: argparse.Namespace) -> int:
    reg = load_registry()
    if not reg:
        print("Registry is empty — nothing to unassign.")
        return 0

    assigned = [
        c for c in sorted(reg) if not _is_conflicted(reg[c]) and reg[c]["model"]
    ]
    if not assigned:
        print("No lenses are currently assigned.")
        return 0

    if not args.yes:
        print(f"This will unassign {len(assigned)} of {len(reg)} lens(es):")
        print(", ".join(assigned))
        print("Registry entries (printed_at/reprints) are kept, only assignment "
              "fields are cleared. Re-run with --yes to confirm.")
        return 1

    for code in assigned:
        was = reg[code]["model"]
        reg[code].update(
            model=None, location=None, assigned_at=None, assigned_by=None, note=None,
            attachment=False,
        )
        print(f"{code} unassigned (was on a {was})")
    save_registry(reg)
    print(f"\n{len(assigned)} lens(es) unassigned. {len(reg)} registry entries kept.")
    return 0


def _warn_conflicts(reg: dict) -> dict:
    """Print a warning for any unresolved merge-conflict entries and drop
    them from the dict returned, so list/report can't crash on them."""
    conflicts = sorted(c for c, e in reg.items() if _is_conflicted(e))
    if conflicts:
        print(
            f"warning: unresolved merge conflicts in lens_registry.json for "
            f"{', '.join(conflicts)} — resolve those entries by hand before "
            f"trusting this output.\n",
            file=sys.stderr,
        )
    return {c: e for c, e in reg.items() if c not in conflicts}


def _rows(reg: dict) -> list[tuple[str, str, str, str, str, str, str]]:
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
            _fmt_attachment(e.get("attachment")),
        ))
    return rows


def cmd_list(args: argparse.Namespace) -> int:
    reg = _warn_conflicts(load_registry())
    if not reg:
        print("Registry is empty — print some labels first.")
        return 0
    header = ("LENS", "MODEL", "LOCATION", "ASSIGNED", "BY", "NOTE", "ATTACHMENT")
    rows = _rows(reg)
    widths = [max(len(r[i]) for r in [header, *rows]) for i in range(len(header))]
    for r in [header, *rows]:
        print("  ".join(cell.ljust(w) for cell, w in zip(r, widths)).rstrip())
    assigned = sum(1 for e in reg.values() if e["model"])
    print(f"\n{assigned} of {len(reg)} lenses installed.")
    return 0


def _reference_rows(known: set[str], counts: dict[str, int]) -> list[tuple[str, str, str]]:
    rows = []
    for item in sorted(known | set(counts)):
        tag = "" if item in known else "not in reference list"
        rows.append((item, str(counts.get(item, 0)), tag))
    return rows


def _print_reference_table(header: tuple[str, str, str], rows: list[tuple[str, str, str]]) -> None:
    if not rows:
        print("(nothing to show)")
        return
    widths = [max(len(r[i]) for r in [header, *rows]) for i in range(len(header))]
    for r in [header, *rows]:
        print("  ".join(cell.ljust(w) for cell, w in zip(r, widths)).rstrip())


def cmd_locations(args: argparse.Namespace) -> int:
    reg = _warn_conflicts(load_registry())
    counts: dict[str, int] = {}
    for e in reg.values():
        loc = e.get("location")
        if loc:
            counts[loc] = counts.get(loc, 0) + 1
    rows = _reference_rows(KNOWN_LOCATIONS, counts)
    _print_reference_table(("LOCATION", "IN USE", ""), rows)
    print(f"\n{len(KNOWN_LOCATIONS)} known location(s).")
    return 0


def cmd_cameras(args: argparse.Namespace) -> int:
    reg = _warn_conflicts(load_registry())
    counts: dict[str, int] = {}
    for e in reg.values():
        model = e.get("model")
        if model:
            counts[model] = counts.get(model, 0) + 1
    rows = _reference_rows(KNOWN_MODELS, counts)
    _print_reference_table(("MODEL", "IN USE", ""), rows)
    print(f"\n{len(KNOWN_MODELS)} known camera model(s).")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    reg = _warn_conflicts(load_registry())
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
        if e.get("attachment"):
            detail += f" [attachment: {_fmt_attachment(e['attachment'])}]"
        lines.append(detail)
    if pending:
        lines.append("")
        lines.append(f"Printed, awaiting installation ({len(pending)}): "
                     + ", ".join(pending))
    message = "\n".join(lines)
    print(message)

    md = [f"# Lens installation update - {today}", ""]
    md.append("| Lens | Model | Location | Assigned | By | Note | Attachment |")
    md.append("|---|---|---|---|---|---|---|")
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
    p.add_argument(
        "--attachment", nargs="?", const=True, default=False, metavar="ID",
        help="omit entirely for no attachment; bare flag if one is present but "
             "its ID is unknown; or give the ID, e.g. --attachment 331456",
    )
    p.set_defaults(func=cmd_assign)

    p = sub.add_parser("relocate", help="change location on already-assigned lenses")
    p.add_argument("codes", nargs="+", metavar="CODE",
                   help="codes and/or ranges, e.g. LE005 LE031-LE036")
    p.add_argument("--to", required=True, metavar="LOCATION",
                   help="new location, e.g. 'Idle'")
    p.set_defaults(func=cmd_relocate)

    p = sub.add_parser(
        "credit",
        help="fix who assigned (and/or the note on) already-assigned lenses, "
             "without touching model/location",
    )
    p.add_argument("codes", nargs="+", metavar="CODE",
                   help="codes and/or ranges, e.g. LE001-LE005")
    p.add_argument("--by", help="who actually assigned/installed these")
    p.add_argument("--note", help="anything else worth recording")
    p.set_defaults(func=cmd_credit)

    p = sub.add_parser("unassign", help="undo an assignment")
    p.add_argument("code")
    p.set_defaults(func=cmd_unassign)

    p = sub.add_parser(
        "unassign-all",
        help="clear every assignment (keep registry entries) for re-verification",
    )
    p.add_argument("--yes", action="store_true", help="confirm the bulk unassign")
    p.set_defaults(func=cmd_unassign_all)

    p = sub.add_parser("list", help="status table of every printed lens")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser(
        "locations", help="known locations, and how many lenses are at each"
    )
    p.set_defaults(func=cmd_locations)

    p = sub.add_parser(
        "cameras", help="known camera models, and how many lenses are on each"
    )
    p.set_defaults(func=cmd_cameras)

    p = sub.add_parser("report", help="print a supervisor-ready summary")
    p.add_argument(
        "--md", metavar="FILE", default="report.md",
        help="markdown file to (re)write every run (default: report.md)",
    )
    p.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
