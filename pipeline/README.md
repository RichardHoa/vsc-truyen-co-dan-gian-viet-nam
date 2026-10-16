# Local OCR pipeline (Vietnamese text only)

Turns the **Vietnamese** text of the scanned books into a reviewed markdown
book, the **Final Book**. Original-language versions (phiên âm, Akhar thrah,
bản viết tay, đối chiếu dị bản, index) are not OCR'd; they stay as PDFs,
listed in each book's `structure.yaml`. Everything runs locally except the AI
Proofreading Pass, which runs on the GPU cluster.

## Read this first

In `data/books/<book>/`:

- **`ai/` is your workspace.** It holds the AI draft and every edit you make to
  it. It is not committed, and it is emptied when a new AI pass comes back.
- **`final/` is the saved book.** It is committed, and it is the only copy
  that lasts.
- **`finalize` is the save button:** it copies `ai/` into `final/` and rebuilds
  the toc and notes from the text.

Three rules:

1. **Every change ends with `finalize`, then a commit.**
2. **Never edit `final/` by hand.** The next `finalize` overwrites it.
3. **Never empty `ai/` before finalizing and committing it**, or its edits are lost.

## The four stages

```
1. OCR        scans ──run──▶ data/ocr/<book>/ ──assemble──▶ book.md        OCR draft
2. AI pass    prepare-ai ──▶ GPU cluster ──copy back──▶ ai/book.ai.md      AI draft
3. Review     review --ai, review --ai --diacritic  (edits ai/)
4. Finalize   finalize ──▶ final/ ──▶ git commit                           Final Book
```

**Fix the text, rename a story or change the toc** of a finished book:
`review --ai`, then `finalize`, then commit.

**Run a new AI pass** (a better model or prompt) on a finished book: stage 2,
then `apply-corrections` to carry your earlier edits over, then stages 3–4.

## Setup (macOS, Apple Silicon)

```sh
brew install tesseract tesseract-lang
cd pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-mac.txt
```

On Linux: `apt install tesseract-ocr tesseract-ocr-vie`,
`pip install -r requirements.txt`, and add `--engines tesseract` to `run`
(Apple Vision is macOS only).

Run every command from `pipeline/` as `python -m vsc_ocr <command>`. `<book>`
is a book id from `data/books/` (a unique part is enough, e.g. `kalipu`), or
`all`. `status` shows how far each book is.

## 1. OCR

```sh
python -m vsc_ocr inventory                 # once: which PDF pages are which book (structure.yaml)
python -m vsc_ocr run <book> --workers 4    # OCR every page twice, compare, clean, read the mục lục
python -m vsc_ocr assemble <book>           # write book.md, toc.json, notes.json
python -m vsc_ocr review <book>             # optional: check the OCR at http://127.0.0.1:8765/
```

- `run` is slow but resumable. `data/ocr/` isn't committed, so on a new
  machine `run` comes first. `data/ocr/<book>/preview.md` shows the cleaned
  text; **⚠** marks where the two OCR engines disagree.
- `assemble` only works for books with code in `vsc_ocr/books/` (Ariya and
  Truyện cổ Dân gian Chăm); a new book needs its own folder there.
- Edits made in the OCR-draft `review` never reach the Final Book, and the
  next `assemble` overwrites them.

## 2. AI Proofreading Pass

1. `python -m vsc_ocr prepare-ai <book>` writes `data-for-ai/<book>/`. Run it
   again after every `assemble` and after changing `spellings.yaml` or
   `titles.yaml`, so the pass uses them.
2. Copy `data-for-ai/<book>/` to the cluster as `vsc-project/` in the
   resume-scanning repo, and run `sbatch scripts/submit_correction.sh` there.
3. When it's done: make sure the current `ai/` is finalized and committed,
   **empty `data/books/<book>/ai/`**, then copy `book.ai.md`,
   `ai_corrections.jsonl` and `boxes.jsonl` from the run folder into it.
4. If the book already has a `final/`, carry your earlier edits over:
   `python -m vsc_ocr apply-corrections <book>` (see
   [below](#how-apply-corrections-works)).

## 3. Review

```sh
python -m vsc_ocr review <book> --ai              # edit the text
python -m vsc_ocr review <book> --ai --diacritic  # then decide the spellings
```

**`review --ai`** shows the text on the left and the scan on the right.

- Save a paragraph with ⌘↵. A blank line splits it, emptying it deletes it,
  and **Merge with next** joins one a page break cut in two.
- Notes are edited as their `[^id]: ...` lines.
- Editing a story heading sets its Story Title in `titles.yaml`.
  `## 12. Title (subtitle)` gives the number, title and subtitle.
- Clear every ⚠: `⚠ ai-missed?` is OCR text the model left out; other ⚠
  are text the OCR didn't see, or a note to place. **Clear ⚠** removes a flag;
  ⌥⇧↓ jumps to the next one, ⌥↓/⌥↑ to the next/previous paragraph.
- Boxes on the scan can be moved or resized, but that isn't saved.

**`--diacritic`** lists words spelled with the same letters but different marks
(`Têwa` / `Tềwa`), showing the AI's, Vision's and Tesseract's reading next to
the scan. Picking the printed one saves a Spelling Rule in `spellings.yaml`
and applies it at once.

- A word also printed in lower case gets a phrase rule (the word with its
  neighbours), or **Depends** (decided per occurrence, no rule).
- In **Ruled**, a different spelling at one occurrence makes a story exception.

## 4. Finalize

```sh
python -m vsc_ocr finalize <book>
git add data/books/<book>/final data/books/<book>/spellings.yaml data/books/<book>/titles.yaml
```

`finalize` replaces `final/` with:

- `book-final.md`: a copy of `ai/book.ai.md`;
- `corrections.jsonl`: a copy of `ai/corrections.jsonl`, the log of your edits;
- `toc.json`: the stories, built from the headings (below);
- `notes.json`: every `[^id]: …` note in the text.

It refuses while any ⚠ is left, on a new pass that `apply-corrections` hasn't
run on (`--force` to skip), and when the OCR draft's `toc.json` is missing or
has no story where a heading starts. It can be run on the same pass any
number of times.

**The toc:** number, title, subtitle and pdf pages come from the headings, so
edit those in `review --ai`. The story `id` and printed page come from the OCR
draft's `toc.json` (the scanned mục lục), matched by the pdf page a story
starts on. So a new heading must start on a page where the mục lục has a
story.

## 5. Publish the Web Edition

```sh
python -m vsc_ocr export-web <book>
```

writes `data/books/<book>/web/<book>/`, the **Web Edition**: `loi_gioi_thieu.md`,
one `story_NNN.md` per story and `table_of_contents.json`, in the format the
website's Book Reader reads. Copy that folder into the website's
`public/data/`. It is generated from `final/book-final.md` alone and never
edited: fix the Final Book (stage 3–4) and run `export-web` again.

It needs `printed_page_offset` in `structure.yaml` (printed page = pdf page −
offset), and `web_title`, the book title the website shows. It writes nothing, and
lists every problem, unless the headings are the Lời giới thiệu and stories 1
to the number of `works`, each with its `<!-- pdf a-b -->`, every note is
called once and has its `<!-- note pdf N -->`, and the text has only Markdown
the website renders (paragraphs, `\-` dialogue, hard-break verse, `###`).

## Reference

### What's in `data/books/<book>/`

| File | What it is | Committed |
|---|---|---|
| `structure.yaml` | which PDF pages are which part of the book | yes |
| `final/` | the Final Book | yes |
| `web/<book>/` | the Web Edition, from `export-web` | no |
| `spellings.yaml` | Spelling Rules, applied by every AI pass | yes |
| `titles.yaml` | Story Titles, written as set by every AI pass | yes |
| `ai/` | your workspace: `book.ai.md` (text), `corrections.jsonl` (your edits), `book.ai.raw.md` (the pass as it came back), `ai_corrections.jsonl` (the model's log), `replayed.json` / `finalized.json` (bookkeeping) | no |
| `book.md`, `book.raw.md` | the OCR draft and `assemble`'s untouched copy | no |
| `corrections.jsonl` | edits made to the OCR draft | no |
| `toc.json`, `notes.json` | the OCR draft's mục lục and notes | no |
| `toc.generated.yaml` | the OCR's raw reading of the mục lục, read by `assemble` | no |

Everything uncommitted can be rebuilt from the scans or the cluster's run
folder, except edits in `ai/` that haven't been finalized.

### How `apply-corrections` works

A new pass words paragraphs a little differently, so earlier edits can't just
be copied over. `apply-corrections` replays each edit from
`final/corrections.jsonl` onto `ai/book.ai.md` wherever its original text is
still found: in its own story, else anywhere it appears exactly once.

- Replayed edits are logged in `ai/corrections.jsonl`.
- Edits it couldn't place are printed and saved in `ai/replayed.json`. Redo
  them in `review --ai`; any you don't redo leave the log at the next
  `finalize` (git history keeps them).
- Spelling edits are skipped: the pass applies `spellings.yaml` itself.

Run it once per pass, before reviewing. It refuses if `ai/corrections.jsonl`
already has edits (`--force` to override).
