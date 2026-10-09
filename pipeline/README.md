# Local OCR pipeline (Vietnamese text only)

Extracts the **Vietnamese** text of the scanned books into structured, reviewable
JSON. Original-language versions (phiên âm, Akhar thrah, bản viết tay, đối chiếu
dị bản, index) are **not** OCR'd; they stay as PDFs, listed in each book's
`structure.yaml`.

Everything runs locally. No external API is called at any step.

| Step | Command | Engine | Output |
|---|---|---|---|
| 1. Inventory | `inventory` | PDF structure (pypdf) | `data/books/<book>/structure.yaml` |
| 2. Render | `render` | pypdfium2 | `cache/render/<book>/pNNNN.png` |
| 3. OCR | `ocr --engine vision` | Apple Vision (macOS) | `data/ocr/<book>/vision/pNNNN.json` |
| 4. Second opinion | `ocr --engine tesseract` | Tesseract `vie` | `data/ocr/<book>/tesseract/pNNNN.json` |
| 5. Cross-check | `compare` | | `data/ocr/<book>/merged/pNNNN.json` |
| 6. Clean & structure | `clean` | | `data/ocr/<book>/pages/pNNNN.json`, `preview.md` |
| 7. Mục lục | `toc` | Tesseract table mode | `data/books/<book>/toc.generated.yaml` |
| 8. Assemble | `assemble` | book-specific code | `data/books/<book>/book.md`, `toc.json`, `notes.json` |

## Setup (macOS, Apple Silicon)

```sh
brew install tesseract tesseract-lang        # Tesseract + Vietnamese model
cd pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-mac.txt          # pypdf, pypdfium2, Pillow, PyYAML, pyobjc Vision
```

Run every command from `pipeline/`: `python -m vsc_ocr <command> ...`.
`<book>` is a book id from `data/books/` (a unique part of it is enough, e.g.
`kalipu`), or `all`.

On Linux, everything except the Vision step works (`apt install tesseract-ocr
tesseract-ocr-vie`, `pip install -r requirements.txt`); use `--primary tesseract`.

## Quick start

```sh
python -m vsc_ocr inventory           # already done; structure.yaml files are committed
python -m vsc_ocr samples             # 7 representative pages, Vision vs Tesseract
python -m vsc_ocr run truyen-co-dan-gian-cham --workers 4
python -m vsc_ocr status
```

Then read `data/ocr/truyen-co-dan-gian-cham/preview.md`. **⚠** marks text the
two engines really disagree on (not just on accents, which Tesseract often
misreads, or on a word in an otherwise matching line), text only one engine saw,
or text with low confidence.

## Ariya (Trường ca Chăm)

This book has its own code (`vsc_ocr/books/ariya_truong_ca_cham/`) and rules
(`data/books/ariya-truong-ca-cham/assemble.yaml`). Two commands, from
`pipeline/`:

```sh
python -m vsc_ocr run ariya-truong-ca-cham --workers 4   # render, OCR, compare, clean, mục lục
python -m vsc_ocr assemble ariya-truong-ca-cham          # book.md, toc.json, notes.json
```

- `run` renders the pages to `cache/render/ariya-truong-ca-cham/`, OCRs them
  with Vision and Tesseract into `data/ocr/ariya-truong-ca-cham/`, and writes
  `toc.generated.yaml`. It takes a while; pages already OCR'd are skipped, so it
  can be stopped and started again. On Linux: `--engines tesseract`.
- `assemble` reads that OCR output and writes `book.md`, `toc.json` and
  `notes.json` in `data/books/ariya-truong-ca-cham/`. It also re-renders pages at
  600 dpi to find note calls OCR lost; `--no-rerender` skips that (faster, fewer
  calls found).

`data/ocr/` isn't committed, so on a new machine `run` has to come first. The
committed outputs come from a Tesseract-only run; a run with Vision changes the
text in all three files.

## Truyện cổ Dân gian Chăm

Its own code is in `vsc_ocr/books/truyen_co_dan_gian_cham/` and its rules
(intro pages, skipped pages, mục lục pages) in
`data/books/truyen-co-dan-gian-cham/assemble.yaml`. The same two commands, from
`pipeline/`:

```sh
python -m vsc_ocr run truyen-co-dan-gian-cham --workers 4   # render, OCR, compare, clean, mục lục
python -m vsc_ocr assemble truyen-co-dan-gian-cham          # book.md, toc.json, notes.json
```

- `run` works as for Ariya (`--engines tesseract` on Linux). Its clean step also
  reads the drop caps again (crops in `data/ocr/truyen-co-dan-gian-cham/dropcaps/`),
  finds the footnotes under the rule and the `* * *` scene breaks.
- `assemble` writes `book.md`, `toc.json` and `notes.json` in
  `data/books/truyen-co-dan-gian-cham/`; `--no-rerender` skips the 600 dpi pass.
  Drop caps whose letter isn't clear start with `⚠ dropcap?`, and every
  disagreement between the mục lục, the headings and `structure.yaml` is listed
  in `toc.json`.

No outputs of this book are committed: run both commands to make them.

## Reviewing a book

```sh
python -m vsc_ocr review truyen-co-dan-gian-cham     # opens http://127.0.0.1:8765/
```

A local page with `book.md` on the left, one section at a time, and the scan
on the right; clicking a paragraph shows its page with the OCR lines it came
from boxed. A box that misses some of the text can be dragged to move it, or
by an edge or corner to resize it; that's only on screen, nothing is saved.
Any book with a `book.md` works (`--port`, `--no-browser`).

- Edit the paragraph and save (⌘↵). A blank line splits it, emptying it
  deletes it; **Merge with next** joins a paragraph a page break cut in two;
  **Clear ⚠** removes the flags once you've checked it. ⌥↓/⌥↑ go to the
  next/previous paragraph, ⌥⇧↓ (**Next ⚠**) to the next flagged one.
- `book.md` is the only file you edit: notes are edited as their
  `[^id]: ...` lines, and `notes.json` follows.
- The first save keeps the pipeline's output as `book.raw.md`, so
  `diff book.raw.md book.md` is everything you corrected. Each save is also
  appended to `corrections.jsonl` (section, pdf pages, before, after): that
  file is what to hand over when improving the pipeline.
- `assemble` on a reviewed book first moves `book.md`, `book.raw.md` and
  `notes.json` to `review-history/<time>/`, so a re-run never loses
  corrections. `corrections.jsonl` stays and keeps growing.
