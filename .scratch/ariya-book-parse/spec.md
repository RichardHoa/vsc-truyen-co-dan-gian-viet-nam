# Parse "Ariya (Trường ca Chăm)" into one Markdown book

Status: ready-for-agent

Book id: `ariya-truong-ca-cham` (source: `master_pdf/Ariya (Trường ca Chăm).pdf`, 530 PDF pages).

## Goal

Write a script that turns this book into:

1. `data/books/ariya-truong-ca-cham/book.md`: the Vietnamese text of the whole book, in reading order.
2. `data/books/ariya-truong-ca-cham/toc.json`: the book's mục lục as structured data, with PDF page ranges.
3. `data/books/ariya-truong-ca-cham/notes.json`: every **Chú thích** note, tied to the sentence that cites it and to PDF pages (see "Chú thích" below).

This book is the first one. Write the script so other books can reuse it later: book-specific rules go in data (`structure.yaml` or a small per-book config), not in the code. Add it as a `python -m vsc_ocr assemble <book>` subcommand next to `clean` and `toc` (see `pipeline/vsc_ocr/__main__.py`).

## What the book contains

All page numbers here are **PDF pages** (1-based), not printed pages. The offset between them changes through the book (p10 is printed 12, p142 is printed 143). Use `printed_page_est` in `data/ocr/<book>/pages/pNNNN.json`, never a fixed offset.

| PDF pages | Content | Parse? |
|---|---|---|
| 1–4 | Cover, title page, Lời mở | yes (skip the cover image) |
| 5–86 | Introduction: A. Phần dẫn nhập, B. Phân tích tác phẩm (one section per epic), with a Chú thích block (e.g. 82–86) | **yes, all of it** |
| 87–507 | The four epics: Cam-Bini, Xah Pakei, Glong Anak, Ppo Parong (per-version ranges in `structure.yaml`) | partly, see below |
| 508–513 | Bảng chuyển tự / Hệ thống chuyển tự Latin (tables with a Cham-script column) | yes, without the Cham-script column |
| 514–518 | Thư mục tham khảo (bibliography) | **yes** |
| 519–521 | Mục lục (Vietnamese) | yes → `toc.json` (not as text in `book.md`) |
| 522–524 | Table of contents (English) | no (duplicates 519–521) |
| 525–530 | Author bio (Inrasara), series list, back cover | no |

Each epic in `data/books/ariya-truong-ca-cham/structure.yaml` lists its `versions` by `kind`. Parse a version according to its kind:

| `kind` | Section in the book | Parse? |
|---|---|---|
| `original-script` | Akhar thrah (Cham script) | **no** |
| `transcription` | Phiên âm Chăm (Cham in Latin letters) | **no** |
| `variant-comparison` | Đối chiếu dị bản | **yes**. Vietnamese prose that quotes Cham words in Latin letters; keep the quotes as printed |
| `literal-translation` | Dịch nghĩa (numbered couplets "1. … / …") | **yes** |
| `verse-translation` | Dịch thơ (unnumbered verse, stanzas) | **yes, when it exists**. Ppo Parong has none |
| `glossary` | Index: Cham word → page refs → Vietnamese gloss (e.g. p142) | **no** |
| `manuscript` | Bản viết tay (handwritten scans) | **no** |

## Chú thích (notes)

Some sections end with a **Chú thích:** block, and some don't. The block starts after a short horizontal rule with the bold label "Chú thích:", followed by numbered notes "(1) …", "(2) …". Example: the introduction's block starts on p82 below the end of the Ppo Parong analysis and runs to p86. A note can wrap across a page break (p84's note (19) carries on to p85). Treat each block's numbering as its own **scope**. Numbering restarts per block, so a note's identity is (scope, number), never the number alone.

In the body text, the **call** that points to a note comes in two forms:

- **Full size in parentheses**: `… vô cùng (6).`
- **Tiny superscript**, usually with parentheses: `vô cùng⁽⁶⁾.` (p10). These are tiny, so OCR mangles them. Expect the call to be dropped entirely, glued onto the word (`cùng6`, `cùng(6`), or read as junk (`®`, `s)`, `”`, `°`). p316 is a live example: Vision read `chễm chệs)` and Tesseract read `chệ®)`, which is almost certainly the call `chệ⁽⁵⁾`. Check `secondary` and `alternatives` in `merged/pNNNN.json` too, because one engine often keeps what the other drops.

Calls in a scope run 1, 2, 3… in reading order. Use that sequence to find calls and to reject false ones. A number in parentheses that breaks the sequence ("(câu 189-193)", list items "(1)", verse numbers) is not a call. A gap in the sequence means a call is missing, and its location is narrowed to the text between the calls on either side of it.

## Steps

### 1. OCR every page that will be parsed

Only p316 has been OCR'd so far (`ls data/ocr/ariya-truong-ca-cham/merged`). The default `--pages ocr` selection covers `content: text` versions plus `unassigned_pages`. `variant-comparison` is marked `content: pdf`, so it is **not** OCR'd by default. Add its pages to `ocr.include` in `structure.yaml` (117-124, 208-213, 307-312, 425-428), then run `python -m vsc_ocr run ariya-truong-ca-cham` from `pipeline/` (see `pipeline/README.md` for setup).

Done when every page in the "Parse? yes" rows has a file in `data/ocr/ariya-truong-ca-cham/pages/`, and no skipped page (Cham script, transcription, glossary, manuscript) was OCR'd.

### 2. Fix verse turnover lines in `clean.py`

In verse mode, `_structure` makes one segment per printed row. A verse line too long for the page is printed with its end flush right on the next row. Example: p316 "Muốn dập tắt lửa thiêng nơi quê hương" / "Panduranga ta dây". That end has to be joined back onto its line. A row is a turnover when it has no verse number, there is no gap above it (gap < 0.5 × median row height), it starts well past the indent (`x0 > left + 0.35 × width`) and it ends at the right margin. Append it to the previous verse segment (text, bbox, flags).

Done when p316's verse 32 is one segment, and a count of turnover joins across all verse pages has been spot-checked against the page images for false joins (centred epigraphs, signature lines). Report the count and anything you checked.

### 3. Build `toc.json` from the mục lục

`python -m vsc_ocr toc` already parses the mục lục into `toc.generated.yaml`. Build `toc.json` from that output, nested like the printed mục lục (A./B./C. → I./II. → 1./2. → a./b.). Each entry has `title`, `level`, `printed_page`, `pdf_start`, `pdf_end`, and `parse: true|false` following the tables above. Then cross-check the epic entries against the version ranges in `structure.yaml`.

Done when every printed mục lục row on PDF pages 519–521 has an entry, every entry has a `pdf_start`, and any disagreement between the TOC and `structure.yaml` is listed in your report instead of being silently resolved.

### 4. Resolve Chú thích

Find every Chú thích block and split it into notes (number, text, PDF pages it is printed on, joining notes that wrap across pages). Then find each note's call in the body of the same section, following "Chú thích (notes)" above. For a call the OCR lost, look in the text between its neighbours: check both engines' text and alternatives first, then re-render that stretch at high DPI and look for the superscript. A call you cannot place stays `unresolved`. Never place a call by guesswork.

Write `notes.json`, one entry per note:

```json
{"id": "gioi-thieu-6", "scope": "gioi-thieu", "number": 6,
 "text": "Chỉ đến đầu thập niên 60 của thế kỉ XX, …",
 "note_pdf_pages": [83],
 "call": {"pdf_page": 10, "sentence": "Và sau cùng là tình trạng bất hoàn chỉnh … đến vô cùng.",
          "ocr_raw": "vô cùng(6).", "how": "superscript, read by vision" },
 "status": "resolved"}
```

`status` is `resolved`, `recovered` (the call was found only through the sequence gap or a re-render; say how in `call.how`), or `unresolved` (`call` is null).

Done when every note in every Chú thích block appears in `notes.json`, the numbers in each scope run with no gaps or duplicates, every call found in the body matches exactly one note, and every `unresolved` and `recovered` note is listed in your report with its page.

### 5. Assemble `book.md`

Walk `toc.json` in order. For each `parse: true` entry, emit the cleaned segments from its pages (`data/ocr/<book>/pages/pNNNN.json`):

- Headings follow the TOC nesting (`#` book, `##` A./B./C. or epic, `###` subsections, and so on).
- Prose is paragraphs. A paragraph marked `continues` joins the last paragraph of the previous page.
- **Dịch nghĩa**: keep the printed couplet numbers ("1." on the first line of each couplet).
- **Dịch thơ**: one line per verse line, a blank line at each `stanza_break`.
- Chú thích: the call becomes a Markdown footnote reference at the call's spot, using the note id (`… vô cùng[^gioi-thieu-6].`). The OCR junk that stood for it (`s)`, `®`) is removed. The block at the end of the section becomes the footnote definitions, each with its pages: `[^gioi-thieu-6]: Chỉ đến đầu thập niên 60 … <!-- note pdf 83 · called on pdf 10 -->`. An `unresolved` note still gets its definition, marked `<!-- call not found -->`.
- Drop running headers/footers ("ariya cam/trường ca chăm 317", "inrasara") and page numbers. `clean` already removes most of them; check what's left.
- After each section heading, add an HTML comment with its PDF pages (`<!-- pdf 125-136 -->`) so a reviewer can find the scan.
- Keep the text exactly as the OCR read it and printed: no spelling fixes, no modernised diacritics. Rows flagged `disagree`/`low_conf` get a trailing `⚠` like `preview.md` does.

Done when `book.md` has every `parse: true` TOC entry as a heading, in order, each followed by non-empty text; every footnote reference has exactly one definition and every resolved note is referenced exactly once; and none of the `parse: false` content (Cham script, transcription, Index word lists, manuscript) shows up in it. Check that last one by searching for glossary-style lines (`word  12, 34  gloss`) and Cham-only stanzas.

### 6. Report

List the files you changed, the commands you ran, the counts (pages OCR'd, TOC entries, turnover joins, notes by status per scope, ⚠ rows), and every judgement call you made. Leave the changes uncommitted.

## Open questions (use these defaults unless the user says otherwise)

- Cham verse quoted inside the **introduction** (e.g. p40, Cham lines followed by their Vietnamese translation) stays. The introduction is parsed in full, quotes and all.
- The English table of contents (522–524) is dropped.
- The transliteration tables (508–513) become Markdown tables without the Cham-script column, as far as the OCR allows. Where the table OCR is unusable, emit the heading plus a `<!-- table not parsed, see pdf 508-513 -->` note instead of guessing.
- The author bio and series list (525–530) are dropped.
