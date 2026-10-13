# Next step: LLM changes to the AI Proofreading Pass

This is for a new session. Its scope is **the model side** of the AI Proofreading Pass: the prompt, what the model is
given, and code that checks the model's reading of names. The code-only fixes from the first review are done (see
"Already done").

## Context

- The book is `truyen-co-dan-gian-cham` (Truyện cổ dân gian Chăm). The text is Vietnamese, full of Cham names.
- The flow is `python -m vsc_ocr prepare-ai <book>` (this repo, `pipeline/vsc_ocr/prepare_ai.py`), which writes
  `data-for-ai/<book>/`. That folder goes to the GPU cluster, where `sbatch scripts/submit_correction.sh` runs
  the pass. The pass lives in the **resume-scanning** repo:
  - `src/prompts/proofread_prompts.py`: prompts and schemas (Phase 1 transcribes one page; Phase 2 places one note)
  - `src/pipelines/proofreader.py`: the parts that need no model (`read_page`, `assemble`, note pairing)
  - `src/cli/proofread.py`: the CLI
  - `tests/test_proofreader.py`: unit tests (`python3 -m pytest tests/test_proofreader.py`)
- The outputs `book.ai.md`, `ai_corrections.jsonl`, `boxes.jsonl` and `coverage.jsonl` get copied back to
  `data/books/<book>/ai/`. The developer reviews them with `python -m vsc_ocr review <book> --ai`, and their edits
  land in `data/books/<book>/ai/corrections.jsonl`.
- Rules: the developer runs every model job and dry run (give them the command), and makes every commit.

## What the first review showed (2026-10-13)

The developer made 33 corrections to the first run's `book.ai.md`. 14 of them came from code, and those are now
fixed. The model's own weaknesses are narrow: **small diacritics, above all in names**, plus decorative drop caps
and dialogue it took for verse.

### Names: the model makes them worse than the OCR

Spellings counted over the whole book:

| Name | OCR (`book.raw.md`) | AI (`ai/book.ai.md`) |
|---|---|---|
| Tềwa Mừnô | 98 × `Tềwa Mừnô`, 9 stray variants | 77 × `Tềwa Mừnô`, **31 × `Têwa Mùnô`**, 3 other variants |
| Jamưtui | 61 × `Jamưtui`, 11 × `Jamutui` | **25 × `Jamưtui`, 37 × `Jamutui`** |

The model drops or swaps small marks (ư→u, ừ→ù, ề→ê) that the Vision OCR reads correctly. It sees 200-dpi grayscale
JPEGs and drifts towards more familiar spellings. The prompt already says "keep Cham names as printed", so
prompting harder alone won't fix it.

The headings show the same thing. The model's reading (the `heading:` comment) next to the raw OCR heading:

| Raw OCR heading | Model's reading | Correct (developer / likely) |
|---|---|---|
| Bảy chàng trai khoe | BẢY CHÀNG TRAI KHOỂ | khoẻ (both wrong) |
| Hoàng tử TêWa MừNô | HOÀNG TỬ TÈWA MÙNÔ | TềWa MừNô (both wrong) |
| Kathăr ăn phân chó | KATHĀR ĂN PHÂN CHÓ | ă: the model wrote a macron ā |
| Param Mudit, Parăm MUlak | PARĀM MŨDIT, PARĀM MŨLAK | check the scan; ā is not Vietnamese |
| chăn dệ | CHĂN DÊ | dê (model right) |
| Chàng Răn / Kén rế / Chăng Tinh | RẮN / RỂ / CHẰNG | model right |
| Jari bäh | JARI BÃH | check the scan |

So the model gets diacritics right only about half the time. Because of this, `assemble` still keeps the raw
heading's letters.

### Other model misreadings the developer fixed

- `bông - bông` → `bồng - bồng` (p28): the same word was right a few lines later.
- `Rua` → `Xưa` (p42): a drop cap.
- p317: a wrapped line of dialogue came out as verse (one line break per printed line). The developer joined it back
  into one paragraph.
- On the 4 pages where the OCR lost a drop-cap line (p28, 274, 417, 427), the model's rebuilt text was right every
  time. The ⚠ flag there is enough.

## The suggested changes, best first

1. **A name list per story, enforced in code.** Take each story's capitalised words from its OCR lines (pages.jsonl;
   lines without the `check` flag are the ones both OCR engines agreed on). Group the spellings that are equal once
   folded (`fold_words`: no diacritics, lower case), and take the most common as the printed spelling (`Tềwa Mừnô`,
   98 times). After transcription, replace a word that folds to a known name but differs in its marks with that
   spelling, and log the change as an AI Proposal. This is deterministic, and it would have fixed all 31
   `Têwa Mùnô`. Watch for a name whose OCR spelling is itself split (`Jamưtui` 61 / `Jamutui` 11): only enforce a
   clear majority, and flag the rest. A Spelling Rule (see "Then" below) beats the OCR majority: read
   `spellings.yaml` from the book's folder in data-for-ai if it is there, and log those changes with their rule.
2. **Give the model the same list in the Phase 1 prompt:** "Names in this story, as printed: Tềwa Mừnô, Ưngcăl,
   Xăng Gì…". This helps on the pages where the OCR garbled the name itself.
3. **Flag the variants left over.** A name that still has two spellings within a story gets ⚠, so review shows it.
4. **Diacritics on common words.** When the model and the OCR differ only in a word's marks, and both OCR engines
   agreed (`check` false), keep the OCR's word. `bông` / `bồng` is this case. Measure first with the A/B script
   (`scripts/compare_ocr_hint.py`) so it doesn't undo real fixes such as `thầy` → `thấy`.
5. **Prompt: scene breaks.** Replace "A scene break (stars or an ornament between paragraphs) is `* * *`" with
   "Leave out scene breaks". The code already drops them (see below); this only saves output tokens.
6. **Prompt: dialogue is not verse.** Say that a dash line of dialogue is one paragraph however it wraps. Only short
   centred lines are verse.
7. **Optional: 300 dpi instead of 200** (`prepare-ai --dpi`), so the marks are bigger. It costs more image tokens
   (check with a dry run) and is less sure to help than 1–4.

## Already done (code only, no model change)

In resume-scanning `src/pipelines/proofreader.py`, with tests:

- Scene breaks (`* * *`) are dropped from the transcription. A rebuilt story has none, and the diff proposes
  deleting the raw ones.
- An OCR line the model left out that is mostly junk (`Š/о1/2оє1`, `N nnn nh Tàn n`, `tt Ũ`, `se b3`) is noise. It
  no longer comes back as `⚠ ai-missed?`, and it is listed in `coverage.jsonl` under `left_out`. Over the book's
  11,914 OCR lines, only 2 genuine ones would count as noise.
- A garbled OCR line right before or after a ⚠ block (the drop-cap line the model read anew, p274 and p417) is
  also left out, under `left_out`.
- Because the noise is gone, a junk line at the foot of a page no longer keeps a paragraph from joining the next
  page (the p11→p12 case).
- Headings: the raw heading loses the note marks the OCR read as punctuation (`(!)`, `(")`), and gains a subtitle
  in brackets that the page prints but the raw heading lacks (`(Likay Ruah Kamay, Kamy Ruah Li kay)`). Its letters
  stay the raw ones (see the table above).
- The book's title section (`# `, the title page, pdf 4) stays as it is in `book.raw.md`. In this repo,
  `prepare_ai.py` no longer sends its pages to the cluster.

## When done

Run the unit tests and a fake or mock-server run on a few pages, not a real model. Then give the developer the
commands: `prepare-ai`, the copy to the cluster, `sbatch scripts/submit_correction.sh`, and `review <book> --ai`.

## Then: `review <book> --ai --diacritic`

After 1–6 above, a review page for the spellings, in this repo. It lists every place where the AI and the OCR read a
word with the same letters but different marks. For each one it shows the AI's, Vision's and Tesseract's spelling
next to the scan, and the developer decides which is printed. Each decision becomes a **Spelling Rule** (see
`CONTEXT.md`), and from then on code applies it, to the current `book.ai.md` and to every later pass. The decisions
below were settled with the developer on 2026-10-13; don't re-decide them.

### What is listed

A **pair** is two spellings that are equal once folded (`fold_words`; `đ` counts as `d`, so `Đăm`/`Dăm` is a pair)
but differ in their marks. The page lists:

- every word where `book.ai.md` and the OCR (`book.raw.md`, by block) form a pair, in headings (the model's
  `heading:` comment against the raw heading) and in body text;
- every change the name enforcement (suggestion 1) made by itself;
- names still spelled two ways within one story (the ⚠ from suggestion 3).

Changes that alter the letters themselves (`Rua` → `Xưa`) stay in the plain `review --ai`.

Matching ignores case: `TÊWA`, `Têwa` and `têwa` are one pair.

### One decision per pair

A pair is decided once, and all its occurrences are listed under it. Clicking an occurrence shows the scan page
with that line boxed (from the line boxes in `data/ocr/<book>/vision/pNNNN.json` and `tesseract/pNNNN.json`).
Each occurrence shows three readings of the word: the AI's, Vision's and Tesseract's. Readings that agree are shown
as one choice.

Answers:

- **AI right**, **Vision right**, **Tesseract right**: makes a rule with that spelling.
- **Neither**: the developer types the spelling, and it makes a rule.
- **Depends**: no rule. Each occurrence is decided on its own, as a plain edit. Use it for words like
  `thầy`/`thấy`.

The page keeps a tally of who was right (AI / Vision / Tesseract). It measures what suggestion 4 needs measured.

### Words and phrases

A rule is for one word by default (`Tềwa`, `Mừnô`, `Jamưtui`), so it also catches the word on its own. A word that
also appears in lower case somewhere in the book is a common word (`bông` means "flower"). For a common word, the
page warns and offers a **phrase** rule instead (`bồng - bồng`, matched with its neighbours), or Depends. It never
offers a bare word rule for a common word.

### Exceptions

A rule covers the whole book. Overriding it at one occurrence makes a **story exception**: the rule is skipped in
that story. There are no exceptions narrower than a story. If the right spelling changes within a story, the answer
is Depends.

### Applying a rule

The replacement takes the case of the word it replaces (`TÊWA` → `TỀWA`, `têwa` → `tềwa`). So one rule covers
headings and body text, and a heading changes too. `assemble` alone keeps the raw heading letters.

### `data/books/<book>/spellings.yaml`

The rules live at book level, not in `ai/`, so a new pass copied into `ai/` doesn't lose them (and `assemble` can
use them later; not now). One entry per folded form:

```yaml
words:
  - spelling: Tềwa
    except: []                 # story titles where the rule is skipped
  - spelling: Jamưtui
    except: []
phrases:
  - spelling: bồng - bồng
    except: []
depends:                       # pairs decided per occurrence: listed so the page groups them, never applied
  - [thầy, thấy]
```

### Log

Answering applies the rule to `ai/book.ai.md` right away. Each block it changes is logged in `ai/corrections.jsonl`
as a Correction with `action: "spelling"` and a `rule` field (the rule's spelling), so the rule's changes are easy
to tell apart from hand edits. `book.ai.raw.md` is kept once as usual. A Depends occurrence is an ordinary `edit`.

### The page

It is a new page served by `review --ai --diacritic` (`--diacritic` requires `--ai`). It reuses `page.html`'s scan
viewer and box drawing: the list is on the left, the scan on the right. It has two tabs:

- **Open**: pairs that have no rule yet. Headings come first, then names by count, then common words.
  Depends pairs come back here on every run.
- **Ruled**: the rules, each with how often it was applied in the current `book.ai.md`. A rule can be changed or
  deleted here.

### To the cluster

`prepare-ai` copies `spellings.yaml` into `data-for-ai/<book>/`. The proofreader (suggestion 1) applies it after
Phase 1, ahead of the OCR majority, and puts its names in the Phase 1 prompt (suggestion 2). So a pair already ruled
doesn't come back as Open after the next pass.

### Order

Do 1–6 first. Of those, 1 (enforcement that reads `spellings.yaml`) and the `prepare-ai` copy block this page,
because they settle the file format. Then build the page. Test it with unit tests on pair finding, case-keeping
replacement, phrase rules and story exceptions, and a run of the server on the real book. The developer does the
reviewing.
