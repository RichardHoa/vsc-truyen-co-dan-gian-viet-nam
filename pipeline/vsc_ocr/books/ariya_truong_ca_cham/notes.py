"""Chú thích: split each notes block into notes and tie every note to the
call in the body that points to it.

A block starts with a row reading "Chú thích:" and runs until the next
section or heading. Each note starts with "(N)"; rows that don't are the
note carrying on (also across a page break). Numbering restarts per block, so
a note is identified by (scope, number). Scopes come from assemble.yaml
(`notes.scopes`, page ranges); a block outside them is named after its section.

Calls are found in the scope's body text before the block:
  - "(6)" at full size, or a superscript OCR kept: "cùng(6)", "cùng6", "cùng(6";
  - superscripts OCR turned into junk ("chệ®)", "chệs)", "cùng°") are only
    candidates, never calls on their own.
Calls run 1, 2, 3... in reading order, so the calls are the longest
increasing run of numbered candidates; numbers that break it ("(câu 189)",
list items) are not calls. A note left without a call is looked for in the
stretch between its neighbours' calls: first the other engine's text and the
alternatives in merged/pNNNN.json, then a junk candidate when it is the only
one in the stretch, then a high-resolution re-read of that stretch. A call
that can't be placed stays `unresolved`; nothing is placed by guesswork.
"""

from __future__ import annotations

import difflib
import re

from .booktoc import Stream, norm, walk
from ...layout import v_overlap
from ...common import Book, from_ranges, read_json, slugify
from .superscript import raised_marks

_block_title = re.compile(r"^\W*ch[uú]\s*th[ií]ch\W*$", re.IGNORECASE)
_note_start = re.compile(r"^\W{0,3}\(\s*([0-9lLIi|!¡]{0,3})\s*\)\s*")
_digits = str.maketrans({"l": "1", "L": "1", "I": "1", "i": "1", "|": "1", "!": "1", "¡": "1"})

# calls in body text; group "n" is the number, the match is what OCR printed
_call_clean = re.compile(r"\((?P<n>[1-9]\d?)\)")
_call_glued = re.compile(r"(?<=[^\W\d_]{2})(?:\((?P<n>[1-9]\d?)(?!\d)\)?|(?P<g>[1-9]\d?)(?=[.,;:!?…]|\s|$))")
# what a superscript call often turns into: quote marks, degree signs, ®...
_call_junk = re.compile(r"(?<=[^\W\d_])\s?(?P<j>\(”\)|s\)|®\)|[\"'”“’°®*%^?]{1,3})(?=[\s.,;:!?…)]|$)")
RERENDER_DPI = 600

_strong_junk = re.compile(r"[°®*%^]|..")  # one plain quote mark alone is most likely a quote

def _number(tok: str) -> int | None:
    t = tok.translate(_digits)
    return int(t) if t.isdigit() else None


def _is_block_title(text: str) -> bool:
    return bool(_block_title.match(text.strip())) or norm(text) == "chuthich"


# ---------------------------------------------------------------- blocks

def find_blocks(stream: Stream, cuts: set) -> list[dict]:
    """[{'start': (page, i), 'notes': [{number, ocr_number, text, pages, pos}]}]"""
    blocks = []
    flat = [(n, i, s) for n in stream.order for i, s in enumerate(stream.segments(n))]
    k = 0
    while k < len(flat):
        n, i, s = flat[k]
        if not _is_block_title(s["text"]):
            k += 1
            continue
        block = dict(start=(n, i), end=(n, i), notes=[])
        k += 1
        while k < len(flat):
            n2, i2, s2 = flat[k]
            if (n2, i2) in cuts or s2["kind"] == "heading" or _is_block_title(s2["text"]):
                break
            m = _note_start.match(s2["text"])
            if m:
                block["notes"].append(dict(ocr_number=m.group(1), text=s2["text"][m.end():].strip(),
                                           pages=[n2], pos=[(n2, i2)], flags=list(s2.get("flags", []))))
            elif block["notes"]:
                note = block["notes"][-1]  # the note carries on (wrapped, or over a page break)
                note["text"] += " " + s2["text"].strip()
                if n2 not in note["pages"]:
                    note["pages"].append(n2)
                note["pos"].append((n2, i2))
                note["flags"] = sorted(set(note["flags"]) | set(s2.get("flags", [])))
            else:
                break
            block["end"] = (n2, i2)
            k += 1
        _number_notes(block)
        blocks.append(block)
    return blocks


def _number_notes(block: dict) -> None:
    """Notes run 1, 2, 3...: take the printed number when it fits, else the
    next in sequence (OCR reads "(1)" as "(L)", "(5)" as "()")."""
    expected = 1
    for note in block["notes"]:
        read = _number(note["ocr_number"])
        note["number"] = expected
        if read != expected:
            note["number_fixed"] = True
        expected += 1


# ---------------------------------------------------------------- calls

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


def _candidates(book: Book, stream: Stream, positions: list[tuple[int, int]], marks) -> list[dict]:
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


def _best_run(cands: list[dict], max_number: int) -> list[dict]:
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


def _sentence(text: str, start: int, end: int) -> str:
    """The sentence around a call, with the call left out."""
    a = max((text.rfind(p, 0, start) for p in (". ", "! ", "? ", "… ")), default=-1)
    a = a + 2 if a >= 0 else 0
    b_candidates = [text.find(p, end) for p in (".", "!", "?", "…")]
    b_candidates = [b for b in b_candidates if b >= 0]
    b = min(b_candidates) + 1 if b_candidates else len(text)
    return (text[a:start] + text[end:b]).strip()


def _word_before(text: str, start: int) -> str:
    m = re.search(r"(\S+)\s*$", text[:start])
    return m.group(1) if m else ""


class Marks:
    """Raised marks per row, from the page re-rendered at RERENDER_DPI."""

    def __init__(self, book: Book, dpi: int = RERENDER_DPI):
        self.book, self.dpi, self.pages, self.rows_seen = book, dpi, {}, 0

    def image(self, n: int):
        if n not in self.pages:
            import pypdfium2 as pdfium
            pdf, idx = self.book.source_of(n)
            doc = pdfium.PdfDocument(str(pdf))
            try:
                self.pages = {n: doc[idx].render(scale=self.dpi / 72, grayscale=True).to_pil()}
            finally:
                doc.close()
        return self.pages[n]

    def __call__(self, n: int, row: dict) -> list[float]:
        self.rows_seen += 1
        return raised_marks(self.image(n), row["bbox"])


_headword = re.compile(r"^(?P<w>[^\W\d_][^:;,.()]{0,30}?)\s*:\s")
_verse_ref = re.compile(r"^C[âa]u\s+(?P<a>\d{1,3})(?:\s*[-–]\s*(?P<b>\d{1,3}))?\b")


def _evidence(stream: Stream, block: dict, cands: list[dict]) -> list[dict]:
    """Calls a note's own text points to. Many notes start with the word they
    explain ("(2) Kawei: tên cũ của làng...") and the call follows that word in
    the body; others name the verse ("(5) Câu 29-30 có lối nói...") and the
    call is in that verse. When exactly one junk candidate sits there, it is
    that note's call (status `recovered`)."""
    out = []
    for note in block["notes"]:
        k = note["number"]
        hits, how = [], None
        m = _headword.match(note["text"])
        if m and 1 <= len(m.group("w").split()) <= 3:
            key = norm(m.group("w"))
            for c in cands:
                if c["kind"] != "junk" or len(key) < 3:
                    continue
                text = stream.segments(c["pos"][0])[c["pos"][1]]["text"]
                before = norm(text[max(0, c["start"] - len(m.group("w")) - 2):c["start"]])
                if before.endswith(key) or (len(key) >= 5 and _ratio(before[-len(key):], key) >= 0.8):
                    hits.append(c)
            how = f"the note explains '{m.group('w')}'; the only junk mark after that word"
        v = _verse_ref.match(note["text"])
        if not hits and v:
            a, b = int(v.group("a")), int(v.group("b") or v.group("a"))
            couplets = _couplet_ranges(stream)
            spots = [p for p, num in couplets.items() if a <= num <= b]
            hits = [c for c in cands if c["kind"] == "junk" and c["pos"] in spots]
            how = f"the note is about verse {a}{'-' + str(b) if b != a else ''}; the only junk mark in it"
        if len(hits) == 1:
            out.append(dict(hits[0], kind="verse" if not m or not how.startswith("the note explains") else "headword",
                            number=k, how=how + f": '{hits[0]['raw'].strip()}'"))
    return out


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def _couplet_ranges(stream: Stream) -> dict:
    """(page, i) -> couplet number, for numbered verse ("29. ..." and the
    unnumbered lines after it)."""
    out, current = {}, None
    for n in stream.order:
        for i, s in enumerate(stream.segments(n)):
            if s["kind"] == "verse":
                if s.get("line_no"):
                    current = s["line_no"]
                if current is not None:
                    out[(n, i)] = current
    return out


def _fill_gap(gap_cands: list[dict], missing: int) -> list[dict] | None:
    """Candidates for the `missing` calls of a gap, in order, or None when
    the evidence doesn't single them out."""
    if missing <= 0:
        return None
    # only marks seen on the scan count: OCR junk alone can be anything
    pool = [c for c in gap_cands if c["kind"] in ("junk", "mark") and c.get("confirmed")]
    return pool if len(pool) == missing else None


def resolve(book: Book, stream: Stream, root: dict, cfg: dict, rerender: bool = True):
    """Returns (notes, calls, blocks); calls maps (page, i) -> [(start, end, note id)]."""
    cuts = {e["_pos"] for e in walk(root) if e.get("_pos")}
    blocks = find_blocks(stream, cuts)
    scopes_cfg = (cfg.get("notes") or {}).get("scopes") or []
    parse_pages = _parse_pages(root, stream)
    marks = Marks(book) if rerender else (lambda n, row: [])
    notes_out, calls = [], {}
    used_ids: set = set()
    for block in blocks:
        bpage = block["start"][0]
        sc = next((s for s in scopes_cfg if bpage in from_ranges(s["pages"])), None)
        if sc:
            scope, scope_pages = sc["id"], set(from_ranges(sc["pages"]))
        else:
            owner = max((e for e in walk(root) if e.get("pdf_start") and e["pdf_start"] <= bpage <= e["pdf_end"]
                         and e.get("level", 0) > 0), key=lambda e: e["level"], default=root)
            scope = slugify(owner["title"]) or "notes"
            scope_pages = set(range(owner.get("pdf_start") or bpage, bpage + 1))
        while scope in used_ids:
            scope += "-2"
        used_ids.add(scope)
        block["scope"] = scope

        body = [(n, i) for n in stream.order if n in scope_pages and n in parse_pages
                for i, s in enumerate(stream.segments(n))
                if (n, i) < block["start"] and s["kind"] not in ("footnote", "line_number", "heading")
                and not _in_other_block(blocks, block, (n, i))]
        cands = _candidates(book, stream, body, marks)
        total = len(block["notes"])
        # a full-size number repeated in the body ("địa danh (2)" in a list)
        # is an annotation, not a call: calls are unique in a scope
        clean_nums = [c["number"] for c in cands if c["kind"] == "clean"]
        cands = [c for c in cands if not (c["kind"] == "clean" and clean_nums.count(c["number"]) > 1)]
        cands += _evidence(stream, block, cands)
        run = _best_run(cands, total)
        placed = {c["number"]: (c, "resolved") for c in run}

        # gaps in the run: between two calls found (or the start / the block)
        anchors = [(0, None)] + [(c["number"], c) for c in run] + [(total + 1, None)]
        for (na, ca), (nb, cb) in zip(anchors, anchors[1:]):
            missing = nb - na - 1
            if missing <= 0:
                continue
            lo = (ca["pos"], ca["end"]) if ca else ((0, 0), 0)
            hi = (cb["pos"], cb["start"]) if cb else (block["start"], 0)
            inside = [c for c in cands if c not in run and lo <= (c["pos"], c["start"]) < hi]
            fill = _fill_gap(inside, missing)
            if fill:
                for k, c in zip(range(na + 1, nb), fill):
                    c = dict(c, number=k, gap=(na, nb))
                    placed[k] = (c, "recovered")
            block.setdefault("gaps", []).append(dict(after=na, before=nb, missing=missing, filled=bool(fill),
                                                     candidates=len(inside)))

        for note in block["notes"]:
            k = note["number"]
            nid = f"{scope}-{k}"
            entry = dict(id=nid, scope=scope, number=k, text=note["text"], note_pdf_pages=note["pages"])
            if note.get("number_fixed"):
                entry["ocr_number"] = note["ocr_number"]
            if note.get("flags"):
                entry["flags"] = note["flags"]
            if k in placed:
                c, status = placed[k]
                text = stream.segments(c["pos"][0])[c["pos"][1]]["text"]
                if c["kind"] in ("headword", "verse"):
                    status = "recovered"
                    how = c["how"]
                elif status == "resolved":
                    how = {"clean": "full size", "glued": "superscript, read by OCR",
                           "secondary": "superscript, read by the other engine / an alternative reading"}[c["kind"]]
                else:
                    a, b = c["gap"]
                    what = f"OCR junk '{c['raw'].strip()}' at" if c["raw"].strip() else "nothing in the OCR text, but"
                    how = (f"sequence gap between calls {a or 'start'} and {b if b <= total else 'end'}: "
                           f"{what} a raised mark on the scan")
                entry["call"] = dict(pdf_page=c["pos"][0], sentence=_sentence(text, c["start"], c["end"]),
                                     ocr_raw=(_word_before(text, c["start"]) + c["raw"]).strip(), how=how)
                calls.setdefault(c["pos"], []).append((c["start"], c["end"], nid))
            else:
                status = "unresolved"
                entry["call"] = None
                prev = max((x for x in placed if x < k), default=None)
                nxt = min((x for x in placed if x > k), default=None)
                entry["call_between"] = dict(
                    after_call=prev, before_call=nxt,
                    pdf_pages=_pages_between(placed.get(prev), placed.get(nxt), body, block))
            entry["status"] = status
            notes_out.append(entry)
    return notes_out, calls, blocks


def _pages_between(a, b, body, block) -> list[int]:
    lo = a[0]["pos"] if a else body[0] if body else block["start"]
    hi = b[0]["pos"] if b else block["start"]
    return sorted({n for n, _ in body if lo[0] <= n <= hi[0]})


def _in_other_block(blocks, block, pos) -> bool:
    return any(b is not block and b["start"] <= pos <= b["end"] for b in blocks)


def _parse_pages(root: dict, stream: Stream) -> set:
    """Pages of parsed entries, less the pages of entries left out."""
    keep, drop = set(), set()
    for e in walk(root):
        if e.get("pdf_start"):
            (keep if e.get("parse") else drop).update(range(e["pdf_start"], e["pdf_end"] + 1))
    return (keep - drop) & set(stream.order)
