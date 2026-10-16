# 02: Read "Truyện cổ dân gian Chăm" on the website through a generalized Book Reader

**What to build:** On the Digitizing Việt Nam website (the `digitizing-vietnam-website` repo), a reader opens `/our-collections/vietnamese-folk-literature/truyen-co-dan-gian-cham` and reads the Chăm book as digitized text, with the same layout and story display as the Kho Tàng reader. The Kho Tàng reader becomes a general **Book Reader** driven by a per-book config, and Kho Tàng keeps behaving exactly as before. The Chăm book's data is the Web Edition from ticket 01, copied by the developer into the website's public data as `truyen-co-dan-gian-cham/`.

See the spec: `.scratch/web-edition-truyen-co-dan-gian-cham/spec.md` (sections "Book Reader" and "Testing Decisions → Website").

**Blocked by:** 01 (Export the Web Edition). The Chăm book needs a Web Edition the developer has generated and copied into the website.

**Status:** ready-for-agent

### Generalization (Kho Tàng unchanged)

- [ ] The Kho Tàng searchable-text module (data loader, reader, Markdown/footnote rendering, footnote popover) is generalized, not copied. It is driven by a book config: Collection Item (collection id + document id), public data folder, TOC shape (Parts → Sections → Stories/Essays + Bibliography, or flat Preface + Stories), search source (Story Name Index or story titles), and labels.
- [ ] The Collection Item page dispatches to the Book Reader when the collection/document pair matches either book's config, replacing the Kho Tàng-only branch.
- [ ] Kho Tàng is unchanged in the browser: tabs per Part and for the Bibliography, Story Name Index search with highlighting, `?ten=` and `?chu-thich=` targeting, the Preface first, previous/next, and existing `?muc=` links.
- [ ] The renderer gains no new Markdown features. The Web Edition already uses the supported dialect.

### Chăm book

- [ ] The book opens on the Lời giới thiệu (its Preface, shown under that printed title). An unknown or missing `?muc=` also opens it.
- [ ] `?muc=` slugs are `loi-gioi-thieu` and `truyen-1` … `truyen-58`. Previous/next run in book order from the Lời giới thiệu to story 58.
- [ ] The contents panel has no tab bar. It shows the search box and then the list (Lời giới thiệu, then 1–58, with titles from the TOC JSON).
- [ ] Search matches story titles and the Preface title, ignoring case and diacritics (so "su tich ga" finds "Sự tích gà gáy sáng"). Results replace the list while there's a query. There is no name highlighting, and `?ten=`/`?chu-thich=` are ignored for this book.
- [ ] Note popovers work and show the "(Trang N)" prefix. A Note Call in a story's title heading works.
- [ ] Verse blocks render as verse, and the Lời giới thiệu's signature renders right-aligned.
- [ ] The loader's existing startup checks (Note counts against content, duplicate slugs) pass for both books.

### Glossary and housekeeping

- [ ] The website's `CONTEXT.md` gains a "Truyện cổ dân gian Chăm" section: the Book is the Preface (Lời giới thiệu) plus 58 Stories, with no Parts, Sections, Essays, Khảo dị or Story Name Index, and search covers story titles. It also gains the **Book Reader** term. Kho Tàng's terms are kept.
- [ ] No test runner is added. The implementer lists the manual browser checks for both books (spec "Testing Decisions → Website") for the developer to run.
- [ ] Changes are left uncommitted.
