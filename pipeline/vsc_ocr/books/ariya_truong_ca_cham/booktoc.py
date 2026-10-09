"""Turn the parsed mục lục (toc.generated.yaml) into toc.json: the book's
outline, nested like the printed mục lục, with PDF page ranges.

  1. Nesting comes from each row's marker, not its indent (indents drift from
     page to page): A./B./C. and "* ..." rows are sections, I./II. and rows in
     capitals (the epics) sit below them, then 1./2., then a./b.; "- ..." rows
     sit below the row above. OCR misreads of the markers ("Ï." for I., "l."
     for 1., "II." for a third III.) are fixed from the sequence of siblings;
     the row as read is kept in `ocr_title`.
  2. Every entry is located in the body: its heading is looked up in the
     cleaned pages (on its printed page when the mục lục gives one, else
     between its neighbours). That gives `pdf_start`; `pdf_end` is the page
     before the next entry that isn't inside it (or the same page when that
     entry starts mid-page).
  3. `parse` follows the version kinds in assemble.yaml, and the version rows
     are cross-checked against structure.yaml. Disagreements are listed in
     toc.json, never resolved silently.
"""

from __future__ import annotations

import difflib
import re

from ...common import Book, from_ranges, nfc, read_json, read_yaml, slugify, strip_diacritics

ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10}
_marker = re.compile(r"^(?P<m>[A-ZĐa-zđ]|[IVXÏÌl|]{1,4}|\d{1,3})\s*[.,:)]\s+(?P<rest>\S.*)$")


def config(book: Book) -> dict:
    p = book.dir / "assemble.yaml"
    return read_yaml(p) if p.exists() else {}


def version_of(book: Book, n: int) -> dict | None:
    """The work version (structure.yaml) a page belongs to, if any."""
    for work in book.s.get("works", []):
        for v in work.get("versions", []):
            if n in from_ranges(v.get("pages")):
                return v
    return None


def norm(s: str) -> str:
    """Comparison key: no diacritics, case, punctuation or spaces."""
    return re.sub(r"[^a-z0-9]", "", strip_diacritics(nfc(s)).casefold())


def _similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, norm(a), norm(b), autojunk=False).ratio()


# ---------------------------------------------------------------- 1. nesting

def _classify(e: dict) -> tuple[str, str | None, str]:
    """(type, marker as read, title without marker)."""
    if e.get("item") is not None:
        return "arabic", str(e["item"]), e["title"]
    if e.get("bullet") == "*":
        return "star", None, e["title"]
    if e.get("bullet"):
        return "dash", None, e["title"]
    m = _marker.match(e["title"])
    if m:
        tok, rest = m.group("m"), m.group("rest")
        if tok in ROMAN or set(tok) <= set("IVXÏÌl|"):
            return "roman-ish", tok, rest
        if tok.isupper():
            return "letter", tok, rest
        return "lower", tok, rest
    letters = [c for c in e["title"] if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.8:
        return "caps", None, e["title"]
    return "plain", None, e["title"]


def _roman(n: int) -> str:
    return {v: k for k, v in ROMAN.items()}[n]


def nest(rows: list[dict], title_rows: int) -> dict:
    """Flat mục lục rows -> {'title', 'children': [...]} with levels."""
    title = " – ".join(r["title"] for r in rows[:title_rows])
    root = dict(title=title, level=0, printed_page=None, children=[])
    rows = rows[title_rows:]
    stack = [root]          # stack[k] = latest entry at level k
    last_num: dict[tuple[int, str], int] = {}  # (parent id, kind) -> last value

    def parent_at(level):
        while len(stack) > level:
            stack.pop()
        return stack[-1]

    typed = [_classify(r) for r in rows]
    prev_level = 0
    for i, (r, (kind, tok, rest)) in enumerate(zip(rows, typed)):
        if kind == "roman-ish":
            # "I." right below an epic or a roman section is the arabic 1.
            kind = "arabic" if len(tok) == 1 and prev_level == 2 else "roman"
        if kind in ("letter", "star"):
            level = 1
        elif kind in ("roman", "caps"):
            level = 2
        elif kind == "arabic":
            level = 3
        elif kind == "lower":
            level = 4
        elif kind == "dash":
            level = prev_level + 1 if typed[i - 1][0] != "dash" else prev_level
        else:  # unmarked mixed-case row: a sibling of the row after it
            nxt = typed[i + 1][0] if i + 1 < len(typed) else "plain"
            level = {"arabic": 3, "roman-ish": 3, "lower": 4}.get(nxt, 1) if prev_level >= 1 else 1
        level = min(level, len(stack))  # never skip a level
        parent = parent_at(level)
        e = dict(title=r["title"], level=level, printed_page=r.get("printed_page"))
        if kind == "plain" and level == 3:
            # a row printed without its number ("Xác định ..." before "2. Về
            # thể thơ"): it still takes its place in the sequence
            last_num[(id(parent), "arabic")] = last_num.get((id(parent), "arabic"), 0) + 1
        # markers run in sequence under one parent: fix misreads from it
        key = (id(parent), kind)
        if kind in ("roman", "arabic", "lower", "letter"):
            expected = last_num.get(key, 0) + 1
            if kind == "roman":
                value = ROMAN.get(tok.replace("Ï", "I").replace("Ì", "I").replace("l", "I").replace("|", "I"))
                fixed = f"{_roman(expected)}. {rest}"
            elif kind == "arabic":
                value = int(tok) if tok.isdigit() else 1
                fixed = f"{expected}. {r['title'] if r.get('item') is not None else rest}"
            else:
                base = "a" if kind == "lower" else "A"
                value = ord(tok.replace("đ", "d").replace("Đ", "D")) - ord(base) + 1
                fixed = f"{chr(ord(base) + expected - 1)}. {rest}"
            last_num[key] = expected
            ocr = r["title"] if kind != "arabic" or r.get("item") is None else f"{r['item']}. {r['title']}"
            if value != expected or nfc(fixed) != nfc(ocr):
                e["ocr_title"] = ocr
            e["title"] = fixed
        elif kind == "dash":
            e["title"] = "- " + r["title"]
        elif kind == "star":
            e["title"] = "* " + r["title"]
        e["children"] = []
        parent["children"].append(e)
        stack.append(e)
        prev_level = level
    return root


def walk(entry: dict):
    """Entries in reading order (pre-order), the root included."""
    yield entry
    for c in entry.get("children", []):
        yield from walk(c)


# ---------------------------------------------------------------- 2. locating

class Stream:
    """The cleaned segments of the book's text pages, in reading order."""

    def __init__(self, book: Book, cfg: dict):
        self.book = book
        skip = set(from_ranges(cfg.get("skip_pages")))
        end = int(cfg.get("end_page") or book.page_count)
        self.pages: dict[int, dict] = {}
        for n in range(1, end + 1):
            p = book.page_path(n)
            if n not in skip and p.exists():
                self.pages[n] = read_json(p)
        self.order = sorted(self.pages)

    def segments(self, n: int) -> list[dict]:
        return self.pages[n]["segments"] if n in self.pages else []


_lead = re.compile(r"^\W*([A-ZĐa-zđ]|[IVXÏÌlL|]{1,4}|\d{1,3})\s*[.,:)]\s*")


def _heading_score(title: str, text: str) -> float:
    """How well a body row matches a mục lục title (markers ignored)."""
    t = norm(_lead.sub("", title.lstrip("-* ")))
    s = norm(_lead.sub("", text))
    if not t or not s:
        return 0.0
    if len(s) > 1.6 * len(t) + 12:
        s = s[: len(t)]  # a heading glued to the start of its paragraph
    score = difflib.SequenceMatcher(None, t, s, autojunk=False).ratio()
    if len(s) < len(t) and len(s) >= max(8, 0.35 * len(t)):
        # a long heading wrapped onto a second row: compare the first part
        score = max(score, difflib.SequenceMatcher(None, t[: len(s)], s, autojunk=False).ratio())
    return score


def find_heading(stream: Stream, title: str, pages, after=None, threshold=0.8):
    """Best (page, segment index) for a title on the given pages, after `after`."""
    best, best_score = None, threshold
    for n in pages:
        for i, s in enumerate(stream.segments(n)):
            if after is not None and (n, i) <= after:
                continue
            if s["kind"] in ("footnote", "line_number"):
                continue
            score = _heading_score(title, s["text"])
            if s["kind"] == "heading":
                score += 0.05
            if score > best_score:
                best, best_score = (n, i), score
    return best


def _ancestors(root: dict, target: dict) -> list[dict]:
    path: list[dict] = []

    def go(e):
        if e is target:
            return True
        path.append(e)
        if any(go(c) for c in e.get("children", [])):
            return True
        path.pop()
        return False
    go(root)
    return path


def _absorb_running_titles(stream: Stream, hit, titles: list[str], taken: set):
    """A version's first page often repeats the work's title above the
    version heading ("ARIYA CAM - BINI" / "Dịch nghĩa"). Those rows belong to
    the version, not to the end of the previous section: move the cut to the
    top of the page and mark them to be dropped."""
    n, i = hit
    segs = stream.segments(n)
    lead = list(range(i))
    if not lead or any((n, j) in taken for j in lead):
        return hit, []
    for j in lead:
        if segs[j]["kind"] != "heading" or max((_similar(segs[j]["text"], t) for t in titles), default=0) < 0.6:
            return hit, []
    return (n, 0), [(n, j) for j in lead]


def _find_marker(stream: Stream, title: str, pages, after):
    """Fallback for a heading whose words OCR garbled ("b. Bừưntt:" for
    "b. Bini"): the first short row starting with the same marker."""
    m = _marker.match(title)
    if not m:
        return None
    want = m.group("m").casefold()
    for n in pages:
        for i, s in enumerate(stream.segments(n)):
            if after is not None and (n, i) <= after:
                continue
            sm = _marker.match(s["text"].strip())
            if sm and sm.group("m").casefold() == want and len(s["text"].split()) <= 4:
                return (n, i)
    return None


def locate(root: dict, stream: Stream, convert, cfg: dict | None = None) -> None:
    """Set entry['_pos'] = (page, segment index) and entry['located'] (how)."""
    cfg = cfg or {}
    images = {int(k): v for k, v in (cfg.get("images") or {}).items()}
    entries = list(walk(root))[1:]
    taken: set = set()
    printed = [convert(e["printed_page"]) if e["printed_page"] else None for e in entries]
    after = None
    for k, e in enumerate(entries):
        page = printed[k]
        image = next((n for n, cap in images.items() if _similar(cap, e["title"].lstrip("-* ")) >= 0.8), None)
        if image is not None:
            e["_pos"], e["located"], e["image"] = (image, 0), "image page", image
        elif page is not None:
            e["_toc_pdf"] = page
            hit = find_heading(stream, e["title"], [p for p in (page, page + 1, page - 1) if p in stream.pages],
                               after=None, threshold=0.75)
            if hit:
                e["_pos"], e["located"] = hit, "heading on its printed page"
            else:
                e["_pos"], e["located"] = (page, 0), "printed page"
        else:
            # between the previous located entry and the next one with a page
            lo = after[0] if after else stream.order[0]
            hi = next((p for p in printed[k + 1:] if p is not None), stream.order[-1])
            window = [n for n in stream.order if lo <= n <= hi]
            hit = find_heading(stream, e["title"], window, after=after)
            if hit:
                e["_pos"], e["located"] = hit, "heading in the body"
            else:
                hit = _find_marker(stream, e["title"], window, after)
                if hit:
                    e["_pos"], e["located"] = hit, "marker only (title unreadable)"
        if e.get("_pos") and e["located"].startswith(("heading", "marker")):
            e["_heading"] = e["_pos"]   # the heading row itself
        if e.get("_pos") and e["located"].startswith("heading"):
            anc = _ancestors(root, e)
            titles = [a["title"] for a in anc if a is not root]
            titles += [w["title"] for a in anc for w in stream.book.s.get("works", []) if w["id"] == a.get("work")]
            titles += [part for w in stream.book.s.get("works", []) for part in re.split(r"[()]", w["title"]) if part.strip()]
            e["_pos"], dropped = _absorb_running_titles(stream, e["_pos"], titles, taken)
            if dropped:
                e["_drop"] = dropped
        if e.get("_pos") and not e.get("image"):  # a picture can be printed out of order
            taken.add(e["_pos"])
            after = e["_pos"]

    # entries not found: a group takes its first child's place, anything else
    # the place of the entry before it (zero length, reported as unlocated)
    for e in reversed(entries):
        if not e.get("_pos"):
            kids = [c for c in walk(e) if c is not e and c.get("_pos")]
            if kids:
                e["_pos"], e["located"] = kids[0]["_pos"], "first child"
    prev = None
    for e in entries:
        if not e.get("_pos"):
            e["_pos"], e["located"] = (prev or (stream.order[0], 0)), "not found"
        prev = e["_pos"]


def set_ranges(root: dict, stream: Stream, end_page: int) -> None:
    entries = list(walk(root))[1:]
    root["pdf_start"] = min(stream.order)
    root["pdf_end"] = end_page
    for k, e in enumerate(entries):
        e["pdf_start"] = e["_pos"][0]
        inside = {id(c) for c in walk(e)}
        nxt = next((o for o in entries[k + 1:] if id(o) not in inside), None)
        if nxt is None:
            e["pdf_end"] = end_page
        else:
            n, i = nxt["_pos"]
            e["pdf_end"] = max(e["pdf_start"], n if i > 0 else n - 1)


# ---------------------------------------------------------------- 3. parse + check

def _version_kinds(title: str, cfg: dict) -> list[str] | None:
    key = norm(title.lstrip("-* "))
    for prefix, kinds in (cfg.get("version_rows") or {}).items():
        if key.startswith(norm(prefix)):
            return list(kinds)
    return None


def _match_work(title: str, works: list[dict]) -> dict | None:
    key = norm(title)
    for w in works:
        if key and key in norm(w["title"]):
            return w
    best, score = None, 0.7
    for w in works:
        for part in re.split(r"[()]", w["title"]):
            r = _similar(title, part)
            if r > score:
                best, score = w, r
    return best


def classify(root: dict, book: Book, cfg: dict) -> list[str]:
    parse_kinds = set(cfg.get("parse_kinds") or [])
    works = book.s.get("works", [])
    problems: list[str] = []
    for e in walk(root):
        kinds = _version_kinds(e["title"], cfg) if e is not root else None
        if kinds:
            e["kinds"] = kinds
            e["parse"] = any(k in parse_kinds for k in kinds)
    for e in walk(root):
        kids = e.get("children", [])
        if any("kinds" in c for c in kids):
            w = _match_work(e["title"], works)
            if w:
                e["work"] = w["id"]
                for c in kids:
                    if "kinds" not in c:
                        continue
                    pages = sorted({n for v in w["versions"] if v["kind"] in c["kinds"]
                                    for n in from_ranges(v["pages"])})
                    if not pages:
                        if c["parse"]:
                            problems.append(f"{e['title']} / {c['title']}: no {c['kinds']} version in structure.yaml")
                        continue
                    if (pages[0], pages[-1]) != (c["pdf_start"], c["pdf_end"]):
                        problems.append(
                            f"{e['title']} / {c['title']}: mục lục gives pdf {c['pdf_start']}-{c['pdf_end']}, "
                            f"structure.yaml {'+'.join(c['kinds'])} {pages[0]}-{pages[-1]}")
                kinds_here = {k for c in kids for k in c.get("kinds", [])}
                for v in w["versions"]:
                    if v["kind"] not in kinds_here:
                        problems.append(f"{e['title']}: structure.yaml {v['kind']} {v['pages']} has no mục lục row")
                first = min(n for v in w["versions"] for n in from_ranges(v["pages"]))
                if e.get("_toc_pdf") and e["_toc_pdf"] != first:
                    problems.append(f"{e['title']}: mục lục page {e['printed_page']} is pdf {e['_toc_pdf']}, "
                                    f"but structure.yaml starts the work on pdf {first}")
            else:
                problems.append(f"{e['title']}: no matching work in structure.yaml")
    # groups follow their contents; everything else is parsed
    for e in reversed(list(walk(root))):
        if "parse" not in e:
            kids = e.get("children", [])
            e["parse"] = any(c["parse"] for c in kids) if any("kinds" in c for c in kids) else True
    return problems


def build(book: Book, stream: Stream, convert) -> tuple[dict, list[str]]:
    cfg = config(book)
    gen = read_yaml(book.dir / "toc.generated.yaml")
    root = nest(gen["entries"], int(cfg.get("toc_title_rows", 0)))
    locate(root, stream, convert, cfg)
    set_ranges(root, stream, int(cfg.get("end_page") or book.page_count))
    problems = classify(root, book, cfg)
    for e in walk(root):
        if e.get("located") == "not found":
            problems.append(f"{e['title']}: heading not found in the body; pdf_start copied from the entry before")
    return root, problems


def to_json(root: dict) -> dict:
    """Drop working fields; ids are slugs of the title path."""
    def clean(e, path):
        slug = slugify(_lead.sub("", e["title"].lstrip("-* "))) or "entry"
        eid = "-".join(path + [slug]) if path else slug
        out = dict(id=eid, title=e["title"], level=e["level"], printed_page=e.get("printed_page"),
                   pdf_start=e.get("pdf_start"), pdf_end=e.get("pdf_end"), parse=e.get("parse", True))
        for k in ("ocr_title", "kinds", "work", "located"):
            if e.get(k):
                out[k] = e[k]
        kids = e.get("children", [])
        if kids:
            out["children"] = [clean(c, path + [slug] if e["level"] else []) for c in kids]
        return out
    return clean(root, [])
