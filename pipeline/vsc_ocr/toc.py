"""Find and parse a book's mục lục (table of contents).

1. Find pages whose top rows say "MỤC LỤC"; the TOC continues on following
   pages while most rows end in a page number.
2. Each row "Title ....... 123" becomes an entry; a title wrapped over two rows
   is re-joined; indentation gives the nesting level; rows without a number
   are section labels ("Phần thứ nhất").
3. Printed page numbers are converted to PDF pages using the printed numbers
   the `clean` step found on each page (nearest known page + offset).
4. Entries are matched to the works found by `inventory`, and the result is
   written to data/books/<book>/toc.generated.yaml for a human to check. For
   books with no per-story splits, these entries are what you turn into works.

Scanned books sometimes contain the same spread twice, so duplicate entries
are dropped.
"""

from __future__ import annotations

import re

import shutil

from .common import Book, read_json, strip_diacritics, to_ranges, write_json, write_yaml
from .inventory import _similar
from .layout import group_rows, norm_space

_entry = re.compile(
    r"^(?P<title>.*?[^\W\d_][^\d]*?)"        # title: has a letter, no trailing digits
    r"(?P<sep>[\s.…·_\-–—=:|,]+)"             # leaders / spaces before the number
    r"(?P<page>\d{1,4})\W*$"
)
_title_marker = re.compile(r"^(muc luc|noi dung)\b")
_item_no = re.compile(r"^(\d{1,3})\s*[.,:)]\s*")
TABLE_ENGINE = "tesseract-table"
MAX_TOC_PAGES = 8


def _strip_noise(text: str) -> str:
    """Drop OCR specks before a title: punctuation, and lone one-letter tokens
    that aren't capitals ("ị s Lời giới thiệu" -> "Lời giới thiệu")."""
    tokens = text.split()
    while tokens:
        t = tokens[0]
        if not any(c.isalnum() for c in t):
            tokens.pop(0)
        elif len(t) == 1 and t.isalpha() and not t.isupper() and len(tokens) > 1:
            tokens.pop(0)
        elif len(t) == 1 and t.isupper() and len(tokens) > 1 and _item_no.match(tokens[1]):
            tokens.pop(0)  # "Ệ 44. Bò và chó sói"
        else:
            break
    return " ".join(tokens)


def _is_toc_title(text: str) -> bool:
    return bool(_title_marker.match(strip_diacritics(text).casefold().strip(" .:")))


def _table_ocr(book: Book, n: int):
    """Mục lục pages are tables (number | title | dot leaders | page). Tesseract's
    default page segmentation scrambles them; --psm 6 (one uniform block) reads
    them row by row. Cached as data/ocr/<book>/tesseract-table/pNNNN.json."""
    out = book.ocr_path(TABLE_ENGINE, n)
    if out.exists():
        return read_json(out)
    img = book.render_path(n)
    if not img.exists() or not shutil.which("tesseract"):
        return None
    from .ocr_tesseract import _check, recognize
    result = recognize(_check(), str(img), psm=6)
    write_json(out, result)
    return result


def _rows(book: Book, n: int, table: bool = False):
    data = _table_ocr(book, n) if table else None
    if data is not None:
        rows = [dict(text=l["text"], bbox=l["bbox"]) for l in data["lines"]]
    else:
        p = book.merged_path(n)
        if not p.exists():
            return None
        rows = [dict(text=r["text"], bbox=r["bbox"]) for r in read_json(p)["rows"]]
    # drop running headers/page numbers using what `clean` removed
    cp = book.page_path(n)
    if cp.exists():
        gone = {r["text"] for r in read_json(cp)["removed"]}
        rows = [r for r in rows if r["text"] not in gone]
    return group_rows(rows)


def _numbered_share(rows) -> float:
    if not rows:
        return 0.0
    return sum(1 for r in rows if _entry.match(norm_space(r["text"]))) / len(rows)


def find_toc_pages(book: Book) -> list[int]:
    pages = []
    n = 1
    while n <= book.page_count:
        rows = _rows(book, n)
        if rows and any(_is_toc_title(r["text"]) for r in rows[:4]):
            run = [n]
            m = n + 1
            while m <= book.page_count and len(run) < MAX_TOC_PAGES:
                nxt = _rows(book, m, table=True)
                if not nxt or _numbered_share(nxt) < 0.5:
                    break
                run.append(m)
                m += 1
            pages.extend(run)
            n = m
        else:
            n += 1
    return pages


def parse_entries(book: Book, toc_pages: list[int]) -> list[dict]:
    entries, pending = [], None
    for n in toc_pages:
        rows = _rows(book, n, table=True) or []
        if not rows:
            continue
        min_x = min(r["bbox"][0] for r in rows)
        for r in rows:
            text = _strip_noise(norm_space(r["text"]))
            if not text or _is_toc_title(text) or strip_diacritics(text).casefold() == "trang":
                continue
            level = max(0, round((r["bbox"][0] - min_x) / 0.04))
            m = _entry.match(text)
            if m:
                title = m.group("title").strip(" .…·_-–—=")
                if pending is not None:
                    title = pending["title"] + " " + title
                    level = pending["level"]
                    pending = None
                entry = dict(title=title, printed_page=int(m.group("page")), level=level, toc_page=n)
                num = _item_no.match(title)
                if num:
                    entry["item"] = int(num.group(1))
                    entry["title"] = title[num.end():].strip()
                entries.append(entry)
            else:
                if pending is not None:  # a section label, not a wrapped title
                    entries.append(dict(title=pending["title"], printed_page=None,
                                        level=pending["level"], toc_page=pending["toc_page"]))
                pending = dict(title=text, level=level, toc_page=n)
    if pending is not None:
        entries.append(dict(title=pending["title"], printed_page=None, level=pending["level"],
                            toc_page=pending["toc_page"]))

    seen, out = set(), []
    for e in entries:
        key = (strip_diacritics(e["title"]).casefold(), e["printed_page"])
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def printed_to_pdf(book: Book):
    known: list[tuple[int, int]] = []  # (printed, pdf)
    for n in range(1, book.page_count + 1):
        p = book.page_path(n)
        if p.exists():
            page = read_json(p)
            pp = page.get("printed_page_est") or (None if page.get("printed_page_suspect") else page.get("printed_page"))
            if pp:
                known.append((pp, n))
    if not known:
        return lambda printed: None, 0

    def convert(printed):
        if printed is None:
            return None
        exact = [n for pp, n in known if pp == printed]
        if exact:
            return exact[0]
        pp, n = min(known, key=lambda k: abs(k[0] - printed))
        guess = printed + (n - pp)
        return guess if 1 <= guess <= book.page_count else None
    return convert, len(known)


def build_toc(book: Book) -> None:
    toc_pages = find_toc_pages(book)
    if not toc_pages:
        print("  no mục lục found in the OCR'd pages")
        return
    entries = parse_entries(book, toc_pages)
    convert, n_known = printed_to_pdf(book)
    works = book.s.get("works", [])
    matched = 0
    for e in entries:
        e["pdf_page"] = convert(e["printed_page"])
        best, best_r = None, 0.0
        for w in works:
            r = _similar(e["title"], w["title"])
            if r > best_r:
                best, best_r = w, r
        if best is not None and best_r >= 0.8:
            e["work"] = best["id"]
            matched += 1
        del e["toc_page"]
    out = dict(
        toc_pages=to_ranges(toc_pages),
        printed_page_numbers_found=n_known,
        entries=entries,
    )
    header = (
        "# Generated by `python -m vsc_ocr toc`. Check against the scan before use.\n"
        "# printed_page = number printed in the mục lục; pdf_page = page in the source PDF\n"
        "# (estimated from printed page numbers detected on nearby pages).\n"
        "# work = id of the matching work in structure.yaml, if any.\n"
    )
    write_yaml(book.dir / "toc.generated.yaml", out, header)
    print(f"  mục lục on page(s) {to_ranges(toc_pages)}: {len(entries)} entries, "
          f"{matched} matched to works -> {book.id}/toc.generated.yaml")
