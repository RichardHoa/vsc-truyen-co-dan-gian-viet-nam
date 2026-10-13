# Local OCR pipeline (Vietnamese text only)

Turns the **Vietnamese** text of the scanned books into a reviewed markdown
book. Original-language versions (phiên âm, Akhar thrah, bản viết tay, đối
chiếu dị bản, index) are **not** OCR'd; they stay as PDFs, listed in each
book's `structure.yaml`.

The OCR runs locally. Only the optional AI Proofreading Pass runs elsewhere,
on the GPU cluster.

## Setup (macOS, Apple Silicon)

```sh
brew install tesseract tesseract-lang        # Tesseract + Vietnamese model
cd pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-mac.txt
```

Run every command from `pipeline/`: `python -m vsc_ocr <command> ...`.
`<book>` is a book id from `data/books/` (a unique part of it is enough, e.g.
`kalipu`), or `all`.

On Linux, everything except Apple Vision works (`apt install tesseract-ocr
tesseract-ocr-vie`, `pip install -r requirements.txt`); add
`--engines tesseract` to `run`.

## 1. From the scans to book.md

```sh
python -m vsc_ocr inventory                       # once: which pages of each PDF are which book (structure.yaml, committed)
python -m vsc_ocr run <book> --workers 4          # render the pages, OCR them twice, compare, clean, read the mục lục
python -m vsc_ocr assemble <book>                 # write data/books/<book>/book.md, its toc and its notes
python -m vsc_ocr review <book>                   # correct book.md next to the scans
```

- `run` takes a while; pages already done are skipped, so it can be stopped
  and started again. `data/ocr/` isn't committed, so on a new machine `run`
  comes first. `data/ocr/<book>/preview.md` shows the cleaned text page by
  page; **⚠** marks text the two OCR engines disagree on.
- `assemble` exists for books with code of their own: Ariya (Trường ca Chăm)
  and Truyện cổ Dân gian Chăm. Re-running it on a reviewed book first moves
  the reviewed `book.md` to `review-history/<time>/`, so corrections are never
  lost.
- `python -m vsc_ocr status` shows how far each book is.

## 2. Reviewing a book

```sh
python -m vsc_ocr review truyen-co-dan-gian-cham     # opens http://127.0.0.1:8765/
```

`book.md` on the left, one section at a time, and the scan on the right with
the clicked paragraph boxed. A box can be dragged or resized on screen;
nothing about it is saved.

- Edit a paragraph and save (⌘↵). A blank line splits it, emptying it
  deletes it; **Merge with next** joins a paragraph a page break cut in two;
  **Clear ⚠** removes the flags once you've checked it. ⌥↓/⌥↑ go to the
  next/previous paragraph, ⌥⇧↓ (**Next ⚠**) to the next flagged one.
- Notes are edited as their `[^id]: ...` lines.
- `book.raw.md` keeps the pipeline's output, so `diff book.raw.md book.md` is
  everything you corrected; each save is also logged in `corrections.jsonl`.


sometimes one section has 2 boxes, add the ability to remove box

## 3. AI Proofreading Pass

A model on the GPU cluster transcribes every page from its scan and suggests a
whole new text, `book.ai.md`, without touching `book.md`.

```sh
python -m vsc_ocr prepare-ai truyen-co-dan-gian-cham   # everything the cluster needs, in data-for-ai/<book>/
```

1. Run `prepare-ai` after every `assemble`.
2. Copy `data-for-ai/<book>/` to the cluster as `vsc-project/` in the
   resume-scanning repo.
3. There, run `sbatch scripts/submit_correction.sh` (see that repo's README).
4. Copy `book.ai.md`, `ai_corrections.jsonl` and `boxes.jsonl` from the run
   folder back to `data/books/<book>/ai/`.
5. Review the AI's text:

```sh
python -m vsc_ocr review truyen-co-dan-gian-cham --ai
```

It works like `review` but edits `ai/book.ai.md`. Its paragraphs marked
`⚠ ai-missed?` hold OCR text the model left out; other ⚠ mark text the OCR
didn't see, or a note still to place. Your edits are logged in
`ai/corrections.jsonl`; `book.md` is left alone.
