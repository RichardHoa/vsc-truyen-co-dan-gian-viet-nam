"""The Web Edition, generated from a Final Book: `python -m pytest tests` from pipeline/."""

import json

import pytest

from vsc_ocr import web

BOOK = [
    "# SÁCH",
    "<!-- pdf 4 · tác giả -->",
    "## Lời giới thiệu",
    "<!-- pdf 6-8 · heading: LỜI GIỚI THIỆU -->",
    "Sách này có hai truyện.",
    "Phan Rang, thu năm 1997  \nTRƯƠNG HIẾN MAI",
    "## 1. Gà gáy[^ga-gay-p10-star]",
    "<!-- pdf 10-14 · heading: GÀ GÁY -->",
    "Ngày xưa có con gà[^ga-gay-p10-1].",
    "<!-- pdf 12 -->",
    "\\- Ò ó o!",
    "\\- Gà gáy rồi.",
    "Tưởng rằng ông táo thật thà  \nHay đâu ông táo một bà hai ông",
    "[^ga-gay-p10-star]: Truyện kể ở Phan Rang. <!-- note pdf 10 -->",
    "[^ga-gay-p10-1]: Gà trống. <!-- note pdf 11 -->",
    "## 2. Pô Ri Yak (Thần sóng)",
    "<!-- pdf 15 -->",
    "Ngày xưa có thần sóng.",
]


def export(lines=BOOK, offset=1, stories=2):
    return web.export("\n\n".join(lines) + "\n", offset, stories, "Sách")


def toc(files):
    return json.loads(files["table_of_contents.json"])


def test_the_preface_and_each_story_get_their_own_file_and_a_toc_entry():
    files = export()
    assert sorted(files) == ["loi_gioi_thieu.md", "story_001.md", "story_002.md", "table_of_contents.json"]
    assert toc(files) == {
        "book_title": "Sách",
        "preface": {"title": "Lời giới thiệu", "markdown_file": "loi_gioi_thieu.md",
                    "start_page": 5, "end_page": 7, "footnote_count": 0},
        "stories": [
            {"story_number": 1, "title": "Gà gáy", "start_page": 9, "end_page": 13,
             "markdown_file": "story_001.md", "footnote_count": 2},
            {"story_number": 2, "title": "Pô Ri Yak (Thần sóng)", "start_page": 14, "end_page": 14,
             "markdown_file": "story_002.md", "footnote_count": 0},
        ],
    }


def test_a_story_is_its_heading_and_text_with_its_notes_renumbered_and_moved_to_the_end():
    lines = BOOK[:8] + ["Ngày xưa có con gà[^ga-gay-p10-1].",
                        "[^ga-gay-p10-1]: Gà trống. <!-- note pdf 11 -->",
                        "Gà gáy[^ga-gay-p13-1] sáng.",
                        "[^ga-gay-p10-star]: Truyện kể ở Phan Rang. <!-- note pdf 10 -->",
                        "[^ga-gay-p13-1]: Lúc rạng đông. <!-- note pdf 13 -->"] + BOOK[15:]
    assert export(lines)["story_001.md"] == (
        "## 1. Gà gáy[^1]\n\n"
        "Ngày xưa có con gà[^2].\n\n"
        "Gà gáy[^3] sáng.\n\n"
        "---\n\n"
        "### Chú thích\n\n"
        "[^1]: (Trang 9) Truyện kể ở Phan Rang.\n\n"
        "[^2]: (Trang 10) Gà trống.\n\n"
        "[^3]: (Trang 12) Lúc rạng đông.\n")


def test_a_note_call_in_a_title_stays_in_the_heading_but_not_in_the_toc_title():
    lines = BOOK[:6] + ["## 1. Bảy chàng trai [^bay-p91-1]", "<!-- pdf 10 -->", "Ngày xưa.",
                        "[^bay-p91-1]: Truyện thơ. <!-- note pdf 10 -->"] + BOOK[15:]
    files = export(lines)
    assert files["story_001.md"].startswith("## 1. Bảy chàng trai [^1]\n\nNgày xưa.\n\n---")
    assert toc(files)["stories"][0]["title"] == "Bảy chàng trai"


def test_every_html_comment_is_removed():
    files = export()
    assert not any("<!--" in content for content in files.values())
    assert files["story_002.md"] == "## 2. Pô Ri Yak (Thần sóng)\n\nNgày xưa có thần sóng.\n"


def test_escaped_dialogue_dashes_become_plain_dashes():
    assert "\n\n- Ò ó o!\n\n- Gà gáy rồi.\n\n" in export()["story_001.md"]


def test_a_block_of_hard_breaks_becomes_verse_lines():
    assert "\n\n> Tưởng rằng ông táo thật thà\n> Hay đâu ông táo một bà hai ông\n\n" in export()["story_001.md"]


def test_the_prefaces_closing_block_becomes_right_aligned_lines():
    assert export()["loi_gioi_thieu.md"] == (
        "## Lời giới thiệu\n\n"
        "Sách này có hai truyện.\n\n"
        "-> Phan Rang, thu năm 1997\n"
        "-> TRƯƠNG HIẾN MAI\n")


# -- refusals: nothing is exported, and every problem is named


def refusal(lines=BOOK, offset=1, stories=2):
    with pytest.raises(web.Refused) as e:
        export(lines, offset, stories)
    return str(e.value)


def test_a_book_without_a_printed_page_offset_is_refused():
    assert "printed_page_offset" in refusal(offset=None)


def test_a_missing_story_is_refused():
    assert "story 3 is missing" in refusal(stories=3)


def test_stories_out_of_order_are_refused():
    lines = BOOK[:6] + BOOK[15:] + BOOK[6:15]
    message = refusal(lines)
    assert "## 2. Pô Ri Yak (Thần sóng)" in message and "## 1. Gà gáy" in message


def test_a_book_not_opening_on_the_lời_giới_thiệu_is_refused():
    assert "## 1. Gà gáy" in refusal(BOOK[:2] + BOOK[6:])


def test_a_heading_without_its_pdf_range_is_refused():
    assert "## 2. Pô Ri Yak (Thần sóng)" in refusal(BOOK[:16] + BOOK[17:])


def test_a_note_call_without_its_definition_is_refused():
    message = refusal(BOOK[:14] + BOOK[15:])
    assert "1. Gà gáy" in message and "[^ga-gay-p10-1]" in message


def test_a_definition_never_called_is_refused():
    lines = BOOK[:8] + ["Ngày xưa có con gà."] + BOOK[9:]
    message = refusal(lines)
    assert "1. Gà gáy" in message and "[^ga-gay-p10-1]" in message


def test_a_note_called_twice_is_refused():
    lines = BOOK[:8] + ["Ngày xưa có con gà[^ga-gay-p10-1], gà[^ga-gay-p10-1]."] + BOOK[9:]
    assert "[^ga-gay-p10-1]" in refusal(lines)


def test_a_definition_without_its_note_pdf_tag_is_refused():
    lines = BOOK[:14] + ["[^ga-gay-p10-1]: Gà trống."] + BOOK[15:]
    message = refusal(lines)
    assert "1. Gà gáy" in message and "[^ga-gay-p10-1]" in message and "note pdf" in message


@pytest.mark.parametrize("block", [
    "Ngày xưa có *con gà*.",
    "Ngày xưa có __con gà__.",
    "Ngày xưa có `con gà`.",
    "Ngày xưa có <b>con gà</b>.",
    "Xem [truyện khác](story_002.md).",
    "* con gà",
    "+ con gà",
    "1. con gà",
    "| con | gà |",
    "* * *",
    "#### Gà gáy",
    "Gà gáy \\* ba lần.",
])
def test_markdown_the_website_doesnt_render_is_refused(block):
    message = refusal(BOOK[:11] + [block] + BOOK[11:])
    assert "1. Gà gáy" in message and block[:20] in message


def test_every_problem_is_reported_at_once():
    lines = BOOK[:8] + ["Ngày xưa có *con gà*[^ga-gay-p10-1]."] + BOOK[9:14] + BOOK[15:16] + BOOK[17:]
    message = refusal(lines, offset=None, stories=3)
    for problem in ["printed_page_offset", "*con gà*", "[^ga-gay-p10-1]", "## 2. Pô Ri Yak", "story 3 is missing"]:
        assert problem in message


def test_the_same_final_book_gives_the_same_web_edition():
    assert export() == export()
    assert all(content.endswith("\n") and not content.endswith("\n\n") for content in export().values())


def test_markdown_the_website_doesnt_render_in_a_note_is_refused():
    lines = BOOK[:14] + ["[^ga-gay-p10-1]: Gà *trống*. <!-- note pdf 11 -->"] + BOOK[15:]
    assert "Gà *trống*." in refusal(lines)


def test_an_escaped_dash_with_no_space_after_it_becomes_a_plain_dash_too():
    lines = BOOK[:11] + ['\\-"Thưa ông.', "\\-..."] + BOOK[12:]
    assert '\n\n-"Thưa ông.\n\n-...\n\n' in export(lines)["story_001.md"]
