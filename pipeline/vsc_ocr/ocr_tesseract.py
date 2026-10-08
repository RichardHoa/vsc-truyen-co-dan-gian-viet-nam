"""OCR with Tesseract (local, open source): the second opinion.

Needs the `tesseract` binary with Vietnamese data:
  macOS:  brew install tesseract tesseract-lang
  Ubuntu: apt install tesseract-ocr tesseract-ocr-vie

Output has the same shape as the Vision output (top-left normalised bboxes),
plus per-word confidences.
"""

from __future__ import annotations

import csv
import io
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor

from .common import Book, nfc, write_json


def _check() -> str:
    exe = shutil.which("tesseract")
    if not exe:
        raise SystemExit("tesseract not found. macOS: brew install tesseract tesseract-lang")
    langs = subprocess.run([exe, "--list-langs"], capture_output=True, text=True).stdout.split()
    if "vie" not in langs:
        raise SystemExit("Tesseract Vietnamese data missing. macOS: brew install tesseract-lang")
    return exe


def recognize(exe: str, image_path: str, psm: int = 3) -> dict:
    proc = subprocess.run(
        [exe, image_path, "stdout", "-l", "vie", "--psm", str(psm), "--dpi", "300", "tsv"],
        capture_output=True, text=True,
        # one thread per process; parallelism comes from --workers instead
        env={**os.environ, "OMP_THREAD_LIMIT": "1"},
    )
    if proc.returncode != 0:
        raise RuntimeError(f"tesseract failed on {image_path}: {proc.stderr[-500:]}")
    rows = list(csv.DictReader(io.StringIO(proc.stdout), delimiter="\t", quoting=csv.QUOTE_NONE))
    if not rows:
        return dict(engine="tesseract", lines=[], image_size=[0, 0])
    page_w = int(rows[0]["width"]) or 1
    page_h = int(rows[0]["height"]) or 1

    groups: dict[tuple, list] = {}
    for r in rows:
        if r["level"] != "5" or not (r.get("text") or "").strip():
            continue
        key = (int(r["block_num"]), int(r["par_num"]), int(r["line_num"]))
        groups.setdefault(key, []).append(r)

    lines = []
    for key in sorted(groups):
        words = groups[key]
        x0 = min(int(w["left"]) for w in words)
        y0 = min(int(w["top"]) for w in words)
        x1 = max(int(w["left"]) + int(w["width"]) for w in words)
        y1 = max(int(w["top"]) + int(w["height"]) for w in words)
        confs = [float(w["conf"]) / 100 for w in words if float(w["conf"]) >= 0]
        lines.append(dict(
            text=nfc(" ".join(w["text"] for w in words)),
            conf=round(sum(confs) / len(confs), 3) if confs else 0.0,
            bbox=[round(x0 / page_w, 5), round(y0 / page_h, 5), round(x1 / page_w, 5), round(y1 / page_h, 5)],
            words=[[nfc(w["text"]), round(float(w["conf"]) / 100, 2)] for w in words],
        ))
    lines.sort(key=lambda l: (l["bbox"][1], l["bbox"][0]))
    version = subprocess.run([exe, "--version"], capture_output=True, text=True).stdout.split("\n")[0]
    return dict(engine="tesseract", engine_version=version, language="vie", psm=psm,
                image_size=[page_w, page_h], lines=lines)


def ocr_pages(book: Book, pages: list[int], workers: int = 1, force: bool = False) -> None:
    exe = _check()
    jobs, missing = [], 0
    for n in pages:
        out = book.ocr_path("tesseract", n)
        img = book.render_path(n)
        if out.exists() and not force:
            continue
        if not img.exists():
            missing += 1
            continue
        jobs.append((img, out))
    if missing:
        print(f"  ! {missing} page(s) not rendered yet; run `render` first")

    def work(job):
        img, out = job
        write_json(out, recognize(exe, str(img)))

    # tesseract is a subprocess, so threads parallelise fine
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for i, _ in enumerate(pool.map(work, jobs), 1):
            if i % 25 == 0:
                print(f"  tesseract {i}/{len(jobs)}")
    print(f"  tesseract OCR'd {len(jobs)} page(s)")
