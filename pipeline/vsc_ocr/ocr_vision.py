"""OCR with Apple's Vision framework (macOS only, fully on-device).

Uses VNRecognizeTextRequest through pyobjc:
  pip install pyobjc-framework-Vision pyobjc-framework-Quartz

Each page produces data/ocr/<book>/vision/pNNNN.json:
  {"engine": "apple-vision", "lines": [{"text", "conf", "bbox": [x0, y0, x1, y1],
   "alternatives": [...]}], ...}
bbox is normalised to 0..1 with the origin at the TOP-left (Vision itself uses
bottom-left; we flip it so every engine shares one convention).

Proper names that appear inside the Vietnamese text (Po Ina Nagar, Kei Kamao,
Hbia Tà Lúi...) are passed as `customWords`, so the language model stops
"correcting" them. Put them in pipeline/config/custom_words.txt (all books) or
data/books/<book>/custom_words.txt (one book). Custom words only take effect
while language correction is on.
"""

from __future__ import annotations

import platform
from concurrent.futures import ProcessPoolExecutor

from .common import Book, nfc, write_json

N_ALTERNATIVES = 3


def _vision():
    try:
        import Vision  # noqa: F401  (pyobjc-framework-Vision)
        from Foundation import NSURL  # noqa: F401
    except ImportError as e:  # pragma: no cover - depends on platform
        raise SystemExit(
            "Apple Vision is unavailable. It needs macOS and:\n"
            "  pip install pyobjc-framework-Vision pyobjc-framework-Quartz\n"
            f"({e})"
        )
    import Vision
    from Foundation import NSURL
    return Vision, NSURL


def vietnamese_language_code() -> str:
    """Vision's code for Vietnamese differs between macOS versions; ask it."""
    Vision, _ = _vision()
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    langs, err = req.supportedRecognitionLanguagesAndReturnError_(None)
    langs = list(langs or [])
    for code in langs:
        if str(code).lower().startswith("vi"):
            return str(code)
    raise SystemExit(
        "This macOS version's Vision framework does not list Vietnamese.\n"
        f"Supported: {', '.join(map(str, langs))}"
    )


def recognize(image_path: str, lang: str, custom_words: list[str], language_correction: bool) -> dict:
    Vision, NSURL = _vision()
    url = NSURL.fileURLWithPath_(image_path)
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, None)
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setRecognitionLanguages_([lang])
    req.setUsesLanguageCorrection_(language_correction)
    if language_correction and custom_words:
        req.setCustomWords_(custom_words)
    req.setMinimumTextHeight_(0.0)
    ok, err = handler.performRequests_error_([req], None)
    if not ok:
        raise RuntimeError(f"Vision failed on {image_path}: {err}")

    lines = []
    for obs in req.results() or []:
        cands = obs.topCandidates_(N_ALTERNATIVES)
        if not cands:
            continue
        best = cands[0]
        bb = obs.boundingBox()
        x0, y_bottom = bb.origin.x, bb.origin.y
        w, h = bb.size.width, bb.size.height
        lines.append(dict(
            text=nfc(str(best.string())),
            conf=round(float(best.confidence()), 3),
            bbox=[round(x0, 5), round(1 - (y_bottom + h), 5), round(x0 + w, 5), round(1 - y_bottom, 5)],
            alternatives=[nfc(str(c.string())) for c in list(cands)[1:]],
        ))
    lines.sort(key=lambda l: (l["bbox"][1], l["bbox"][0]))
    return dict(
        engine="apple-vision",
        engine_version=f"macOS {platform.mac_ver()[0]}",
        language=lang,
        language_correction=language_correction,
        custom_words=len(custom_words) if language_correction else 0,
        lines=lines,
    )


def _work(args):
    image, out, lang, words, lc = args
    from pathlib import Path
    from PIL import Image
    result = recognize(image, lang, words, lc)
    with Image.open(image) as im:
        result["image_size"] = list(im.size)
    write_json(Path(out), result)
    return out


def ocr_pages(book: Book, pages: list[int], workers: int = 1, force: bool = False,
              language_correction: bool = True) -> None:
    lang = vietnamese_language_code()
    words = book.custom_words()
    print(f"  Vision language '{lang}', {len(words)} custom words, language correction {language_correction}")
    jobs, missing = [], 0
    for n in pages:
        out = book.ocr_path("vision", n)
        img = book.render_path(n)
        if out.exists() and not force:
            continue
        if not img.exists():
            missing += 1
            continue
        jobs.append((str(img), str(out), lang, words, language_correction))
    if missing:
        print(f"  ! {missing} page(s) not rendered yet; run `render` first")
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for i, _ in enumerate(pool.map(_work, jobs), 1):
                if i % 25 == 0:
                    print(f"  vision {i}/{len(jobs)}")
    else:
        for i, job in enumerate(jobs, 1):
            _work(job)
            if i % 25 == 0:
                print(f"  vision {i}/{len(jobs)}")
    print(f"  vision OCR'd {len(jobs)} page(s)")
