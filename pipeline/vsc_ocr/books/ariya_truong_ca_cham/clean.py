"""Ariya's copy of the shared `vsc_ocr.clean`, with this book's changes:
  - a verse line too long for the page, printed flush right on the next row,
    is joined back onto its line (`turnover: true`);
  - Dịch nghĩa / Dịch thơ pages are always verse, Đối chiếu dị bản always prose;
  - a page's printed number is trusted when a neighbour shows the same offset.

Turn merged OCR rows into structured page text.

Per book (headers repeat across pages, so this needs the whole book):
  1. Running headers/footers: rows at the very top/bottom of a page whose text
     (digits ignored) repeats on many pages -> removed. Decorative bands that
     OCR as junk in that zone are removed too.
  2. Printed page number: a lone number at the top/bottom, or a number glued to
     a running header ("74   Sử thi Ba Na").
  3. Footnotes: smaller rows near the bottom starting with (5), 5 or *.
  4. Page mode: "prose" (justified lines reaching the right margin) or "verse"
     (ragged lines).
       prose -> rows joined into paragraphs (indent / short line / gap / dash
                starts a new one); "continues" marks a first paragraph that
                carries on from the previous page.
       verse -> one segment per line, with line numbers ("28.", "1940")
                split off, stanza breaks, and speaker labels ("Già làng nói:").
  5. Headings: centred short rows, or rows in capitals.
  6. Inline markers kept in the text but also listed: footnote calls "(5)" and
     source page references "[tr.194]".
  7. Language guess per page (vi / mixed / other), from Vietnamese syllable
     structure, so mixed-language pages can be routed to review.

Text is never "corrected": printing errors in the books stay as printed.

Writes data/ocr/<book>/pages/pNNNN.json and data/ocr/<book>/preview.md.
"""

from __future__ import annotations

import difflib
import re
import statistics

from ...common import OCR_DIR, Book, nfc, page_id, read_json, strip_diacritics, write_json
from ...layout import height, median_height, norm_space, union
from ...vietnamese import guess_language
from .booktoc import version_of

EDGE_ROWS = 2          # how many rows at the top/bottom can be header/footer
TOP_ZONE = 0.15        # ...and they must lie within this fraction of the page
BOTTOM_ZONE = 0.85

VERSE_KINDS = {"literal-translation", "verse-translation"}
PROSE_KINDS = {"variant-comparison"}   # notes on the manuscripts, ragged but prose

_lone_number = re.compile(r"^\W*(\d{1,4})\W*$")
_lead_number = re.compile(r"^\W*(\d{1,4})\s+(\D.*)$")
_trail_number = re.compile(r"^(.*\D)\s+(\d{1,4})\W*$")
_verse_number = re.compile(r"^(\d{1,4})\s*[.)]?\s+(\S.*)$")
_footnote_start = re.compile(r"^(\(\d{1,2}\)|\d{1,2}[.)]?\s|\*)")
_note_call = re.compile(r"(?<=\S)\((\d{1,2})\)")
_source_ref = re.compile(r"\[tr\.\s*(\d+)\]")
_dash_start = re.compile(r"^[-–—•❖*]")


def _key(text: str) -> str:
    """Header identity: letters only, no digits/diacritics/case."""
    return re.sub(r"[^a-z]", "", strip_diacritics(text).casefold())


def _alpha_ratio(text: str) -> float:
    t = text.replace(" ", "")
    return sum(c.isalpha() for c in t) / len(t) if t else 0.0


def _edge_rows(rows):
    top = [i for i, r in enumerate(rows[:EDGE_ROWS]) if r["bbox"][3] <= TOP_ZONE]
    n = len(rows)
    bottom = [i for i in range(max(0, n - EDGE_ROWS), n) if rows[i]["bbox"][1] >= BOTTOM_ZONE]
    return top, bottom


def find_running_headers(pages: dict[int, dict]) -> set[str]:
    """Header/footer keys that repeat on enough pages of the book."""
    page_keys: dict[int, set[str]] = {}
    for n, merged in pages.items():
        rows = merged["rows"]
        top, bottom = _edge_rows(rows)
        keys = {_key(rows[i]["text"]) for i in top + bottom}
        page_keys[n] = {k for k in keys if len(k) >= 4}
    all_keys = sorted({k for ks in page_keys.values() for k in ks})
    min_pages = max(3, int(0.04 * len(pages)))
    repeating = set()
    for k in all_keys:
        count = sum(
            1 for ks in page_keys.values()
            if any(k == o or difflib.SequenceMatcher(None, k, o).ratio() >= 0.8 for o in ks)
        )
        if count >= min_pages:
            repeating.add(k)
    return repeating


def _is_header(text: str, headers: set[str]) -> bool:
    k = _key(text)
    if len(k) < 4:
        return False
    return any(k == h or difflib.SequenceMatcher(None, k, h).ratio() >= 0.8 for h in headers)


def clean_page(merged: dict, headers: set[str], mode: str | None = None) -> dict:
    rows = [dict(r) for r in merged["rows"]]
    removed, printed_page = [], None
    top, bottom = _edge_rows(rows)
    drop = set()
    for i in top + bottom:
        text = rows[i]["text"].strip()
        m = _lone_number.match(text)
        if m:
            printed_page = printed_page or int(m.group(1))
            drop.add(i)
            removed.append(dict(text=text, why="page_number"))
            continue
        for pat, num_group, rest_group in ((_lead_number, 1, 2), (_trail_number, 2, 1)):
            m = pat.match(text)
            if m and _is_header(m.group(rest_group), headers):
                printed_page = printed_page or int(m.group(num_group))
                drop.add(i)
                removed.append(dict(text=text, why="header+page_number"))
                break
        else:
            if _is_header(text, headers):
                drop.add(i)
                removed.append(dict(text=text, why="running_header"))
            elif i in top and _alpha_ratio(text) < 0.5:
                drop.add(i)
                removed.append(dict(text=text, why="decoration"))
            elif i in bottom and len(text.replace(" ", "")) <= 3:
                drop.add(i)  # specks or a misread page number ("1T")
                removed.append(dict(text=text, why="fragment"))
    body = [r for i, r in enumerate(rows) if i not in drop and r["text"].strip()]

    h = median_height(body)
    # ---- footnotes
    # A footnote starts low on the page, in smaller type, with "(5)"/"*", or with
    # "5 ..." after a visible gap (so a numbered verse line isn't mistaken for one).
    numbered = sum(1 for r in body if _verse_number.match(r["text"].strip()))
    foot_start = None
    for i, r in enumerate(body):
        if numbered >= 3 and not r["text"].lstrip().startswith(("(", "*")):
            continue  # numbered verse page: "28. ..." is a verse line, not a note
        if r["bbox"][1] <= 0.6 or height(r["bbox"]) >= 0.85 * h or not _footnote_start.match(r["text"]):
            continue
        gap = r["bbox"][1] - body[i - 1]["bbox"][3] if i else 1.0
        if r["text"].lstrip().startswith(("(", "*")) or gap >= 1.2 * h:
            foot_start = i
            break
    footnotes = []
    if foot_start is not None:
        end = foot_start
        for r in body[foot_start:]:
            small = height(r["bbox"]) < 0.95 * h
            if _footnote_start.match(r["text"]) and (small or not footnotes):
                footnotes.append(dict(r, flags=list(r.get("flags", []))))
            elif footnotes and small:  # footnote wrapped onto another row
                footnotes[-1]["text"] += " " + r["text"]
                footnotes[-1]["flags"] = sorted(set(footnotes[-1]["flags"]) | set(r.get("flags", [])))
            else:
                break
            end += 1
        body = body[:foot_start] + body[end:]

    segments, mode = _structure(body, h, mode)
    for f in footnotes:
        segments.append(dict(kind="footnote", text=norm_space(f["text"]), bbox=f["bbox"], flags=f["flags"]))

    for s in segments:
        notes = _note_call.findall(s["text"]) if s["kind"] != "footnote" else []
        refs = _source_ref.findall(s["text"])
        if notes:
            s["notes"] = [int(x) for x in notes]
        if refs:
            s["source_pages"] = [int(x) for x in refs]
        s["text"] = nfc(s["text"])

    all_text = " ".join(s["text"] for s in segments)
    return dict(
        page=merged.get("page"),
        printed_page=printed_page,
        mode=mode,
        language=guess_language(all_text),
        segments=segments,
        removed=removed,
        stats=dict(segments=len(segments),
                   flagged=sum(1 for s in segments if s.get("flags"))),
    )


def _structure(rows: list[dict], h: float, mode: str | None = None):
    if not rows:
        return [], "empty"
    xs0 = sorted(r["bbox"][0] for r in rows)
    xs1 = sorted(r["bbox"][2] for r in rows)
    left = xs0[len(xs0) // 10]
    right = xs1[(len(xs1) * 9) // 10]
    width = max(right - left, 1e-6)
    center = (left + right) / 2
    full = sum(1 for r in rows if r["bbox"][2] >= right - 0.04 * width)
    mean_width = statistics.mean((r["bbox"][2] - r["bbox"][0]) / width for r in rows)
    if mode is None:
        mode = "prose" if (len(rows) >= 4 and full / len(rows) >= 0.45) or mean_width > 0.85 else "verse"

    gaps = [rows[i + 1]["bbox"][1] - rows[i]["bbox"][3] for i in range(len(rows) - 1)]
    gaps = [g for g in gaps if g > 0]
    med_gap = statistics.median(gaps) if gaps else h * 0.4
    big_gap = max(0.9 * h, 1.8 * med_gap)

    def is_heading(r) -> bool:
        t = r["text"].strip()
        words = len(t.split())
        if not t or words > 15 or _verse_number.match(t):
            return False
        letters = [c for c in t if c.isalpha()]
        caps = sum(c.isupper() for c in letters) / len(letters) if letters else 0
        centred = (abs((r["bbox"][0] + r["bbox"][2]) / 2 - center) < 0.04
                   and r["bbox"][0] > left + 0.08 * width)
        tall = height(r["bbox"]) > 1.3 * h
        if caps > 0.8 and len(letters) >= 3:
            return True
        if mode == "prose":
            return centred and r["bbox"][2] < right - 0.08 * width
        return centred and tall

    segments: list[dict] = []
    prev = None
    for idx, r in enumerate(rows):
        text = norm_space(r["text"])
        flags = list(r.get("flags", []))
        gap = r["bbox"][1] - prev["bbox"][3] if prev else 0.0
        if is_heading(r):
            segments.append(dict(kind="heading", text=text, bbox=r["bbox"], flags=flags))
            prev = r
            continue
        if mode == "prose":
            indent = r["bbox"][0] > left + 0.05 * width
            prev_short = prev is not None and prev["bbox"][2] < right - 0.06 * width
            new_par = (
                not segments or segments[-1]["kind"] != "paragraph" or indent or prev_short
                or gap > big_gap or bool(_dash_start.match(text))
            )
            if new_par:
                seg = dict(kind="paragraph", text=text, bbox=list(r["bbox"]), flags=flags)
                if not segments and not indent and not _dash_start.match(text):
                    seg["continues"] = True  # carries on from the previous page
                segments.append(seg)
            else:
                seg = segments[-1]
                if seg["text"].endswith("-") and len(seg["text"]) > 1 and seg["text"][-2].isalpha() \
                        and text[:1].islower():
                    seg["text"] += text        # hyphenated name broken across lines: Tơ-bu-|lăng-xu
                else:
                    seg["text"] += " " + text
                seg["bbox"] = [min(seg["bbox"][0], r["bbox"][0]), seg["bbox"][1],
                               max(seg["bbox"][2], r["bbox"][2]), r["bbox"][3]]
                seg["flags"] = sorted(set(seg["flags"]) | set(flags))
        else:
            if _is_turnover(r, text, gap, h, left, right, width) and segments \
                    and segments[-1]["kind"] == "verse":
                # the end of a verse line too long for the page, printed flush
                # right on the next row: "Muốn dập tắt lửa thiêng nơi quê hương"
                # / "Panduranga ta đây" -> one line
                seg = segments[-1]
                seg["text"] += " " + text
                seg["bbox"] = union([seg["bbox"], r["bbox"]])
                seg["flags"] = sorted(set(seg["flags"]) | set(flags))
                seg["turnover"] = True
                prev = r
                continue
            seg = dict(kind="verse", text=text, bbox=r["bbox"], flags=flags)
            m = _verse_number.match(text)
            if m and int(m.group(1)) < 10000:
                seg["line_no"] = int(m.group(1))
                seg["text"] = m.group(2)
            elif _lone_number.match(text):
                seg["kind"] = "line_number"
            elif text.endswith(":") and len(text.split()) <= 8:
                seg["kind"] = "speaker"
            if prev is not None and gap > big_gap:
                seg["stanza_break"] = True
            segments.append(seg)
        prev = r
    return segments, mode


def _is_turnover(r, text, gap, h, left, right, width) -> bool:
    """A verse row that only carries the end of the line above it: no verse
    number, no gap above it, starting well past the indent and ending at the
    right margin."""
    b = r["bbox"]
    return (not _verse_number.match(text) and not _lone_number.match(text)
            and gap < 0.5 * h
            and b[0] > left + 0.35 * width
            and b[2] >= right - 0.04 * width)


def clean_book(book: Book, pages: list[int]) -> None:
    merged = {}
    for n in pages:
        p = book.merged_path(n)
        if p.exists():
            merged[n] = read_json(p)
    if not merged:
        print("  nothing to clean; run `compare` first")
        return
    # header detection uses every merged page of the book, not just this batch
    all_merged = dict(merged)
    for p in sorted((OCR_DIR / book.id / "merged").glob("p*.json")):
        n = int(p.stem[1:])
        if n not in all_merged:
            all_merged[n] = read_json(p)
    headers = find_running_headers(all_merged)

    langs = {"vi": 0, "mixed": 0, "other": 0, "unknown": 0}
    for n, m in merged.items():
        m.setdefault("page", n)
        # translations printed line by line are verse whatever the layout
        # looks like (long verse lines can fill a page like prose); notes on
        # the manuscripts are prose even where their lines are short
        kind = (version_of(book, n) or {}).get("kind")
        mode = "verse" if kind in VERSE_KINDS else "prose" if kind in PROSE_KINDS else None
        page = clean_page(m, headers, mode=mode)
        write_json(book.page_path(n), page)
        langs[page["language"]["guess"]] += 1
    suspect = infer_printed_pages(book)
    print(f"  cleaned {len(merged)} page(s); {len(headers)} running header(s); language: {langs}; "
          f"{suspect} suspicious printed page number(s)")
    write_preview(book)


def infer_printed_pages(book: Book, window: int = 15) -> int:
    """Printed page = PDF page - offset, and the offset is constant over long
    stretches. Fit it locally (median of detected offsets within ±window pages),
    mark detections that disagree as suspect (OCR misreads, numbers from a
    mục lục...), and estimate the number for pages where none was found.
    Writes `printed_page_est` (and `printed_page_suspect`) into each page."""
    files = {int(p.stem[1:]): p for p in (OCR_DIR / book.id / "pages").glob("p*.json")}
    pages = {n: read_json(p) for n, p in files.items()}
    offsets = {n: n - pg["printed_page"] for n, pg in pages.items() if pg.get("printed_page")}
    suspect = 0
    for n, pg in pages.items():
        near = [o for m, o in offsets.items() if abs(m - n) <= window and m != n]
        est = None
        if len(near) >= 3:
            off = statistics.median_low(near)
            if sum(1 for o in near if o == off) >= max(2, len(near) // 2):
                est = n - off if n - off >= 1 else None
        own = offsets.get(n)
        if own is not None and any(offsets.get(m) == own for m in (n - 2, n - 1, n + 1, n + 2)):
            # the offset shifts where the book has an unnumbered or missing
            # page; a detection that agrees with a close neighbour wins over
            # the median of the wider window
            est = pg["printed_page"]
        before = (pg.get("printed_page_est"), pg.get("printed_page_suspect"))
        pg["printed_page_est"] = est if est is not None else pg.get("printed_page")
        bad = bool(pg.get("printed_page") and est is not None and pg["printed_page"] != est)
        pg["printed_page_suspect"] = bad
        suspect += bad
        if (pg["printed_page_est"], pg["printed_page_suspect"]) != before:
            write_json(files[n], pg)
    return suspect


def write_preview(book: Book) -> None:
    """A Markdown preview of everything cleaned so far, readable on GitHub.
    Flagged text is marked ⚠ so reviewers can jump to it."""
    out = [f"# {book.s['title']}\n",
           "_OCR preview, generated by `python -m vsc_ocr clean`. ⚠ = engines disagree or low confidence._\n"]
    for p in sorted((OCR_DIR / book.id / "pages").glob("p*.json")):
        page = read_json(p)
        n = page.get("page") or int(p.stem[1:])
        lang = page["language"]
        head = f"## {page_id(n)}"
        if page.get("printed_page_est"):
            head += f" · tr. {page['printed_page_est']}" + ("?" if page.get("printed_page_suspect") else "")
        head += f" · {page['mode']} · {lang['guess']}"
        out.append(head + "\n")
        for s in page["segments"]:
            mark = " ⚠" if s.get("flags") else ""
            t = s["text"]
            if s["kind"] == "heading":
                out.append(f"### {t}{mark}\n")
            elif s["kind"] == "verse":
                if s.get("stanza_break"):
                    out.append("")
                num = f"{s['line_no']}. " if "line_no" in s else ""
                out.append(f"{num}{t}{mark}  ")
            elif s["kind"] == "speaker":
                out.append(f"**{t}**{mark}  ")
            elif s["kind"] == "footnote":
                out.append(f"\n> {t}{mark}\n")
            elif s["kind"] == "line_number":
                continue
            else:
                out.append(("… " if s.get("continues") else "") + f"{t}{mark}\n")
        out.append("")
    path = OCR_DIR / book.id / "preview.md"
    path.write_text("\n".join(out), encoding="utf-8")
