"""The shared `vsc_ocr.clean`, plus what it gets wrong on this book. Each page
goes through the shared `clean_page`; before that:

  - footnotes: everything below the short rule at the foot of the page (found
    on the render) is the page's notes, one segment per note. Notes start
    with "(1)", "(2)"... or "(*)" (p178), which the shared regex doesn't know;
  - scene breaks: the three-asterisk ornament between paragraphs (found on
    the render: a small centred mark alone in a wide gap) becomes a `break`
    segment; whatever OCR made of it is dropped;
  - drop caps: on the first page of the Lời giới thiệu and of every story,
    see `dropcap`;
  - pages are prose: a page the shared step calls verse (short dialogue
    lines) is joined back into paragraphs;
  - rows without a letter (specks, show-through) are dropped. The book has
    no running headers, so the shared search for them is skipped.

Writes data/ocr/<book>/pages/pNNNN.json and preview.md like the shared step.
"""

from __future__ import annotations

import re

from PIL import Image, ImageOps

from ... import clean as shared
from ...common import OCR_DIR, Book, from_ranges, read_json, write_json
from ...layout import median_height, norm_space
from . import dropcap
from .config import config, section_starts

INK = 140
_lone_number = re.compile(r"^\W*\d{1,4}\W*$")
_letter = re.compile(r"[^\W\d_]")
# "(1)", "(2)", "(*)" as OCR reads them: "(L)", "(l", "1)", "(°)", "(+)"
NOTE_START = re.compile(r"^[^\w(]{0,2}(?:[(\[{]\s*(?P<a>[0-9lLIi|!¡*°+xX]{1,2})\s*[)\]}]?\s*|(?P<b>\S{1,2})\)\s+)")


def _ink_rows(img: Image.Image, x0: int, x1: int, y0: int, y1: int) -> list[float]:
    """Share of ink per pixel row of a region."""
    region = ImageOps.invert(img.crop((x0, y0, x1, y1)).convert("L")).point(lambda v: 255 if v > 255 - INK else 0)
    return [v / 255 for v in region.resize((1, y1 - y0), Image.BOX).getdata()]


def find_rule(img: Image.Image, rows: list[dict]) -> float | None:
    """y (0-1) of the footnote rule: a thin horizontal line, short (about a
    fifth of the text width) and starting at the left margin, low on the page,
    with nothing else in its pixel rows."""
    if not rows:
        return None
    W, H = img.size
    left = min(r["bbox"][0] for r in rows)
    right = max(r["bbox"][2] for r in rows)
    x0, x1 = max(0, int((left - 0.02) * W)), min(W, int((right + 0.02) * W))
    y0, y1 = int(0.45 * H), int(0.97 * H)
    ink = _ink_rows(img, x0, x1, y0, y1)
    width = x1 - x0
    for i in range(6, len(ink) - 6):
        if not 0.06 <= ink[i] <= 0.5:
            continue
        # thin (up to about 5 pixel rows at 300 dpi), with blank rows around it
        if max(ink[i - 6], ink[i + 6]) > 0.3 * ink[i] or ink[i] < max(ink[i - 3:i + 4]):
            continue
        y = y0 + i
        # the rule can lean a little: look at a band of rows around it
        line = ImageOps.invert(img.crop((x0, y - 4, x1, y + 5)).convert("L")).resize((width, 1), Image.BOX)
        cols = [v > 25 for v in line.getdata()]
        runs, start = [], None
        for k, c in enumerate(cols + [False]):
            if c and start is None:
                start = k
            elif not c and start is not None:
                if runs and start - runs[-1][1] <= 0.01 * width:
                    runs[-1] = (runs[-1][0], k)   # a break in the scan of the line
                else:
                    runs.append((start, k))
                start = None
        if not runs:
            continue
        a, b = max(runs, key=lambda r: r[1] - r[0])
        if 0.1 * width <= b - a <= 0.45 * width and a <= 0.1 * width and sum(cols) <= 1.3 * (b - a):
            return y / H
    return None


def find_breaks(img: Image.Image, rows: list[dict]) -> list[list[float]]:
    """Scene-break ornaments: a small, centred cluster of ink alone in a gap
    of more than two text rows between paragraphs. Returns their bboxes."""
    if len(rows) < 2:
        return []
    W, H = img.size
    h = median_height(rows)
    left = min(r["bbox"][0] for r in rows)
    right = max(r["bbox"][2] for r in rows)
    centre = (left + right) / 2
    out = []
    for a, b in zip(rows, rows[1:]):
        gy0, gy1 = a["bbox"][3], b["bbox"][1]
        if gy1 - gy0 < 2.2 * h:
            continue
        box = (int(left * W), int((gy0 + 0.2 * h) * H), int(right * W), int((gy1 - 0.2 * h) * H))
        if box[3] <= box[1]:
            continue
        bits = ImageOps.invert(img.crop(box).convert("L")).point(lambda v: 255 if v > 255 - INK else 0)
        mid = (int((centre - 0.1) * W) - box[0], int((centre + 0.1) * W) - box[0])
        cols = [v * bits.height / 255 for v in bits.resize((bits.width, 1), Image.BOX).getdata()]
        inside = sum(cols[max(0, mid[0]):mid[1]])
        outside = sum(cols) - inside
        # the ornament sits in the middle; specks and show-through elsewhere are few
        if inside < 40 or outside > 0.3 * inside:
            continue
        ink = bits.crop((max(0, mid[0]), 0, mid[1], bits.height)).getbbox()
        bx0, by0 = (box[0] + max(0, mid[0]) + ink[0]) / W, (box[1] + ink[1]) / H
        bx1, by1 = (box[0] + max(0, mid[0]) + ink[2]) / W, (box[1] + ink[3]) / H
        if by1 - by0 <= 3 * h:
            out.append([round(bx0, 4), round(by0, 4), round(bx1, 4), round(by1, 4)])
    return out


def as_prose(segments: list[dict]) -> list[dict]:
    """The book is prose throughout; a page of short dialogue lines looks
    ragged enough for the shared step to call it verse. Join its lines back
    into paragraphs with the shared rules: an indented line, a dash or a short
    line before starts a new paragraph."""
    lines = [s for s in segments if s["kind"] in ("verse", "speaker", "line_number")]
    if not lines:
        return segments
    left = sorted(s["bbox"][0] for s in lines)[len(lines) // 10]
    right = sorted(s["bbox"][2] for s in lines)[(len(lines) * 9) // 10]
    width = max(right - left, 1e-6)
    out: list[dict] = []
    prev = None
    for s in segments:
        if s not in lines:
            out.append(s)
            prev = None
            continue
        text = (f"{s['line_no']} " if "line_no" in s else "") + s["text"]
        indent = s["bbox"][0] > left + 0.05 * width
        prev_short = prev is not None and prev["bbox"][2] < right - 0.06 * width
        if prev is None or indent or prev_short or shared._dash_start.match(text):
            seg = dict(kind="paragraph", text=text, bbox=list(s["bbox"]), flags=list(s.get("flags", [])))
            if not out and not indent and not shared._dash_start.match(text):
                seg["continues"] = True
            out.append(seg)
        else:
            seg = out[-1]
            seg["text"] += " " + text
            seg["bbox"] = [min(seg["bbox"][0], s["bbox"][0]), seg["bbox"][1], max(seg["bbox"][2], s["bbox"][2]), s["bbox"][3]]
            seg["flags"] = sorted(set(seg["flags"]) | set(s.get("flags", [])))
        prev = s
    return out


def split_notes(rows: list[dict]) -> list[dict]:
    """Footnote rows -> one footnote segment per note."""
    notes: list[dict] = []
    for r in rows:
        text = norm_space(r["text"])
        m = NOTE_START.match(text)
        if m or not notes:
            raw = (m.group("a") or m.group("b")) if m else None
            notes.append(dict(kind="footnote", marker_raw=raw, text=text, bbox=list(r["bbox"]),
                              flags=list(r.get("flags", []))))
        else:
            n = notes[-1]
            n["text"] += " " + text
            n["bbox"] = [min(n["bbox"][0], r["bbox"][0]), n["bbox"][1], max(n["bbox"][2], r["bbox"][2]), r["bbox"][3]]
            n["flags"] = sorted(set(n["flags"]) | set(r.get("flags", [])))
    return notes


def clean_page(book: Book, n: int, merged: dict, headers: set, firsts: set, lexicon) -> dict:
    rows = [dict(r) for r in merged["rows"] if r["text"].strip()]
    path = book.render_path(n)
    img = Image.open(path) if path.exists() else None
    extra: dict = {}

    # page number rows stay for the shared step, which reads and drops them
    tail = [r for r in rows if r["bbox"][1] >= shared.BOTTOM_ZONE and _lone_number.match(r["text"].strip())]
    # rows without a letter are specks, show-through or ornaments
    body = [r for r in rows if r not in tail and _letter.search(r["text"])]

    notes: list[dict] = []
    rule = find_rule(img, body) if img is not None else None
    if rule is not None:
        below = [r for r in body if r["bbox"][1] >= rule - 0.003]
        if below:
            body = [r for r in body if r not in below]
            notes = split_notes(below)
            extra["footnote_rule"] = round(rule, 4)

    breaks = find_breaks(img, body) if img is not None else []
    if breaks:
        # what OCR made of an ornament ("*", ". :") goes
        body = [r for r in body if not any(b[1] - 0.01 <= (r["bbox"][1] + r["bbox"][3]) / 2 <= b[3] + 0.01
                                           and not re.search(r"[^\W\d_]{3}", r["text"]) for b in breaks)]

    if n in firsts:
        extra["dropcap"] = dropcap.fix_page(book, n, body, lexicon)

    page = shared.clean_page(dict(merged, rows=body + tail), headers)
    if page["mode"] == "verse":
        page["segments"], page["mode"] = as_prose(page["segments"]), "prose"
    segs = page["segments"]
    for b in breaks:
        at = next((k for k, s in enumerate(segs) if s["bbox"][1] > b[1]), len(segs))
        segs.insert(at, dict(kind="break", text="* * *", bbox=b, flags=[]))
    segs.extend(notes)
    page.update(extra)
    if breaks:
        page["scene_breaks"] = len(breaks)
    page["stats"] = dict(segments=len(segs), flagged=sum(1 for s in segs if s.get("flags")))
    return page


def clean_book(book: Book, pages: list[int]) -> None:
    merged = {}
    for n in pages:
        p = book.merged_path(n)
        if p.exists():
            merged[n] = read_json(p)
    if not merged:
        print("  nothing to clean; run `compare` first")
        return
    all_merged = dict(merged)
    for p in sorted((OCR_DIR / book.id / "merged").glob("p*.json")):
        k = int(p.stem[1:])
        if k not in all_merged:
            all_merged[k] = read_json(p)
    headers: set = set()   # the book has no running headers
    cfg = config(book)
    firsts = section_starts(book, cfg)
    # the words of the book, less the broken first words beside the drop caps
    lexicon = dropcap.Lexicon(r["text"].split(" ", 1)[-1] if k in firsts and i < 4 else r["text"]
                              for k, m in all_merged.items() for i, r in enumerate(m["rows"]))
    skip = set(from_ranges(cfg.get("no_dropcap")))
    firsts -= skip

    langs = {"vi": 0, "mixed": 0, "other": 0, "unknown": 0}
    found = notes = breaks = 0
    for n, m in sorted(merged.items()):
        m.setdefault("page", n)
        page = clean_page(book, n, m, headers, firsts, lexicon)
        write_json(book.page_path(n), page)
        langs[page["language"]["guess"]] += 1
        found += bool(page.get("dropcap", {}).get("letter"))
        notes += sum(1 for s in page["segments"] if s["kind"] == "footnote")
        breaks += page.get("scene_breaks", 0)
    suspect = shared.infer_printed_pages(book)
    print(f"  cleaned {len(merged)} page(s); language: {langs}; {suspect} suspicious printed page number(s); "
          f"{found}/{len(firsts & set(merged))} drop cap(s) read; {notes} footnote(s); {breaks} scene break(s)")
    shared.write_preview(book)
