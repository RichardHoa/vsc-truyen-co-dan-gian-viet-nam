"""The mục lục (PDF 553-556 here): the shared `vsc_ocr.toc` reading, with this
book's changes:
  - the pages come from `toc_pages` in assemble.yaml;
  - one entry per printed row: no row carries on the title above it (the
    shared parser joined "55. Trai kén vợ, gái kén chồng" to the next row
    when OCR read its page number "516" as "S16");
  - the item numbers run 1-58 after the "• Lời giới thiệu" row, so they come
    from the row order; the number as read is kept in `ocr_item` when it
    differs ("đ1." for 31, "S1." for 51), with any noise before it
    ("554 | 53.") dropped;
  - page numbers: "S" read for 5 and "l"/"I" for 1 are fixed; a number that
    breaks the increasing order ("1588" between 153 and 169, "283" between
    256 and 268) is repaired from the digits read when one fix fits, else
    left out (`printed_page: null`) and reported.

Writes data/books/<book>/toc.generated.yaml like the shared step.
"""

from __future__ import annotations

import re

from ...common import Book, from_ranges, to_ranges, write_yaml
from ...layout import norm_space
from ...toc import _is_toc_title, _rows, _strip_noise, printed_to_pdf
from .config import config

_page = re.compile(r"(?:^|[\s.…·_\-–—=:|,])(?P<page>[0-9SlIO]{1,4})\W*$")
_digit_fix = str.maketrans({"S": "5", "l": "1", "I": "1", "O": "0"})
_item = re.compile(r"^[0-9SlIOođ]{1,3}[.,:]$")
_letter = re.compile(r"[^\W\d_]")
# digits OCR confuses in this print
_confused = {"8": "630", "6": "85", "3": "8", "5": "63", "1": "7", "7": "1", "0": "86"}


def parse_row(text: str) -> dict | None:
    """'554 | 53. Hà Niên lấy người ...... 488' -> title, page, item as read."""
    text = _strip_noise(norm_space(text))
    if not _letter.search(text) or _is_toc_title(text):
        return None
    page = None
    m = _page.search(text)
    if m and re.search(r"\d", m.group("page")):
        page = m.group("page").translate(_digit_fix)
        text = text[:m.start("page")]
    tokens = text.split()
    item = None
    # noise and the item number before the title: "•", "554", "|", "53."
    while tokens and (not _letter.search(tokens[0]) or _item.match(tokens[0])):
        t = tokens.pop(0)
        if _item.match(t):
            item = t.rstrip(".,:")
    title = " ".join(tokens).strip(" .…·_-–—=~|")
    return dict(title=title, page=int(page) if page and page.isdigit() else None, ocr_item=item)


def _readings(s: str) -> set[int]:
    """Numbers one OCR slip away from s: a digit too many, or a digit misread."""
    out = {int(s[:i] + s[i + 1:]) for i in range(len(s)) if len(s) > 1}
    out |= {int(s[:i] + d + s[i + 1:]) for i, c in enumerate(s) for d in _confused.get(c, "")}
    return out


def _fix_pages(entries: list[dict]) -> list[str]:
    """Pages run upward. A number out of order is fixed when exactly one
    reading one OCR slip away from it is in order; otherwise it is left out."""
    problems = []
    for k, e in enumerate(entries):
        p = e["printed_page"]
        prev = next((x["printed_page"] for x in reversed(entries[:k]) if x["printed_page"]), 0)
        nxt = next((x["printed_page"] for x in entries[k + 1:] if x["printed_page"]), None)
        if p is not None and prev < p and (nxt is None or p < nxt):
            continue
        s = str(p) if p is not None else ""
        fits = sorted(x for x in _readings(s) if prev < x and (nxt is None or x < nxt)) if s else []
        if len(fits) == 1:
            e["ocr_page"], e["printed_page"] = s, fits[0]
            problems.append(f"row {e.get('item') or e['title']}: page read as {s}, out of order; {fits[0]} fits")
        else:
            e["ocr_page"], e["printed_page"] = s or None, None
            problems.append(f"row {e.get('item') or e['title']}: page read as {s or 'nothing'}, out of order; left out")
    return problems


def build_toc(book: Book) -> None:
    cfg = config(book)
    toc_pages = from_ranges(cfg.get("toc_pages"))
    entries = []
    for n in toc_pages:
        for r in _rows(book, n, table=True) or []:
            e = parse_row(r["text"])
            if e and e["title"]:
                entries.append(dict(title=e["title"], printed_page=e["page"], ocr_item=e["ocr_item"],
                                    toc_page=n, ocr_row=norm_space(r["text"])))
    # the first row is the Lời giới thiệu, then the stories in order
    for k, e in enumerate(entries):
        e["item"] = k if k else None
        if e["ocr_item"] is None or e["ocr_item"] == str(e["item"]):
            del e["ocr_item"]
    problems = _fix_pages(entries)
    convert, n_known = printed_to_pdf(book)
    works = book.s.get("works", [])
    for e in entries:
        e["pdf_page"] = convert(e["printed_page"])
        if e["item"] and e["item"] <= len(works):
            e["work"] = works[e["item"] - 1]["id"]   # by order: both lists hold the 58 stories in order
    if len(entries) != len(works) + 1:
        problems.append(f"{len(entries)} mục lục rows for {len(works)} works + the Lời giới thiệu")
    out = dict(toc_pages=to_ranges(toc_pages), printed_page_numbers_found=n_known,
               problems=problems, entries=entries)
    header = (
        "# Generated by `python -m vsc_ocr toc`. Check against the scan before use.\n"
        "# printed_page = number printed in the mục lục; pdf_page = page in the source PDF\n"
        "# (from the printed page numbers found on the pages). work = the structure.yaml\n"
        "# work in the same place in the order.\n"
    )
    write_yaml(book.dir / "toc.generated.yaml", out, header)
    print(f"  mục lục on page(s) {to_ranges(toc_pages)}: {len(entries)} rows, {len(problems)} problem(s)")
    for p in problems:
        print(f"    - {p}")
