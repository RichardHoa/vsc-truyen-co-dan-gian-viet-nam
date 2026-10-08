"""Build data/books/<id>/structure.yaml for every book, without any OCR.

The 15 PDFs in master_pdf/ are the complete scanned books. Everything under
truyen_nguoi_*/ is a hand-made split of those books (one PDF per story and per
language version) that re-uses the exact same scan images. We match every
split page back to its master page by hashing the embedded scan image (plus the
crop box, because one scan image holds two book pages). That gives us, for free,
the list of works in each book, their language versions and their page ranges.

Splits whose images appear in no master (e.g. "Truyện cổ dân gian Chăm Bình
Thuận") become a book of their own, built from the split files.
"""

from __future__ import annotations

import difflib
import hashlib
import os
import re
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

from .common import (
    BOOKS_DIR, CACHE_DIR, MASTER_DIR, REPO_ROOT, nfc, read_json, slugify, to_ranges,
    write_json, write_yaml,
)

# Folder name (slug prefix) -> what kind of version it holds.
# content: "text" = Vietnamese, gets OCR'd; "pdf" = kept as scan only.
VERSION_KINDS = [
    ("ban-dich-tieng-viet", dict(kind="translation", language="vi", content="text")),
    ("dich-nghia-tieng-viet", dict(kind="literal-translation", language="vi", content="text")),
    ("dich-tho-tieng-viet", dict(kind="verse-translation", language="vi", content="text")),
    ("tom-tat-noi-dung", dict(kind="summary", language="vi", content="text")),
    ("phien-am", dict(kind="transcription", language=None, content="pdf", script="Latn")),
    ("akhar-thrah", dict(kind="original-script", language="cham", content="pdf", script="Cham")),
    ("ban-viet-tay", dict(kind="manuscript", language="cham", content="pdf", script="Cham")),
    ("index", dict(kind="glossary", language=None, content="pdf")),
    ("doi-chieu-di-ban", dict(kind="variant-comparison", language=None, content="pdf")),
]
# A story file sitting directly in a collection folder (no version sub-folder)
# is a Vietnamese text. The OCR step still checks each page's language.
DEFAULT_VERSION = dict(kind="text", language="vi", content="text")

ETHNIC_FOLDERS = {
    "truyen_nguoi_cham": "cham",
    "truyen_nguoi_raglai": "raglai",
    "truyen_nguoi_bana": "bana",
    "truyen_nguoi_mo_nong": "mnong",
    "truyen_nguoi_hre": "hre",
}

VI_KINDS_PREFERRED_FOR_TITLE = ("translation", "text", "literal-translation", "verse-translation")


def version_info(folder_label: str | None, ethnic: str) -> dict:
    if folder_label is None:
        return dict(DEFAULT_VERSION)
    slug = slugify(folder_label)
    for prefix, info in VERSION_KINDS:
        if slug.startswith(prefix):
            info = dict(info)
            if info["language"] is None:
                info["language"] = ethnic
            return info
    return dict(kind=slug, language=None, content="pdf")


# ---------------------------------------------------------------- page keys

def _page_keys(path: Path) -> list[tuple[tuple[str, ...], frozenset]]:
    """For each page: (hashes of its scan images, rounded crop-box coordinates)."""
    reader = PdfReader(str(path))
    out = []
    for page in reader.pages:
        hashes = []
        res = page.get("/Resources") or {}
        xobjects = res.get("/XObject") or {}
        for name in xobjects:
            obj = xobjects[name].get_object()
            if obj.get("/Subtype") == "/Image":
                hashes.append(hashlib.md5(obj._data).hexdigest())
        cb = page.cropbox
        coords = frozenset(round(float(v) * 2) / 2 for v in (cb.left, cb.bottom, cb.right, cb.top))
        out.append((tuple(sorted(hashes)), coords))
    return out


def _cached_keys(path: Path, cache: dict) -> list:
    st = path.stat()
    tag = f"{st.st_size}:{int(st.st_mtime)}"
    rel = str(path.relative_to(REPO_ROOT))
    hit = cache.get(rel)
    if hit and hit["tag"] == tag:
        return [(tuple(h), frozenset(c)) for h, c in hit["keys"]]
    keys = _page_keys(path)
    cache[rel] = {"tag": tag, "keys": [[list(h), sorted(c)] for h, c in keys]}
    return keys


# ---------------------------------------------------------------- scanning

def _split_files():
    """Yield (path, ethnic, collection folder, version folder or None)."""
    for top, ethnic in ETHNIC_FOLDERS.items():
        root = REPO_ROOT / top
        if not root.exists():
            continue
        for dirpath, _, files in os.walk(root):
            for f in sorted(files):
                if not f.lower().endswith(".pdf"):
                    continue
                p = Path(dirpath) / f
                parts = p.relative_to(root).parts
                collection = parts[0].strip()
                version = parts[1].strip() if len(parts) >= 3 else None
                yield p, ethnic, collection, version


def _title_parts(title: str) -> list[str]:
    """'Main (Alt)' -> ['Main (Alt)', 'Main', 'Alt'] as slugs."""
    parts = [title] + re.split(r"[()]", title)
    return [s for s in (slugify(p) for p in parts) if s]


def _similar(a: str, b: str) -> float:
    """Best similarity over full titles and their main/parenthetical parts, since
    folders sometimes name the same work differently ('Trường Xah Pakei (Trường ca
    Xah Pakei)' vs 'Trường ca Xah Pakei (Ariya Xah Pakei)')."""
    return max(
        difflib.SequenceMatcher(None, x, y).ratio()
        for x in _title_parts(a) for y in _title_parts(b)
    )


def build(force: bool = False, verbose: bool = True) -> None:
    cache_path = CACHE_DIR / "inventory_keys.json"
    cache = read_json(cache_path) if cache_path.exists() else {}

    # 1. index every master page
    masters = sorted(MASTER_DIR.glob("*.pdf"))
    index: dict[tuple, list] = defaultdict(list)  # image hashes -> [(master, page, coords)]
    master_pages: dict[Path, int] = {}
    for m in masters:
        if verbose:
            print(f"  indexing {m.name}")
        keys = _cached_keys(m, cache)
        master_pages[m] = len(keys)
        for i, (hashes, coords) in enumerate(keys, start=1):
            if hashes:
                index[hashes].append((m, i, coords))

    # 2. match every split page to a master page
    # group key: (master or None, ethnic, collection)
    files_by_group: dict[tuple, list] = defaultdict(list)
    unmatched_pages = 0
    for path, ethnic, collection, version in _split_files():
        keys = _cached_keys(path, cache)
        pages, master = [], None
        for hashes, coords in keys:
            cands = index.get(hashes, []) if hashes else []
            if not cands:
                pages.append(None)
                continue
            best = max(cands, key=lambda c: len(c[2] & coords))
            pages.append(best[1])
            master = best[0]
        missing = sum(p is None for p in pages)
        if master is not None and missing:
            unmatched_pages += missing
            if verbose:
                print(f"  ! {missing} page(s) of {path.relative_to(REPO_ROOT)} not found in master")
        files_by_group[(master, ethnic, collection)].append(
            dict(path=path, version=version, pages=[p for p in pages if p], n=len(keys))
        )
    write_json(cache_path, cache)

    # 3. assemble books
    books: dict[str, dict] = {}

    def new_book(book_id, title, sources, page_count):
        return books.setdefault(book_id, dict(
            id=book_id, title=title, sources=sources, page_count=page_count,
            ethnic_groups=[], works=[], duplicates=[],
        ))

    for m in masters:
        new_book(slugify(m.stem), nfc(m.stem),
                 [dict(pdf=str(m.relative_to(REPO_ROOT)), pages=master_pages[m])],
                 master_pages[m])

    for (master, ethnic, collection), files in sorted(
        files_by_group.items(), key=lambda kv: (str(kv[0][0]), kv[0][1], kv[0][2])
    ):
        if master is not None:
            book = books[slugify(master.stem)]
        else:
            # split-only book: its pages are the split files, concatenated
            files.sort(key=lambda f: (f["version"] or "", f["path"].name))
            first = 1
            for f in files:
                f["pages"] = list(range(first, first + f["n"]))
                first += f["n"]
            book = new_book(
                slugify(collection), nfc(collection),
                [dict(pdf=str(f["path"].relative_to(REPO_ROOT)), pages=f["n"]) for f in files],
                first - 1,
            )
            book["note"] = "No master PDF exists for this book; it is assembled from the split files."
        if ethnic not in book["ethnic_groups"]:
            book["ethnic_groups"].append(ethnic)
        _add_works(book, files, ethnic, collection)

    # 4. write
    for book in books.values():
        _finish_and_write(book, force)
    if verbose:
        print(f"Wrote {len(books)} books to {BOOKS_DIR.relative_to(REPO_ROOT)}/"
              + (f" ({unmatched_pages} split pages unmatched)" if unmatched_pages else ""))


def _add_works(book: dict, files: list[dict], ethnic: str, collection: str) -> None:
    by_version: dict[str | None, list] = defaultdict(list)
    for f in files:
        by_version[f["version"]].append(f)

    single_work = len(by_version) > 1 and all(len(v) == 1 for v in by_version.values())
    works: list[dict] = []
    for version_label in sorted(by_version, key=lambda v: v or ""):
        info = version_info(version_label, ethnic)
        seen_pages: dict[tuple, Path] = {}
        for f in by_version[version_label]:
            rel = str(f["path"].relative_to(REPO_ROOT))
            key = tuple(f["pages"])
            if key in seen_pages:
                book["duplicates"].append(dict(file=rel, same_pages_as=str(seen_pages[key].relative_to(REPO_ROOT))))
                continue
            seen_pages[key] = f["path"]
            title = nfc(f["path"].stem.strip())
            if single_work and works:
                work = works[0]
            else:
                work = None
                best = 0.0
                for w in works:
                    if any(v["folder"] == version_label for v in w["_versions"]):
                        continue
                    r = _similar(w["_titles"][0], title)
                    if r > best:
                        best, work = r, w
                if best < 0.75:
                    work = None
            if work is None:
                work = dict(_titles=[], _versions=[], ethnic_group=ethnic, collection=nfc(collection))
                works.append(work)
            work["_titles"].append(title)
            work["_versions"].append(dict(
                folder=version_label, **info, pages=f["pages"], split_pdf=rel,
            ))
    book["works"].extend(works)


def _finish_and_write(book: dict, force: bool) -> None:
    works_out = []
    used_ids: set[str] = set()
    covered: set[int] = set()
    for w in book["works"]:
        versions = sorted(w["_versions"], key=lambda v: min(v["pages"]) if v["pages"] else 0)
        title = w["_titles"][0]
        for v in versions:
            if v["kind"] in VI_KINDS_PREFERRED_FOR_TITLE:
                title = w["_titles"][w["_versions"].index(v)]
                break
        wid = slugify(title) or "work"
        base, k = wid, 2
        while wid in used_ids:
            wid, k = f"{base}-{k}", k + 1
        used_ids.add(wid)
        out_versions = []
        for v in versions:
            covered.update(v["pages"])
            ov = dict(kind=v["kind"], language=v["language"], content=v["content"])
            if v.get("script"):
                ov["script"] = v["script"]
            ov["pages"] = to_ranges(v["pages"])
            ov["folder"] = v["folder"]
            ov["split_pdf"] = v["split_pdf"]
            out_versions.append(ov)
        works_out.append(dict(
            id=wid,
            title=title,
            ethnic_group=w["ethnic_group"],
            collection=w["collection"],
            genre=None,
            versions=out_versions,
        ))
    works_out.sort(key=lambda w: min((int(v["pages"].split(",")[0].split("-")[0])
                                      for v in w["versions"] if v["pages"]), default=0))

    unassigned = sorted(set(range(1, book["page_count"] + 1)) - covered)
    out = dict(
        id=book["id"],
        title=book["title"],
        **({"note": book["note"]} if book.get("note") else {}),
        metadata=dict(
            subtitle=None, editors=[], authors=[], translators=[], publisher=None,
            year=None, place=None, isbn=None, series=None, rights=None,
        ),
        ethnic_groups=book["ethnic_groups"],
        page_count=book["page_count"],
        sources=book["sources"],
        unassigned_pages=to_ranges(unassigned),
        ocr=dict(include="", exclude=""),
        works=works_out,
    )
    if book["duplicates"]:
        out["duplicates"] = book["duplicates"]

    header = (
        "# Generated by `python -m vsc_ocr inventory`; safe to edit by hand.\n"
        "# Page numbers are 1-based pages of the source PDF(s), not printed page numbers.\n"
        "# content: text -> Vietnamese, OCR'd | pdf -> kept as scan only.\n"
        "# unassigned_pages are covered by no split (front matter, intro, mục lục...) and are OCR'd.\n"
        "# ocr.include / ocr.exclude: page ranges to add to / remove from OCR.\n"
    )
    path = BOOKS_DIR / book["id"] / "structure.yaml"
    if path.exists() and not force:
        path = path.with_name("structure.generated.yaml")
        print(f"  {book['id']}: structure.yaml exists, wrote {path.name} instead (use --force to overwrite)")
    write_yaml(path, out, header)
