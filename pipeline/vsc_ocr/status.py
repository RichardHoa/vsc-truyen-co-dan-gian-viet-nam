"""Progress table: how far each book has got through the pipeline."""

from __future__ import annotations

from .common import Book, all_book_ids


def show() -> None:
    ids = all_book_ids()
    if not ids:
        print("No books yet. Run `python -m vsc_ocr inventory`.")
        return
    cols = ("ocr pages", "rendered", "vision", "tesseract", "merged", "cleaned")
    print(f"{'book':48} " + " ".join(f"{c:>9}" for c in cols))
    for i in ids:
        b = Book(i)
        pages = b.ocr_pages()
        counts = (
            len(pages),
            sum(b.render_path(n).exists() for n in pages),
            sum(b.ocr_path("vision", n).exists() for n in pages),
            sum(b.ocr_path("tesseract", n).exists() for n in pages),
            sum(b.merged_path(n).exists() for n in pages),
            sum(b.page_path(n).exists() for n in pages),
        )
        print(f"{i[:48]:48} " + " ".join(f"{c:>9}" for c in counts))
