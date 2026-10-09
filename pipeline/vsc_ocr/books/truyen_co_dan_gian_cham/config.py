"""This book's rules (data/books/truyen-co-dan-gian-cham/assemble.yaml)."""

from __future__ import annotations

from ...common import Book, from_ranges, read_yaml


def config(book: Book) -> dict:
    p = book.dir / "assemble.yaml"
    return read_yaml(p) if p.exists() else {}


def section_starts(book: Book, cfg: dict) -> set[int]:
    """First page of the Lời giới thiệu and of every story (structure.yaml)."""
    firsts = {from_ranges(cfg["intro"]["pages"])[0]} if cfg.get("intro") else set()
    for w in book.s.get("works", []):
        pages = [n for v in w.get("versions", []) for n in from_ranges(v.get("pages"))]
        if pages:
            firsts.add(min(pages))
    return firsts
