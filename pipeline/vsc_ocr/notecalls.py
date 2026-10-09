"""Note calls in body text: where a footnote's call ("vô cùng⁽⁶⁾") sits.

OCR reads a call as "(6)" at full size, keeps a superscript glued to its word
("cùng(6)", "cùng6", "cùng(6"), or turns it into junk ("chệ®)", "cùng°").
`candidates` lists every such place in a stretch of segments (junk only as a
candidate, never as a call on its own), adding what the other engine or the
alternatives read and the raised marks found on the scan. Calls run 1, 2, 3...
in reading order, so `best_run` keeps the longest increasing run of numbered
candidates. Moved here from Ariya's notes.py so every book can use it.
"""

from __future__ import annotations

import re

from .common import Book, read_json
from .layout import v_overlap
from .stream import Stream

# calls in body text; group "n" is the number, the match is what OCR printed
_call_clean = re.compile(r"\((?P<n>[1-9]\d?)\)")
_call_glued = re.compile(r"(?<=[^\W\d_]{2})(?:\((?P<n>[1-9]\d?)(?!\d)\)?|(?P<g>[1-9]\d?)(?=[.,;:!?…]|\s|$))")
# what a superscript call often turns into: quote marks, degree signs, ®...
_call_junk = re.compile(r"(?<=[^\W\d_])\s?(?P<j>\(”\)|s\)|®\)|[\"'”“’°®*%^?]{1,3})(?=[\s.,;:!?…)]|$)")

_strong_junk = re.compile(r"[°®*%^]|..")  # one plain quote mark alone is most likely a quote


def _row_spans(text: str, rows: list[dict]) -> list[tuple[int, int, dict]]:
    """Where each OCR row of a segment sits in the segment's text."""
    spans, at = [], 0
    for r in rows:
        t = " ".join(r["text"].split())
        k = text.find(t, at) if t else -1
        if k < 0:
            continue
        spans.append((k, k + len(t), r))
        at = k + len(t)
    return spans


def _segment_rows(book: Book, stream: Stream, cache: dict, n: int, i: int):
    """The merged OCR rows that make up segment i of page n, with their spans."""
    if n not in cache:
        mp = book.merged_path(n)
        cache[n] = read_json(mp)["rows"] if mp.exists() else []
    seg = stream.segments(n)[i]
    rows = [r for r in cache[n] if v_overlap(r["bbox"], seg["bbox"]) >= 0.5
            and r["bbox"][1] >= seg["bbox"][1] - 0.005 and r["bbox"][3] <= seg["bbox"][3] + 0.005]
    return _row_spans(seg["text"], rows)


def _word_end_near(text: str, a: int, b: int, x: float) -> int | None:
    """The end of the word closest to fraction x of the row text[a:b]."""
    want = a + x * (b - a)
    ends = [m.end() for m in re.finditer(r"[^\W\d_]+", text[a:b])]
    if not ends:
        return None
    return a + min(ends, key=lambda e: abs(a + e - want))


def _is_closing_quote(text: str, start: int, mark: str) -> bool:
    before = text[:start]
    if mark == '"':
        return before.count('"') % 2 == 1
    if mark == "”":
        return before.rfind("“") > before.rfind("”")
    if mark == "’" or mark == "'":
        return before.rfind("‘") > before.rfind("’")
    return False


def candidates(book: Book, stream: Stream, positions: list[tuple[int, int]], marks) -> list[dict]:
    """Every place in the body that may be a call. `marks(n, row)` gives the
    raised marks seen on the scan in that row (fractions of its width)."""
    out = []
    rows_cache: dict = {}
    for n, i in positions:
        text = stream.segments(n)[i]["text"]
        spans = []
        found = []
        for kind, rx in (("clean", _call_clean), ("glued", _call_glued), ("junk", _call_junk)):
            for m in rx.finditer(text):
                if any(a < m.end() and m.start() < b for a, b in spans):
                    continue
                c = dict(pos=(n, i), start=m.start(), end=m.end(), kind=kind, number=None)
                if kind == "junk":
                    j = m.group("j")
                    if len(j) == 1 and j in "?" or _is_closing_quote(text, m.start("j"), j):
                        continue
                    c["start"] = m.start("j") if not text[m.start():m.start("j")].strip() else m.start()
                    c["strong"] = bool(_strong_junk.search(j))
                else:
                    c["number"] = int(m.group("n") or m.group("g"))
                    w0 = text.rfind(" ", 0, m.start()) + 1
                    if kind == "glued" and text[w0:w0 + 1] == "(":
                        continue  # "(câu14?7)": a reference inside brackets, not a call
                    if kind == "clean" and m.start() > 0 and text[m.start() - 1].isalpha():
                        c["kind"] = "glued"  # "cùng(6)": a superscript OCR kept
                c["raw"] = text[c["start"]:c["end"]]
                spans.append((m.start(), m.end()))
                found.append(c)
        # the other engine and the alternatives may have kept a call this one lost
        row_spans = _segment_rows(book, stream, rows_cache, n, i)
        for a, b, row in row_spans:
            readings = [row["secondary"]] if row.get("secondary") and row["secondary"] != row["text"] else []
            readings += [x if isinstance(x, str) else x.get("text", "") for x in row.get("alternatives", [])]
            for txt in readings:
                for m in re.finditer(r"(?P<w>[^\W\d_]{2,})\s?\((?P<n>[1-9]\d?)\)", txt):
                    w = m.group("w")
                    hits = [k.end() for k in re.finditer(re.escape(w), text[a:b])]
                    if len(hits) == 1 and not any(x["start"] <= a + hits[0] <= x["end"] for x in found):
                        found.append(dict(pos=(n, i), start=a + hits[0], end=a + hits[0], kind="secondary",
                                          number=int(m.group("n")), raw="", word=w))
        # raised marks on the scan confirm junk candidates; a mark with no
        # junk near it is a call OCR dropped entirely
        for a, b, row in row_spans:
            xs = marks(n, row)
            if not xs:
                continue
            here = [c for c in found if a <= c["start"] <= b + 1]
            for x in xs:
                near = [c for c in here if abs((c["start"] - a) / max(1, b - a) - x) <= 0.12]
                for c in near:
                    if c["kind"] == "junk":
                        c["confirmed"] = True
                if not near:
                    at = _word_end_near(text, a, b, x)
                    if at is not None:
                        found.append(dict(pos=(n, i), start=at, end=at, kind="mark", number=None,
                                          raw="", confirmed=True))
        out.extend(found)
    out.sort(key=lambda c: (c["pos"], c["start"]))
    return out


def best_run(cands: list[dict], max_number: int) -> list[dict]:
    """Longest run of numbered candidates whose numbers increase in reading
    order (weighted: a full-size "(6)" counts more than a glued "6")."""
    nums = [c for c in cands if c["number"] is not None and 1 <= c["number"] <= max_number]
    if not nums:
        return []
    w = [{"clean": 2.0, "secondary": 1.5, "headword": 1.5, "verse": 1.5}.get(c["kind"], 1.0) for c in nums]
    best = list(w)
    back = [-1] * len(nums)
    for j in range(len(nums)):
        for i in range(j):
            if nums[i]["number"] < nums[j]["number"] and best[i] + w[j] > best[j]:
                best[j], back[j] = best[i] + w[j], i
    j = max(range(len(nums)), key=lambda x: best[x])
    run = []
    while j != -1:
        run.append(nums[j])
        j = back[j]
    return run[::-1]


def sentence(text: str, start: int, end: int) -> str:
    """The sentence around a call, with the call left out."""
    a = max((text.rfind(p, 0, start) for p in (". ", "! ", "? ", "… ")), default=-1)
    a = a + 2 if a >= 0 else 0
    b_candidates = [text.find(p, end) for p in (".", "!", "?", "…")]
    b_candidates = [b for b in b_candidates if b >= 0]
    b = min(b_candidates) + 1 if b_candidates else len(text)
    return (text[a:start] + text[end:b]).strip()


def word_before(text: str, start: int) -> str:
    m = re.search(r"(\S+)\s*$", text[:start])
    return m.group(1) if m else ""


def fill_gap(gap_cands: list[dict], missing: int) -> list[dict] | None:
    """Candidates for the `missing` calls of a gap, in order, or None when
    the evidence doesn't single them out."""
    if missing <= 0:
        return None
    # only marks seen on the scan count: OCR junk alone can be anything
    pool = [c for c in gap_cands if c["kind"] in ("junk", "mark") and c.get("confirmed")]
    return pool if len(pool) == missing else None
