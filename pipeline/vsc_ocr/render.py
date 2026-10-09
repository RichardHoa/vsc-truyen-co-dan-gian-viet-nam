"""Render PDF pages to grayscale PNGs for OCR.

pypdfium2 renders the page *crop box*, which matters here: most masters store a
two-page spread as one scan image and use the crop box to show one half. A
renderer that used the media box would OCR both pages twice.

The scans are mostly 1-bit at 200-300 dpi. Rendering at 300 dpi with
anti-aliasing smooths the jagged 1-bit edges, which helps both engines with
small Vietnamese diacritics.
"""

from __future__ import annotations

import pypdfium2 as pdfium

from .common import Book


def render_pages(book: Book, pages: list[int], dpi: int = 300, force: bool = False) -> None:
    docs: dict = {}
    done = skipped = 0
    try:
        for n in pages:
            out = book.render_path(n)
            if out.exists() and not force:
                skipped += 1
                continue
            pdf, idx = book.source_of(n)
            doc = docs.get(pdf)
            if doc is None:
                doc = docs[pdf] = pdfium.PdfDocument(str(pdf))
            page = doc[idx]
            image = page.render(scale=dpi / 72, grayscale=True).to_pil()
            out.parent.mkdir(parents=True, exist_ok=True)
            image.save(out, optimize=True)
            page.close()
            done += 1
            if done % 25 == 0:
                print(f"  rendered {done}/{len(pages) - skipped}")
    finally:
        for d in docs.values():
            d.close()
    print(f"  rendered {done}, already present {skipped}")
