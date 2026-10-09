"""book.md as blocks (the paragraphs between blank lines) grouped into
sections (a `#` heading and the blocks up to the next one), and where each
block is on the scans.

assemble writes book.md as blocks joined by one blank line, so splitting and
joining it gives back the same file.

A block is found on the scans by comparing it with the OCR'd segments of its
section's pages (data/ocr/<book>/pages/pNNNN.json): a segment belongs to the
block when a 16-letter piece of it (from a quarter, half and three quarters
of the way in) is in the block, or, for a segment under 8 letters ("Vua hỏi
:"), when the block is that segment. Letters only, lower case, so markup,
note calls and most small corrections don't stop a match.
"""

from __future__ import annotations

import re

from ..common import read_json

HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
PDF_RANGE = re.compile(r"^<!--\s*pdf\s+(\d+)(?:-(\d+))?")
NOTE_DEF = re.compile(r"^\[\^([^\]\s]+)\]:\s?(.*)$", re.S)
FLAG = "⚠"
_ref = re.compile(r"\[\^[^\]\s]+\]:?")
_comment = re.compile(r"<!--.*?-->", re.S)
PROBE = 16
_numbered = re.compile(r"^#+\s*(?:[\dIVXLA-Z]{1,4}\.\s+)?")   # "## 28. ", "### I. "
_marker = re.compile(r"^\s*\(?\*?\d*\)\s*")       # "(1) " opening a footnote


def split(text: str) -> list[str]:
    text = text.rstrip("\n")
    return text.split("\n\n") if text else []


def join(blocks: list[str]) -> str:
    return "\n\n".join(blocks) + "\n"


def kind(block: str) -> str:
    if HEADING.match(block):
        return "heading"
    if block.startswith("<!--"):
        return "comment"
    if NOTE_DEF.match(block):
        return "note"
    if block.strip() == "* * *":
        return "break"
    return "text"


def sections(blocks: list[str]) -> list[dict]:
    """[{title, level, start, end, pdf: [a, b] | None, flags}], `end` exclusive."""
    out: list[dict] = []
    for i, b in enumerate(blocks):
        m = HEADING.match(b)
        if m:
            out.append(dict(title=_ref.sub("", m.group(2)).strip(), level=len(m.group(1)), start=i))
        elif not out:
            out.append(dict(title="(trước tiêu đề)", level=1, start=0))
    for k, s in enumerate(out):
        s["end"] = out[k + 1]["start"] if k + 1 < len(out) else len(blocks)
        s["pdf"] = None
        for b in blocks[s["start"]:s["end"]]:
            m = PDF_RANGE.match(b)
            if m:
                a = int(m.group(1))
                s["pdf"] = [a, int(m.group(2) or a)]
                break
        s["flags"] = sum(b.count(FLAG) for b in blocks[s["start"]:s["end"]])
    return out


def section_of(secs: list[dict], index: int) -> int:
    return next((k for k, s in enumerate(secs) if s["start"] <= index < s["end"]), max(len(secs) - 1, 0))


def letters(s: str) -> str:
    return "".join(c for c in s.lower() if c.isalnum())


def _probes(norm: str) -> list[str]:
    if len(norm) < 8:
        return [norm] if len(norm) >= 3 else []
    if len(norm) <= PROBE:
        return [norm]
    return list({norm[p:p + PROBE] for p in (len(norm) // 4, len(norm) // 2, len(norm) * 3 // 4 - PROBE // 2)})


class Scans:
    """The OCR'd segments of each page, read once."""

    def __init__(self, book):
        self.book = book
        self._pages: dict[int, list] = {}

    def segments(self, n: int) -> list[tuple[list[str], list[float]]]:
        if n not in self._pages:
            path = self.book.page_path(n)
            segs = read_json(path).get("segments", []) if path.exists() else []
            self._pages[n] = [(_probes(letters(_marker.sub("", s.get("text", "")) if s.get("kind") == "footnote"
                                               else s.get("text", ""))), s.get("bbox")) for s in segs]
        return self._pages[n]

    def locate(self, blocks: list[str], pdf: list[int] | None) -> list[list[dict]]:
        """For each block, the boxes [{page, bbox}] of the segments in it."""
        if not pdf:
            return [[] for _ in blocks]
        pages = range(pdf[0], pdf[1] + 1)
        out = []
        for b in blocks:
            if kind(b) in ("comment", "break"):
                out.append([])
                continue
            plain = _comment.sub("", _ref.sub("", b)).replace("dropcap?", "")
            norms = {letters(plain), letters(_numbered.sub("", plain))}    # the page may print the number or not
            out.append([dict(page=n, bbox=bbox) for n in pages for probes, bbox in self.segments(n)
                        if bbox and any(p in m if len(p) >= 8 else p == m for p in probes for m in norms)])
        return out
