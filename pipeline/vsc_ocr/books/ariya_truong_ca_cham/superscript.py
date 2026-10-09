"""Find raised marks (superscript note calls, "vô cùng⁽⁶⁾") on the page image.

OCR engines read the tiny raised "(6)" as junk ("cùng\"'", "chệ®)") or drop
it. On the scan it is easy to see: a small cluster of ink that sits entirely
in the upper part of the text row, with no ink below it, made of three or
more strokes ("(", digits, ")"). This module finds such clusters in a row.
Superscript digits are too small at these scan resolutions to be read
reliably, so their number comes from the call sequence, not from here.

Used by `notes` on the stretch of text where the call sequence has a gap.
"""

from __future__ import annotations

from PIL import Image, ImageOps

INK = 140             # grey level below which a pixel is ink
TOP_BAND = 0.6        # a superscript lies in the top 60 % of the row


def _column_ink(img: Image.Image) -> list[int]:
    """Ink per column, computed in C: invert, squash to one row."""
    inv = ImageOps.invert(img.convert("L")).point(lambda v: 255 if v > 255 - INK else 0)
    return list(inv.resize((img.width, 1), Image.BOX).getdata())


def clusters(row_img: Image.Image) -> list[tuple[int, int]]:
    """[(x0, x1)] of clusters of three or more strokes with ink in the upper
    part of the row and none below it."""
    w, h = row_img.size
    if w < 4 or h < 6:
        return []
    top = _column_ink(row_img.crop((0, 0, w, int(h * TOP_BAND))))
    # (stop short of the bottom: the next row's accents can reach into the box)
    low = _column_ink(row_img.crop((0, int(h * TOP_BAND), w, int(h * 0.92))))
    runs, start = [], None
    for x in range(w + 1):
        high_only = x < w and top[x] > 0 and low[x] == 0
        if high_only and start is None:
            start = x
        elif not high_only and start is not None:
            runs.append((start, x))
            start = None
    # "(", "6", ")" are separate strokes with thin gaps between them
    groups: list[list[tuple[int, int]]] = []
    for r in runs:
        if groups and r[0] - groups[-1][-1][1] <= 0.12 * h \
                and all(low[x] == 0 for x in range(groups[-1][-1][1], r[0])):
            groups[-1].append(r)
        else:
            groups.append([r])
    # about as wide as a letter or two; a lone raised stroke or a pair is an
    # apostrophe or a quote mark
    out = []
    for g in groups:
        a, b = g[0][0], g[-1][1]
        if len(g) < 3 or not 0.25 * h <= b - a <= 1.6 * h:
            continue
        # it floats: clear of the top of the box (where the row above can
        # reach down) and about a third of the row high
        ink = ImageOps.invert(row_img.crop((a, 0, b, int(h * TOP_BAND))).convert("L")) \
            .point(lambda v: 255 if v > 255 - INK else 0).getbbox()
        if ink and ink[1] > 0.1 * h and 0.2 * h <= ink[3] - ink[1] <= 0.5 * h:
            out.append((a, b))
    return out


def raised_marks(page_img: Image.Image, bbox) -> list[float]:
    """Positions (fraction of the row's width) of raised marks in one row."""
    W, H = page_img.size
    x0, x1 = int(bbox[0] * W), int(bbox[2] * W)
    pad = int(0.15 * (bbox[3] - bbox[1]) * H)  # the raised call can top the row box
    y0, y1 = max(0, int(bbox[1] * H) - pad), int(bbox[3] * H)
    if y1 - y0 < 6 or x1 - x0 < 6:
        return []
    row = page_img.crop((x0, y0, min(W, x1 + int(0.02 * W)), y1))
    return [(a + b) / 2 / (x1 - x0) for a, b in clusters(row)
            if a >= 0.05 * row.width]  # at the very start: a verse number, not a call
