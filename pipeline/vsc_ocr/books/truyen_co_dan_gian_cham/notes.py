"""Footnotes: each page's notes (below the rule, see `clean`) and the call in
the page's body or heading that points to each one.

Numbering restarts on every page, so a note is (page, marker): "(1)", "(2)"...
or "(*)". Its id is `<section id>-p<pdf>-<n>` (`-star` for "(*)").

Calls are looked for on the same page only, with the shared `notecalls`:
full-size or glued numbers OCR kept ("thịt(1", "pu1"), the other engine and
the alternatives, and junk OCR made of a superscript ("®", "s)", "”"), checked
against raised marks on a 600 dpi render. Calls on a page run 1, 2... in
reading order, so the longest increasing run of numbered candidates are the
calls; a number that breaks it ("(trang 63)") isn't one. A note left without
a call takes the one raised mark (or confirmed junk) in the stretch between
its neighbours' calls, or anywhere on the page when it is the page's only
note (`recovered`); otherwise it stays `unresolved`. Nothing is placed by
guesswork.
"""

from __future__ import annotations

import re

from ...common import Book
from ...notecalls import best_run, candidates, sentence, word_before
from ...stream import Stream
from ...superscript import Marks

_digits = str.maketrans({"l": "1", "L": "1", "I": "1", "i": "1", "|": "1", "!": "1", "¡": "1"})
_star = set("*°+xX")
# the marker at the start of a note, as clean found it
_marker = re.compile(r"^[^\w(]{0,2}(?:[(\[{]\s*[^\s)\]}]{1,2}\s*[)\]}]?\s*|\S{1,2}\)\s+)")
_head_junk = re.compile(r"\s?(?P<j>\(\w?|\w?\))\W*$")
_star_junk = re.compile(r"(?<=\S)\s?(?P<j>\(?[*°+”\"'’]\)?)(?=[\s.,;:!?…]|$)")

HOW = {"clean": "full-size number in the OCR text", "glued": "superscript, read by OCR",
       "secondary": "superscript, read by the other engine / an alternative reading",
       "junk": "OCR junk on a raised mark", "mark": "raised mark on the 600 dpi scan, nothing in the OCR text",
       "star": "OCR junk where the (*) is printed"}


def page_notes(segs: list[dict]) -> list[dict]:
    """The page's footnote segments -> notes with their marker."""
    notes, k = [], 0
    for i, s in enumerate(segs):
        if s["kind"] != "footnote":
            continue
        raw = s.get("marker_raw")
        m = _marker.match(s["text"])
        text = s["text"][m.end():].strip() if m else s["text"].strip()
        star = bool(raw) and raw in _star
        note = dict(index=i, text=text, raw=raw, flags=list(s.get("flags", [])))
        if star:
            note["marker"] = "*"
        else:
            k += 1
            note["marker"] = str(k)
            read = (raw or "").translate(_digits)
            if read != str(k):
                note["marker_fixed"] = True   # "(L)", "Œ)" or nothing read: the sequence decides
        notes.append(note)
    return notes


def _heading_junk(segs: list[dict], heads: list, cands: list[dict]) -> list[dict]:
    """A call at the end of a heading that OCR read as a bracket with no
    partner ("BÌLÀ g)", "ĐIÊNG (Đ", "ĐÊU)") is junk standing for the call; it
    replaces any raised mark found at the same place."""
    for p in heads:
        text = segs[p[1]]["text"].rstrip()
        m = _head_junk.search(text)
        if not m or text.count("(") == text.count(")"):
            continue
        cands = [c for c in cands if not (c["pos"] == p and c["start"] >= m.start("j") - 1)]
        cands.append(dict(pos=p, start=m.start("j"), end=m.end("j"), kind="junk", number=None,
                          raw=m.group("j"), confirmed=True))
    return sorted(cands, key=lambda c: (c["pos"], c["start"]))


def resolve(book: Book, stream: Stream, owner_of, heading_at: set, rerender: bool = True):
    """Returns (notes, calls): calls maps (page, i) -> [(start, end, note id)].
    `owner_of(page)` is the section id; heading_at holds the heading segments."""
    marks = Marks(book) if rerender else (lambda n, row: [])
    notes_out, calls = [], {}
    for n in stream.order:
        segs = stream.segments(n)
        notes = page_notes(segs)
        if not notes:
            continue
        scope = owner_of(n)
        body = [(n, i) for i, s in enumerate(segs) if s["kind"] in ("paragraph", "heading", "verse")]
        cands = candidates(book, stream, body, marks) if body else []
        cands = _heading_junk(segs, [p for p in body if p in heading_at], cands)
        numbered = [x for x in notes if x["marker"] != "*"]
        run = best_run(cands, len(numbered))
        placed = {str(c["number"]): (c, "resolved") for c in run}
        free = [c for c in cands if c not in run and c["kind"] in ("junk", "mark") and c.get("confirmed")]

        # gaps in the run: the only confirmed mark between two calls
        anchors = [(0, None)] + [(c["number"], c) for c in run] + [(len(numbered) + 1, None)]
        for (na, ca), (nb, cb) in zip(anchors, anchors[1:]):
            missing = nb - na - 1
            if missing <= 0:
                continue
            lo = (ca["pos"], ca["end"]) if ca else ((0, 0), 0)
            hi = (cb["pos"], cb["start"]) if cb else ((n + 1, 0), 0)
            pool = [c for c in free if lo <= (c["pos"], c["start"]) < hi]
            if len(pool) == missing:
                for k, c in zip(range(na + 1, nb), pool):
                    how = f"{HOW[c['kind']]}; the only one between calls {na or 'start'} and " \
                          f"{nb if nb <= len(numbered) else 'end'}"
                    placed[str(k)] = (dict(c, how=how), "recovered")
                    free.remove(c)

        # the (*) note: a star-like mark OCR kept, else the one mark left on the page
        if any(x["marker"] == "*" for x in notes):
            stars = []
            for p in body:
                text = segs[p[1]]["text"]
                for m in _star_junk.finditer(text):
                    stars.append(dict(pos=p, start=m.start("j"), end=m.end("j"), kind="star", number=None,
                                      raw=m.group("j")))
            if len(stars) == 1:
                placed["*"] = (dict(stars[0], how=HOW["star"]), "recovered")
            elif len(free) == 1:
                placed["*"] = (dict(free[0], how=HOW[free[0]["kind"]] + "; the only one on the page"), "recovered")

        for note in notes:
            mk = note["marker"]
            nid = f"{scope}-p{n}-{'star' if mk == '*' else mk}"
            entry = dict(id=nid, scope=scope, page=n, marker=mk, text=note["text"], note_pdf_pages=[n])
            if note.get("marker_fixed"):
                entry["ocr_marker"] = note["raw"]
            if note["flags"]:
                entry["flags"] = note["flags"]
            if mk in placed:
                c, status = placed[mk]
                seg = segs[c["pos"][1]]
                text = seg["text"]
                entry["call"] = dict(pdf_page=n, **{"in": "heading" if c["pos"] in heading_at else "body"},
                                     sentence=sentence(text, c["start"], c["end"]),
                                     ocr_raw=(word_before(text, c["start"]) + text[c["start"]:c["end"]]).strip(),
                                     how=c.get("how") or HOW[c["kind"]])
                calls.setdefault(c["pos"], []).append((c["start"], c["end"], nid))
            else:
                status = "unresolved"
                entry["call"] = None
            entry["status"] = status
            notes_out.append(entry)
    return notes_out, calls
