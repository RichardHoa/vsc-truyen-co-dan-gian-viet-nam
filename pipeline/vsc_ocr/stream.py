"""A book's cleaned pages as one stream of segments, and finding a mục lục
title among them. Moved here from Ariya's booktoc.py so every book can use it."""

from __future__ import annotations

import difflib
import re

from .common import Book, from_ranges, nfc, read_json, strip_diacritics


def norm(s: str) -> str:
    """Comparison key: no diacritics, case, punctuation or spaces."""
    return re.sub(r"[^a-z0-9]", "", strip_diacritics(nfc(s)).casefold())


def similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, norm(a), norm(b), autojunk=False).ratio()


class Stream:
    """The cleaned segments of the book's text pages, in reading order."""

    def __init__(self, book: Book, cfg: dict):
        self.book = book
        skip = set(from_ranges(cfg.get("skip_pages")))
        end = int(cfg.get("end_page") or book.page_count)
        self.pages: dict[int, dict] = {}
        for n in range(1, end + 1):
            p = book.page_path(n)
            if n not in skip and p.exists():
                self.pages[n] = read_json(p)
        self.order = sorted(self.pages)

    def segments(self, n: int) -> list[dict]:
        return self.pages[n]["segments"] if n in self.pages else []


LEAD_MARKER = re.compile(r"^\W*([A-ZĐa-zđ]|[IVXÏÌlL|]{1,4}|\d{1,3})\s*[.,:)]\s*")


def heading_score(title: str, text: str) -> float:
    """How well a body row matches a mục lục title (markers ignored)."""
    t = norm(LEAD_MARKER.sub("", title.lstrip("-* ")))
    s = norm(LEAD_MARKER.sub("", text))
    if not t or not s:
        return 0.0
    if len(s) > 1.6 * len(t) + 12:
        s = s[: len(t)]  # a heading glued to the start of its paragraph
    score = difflib.SequenceMatcher(None, t, s, autojunk=False).ratio()
    if len(s) < len(t) and len(s) >= max(8, 0.35 * len(t)):
        # a long heading wrapped onto a second row: compare the first part
        score = max(score, difflib.SequenceMatcher(None, t[: len(s)], s, autojunk=False).ratio())
    return score


def find_heading(stream: Stream, title: str, pages, after=None, threshold=0.8):
    """Best (page, segment index) for a title on the given pages, after `after`."""
    best, best_score = None, threshold
    for n in pages:
        for i, s in enumerate(stream.segments(n)):
            if after is not None and (n, i) <= after:
                continue
            if s["kind"] in ("footnote", "line_number"):
                continue
            score = heading_score(title, s["text"])
            if s["kind"] == "heading":
                score += 0.05
            if score > best_score:
                best, best_score = (n, i), score
    return best
