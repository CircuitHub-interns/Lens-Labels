"""Lens label generator — Circuit Hub LE series.

Produces print-ready 25 x 12.5 mm labels (SVG and/or PDF, one label per page):

  +--------------------------+
  | [12x12 DataMatrix] LE123 |
  +--------------------------+

Layout spec (mock-up 01, approved 2026-07-06):
  - Label stock ..... 25.0 x 12.5 mm, black on white
  - Data Matrix ..... 12x12 ECC 200, 0.75 mm module -> 9.0 x 9.0 mm symbol,
                      left-anchored at x=1.0 mm, vertically centered (y=1.75 mm)
  - Quiet zone ...... worst side 1.0 mm (left); spec minimum is 1 module = 0.75 mm
  - Human-readable .. remaining width (11.5 -> 24.0 mm), bold condensed,
                      stretched to fill the region exactly at any code length
  - Capacity ........ 12x12 holds LE1 through LE123456 (5 data codewords;
                      ASCII mode packs digit pairs into single codewords)

Usage:
  python lens_label.py LE123                 # -> labels/LE123.svg + labels/LE123.pdf
  python lens_label.py LE123 LE124 LE125     # one file pair per code
  python lens_label.py LE123 --svg           # SVG only
  python lens_label.py LE123 --pdf -o out    # PDF only, custom output dir

Every generated code is also logged to lens_registry.json; use lens_tracker.py
to assign lenses to cameras and build the supervisor report.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
import os

from ppf.datamatrix import DataMatrix

from lens_tracker import register_print

# ---------------------------------------------------------------- geometry (mm)
LABEL_W = 25.0
LABEL_H = 12.5

MODULE = 0.75          # DataMatrix module size
N = 12                 # 12x12 symbol
SYM = MODULE * N       # 9.0 mm symbol edge

DM_X = 1.0                     # left quiet zone
DM_Y = (LABEL_H - SYM) / 2     # 1.75 mm top/bottom

TXT_X0 = DM_X + SYM + 1.5      # text region: 11.5 mm ...
TXT_X1 = LABEL_W - 1.0         # ... to 24.0 mm
TXT_FONT_MM = 5.6              # nominal font size before horizontal fit

CODE_RE = re.compile(r"^LE\d{1,6}$")

MM_TO_PT = 72 / 25.4


def encode(code: str) -> list[list[int]]:
    """Return the 12x12 module grid (1 = dark) for a validated LE code."""
    if not CODE_RE.match(code):
        raise ValueError(
            f"{code!r} is not a valid LE code (expected LE + 1-6 digits, e.g. LE123)"
        )
    matrix = DataMatrix(code).matrix
    if len(matrix) != N or len(matrix[0]) != N:
        raise ValueError(
            f"{code!r} encoded to {len(matrix)}x{len(matrix[0])}, expected {N}x{N}"
        )
    return matrix


# ------------------------------------------------------------------------- SVG
def label_svg(code: str) -> str:
    """Full label as an SVG document in real millimeter units."""
    matrix = encode(code)
    modules = "".join(
        f'<rect x="{DM_X + c * MODULE:.3f}" y="{DM_Y + r * MODULE:.3f}" '
        f'width="{MODULE}" height="{MODULE}"/>'
        for r in range(N)
        for c in range(N)
        if matrix[r][c]
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{LABEL_W}mm" height="{LABEL_H}mm" '
        f'viewBox="0 0 {LABEL_W} {LABEL_H}">'
        f'<rect width="{LABEL_W}" height="{LABEL_H}" fill="#fff"/>'
        f'<g fill="#000">{modules}</g>'
        f'<text x="{(TXT_X0 + TXT_X1) / 2}" y="{LABEL_H / 2}" '
        f'textLength="{TXT_X1 - TXT_X0:.2f}" lengthAdjust="spacingAndGlyphs" '
        f'text-anchor="middle" dominant-baseline="central" '
        f"font-family=\"Bahnschrift, 'Arial Narrow', sans-serif\" font-weight=\"700\" "
        f'font-size="{TXT_FONT_MM}" fill="#000">{code}</text>'
        f"</svg>"
    )


# ------------------------------------------------------------------------- PDF
def label_pdf(code: str, path: Path) -> None:
    """Write a single-page PDF whose page is exactly the 25 x 12.5 mm label."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas

    matrix = encode(code)
    c = canvas.Canvas(str(path), pagesize=(LABEL_W * MM_TO_PT, LABEL_H * MM_TO_PT))
    c.setTitle(f"Lens label {code}")

    def rect_mm(x: float, y_top: float, w: float, h: float) -> None:
        # PDF origin is bottom-left; our spec measures y from the top edge.
        c.rect(
            x * MM_TO_PT,
            (LABEL_H - y_top - h) * MM_TO_PT,
            w * MM_TO_PT,
            h * MM_TO_PT,
            stroke=0,
            fill=1,
        )

    c.setFillColorRGB(1, 1, 1)
    rect_mm(0, 0, LABEL_W, LABEL_H)

    c.setFillColorRGB(0, 0, 0)
    for r in range(N):
        for col in range(N):
            if matrix[r][col]:
                rect_mm(DM_X + col * MODULE, DM_Y + r * MODULE, MODULE, MODULE)

    # Human-readable: Helvetica-Bold horizontally scaled to fill the text
    # region exactly, mirroring the SVG textLength behaviour.
    font, size_pt = "Helvetica-Bold", TXT_FONT_MM * MM_TO_PT
    natural_pt = stringWidth(code, font, size_pt)
    target_pt = (TXT_X1 - TXT_X0) * MM_TO_PT
    text = c.beginText()
    text.setFont(font, size_pt)
    text.setHorizScale(100 * target_pt / natural_pt)
    # Vertically center on cap height (~0.72 em for Helvetica).
    baseline_pt = (LABEL_H / 2) * MM_TO_PT - (0.72 * size_pt) / 2
    text.setTextOrigin(TXT_X0 * MM_TO_PT, baseline_pt)
    text.textOut(code)
    c.drawText(text)

    c.showPage()
    c.save()


# ------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate 25 x 12.5 mm lens labels (LE series)."
    )
    parser.add_argument("codes", nargs="+", metavar="CODE", help="e.g. LE123 LE124")
    parser.add_argument("--svg", action="store_true", help="write SVG only")
    parser.add_argument("--pdf", action="store_true", help="write PDF only")
    parser.add_argument(
        "-o", "--out", default="labels", help="output directory (default: labels)"
    )
    args = parser.parse_args(argv)

    want_svg = args.svg or not args.pdf
    want_pdf = args.pdf or not args.svg

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    for code in args.codes:
        code = code.upper()
        try:
            if want_svg:
                svg_path = out / f"{code}.svg"
                svg_path.write_text(label_svg(code), encoding="utf-8")
                print(f"wrote {svg_path}")
            if want_pdf:
                pdf_path = out / f"{code}.pdf"
                label_pdf(code, pdf_path)
                print(f"wrote {pdf_path}")
            register_print(code)
        except ValueError as err:
            print(f"error: {err}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
