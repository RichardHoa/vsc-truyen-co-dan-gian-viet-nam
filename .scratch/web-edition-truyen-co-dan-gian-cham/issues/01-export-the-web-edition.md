# 01: Export the Web Edition of "Truyện cổ dân gian Chăm" from its Final Book

**What to build:** A developer runs one pipeline command on `truyen-co-dan-gian-cham` and gets the book's **Web Edition**: a folder in the book's own data directory holding the Lời giới thiệu, one Markdown file per story and a table of contents JSON, written in the format the website's Kho Tàng reader reads. The developer copies the folder into the website by hand. The command reads only the Final Book and the book's `structure.yaml`, never `toc.json`. If the Final Book has any problem that would publish a broken book, the command writes nothing and lists every problem.

See the spec: `.scratch/web-edition-truyen-co-dan-gian-cham/spec.md` (sections "Web Edition export" and "Testing Decisions → Pipeline").

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

### Command and config

- [ ] A new command `python -m vsc_ocr export-web <book>` exists alongside `finalize` and is listed in the CLI help.
- [ ] `structure.yaml` for `truyen-co-dan-gian-cham` has `printed_page_offset: 1` (printed page = pdf page − offset). The command refuses to run, writing nothing, when a book lacks this field.
- [ ] The output goes to the book's `web/<book-id>/` folder, which is emptied before each write. `web/` folders are gitignored.
- [ ] The work is done by one pure function (Final Book text + offset → mapping of relative path to file content, or one error listing every problem). The command only reads its inputs, calls the function and writes the result.

### Output

- [ ] The folder holds `loi_gioi_thieu.md`, `story_001.md` … `story_058.md` and `table_of_contents.json`. There are no Part or Section folders.
- [ ] `table_of_contents.json` has `book_title: "Truyện cổ dân gian Chăm"`, a `preface` entry (title "Lời giới thiệu") and a `stories` list in book order. Each entry has its number (stories), title, `start_page`/`end_page` (from the heading's `<!-- pdf a-b -->` minus the offset), `markdown_file` and `footnote_count`.
- [ ] TOC titles are the Final Book's Story Titles exactly (subtitles included), with any Note Call removed.
- [ ] Each story file starts with `## N. Title` (the Preface with `## Lời giới thiệu`). A Note Call in a title stays in that heading. There is no `#` Section line.
- [ ] Every HTML comment is removed.
- [ ] Within each Entry, Note Calls are renumbered `[^1]…[^n]` in reading order, the title heading included. The definitions follow, in the same order, after `---` and `### Chú thích`, each as `[^k]: (Trang N) <text>` with N = its `note pdf` page − offset.
- [ ] Lines starting with `\- ` become `- `.
- [ ] Blocks written with Markdown hard breaks become `> ` verse lines with the trailing spaces removed, except the Lời giới thiệu's closing place/date and signature block, whose lines become `-> ` lines.
- [ ] Output is deterministic: running twice on the same Final Book gives byte-identical files (UTF-8, `\n`, one trailing newline, stable JSON key order).

### Refusals (nothing written, every problem listed, each naming the story or Note at fault)

- [ ] The headings aren't exactly the Lời giới thiệu and then stories 1 to 58 in order, each with a pdf range comment.
- [ ] A Note Call has no definition, or a definition is never called, within an Entry.
- [ ] A Note Definition has no `note pdf N` tag.
- [ ] Markdown appears that the website renderer doesn't support. The supported set is `#`–`###` headings, plain paragraphs, `> ` verse, `-> ` right-aligned lines and footnote links.

### Tests

- [ ] pytest tests in the style of the existing Final Book replay tests (inline fixture books) cover each output rule and each refusal above, through the pure function only.
- [ ] The implementer does not run the command on the real book. They give the developer the command, and the developer's run must produce 59 Markdown files, 58 stories and 42 Notes in total.
- [ ] Changes are left uncommitted.
