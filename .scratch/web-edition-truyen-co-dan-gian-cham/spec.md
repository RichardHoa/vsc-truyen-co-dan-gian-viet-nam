# Web Edition of "Truyện cổ dân gian Chăm", read on the website like Kho Tàng

Status: ready-for-agent

Book id: `truyen-co-dan-gian-cham`. Website: the `digitizing-vietnam-website` repo (Next.js), Collection Item `/our-collections/vietnamese-folk-literature/truyen-co-dan-gian-cham`.

## Problem Statement

The Final Book of *Truyện cổ dân gian Chăm* is finished and reviewed, but it exists only as one large Markdown file in this repo. Nobody can read it on the Digitizing Việt Nam website. The website already has a good reader for another book of folk tales, *Kho tàng truyện cổ tích Việt Nam*. That reader has a contents panel with search on one side and the open story with previous/next links on the other, Footnotes that pop up, and a link to every Entry. But it reads only Kho Tàng's own data folder, laid out in Parts and Sections, and its code is written for that one book. The Chăm book also has quirks the website can't take as they are. Its Notes use named ids, it carries review comments, its dialogue dashes are escaped, its verse is written with Markdown hard breaks, and its table of contents (`toc.json`) has three wrong printed page numbers (stories 31, 32 and 34) because they were OCR'd from the printed Mục lục.

## Solution

Two pieces of work:

1. **The Web Edition (this repo).** A new pipeline command generates the Web Edition from the Final Book. It writes a folder with one Markdown file for the Lời giới thiệu, one per story, and a `table_of_contents.json`, all in the format the website's reader reads. The developer copies that folder into the website's public data by hand. The Web Edition is never edited. A fix goes into the Final Book, and the Web Edition is generated again.
2. **The Book Reader (website repo).** The Kho Tàng reader becomes a general **Book Reader** driven by a per-book config. Kho Tàng keeps behaving exactly as it does today. The Chăm book replaces Mirador on its Collection Item with the same layout and story display. Its contents panel is a plain list (no tabs, since the book has no Parts), and its search box matches story titles.

## User Stories

### Reader on the website

1. As a website reader, I want to open `/our-collections/vietnamese-folk-literature/truyen-co-dan-gian-cham` and read the book as digitized text instead of page scans, so that I can read the stories comfortably.
2. As a website reader, I want the Chăm book to look and behave like the Kho Tàng reader, so that the site feels consistent across books.
3. As a website reader, I want the book to open on the Lời giới thiệu, so that I start where the printed book starts.
4. As a website reader, I want a contents panel listing the Lời giới thiệu and then stories 1 to 58 in book order, so that I can see everything the book holds.
5. As a website reader, I want no tab bar in the contents panel, because the book has no Parts and an empty one-tab bar would only be noise.
6. As a website reader, I want each story listed with its number and printed title, so that I can find it the way the printed Mục lục shows it.
7. As a website reader, I want story titles listed without Note Call marks, so that the list reads cleanly.
8. As a website reader, I want to search story titles ignoring case and diacritics (so "su tich ga" finds "Sự tích gà gáy sáng"), so that I can find a story without typing Vietnamese marks.
9. As a website reader, I want the search results to replace the list while I have a query, and the list to come back when I clear it, as in Kho Tàng.
10. As a website reader, I want to open a story from the list or the search results, so that I can read it.
11. As a website reader, I want previous/next links on every Entry following book order, so that I can read straight through.
12. As a website reader, I want every Entry to have its own link (`?muc=loi-gioi-thieu`, `?muc=truyen-1` … `?muc=truyen-58`), so that I can share or bookmark a single story.
13. As a website reader, I want an unknown or missing `?muc=` to open the Lời giới thiệu, so that a bad link still shows the book.
14. As a website reader, I want each story to start with its heading as printed ("5. Prăm Tịch, Prăm Lắc"), including any subtitle the book prints ("10. Pô Ri Yak (Thần sóng)"), so that the text matches the book.
15. As a website reader, I want a Note Call printed in a story's title to show as a note link in the story's heading, so that I see the note where the book prints it.
16. As a website reader, I want Note Calls in the text to be numbered 1, 2, 3… within each story, so that they are easy to follow.
17. As a website reader, I want clicking a Note Call to open its Note in a popover, as in Kho Tàng, so that I can read it without losing my place.
18. As a website reader, I want each Note to begin with "(Trang N)", N being the printed page it appears on, so that I can find it in the printed book.
19. As a website reader, I want the Notes listed at the end of each story under "Chú thích", so that I can read them all together.
20. As a website reader, I want dialogue lines to start with a plain dash, not "\-", so that the text reads as printed.
21. As a website reader, I want verse (songs, ca dao, Cham chants) shown as verse lines, so that the poetry keeps its line breaks.
22. As a website reader, I want the Lời giới thiệu's closing place, date and signature ("Phan Rang, thu năm 1997" / "TRƯƠNG HIẾN MAI") right-aligned, like Kho Tàng's Preface signature.
23. As a website reader, I want no review traces (pdf page comments, heading OCR, note tags) in the text, so that I see only the book.

### Kho Tàng reader (must not change)

24. As a Kho Tàng reader, I want the Kho Tàng reader to look and behave exactly as before (tabs per Part and for the Bibliography, Story Name Index search with name highlighting and Footnote targeting, Preface first, previous/next, `?muc=` slugs), so that the generalization costs me nothing.
25. As a Kho Tàng reader, I want every existing Kho Tàng link (`?muc=`, `?ten=`, `?chu-thich=`) to keep working.

### Developer / editor

26. As a developer, I want one pipeline command that generates the Web Edition of a book from its Final Book, so that publishing a book is one step.
27. As a developer, I want the Web Edition generated from the Final Book alone (not `toc.json`), so that wrong numbers from the OCR'd Mục lục can't reach the website.
28. As a developer, I want the Web Edition written into the book's own folder in this repo, which I then copy into the website by hand, so that nothing writes into the website repo behind my back.
29. As a developer, I want the generated folder ignored by git in this repo, since it can always be generated again.
30. As a developer, I want printed page numbers worked out from the pdf page and the book's printed-page offset, so that every page number in the Web Edition follows one rule.
31. As a developer, I want the offset recorded in the book's `structure.yaml` (`printed_page_offset: 1` for this book, meaning printed page = pdf page − 1), so that it sits with the other facts about the scan.
32. As a developer, I want the command to refuse to run when the book has no `printed_page_offset`, so that a page number is never guessed.
33. As a developer, I want the command to refuse to write anything unless the Final Book has exactly the Lời giới thiệu and stories 1 to 58, numbered in order, so that a broken heading can't publish a broken book.
34. As a developer, I want the command to refuse to write anything when any story's Note Calls and Note Definitions don't pair one-to-one, so that no Note is lost or orphaned.
35. As a developer, I want the command to refuse to write anything when any Note Definition lacks its `note pdf N` tag, so that every Note gets its page.
36. As a developer, I want every refusal to name the stories and Notes at fault, so that I can fix the Final Book quickly.
37. As a developer, I want the TOC JSON to record each Entry's Note count, so that the website's own count check still catches a mismatch.
38. As a developer, I want the TOC JSON to record each Entry's printed start and end pages, as Kho Tàng's does.
39. As a developer, I want running the command twice on the same Final Book to give byte-identical output, so that copying it into the website shows a clean diff.
40. As a developer adding a later book, I want the Book Reader to take a book config (data folder, Collection Item, whether it has Parts/tabs, a Story Name Index, a Bibliography), so that a new book is mostly config plus its Web Edition.
41. As a developer, I want the website glossary to describe the Chăm book and the Book Reader, so that the site's vocabulary matches the code.

## Implementation Decisions

### Web Edition export (this repo, Python pipeline)

- **Glossary.** The output is the **Web Edition** (already in this repo's `CONTEXT.md`). The input is the **Final Book**. It is the only input, and `toc.json` is not read.
- **New pipeline command**, next to `finalize`, run as `python -m vsc_ocr export-web <book>`. It is generic, but the only book that has one today is `truyen-co-dan-gian-cham`.
- **Module shape: one pure function at the seam.** It takes the Final Book's text and the printed-page offset and returns the Web Edition as a mapping of relative path → file content. If any check fails, it raises one error listing every problem. The command only reads `structure.yaml` and the Final Book, calls the function, and writes the files. If anything fails, it writes nothing.
- **Output location.** The book's folder in this repo, at `web/<book-id>/`, so the folder to copy is named after the book. The whole `web/` folder is gitignored. Before writing, the command empties its own output folder, so stale files can't survive.
- **Book config.** `structure.yaml` gains `printed_page_offset: 1` for this book. Printed page = pdf page − `printed_page_offset`. A missing field is a refusal.
- **Output files** (flat: no Part or Section folders):
  - `loi_gioi_thieu.md`: the Lời giới thiệu.
  - `story_001.md` … `story_058.md`: one per story, zero-padded to three digits.
  - `table_of_contents.json`.
- **TOC JSON shape.** It mirrors Kho Tàng's root TOC, without Parts and Sections:
  - `book_title: "Truyện cổ dân gian Chăm"` (sentence case, not the all-caps heading).
  - `preface: { title: "Lời giới thiệu", markdown_file, start_page, end_page, footnote_count }`.
  - `stories: [{ story_number, title, start_page, end_page, markdown_file, footnote_count }]` in book order.
  - `title` is the Story Title exactly as the Final Book's heading sets it (subtitle included), minus any Note Call.
  - Pages come from the `<!-- pdf a-b -->` comment under each heading. A single page `pdf a` means start = end.
  - `has_khao_di` is omitted: the book has no Khảo dị.
- **Story file content.**
  - It starts with `## N. Title` for stories and `## Lời giới thiệu` for the Preface. A Note Call in the title stays in the heading. There is no `#` Section line, since there are no Sections.
  - Every HTML comment is removed: pdf ranges, heading OCR, `note pdf` tags and the book-level comment.
  - **Notes.** Within each Entry, the named Note Calls `[^some-id]` are renumbered `[^1]…[^n]` in reading order, the title heading included. The Note Definitions are moved, in the same order, to the end of the file after a `---` line and a `### Chú thích` heading. This is exactly the delimiter and positional pairing the website's footnote parser expects. Each definition becomes `[^k]: (Trang N) <text>`, with N = the `note pdf` page − offset.
  - **Dialogue dashes.** A line starting with `\- ` becomes `- `. The website renders Stories' `- ` lines as prose, and Kho Tàng's text uses the plain dash.
  - **Hard-break blocks.** A block whose lines end with Markdown hard breaks (two trailing spaces) becomes verse: every line of the block is written as `> line`, with the trailing spaces removed. **The one exception** is the Lời giới thiệu's closing block (place/date and signature), whose lines become `-> ` right-aligned lines, as in Kho Tàng's Preface.
  - Any other Markdown the website renderer doesn't handle (it supports `#`–`###` headings, plain paragraphs, `> ` verse, `-> ` right-aligned lines and footnote links) is a refusal, not silently passed through.
- **Checks (any failure means nothing is written; the error lists every failure):**
  - The Final Book's headings are exactly `Lời giới thiệu` and then `1.` … `58.` in order, each followed by a pdf range comment.
  - Within each Entry, every Note Call has exactly one Note Definition and every Note Definition is called exactly once.
  - Every Note Definition has a `note pdf N` tag.
- **Deterministic output.** Stable key order and formatting in the JSON, UTF-8, `\n` line endings, and one trailing newline per file.

### Book Reader (website repo, Next.js)

- **Generalize, don't copy.** The Kho Tàng searchable-text module (data loader, reader, Markdown and footnote rendering, footnote popover) becomes a Book Reader parameterized by a **book config**. There are two configs: Kho Tàng and the Chăm book.
- **Book config** carries at least:
  - the Collection Item it replaces Mirador on (collection id + document id),
  - its public data folder,
  - its TOC shape: Kho Tàng's Parts → Sections → Stories/Essays plus the Bibliography, or the flat Preface + Stories,
  - its search source: the Story Name Index (Kho Tàng) or story titles (Chăm),
  - its translation keys or labels.
- **Data loader.** It reads the config's TOC JSON into the same divisions → sections → entries model Kho Tàng uses today. A flat book becomes one division whose entries are the Preface and then the Stories. The `?muc=` slugs are `loi-gioi-thieu` and `truyen-<n>`. Book order, the default Entry (the Preface), lookup, previous/next and the footnote count check work the same for both books.
- **Lời giới thiệu is the Chăm book's Preface** (same Entry kind as Kho Tàng's Preface), shown under its printed title.
- **Contents panel.** When a book has a single division, the tab bar is hidden and the panel shows the search box and then the list.
- **Search for the Chăm book** matches story titles (and the Preface title) with the same case- and diacritic-insensitive key the Kho Tàng search uses. There is no name highlighting and no Footnote targeting; `?ten=` and `?chu-thich=` are simply ignored for this book.
- **Rendering** is unchanged. The Web Edition is written in the dialect the renderer already supports, so no renderer feature is added.
- **Routing.** The Collection Item page dispatches to the Book Reader when the collection/document pair matches either book's config, replacing the current Kho Tàng-only branch.
- **Strapi** still supplies the Collection Item's title, abstract and metadata. The Collection Item `truyen-co-dan-gian-cham` in `vietnamese-folk-literature` is assumed to exist.
- **Website glossary.** Add to the website's `CONTEXT.md` a "Truyện cổ dân gian Chăm" section: the Book is the Preface (Lời giới thiệu) plus 58 Stories. It has no Parts, Sections, Essays, Khảo dị or Story Name Index, and its search covers story titles. Also add the **Book Reader** term (the item viewer for a digitized book, driven by a book config). Kho Tàng's existing terms stay as they are.

## Testing Decisions

- **Good tests check external behaviour only.** Feed a Final Book's text in and assert on the files that come out, or on the refusal. Never test helper functions or intermediate structures.
- **Pipeline: one seam, the pure export function**, tested with pytest in the style of the existing Final Book replay tests (small fixture books written inline as lists of lines). Cases:
  - The Lời giới thiệu and stories become the expected file names, and the TOC JSON has the right titles, numbers, pages (pdf − offset) and Note counts.
  - Named Note Calls are renumbered per Entry in reading order, including a call in the title heading, which stays in the heading but not in the TOC title.
  - Definitions move under `---` / `### Chú thích` with a `(Trang N)` prefix.
  - All HTML comments are removed.
  - `\- ` becomes `- `.
  - A hard-break block becomes `> ` verse lines, and the Lời giới thiệu's closing block becomes `-> ` lines.
  - Each refusal: missing offset, a missing or out-of-order story number, a call without a definition, a definition never called, a definition without `note pdf`, unsupported Markdown. Each one names the culprit, and several problems are reported together.
  - The same input gives identical output.
- **A real-data run** of the command on `truyen-co-dan-gian-cham` must succeed and produce 59 Markdown files and a TOC JSON with 58 stories and 42 Notes in total. The developer runs it (see Further Notes).
- **Website: no automated tests.** The website has no test runner, and none is added. Checking relies on the data loader's existing startup checks (Note counts against content, duplicate slugs) plus a manual browser check:
  - **Kho Tàng:** tabs, Story Name Index search with highlighting and `?chu-thich=` targeting, Preface first, previous/next, and a few old links, all unchanged.
  - **Chăm book:** opens on the Lời giới thiệu, there are no tabs, title search works without diacritics, Note popovers show "(Trang N)", a title Note Call works in the heading, verse and the signature render, and previous/next runs from the Lời giới thiệu to story 58.

## Out of Scope

- Changing or removing `toc.json` (the OCR Draft's or the Final Book's) or fixing its wrong printed pages for stories 31, 32 and 34. `finalize` still produces and uses it. The Web Edition just doesn't read it.
- Building a name index for the Chăm book, or any name highlighting.
- Inventing Parts or Sections, for example grouping by the introduction's "32 translated / 26 collected" split.
- Copying the Web Edition into the website repo automatically. The developer copies it by hand.
- Creating or editing the Strapi Collection Item.
- Web Editions for other books, though the command and the Book Reader config must not prevent them.
- Any change to the Final Book's text.
- Adding a test runner to the website.

## Further Notes

- **Pages.** The Final Book's pdf ranges are the trusted source. Every story's start in `toc.json` is printed = pdf − 1 except 31 (`null`, the OCR read "883"), 32 (Mục lục OCR gives 268; it should be 266) and 34 (311; it should be 315). Those wrong numbers come from OCR of the printed Mục lục (pdf 554–555). The pdf ranges come from the human-checked split ranges in `structure.yaml`.
- **Dialect conversion was decided while writing this spec, not during the grilling.** The renderer doesn't handle `\-` or hard breaks, so the export converts them (907 escaped dashes, and about 15 hard-break blocks such as ca dao and Cham chants). Treating every hard-break block as verse, except the Lời giới thiệu's signature, is the spec's choice. The developer should glance at a few of these blocks in the browser.
- **Running jobs.** The developer runs the export and copies the folder, following this repo's practice that the developer runs pipeline jobs. The implementer gives the command rather than running it on real data.
- **Commits.** Commits are made by the developers; the implementer leaves changes uncommitted.
- **Two repos.** This spec covers work in this repo (export) and in the website repo (Book Reader). They can be built independently. The website work can use a Web Edition generated once by the developer.
