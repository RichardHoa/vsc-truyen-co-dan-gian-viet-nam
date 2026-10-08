"""Shared paths, page-range helpers, and IO used by every pipeline step."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
MASTER_DIR = REPO_ROOT / "master_pdf"
DATA_DIR = REPO_ROOT / "data"
BOOKS_DIR = DATA_DIR / "books"
OCR_DIR = DATA_DIR / "ocr"
GROUNDTRUTH_DIR = DATA_DIR / "groundtruth"
CACHE_DIR = REPO_ROOT / "cache"
RENDER_DIR = CACHE_DIR / "render"
CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


# ---------------------------------------------------------------- text utils

def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def strip_diacritics(s: str) -> str:
    s = s.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def slugify(s: str) -> str:
    s = strip_diacritics(nfc(s)).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


# ---------------------------------------------------------------- page ids

def page_id(n: int) -> str:
    return f"p{n:04d}"


def page_num(pid: str) -> int:
    return int(pid.lstrip("p"))


def to_ranges(pages) -> str:
    """[1,2,3,7,9,10] -> '1-3,7,9-10'"""
    pages = sorted(set(pages))
    out, i = [], 0
    while i < len(pages):
        j = i
        while j + 1 < len(pages) and pages[j + 1] == pages[j] + 1:
            j += 1
        out.append(str(pages[i]) if i == j else f"{pages[i]}-{pages[j]}")
        i = j + 1
    return ",".join(out)


def from_ranges(spec) -> list[int]:
    """'1-3,7' -> [1,2,3,7]. Also accepts an int or an empty value."""
    if spec is None or spec == "":
        return []
    if isinstance(spec, int):
        return [spec]
    pages: list[int] = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            pages.extend(range(int(a), int(b) + 1))
        else:
            pages.append(int(part))
    return pages


# ---------------------------------------------------------------- json / yaml

def read_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    tmp.replace(path)


def read_yaml(path: Path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def write_yaml(path: Path, obj, header: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        if header:
            f.write(header)
        yaml.safe_dump(obj, f, allow_unicode=True, sort_keys=False, width=1000)


# ---------------------------------------------------------------- books

class Book:
    """A book as described by data/books/<id>/structure.yaml."""

    def __init__(self, book_id: str):
        self.id = book_id
        self.dir = BOOKS_DIR / book_id
        self.structure_path = self.dir / "structure.yaml"
        if not self.structure_path.exists():
            raise SystemExit(
                f"No structure for '{book_id}'. Run `python -m vsc_ocr inventory` first."
            )
        self.s = read_yaml(self.structure_path)

    # -- pages and their source PDFs
    @property
    def page_count(self) -> int:
        return int(self.s["page_count"])

    def source_of(self, n: int) -> tuple[Path, int]:
        """Book page number -> (pdf path, 0-based page index in that pdf)."""
        first = 1
        for src in self.s["sources"]:
            if first <= n < first + src["pages"]:
                return REPO_ROOT / src["pdf"], n - first
            first += src["pages"]
        raise IndexError(f"{self.id}: page {n} out of range 1..{self.page_count}")

    # -- which pages get OCR'd
    def ocr_pages(self) -> list[int]:
        """Pages of Vietnamese text versions, plus pages no split covers
        (front matter, introductions, mục lục), plus manual includes."""
        pages: set[int] = set()
        covered: set[int] = set()
        for work in self.s.get("works", []):
            for v in work.get("versions", []):
                vp = from_ranges(v.get("pages"))
                covered.update(vp)
                if v.get("content") == "text":
                    pages.update(vp)
        pages.update(set(range(1, self.page_count + 1)) - covered)
        ocr = self.s.get("ocr", {}) or {}
        pages.update(from_ranges(ocr.get("include")))
        pages.difference_update(from_ranges(ocr.get("exclude")))
        return sorted(pages)

    # -- custom vocabulary (proper names) for the OCR engine
    def custom_words(self) -> list[str]:
        words: list[str] = []
        for path in (CONFIG_DIR / "custom_words.txt", self.dir / "custom_words.txt"):
            if path.exists():
                for line in path.read_text(encoding="utf-8").splitlines():
                    line = nfc(line.strip())
                    if line and not line.startswith("#"):
                        words.append(line)
        return list(dict.fromkeys(words))

    # -- output locations
    def render_path(self, n: int) -> Path:
        return RENDER_DIR / self.id / f"{page_id(n)}.png"

    def ocr_path(self, engine: str, n: int) -> Path:
        return OCR_DIR / self.id / engine / f"{page_id(n)}.json"

    def merged_path(self, n: int) -> Path:
        return OCR_DIR / self.id / "merged" / f"{page_id(n)}.json"

    def page_path(self, n: int) -> Path:
        return OCR_DIR / self.id / "pages" / f"{page_id(n)}.json"


def all_book_ids() -> list[str]:
    if not BOOKS_DIR.exists():
        return []
    return sorted(p.name for p in BOOKS_DIR.iterdir() if (p / "structure.yaml").exists())


def resolve_books(arg: str) -> list[Book]:
    ids = all_book_ids()
    if arg == "all":
        return [Book(i) for i in ids]
    if arg in ids:
        return [Book(arg)]
    matches = [i for i in ids if arg in i]
    if len(matches) == 1:
        return [Book(matches[0])]
    raise SystemExit(
        f"Unknown or ambiguous book '{arg}'. Known books:\n  " + "\n  ".join(ids)
    )


def select_pages(book: Book, spec: str | None) -> list[int]:
    if spec in (None, "", "ocr"):
        return book.ocr_pages()
    if spec == "all":
        return list(range(1, book.page_count + 1))
    return from_ranges(spec)
