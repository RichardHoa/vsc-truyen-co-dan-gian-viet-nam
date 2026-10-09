"""Decorative drop caps: the Lời giới thiệu and every story open with a large
ornamental capital spanning two lines ("C" + "ứ theo truyền thuyết...",
"V" + "ua Itá Ita..."). The capital has no diacritic; the marks sit on the
body-type letters after it.

OCR drops the capital, reads it as junk ("1)", "\\wW", "lên") or glues it to
either line ("Xlàm gì cả"). So, on a section's first page:

  1. find the capital on the 300 dpi render: one tall ink blob (about two
     rows high) at the left margin, beside the first rows of the section;
  2. re-read the two rows to the right of it with Tesseract (`psm 6`), which
     can't see the capital, and align that reading with the OCR rows: what
     the OCR put before the first words both agree on is the capital's
     doing and is removed (replaced by the re-read words when the OCR
     garbled them, flagged `dropcap-reread`);
  3. pick the capital: the letter that turns the first word's fragment into
     the word this book uses most (counted over all its OCR text, with the
     next word as context). When no letter clearly wins, the fragment is
     left as it is and flagged `dropcap?`.

The capital's crop and the re-read rows are saved to
data/ocr/<book>/dropcaps/ for checking against the scan.
"""

from __future__ import annotations

import difflib
import re
from collections import Counter

from PIL import Image, ImageOps

from ...common import OCR_DIR, Book, nfc, strip_diacritics
from ...layout import median_height
from ...vietnamese import is_vietnamese_syllable, strip_tones

INK = 140
SCALE = 2                   # components are found on the render shrunk by this
LETTERS = "ABCDĐEGHIKLMNOPQRSTUVXY"
# a lowercase letter that can follow each capital in a word ("Th", "Ng"...)
CLUSTERS = {"C": "h", "G": "hi", "K": "h", "N": "gh", "P": "h", "T": "hr", "Q": "u"}
_word = re.compile(r"[^\W\d_]+")
_first = re.compile(r"^(\W*)([^\W\d_]*)(.*)$")


# ---------------------------------------------------------------- 1. the glyph

def _components(img: Image.Image, box) -> list[dict]:
    """The 8-connected ink components inside box: {'bbox': [x0, y0, x1, y1],
    'pixels': [(x, y), ...]}, in pixels of `img`."""
    x0, y0, x1, y1 = box
    crop = img.crop(box)
    w, h = crop.size
    bits = ImageOps.invert(crop.convert("L")).point(lambda v: 1 if v > 255 - INK else 0)
    px = list(bits.getdata())
    seen = bytearray(w * h)
    out = []
    for start in range(w * h):
        if not px[start] or seen[start]:
            continue
        stack, pixels = [start], []
        seen[start] = 1
        while stack:
            k = stack.pop()
            y, x = divmod(k, w)
            pixels.append((x + x0, y + y0))
            for dy in (-1, 0, 1):
                yy = y + dy
                if not 0 <= yy < h:
                    continue
                for dx in (-1, 0, 1):
                    xx = x + dx
                    if 0 <= xx < w:
                        j = yy * w + xx
                        if px[j] and not seen[j]:
                            seen[j] = 1
                            stack.append(j)
        xs = [p[0] for p in pixels]
        ys = [p[1] for p in pixels]
        out.append(dict(bbox=[min(xs), min(ys), max(xs) + 1, max(ys) + 1], pixels=pixels))
    return out


def find_glyph(img: Image.Image, rows: list[dict]) -> dict | None:
    """The drop cap beside the first rows of a section: {'bbox': normalised
    [x0, y0, x1, y1], 'pixels': its ink, in pixels of `img`}, or None."""
    body = [r for r in rows if r["text"].strip()]
    if len(body) < 3:
        return None
    h = median_height(body)
    left = sorted(r["bbox"][0] for r in body)[len(body) // 10]
    small = img.resize((img.width // SCALE, img.height // SCALE), Image.BOX)
    W, H = small.size
    for r in body[:10]:
        if r["bbox"][1] > 0.65:
            break
        box = (max(0, int((left - 0.06) * W)), max(0, int((r["bbox"][1] - 1.0 * h) * H)),
               int(min(0.45, left + 0.25) * W), min(H, int((r["bbox"][1] + 3.2 * h) * H)))
        comps = _components(small, box)
        tall = [c for c in comps
                if (c["bbox"][3] - c["bbox"][1]) / H >= 1.6 * h and (c["bbox"][2] - c["bbox"][0]) / W <= 0.2
                and c["bbox"][0] / W <= left + 0.04]
        if not tall:
            continue
        main = max(tall, key=lambda c: c["bbox"][3] - c["bbox"][1])
        g, pixels = list(main["bbox"]), list(main["pixels"])
        # an ornate capital can come in pieces: take the ones inside its box
        for c in comps:
            b = c["bbox"]
            inside_x = min(b[2], g[2]) - max(b[0], g[0]) >= 0.5 * (b[2] - b[0])
            if c is not main and inside_x and b[1] >= g[1] - 2 and b[3] <= g[3] + 2:
                g = [min(g[0], b[0]), min(g[1], b[1]), max(g[2], b[2]), max(g[3], b[3])]
                pixels += c["pixels"]
        return dict(bbox=[g[0] / W, g[1] / H, g[2] / W, g[3] / H],
                    pixels=[(x * SCALE + dx, y * SCALE + dy) for x, y in pixels
                            for dx in range(-1, SCALE + 1) for dy in range(-1, SCALE + 1)])
    return None


# ---------------------------------------------------------------- 2. the rows

def _words(text: str) -> list[str]:
    return text.split()


def _key(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", strip_diacritics(nfc(w)).casefold())


def realign(ocr: str, ref: str, touches: bool) -> tuple[str, str | None, bool]:
    """(row text without what the capital caused, junk removed, re-read?).

    Tokens without a letter at the start of the row ("1)", ">") are the
    capital read as junk. Then the first stretch of words both readings share
    anchors them, and what the OCR has before it is compared with the re-read
    row (which can't contain the capital): a stray token or glued letters are
    dropped; words the OCR lost are put back from the re-read. Words that
    differ otherwise are replaced only when the OCR row reaches into the
    capital (`touches`); else the OCR reading stands."""
    P, R = _words(ocr), _words(ref)
    junk = []
    while P and not _word.search(P[0]):
        junk.append(P.pop(0))
    while R and not _word.search(R[0]):
        R.pop(0)  # specks of the capital at the crop's edge
    cut = " ".join(junk) or None
    if not P or not R:
        return " ".join(P), cut, False
    sm = difflib.SequenceMatcher(None, [_key(w) for w in P], [_key(w) for w in R], autojunk=False)
    blocks = [b for b in sm.get_matching_blocks() if b.size >= 2]
    if not blocks or blocks[0].b > 3 or blocks[0].a > 4:
        return " ".join(P), cut, False   # the readings don't line up near the start
    j, k = blocks[0].a, blocks[0].b
    pre, want, rest = P[:j], R[:k], P[j:]
    keys = lambda ws: [_key(w) for w in ws]
    both = lambda extra: " ".join(x for x in (cut, extra) if x) or None
    if keys(pre) == keys(want):
        return " ".join(P), cut, False
    if not pre:
        return " ".join(want + rest), cut, True                         # the OCR lost the word
    if keys(pre[1:]) == keys(want):
        return " ".join(pre[1:] + rest), both(pre[0]), False             # "C ứ theo"
    if want and len(pre) == len(want) and keys(pre[1:]) == keys(want[1:]):
        a, b = pre[0], want[0]
        m = re.match(r"^(?:\W|\d|[A-ZĐ])+(?=[^\W\d_])", a)
        if m and _key(b) and _key(a[m.end():]) == _key(b):
            return " ".join([a[m.end():]] + pre[1:] + rest), both(m.group(0)), False   # "Xlàm", "Cứ"
    if not touches or not want:
        return " ".join(P), cut, False
    return " ".join(want + rest), both(" ".join(pre)), True


# ---------------------------------------------------------------- 3. the letter

class Lexicon:
    """Word and word-pair counts over the book's OCR text."""

    def __init__(self, texts):
        self.uni: Counter = Counter()
        self.bi: Counter = Counter()
        for t in texts:
            ws = [w.casefold() for w in _word.findall(nfc(t))]
            self.uni.update(ws)
            self.bi.update(zip(ws, ws[1:]))
        self.toneless: dict[str, list[str]] = {}
        for w in self.uni:
            self.toneless.setdefault(strip_tones(w), []).append(w)

    def score(self, word: str, nxt: str | None) -> float:
        """How likely `word` opens a section before `nxt`. The word after it
        weighs most ("tại một", not "hai một"); how common the word is counts
        only up to a cap, so "vừa" doesn't beat "xưa kia" on frequency alone.
        The same word with another tone mark counts half, and only when the
        book has it before `nxt`: OCR loses marks next to the capital ("ai"
        for "ại" in "Tại một", "ôi" for "ỗi" in "Mỗi ngày")."""
        bi = (lambda w: 50 * self.bi[(w, nxt)]) if nxt else (lambda w: 0)
        others = [w for w in self.toneless.get(strip_tones(word), []) if w != word]
        return bi(word) + min(self.uni[word], 100) + 0.5 * sum(bi(w) for w in others)

    def choose(self, fragments: list[str], nxt: str | None) -> tuple[dict | None, list]:
        """The best opening word for the fragments read beside the capital:
        {'letter', 'word', 'fragment', 'added'} or None when no candidate
        clearly wins, and the scores, best first. `added` is a letter the
        re-read lost between the capital and the fragment ("T" + "h" + "uở")."""
        nxt = nxt.casefold() if nxt else None
        cands = {}
        for frag in fragments:
            f = frag.casefold()
            for c in LETTERS:
                for add in [""] + list(CLUSTERS.get(c, "")):
                    w = c.casefold() + add + f
                    if not (is_vietnamese_syllable(w) or self.uni[w]):
                        continue
                    s = self.score(w, nxt) * (0.5 if add else 1.0)
                    key = (c, add, frag)
                    cands[key] = max(cands.get(key, 0), s)
        ranked = sorted(cands.items(), key=lambda kv: -kv[1])
        scores = [(c + add + f.casefold(), round(v, 1)) for (c, add, f), v in ranked]
        # a letter is clear when it beats every other letter (not every other
        # spelling of the same word)
        by_letter: dict = {}
        for (c, add, f), v in ranked:
            by_letter.setdefault(c, v)
        best = ranked[0] if ranked else None
        others = [v for c, v in by_letter.items() if best and c != best[0][0]]
        if not best or best[1] < 5 or (others and best[1] < 2 * max(others)):
            return None, scores
        (c, add, f), _ = best
        return dict(letter=c, word=c + add + f.casefold(), fragment=f, added=add or None), scores


# ---------------------------------------------------------------- the page

def fix_page(book: Book, n: int, rows: list[dict], lexicon: Lexicon) -> dict:
    """Edit rows (OCR rows of a section's first page) in place; returns what
    was done, for the page JSON and the report."""
    from ...ocr_tesseract import _check, recognize

    info: dict = dict(page=n)
    path = book.render_path(n)
    if not path.exists():
        info["problem"] = "page not rendered"
        return info
    img = Image.open(path)
    found = find_glyph(img, rows)
    if found is None:
        info["problem"] = "no drop cap found"
        return info
    g = found["bbox"]
    info["glyph_bbox"] = [round(x, 4) for x in g]
    W, H = img.size
    out_dir = OCR_DIR / book.id / "dropcaps"
    out_dir.mkdir(parents=True, exist_ok=True)
    pad = 4
    img.crop((max(0, int(g[0] * W) - pad), max(0, int(g[1] * H) - pad),
              int(g[2] * W) + pad, int(g[3] * H) + pad)).save(out_dir / f"p{n:04d}-glyph.png")

    # the rows beside the capital; a row inside it is the capital read alone
    gh = g[3] - g[1]
    beside, alone = [], []
    for r in rows:
        b = r["bbox"]
        cy = (b[1] + b[3]) / 2
        if not (g[1] - 0.15 * gh <= cy <= g[3] + 0.1 * gh):
            continue
        (alone if b[2] <= g[2] + 0.01 else beside).append(r)
    beside.sort(key=lambda r: r["bbox"][1] + r["bbox"][3])   # a row stretched by the capital starts higher
    for r in alone:
        rows.remove(r)
    info["removed_rows"] = [r["text"] for r in alone]
    if not beside:
        info["problem"] = "no text beside the drop cap"
        return info

    # re-read the two rows with the capital's ink painted out
    h = median_height(rows)
    masked = img.convert("L").copy()
    for x, y in found["pixels"]:
        if 0 <= x < W and 0 <= y < H:
            masked.putpixel((x, y), 255)
    crop_box = (max(0, int((g[0] - 0.01) * W)), max(0, int((g[1] - 0.4 * h) * H)),
                min(W, int((max(r["bbox"][2] for r in beside) + 0.01) * W)), min(H, int((g[3] + 0.5 * h) * H)))
    crop_path = out_dir / f"p{n:04d}-rows.png"
    crop = masked.crop(crop_box)
    framed = Image.new("L", (crop.width + 60, crop.height + 60), 255)  # Tesseract misreads text at the edge
    framed.paste(crop.convert("L"), (30, 30))
    framed.save(crop_path)
    ref = [l["text"] for l in sorted(recognize(_check(), str(crop_path), psm=6)["lines"],
                                     key=lambda l: l["bbox"][1]) if l["text"].strip()]
    info["reread"] = ref[:2]

    lines = beside[:2]
    edits = []
    for k, r in enumerate(lines):
        if k >= len(ref):
            break
        text, junk, reread = realign(r["text"], ref[k], touches=r["bbox"][0] < (g[0] + g[2]) / 2)
        if text != r["text"]:
            edits.append(dict(line=k + 1, ocr=r["text"], junk=junk, reread=reread))
            r["text"] = text
            if reread:
                r["flags"] = sorted(set(r.get("flags", [])) | {"dropcap-reread"})
        # the rows beside the capital start where it starts: the first is not
        # a short centred row (a heading), the second carries on the paragraph
        r["bbox"] = [g[0]] + list(r["bbox"][1:])
    info["edits"] = edits

    first = lines[0]
    ws = first["text"].split()
    if not ws:
        info["problem"] = "first row empty"
        return info
    m = _first.match(ws[0])
    lead, frag, tail = m.group(1), m.group(2), m.group(3)
    fragments = [frag] if frag else []
    rm = _first.match(ref[0].split()[0]) if ref and ref[0].split() else None
    if rm and rm.group(2) and rm.group(2) != frag:
        fragments.append(rm.group(2))    # the re-read may have the fragment right
    nxt = _word.search(" ".join(ws[1:]))
    nxt = nxt.group(0) if nxt else None
    # the OCR's own fragment first; the re-read's only when that one isn't clear
    choice, scores = lexicon.choose(fragments[:1], nxt) if frag else (None, [])
    if choice is None and len(fragments) > 1 or not frag:
        choice, scores = lexicon.choose(fragments, nxt)
    info.update(fragments=fragments, candidates=scores[:4])
    if choice is None:
        info["letter"] = None
        first["flags"] = sorted(set(first.get("flags", [])) | {"dropcap?"})
        return info
    info.update(letter=choice["letter"], fragment=choice["fragment"])
    if choice["fragment"] != frag:
        lead, tail = "", ""
        first["flags"] = sorted(set(first.get("flags", [])) | {"dropcap-reread"})
    if choice["added"]:
        info["added"] = choice["added"]
        first["flags"] = sorted(set(first.get("flags", [])) | {"dropcap-added"})
    ws[0] = lead + choice["word"][:1].upper() + choice["word"][1:] + tail
    first["text"] = " ".join(ws)
    info["first_words"] = " ".join(first["text"].split()[:3])
    return info
