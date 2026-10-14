"""The Final Book: an AI pass's text once a human has reviewed it, in
data/books/<book>/final/ (committed), all a reader of the book needs:

  book-final.md       the text
  corrections.jsonl   the Corrections a human made to it
  toc.json            its stories: id, number, title, subtitle, printed page and
                      pdf pages; built from book-final.md's headings, with the
                      ids and printed pages of the OCR draft's toc.json, matched
                      by the story's first pdf page
  notes.json          its notes: id, story, pdf page, marker, text and whether
                      the text calls it; built from book-final.md

  `python -m vsc_ocr apply-corrections <book>`
      replays the Final Book's Corrections (final/corrections.jsonl) onto a new AI
      pass (ai/book.ai.md). A Correction is applied where its `before` blocks
      are still there: in its own section, else anywhere the book has them
      exactly once. The applied ones are logged in ai/corrections.jsonl, the
      others listed to redo in `review --ai`. Spelling corrections are not
      replayed: the pass applies spellings.yaml itself. It leaves
      ai/replayed.json behind, naming the pass it ran on.

  `python -m vsc_ocr finalize <book>`
      writes final/: ai/book.ai.md as book-final.md, ai/corrections.jsonl as
      corrections.jsonl (replacing the previous log), and the toc.json and
      notes.json built from it. It refuses while any ⚠ is
      left, and, when a Final Book exists already, unless this pass is the one
      the Final Book was made from or apply-corrections has run on it
      (`--force` skips that check), and when the OCR draft's toc.json is
      missing or lacks a story. It leaves ai/finalized.json behind.

A pass is named by the sha1 of its ai_corrections.jsonl, the model's own log,
which is copied from the cluster with every pass and never edited here.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from .common import Book, read_json, write_json
from .review import mdbook

FINAL_DIR = "final"
FINAL = "book-final.md"
LOG = "corrections.jsonl"
REPLAYED = "replayed.json"
FINALIZED = "finalized.json"


def replay(blocks: list[str], corrections: list[dict]) -> tuple[list[str], list[dict], list[dict]]:
    """`blocks` with `corrections` applied in order, the ones applied and the ones whose `before` isn't found once."""
    blocks = list(blocks)
    applied, missed = [], []
    for c in corrections:
        if c["action"] == "spelling" or c["before"] == c["after"]:
            continue
        at = _find(blocks, c["before"], c["section"])
        if at is None:
            missed.append(c)
            continue
        blocks[at:at + len(c["before"])] = c["after"]
        applied.append(c)
    return blocks, applied, missed


def _find(blocks: list[str], before: list[str], section: str) -> int | None:
    n = len(before)
    if not n:
        return None
    hits = [i for i in range(len(blocks) - n + 1) if blocks[i:i + n] == before]
    secs = mdbook.sections(blocks)
    own = [i for i in hits if secs[mdbook.section_of(secs, i)]["title"] == section]
    for found in (own, hits):
        if len(found) == 1:
            return found[0]
    return None


def flags(blocks: list[str]) -> dict[str, int]:
    """{section title: number of ⚠} for the sections that still have one."""
    return {s["title"]: s["flags"] for s in mdbook.sections(blocks) if s["flags"]}


_story = re.compile(r"^(?:(\d+)\.\s+)?(.*?)(?:\s*\(([^()]*)\))?$", re.S)
_note_page = re.compile(r"<!--\s*note pdf (\d+)")
_comment = re.compile(r"\s*<!--.*?-->", re.S)


def toc(blocks: list[str], ocr_toc: dict) -> dict:
    """The Final Book's toc.json: its headings, with the ids and printed pages of the OCR draft's toc.json
    (`ocr_toc`), matched by first pdf page."""
    known = {e["pdf_start"]: e for e in _entries(ocr_toc["toc"])}
    title, children, unknown = ocr_toc["toc"]["title"], [], []
    for s in mdbook.sections(blocks):
        if s["level"] == 1:
            title = s["title"]
            continue
        e = known.get(s["pdf"][0]) if s["pdf"] else None
        if e is None:
            unknown.append(s["title"])
            continue
        number, name, subtitle = _story.match(s["title"]).groups()
        children.append(dict(id=e["id"], number=int(number) if number else None, title=name, subtitle=subtitle,
                             level=s["level"] - 1, printed_page=e["printed_page"],
                             pdf_start=s["pdf"][0], pdf_end=s["pdf"][1]))
    if unknown:
        raise SystemExit("the OCR draft's toc.json has no story starting on these sections' first pdf page:\n"
                         + "\n".join(f"    {t}" for t in unknown))
    return dict(book=ocr_toc["book"], toc=dict(
        id=ocr_toc["toc"]["id"], title=title, level=0,
        pdf_start=min((c["pdf_start"] for c in children), default=None),
        pdf_end=max((c["pdf_end"] for c in children), default=None), children=children))


def _entries(node: dict) -> list[dict]:
    return [e for c in node.get("children", []) for e in [c, *_entries(c)]]


def notes(blocks: list[str], book_toc: dict) -> dict:
    """The Final Book's notes.json: each note definition, by the story it is in (`book_toc`'s ids)."""
    ids = {c["pdf_start"]: c["id"] for c in _entries(book_toc["toc"])}
    text = "\n".join(b for b in blocks if not mdbook.NOTE_DEF.match(b))
    out = []
    for s in mdbook.sections(blocks):
        for b in blocks[s["start"]:s["end"]]:
            m = mdbook.NOTE_DEF.match(b)
            if not m:
                continue
            nid, body = m.groups()
            page = _note_page.search(body)
            out.append(dict(id=nid, scope=ids.get(s["pdf"][0]) if s["pdf"] else None,
                            page=int(page.group(1)) if page else None, marker=nid.rsplit("-", 1)[-1],
                            text=_comment.sub("", body).strip(), called=f"[^{nid}]" in text))
    return dict(book=book_toc["book"], notes=out)


def apply_corrections(book: Book, force: bool = False) -> None:
    ai = book.dir / "ai"
    text_path = ai / "book.ai.md"
    if not text_path.exists():
        raise SystemExit(f"{text_path} doesn't exist: copy the AI pass's book.ai.md there first.")
    if not (book.dir / FINAL_DIR / FINAL).exists():
        raise SystemExit(f"{book.id} has no {FINAL_DIR}/{FINAL} yet: there is nothing to replay (skip this step for a book's first pass).")
    pass_id = _pass_id(ai)
    if pass_id is None:
        raise SystemExit(f"{ai / 'ai_corrections.jsonl'} doesn't exist: copy it from the run folder with book.ai.md.")
    if _marked(ai / REPLAYED, pass_id):
        raise SystemExit(f"apply-corrections has run on this pass already ({ai / REPLAYED}).")
    if _read_log(ai / LOG) and not force:
        raise SystemExit(f"{ai / LOG} has Corrections already: empty ai/ before copying a new pass in, "
                         "and run apply-corrections before reviewing it (--force to replay anyway).")

    text = text_path.read_text(encoding="utf-8")
    blocks, applied, missed = replay(mdbook.split(text), _read_log(book.dir / FINAL_DIR / LOG))
    raw = ai / "book.ai.raw.md"
    if not raw.exists():
        raw.write_text(text, encoding="utf-8")
    tmp = text_path.with_suffix(".md.tmp")
    tmp.write_text(mdbook.join(blocks), encoding="utf-8")
    tmp.replace(text_path)
    time = datetime.now().isoformat(timespec="seconds")
    with open(ai / LOG, "a", encoding="utf-8") as f:
        for c in applied:
            f.write(json.dumps(dict(c, replayed=time), ensure_ascii=False) + "\n")
    write_json(ai / REPLAYED, dict(time=time, pass_sha1=pass_id, applied=len(applied), missed=missed))

    print(f"  {len(applied)} Correction(s) applied to {text_path.relative_to(book.dir)}, {len(missed)} not found:")
    for c in missed:
        pages = ",".join(map(str, c["pdf_pages"])) or "-"
        print(f"\n  [{c['action']}] {c['section']} (pdf {pages})")
        for b in c["before"]:
            print(f"    - {_short(b)}")
        for b in c["after"]:
            print(f"    + {_short(b)}")
    if missed:
        print(f"\n  Check them in `python -m vsc_ocr review {book.id} --ai` (also listed in ai/{REPLAYED}).")


def finalize(book: Book, force: bool = False) -> None:
    ai = book.dir / "ai"
    text_path = ai / "book.ai.md"
    if not text_path.exists():
        raise SystemExit(f"{text_path} doesn't exist: there is no AI pass to finalize.")
    pass_id = _pass_id(ai)
    out = book.dir / FINAL_DIR
    final = out / FINAL
    if final.exists() and not force and not (pass_id and (_marked(ai / FINALIZED, pass_id) or _marked(ai / REPLAYED, pass_id))):
        raise SystemExit(f"{final} was made from another pass, and apply-corrections hasn't run on this one: "
                         f"run `python -m vsc_ocr apply-corrections {book.id}` first, so its Corrections aren't lost "
                         "(--force to finalize anyway).")
    text = text_path.read_text(encoding="utf-8")
    left = flags(mdbook.split(text))
    if left:
        lines = "\n".join(f"    {n} ⚠  {title}" for title, n in left.items())
        raise SystemExit(f"{text_path} still has {sum(left.values())} ⚠; clear them in `review --ai` first:\n{lines}")

    ocr_toc = book.dir / "toc.json"
    if not ocr_toc.exists():
        raise SystemExit(f"{ocr_toc} doesn't exist: run `python -m vsc_ocr assemble {book.id}` first "
                         "(the Final Book's toc takes its printed page numbers from it).")
    blocks = mdbook.split(text)
    book_toc = toc(blocks, read_json(ocr_toc))
    book_notes = notes(blocks, book_toc)

    out.mkdir(exist_ok=True)
    final.write_text(text, encoding="utf-8")
    log = ai / LOG
    (out / LOG).write_text(log.read_text(encoding="utf-8") if log.exists() else "", encoding="utf-8")
    write_json(out / "toc.json", book_toc)
    write_json(out / "notes.json", book_notes)
    write_json(ai / FINALIZED, dict(time=datetime.now().isoformat(timespec="seconds"), pass_sha1=pass_id))
    print(f"  {out.relative_to(book.dir.parent)}/ written: {len(book_toc['toc']['children'])} stories, "
          f"{len(book_notes['notes'])} notes, {len(_read_log(log))} Correction(s). Commit it.")


def _pass_id(ai: Path) -> str | None:
    path = ai / "ai_corrections.jsonl"
    return hashlib.sha1(path.read_bytes()).hexdigest() if path.exists() else None


def _marked(path: Path, pass_id: str) -> bool:
    return path.exists() and read_json(path).get("pass_sha1") == pass_id


def _read_log(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _short(s: str, n: int = 100) -> str:
    s = s.replace("\n", " ⏎ ")
    return s if len(s) <= n else s[:n] + "…"
