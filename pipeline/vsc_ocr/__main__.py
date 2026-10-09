"""Command line entry point: `python -m vsc_ocr <command> ...` (run from pipeline/)."""

from __future__ import annotations

import argparse
import sys


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="vsc_ocr", description="Local OCR pipeline for the Vietnamese texts.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("inventory", help="build data/books/*/structure.yaml from master + split PDFs")
    s.add_argument("--force", action="store_true", help="overwrite existing structure.yaml files")

    def book_cmd(name, help_):
        s = sub.add_parser(name, help=help_)
        s.add_argument("book", help="book id (or a unique part of it), or 'all'")
        s.add_argument("--pages", help="'ocr' (default: Vietnamese + unassigned pages), 'all', or ranges like 1-20,31")
        return s

    s = book_cmd("render", "render pages to cache/render/<book>/pNNNN.png")
    s.add_argument("--dpi", type=int, default=300)
    s.add_argument("--force", action="store_true")

    s = book_cmd("ocr", "OCR rendered pages with one engine")
    s.add_argument("--engine", choices=["vision", "tesseract"], required=True)
    s.add_argument("--workers", type=int, default=1)
    s.add_argument("--force", action="store_true")
    s.add_argument("--no-language-correction", action="store_true",
                   help="vision: disable Apple's language model (also disables custom words)")

    s = book_cmd("compare", "merge engines, flag lines where they disagree")
    s.add_argument("--primary", choices=["vision", "tesseract"], default="vision")

    book_cmd("clean", "drop headers/footers, build paragraphs/verse, detect page numbers and language")
    book_cmd("toc", "find and parse the mục lục; write data/books/<book>/toc.generated.yaml")
    s = book_cmd("assemble", "write data/books/<book>/book.md, toc.json and notes.json (books with code in vsc_ocr/books/)")
    s.add_argument("--no-rerender", action="store_true",
                   help="don't re-render pages at high DPI to look for lost note calls")

    s = book_cmd("run", "render + ocr + compare + clean + toc")
    s.add_argument("--engines", default="vision,tesseract")
    s.add_argument("--primary", choices=["vision", "tesseract"], default=None)
    s.add_argument("--workers", type=int, default=1)
    s.add_argument("--dpi", type=int, default=300)

    s = sub.add_parser("review", help="review book.md next to the scans in a local web page")
    s.add_argument("book", help="book id (or a unique part of it)")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-browser", action="store_true", help="don't open the page in a browser")

    sub.add_parser("status", help="progress per book")

    s = sub.add_parser("samples", help="run the pipeline on the sample pages in config/samples.yaml")
    s.add_argument("--engines", default="vision,tesseract")
    book_cmd("evaluate", "character/word error rates against data/groundtruth/<book>/pNNNN.txt")

    a = p.parse_args(argv)

    if a.cmd == "inventory":
        from . import inventory
        inventory.build(force=a.force)
        return
    if a.cmd == "status":
        from . import status
        status.show()
        return
    if a.cmd == "samples":
        _samples(a.engines)
        return
    if a.cmd == "review":
        from .common import resolve_books
        from .review import serve
        books = resolve_books(a.book)
        if len(books) != 1:
            raise SystemExit("review one book at a time")
        serve(books[0], port=a.port, open_browser=not a.no_browser)
        return

    from .common import resolve_books, select_pages
    for book in resolve_books(a.book):
        pages = select_pages(book, a.pages)
        print(f"== {book.id}: {a.cmd} on {len(pages)} page(s)")
        if a.cmd == "render":
            from . import render
            render.render_pages(book, pages, dpi=a.dpi, force=a.force)
        elif a.cmd == "ocr":
            _ocr(book, pages, a.engine, a.workers, a.force, not a.no_language_correction)
        elif a.cmd == "compare":
            from . import compare
            compare.compare_pages(book, pages, primary=a.primary)
        elif a.cmd == "clean":
            _step(book, "clean", "clean_book")(book, pages)
        elif a.cmd == "toc":
            _step(book, "toc", "build_toc")(book)
        elif a.cmd == "assemble":
            from .books import module_for
            mod = module_for(book)
            if mod is None or not hasattr(mod, "assemble"):
                raise SystemExit(f"{book.id} has no code of its own yet (vsc_ocr/books/{book.id.replace('-', '_')}/)")
            _keep_reviewed(book)
            mod.assemble(book, rerender=not a.no_rerender)
        elif a.cmd == "evaluate":
            from . import evaluate
            evaluate.evaluate_book(book, pages if a.pages else None)
        elif a.cmd == "run":
            from . import compare, render
            engines = [e.strip() for e in a.engines.split(",") if e.strip()]
            render.render_pages(book, pages, dpi=a.dpi)
            for e in engines:
                _ocr(book, pages, e, a.workers, False, True)
            compare.compare_pages(book, pages, primary=a.primary or engines[0])
            _step(book, "clean", "clean_book")(book, pages)
            _step(book, "toc", "build_toc")(book)


def _keep_reviewed(book) -> None:
    """Before assemble overwrites book.md: if it was corrected in `review`, move
    it and its book.raw.md to review-history/<time>/ so the work isn't lost.
    corrections.jsonl stays where it is and keeps growing."""
    raw = book.dir / "book.raw.md"
    if not raw.exists():
        return
    from datetime import datetime
    dest = book.dir / "review-history" / datetime.now().strftime("%Y%m%d-%H%M%S")
    dest.mkdir(parents=True)
    for name in ("book.raw.md", "book.md", "notes.json"):
        if (book.dir / name).exists():
            (book.dir / name).replace(dest / name)
    print(f"  reviewed book.md moved to {dest.relative_to(book.dir.parent.parent.parent)}/")


def _step(book, module: str, func: str):
    """A book's own version of a step (vsc_ocr/books/<book>/), else the shared one."""
    import importlib
    from .books import module_for
    mod = module_for(book)
    if mod is not None and hasattr(mod, func):
        return getattr(mod, func)
    return getattr(importlib.import_module(f".{module}", __package__), func)


def _samples(engines_arg: str) -> None:
    from . import clean, compare, render
    from .common import CONFIG_DIR, from_ranges, read_json, read_yaml, resolve_books
    engines = [e.strip() for e in engines_arg.split(",") if e.strip()]
    print(f"{'book':40} {'page':>5} {'rows':>5} {'flagged':>8} {'agree':>6}  lang")
    for item in read_yaml(CONFIG_DIR / "samples.yaml"):
        book = resolve_books(item["book"])[0]
        pages = from_ranges(item["pages"])
        render.render_pages(book, pages)
        for e in engines:
            _ocr(book, pages, e, 1, False, True)
        compare.compare_pages(book, pages, primary=engines[0])
        clean.clean_book(book, pages)
        for n in pages:
            st = read_json(book.merged_path(n))["stats"]
            lang = read_json(book.page_path(n))["language"]["guess"]
            print(f"{book.id[:40]:40} {n:>5} {st['rows']:>5} {st['flagged']:>8} "
                  f"{st['agreement'] if st['agreement'] is not None else '-':>6}  {lang}")


def _ocr(book, pages, engine, workers, force, language_correction):
    if engine == "vision":
        from . import ocr_vision
        ocr_vision.ocr_pages(book, pages, workers=workers, force=force,
                             language_correction=language_correction)
    else:
        from . import ocr_tesseract
        ocr_tesseract.ocr_pages(book, pages, workers=workers, force=force)


if __name__ == "__main__":
    sys.exit(main())
