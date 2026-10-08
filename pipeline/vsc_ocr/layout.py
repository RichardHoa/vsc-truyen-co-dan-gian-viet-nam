"""Geometry helpers shared by compare and clean. Boxes are [x0, y0, x1, y1],
normalised 0..1, origin top-left."""

from __future__ import annotations

import re
import statistics


def height(b) -> float:
    return b[3] - b[1]


def v_overlap(a, b) -> float:
    """Vertical overlap as a fraction of the smaller box height."""
    inter = min(a[3], b[3]) - max(a[1], b[1])
    h = min(height(a), height(b))
    return inter / h if h > 0 else 0.0


def v_overlap_max(a, b) -> float:
    """Vertical overlap as a fraction of the LARGER box height: a tall junk box
    (e.g. a whole column misread as one line) doesn't count as sharing a row
    with every small line it covers."""
    inter = min(a[3], b[3]) - max(a[1], b[1])
    h = max(height(a), height(b))
    return inter / h if h > 0 else 0.0


def union(boxes):
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def group_rows(lines: list[dict], min_overlap: float = 0.5) -> list[dict]:
    """Merge line boxes that sit on the same baseline into rows.

    Engines split a visual line differently: Vision may return a verse number
    ("28.") and its verse as two observations, or a mục lục title and its page
    number separately; Tesseract may do the opposite. Rows make both comparable.
    Returns [{"text", "bbox", "parts": [line, ...]}] top to bottom.
    """
    rows: list[list[dict]] = []
    for line in sorted(lines, key=lambda l: (l["bbox"][1], l["bbox"][0])):
        for row in rows:
            if all(v_overlap_max(p["bbox"], line["bbox"]) >= min_overlap for p in row):
                row.append(line)
                break
        else:
            rows.append([line])
    out = []
    for row in rows:
        row.sort(key=lambda l: l["bbox"][0])
        out.append(dict(
            text=" ".join(l["text"].strip() for l in row if l["text"].strip()),
            bbox=union([l["bbox"] for l in row]),
            parts=row,
        ))
    out.sort(key=lambda r: (r["bbox"][1], r["bbox"][0]))
    return out


def median_height(rows) -> float:
    hs = [height(r["bbox"]) for r in rows if height(r["bbox"]) > 0]
    return statistics.median(hs) if hs else 0.02


_ws = re.compile(r"\s+")


def norm_space(s: str) -> str:
    return _ws.sub(" ", s).strip()
