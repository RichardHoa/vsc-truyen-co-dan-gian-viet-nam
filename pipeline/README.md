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
two engines disagree on, or text with low confidence.

## The steps in detail

### 1. Inventory: which pages are what (no OCR)

The 15 PDFs in `master_pdf/` are the complete books. Every PDF under
`truyen_nguoi_*/` is a hand-made split of a master (one file per story and
language version) that **re-uses the same scan images**. `inventory` hashes
those images to map each split page to its master page. From that it writes one
`structure.yaml` per book with:

- **works**: the stories/epics, each with its **versions**: `kind`
  (translation, literal-translation, verse-translation, summary, transcription,
  original-script, manuscript, glossary, variant-comparison), `language`, and
  `content: text` (Vietnamese, OCR'd) or `content: pdf` (kept as scan).
  Each version also has its `pages` and the `split_pdf` it came from.
- **unassigned_pages**: pages no split covers (covers, introductions, mục lục,
  colophon). These are OCR'd too, because that's where the book metadata and
  table of contents live.
- **metadata**: empty fields (editors, publisher, year, ISBN, ...) to fill in by
  hand from the title and colophon pages.

Notes:
- "Truyện cổ dân gian Chăm Bình Thuận" has **no master PDF**. Its book is built
  from the 26 split files (`sources:` lists them in order).
- Page numbers in `structure.yaml` are **PDF pages**, not printed page numbers.
- The file is meant to be edited by hand. Re-running `inventory` writes
  `structure.generated.yaml` next to an existing file instead of overwriting it
  (`--force` overwrites).
- `ocr.include` / `ocr.exclude` add or remove page ranges from OCR.

### 2. Render

Renders each page's **crop box** at 300 dpi in grayscale. Most masters store a
two-page spread as one image and show half of it through the crop box; a
renderer that ignored the crop box would OCR both pages twice. Rendering the
1-bit scans with anti-aliasing also helps with small diacritics.

### 3. OCR with Apple Vision

`VNRecognizeTextRequest`, accurate mode, Vietnamese (the language code is
looked up from the OS). Each line is saved with its text, confidence, position
and up to 2 alternative readings.

**Proper names.** The Vietnamese translations are full of Cham/Raglai/Ba Na
names (*Po Ina Nagar, Hbia Tà Lúi, Ka Li Pu, Chiêng Poh Way Takai Gok*) that
Vietnamese language models "correct". `config/custom_words.txt` (all books,
seeded from the work titles) and `data/books/<book>/custom_words.txt` (one book)
are passed to Vision as custom words. Add names there as reviewers find them,
then re-run with `--force`.

`--no-language-correction` turns Apple's language model off entirely. Try it on
`samples` and compare: it can help with names but hurt with diacritics.

### 4. Tesseract (second opinion)

The same pages through Tesseract `vie`. Tesseract alone is usable: on a sample
of these books it made about 2-5 % word errors on 200-300 dpi prose and ~10 %
on difficult pages, mostly diacritics (`ơ/ở/ổ`, `ồ/ô`, `đ/d`). Its job here is
to **disagree** with Vision.

### 5. Compare

Pairs both engines' lines by position and diffs the words. A row is flagged
`disagree`, `low_conf`, `missing_in_secondary` or `only_in_secondary`.
Reviewers then read only flagged rows (typically a few % of rows on clean prose,
more on the 150-dpi Ariya pages) instead of proofreading every page.

### 6. Clean & structure

Per book:
- removes running headers/footers (text repeated at the top/bottom of many
  pages), decorative bands and specks;
- detects the **printed page number**, then fits the printed↔PDF offset across
  neighbouring pages to catch misreads (`printed_page_suspect`) and fill gaps
  (`printed_page_est`);
- detects **prose** vs **verse** pages. Prose rows become paragraphs (indent,
  short line, gap or dash starts a new one); `continues: true` marks a paragraph
  that carries on from the previous page. Verse rows stay one line each, with
  `line_no` split off ("28.", "1940"), `stanza_break`, and `speaker` labels
  ("Già làng nói:");
- marks headings, footnotes, footnote calls `(5)` → `notes`, and source page
  references `[tr.194]` → `source_pages`;
- tags each page's **language** (`vi` / `mixed` / `other`) by checking the
  lowercase words against Vietnamese syllable structure. Pages tagged `mixed` or
  `other` inside a Vietnamese version need a look (bilingual pages, English
  summaries...).

Text is **never corrected**. Misprints in the books stay as printed.

### 7. Mục lục

Finds the page titled MỤC LỤC (or NỘI DUNG) and the pages after it. It
re-OCRs them with Tesseract in table mode (`--psm 6`), which reads
"title ..... page" rows far better than page mode, and parses the entries. It
converts printed page numbers to PDF pages and matches the entries to the works
in `structure.yaml`. On *Truyện cổ dân gian Chăm* this found 58 entries and
matched 55 of them; the rest had OCR noise in the item number. For a book
without per-story splits, `toc.generated.yaml` is the starting point for its
list of works.

## Measuring accuracy

Type the exact text of a few pages into `data/groundtruth/<book>/pNNNN.txt` and
run `python -m vsc_ocr evaluate <book>`. It reports CER (characters), WER
(words) and DER (CER with diacritics removed, so CER − DER ≈ diacritic-only
errors) for Vision, Tesseract and the cleaned text. Do this on the 7 pages in
`config/samples.yaml` before running whole books, to choose between language
correction on/off and to check the thresholds.

## Page JSON (`data/ocr/<book>/pages/pNNNN.json`)

```json
{
  "page": 50, "printed_page": 48, "printed_page_est": 48, "printed_page_suspect": false,
  "mode": "verse",
  "language": {"guess": "vi", "invalid_ratio": 0.02, "words": 212},
  "segments": [
    {"kind": "speaker", "text": "Già làng nói:", "bbox": [0.13, 0.31, 0.32, 0.33], "flags": []},
    {"kind": "verse", "text": "Ơ Ma Klu! Ơ Mi Klu lại đây ngồi", "flags": ["disagree"]},
    {"kind": "verse", "line_no": 28, "text": "Ví thật thân phận ta thế nào chẳng ai biết", "stanza_break": true}
  ],
  "removed": [{"text": "48", "why": "page_number"}]
}
```

`kind` is one of `heading`, `paragraph`, `verse`, `speaker`, `footnote` or
`line_number`. `bbox` is `[x0, y0, x1, y1]`, normalised 0–1 from the top-left of
the page image. That's enough for a review tool to highlight the line on the
scan.

## Not done yet

- A review UI (scan next to text, jump to flagged rows, mark pages reviewed).
- Export to the website format (one JSON/Markdown per work), joining
  paragraphs across pages.
- Compressed web copies of the original-language PDFs.
- Filling in the book metadata (by hand, from the title and colophon pages).
