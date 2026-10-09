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
from ...common import Book, from_ranges, slugify
from ...notecalls import best_run as _best_run, candidates as _candidates, fill_gap as _fill_gap
from ...notecalls import sentence as _sentence, word_before as _word_before
from ...superscript import Marks

_block_title = re.compile(r"^\W*ch[uú]\s*th[ií]ch\W*$", re.IGNORECASE)
_note_start = re.compile(r"^\W{0,3}\(\s*([0-9lLIi|!¡]{0,3})\s*\)\s*")
_digits = str.maketrans({"l": "1", "L": "1", "I": "1", "i": "1", "|": "1", "!": "1", "¡": "1"})


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
        hits, kind = [], None
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
            kind = "headword"
        v = _verse_ref.match(note["text"])
        if not hits and v:
            a, b = int(v.group("a")), int(v.group("b") or v.group("a"))
            couplets = _couplet_ranges(stream)
            spots = [p for p, num in couplets.items() if a <= num <= b]
            hits = [c for c in cands if c["kind"] == "junk" and c["pos"] in spots]
            kind = "verse"
        if len(hits) == 1:
            out.append(dict(hits[0], kind=kind, number=k))
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
                entry["call"] = dict(pdf_page=c["pos"][0], sentence=_sentence(text, c["start"], c["end"]),
                                     ocr_raw=(_word_before(text, c["start"]) + c["raw"]).strip())
                calls.setdefault(c["pos"], []).append((c["start"], c["end"], nid))
            else:
                status = "unresolved"
                entry["call"] = None
            entry["status"] = status
            notes_out.append(entry)
    return notes_out, calls, blocks


def _in_other_block(blocks, block, pos) -> bool:
    return any(b is not block and b["start"] <= pos <= b["end"] for b in blocks)


def _parse_pages(root: dict, stream: Stream) -> set:
    """Pages of parsed entries, less the pages of entries left out."""
    keep, drop = set(), set()
    for e in walk(root):
        if e.get("pdf_start"):
            (keep if e.get("parse") else drop).update(range(e["pdf_start"], e["pdf_end"] + 1))
    return (keep - drop) & set(stream.order)
