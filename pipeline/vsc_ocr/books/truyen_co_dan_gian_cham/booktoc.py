"""toc.json: the mục lục (toc.generated.yaml) with each entry's PDF range,
its heading as printed on its first page, and the structure.yaml work it is.

  - Rows and works are matched by order (both hold the 58 stories in the same
    order), never by title: the three spellings differ ("Ta Pa Nrang",
    "JÀ PA NRANG", "Jà Pang Nrang"), and all three are kept.
  - `pdf_start` is the row's printed page through the printed page numbers
    found on the pages; `pdf_end` is the page before the next entry.
  - The heading is the centred rows at the top of the first page: a title,
    and a subtitle when a row is in parentheses ("PÔ RI YAK" / "(Thần sóng)").
  - Every disagreement (page or title) between the mục lục, the heading and
    structure.yaml is listed in `disagreements`, never resolved silently.
"""

from __future__ import annotations

import difflib
import re

from ...common import Book, from_ranges, nfc, read_yaml, strip_diacritics
from ...stream import Stream, heading_score, similar

_stray = re.compile(r"(?<!\S)[^\w\s(]+(?=\w)|(?<=[\s\w])J(?=[a-zđ])")
_junk_tail = re.compile(r"(\s+[^\w\s()]+)+$")
_edge_punct = " .,:;'\"“”‘’`_-–—|"


def toc_title(raw: str, stray: bool) -> tuple[str, str | None]:
    """The mục lục row's title, without OCR specks at its end and, on the rows
    with a stray printing mark, without the mark ("Chàng Jkhổ")."""
    t = _junk_tail.sub("", raw).strip()
    removed = None
    if stray:
        m = _stray.search(t)
        if m:
            removed = m.group(0)
            t = t[:m.start()] + t[m.end():]
    return t, removed


def _caps(t: str) -> bool:
    letters = [c for c in t if c.isalpha()]
    return bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.6


def page_heading(stream: Stream, n: int) -> tuple[list[int], list[str]]:
    """The heading rows at the top of page n: (segment indexes, texts). The
    title is in capitals; a row after it in parentheses or in lower case is
    its subtitle."""
    idx, texts = [], []
    for i, s in enumerate(stream.segments(n)):
        t = s["text"].strip(_edge_punct)
        if s["kind"] != "heading" or not (_caps(t) or (idx and len(idx) < 3 and ("(" in t or ")" in t))):
            break
        idx.append(i)
        texts.append(s["text"])
    return idx, texts


def split_heading(texts: list[str]) -> tuple[str, str | None]:
    """Heading rows -> (title, subtitle). The subtitle is the part in
    parentheses ("PÔ RI YAK" / "(Thần sóng)", "JA PA-OK (Cậu Xoài)"), or a
    row after the title not in capitals ("đà ri Băh)" read for "(Jà ri Băh)");
    it is kept without the parentheses."""
    title, sub = [], []
    for t in texts:
        t = t.strip(_edge_punct)
        head, paren, rest = t.partition(" (")
        if title or sub:
            if sub or t.startswith("(") or not _caps(t):
                sub.append(t)
                continue
        if paren:
            title.append(head)
            sub.append("(" + rest)
        elif t.startswith("(") and title:
            sub.append(t)
        else:
            title.append(t)
    subtitle = " ".join(sub).strip("() ") or None
    return " ".join(title).strip(_edge_punct), subtitle


def _letters(s: str) -> list[tuple[int, str]]:
    return [(i, strip_diacritics(c).casefold()) for i, c in enumerate(s) if c.isalpha()]


def recase(printed: str, model: str) -> str:
    """The printed (upper-case) heading in the casing of the mục lục row: each
    letter is lower case unless the matching letter of `model` is a capital.
    The spelling stays the heading's ("HOÀNG TỬ TỀWA MỪNÔ" with the model
    "Hoàng tử Tề Wa Mừ Nô" -> "Hoàng tử TềWa MừNô")."""
    if not any(c.islower() for c in model):
        model = model.capitalize()
    out = list(printed.lower())
    a, b = _letters(printed), _letters(model)
    sm = difflib.SequenceMatcher(None, [c for _, c in a], [c for _, c in b], autojunk=False)
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            if model[b[blk.b + k][0]].isupper():
                out[a[blk.a + k][0]] = printed[a[blk.a + k][0]].upper()
    # a word the alignment missed ("RÍT" against "Hít"): the model's word in
    # the same place decides
    words, mwords = list(re.finditer(r"\S+", printed)), model.split()
    if len(words) == len(mwords):
        for w, mw in zip(words, mwords):
            k = next((i for i in range(w.start(), w.end()) if out[i].isalpha()), None)
            if k is not None and mw[:1].isupper():
                out[k] = out[k].upper()
    first = next((i for i, c in enumerate(out) if c.isalpha()), None)
    if first is not None:
        out[first] = out[first].upper()
    return nfc("".join(out))


def build(book: Book, stream: Stream, cfg: dict) -> tuple[list[dict], list[str]]:
    gen = read_yaml(book.dir / "toc.generated.yaml")
    rows = gen["entries"]
    works = book.s.get("works", [])
    stray_rows = set(cfg.get("toc_stray_marks") or [])
    end_page = int(cfg.get("end_page") or book.page_count)
    intro = cfg.get("intro") or {}
    problems = list(gen.get("problems") or [])

    entries = []
    for k, r in enumerate(rows):
        e = dict(number=r.get("item"), printed_page=r.get("printed_page"), toc_pdf=r.get("pdf_page"))
        e["toc_title"], removed = toc_title(r["title"], r.get("item") in stray_rows)
        if r.get("item") in stray_rows:
            if removed:
                e["toc_stray_mark"] = removed
            else:
                problems.append(f"row {r['item']}: the stray mark isn't in the OCR text ('{r['title']}')")
        if k == 0:
            e.update(id=intro.get("id", "loi-gioi-thieu"), number=None,
                     structure_title=None, structure_pages=intro.get("pages"))
        else:
            w = works[k - 1] if k - 1 < len(works) else None
            v = (w or {}).get("versions", [{}])[0]
            e.update(id=w["id"] if w else f"entry-{k}", structure_title=w["title"] if w else None,
                     structure_pages=v.get("pages"))
        entries.append(e)

    # pages: from the mục lục, else from structure.yaml
    for e in entries:
        sp = from_ranges(e["structure_pages"])
        e["pdf_start"] = e["toc_pdf"]
        if e["pdf_start"] is None and sp:
            e["pdf_start"] = sp[0]
            problems.append(f"{e['id']}: no page in the mục lục; pdf_start {sp[0]} from structure.yaml")
    # a mục lục page with no heading on it: the story starts where
    # structure.yaml says, if its heading is there
    for e in entries:
        sp = from_ranges(e["structure_pages"])
        if not page_heading(stream, e["pdf_start"])[0] and sp and sp[0] != e["pdf_start"] \
                and page_heading(stream, sp[0])[0]:
            problems.append(f"{e['id']}: no heading on pdf {e['pdf_start']} (mục lục page {e['printed_page']}); "
                            f"the heading is on pdf {sp[0]} as structure.yaml says, so the story starts there")
            e["pdf_start"] = sp[0]
    for k, e in enumerate(entries):
        nxt = next((x["pdf_start"] for x in entries[k + 1:] if x["pdf_start"]), None)
        e["pdf_end"] = (nxt - 1) if nxt else end_page
        if k == 0 and intro.get("pages"):
            e["pdf_end"] = from_ranges(intro["pages"])[-1]   # the page after it is blank
        sp = from_ranges(e["structure_pages"])
        if sp and (sp[0], sp[-1]) != (e["pdf_start"], e["pdf_end"]):
            problems.append(f"{e['id']}: pdf {e['pdf_start']}-{e['pdf_end']} from the mục lục, "
                            f"structure.yaml has {sp[0]}-{sp[-1]}")
        printed_est = (stream.pages.get(e["pdf_start"]) or {}).get("printed_page_est")
        if e["printed_page"] and printed_est and printed_est != e["printed_page"]:
            problems.append(f"{e['id']}: mục lục page {e['printed_page']}, but pdf {e['pdf_start']} "
                            f"is printed page {printed_est}")

    # headings
    for e in entries:
        idx, texts = page_heading(stream, e["pdf_start"])
        e["_heading"] = [(e["pdf_start"], i) for i in idx]
        e["heading_ocr"] = texts
        if not texts:
            problems.append(f"{e['id']}: no heading at the top of pdf {e['pdf_start']}")
            continue
        title, sub = split_heading(texts)
        score = max(heading_score(e["toc_title"], " ".join(texts)),
                    heading_score(e["structure_title"] or e["toc_title"], " ".join(texts)))
        if score < 0.5:
            problems.append(f"{e['id']}: heading on pdf {e['pdf_start']} '{' / '.join(texts)}' "
                            f"doesn't match the mục lục '{e['toc_title']}'")
        elif similar(title, e["toc_title"].split("(")[0]) < 0.9 or (
                e["structure_title"] and similar(title, e["structure_title"].split("(")[0]) < 0.9):
            problems.append(f"{e['id']}: titles differ: heading '{' / '.join(texts)}', mục lục "
                            f"'{e['toc_title']}', structure.yaml '{e['structure_title']}'")
        e["_score"] = score
    return entries, problems


def _model(title: str, toc: str, structure: str | None) -> str:
    """The casing model: the mục lục row, unless the structure.yaml title is
    clearly closer to the heading's letters (the row is another title, "Chang
    nghèo" for "JARI BĂH", or misread, "da-pa-ok", "MƯIak")."""
    if not structure:
        return toc
    structure = structure.split(" (")[0]
    key = lambda s: "".join(c for _, c in _letters(s))
    a, b = (difflib.SequenceMatcher(None, key(title), key(x), autojunk=False).ratio() for x in (toc, structure))
    return structure if b > a else toc


def finish_titles(entries: list[dict], heading_texts: dict) -> None:
    """title / subtitle from the heading (call marks taken out:
    `heading_texts[id]` is the heading rows without them), cased like the
    mục lục row (see `_model`). A heading too garbled to match keeps the mục
    lục title."""
    for e in entries:
        texts = heading_texts.get(e["id"]) or e["heading_ocr"]
        if not texts or e.get("_score", 0) < 0.5:
            e["title"], e["subtitle"], e["title_from"] = e["toc_title"].split(" (")[0], None, "mục lục"
            continue
        title, sub = split_heading(texts)
        e["title_printed"] = title
        e["subtitle_printed"] = sub
        toc_main, _, toc_sub = e["toc_title"].partition("(")
        e["title"] = recase(title, _model(title, toc_main.strip() or e["toc_title"], e["structure_title"]))
        if sub is None:
            e["subtitle"] = None
        elif sub.isupper():
            e["subtitle"] = recase(sub, toc_sub.strip(") ") or (e["structure_title"] or "").partition("(")[2].strip(") ") or sub)
        else:
            e["subtitle"] = sub
        e["title_from"] = "heading"


def to_json(book: Book, entries: list[dict], cfg: dict, end_page: int) -> dict:
    children = []
    for e in entries:
        out = dict(id=e["id"], number=e["number"], title=e.get("title"))
        if e["number"] is not None:
            out["subtitle"] = e.get("subtitle")
        out["toc_title"] = e["toc_title"]
        if e["number"] is not None:
            out["structure_title"] = e["structure_title"]
        out.update(level=1, printed_page=e["printed_page"], pdf_start=e["pdf_start"], pdf_end=e["pdf_end"],
                   parse=True)
        if e.get("heading_ocr"):
            out["heading_ocr"] = e["heading_ocr"]
        if e.get("title_from") == "mục lục":
            out["title_from"] = "mục lục (heading unreadable)"
        if e.get("toc_stray_mark"):
            out["toc_stray_mark"] = e["toc_stray_mark"]
        children.append(out)
    return dict(id=book.id, title=cfg.get("title") or book.s["title"], level=0,
                pdf_start=entries[0]["pdf_start"] if entries else None, pdf_end=end_page, parse=True,
                children=children)
