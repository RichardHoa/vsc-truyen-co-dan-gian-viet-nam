"""Cross-check two OCR engines and flag lines that need a human.

For each page: group both engines' lines into visual rows, pair rows by
position, and diff their text. A row is flagged when
  - the engines disagree beyond accents,    -> "disagree"
    and the row (accents ignored) is under
    DISAGREE_BELOW alike
  - the primary engine's confidence is low  -> "low_conf"
  - only one engine saw text there          -> "missing_in_secondary" / row added
                                               with "only_in_secondary"
Tesseract misreads Vietnamese accents all the time, so a difference only in
accents, or a word or two in an otherwise matching row, is kept in "diff" but
not flagged. Reviewers then only read flagged rows instead of proofreading
every page.

Writes data/ocr/<book>/merged/pNNNN.json.
"""

from __future__ import annotations

import difflib
import unicodedata

from .common import Book, read_json, write_json
from .layout import group_rows, norm_space, v_overlap

LOW_CONF = {"vision": 0.5, "tesseract": 0.75}
PUNCT = ".,;:!?…\"'“”‘’()[]-–—«»"
DISAGREE_BELOW = 0.9


def _words(s: str) -> list[str]:
    return norm_space(s).split(" ") if s.strip() else []


def _same_ignoring_punct(a: list[str], b: list[str]) -> bool:
    strip = lambda ws: [w.strip(PUNCT) for w in ws if w.strip(PUNCT)]
    return strip(a) == strip(b)


def _fold(s: str) -> str:
    """Lower case, without accents or vowel marks: "Điển" -> "dien"."""
    d = unicodedata.normalize("NFD", norm_space(s).casefold())
    return "".join(c for c in d if not unicodedata.combining(c)).replace("đ", "d")


def _disagree(a: str, b: str, diff: list[list[str]]) -> bool:
    if all(_fold(x) == _fold(y) for x, y in diff):
        return False
    return difflib.SequenceMatcher(None, _fold(a), _fold(b), autojunk=False).ratio() < DISAGREE_BELOW


def word_diff(a: str, b: str) -> list[list[str]]:
    """[[primary words, secondary words], ...] for every differing span."""
    wa, wb = _words(a), _words(b)
    sm = difflib.SequenceMatcher(None, wa, wb, autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        pa, pb = wa[i1:i2], wb[j1:j2]
        if _same_ignoring_punct(pa, pb):
            continue
        out.append([" ".join(pa), " ".join(pb)])
    return out


def compare_page(primary: dict, secondary: dict | None, primary_name: str) -> dict:
    prow = group_rows(primary["lines"])
    srow = group_rows(secondary["lines"]) if secondary else []
    used = set()
    out_rows = []
    for r in prow:
        conf = min((p["conf"] for p in r["parts"]), default=0.0)
        flags = []
        if conf < LOW_CONF.get(primary_name, 0.5):
            flags.append("low_conf")
        entry = dict(text=r["text"], bbox=r["bbox"], conf=conf)
        alts = [a for p in r["parts"] for a in p.get("alternatives", [])]
        if alts:
            entry["alternatives"] = alts
        if secondary is not None:
            matches = [i for i, s in enumerate(srow) if v_overlap(r["bbox"], s["bbox"]) >= 0.5]
            if matches:
                used.update(matches)
                other = " ".join(srow[i]["text"] for i in matches)
                entry["secondary"] = other
                entry["similarity"] = round(difflib.SequenceMatcher(
                    None, norm_space(r["text"]), norm_space(other), autojunk=False).ratio(), 3)
                diff = word_diff(r["text"], other)
                if diff:
                    entry["diff"] = diff
                    if _disagree(r["text"], other, diff):
                        flags.append("disagree")
            else:
                flags.append("missing_in_secondary")
        entry["flags"] = flags
        out_rows.append(entry)

    # text only the secondary engine saw (primary may have dropped a line)
    for i, s in enumerate(srow):
        if i in used or not s["text"].strip():
            continue
        out_rows.append(dict(text=s["text"], bbox=s["bbox"], conf=0.0,
                             secondary=s["text"], flags=["only_in_secondary"]))
    out_rows.sort(key=lambda e: (e["bbox"][1], e["bbox"][0]))

    flagged = sum(1 for e in out_rows if e["flags"])
    sims = [e["similarity"] for e in out_rows if "similarity" in e]
    return dict(
        primary=primary_name,
        secondary=secondary.get("engine") if secondary else None,
        image_size=primary.get("image_size"),
        rows=out_rows,
        stats=dict(rows=len(out_rows), flagged=flagged,
                   agreement=round(sum(sims) / len(sims), 3) if sims else None),
    )


def compare_pages(book: Book, pages: list[int], primary: str = "vision") -> None:
    secondary_name = "tesseract" if primary == "vision" else "vision"
    done = no_primary = 0
    total_rows = total_flagged = 0
    for n in pages:
        p_path = book.ocr_path(primary, n)
        if not p_path.exists():
            no_primary += 1
            continue
        s_path = book.ocr_path(secondary_name, n)
        merged = compare_page(read_json(p_path), read_json(s_path) if s_path.exists() else None, primary)
        merged["page"] = n
        write_json(book.merged_path(n), merged)
        done += 1
        total_rows += merged["stats"]["rows"]
        total_flagged += merged["stats"]["flagged"]
    if no_primary:
        print(f"  ! {no_primary} page(s) have no {primary} OCR yet")
    if total_rows:
        print(f"  merged {done} page(s): {total_flagged}/{total_rows} rows flagged "
              f"({100 * total_flagged / total_rows:.1f}%)")
