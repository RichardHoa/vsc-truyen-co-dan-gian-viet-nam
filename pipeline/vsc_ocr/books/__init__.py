"""Book-specific code. Every book is laid out differently (versions, verse
numbering, notes, tables...), so each one that needs more than the shared
steps gets its own package here, named after its id with underscores:
`books/ariya_truong_ca_cham/` for `ariya-truong-ca-cham`.

A book package can provide any of:
  clean_book(book, pages)   replaces the shared `clean` step
  build_toc(book)           replaces the shared `toc` step
  assemble(book, rerender)  writes data/books/<book>/book.md, toc.json, notes.json
Steps it doesn't provide fall back to the shared modules.
"""

from __future__ import annotations

import importlib
import importlib.util


def module_for(book):
    """The book's package, or None when the book has no code of its own."""
    name = f"{__name__}.{book.id.replace('-', '_')}"
    if importlib.util.find_spec(name) is None:
        return None
    return importlib.import_module(name)
