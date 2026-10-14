"""The diacritic review: `python -m vsc_ocr review <book> --ai --diacritic`.

Lists every word of ai/book.ai.md that the AI, the OCR and the current text
spell with the same letters but different marks (see spellings.py), grouped
by its fold: one pair, decided once. Each occurrence has three readings, the
AI's, Vision's and Tesseract's, and its OCR line boxed on the scan.

  the AI's reading         the pass's own text: book.ai.raw.md (or book.ai.md
                           before any edit) with the pass's name enforcement
                           undone from ai_corrections.jsonl, so a name the code
                           respelled shows the model's spelling; for a heading,
                           its `heading:` comment
  Vision's, Tesseract's    the word on the OCR line the occurrence is on
                           (data/ocr/<book>/merged/pNNNN.json: Vision's text and
                           Tesseract's as `secondary`), found by its neighbours

A decision is a Spelling Rule in data/books/<book>/spellings.yaml, applied to
book.ai.md right away; each block it changes is logged in ai/corrections.jsonl
with action "spelling" and the rule. A Depends pair gets no rule: its
occurrences are edited one by one, as plain edits. A heading with a Story
Title (titles.yaml) is not listed and no rule changes it, and a rule's story
exceptions name Story Titles.
"""

from __future__ import annotations

import json
import threading
import unicodedata
from pathlib import Path

from ..common import read_json
from . import mdbook
from . import spellings as sp
from . import titles as st

SPELLINGS = "spellings.yaml"
# a pass's log entry that respelled names, its own way or by a Spelling Rule
_ENFORCED = ("names as the OCR prints them", "Spelling Rule:")


class Lines:
    """The merged OCR lines of each page, with their words, read once."""

    def __init__(self, book):
        self.book = book
        self._pages: dict[int, list[dict]] = {}

    def rows(self, n: int) -> list[dict]:
        if n not in self._pages:
            path = self.book.merged_path(n)
            rows = read_json(path).get("rows", []) if path.exists() else []
            out = []
            for r in rows:
                vision = "" if "only_in_secondary" in r.get("flags", []) else r.get("text", "")
                tess = r.get("secondary", "")
                out.append(dict(bbox=r["bbox"], vision=sp.spans(vision), tesseract=sp.spans(tess),
                                folds={s[3] for s in sp.spans(vision + " " + tess)}))
            self._pages[n] = out
        return self._pages[n]

    def find(self, f: str, before: list[str], after: list[str], pages: list[int]) -> dict | None:
        """The line holding the word folded `f` whose words best match its neighbours, with each engine's reading."""
        near = set(before) | set(after)
        best, score = None, -1
        for n in pages:
            for r in self.rows(n):
                if f in r["folds"]:
                    s = len(near & r["folds"])
                    if s > score:
                        best, score = (n, r), s
        if best is None:
            return None
        n, r = best
        return dict(page=n, bbox=r["bbox"], vision=_word(r["vision"], f, before, after),
                    tesseract=_word(r["tesseract"], f, before, after))


def _word(words: list[tuple], f: str, before: list[str], after: list[str]) -> str | None:
    """The word folded `f` among `words` (a line's) whose neighbours best match `before` and `after`."""
    hits = [k for k, w in enumerate(words) if w[3] == f]
    if not hits:
        return None

    def score(k):
        return (k > 0 and before[-1:] == [words[k - 1][3]]) + (k + 1 < len(words) and after[:1] == [words[k + 1][3]])

    return words[max(hits, key=score)][0]


def model_text(dir: Path, current: list[str]) -> list[str]:
    """The pass's own text (see the module doc): its output with the names its code respelled put back."""
    raw = dir / "book.ai.raw.md"
    blocks = mdbook.split(raw.read_text(encoding="utf-8")) if raw.exists() else list(current)
    log = dir / "ai_corrections.jsonl"
    if not log.exists():
        return blocks

    def key(b):
        return tuple(s[3] for s in sp.spans(b))

    section = [""] * len(blocks)        # each block's section title, folded
    for s in mdbook.sections(blocks):
        section[s["start"]:s["end"]] = [sp.fold(s["title"])] * (s["end"] - s["start"])
    at: dict[tuple, list[int]] = {}
    for i, b in enumerate(blocks):
        at.setdefault(key(b), []).append(i)
    with open(log, encoding="utf-8") as f:
        for line in f:
            e = json.loads(line) if line.strip() else {}
            if (any(m in e.get("reason", "") for m in _ENFORCED) or e.get("rule")) \
                    and len(e.get("before", [])) == len(e.get("after", [])) == 1:
                free = at.get(key(e["after"][0]))
                if free:        # the same text may be in several blocks: take one in the entry's section
                    mine = [i for i in free if section[i] == sp.fold(e.get("section", ""))]
                    i = (mine or free)[0]
                    free.remove(i)
                    blocks[i] = e["before"][0]
    return blocks


class Diacritic:
    """The pairs of a Review of book.ai.md, and the decisions on them."""

    def __init__(self, review):
        self.review = review
        self.book = review.book
        self.path = review.book.dir / SPELLINGS
        self.lines = Lines(review.book)
        self.lock = threading.Lock()
        self._cache: tuple | None = None
        raw = review.book.dir / "book.raw.md"
        if not raw.exists():
            raise SystemExit(f"{raw} doesn't exist: the diacritic review reads the OCR's text from it.")
        self.raw = mdbook.split(raw.read_text(encoding="utf-8"))
        self.titles_path = review.book.dir / st.FILE

    # -- reads
    def rules(self) -> dict:
        return sp.load(self.path)

    def titles(self) -> dict[int, str]:
        return st.load(self.titles_path)

    def _occurrences(self) -> tuple[list[dict], dict]:
        """Every listed occurrence with its readings and box (cached while book.ai.md and the rules are unchanged)."""
        r = self.review
        with r.lock:
            r._load()
            blocks, version, secs = r.blocks, r.version, r.secs
        data, titles = self.rules(), self.titles()
        stamp = (version, json.dumps(data, ensure_ascii=False), json.dumps(titles, ensure_ascii=False))
        if self._cache and self._cache[0] == stamp:
            return self._cache[1], data
        common = sp.lower_folds(*blocks, *self.raw)
        fixed = st.set_headings(blocks, self.raw, titles)
        found = [o for o in sp.find_pairs(blocks, self.raw, model_text(r.dir, blocks), common)
                 if o["block"] not in fixed]
        story = sp.story_titles(blocks, self.raw, titles)
        boxes: dict[int, list[dict]] = {}
        for k in sorted({o["section"] for o in found}):
            s = secs[k]
            for j, bx in enumerate(r._boxes(s["start"], blocks[s["start"]:s["end"]], s["pdf"])):
                boxes[s["start"] + j] = bx
        for o in found:
            s = secs[o["section"]]
            text = unicodedata.normalize("NFC", blocks[o["block"]])     # the offsets `spans` gives are into NFC
            before = [w[3] for w in sp.spans(o["before"])]
            after = [w[3] for w in sp.spans(o["after"])]
            on = sorted({b["page"] for b in boxes.get(o["block"], [])})
            sec_pages = list(range(s["pdf"][0], s["pdf"][1] + 1)) if s["pdf"] else []
            hit = self.lines.find(o["fold"], before, after, on) or self.lines.find(o["fold"], before, after, sec_pages)
            words = sp.spans(text)
            k = next(j for j, w in enumerate(words) if w[1] == o["start"])
            o.update(id=f"{o['block']}:{o['start']}", title=story[o["block"]], page=hit and hit["page"],
                     bbox=hit and hit["bbox"], vision=hit and hit["vision"], tesseract=hit and hit["tesseract"],
                     near=text[words[max(0, k - 1)][1]:words[min(len(words) - 1, k + 1)][2]],
                     rule=sp.covered(text, o["start"], data, story[o["block"]]),
                     page_hint=on[0] if on else (sec_pages[0] if sec_pages else None))
        self._cache = (stamp, found)
        return found, data

    def listing(self) -> dict:
        found, data = self._occurrences()
        pairs: dict[str, dict] = {}
        for o in found:
            p = pairs.setdefault(o["fold"], dict(fold=o["fold"], name=o["name"], heading=False, occurrences=[]))
            p["heading"] |= o["heading"]
            p["occurrences"].append(o)
        for p in pairs.values():
            seen = [w for o in p["occurrences"] for w in (o["word"], o["ai"], o["vision"], o["tesseract"]) if w]
            p["spellings"] = list(dict.fromkeys(w.lower() for w in seen))
            p["depends"] = sp.depends(data, p["fold"])
            p["word_rule"] = (sp.word_rule(data, p["fold"]) or {}).get("spelling")
            p["open"] = p["depends"] or (not p["word_rule"] and any(o["rule"] is None for o in p["occurrences"]))
        opened = sorted((p for p in pairs.values() if p["open"]),
                        key=lambda p: (not p["heading"], not p["name"], -len(p["occurrences"]), p["fold"]))
        applied, words = self._applied(data), self._words()
        ruled = [self._ruled(kind, r, found, applied, words) for kind in ("words", "phrases") for r in data[kind]]
        tally = dict(occurrences=0, ai=0, vision=0, tesseract=0)
        for o in found:
            if o["rule"]:
                tally["occurrences"] += 1
                for who in ("ai", "vision", "tesseract"):
                    tally[who] += bool(o[who]) and o[who].lower() == o["word"].lower()
        with self.review.lock:
            version = self.review.version
        return dict(book=self.book.id, version=version, open=opened, ruled=ruled, tally=tally,
                    depends=data["depends"])

    def _ruled(self, kind: str, rule: dict, found: list[dict], applied: dict, words: list[list[str]]) -> dict:
        folds = [w[3] for w in sp.spans(rule["spelling"])]
        mine = [o for o in found if o["rule"] == rule["spelling"]
                or (kind == "words" and o["fold"] == folds[0] and sp.skipped(rule, o["title"]))]
        want = [w[0].lower() for w in sp.spans(rule["spelling"])]
        in_book = sum(1 for ws in words for i in range(len(ws) - len(want) + 1) if ws[i:i + len(want)] == want)
        return dict(kind=kind[:-1], spelling=rule["spelling"], fold=folds[0] if kind == "words" else None,
                    folds=folds, **{"except": rule["except"]}, applied=applied.get(rule["spelling"], 0),
                    in_book=in_book, occurrences=mine)

    def _applied(self, data: dict) -> dict[str, int]:
        """For each rule, the words it changed, by this page (corrections.jsonl) and by the pass (ai_corrections.jsonl)."""
        folds = {r["spelling"]: {w[3] for w in sp.spans(r["spelling"])} for k in ("words", "phrases") for r in data[k]}
        out: dict[str, int] = {}
        for name in ("corrections.jsonl", "ai_corrections.jsonl"):
            path = self.review.dir / name
            if not path.exists():
                continue
            with open(path, encoding="utf-8") as f:
                for line in f:
                    e = json.loads(line) if line.strip() else {}
                    rules = e.get("rule") or []
                    for rule in [rules] if isinstance(rules, str) else rules:
                        if rule in folds:
                            out[rule] = out.get(rule, 0) + sum(
                                1 for a, b in zip(e["before"], e["after"]) for x, y in zip(sp.spans(a), sp.spans(b))
                                if x[3] == y[3] and x[3] in folds[rule] and x[0] != y[0])
        return out

    def _words(self) -> list[list[str]]:
        """book.ai.md's words in lower case, block by block: to count how often it spells a rule's way."""
        with self.review.lock:
            blocks = list(self.review.blocks)
        return [[w[0].lower() for w in sp.spans(b)] for b in blocks]

    # -- writes
    def _apply(self, version: str, data: dict, why: str) -> dict:
        """Save the rules, then apply them all to book.ai.md, one logged Correction per block changed."""
        r = self.review
        with r.lock:
            r._current(version)
            titles = self.titles()
            story = sp.story_titles(r.blocks, self.raw, titles)
            changed = sp.apply(r.blocks, data, story, st.set_headings(r.blocks, self.raw, titles))
            entries = {}
            for i, (_, ch) in changed.items():
                rules = list(dict.fromkeys(c[2] for c in ch))
                entries[i] = dict(rule=rules[0] if len(rules) == 1 else rules)
            r._replace({i: new for i, (new, _) in changed.items()}, "spelling", entries)
            sp.save(self.path, data)        # after the book, so a failed write leaves the rules as they were
        return dict(version=r.version, changed=len(changed))

    def _check_spelling(self, spelling: str, f: str | None = None) -> str:
        spelling = unicodedata.normalize("NFC", spelling.strip())
        if not sp.spans(spelling):
            raise ValueError("type a spelling")
        if f is not None and f not in [w[3] for w in sp.spans(spelling)]:
            raise ValueError(f"“{spelling}” isn't a spelling of {f}")
        return spelling

    def rule(self, version: str, kind: str, fold: str, spelling: str) -> dict:
        """A new rule for the pair `fold`: a word rule, or a phrase holding the word (a common word gets only a phrase)."""
        with self.lock:
            spelling = self._check_spelling(spelling, fold)
            data = self.rules()
            words = sp.spans(spelling)
            if kind == "word":
                if len(words) != 1:
                    raise ValueError("a word rule is one word: use a phrase rule for more")
                with self.review.lock:
                    blocks = list(self.review.blocks)
                if fold in sp.lower_folds(*blocks, *self.raw):
                    raise ValueError(f"“{spelling}” is a common word (it is printed in lower case): "
                                     "make a phrase rule or answer Depends")
                data["words"] = [r for r in data["words"] if sp.fold(r["spelling"]) != fold]
                data["words"].append({"spelling": spelling, "except": []})
            elif kind == "phrase":
                if len(words) < 2:
                    raise ValueError("a phrase rule needs the word and at least one neighbour")
                key = [w[3] for w in words]
                data["phrases"] = [r for r in data["phrases"] if [w[3] for w in sp.spans(r["spelling"])] != key]
                data["phrases"].append({"spelling": spelling, "except": []})
            else:
                raise ValueError(f"unknown rule kind {kind}")
            data["depends"] = [d for d in data["depends"] if not any(sp.fold(w) == fold for w in d)]
            return self._apply(version, data, spelling)

    def change(self, version: str, kind: str, old: str, spelling: str | None) -> dict:
        """A rule respelled (applied again) or, with no `spelling`, deleted (book.ai.md keeps its text)."""
        with self.lock:
            data = self.rules()
            key = kind + "s"
            rule = next((r for r in data[key] if r["spelling"] == old), None)
            if rule is None:
                raise ValueError(f"no {kind} rule “{old}”")
            if spelling is None:
                data[key].remove(rule)
                sp.save(self.path, data)
                return dict(version=self.review.version, changed=0)
            spelling = self._check_spelling(spelling)
            if [w[3] for w in sp.spans(spelling)] != [w[3] for w in sp.spans(old)]:
                raise ValueError(f"“{spelling}” has other letters than “{old}”: a rule only changes marks")
            rule["spelling"] = spelling
            return self._apply(version, data, spelling)

    def depends(self, version: str, fold: str, spellings: list[str], on: bool) -> dict:
        with self.lock:
            data = self.rules()
            data["depends"] = [d for d in data["depends"] if not any(sp.fold(w) == fold for w in d)]
            if on:
                if sp.word_rule(data, fold):
                    raise ValueError("this pair has a rule: delete it in Ruled first")
                pair = list(dict.fromkeys(unicodedata.normalize("NFC", w) for w in spellings if sp.fold(w) == fold))
                if not pair:
                    raise ValueError(f"no spelling of {fold} given")
                data["depends"].append(pair)
            sp.save(self.path, data)
            return dict(version=self.review.version)

    def word(self, version: str, block: int, start: int, end: int, spelling: str, override: str | None) -> dict:
        """
        One occurrence respelled as a plain edit. With `override` (a rule's spelling), the rule gets a story
        exception for the occurrence's story first, so it no longer applies there.
        """
        with self.lock:
            r = self.review
            with r.lock:
                r._current(version)
                text = unicodedata.normalize("NFC", r.blocks[block]) if 0 <= block < len(r.blocks) else ""
                word = text[start:end]
                if len(sp.spans(word)) != 1:
                    raise ValueError("that word is no longer there: reload the page")
                spelling = self._check_spelling(spelling, sp.fold(word))
                if len(sp.spans(spelling)) != 1:
                    raise ValueError("type one word")
                data = None
                if override:
                    story = sp.story_titles(r.blocks, self.raw, self.titles())[block]
                    data = self.rules()
                    rule = next((x for k in ("words", "phrases") for x in data[k] if x["spelling"] == override), None)
                    if rule is None:
                        raise ValueError(f"no rule “{override}”")
                    if not sp.skipped(rule, story):
                        rule["except"].append(story)
                new = text[:start] + sp.cased(spelling, word) + text[end:]
                if new != r.blocks[block]:
                    r._replace({block: new}, "edit", {})
                if data is not None:
                    sp.save(self.path, data)
                return dict(version=r.version, section=mdbook.section_of(r.secs, block))
