"""Ruled tables (e.g. a transliteration table): find the grid on the page
image and read it cell by cell.

Page OCR reads a ruled table row by row and loses the columns. The rules
themselves are easy to find on the scan: long horizontal and vertical runs of
ink. Each cell between them is re-read on its own with Tesseract. Columns
listed in `drop_columns` (e.g. a column in Cham script) are not read.

Returns None when no grid is found, so the caller can say the table was not
parsed instead of guessing.
"""

from __future__ import annotations

from PIL import Image, ImageFilter, ImageOps

from ...common import nfc
from ...layout import norm_space

LINE = 0.6      # a rule covers at least this share of the table's width / height
INK = 140


def _ink_mask(img: Image.Image) -> Image.Image:
    return ImageOps.invert(img.convert("L")).point(lambda v: 255 if v > 255 - INK else 0)


def _longest_runs(mask: Image.Image) -> list[int]:
    """Longest unbroken run of ink in each row of a 0/255 mask."""
    w, h = mask.size
    data = mask.tobytes()
    return [max(map(len, data[y * w:(y + 1) * w].split(b"\x00"))) for y in range(h)]


def _centres(flags: list[bool], merge: int = 15) -> list[int]:
    """Centres of the runs of True; runs closer than `merge` px are one rule
    (a doubled or broken line)."""
    out, start = [], None
    for i, f in enumerate(flags + [False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            c = (start + i - 1) // 2
            if out and c - out[-1] < merge:
                out[-1] = (out[-1] + c) // 2
            else:
                out.append(c)
            start = None
    return out


def find_grid(img: Image.Image) -> tuple[list[int], list[int]] | None:
    """(x positions of vertical rules, y positions of horizontal rules).
    A rule is a long unbroken run of ink; the mask is thickened first so a
    slightly skewed scan still gives unbroken runs."""
    mask = _ink_mask(img).filter(ImageFilter.MaxFilter(5))
    w, h = mask.size
    runs = _longest_runs(mask)
    ys = _centres([r >= 0.4 * w for r in runs])
    if len(ys) < 2:
        return None
    band = mask.crop((0, ys[0], w, ys[-1] + 1)).transpose(Image.Transpose.TRANSPOSE)
    xs = _centres([r >= LINE * (ys[-1] - ys[0]) for r in _longest_runs(band)])
    if len(xs) < 2:
        return None
    return xs, ys


def read_table(img: Image.Image, tesseract: str, drop_columns=()) -> dict | None:
    """{'rows': [[cell text, ...]], 'bbox': [x0, y0, x1, y1] normalised} or None."""
    from ...ocr_tesseract import recognize
    import tempfile

    grid = find_grid(img)
    if not grid:
        return None
    xs, ys = grid
    W, H = img.size
    drop = {c - 1 for c in drop_columns}
    rows = []
    for y0, y1 in zip(ys, ys[1:]):
        if y1 - y0 < 8:
            continue
        cells = []
        for k, (x0, x1) in enumerate(zip(xs, xs[1:])):
            if k in drop or x1 - x0 < 8:
                continue
            cell = img.crop((x0 + 4, y0 + 4, x1 - 3, y1 - 3))
            if not _ink_mask(cell).getbbox():
                cells.append("")
                continue
            with tempfile.NamedTemporaryFile(suffix=".png") as f:
                cell.save(f.name)
                res = recognize(tesseract, f.name, psm=6)
            cells.append(nfc(norm_space(" / ".join(l["text"] for l in res["lines"]))))
        if any(cells):
            rows.append(cells)
    if not rows:
        return None
    return dict(rows=rows, bbox=[xs[0] / W, ys[0] / H, xs[-1] / W, ys[-1] / H])


def to_markdown(rows: list[list[str]]) -> str:
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    esc = lambda t: t.replace("|", "\\|")
    out = ["| " + " | ".join(esc(c) for c in rows[0]) + " |",
           "|" + "---|" * width]
    out += ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows[1:]]
    return "\n".join(out)
