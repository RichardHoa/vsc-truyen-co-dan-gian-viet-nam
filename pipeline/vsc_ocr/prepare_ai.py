"""Everything an AI Proofreading Pass needs, in one folder to copy to the GPU
cluster: `python -m vsc_ocr prepare-ai <book>`.

Writes data-for-ai/<book>/ (at the repo root; re-running overwrites it):

  book.json                 book id and title, the sections and their pdf
                            ranges (from book.raw.md's `<!-- pdf a-b -->`
                            comments), the sha1 of book.raw.md, image dpi
  book.raw.md               the pipeline output the pass is diffed against
  notes.json                the pipeline's notes (ids, pages, markers)
  human_corrections.jsonl   the reviewer's Corrections, the ground truth for
                            comparing runs
  spellings.yaml            the book's Spelling Rules, if it has any: the
                            pass applies them and lists their names in the
                            prompt
  pages.jsonl               one line per page of the sections:
      page, printed_page_est
      lines     the OCR lines (merged/: Vision, with Tesseract's
                disagreements flagged) as {n, text, bbox, check, role};
                role is body, footnote or removed (page numbers, headers,
                letterless specks the clean step dropped)
      segments  the clean step's paragraphs, headings and footnotes as
                {kind, bbox, continues}; `continues` on the first paragraph
                means it carries on from the previous page
      column    the body's left and right edges, and `indent_at`: a line
                starting right of it opens a paragraph
  images/pNNNN.jpg          every page, grayscale JPEG at --dpi (200)
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime

import pypdfium2 as pdfium

from .common import REPO_ROOT, Book, read_json, to_ranges
from .review import mdbook

OUT_DIR = REPO_ROOT / "data-for-ai"
JPEG_QUALITY = 85


def _inside(bbox, seg) -> bool:
    """A line belongs to a segment when its middle is inside the segment's box."""
    x, y = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    return seg[0] - 0.01 <= x <= seg[2] + 0.01 and seg[1] - 0.005 <= y <= seg[3] + 0.005


def page_entry(n: int, merged: dict | None, page: dict | None) -> dict:
    """One pages.jsonl line from a page's merged rows and its cleaned page."""
    rows = merged["rows"] if merged else []
    segs = page["segments"] if page else []
    removed = [r["text"].strip() for r in (page or {}).get("removed", [])]
    lines = []
    for k, r in enumerate(rows, 1):
        text = r["text"].strip()
        holder = next((s for s in segs if _inside(r["bbox"], s["bbox"])), None)
        if text in removed:
            removed.remove(text)
            role = "removed"
        elif holder is None and not any(c.isalpha() for c in text):
            role = "removed"        # a speck or ornament the clean step dropped without listing it
        else:
            role = "footnote" if holder is not None and holder["kind"] == "footnote" else "body"
        lines.append(dict(n=k, text=text, bbox=r["bbox"], check=bool(r.get("flags")), role=role))

    body = [ln["bbox"] for ln in lines if ln["role"] == "body"]
    column = None
    if body:
        xs0, xs1 = sorted(b[0] for b in body), sorted(b[2] for b in body)
        left, right = xs0[len(xs0) // 10], xs1[(len(xs1) * 9) // 10]
        # as clean does: a line starting 5% of the column's width in is indented
        column = dict(left=left, right=right, indent_at=round(left + 0.05 * (right - left), 5))
    return dict(
        page=n,
        printed_page_est=(page or {}).get("printed_page_est"),
        lines=lines,
        segments=[dict(kind=s["kind"], bbox=s["bbox"], continues=bool(s.get("continues"))) for s in segs],
        column=column,
    )


def _render(book: Book, pages: list[int], out_dir, dpi: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    docs: dict = {}
    try:
        for k, n in enumerate(pages, 1):
            pdf, idx = book.source_of(n)
            doc = docs.get(pdf)
            if doc is None:
                doc = docs[pdf] = pdfium.PdfDocument(str(pdf))
            page = doc[idx]
            page.render(scale=dpi / 72, grayscale=True).to_pil().convert("L").save(
                out_dir / f"p{n:04d}.jpg", quality=JPEG_QUALITY)
            page.close()
            if k % 50 == 0:
                print(f"  rendered {k}/{len(pages)}")
    finally:
        for d in docs.values():
            d.close()


def prepare(book: Book, dpi: int = 200) -> None:
    raw_path = book.dir / "book.raw.md"
    if not raw_path.exists():
        raise SystemExit(f"{raw_path} doesn't exist: run `python -m vsc_ocr assemble {book.id}` first.")
    text = raw_path.read_text(encoding="utf-8")
    # the book's title (`# `, the title page) is not story text: the pass leaves it as it is
    sections = [dict(title=s["title"], pdf=s["pdf"]) for s in mdbook.sections(mdbook.split(text))
                if s["pdf"] and s["level"] > 1]
    pages = sorted({n for s in sections for n in range(s["pdf"][0], s["pdf"][1] + 1)})

    out = OUT_DIR / book.id
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copyfile(raw_path, out / "book.raw.md")
    for src, dst in (("notes.json", "notes.json"), ("corrections.jsonl", "human_corrections.jsonl"),
                     ("spellings.yaml", "spellings.yaml")):
        if (book.dir / src).exists():
            shutil.copyfile(book.dir / src, out / dst)
        else:
            print(f"  no {src}: {dst} left out")

    with open(out / "pages.jsonl", "w", encoding="utf-8") as f:
        for n in pages:
            mp, pp = book.merged_path(n), book.page_path(n)
            entry = page_entry(n, read_json(mp) if mp.exists() else None, read_json(pp) if pp.exists() else None)
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    (out / "book.json").write_text(json.dumps(dict(
        book=book.id, title=book.s["title"], sections=sections, text_pages=to_ranges(pages),
        raw_sha1=hashlib.sha1(text.encode()).hexdigest(), dpi=dpi,
        made=datetime.now().isoformat(timespec="seconds"),
    ), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"  rendering {len(pages)} pages at {dpi} dpi")
    _render(book, pages, out / "images", dpi)
    print(f"  {out.relative_to(REPO_ROOT)}/: {len(sections)} sections, {len(pages)} pages; "
          f"copy the folder to the cluster as is")
