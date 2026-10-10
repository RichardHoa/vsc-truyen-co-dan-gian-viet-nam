"""Which scanned page each block of book.raw.md is on, for an AI Proofreading
Pass that runs one task per page: `python -m vsc_ocr export-pages <book>`.

Writes data/books/<book>/pages.jsonl, one line per page that has blocks:

  {"page": 29, "section": "5. Prăm Tịch, Prăm Lắc (!)", "raw_sha1": "…",
   "own": [{"i": 143, "pages": [29, 30]}, …], "continued": [141]}

  own        the blocks (indices into book.raw.md split on blank lines) that
             start on this page, with every page each one is on
  continued  blocks that start on an earlier page and run onto this one

A block's pages are where `mdbook.Scans.locate` finds it, kept in reading
order: its start page is never before the previous block's, and it runs on
over consecutive pages only. A block not found on the scans (a badly OCR'd
paragraph, or a line under 8 letters found only past the next page) goes on
the page where the block before it ends. A Note Definition is on
the page its `<!-- note pdf N -->` comment names. Comments and breaks
belong to no page.
"""

from __future__ import annotations

import hashlib
import json
import re

from . import mdbook

MAX_SPAN = 3     # pages one block may run over
_note_page = re.compile(r"<!--\s*note pdf (\d+)")


def _span(found: set[int], after: int) -> list[int]:
    """The run of consecutive pages in `found` starting at its first page >= `after`."""
    later = sorted(p for p in found if p >= after)
    if not later:
        return []
    run = [later[0]]
    while len(run) < MAX_SPAN and run[-1] + 1 in found:
        run.append(run[-1] + 1)
    return run


def export(book) -> None:
    raw_path = book.dir / "book.raw.md"
    if not raw_path.exists():
        print(f"  {book.id}: no book.raw.md, skipped (run `python -m vsc_ocr assemble {book.id}` first)")
        return
    text = raw_path.read_text(encoding="utf-8")
    sha1 = hashlib.sha1(text.encode()).hexdigest()
    blocks = mdbook.split(text)
    scans = mdbook.Scans(book)

    pages: dict[int, dict] = {}
    unplaced = no_pdf = 0
    for sec in mdbook.sections(blocks):
        if not sec["pdf"]:
            no_pdf += sum(mdbook.kind(blocks[i]) not in ("comment", "break") for i in range(sec["start"], sec["end"]))
            continue
        idx = range(sec["start"], sec["end"])
        boxes = scans.locate([blocks[i] for i in idx], sec["pdf"])
        prev = end = sec["pdf"][0]    # where the previous block starts and ends
        for i, bx in zip(idx, boxes):
            kind = mdbook.kind(blocks[i])
            if kind in ("comment", "break"):
                continue
            m = _note_page.search(blocks[i]) if kind == "note" else None
            if m:
                span = [int(m.group(1))]
            else:
                span = _span({b["page"] for b in bx}, prev)
                # A line under 8 letters matches any identical line; one that skips ahead a page is more
                # likely such a match than the block's page
                if span and span[0] > end + 1 and len(mdbook.letters(blocks[i])) < 8:
                    span = []
                if not span:
                    span, unplaced = [end], unplaced + 1
                prev, end = span[0], span[-1]
            for k, n in enumerate(span):
                pg = pages.setdefault(n, dict(page=n, section=sec["title"], raw_sha1=sha1, own=[], continued=[]))
                if k == 0:
                    pg["own"].append(dict(i=i, pages=span))
                else:
                    pg["continued"].append(i)

    out = book.dir / "pages.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for n in sorted(pages):
            f.write(json.dumps(pages[n], ensure_ascii=False) + "\n")
    owned = sum(len(p["own"]) for p in pages.values())
    print(f"  {out.name}: {len(pages)} pages, {owned} blocks ({unplaced} not found on the scans, "
          f"placed with the block before)" + (f"; {no_pdf} blocks left out: their section has no pdf range"
                                              if no_pdf else ""))
