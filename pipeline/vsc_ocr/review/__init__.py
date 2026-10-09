"""Side-by-side review of an assembled book: `python -m vsc_ocr review <book>`.

A local web page shows book.md one section at a time next to the scanned page
each paragraph came from, with the OCR lines boxed on the scan. Works for any
book that has data/books/<book>/book.md (sections are its `#` headings, each
followed by a `<!-- pdf a-b -->` comment).

  mdbook.py   book.md as blocks and sections; finds each block on the scans
  notes.py    keeps notes.json in step with the notes in book.md
  server.py   the HTTP server and the edit log
  page.html   the page

book.md is the only file you edit. Each save:
  - keeps the untouched pipeline output once, as book.raw.md
    (`diff book.raw.md book.md` is everything you corrected);
  - appends the change, with its section and pages, to corrections.jsonl;
  - rewrites the notes in notes.json from the `[^id]: ...` lines.
"""

from .server import serve

__all__ = ["serve"]
