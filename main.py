"""One-shot lens labeling — print a label and log its installation together.

Usage:
  python main.py --print LE001
  python main.py --print LE001 --assign 33-306 --location "SM1 EE"
  python main.py --print LE001 --assign 33-306 --location "SM1 EE" --by Jonathan --note "replacement"

--print generates labels/<CODE>.svg + .pdf and logs the code to the registry.
--assign (optional) records the lens on a camera model in the same breath,
with --location / --by / --note carried through to lens_tracker.

For everything else (list, report, unassign) use lens_tracker.py directly.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lens_label import label_pdf, label_svg
from lens_tracker import cmd_assign, register_print


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print a lens label and optionally assign it in one command."
    )
    parser.add_argument("--print", dest="code", required=True, metavar="CODE",
                        help="lens code to print, e.g. LE001")
    parser.add_argument("--assign", dest="model", metavar="MODEL",
                        help="camera model the lens goes on, e.g. 33-306")
    parser.add_argument("--location", help="where the camera is, e.g. 'SM1 EE'")
    parser.add_argument("--by", help="who installed it")
    parser.add_argument("--note", help="anything else worth recording")
    parser.add_argument(
        "--attachment", nargs="?", const=True, default=False, metavar="ID",
        help="omit entirely for no attachment; bare flag if one is present but "
             "its ID is unknown; or give the ID, e.g. --attachment 331456",
    )
    parser.add_argument("-o", "--out", default="labels",
                        help="output directory (default: labels)")
    args = parser.parse_args(argv)

    if (args.location or args.by or args.note) and not args.model:
        parser.error("--location/--by/--note need --assign MODEL to attach to")

    code = args.code.upper()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    try:
        svg_path = out / f"{code}.svg"
        svg_path.write_text(label_svg(code), encoding="utf-8")
        print(f"wrote {svg_path}")
        pdf_path = out / f"{code}.pdf"
        label_pdf(code, pdf_path)
        print(f"wrote {pdf_path}")
    except ValueError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    register_print(code)

    if args.model:
        return cmd_assign(argparse.Namespace(
            code=code,
            model=args.model,
            location=args.location,
            by=args.by,
            note=args.note,
            attachment=args.attachment,
        ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
