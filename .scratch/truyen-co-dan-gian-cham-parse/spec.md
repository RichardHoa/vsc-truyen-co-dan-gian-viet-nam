# Parse "Truyện cổ Dân gian Chăm" into one Markdown book

Status: ready-for-agent

Book id: `truyen-co-dan-gian-cham` (source: `master_pdf/Truyện cổ Dân gian Chăm.pdf`, 557 PDF pages, scanned images, no text layer).

## Goal

Write code that turns this book into:

1. `data/books/truyen-co-dan-gian-cham/book.md`: the Vietnamese text of the whole book in reading order. The **Lời giới thiệu** is a section of its own, followed by the 58 stories.
2. `data/books/truyen-co-dan-gian-cham/toc.json`: the book's mục lục as structured data, with PDF page ranges.
3. `data/books/truyen-co-dan-gian-cham/notes.json`: every footnote, tied to the place in the text that calls it.

Follow the pattern that Ariya set up (`pipeline/vsc_ocr/books/ariya_truong_ca_cham/`, `.scratch/ariya-book-parse/spec.md`). Book-specific code goes in a new package `pipeline/vsc_ocr/books/truyen_co_dan_gian_cham/` and book-specific rules go in `data/books/truyen-co-dan-gian-cham/assemble.yaml`. It runs as `python -m vsc_ocr assemble truyen-co-dan-gian-cham`. Where Ariya code fits as it is (`superscript.py`, `Stream`, `find_heading`, the TOC row parser), import it or move it to a shared module. Don't copy it. **Ariya's output must not change.** Re-run `assemble ariya-truong-ca-cham` afterwards and diff the results to check.

This book is simpler than Ariya: it has prose only, one language, no versions and no tables. The hard parts are the **typography** (see "Styles that break OCR").

## What the book contains

All page numbers here are **PDF pages** (1-based). Every PDF page holds one printed page. On the pages checked (6, 10, 14, 24, 100, 316, 409, 552, 553) the printed number is PDF − 1. Still use `printed_page_est` from `data/ocr/<book>/pages/pNNNN.json` and report any page where the offset is different. Don't hard-code `−1`.

| PDF pages | Content | Parse? |
|---|---|---|
| 1 | Cover (colour image) | no |
| 2 | Half-title "TRUYỆN CỔ DÂN GIAN CHĂM" | no |
| 3 | Sponsor note (Quỹ Thụy Điển – Việt Nam; Vietnamese + English) | no (see open questions) |
| 4 | Title page: authors, NXB Văn hóa Dân tộc, Hà Nội 2000, handwritten date and signature | metadata only, see step 6 |
| 5 | Blank (show-through only) | no |
| **6–8** | **Lời giới thiệu** (printed 5–7), signed "Phan Rang, thu năm 1997 / TRƯƠNG HIẾN MAI" | **yes, its own section** |
| 9 | Blank (printed 8) | no |
| 10–552 | The 58 stories (per-story ranges in `structure.yaml` `works`) | **yes** |
| 553–555 | Mục lục (printed 552–554) | yes → `toc.json`, not as text in `book.md` |
| 556 | Colophon (publisher, editors, print run, "In xong … tháng 4 năm 2000") | metadata only, see step 6 |
| 557 | Back cover | no |

`structure.yaml` currently lists `unassigned_pages: 1-9,553-557`. Those pages are OCR'd by default, which is fine.

### The mục lục (PDF 553–555)

It has one column on 553–554 and two columns on 555, with these rows:

- `• Lời giới thiệu ........ 5` has a bullet, no number, and printed page 5 (= PDF 6).
- `1. Sự tích gà gáy sáng ........ 9` through `58. Thỏ đi săn thịt cho Chằng Tinh ăn ........ 544` are the stories.

There is no nesting. Every entry is level 1 under the book. Known traps:

- **PDF 555 has two columns** (rows 34–52 on the left, 53–58 on the right). Read them left column first, then right. Don't interleave the rows by height. The page number for a row is the number at the right edge of that row's own column.
- Printing blemishes: row 23 reads "Chàng **J**khổ" and row 50 reads "(tức thằng **J**khổ)". The `J` is a stray mark in the scan, not a letter. Strip it from `toc_title` and report it.
- TOC titles differ from the story's own heading and from the `structure.yaml` title (which came from the split-PDF filenames). Examples:

  | # | Mục lục | Heading on the story's first page | `structure.yaml` title |
  |---|---|---|---|
  | 10 | Pori yak (Thần Sóng) | PÔ RI YAK / (Thần sóng) | Pô Ri Yak (Thần Sóng) |
  | 32 | Ka thar ăn phân chó | (not checked) | Kathăr ăn phân chó |
  | 33 | Hoàng tử Tề Wa Mừ Nô | HOÀNG TỬ TỀWA MỪNÔ | Hoàng tử TềWa MừNô |
  | 47 | Jốt đi học | JÔT ĐI HỌC / (Ja Jốt nao mugru) | Jôt đi học (Ja Jôt nao mugru) |
  | 50 | Jà ri Băh (tức thằng khổ) | THẰNG KHỔ / (Jà ri Băh) | Thằng khổ (Jàri Băh) |
  | 54 | Ta Pa Nrang bỏ xứ | JÀ PA NRANG BỎ XỨ | Jà Pang Nrang bỏ xứ |
  | 56 | Chàng nghèo | JARI BĂH / (Chàng nghèo) | Jari Băh (Chàng nghèo) |

  Match TOC rows to `structure.yaml` works **by order and page**, not by title. Both lists have 58 entries in the same order. Keep all three spellings (see step 3). Don't "fix" one spelling into another.

## Styles that break OCR

These come from the page images. Each one makes the engines drop, merge or misread characters, so handle each one explicitly and test it on the pages named.

### 1. Decorative drop caps

The Lời giới thiệu (p6) and **every story** start with a large ornamental initial (blackletter or engraved style) that spans 2 lines. The rest of the word is printed in body type next to it, and the second line is indented to clear the initial.

| Page | Printed | Initial | Rest of word |
|---|---|---|---|
| 6 | **D**ân tộc Chăm… | D | ân |
| 10 | **C**ứ theo truyền thuyết… | C | ứ |
| 15 | **X**ưa kia… | X | ưa |
| 60 | **N**gày xưa… | N | gày |
| 274 | **H**oàng đế Cuma… | H (looks like a lowercase blackletter `h`) | oàng |
| 316 | **V**ua Itá Ita… | V | ua |
| 465 | **T**huở trước… | T | huở |

The initial is always a plain capital Latin letter **with no diacritic**. Any tone or vowel mark sits on the body-type letters after it ("C" + "ứ", "X" + "ưa"). Expect the OCR to:

- drop the initial ("ứ theo truyền thuyết", "ua Itá Ita"),
- read it as junk or as another letter (`I`, `1`, `)`, `T`→`I`, `H`→`h`/`b`, `X`→`K`, `D`→`Đ`/`ID`),
- glue it onto the **second** line, because that line starts beside it ("Xlàm gì cả", "Ikể lại"),
- or read it as its own line.

What to do: on the first page of each section, find the drop-cap glyph by its size, a single tall ink blob at the left margin spanning about 2 body rows. Remove anything the OCR attributed to it from both lines, and prepend the right capital to the first word. Pick the capital from what makes the first word a Vietnamese (or Cham-name) word: try candidates `A–Z` and choose the one that turns the fragment into a known word or syllable. `vietnamese.py` can help, and so can the second engine. If no candidate is clearly best, crop the glyph and record it as `⚠ dropcap?` instead of guessing. Write every section's chosen initial into the report (59 rows: intro + 58 stories) so they can be checked by eye against the scans in one pass.

Done when the first word of every section is complete. Check this by listing the first 3 words of each section and comparing them with the page images.

### 2. Italics

- The **whole Lời giới thiệu (p6–8) is set in italic**, with one bold italic phrase (*Truyện cổ dân gian Chăm*, p8). Italic Vietnamese is where OCR most often loses or swaps diacritics (`ỏ`/`ở`, `ã`/`ạ`, `ư`/`u`). Expect more engine disagreement here than anywhere else. Use both engines plus `alternatives`, mark every row the engines disagree on with `⚠`, and don't auto-correct.
- Inside stories, Cham words and some glosses are italic: "*kré*" (p85), "*tà rồng*" (p207), "*Chây ula prong*" (p195), "*quá*" (p363), and footnote text "*pui thành pờ-rộ*" (p363). These Cham words have no Vietnamese dictionary support. Don't let a language-correction step "fix" them, and keep them exactly as printed. The OCR gives no style information, so book.md doesn't mark italics (see open questions).

### 3. Small type: footnotes and superscript calls

Footnotes are printed **at the bottom of the page they belong to**, below a short horizontal rule (about 20 % of the text width, at the left), in smaller type. **Numbering restarts on every page.** Most pages that have notes use only `(1)` and some reach `(2)`. One note uses `(*)` instead of a number (p178: "(*) Cốt truyện giống truyện Trời không phụ người nhân đức (trang 63). (B.T.)"). A note can wrap onto a second line in the same small type.

The **call** in the body is a tiny raised `⁽¹⁾`. It is placed:

- glued to the word: `P'Tao-lu-pu⁽¹⁾` (p29), `nôm-đa⁽¹⁾` (p361), `quá⁽²⁾` (p363), `bông⁽²⁾` (p28),
- after a space or after punctuation: `con thịt ⁽¹⁾ cho` (p126), `ở đấy. ⁽¹⁾` (p90, at the very end of a story), `Chây ma ki rum ! ⁽¹⁾` (p195),
- **in a story heading**: `HOÀNG TỬ UMRÚP VÀ CÔ GÁI CHĂN DÊ⁽¹⁾` (p316). This note belongs to the heading.

As in Ariya, OCR drops these calls, glues them on (`thịt(1`, `pu1`), or reads them as junk (`®`, `s)`, `”`, `°`, `'`). Ariya's `superscript.py` finds raised ink clusters in a row. Reuse it.

Pages known to have a footnote rule (from a quick, **incomplete** image scan; it missed p316): 19, 28, 29, 79, 84, 85, 90, 118, 126, 178, 186, 195, 207, 270, 316, 330, 341, 361, 363, 390, 416. Use these as test pages, but find the full set yourself: a rule plus small-type rows starting with `(n)` or `(*)`, low on the page. The shared `clean.py` footnote regex (`_footnote_start`) does **not** match `(*)`, so extend it.

### 4. Other layout marks

- **Scene breaks**: a centred ornament of three asterisks in a triangle (`*` over `* *`, e.g. p118). OCR reads it as stray `*`, `.`, `:`, or nothing. Emit it as one `* * *` line between paragraphs, never as text inside a paragraph.
- **Story headings**: centred, bold, upper case, sometimes 2 lines, often with a second line in parentheses (`PÔ RI YAK` / `(Thần sóng)`, `TRAI KÉN VỢ, GÁI KÉN CHỒNG` / `(Likay Ruah Kamay, Kamy Ruah Li kay)`). The two lines are one heading: a title plus a subtitle. Upper-case Vietnamese with diacritics stacked above capitals (`Ỗ`, `Ầ`, `Ề`) loses marks easily, so take the heading text from the OCR and cross-check it with the TOC row.
- **Dialogue** lines start with `- ` (hyphen and space) at the paragraph indent. Keep the dash. Don't turn these into Markdown list items: escape them in book.md (`\- Hơi con người…`) or write them as the en dash the book means. Pick one, apply it everywhere, and say which in the report.
- Quotation marks are straight `"` in the print (`"phân chó"`, `"Ăn quen Chằng đen mắc bẫy"`). Keep them as OCR reads them.
- Ellipses `...` and the spaced punctuation of the period (`hỏi :`, `rum !`, `quỷ ?`) are part of the printed text. Keep them, don't normalise the spaces.
- Scan noise: show-through from the other side of the page (p5, p9), specks, and a stray mark under the last line on p551. Drop rows that have no letters.
- No running headers. The only page furniture is the page number at the bottom. `clean` already drops it.

## Steps

### 1. OCR every page

Run `python -m vsc_ocr run truyen-co-dan-gian-cham --workers 4` from `pipeline/` (Vision + Tesseract, see `pipeline/README.md`). The default `--pages ocr` covers all 557 pages, because every work is `content: text` plus the unassigned pages.

Done when every page in the "Parse? yes / metadata" rows has a file in `data/ocr/truyen-co-dan-gian-cham/pages/`. Report the pages where `printed_page_est` ≠ PDF − 1.

### 2. Clean, with the book's own rules

Add a book-specific `clean_book` only for what the shared `clean.py` gets wrong on this book: drop caps (style 1), `(*)` footnotes (style 3), and scene breaks (style 4). Keep everything else shared.

Done when, for these test pages, the cleaned `pages/pNNNN.json` is right by eye against the scan: 6, 8, 10, 15, 28, 29, 90, 118, 178, 195, 274, 316, 363, 465, 551. Report what you checked.

### 3. Build `toc.json` from the mục lục

Parse PDF 553–555 (see "The mục lục" above). Output:

```json
{"book": "truyen-co-dan-gian-cham",
 "toc": {"id": "truyen-co-dan-gian-cham", "title": "TRUYỆN CỔ DÂN GIAN CHĂM", "level": 0,
         "pdf_start": 6, "pdf_end": 552, "parse": true,
  "children": [
   {"id": "loi-gioi-thieu", "number": null, "title": "Lời giới thiệu", "toc_title": "Lời giới thiệu",
    "level": 1, "printed_page": 5, "pdf_start": 6, "pdf_end": 8, "parse": true},
   {"id": "su-tich-ga-gay-sang", "number": 1, "title": "SỰ TÍCH GÀ GÁY SÁNG", "subtitle": null,
    "toc_title": "Sự tích gà gáy sáng", "structure_title": "Sự tích gà gáy sáng",
    "level": 1, "printed_page": 9, "pdf_start": 10, "pdf_end": 14, "parse": true},
   …]}}
```

- `id` is the `structure.yaml` work id. The intro is `loi-gioi-thieu`.
- `title` / `subtitle` are the heading as printed on the story's first page (subtitle = the parenthesised second line, without the parentheses or with them, but the same way everywhere). `toc_title` is the mục lục row with the stray `J` removed. `structure_title` is the `structure.yaml` title.
- `pdf_start` comes from the printed page through `printed_page_est`. `pdf_end` is the page before the next entry's start. The intro's `pdf_end` is 8 (p9 is blank).

Then cross-check each story's `pdf_start`/`pdf_end` against `structure.yaml` `versions[0].pages`, and check that the heading is found on `pdf_start`.

Done when all 59 rows (intro + 58) have an entry, every entry has a `pdf_start`, and every disagreement between the TOC, the page heading and `structure.yaml` (page or title) is listed in the report, not silently resolved.

### 4. Resolve footnotes

For every page, split its footnote block into notes (marker, text, joining wrapped rows). Then find each note's call **on the same page**, in the body or the heading.

- A note's identity is (page, marker): `id` = `<section-id>-p<pdf>-<n>` (e.g. `chang-rit-p126-1`; `(*)` → `-star`).
- On one page, calls run 1, 2… in reading order. Use that to reject false calls: a full-size `(1)` in running text that isn't raised, numbers in "(trang 63)", and so on.
- A call the OCR lost: look between neighbouring calls (or anywhere on the page, when there is only one note). Check both engines and `alternatives` first, then the raised-ink detector at high DPI. If it still can't be placed, it is `unresolved`. Never place it by guesswork.
- A note can't continue onto the next page in this book (none seen). If you find one, report it.

`notes.json` follows the Ariya shape, with `scope` = the section id:

```json
{"id": "chang-rit-p126-1", "scope": "chang-rit", "page": 126, "marker": "1",
 "text": "Danh từ người đi săn thường gọi, chỉ những con thú săn bắn được.",
 "note_pdf_pages": [126],
 "call": {"pdf_page": 126, "in": "body", "sentence": "- Gã kia, trả ngay con thịt (1) cho ta để nộp đức vua.",
          "ocr_raw": "con thịt (1) cho", "how": "superscript, read by vision"},
 "status": "resolved"}
```

`in` is `body` or `heading`. `status` is `resolved`, `recovered` (found only through the sequence or the image detector; say how in `call.how`), or `unresolved` (`call` is null). Add a `counts` object per scope, like Ariya.

Done when every footnote on every page is in `notes.json`, the markers on each page run with no gaps or duplicates, every call matches exactly one note on its page, and every `recovered`/`unresolved` note is listed in the report with its page.

### 5. Assemble `book.md`

```markdown
# TRUYỆN CỔ DÂN GIAN CHĂM

<!-- pdf 4 · Trương Hiến Mai, Nguyễn Thị Bạch Cúc, Sử Văn Ngọc, Trương Tôn — dịch, biên soạn, tuyển chọn · NXB Văn hóa Dân tộc, Hà Nội 2000 -->

## Lời giới thiệu

<!-- pdf 6-8 -->

Dân tộc Chăm có một nền văn hoá rất đa dạng …

Phan Rang, thu năm 1997

TRƯƠNG HIẾN MAI

## 1. Sự tích gà gáy sáng

<!-- pdf 10-14 · heading: SỰ TÍCH GÀ GÁY SÁNG -->

Cứ theo truyền thuyết ngày xưa, …
```

- One `##` per TOC entry, in TOC order. The story heading is `## <n>. <title in sentence case>`, with ` (<subtitle>)` when there is one. Use the TOC row's casing as the model, but take the spelling from the page heading. The printed upper-case heading goes in the comment. If you'd rather keep the upper-case heading as the Markdown heading, say so in the report. Either way is fine, as long as it's the same throughout.
- Prose is paragraphs. A paragraph marked `continues` joins the last paragraph of the previous page. Watch for words split by a hyphen at a page break (rare in this book, which justifies text by spacing, not hyphenation).
- Scene break → `* * *`.
- Footnote calls become Markdown footnote references at the call's spot (`… P'Tao-lu-pu[^pram-tich-pram-lac-p29-1] đi qua`). The OCR junk that stood for the call is removed. A call in a heading goes at the end of the heading line. Definitions go at the end of the section: `[^id]: text <!-- note pdf 29 -->`. An `unresolved` note still gets a definition, marked `<!-- call not found -->`.
- Footnote text never appears inside the running prose. Check this by searching book.md for `^\(\d\)` and `(B.T.)` outside definitions.
- The Lời giới thiệu's signature (place/date line, name) is kept as two short paragraphs at the end of the section.
- Keep the text exactly as the OCR read it and printed: no spelling fixes, no modernised diacritics, no change to `hoá`/`hóa` or `y`/`i` variants. Rows flagged `disagree`/`low_conf` get a trailing `⚠`. The only edits allowed are the ones this spec names: the drop-cap letter, removing call junk, removing the stray `J` in TOC titles, and joining across pages.

Done when book.md has the intro + 58 stories as `##` headings in TOC order, each followed by non-empty text; the first word of each section is complete (drop cap); every footnote reference has exactly one definition and every resolved note is referenced exactly once; there is no mục lục text, colophon, sponsor note or page numbers in the body (search for lines that are only digits, and for "NHÀ XUẤT BẢN", "In xong", "Giấy phép").

### 6. Fill in book metadata

From the title page (p4) and the colophon (p556), fill the empty `metadata` block in `structure.yaml`: authors/translators ("Trương Hiến Mai, Nguyễn Thị Bạch Cúc, Sử Văn Ngọc, Trương Tôn", credited as "Dịch, biên soạn, tuyển chọn"), publisher (Nhà xuất bản Văn hoá Dân tộc), place (Hà Nội), year (2000), and the editors from p556 (Chịu trách nhiệm xuất bản: PGS. PTS Hoàng Nam, Trương Hiến Mai; Biên tập: Hoàng Tuấn Cư; …), plus "Trung tâm Nghiên cứu Văn hoá Chăm – Ninh Thuận". Copy the names as printed and check them against the scan, because the colophon is small type. Do it by hand; this needs no code.

### 7. Report

List the files you changed, the commands you ran, and the counts: pages OCR'd, TOC entries, drop caps found / unsure, scene breaks, footnotes by status, `⚠` rows (and how many are in the italic Lời giới thiệu). Include the 59-row drop-cap table, the TOC/heading/structure disagreements, and every judgement call you made. Confirm that Ariya's outputs did not change. Leave the changes uncommitted.

## Open questions (use these defaults unless the user says otherwise)

- **Italics aren't marked** in book.md (no `*…*`), because the OCR gives no style data. If marking italic Cham words turns out to matter, it's a follow-up.
- The sponsor note (p3), half-title (p2), cover and back cover are dropped. The title page and colophon feed `structure.yaml` metadata and the comment under `#`, not body text.
- The intro says the book has "32 truyện" from the centre's archive + "26 truyện do Tuấn Dũng sưu tầm" = 58. The split between the two groups isn't marked in the book, so it isn't recorded.
- If a story turns out to contain verse (a song or chant in short centred lines), keep one line per printed line with a blank line between stanzas, and list those pages in the report.
