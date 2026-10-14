"""Story Titles (data/books/<book>/titles.yaml): each story's heading as a
human set it. The AI Proofreading Pass writes them exactly as set (prepare-ai
copies this file to the cluster), and no Spelling Rule changes them. No
server here: blocks in, titles out.

A story is named by the first pdf page of its section in book.raw.md, the
sections of a reviewed book being paired with book.raw.md's by their order:

  titles: [{pdf: 447, title: "48. Jôt đi học (Ja Jôt nao mugru)"}]

  from_book     the titles a reviewed book's headings give
  changed       the titles after an edit, when it changed a heading
  set_headings  the headings a Story Title decides
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

from ..common import read_yaml, write_yaml
from .mdbook import HEADING, sections

FILE = "titles.yaml"
HEADER = ("# Story Titles for this book: each story's heading as set, by the first pdf page of its section.\n"
          "# Edit a heading in `python -m vsc_ocr review <book>` (or by hand here); the AI Proofreading Pass\n"
          "# writes them as they are (prepare-ai copies this file to the cluster).\n")


def load(path: Path) -> dict[int, str]:
    data = (read_yaml(path) if path.exists() else None) or {}
    return {int(t["pdf"]): unicodedata.normalize("NFC", str(t["title"]).strip()) for t in data.get("titles") or []}


def save(path: Path, titles: dict[int, str]) -> None:
    """Written to a temporary file first, so a read never sees half of it."""
    tmp = path.with_suffix(".yaml.tmp")
    write_yaml(tmp, {"titles": [dict(pdf=p, title=titles[p]) for p in sorted(titles)]}, header=HEADER)
    tmp.replace(path)


def _stories(blocks: list[str], raw: list[str]) -> list[tuple[dict, int]] | None:
    """Each story section of `blocks` with the first pdf page of its book.raw.md section, or None when the
    two books' sections can't be paired by their order."""
    secs, raw_secs = sections(blocks), sections(raw)
    if len(secs) != len(raw_secs) or any(a["level"] != b["level"] for a, b in zip(secs, raw_secs)):
        return None
    return [(s, r["pdf"][0]) for s, r in zip(secs, raw_secs)
            if r["pdf"] and s["level"] > 1 and HEADING.match(blocks[s["start"]])]


def from_book(blocks: list[str], raw: list[str]) -> dict[int, str]:
    """The Story Titles `blocks`' headings give: note calls left out, lines joined."""
    return {pdf: unicodedata.normalize("NFC", s["title"]) for s, pdf in _stories(blocks, raw) or []}


def changed(before: list[str], after: list[str], raw: list[str], titles: dict[int, str]) -> dict[int, str] | None:
    """`titles` with the headings an edit (`before` -> `after`) changed set, or None when it changed none or
    added or removed a heading."""
    old, new = _stories(before, raw), _stories(after, raw)
    if old is None or new is None or len(old) != len(new):
        return None
    out = dict(titles)
    for (a, _), (b, pdf) in zip(old, new):
        if before[a["start"]] != after[b["start"]]:
            out[pdf] = unicodedata.normalize("NFC", b["title"])
    return out if out != titles else None


def set_headings(blocks: list[str], raw: list[str], titles: dict[int, str]) -> set[int]:
    """The indexes of the headings in `blocks` whose story has a Story Title."""
    return {s["start"] for s, pdf in _stories(blocks, raw) or [] if pdf in titles}
