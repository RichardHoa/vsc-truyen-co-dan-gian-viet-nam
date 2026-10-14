"""Story Titles (titles.yaml): `python -m pytest tests` from pipeline/."""

from vsc_ocr.review import titles as st

RAW = ["# TRUYỆN CỔ DÂN GIAN CHĂM", "<!-- pdf 4 · front -->",
       "## 28. Kén rế", "<!-- pdf 248-250 -->", "Ngày xưa.",
       "## 48. Jôt đi học (Ja Jốt nao mugru)", "<!-- pdf 447-450 -->", "Ja Jốt đi học."]
AI = ["# TRUYỆN CỔ DÂN GIAN CHĂM", "<!-- pdf 4 · front -->",
      "## 28. Kén rể [^ken-re-p248-1]", "<!-- pdf 248-250 · heading: KÉN RỂ -->", "Ngày xưa.",
      "## 48. Jôt đi học\n## (Ja Jôt nao mugru)", "<!-- pdf 447-450 -->", "Ja Jốt đi học."]


def test_the_story_titles_are_a_books_headings_by_the_first_pdf_page_of_their_raw_section():
    # no note calls, one line; the book's own title (`# `) is not a story
    assert st.from_book(AI, RAW) == {248: "28. Kén rể", 447: "48. Jôt đi học (Ja Jôt nao mugru)"}


def test_editing_a_heading_sets_its_story_title():
    after = list(AI)
    after[2] = "## 28. Kén Rể [^ken-re-p248-1]"
    after[4] = "Ngày xưa lắm."

    assert st.changed(AI, after, RAW, {248: "28. Kén rể", 447: "x"}) == {248: "28. Kén Rể", 447: "x"}
    assert st.changed(AI, [b.replace("xưa.", "xưa!") for b in AI], RAW, {}) is None     # no heading edited


def test_a_heading_deleted_or_added_sets_nothing():
    assert st.changed(AI, AI[:5] + AI[6:], RAW, {}) is None


def test_the_headings_with_a_story_title_are_the_ones_left_as_set():
    assert st.set_headings(AI, RAW, {447: "48. Jôt đi học (Ja Jôt nao mugru)"}) == {5}
