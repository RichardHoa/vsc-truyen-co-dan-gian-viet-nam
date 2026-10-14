# Truyện cổ dân gian Việt Nam

Domain vocabulary for turning scanned folk-tale books into reviewed, structured text.

## Language

**Final Book**:
A book's official, reviewed text: an AI Proofreading Pass's output after a human has reviewed and corrected it against the scans. It is the one text published, and it is kept whole, so it never has to be rebuilt.
_Avoid_: official book, AI book, book.md

**OCR Draft**:
A book's text as the OCR pipeline assembles it from the scans, before any AI Proofreading Pass. It is what the pass starts from; it can be rebuilt from the scans at any time.
_Avoid_: book (alone), raw book

**AI Draft**:
The text one AI Proofreading Pass wrote, together with the human review of it (Corrections, Spelling Rules, Story Titles). Finalizing it makes it the Final Book; a new pass replaces it.
_Avoid_: AI book, AI output (for the reviewed text)

**Correction**:
An edit a human reviewer makes to a book's text against the scan (edit, delete or merge of a paragraph), logged in `corrections.jsonl`. Only humans make Corrections; applying a Spelling Rule to a text is also a Correction, logged as such.
_Avoid_: fix, AI correction

**AI Proofreading Pass**:
One run of a model over a book's raw pipeline output, with the scanned pages in view, to make the text match the scan. It produces AI Proposals and never edits the reviewed book.
_Avoid_: AI correction, AI review

**AI Proposal**:
One change suggested by an AI Proofreading Pass to one or more paragraphs, with the model's reason. It makes the text faithful to the scan: OCR misreads, diacritics, drop caps, stray characters, ⚠ flags, paragraphs split by a page, and notes. It never rewords, never fixes the book's own printed typos, and never "corrects" a word towards a more familiar one: Cham names and terms are kept exactly as the scan prints them. It is a proposal until a human accepts it, and it is kept apart from Corrections.
_Avoid_: AI correction, suggestion

**Spelling Rule**:
A human decision that one spelling of a word is the printed one, for the whole book (optionally with exceptions for single stories). It covers words whose spellings differ only in their marks (`Tềwa`, not `Têwa`) and is made by reviewing the AI's and the OCR's readings against the scan. Once made, it is applied without asking, both to the current AI output and to every later AI Proofreading Pass. A word whose correct marks depend on context gets no Spelling Rule.
_Avoid_: name rule, auto-correction, dictionary

**Story Title**:
A story's heading as a human set it: its number, its title and any subtitle the book prints under it, with the marks the scan prints. Once set, it is the story's one title: an AI Proofreading Pass writes it exactly as set, and no Spelling Rule or model reading changes it.
_Avoid_: heading (for the set title), raw heading, fixed title

**Note**:
An explanatory footnote printed in the book. It has a **Note Call** (the `[^id]` mark in the story text) and a **Note Definition** (the `[^id]: …` line). The book may print a definition on the call's page or only at the end of the story.
_Avoid_: footnote (alone), annotation
