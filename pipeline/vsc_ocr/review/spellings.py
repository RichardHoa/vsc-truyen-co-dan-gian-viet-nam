"""Spelling Rules (data/books/<book>/spellings.yaml) and the words the
diacritic review lists. No files and no server here: text in, text out.

A word's fold is its letters in lower case without marks (`đ` counts as `d`),
so `Tềwa`, `TÊWA` and `têwa` all fold to `tewa`. Two spellings with the same
fold that differ in their marks are a pair. Words, note calls and folding
are the same as the AI Proofreading Pass's (resume-scanning
`src/pipelines/proofreader.py`), so a rule does the same here as there.

spellings.yaml, one entry per folded form:

  words:   [{spelling: Tềwa, except: [Story Titles where the rule is skipped]}]
  phrases: [{spelling: bồng - bồng, except: []}]   matched with their neighbours
  depends: [[thầy, thấy]]                          decided per occurrence, never applied

  respell     a text with the rules applied, each word in its own case
  find_pairs  the occurrences where the current text, the model's reading and
              the OCR spell a word with the same letters but different marks
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from ..common import read_yaml, write_yaml
from .mdbook import HEADING, kind, sections
from .mdbook import _comment, _ref as _call
_heading_read = re.compile(r"·\s*heading:\s*(.*?)\s*(?:·|-->)", re.S)
CONTEXT = 4     # words each side of an occurrence used to find it on the scan and to show it

HEADER = ("# Spelling Rules for this book, made in `python -m vsc_ocr review <book> --ai --diacritic`.\n"
          "# The AI Proofreading Pass applies them too (prepare-ai copies this file to the cluster).\n")


# ---------------------------------------------------------------- words

def fold(s: str) -> str:
    """Lower-case letters and digits without marks: "Tềwa" -> "tewa", "Đăm" -> "dam"."""
    s = unicodedata.normalize("NFD", s.lower().replace("đ", "d"))
    return "".join(c for c in s if c.isalnum() and not unicodedata.combining(c))


def spans(text: str) -> list[tuple[str, int, int, str]]:
    """The words of `text` (NFC) as (word, start, end, fold). Note calls and `<!-- -->` comments have none."""
    text = unicodedata.normalize("NFC", text)
    chars = []
    for c in text:
        f = unicodedata.normalize("NFD", c.lower().replace("đ", "d"))[:1]
        chars.append(f if "a" <= f <= "z" or "0" <= f <= "9" else " ")
    for pat in (_call, _comment):
        for m in pat.finditer(text):
            chars[m.start():m.end()] = " " * (m.end() - m.start())
    return [(text[m.start():m.end()], m.start(), m.end(), m.group(0))
            for m in re.finditer(r"[a-z0-9]+", "".join(chars))]


def cased(spelling: str, like: str) -> str:
    """`spelling` in the case of `like`: ("Tềwa", "TÊWA") -> "TỀWA", ("Tềwa", "têwa") -> "tềwa", ("Tềwa", "TêWa") -> "TềWa"."""
    if len(spelling) == len(like):
        return "".join(s.upper() if c.isupper() else s.lower() for s, c in zip(spelling, like))
    if like.isupper():
        return spelling.upper()
    return spelling[:1].upper() + spelling[1:].lower() if like[:1].isupper() else spelling.lower()


def _gap(text: str, a: tuple, b: tuple) -> str:
    """The punctuation between two words of `text`, spaces left out."""
    return "".join(text[a[2]:b[1]].split())


# ---------------------------------------------------------------- the file

def empty() -> dict:
    return dict(words=[], phrases=[], depends=[])


def load(path: Path) -> dict:
    data = (read_yaml(path) if path.exists() else None) or {}
    out = empty()
    for key in ("words", "phrases"):
        out[key] = [dict(spelling=unicodedata.normalize("NFC", str(r["spelling"])), **{"except": list(r.get("except") or [])})
                    for r in data.get(key) or []]
    out["depends"] = [[unicodedata.normalize("NFC", str(w)) for w in pair] for pair in data.get("depends") or []]
    return out


def save(path: Path, data: dict) -> None:
    write_yaml(path, {k: data.get(k) or [] for k in ("words", "phrases", "depends")}, header=HEADER)


def word_rule(data: dict, f: str) -> dict | None:
    return next((r for r in data["words"] if fold(r["spelling"]) == f), None)


def depends(data: dict, f: str) -> bool:
    return any(fold(w) == f for pair in data["depends"] for w in pair)


def skipped(rule: dict, title: str) -> bool:
    """The rule has a story exception for the story titled `title`."""
    return fold(title) in {fold(t) for t in rule.get("except") or []}


# ---------------------------------------------------------------- applying

def _phrase_hits(text: str, sps: list, rule: dict) -> list[int]:
    """Where `rule` (a phrase) starts among `sps`, the words of `text`: its words and the punctuation between them."""
    want = spans(rule["spelling"])
    folds, gaps = [s[3] for s in want], [_gap(rule["spelling"], a, b) for a, b in zip(want, want[1:])]
    n = len(folds)
    return [i for i in range(len(sps) - n + 1)
            if [s[3] for s in sps[i:i + n]] == folds
            and [_gap(text, a, b) for a, b in zip(sps[i:i + n], sps[i + 1:i + n])] == gaps]


def respell(text: str, data: dict, title: str) -> tuple[str, list[tuple[str, str, str]]]:
    """
    `text` with the Spelling Rules applied (phrases first, then words), each word in its own case, the rules
    excepted for the story titled `title` left out: (text, [(before, after, rule spelling)]).
    """
    text = unicodedata.normalize("NFC", text)
    sps = spans(text)
    edits: list[tuple] = []     # (start, end, after, before, rule spelling)
    used: set[int] = set()
    for r in data["phrases"]:
        if skipped(r, title):
            continue
        words = [s[0] for s in spans(r["spelling"])]
        for i in _phrase_hits(text, sps, r):
            win = sps[i:i + len(words)]
            if any(k in used for k in range(i, i + len(win))):
                continue
            used |= set(range(i, i + len(win)))
            for w, s in zip(words, win):
                if w.lower() != s[0].lower():
                    edits.append((s[1], s[2], cased(w, s[0]), s[0], r["spelling"]))
    for k, (word, start, end, f) in enumerate(sps):
        r = word_rule(data, f) if k not in used else None
        if r and not skipped(r, title) and r["spelling"].lower() != word.lower():
            edits.append((start, end, cased(r["spelling"], word), word, r["spelling"]))
    edits.sort()
    for start, end, new, _, _ in reversed(edits):
        text = text[:start] + new + text[end:]
    return text, [(before, new, rule) for _, _, new, before, rule in edits]


def covered(text: str, start: int, data: dict, title: str) -> str | None:
    """The rule (its spelling) that decides the word starting at `start` in `text`, if any."""
    text = unicodedata.normalize("NFC", text)
    sps = spans(text)
    k = next((k for k, s in enumerate(sps) if s[1] == start), None)
    if k is None:
        return None
    for r in data["phrases"]:
        if not skipped(r, title):
            n = len(spans(r["spelling"]))
            if any(i <= k < i + n for i in _phrase_hits(text, sps, r)):
                return r["spelling"]
    r = word_rule(data, sps[k][3])
    return r["spelling"] if r and not skipped(r, title) else None


def apply(blocks: list[str], data: dict, story: list[str], fixed: set[int] = frozenset()) -> dict[int, tuple[str, list]]:
    """
    The blocks the rules change: {index: (new text, [(before, after, rule)])}, `story` being each block's story
    title (`story_titles`, the titles story exceptions name). Headings change too, but those a Story Title decides
    (`fixed`, their indexes); comments don't.
    """
    out = {}
    for i, (b, title) in enumerate(zip(blocks, story)):
        if kind(b) == "comment" or i in fixed:
            continue
        new, changes = respell(b, data, title)
        if changes:
            out[i] = (new, changes)
    return out


def check_sections(mine: list[dict], raw: list[dict]) -> None:
    """Sections are paired by their order: refuse when the two books don't have the same headings."""
    if len(mine) != len(raw) or any(a["level"] != b["level"] for a, b in zip(mine, raw)):
        raise ValueError(f"book.ai.md has {len(mine)} sections and book.raw.md {len(raw)} (or their levels differ): "
                         "the sections can't be paired, so the spellings can't be compared")


def story_titles(blocks: list[str], raw: list[str], titles: dict[int, str] | None = None) -> list[str]:
    """Each block's story title: its Story Title (`titles`, by first pdf page), else as book.raw.md prints it,
    the sections paired by their order."""
    secs, raw_secs = sections(blocks), sections(raw)
    check_sections(secs, raw_secs)
    out = []
    for s, r in zip(secs, raw_secs):
        title = (titles or {}).get(r["pdf"][0]) if r["pdf"] and r["level"] > 1 else None
        out += [title or r["title"]] * (s["end"] - s["start"])
    return out


# ---------------------------------------------------------------- pairs

def _section_words(blocks: list[str], start: int, end: int) -> list[tuple[int, str, int, int, str]]:
    """The words of blocks start..end as (block, word, start, end, fold); comments and scene breaks have none."""
    return [(i, *s) for i in range(start, end) if kind(blocks[i]) not in ("comment", "break") for s in spans(blocks[i])]


def _readings(mine: list, theirs: list) -> dict[int, str]:
    """For each of `mine` (by position) the word of `theirs` it lines up with, where the folds run the same."""
    out = {}
    sm = SequenceMatcher(None, [w[-1] for w in mine], [w[-1] for w in theirs], autojunk=False)
    for a, b, n in sm.get_matching_blocks():
        for k in range(n):
            out[a + k] = theirs[b + k][1]
    return out


def heading_reading(blocks: list[str], start: int, end: int) -> str | None:
    """The model's own reading of a section's heading: the `heading:` part of its `<!-- pdf … -->` comment."""
    for b in blocks[start:end]:
        if kind(b) == "comment":
            m = _heading_read.search(b)
            if m:
                return m.group(1)
    return None


def lower_folds(*texts: str) -> set[str]:
    """Folds of the words printed in lower case somewhere: these are common words, not names."""
    return {s[3] for t in texts for s in spans(t) if s[0][:1].islower()}


def find_pairs(current: list[str], raw: list[str], model: list[str], common: set[str]) -> list[dict]:
    """
    Every word of `current` (book.ai.md's blocks) whose spelling differs only in its marks from the model's reading
    (`model`, the pass's own text; for a heading, its `heading:` comment) or the OCR's (`raw`, book.raw.md), and
    every occurrence of a name (a fold not in `common`) still spelled two ways within one story. Sections are paired
    by their order. Each as {fold, block, start, end, word, ai, ocr, section, heading, name}.
    """
    cur_secs, raw_secs, mod_secs = sections(current), sections(raw), sections(model)
    check_sections(cur_secs, raw_secs)
    out = []
    for k, cs in enumerate(cur_secs):
        cw = _section_words(current, cs["start"], cs["end"])
        rs, ms = (raw_secs[k] if k < len(raw_secs) else None), (mod_secs[k] if k < len(mod_secs) else None)
        rw = _section_words(raw, rs["start"], rs["end"]) if rs else []
        mw = _section_words(model, ms["start"], ms["end"]) if ms else []
        ocr, ai = _readings(cw, rw), _readings(cw, mw)
        heading = [p for p, w in enumerate(cw) if HEADING.match(current[w[0]])]
        read = heading_reading(current, cs["start"], cs["end"])
        if heading and read is not None:
            for p in heading:
                ai.pop(p, None)
            hw = [(0, *s) for s in spans(read)]
            ai.update({heading[q]: w for q, w in _readings([cw[p] for p in heading], hw).items()})

        spelled: dict[str, set[str]] = {}     # a name's spellings in the story's text (its heading has a style of its own)
        for p, w in enumerate(cw):
            if w[-1] not in common and p not in heading:
                spelled.setdefault(w[-1], set()).add(w[1].lower())
        for p, (i, word, start, end, f) in enumerate(cw):
            if not f.isalpha():
                continue
            seen = {word.lower(), ai.get(p, word).lower(), ocr.get(p, word).lower()}
            name = f not in common and p not in heading and len(spelled.get(f, ())) > 1
            if len(seen) > 1 or name:
                out.append(dict(fold=f, block=i, start=start, end=end, word=word, ai=ai.get(p), ocr=ocr.get(p),
                                section=k, heading=p in heading, name=f not in common,
                                before=" ".join(w[1] for w in cw[max(0, p - CONTEXT):p]),
                                after=" ".join(w[1] for w in cw[p + 1:p + 1 + CONTEXT])))
    return out
