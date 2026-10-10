# Truyện cổ dân gian Việt Nam

Domain vocabulary for turning scanned folk-tale books into reviewed, structured text.

## Language

**Correction**:
An edit a human reviewer makes to a book's text against the scan (edit, delete or merge of a paragraph), logged in `corrections.jsonl`. Only humans make Corrections.
_Avoid_: fix, AI correction

**AI Proofreading Pass**:
One run of a model over a book's raw pipeline output, with the scanned pages in view, to make the text match the scan. It produces AI Proposals and never edits the reviewed book.
_Avoid_: AI correction, AI review

**AI Proposal**:
One change suggested by an AI Proofreading Pass to one or more paragraphs, with the model's reason. It makes the text faithful to the scan: OCR misreads, diacritics, drop caps, stray characters, ⚠ flags, paragraphs split by a page, and notes. It never rewords, never fixes the book's own printed typos, and never "corrects" a word towards a more familiar one: Cham names and terms are kept exactly as the scan prints them. It is a proposal until a human accepts it, and it is kept apart from Corrections.
_Avoid_: AI correction, suggestion

**Note**:
An explanatory footnote printed in the book. It has a **Note Call** (the `[^id]` mark in the story text) and a **Note Definition** (the `[^id]: …` line). The book may print a definition on the call's page or only at the end of the story.
_Avoid_: footnote (alone), annotation
