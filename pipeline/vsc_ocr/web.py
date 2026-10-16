"""The Web Edition: the Final Book (final/book-final.md) as the files the
Digitizing Việt Nam website's Book Reader reads, in data/books/<book>/web/<book>/
(gitignored; the developer copies the folder into the website's public data
by hand):

  loi_gioi_thieu.md        the Lời giới thiệu
  story_001.md ...         one per story
  table_of_contents.json   the book title, the Preface and the stories in book
                           order, with printed pages and Note counts

  `python -m vsc_ocr export-web <book>`
      generates it from the Final Book alone (never toc.json), with printed
      page = pdf page - structure.yaml's `printed_page_offset`, the book title
      structure.yaml's `web_title` and as many stories as its `works`. It writes nothing, and lists every problem, when the Final Book
      would publish a broken book.

The Web Edition is never edited: a fix goes into the Final Book, and the Web
Edition is generated again.
"""

from __future__ import annotations

import json
import re
import shutil

from .common import Book
from .final import FINAL, FINAL_DIR
from .review import mdbook

PREFACE = "Lời giới thiệu"
PREFACE_FILE = "loi_gioi_thieu.md"
TOC_FILE = "table_of_contents.json"

_call = re.compile(r"\[\^([^\]\s]+)\](?!:)")
_number = re.compile(r"^(\d+)\.\s+(.*)$", re.S)
_comment = re.compile(r"\s*<!--.*?-->", re.S)
_note_page = re.compile(r"<!--\s*note pdf (\d+)")
_dash = re.compile(r"^\\-", re.M)
_hard_break = re.compile(r" {2,}\n")
# what the website's renderer would show wrongly: emphasis, code, html, links, escapes, tables, lists, rules
_inline = re.compile(r"[*_`|\\]|<[A-Za-z/!]|\]\(")
_line_start = re.compile(r"^(?:[+] |\d+[.)] |-{3,}\s*$)", re.M)


class Refused(SystemExit):
    """The Final Book has problems that would publish a broken book."""


def write(book: Book) -> None:
    """Generate web/<book>/ from the Final Book, replacing what was there; nothing is written on a refusal."""
    final = book.dir / FINAL_DIR / FINAL
    if not final.exists():
        raise SystemExit(f"{final} doesn't exist: run `python -m vsc_ocr finalize {book.id}` first.")
    if not book.s.get("web_title"):
        raise SystemExit(f"{book.structure_path} has no web_title: the book title the website shows "
                         "(written as printed, in sentence case).")
    files = export(final.read_text(encoding="utf-8"), book.s.get("printed_page_offset"),
                   len(book.s.get("works", [])), book.s["web_title"])
    out = book.dir / "web" / book.id
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for path, content in files.items():
        with open(out / path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
    toc = json.loads(files[TOC_FILE])
    notes = toc["preface"]["footnote_count"] + sum(s["footnote_count"] for s in toc["stories"])
    print(f"  {out.relative_to(book.dir.parent)}/ written: {len(files) - 1} Markdown files, "
          f"{len(toc['stories'])} stories, {notes} notes. Copy the folder into the website's public/data/.")


def export(text: str, offset: int | None, stories: int, title: str) -> dict[str, str]:
    """The Web Edition of the Final Book `text`, as {relative path: file content}, for a book of `stories`
    stories whose printed page is pdf page - `offset`. Raises Refused listing every problem."""
    problems = []
    if offset is None:
        problems.append("the book has no printed_page_offset in its structure.yaml")
        offset = 0
    blocks = mdbook.split(text)
    starts = [i for i, b in enumerate(blocks) if _level(b) == 2]
    for b in blocks[:starts[0] if starts else len(blocks)]:
        if _level(b) != 1 and mdbook.kind(b) != "comment":
            problems.append(f"text before the first ## heading: {_short(b)}")
    files, preface, toc_stories = {}, None, []
    for k, (first, last) in enumerate(zip(starts, starts[1:] + [len(blocks)])):
        heading = blocks[first]
        name = _call.sub("", mdbook.HEADING.match(heading).group(2)).strip()
        number = _number.match(name)
        expected = PREFACE if k == 0 else f"story {k}"
        if (name != PREFACE) if k == 0 else (not number or int(number.group(1)) != k):
            problems.append(f"'{_short(heading)}' is where {expected} should be")
            continue
        pdf = mdbook.PDF_RANGE.match(blocks[first + 1]) if first + 1 < last else None
        if not pdf:
            problems.append(f"'{_short(heading)}' has no <!-- pdf a-b --> comment under it")
            continue
        start, end = int(pdf.group(1)) - offset, int(pdf.group(2) or pdf.group(1)) - offset
        heading, body, notes, wrong = _entry(blocks[first:last], offset, preface=k == 0)
        problems += [f"{name}: {w}" for w in wrong]
        content = mdbook.join([heading, *body] + (["---", "### Chú thích", *notes] if notes else []))
        if k == 0:
            preface = dict(title=PREFACE, markdown_file=PREFACE_FILE, start_page=start, end_page=end,
                           footnote_count=len(notes))
            files[PREFACE_FILE] = content
            continue
        path = f"story_{k:03d}.md"
        toc_stories.append(dict(story_number=k, title=number.group(2), start_page=start, end_page=end,
                                markdown_file=path, footnote_count=len(notes)))
        files[path] = content
    if not starts:
        problems.append(f"the {PREFACE} is missing")
    problems += [f"'{_short(blocks[a])}' is after the last story ({stories})" for a in starts[stories + 1:]]
    problems += [f"story {n} is missing" for n in range(len(starts), stories + 1) if n]
    if problems:
        raise Refused(f"the Web Edition isn't written: the Final Book has {len(problems)} problem(s):\n"
                      + "\n".join(f"    {p}" for p in problems))
    files[TOC_FILE] = json.dumps(dict(book_title=title, preface=preface, stories=toc_stories),
                                 ensure_ascii=False, indent=2) + "\n"
    return files


def _level(block: str) -> int:
    m = mdbook.HEADING.match(block)
    return len(m.group(1)) if m else 0


def _short(s: str, n: int = 80) -> str:
    s = s.replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"


def _entry(blocks: list[str], offset: int, preface: bool) -> tuple[str, list[str], list[str], list[str]]:
    """An Entry's heading, its text in the website's dialect and its Note Definitions, with the Note Calls
    numbered in reading order, and what is wrong with its Notes."""
    defs, text, wrong = {}, [], []
    for b in blocks:
        m = mdbook.NOTE_DEF.match(b)
        if m:
            if m.group(1) in defs:
                wrong.append(f"[^{m.group(1)}] is defined twice")
            defs[m.group(1)] = m.group(2)
        elif mdbook.kind(b) != "comment":
            text.append(_comment.sub("", b))
    order: list[str] = []

    def renumber(m: re.Match) -> str:
        order.append(m.group(1))
        return f"[^{len(order)}]"

    heading, *body = [_call.sub(renumber, b) for b in text]
    body = [_dialect(b, closing=preface and i == len(body) - 1) for i, b in enumerate(body)]
    wrong += [f"Markdown the website doesn't render: {_short(b)}" for b in body if _unsupported(b)]
    for nid in dict.fromkeys(order):
        if order.count(nid) > 1:
            wrong.append(f"[^{nid}] is called {order.count(nid)} times")
        if nid not in defs:
            wrong.append(f"[^{nid}] is called but has no definition")
    wrong += [f"[^{nid}] is defined but never called" for nid in defs if nid not in order]
    notes = []
    for k, nid in enumerate(order, 1):
        if nid not in defs:
            continue
        page = _note_page.search(defs[nid])
        if not page:
            wrong.append(f"[^{nid}]'s definition has no <!-- note pdf N --> tag")
            continue
        note = _comment.sub("", defs[nid]).strip()
        if _unsupported(note):
            wrong.append(f"[^{nid}]: Markdown the website doesn't render: {_short(note)}")
        notes.append(f"[^{k}]: (Trang {int(page.group(1)) - offset}) {note}")
    return heading, body, notes, wrong


def _unsupported(block: str) -> bool:
    """Whether a block (in the website's dialect) has Markdown the renderer doesn't handle: it renders
    `###` headings, plain paragraphs (whose `- ` lines are dialogue), `> ` verse, `-> ` right-aligned lines
    and Note Calls."""
    if mdbook.HEADING.match(block):
        return _level(block) != 3
    return bool(_inline.search(block) or _line_start.search(block))


def _dialect(block: str, closing: bool) -> str:
    """A text block as the website writes it: plain dialogue dashes, and a block of hard breaks as verse
    lines, or as right-aligned lines when it is the Preface's `closing` place, date and signature."""
    block = _dash.sub("-", block)
    if not _hard_break.search(block):
        return block
    mark = "-> " if closing else "> "
    return "\n".join(mark + line.rstrip() for line in block.split("\n"))
