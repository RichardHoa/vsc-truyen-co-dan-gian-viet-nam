"""Assemble one book: data/books/<book>/toc.json, notes.json and book.md.

  toc.json   the mục lục nested and located in the body (see `booktoc`), with
             the disagreements against structure.yaml.
  notes.json every Chú thích note and the call that points to it (see `notes`).
  book.md    the parsed text in mục lục order: one heading per entry, nested
             like the mục lục, each followed by `<!-- pdf a-b -->`.

What goes in comes from assemble.yaml (front matter, skipped pages, which
version kinds are parsed, picture pages, ruled tables). Within a section:

  - prose segments become paragraphs; a paragraph marked `continues` joins
    the one before it (it carries on from the previous page);
  - verse lines are kept one per line, with a blank line at a stanza break;
  - literal translations keep their couplet numbers. OCR garbles some of
    them ("1ã. Thương với yêu", "683" for 63); a number that breaks the
    sequence is replaced by the one the sequence expects and marked ⚠, the
    text after it is left as read;
  - a note call becomes `[^id]` (the OCR junk that stood for it is removed)
    and the Chú thích block becomes the footnote definitions;
  - rows the engines disagree on, or read with low confidence, end in ⚠.

Text is never corrected: what OCR read stays as read.
"""

from __future__ import annotations

import re

from . import booktoc, notes as notes_mod, toc as toc_mod
from .booktoc import Stream, version_of, walk
from ...common import Book, from_ranges, write_json

FLAG = " ⚠"
_bullet = re.compile(r"^[-*]\s+")
# a misread couplet number left at the start of the line: "1ã. ", "58, ", "3... "
_garbled_no = re.compile(r"^(?P<tok>[^\s.,:;…]{1,3})\s*(?:[.,:;]+|…)\s+(?=\S)")
_lone_no = re.compile(r"^\W*(\d{1,4})\W*$")
_md_start = re.compile(r"^(?=[-*+#>]\s|\d{1,4}[.)]\s|[=_]{3})")
_tag = re.compile(r"<(?=[A-Za-z/!])")
_word = re.compile(r"[^\W\d_]{3}")


def _is_noise(t: str) -> bool:
    """Specks on the scan read as text ("~“ + Z* ~ ¿ z Z ^"): no word of
    three letters, and mostly not letters or digits."""
    chars = [c for c in t if not c.isspace()]
    return not _word.search(t) and sum(c.isalnum() for c in chars) < 0.7 * len(chars)


def _md_line(t: str) -> str:
    """Keep a verse line from turning into a list item, heading or HTML."""
    return _md_start.sub("\\\\", _tag.sub("&lt;", t))


def _pages(a: int, b: int) -> str:
    return f"{a}" if a == b else f"{a}-{b}"


# ---------------------------------------------------------------- sections

def _sections(root: dict, stream: Stream, images: set):
    """(entry, [(page, i), ...]) in mục lục order; the root's list is the front
    matter. A segment belongs to the last entry located at or before it."""
    entries = list(walk(root))
    owner_at = {}
    for e in entries[1:]:
        if e.get("_pos") and not e.get("image"):
            owner_at[e["_pos"]] = e   # entries sharing a place: the innermost (last) one owns it
    content = {id(e): [] for e in entries}
    current = root
    for n in stream.order:
        if n in images:
            continue
        for i, _ in enumerate(stream.segments(n)):
            current = owner_at.get((n, i), current)
            content[id(current)].append((n, i))
    return [(e, content[id(e)]) for e in entries]


def _skipped(root: dict) -> set:
    """Segments that are an entry's own heading, or a running title above it."""
    out = set()
    for e in walk(root):
        if e.get("_heading"):
            out.add(e["_heading"])
        out.update(e.get("_drop", []))
    return out


# ---------------------------------------------------------------- text

def _with_calls(text: str, spans) -> str:
    """Replace each call (or the junk OCR made of it) by `[^id]`."""
    for start, end, nid in sorted(spans, reverse=True):
        text = text[:start].rstrip() + f"[^{nid}]" + text[end:]
    return text


def _number_couplets(lines: list[dict]) -> list[dict]:
    """Set line['num'] on the first line of each couplet. Returns the lines
    whose number was repaired from the sequence (they get ⚠).

    A number read by OCR is kept when it is the one expected, or close to it
    and followed by the next one (numbers were lost before it). Otherwise
    the sequence decides: "683" between 62 and 64 is 63. A first line whose
    number OCR garbled ("1ã. Thương...") or dropped gets the expected one,
    the latter only when the lines up to the next number read leave room for
    exactly the couplets missing."""
    raw = [ln.get("line_no") for ln in lines]
    repaired = []
    expected, since = 1, None   # since: lines since the last numbered one

    def next_read(k):
        return next(((j, v) for j, v in enumerate(raw[k + 1:], k + 1) if v is not None), (None, None))

    def mark(ln, num):
        ln["num"], ln["repaired"] = num, True
        repaired.append(ln)

    out = []
    for k, ln in enumerate(lines):
        if ln["kind"] == "line_number":
            v = ln["line_no"]
            # a number OCR put after the line it belongs to
            if out and out[-1].get("num") is None and out[-1].get("due") and v is not None:
                if v == expected:
                    out[-1]["num"] = v
                else:
                    mark(out[-1], expected)
                expected, since = expected + 1, 1
            else:
                ln["pending"] = v
                out.append(ln)
            continue
        pending = out[-1].pop("pending", None) if out and out[-1]["kind"] == "line_number" else None
        n = ln.get("line_no") if ln.get("line_no") is not None else pending
        due = since is None or since >= 2
        ln["due"] = due
        if n is not None:
            _, nxt = next_read(k)
            if n == expected or (0 < n - expected <= 5 and nxt in (None, n + 1)):
                ln["num"] = n
            else:
                mark(ln, expected)
            expected, since = ln["num"] + 1, 1
        elif due:
            m = _garbled_no.match(ln["text"])
            if m:
                ln["text"] = ln["text"][m.end():]
                mark(ln, expected)
            else:
                j, nxt = next_read(k)
                missing = nxt - expected if nxt is not None else 0
                between = [x for x in lines[k:j] if x["kind"] != "line_number"]
                garbled = sum(1 for x in between if _garbled_no.match(x["text"]))
                if 0 < missing <= 10 and garbled == 0 and len(between) >= 2 * missing:
                    mark(ln, expected)   # number not read at all
            if ln.get("num") is not None:
                expected, since = expected + 1, 1
            elif since is not None:
                since += 1
        else:
            since += 1
        out.append(ln)
    return repaired


class Section:
    """Markdown blocks for one entry's segments."""

    def __init__(self, book: Book, stream: Stream, calls: dict, block_at: dict, tables: dict):
        self.book, self.stream, self.calls, self.block_at, self.tables = book, stream, calls, block_at, tables
        self.repaired: list[dict] = []
        self.noise: list = []

    def text(self, pos) -> str:
        s = self.stream.segments(pos[0])[pos[1]]
        t = _with_calls(s["text"], self.calls.get(pos, []))
        return t + (FLAG if s.get("flags") else "")

    def render(self, positions: list) -> list[str]:
        out: list[str] = []
        verse: list[str] = []        # the verse block being built
        couplets: list[dict] = []    # literal-translation lines being collected
        last_kind = None

        def flush():
            nonlocal verse, couplets
            if verse:
                out.append("\n".join(f"{_md_line(v)}  " for v in verse).rstrip())
                verse = []
            if couplets:
                self.repaired += _number_couplets(couplets)
                cur: list[str] = []
                for ln in couplets:
                    if ln["kind"] == "line_number":
                        continue
                    t = _md_line(ln["text"]) + (FLAG if ln["flags"] or ln.get("repaired") else "")
                    if ln.get("num") is not None:
                        if cur:
                            out.append("  \n".join(cur))
                        cur = [f"{ln['num']}\\. {_tag.sub('&lt;', ln['text'])}" + (FLAG if ln["flags"] or ln.get("repaired") else "")]
                    else:
                        cur.append(t)
                if cur:
                    out.append("  \n".join(cur))
                couplets = []

        for pos in positions:
            n, i = pos
            if pos in self.block_at:
                flush()
                out.append(self.block_at[pos])
                last_kind = "notes"
                continue
            if pos in self.tables:
                flush()
                if self.tables[pos]:
                    out.append(self.tables[pos])
                last_kind = "table"
                continue
            s = self.stream.segments(n)[i]
            if s.get("flags") and _is_noise(s["text"]):
                self.noise.append(pos)   # specks on the scan read as "~“ + Z* ~"
                continue
            v = version_of(self.book, n)
            kind = v["kind"] if v else None
            if kind == "literal-translation":
                if s["kind"] == "line_number":
                    m = _lone_no.match(s["text"])
                    couplets.append(dict(kind="line_number", line_no=int(m.group(1)) if m else None,
                                         text="", flags=[], page=n, read=s["text"]))
                else:
                    t = _with_calls(s["text"], self.calls.get(pos, []))
                    couplets.append(dict(kind="verse", line_no=s.get("line_no"), text=t,
                                         flags=s.get("flags", []), page=n, read=s["text"]))
                continue
            if s["kind"] == "line_number":
                continue
            t = self.text(pos)
            if s["kind"] == "verse":
                if s.get("stanza_break") and verse:
                    flush()
                if s.get("line_no") is not None:
                    t = f"{s['line_no']}. {t}"
                verse.append(t)
                last_kind = "verse"
            elif s["kind"] == "speaker":
                if s.get("stanza_break") and verse:
                    flush()
                verse.append(f"**{t.rstrip(FLAG)}**" + (FLAG if s.get("flags") else ""))
                last_kind = "verse"
            elif s["kind"] == "heading" and kind == "verse-translation":
                verse.append(t)   # a short centred verse line, not a heading
            elif s["kind"] == "heading":
                flush()
                out.append(f"**{t.rstrip(FLAG)}**" + (FLAG if s.get("flags") else ""))
                last_kind = "heading"
            else:  # paragraph, footnote
                flush()
                if s.get("continues") and last_kind == "paragraph" and out:
                    prev = out[-1]
                    if prev.endswith(FLAG):
                        prev = prev[: -len(FLAG)]
                        t = t if t.endswith(FLAG) else t + FLAG
                    if prev.endswith("-") and len(prev) > 1 and prev[-2].isalpha() and t[:1].islower():
                        out[-1] = prev + t
                    else:
                        out[-1] = prev + " " + t
                else:
                    out.append(t)
                last_kind = "paragraph"
        flush()
        return out


# ---------------------------------------------------------------- notes, tables

def _definitions(blocks: list[dict], notes_out: list[dict]) -> tuple[dict, set]:
    """{block start: markdown of its definitions}, and every segment of a block."""
    by_id = {n["id"]: n for n in notes_out}
    at, inside = {}, set()
    for b in blocks:
        inside.add(b["start"])
        lines = ["**Chú thích:**", ""]
        for note in b["notes"]:
            inside.update(note["pos"])
            e = by_id[f"{b['scope']}-{note['number']}"]
            pages = _pages(min(e["note_pdf_pages"]), max(e["note_pdf_pages"]))
            where = f"called on pdf {e['call']['pdf_page']}" if e["call"] else "call not found"
            flag = FLAG if e.get("flags") or e.get("ocr_number") else ""
            lines.append(f"[^{e['id']}]: {_tag.sub('&lt;', e['text'])}{flag} <!-- note pdf {pages} · {where} -->")
        at[b["start"]] = "\n".join(lines)
    return at, inside


def _tables(book: Book, stream: Stream, cfg: dict) -> tuple[dict, set, list[str]]:
    """{first segment inside a table: markdown or ''}, the segments it
    replaces, and a log line per page."""
    from ...ocr_tesseract import _check
    from .tables import read_table, to_markdown
    from PIL import Image

    at, inside, log = {}, set(), []
    specs = cfg.get("tables") or []
    if not specs:
        return at, inside, log
    exe = _check()
    for spec in specs:
        pages = [n for n in from_ranges(spec["pages"]) if n in stream.pages]
        failed, header = [], None
        for n in pages:
            path = book.render_path(n)
            res = read_table(Image.open(path), exe, spec.get("drop_columns") or []) if path.exists() else None
            segs = stream.segments(n)
            if res:
                x0, y0, x1, y1 = res["bbox"]
                # a table carried on from the page before has no header row: repeat it
                if header is None:
                    header = res["rows"][0]
                elif booktoc._similar(" ".join(res["rows"][0]), " ".join(header)) < 0.5:
                    res["rows"].insert(0, header)
                hit = [(n, i) for i, s in enumerate(segs)
                       if y0 - 0.01 <= (s["bbox"][1] + s["bbox"][3]) / 2 <= y1 + 0.01]
                body = to_markdown(res["rows"])
                note = f"<!-- table read cell by cell from pdf {n}"
                if spec.get("drop_columns"):
                    note += f"; column {', '.join(map(str, spec['drop_columns']))} (Cham script) left out"
                md = note + " -->\n\n" + body
                log.append(f"pdf {n}: table {len(res['rows'])} rows x {len(res['rows'][0])} columns")
            else:
                hit = [(n, i) for i in range(len(segs))]
                failed.append(n)
                md = ""
                log.append(f"pdf {n}: no table grid found")
            if hit:
                inside.update(hit)
                at[hit[0]] = md
        if failed:
            first = next((p for p in sorted(at) if p[0] == failed[0]), None)
            if first is not None:
                at[first] = f"<!-- table not parsed, see pdf {spec['pages']} -->"
    return at, inside, log


# ---------------------------------------------------------------- book

def assemble(book: Book, rerender: bool = True) -> dict:
    cfg = booktoc.config(book)
    stream = Stream(book, cfg)
    convert, _ = toc_mod.printed_to_pdf(book)
    root, problems = booktoc.build(book, stream, convert)
    notes_out, calls, blocks = notes_mod.resolve(book, stream, root, cfg, rerender=rerender)
    defs, in_blocks = _definitions(blocks, notes_out)
    table_at, in_tables, table_log = _tables(book, stream, cfg)
    images = {int(k) for k in (cfg.get("images") or {})}
    front = set(from_ranges(cfg.get("front_matter")))
    skip = _skipped(root) | (in_blocks - set(defs)) | (in_tables - set(table_at))
    block_at = dict(defs)

    sec = Section(book, stream, calls, block_at, table_at)
    out = []
    for e, positions in _sections(root, stream, images):
        if not e.get("parse", True):
            continue
        level = e["level"] + 1
        title = _bullet.sub("", e["title"])
        out.append(f"{'#' * min(level, 6)} {title}")
        out.append(f"<!-- pdf {_pages(e['pdf_start'], e['pdf_end'])} -->")
        if e.get("image"):
            out.append(f"<!-- image not parsed, see pdf {e['image']} -->")
            continue
        if e is root:
            positions = [p for p in positions if p[0] in front]
        out += sec.render([p for p in positions if p not in skip])
    text = "\n\n".join(out).rstrip() + "\n"
    (book.dir / "book.md").write_text(text, encoding="utf-8")

    write_json(book.dir / "toc.json", dict(book=book.id, toc=booktoc.to_json(root), disagreements=problems))
    counts: dict = {}
    for n in notes_out:
        counts.setdefault(n["scope"], {}).setdefault(n["status"], 0)
        counts[n["scope"]][n["status"]] += 1
    write_json(book.dir / "notes.json", dict(book=book.id, counts=counts, notes=notes_out))

    flagged = text.count(FLAG.strip())
    print(f"  toc.json: {sum(1 for _ in walk(root)) - 1} entries, {len(problems)} disagreement(s)")
    for p in problems:
        print(f"    - {p}")
    print(f"  notes.json: {len(notes_out)} notes in {len(blocks)} block(s): {counts}")
    for line in table_log:
        print(f"  {line}")
    print(f"  book.md: {len(text.splitlines())} lines, {flagged} ⚠, {len(sec.repaired)} couplet number(s) repaired, "
          f"{len(sec.noise)} flagged row(s) without a word left out")
    return dict(problems=problems, notes=notes_out, repaired=sec.repaired, noise=sec.noise, tables=table_log)
