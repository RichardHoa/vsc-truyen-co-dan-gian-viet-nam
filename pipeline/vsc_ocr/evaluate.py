"""Measure OCR accuracy against hand-typed ground truth.

Put the exact text of a page (as printed, line breaks don't matter) in
data/groundtruth/<book>/pNNNN.txt, then run `python -m vsc_ocr evaluate <book>`.
Reports, per page and engine:
  CER  character error rate (edit distance / length)
  WER  word error rate
  DER  "diacritic" error rate: CER after removing every tone/vowel mark, so
       CER - DER ≈ errors that are only about diacritics
for the raw Vision and Tesseract output and for the cleaned text (which also
shows whether header/footer removal threw away real text).
"""

from __future__ import annotations

from .common import GROUNDTRUTH_DIR, Book, nfc, page_num, read_json, strip_diacritics
from .layout import group_rows, norm_space


def _levenshtein(a, b) -> int:
    try:
        from rapidfuzz.distance import Levenshtein
        return Levenshtein.distance(a, b)
    except ImportError:
        pass
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _norm(text: str) -> str:
    return norm_space(nfc(text))


def scores(truth: str, hyp: str) -> dict:
    t, h = _norm(truth), _norm(hyp)
    cer = _levenshtein(t, h) / max(len(t), 1)
    wer = _levenshtein(t.split(), h.split()) / max(len(t.split()), 1)
    td, hd = strip_diacritics(t), strip_diacritics(h)
    der = _levenshtein(td, hd) / max(len(td), 1)
    return dict(cer=round(cer, 4), wer=round(wer, 4), der=round(der, 4))


def _raw_text(path) -> str | None:
    if not path.exists():
        return None
    return "\n".join(r["text"] for r in group_rows(read_json(path)["lines"]))


def _clean_text(path) -> str | None:
    if not path.exists():
        return None
    return "\n".join(s["text"] for s in read_json(path)["segments"])


def evaluate_book(book: Book, pages: list[int] | None = None) -> None:
    gt_dir = GROUNDTRUTH_DIR / book.id
    files = sorted(gt_dir.glob("p*.txt")) if gt_dir.exists() else []
    if pages:
        files = [f for f in files if page_num(f.stem) in pages]
    if not files:
        print(f"  no ground truth in {gt_dir} (add pNNNN.txt files)")
        return
    totals: dict[str, list] = {}
    print(f"  {'page':6} {'source':10} {'CER':>7} {'WER':>7} {'DER':>7}")
    for f in files:
        n = page_num(f.stem)
        truth = f.read_text(encoding="utf-8")
        for name, text in (
            ("vision", _raw_text(book.ocr_path("vision", n))),
            ("tesseract", _raw_text(book.ocr_path("tesseract", n))),
            ("cleaned", _clean_text(book.page_path(n))),
        ):
            if text is None:
                continue
            s = scores(truth, text)
            totals.setdefault(name, []).append(s)
            print(f"  {f.stem:6} {name:10} {s['cer']:7.2%} {s['wer']:7.2%} {s['der']:7.2%}")
    print("  mean:")
    for name, ss in totals.items():
        avg = {k: sum(s[k] for s in ss) / len(ss) for k in ("cer", "wer", "der")}
        print(f"  {'':6} {name:10} {avg['cer']:7.2%} {avg['wer']:7.2%} {avg['der']:7.2%}   ({len(ss)} pages)")
