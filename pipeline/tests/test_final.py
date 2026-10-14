"""Replaying the Final Book's Corrections onto a new AI pass: `python -m pytest tests` from pipeline/."""

from vsc_ocr import final

NEW = ["# SÁCH", "## 1. Gà gáy", "<!-- pdf 10-14 -->", "Ngày xưa có con gà. ⚠", "Gà gáy.",
       "## 2. Chàng Cuội", "<!-- pdf 15-18 -->", "Ngày xưa có chàng Cuội.", "Gà gáy."]


def corr(action, section, before, after):
    return dict(time="2026-10-15T10:00:00", action=action, section=section, pdf_pages=[10], before=before, after=after)


def test_a_correction_whose_before_is_still_there_is_applied():
    c = corr("edit", "1. Gà gáy", ["Ngày xưa có con gà. ⚠"], ["Ngày xưa có con gà."])
    blocks, applied, missed = final.replay(NEW, [c])
    assert blocks[3] == "Ngày xưa có con gà."
    assert applied == [c] and missed == []


def test_deletes_and_merges_replay_their_whole_run_of_blocks():
    merge = corr("merge", "1. Gà gáy", ["Ngày xưa có con gà. ⚠", "Gà gáy."], ["Ngày xưa có con gà. Gà gáy. ⚠"])
    delete = corr("delete", "2. Chàng Cuội", ["## 2. Chàng Cuội"], [])
    blocks, applied, missed = final.replay(NEW, [merge, delete])
    assert blocks == ["# SÁCH", "## 1. Gà gáy", "<!-- pdf 10-14 -->", "Ngày xưa có con gà. Gà gáy. ⚠",
                      "<!-- pdf 15-18 -->", "Ngày xưa có chàng Cuội.", "Gà gáy."]
    assert len(applied) == 2 and missed == []


def test_corrections_apply_in_order_so_a_later_one_sees_an_earlier_ones_result():
    first = corr("edit", "1. Gà gáy", ["Gà gáy."], ["Gà gáy sáng."])
    second = corr("edit", "1. Gà gáy", ["Gà gáy sáng."], ["Gà gáy sáng!"])
    blocks, applied, missed = final.replay(NEW, [first, second])
    assert blocks[4] == "Gà gáy sáng!" and blocks[8] == "Gà gáy."
    assert len(applied) == 2


def test_a_before_found_in_its_own_section_is_preferred_to_the_same_text_elsewhere():
    c = corr("edit", "2. Chàng Cuội", ["Gà gáy."], ["Gà gáy to."])
    blocks, _, _ = final.replay(NEW, [c])
    assert blocks[4] == "Gà gáy." and blocks[8] == "Gà gáy to."


def test_a_before_not_in_its_section_is_applied_where_the_book_has_it_once():
    c = corr("edit", "Lời giới thiệu", ["Ngày xưa có chàng Cuội."], ["Thuở xưa có chàng Cuội."])
    blocks, applied, _ = final.replay(NEW, [c])
    assert blocks[7] == "Thuở xưa có chàng Cuội." and applied == [c]


def test_a_before_the_new_pass_wrote_differently_or_twice_elsewhere_is_missed():
    gone = corr("edit", "1. Gà gáy", ["Ngày xưa có con gà trống. ⚠"], ["Ngày xưa có con gà trống."])
    twice = corr("edit", "Lời giới thiệu", ["Gà gáy."], ["Gà gáy to."])
    blocks, applied, missed = final.replay(NEW, [gone, twice])
    assert blocks == NEW and applied == []
    assert missed == [gone, twice]


def test_spelling_corrections_are_not_replayed():
    c = corr("spelling", "1. Gà gáy", ["Gà gáy."], ["Gà Gáy."])
    blocks, applied, missed = final.replay(NEW, [c])
    assert blocks == NEW and applied == [] and missed == []


def test_flags_counts_the_warnings_left_by_section():
    assert final.flags(NEW) == {"1. Gà gáy": 1}


# -- the commands, on a book folder in tmp_path

import json
from types import SimpleNamespace

import pytest


DRAFT = "## 1. Gà gáy\n\n<!-- pdf 10-14 -->\n\nGà gáy. ⚠\n"
DONE = DRAFT.replace(" ⚠", "")


def book_with_pass(tmp_path, text, model_log="pass 1"):
    (tmp_path / "toc.json").write_text(json.dumps({"book": "sach", "toc": {"id": "sach", "title": "SÁCH", "children": [
        {"id": "ga-gay", "printed_page": 9, "pdf_start": 10}]}}), encoding="utf-8")
    (tmp_path / "ai").mkdir(exist_ok=True)
    (tmp_path / "ai" / "book.ai.md").write_text(text, encoding="utf-8")
    (tmp_path / "ai" / "ai_corrections.jsonl").write_text(model_log, encoding="utf-8")
    return SimpleNamespace(id="sach", dir=tmp_path)


def new_pass(book, text, model_log):
    for p in (book.dir / "ai").iterdir():
        p.unlink()
    book_with_pass(book.dir, text, model_log)


def log(path, *entries):
    path.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries), encoding="utf-8")


def test_finalize_refuses_while_a_warning_is_left(tmp_path):
    book = book_with_pass(tmp_path, DRAFT)
    with pytest.raises(SystemExit, match="1 ⚠"):
        final.finalize(book)
    assert not (tmp_path / "final" / "book-final.md").exists()


def test_finalize_copies_the_text_and_replaces_the_log(tmp_path):
    book = book_with_pass(tmp_path, DONE)
    (tmp_path / "final").mkdir()
    log(tmp_path / "final" / "corrections.jsonl", corr("edit", "x", ["old"], ["older"]))
    log(tmp_path / "ai" / "corrections.jsonl", corr("edit", "1. Gà gáy", ["Gà gáy. ⚠"], ["Gà gáy."]))
    final.finalize(book)
    assert (tmp_path / "final" / "book-final.md").read_text(encoding="utf-8") == DONE
    assert (tmp_path / "final" / "corrections.jsonl").read_text() == (tmp_path / "ai" / "corrections.jsonl").read_text()
    assert json.loads((tmp_path / "final" / "toc.json").read_text())["toc"]["children"][0]["printed_page"] == 9
    assert json.loads((tmp_path / "final" / "notes.json").read_text())["notes"] == []


def test_the_same_pass_finalizes_again_but_a_new_one_needs_its_corrections_replayed(tmp_path):
    book = book_with_pass(tmp_path, DRAFT)
    (tmp_path / "ai" / "book.ai.md").write_text(DONE, encoding="utf-8")
    log(tmp_path / "ai" / "corrections.jsonl", corr("edit", "1. Gà gáy", ["Gà gáy. ⚠"], ["Gà gáy."]))
    final.finalize(book)
    final.finalize(book)                                    # a later fix to the same pass

    new_pass(book, DRAFT, "pass 2")
    with pytest.raises(SystemExit, match="apply-corrections"):
        final.finalize(book)

    final.apply_corrections(book)
    assert (tmp_path / "ai" / "book.ai.md").read_text(encoding="utf-8") == DONE
    assert (tmp_path / "ai" / "book.ai.raw.md").read_text(encoding="utf-8") == DRAFT
    final.finalize(book)
    assert len((tmp_path / "final" / "corrections.jsonl").read_text().splitlines()) == 1


def test_apply_corrections_runs_once_per_pass_and_not_over_a_reviewed_one(tmp_path):
    book = book_with_pass(tmp_path, DONE)
    with pytest.raises(SystemExit, match="nothing to replay"):
        final.apply_corrections(book)
    final.finalize(book)

    new_pass(book, DONE, "pass 2")
    log(tmp_path / "ai" / "corrections.jsonl", corr("edit", "1. Gà gáy", ["a"], ["b"]))
    with pytest.raises(SystemExit, match="has Corrections already"):
        final.apply_corrections(book)
    final.apply_corrections(book, force=True)
    with pytest.raises(SystemExit, match="already"):
        final.apply_corrections(book)


# -- the Final Book's toc.json and notes.json, from its text

BOOK = ["# SÁCH", "<!-- pdf 4 · front -->",
        "## Lời giới thiệu", "<!-- pdf 6-8 · heading: LỜI GIỚI THIỆU -->", "Lời.",
        "## 1. Gà gáy[^ga-gay-p10-1]", "<!-- pdf 10-14 -->", "Con gà[^ga-gay-p10-2] gáy.",
        "[^ga-gay-p10-1]: Gà : con gà. <!-- note pdf 10 -->",
        "[^ga-gay-p10-2]: Gáy : kêu. <!-- note pdf 10 · call not found -->",
        "## 2. Jôt đi học (Ja Jôt nao mugru)", "<!-- pdf 15-18 -->", "Jôt đi học.",
        "[^jot-di-hoc-ja-jot-nao-mugru-p16-1]: Jôt : tên. <!-- note pdf 16 -->"]
OCR_TOC = {"book": "sach", "toc": {"id": "sach", "title": "SÁCH", "level": 0, "pdf_start": 6, "pdf_end": 18, "children": [
    {"id": "loi-gioi-thieu", "number": None, "title": "Lời giới thiệu", "level": 1, "printed_page": 5,
     "pdf_start": 6, "pdf_end": 8, "toc_title": "Ỉ s Lời giới thiệu", "heading_ocr": ["LỜI GIỚI THIỆU"]},
    {"id": "ga-gay", "number": 1, "title": "Gà gầy", "level": 1, "printed_page": 9, "pdf_start": 10, "pdf_end": 14},
    {"id": "jot-di-hoc-ja-jot-nao-mugru", "number": 2, "title": "Jôt đi học", "subtitle": "Ja Jốt nao mugru",
     "level": 1, "printed_page": 14, "pdf_start": 15, "pdf_end": 18}]}, "disagreements": ["row 2: ..."]}


def test_the_toc_is_the_final_books_headings_with_the_ocr_tocs_ids_and_printed_pages():
    assert final.toc(BOOK, OCR_TOC) == {"book": "sach", "toc": {
        "id": "sach", "title": "SÁCH", "level": 0, "pdf_start": 6, "pdf_end": 18, "children": [
            {"id": "loi-gioi-thieu", "number": None, "title": "Lời giới thiệu", "subtitle": None, "level": 1,
             "printed_page": 5, "pdf_start": 6, "pdf_end": 8},
            {"id": "ga-gay", "number": 1, "title": "Gà gáy", "subtitle": None, "level": 1,
             "printed_page": 9, "pdf_start": 10, "pdf_end": 14},
            {"id": "jot-di-hoc-ja-jot-nao-mugru", "number": 2, "title": "Jôt đi học", "subtitle": "Ja Jôt nao mugru",
             "level": 1, "printed_page": 14, "pdf_start": 15, "pdf_end": 18}]}}


def test_a_section_the_ocr_toc_has_no_entry_for_stops_the_toc():
    ocr = {"book": "sach", "toc": dict(OCR_TOC["toc"], children=OCR_TOC["toc"]["children"][:2])}
    with pytest.raises(SystemExit, match="2. Jôt đi học"):
        final.toc(BOOK, ocr)


def test_the_notes_are_the_final_books_note_definitions_by_section():
    toc = final.toc(BOOK, OCR_TOC)
    assert final.notes(BOOK, toc) == {"book": "sach", "notes": [
        {"id": "ga-gay-p10-1", "scope": "ga-gay", "page": 10, "marker": "1", "text": "Gà : con gà.", "called": True},
        {"id": "ga-gay-p10-2", "scope": "ga-gay", "page": 10, "marker": "2", "text": "Gáy : kêu.", "called": True},
        {"id": "jot-di-hoc-ja-jot-nao-mugru-p16-1", "scope": "jot-di-hoc-ja-jot-nao-mugru", "page": 16,
         "marker": "1", "text": "Jôt : tên.", "called": False}]}
