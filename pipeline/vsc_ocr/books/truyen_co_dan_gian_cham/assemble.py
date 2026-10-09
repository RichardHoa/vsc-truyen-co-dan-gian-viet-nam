"""Assemble the book: data/books/<book>/toc.json, notes.json and book.md.

book.md has the book title, then one `##` section per mục lục entry in
order: the Lời giới thiệu, then "## <n>. <title> (<subtitle>)" for each story,
cased like the mục lục row but spelled as the page heading prints it (the
heading as OCR read it is in the comment under it). Within a section:

  - paragraphs; one marked `continues` joins the paragraph before it (it
    carries on from the previous page);
  - dialogue lines keep their dash, escaped so Markdown doesn't make a list
    of them (`\\- Hơi con người…`);
  - a scene break is a `* * *` line;
  - centred lines inside a story (songs, chants) are kept one per line;
    in the Lời giới thiệu they are the signature, one paragraph each;
  - a note call becomes `[^id]` (the OCR junk that stood for it is removed;
    a call in the heading goes at the end of the heading line), and the
    section's notes are listed at its end;
  - rows the engines disagree on, or read with low confidence, end in ⚠;
    a drop cap whose letter isn't clear is marked `⚠ dropcap?`.

Text is never corrected: what OCR read stays as read.
"""

from __future__ import annotations

import re

from ...common import Book, write_json
from ...stream import Stream
from . import booktoc, notes as notes_mod
from .config import config

FLAG = " ⚠"
_md_start = re.compile(r"^(?=[-*+#>]|\d{1,4}[.)]\s|[=_]{3})")
_tag = re.compile(r"<(?=[A-Za-z/!])")


def _md(t: str) -> str:
    """Keep a paragraph from turning into a list item, heading or HTML."""
    return _md_start.sub("\\\\", _tag.sub("&lt;", t))


def _pages(a: int, b: int) -> str:
    return f"{a}" if a == b else f"{a}-{b}"


def _with_calls(text: str, spans) -> str:
    """Replace each call (or the junk OCR made of it) by `[^id]`."""
    for start, end, nid in sorted(spans, reverse=True):
        text = text[:start].rstrip() + f"[^{nid}]" + text[end:]
    return text


def _without_calls(text: str, spans) -> str:
    for start, end, _ in sorted(spans, reverse=True):
        text = text[:start].rstrip() + text[end:]
    return text


def _flag(s: dict) -> str:
    flags = set(s.get("flags", [])) - {"dropcap?"}
    return FLAG if flags else ""


class Section:
    def __init__(self, stream: Stream, calls: dict):
        self.stream, self.calls = stream, calls

    def render(self, positions: list, intro: bool) -> list[str]:
        out: list[str] = []
        lines: list[str] = []      # centred lines being collected
        last = None

        def flush():
            nonlocal lines
            if lines:
                out.append("  \n".join(lines))
                lines = []

        for n, i in positions:
            s = self.stream.segments(n)[i]
            if s["kind"] in ("footnote", "line_number"):
                continue
            t = _with_calls(s["text"], self.calls.get((n, i), []))
            if s["kind"] == "break":
                flush()
                out.append("* * *")
                last = "break"
                continue
            if s["kind"] == "heading" and not intro:
                lines.append(_md(t) + _flag(s))
                last = "line"
                continue
            flush()
            if "dropcap?" in s.get("flags", []):
                t = "⚠ dropcap? " + t
            t = _md(t) + _flag(s)
            if s.get("continues") and last == "paragraph" and out:
                prev = out[-1]
                if prev.endswith(FLAG):
                    prev = prev[: -len(FLAG)]
                    t = t if t.endswith(FLAG) else t + FLAG
                t = t[1:] if t.startswith("\\") else t
                if prev.endswith("-") and len(prev) > 1 and prev[-2].isalpha() and t[:1].islower():
                    out[-1] = prev + t        # a word split by a hyphen at the page break
                else:
                    out[-1] = prev + " " + t
            else:
                out.append(t)
            last = "paragraph"
        flush()
        return out


def assemble(book: Book, rerender: bool = True) -> dict:
    cfg = config(book)
    end_page = int(cfg.get("end_page") or book.page_count)
    stream = Stream(book, dict(skip_pages=cfg.get("skip_pages"), end_page=end_page))
    entries, problems = booktoc.build(book, stream, cfg)

    def owner_of(n: int) -> str:
        return next((e["id"] for e in entries if e["pdf_start"] <= n <= e["pdf_end"]), "front")

    heading_at = {p for e in entries for p in e["_heading"]}
    notes_out, calls = notes_mod.resolve(book, stream, owner_of, heading_at, rerender=rerender)

    # the heading without its call marks, then title / subtitle
    clean_heads = {e["id"]: [_without_calls(stream.segments(n)[i]["text"], calls.get((n, i), []))
                             for n, i in e["_heading"]] for e in entries}
    booktoc.finish_titles(entries, clean_heads)

    by_scope: dict = {}
    for note in notes_out:
        by_scope.setdefault(note["scope"], []).append(note)

    sec = Section(stream, calls)
    out = [f"# {cfg.get('title') or book.s['title']}"]
    if cfg.get("front"):
        out.append(f"<!-- {cfg['front']} -->")
    intro_id = (cfg.get("intro") or {}).get("id")
    for e in entries:
        intro = e["id"] == intro_id
        head_calls = [nid for p in e["_heading"] for _, _, nid in sorted(calls.get(p, []))]
        if intro:
            title = cfg["intro"].get("title") or e["title"]
        else:
            title = f"{e['number']}. {e['title']}" + (f" ({e['subtitle']})" if e.get("subtitle") else "")
        out.append(f"## {title}" + "".join(f"[^{x}]" for x in head_calls))
        comment = f"pdf {_pages(e['pdf_start'], e['pdf_end'])}"
        if e.get("heading_ocr") and not intro:
            comment += " · heading: " + " / ".join(clean_heads[e["id"]])
        out.append(f"<!-- {comment} -->")
        skip = set(e["_heading"])
        positions = [(n, i) for n in range(e["pdf_start"], e["pdf_end"] + 1) if n in stream.pages
                     for i in range(len(stream.segments(n))) if (n, i) not in skip]
        out += sec.render(positions, intro)
        for note in by_scope.get(e["id"], []):
            tail = f" <!-- note pdf {note['page']}" + ("" if note["call"] else " · call not found") + " -->"
            flag = FLAG if note.get("flags") or note.get("ocr_marker") else ""
            out.append(f"[^{note['id']}]: {_tag.sub('&lt;', note['text'])}{flag}{tail}")
    text = "\n\n".join(out).rstrip() + "\n"
    (book.dir / "book.md").write_text(text, encoding="utf-8")

    write_json(book.dir / "toc.json", dict(book=book.id, toc=booktoc.to_json(book, entries, cfg, end_page),
                                           disagreements=problems))
    counts: dict = {}
    for note in notes_out:
        counts.setdefault(note["scope"], {}).setdefault(note["status"], 0)
        counts[note["scope"]][note["status"]] += 1
    write_json(book.dir / "notes.json", dict(book=book.id, counts=counts, notes=notes_out))

    status: dict = {}
    for note in notes_out:
        status[note["status"]] = status.get(note["status"], 0) + 1
    print(f"  toc.json: {len(entries)} entries, {len(problems)} disagreement(s)")
    for p in problems:
        print(f"    - {p}")
    print(f"  notes.json: {len(notes_out)} notes: {status}")
    for note in notes_out:
        if note["status"] != "resolved":
            print(f"    - pdf {note['page']} ({note['marker']}) {note['status']}"
                  + (f": {note['call']['how']}" if note["call"] else ""))
    print(f"  book.md: {len(text.splitlines())} lines, {text.count(FLAG.strip())} ⚠, "
          f"{text.count('⚠ dropcap?')} unsure drop cap(s)")
    return dict(problems=problems, notes=notes_out)

