"""Spelling Rules and the diacritic review's pairs: `python -m pytest tests` from pipeline/."""

from vsc_ocr.review import spellings as sp


def rules(words=(), phrases=(), depends=()):
    """A spellings.yaml as `load` gives it; a word is a spelling or (spelling, [excepted story titles])."""
    words = [w if isinstance(w, tuple) else (w, []) for w in words]
    return dict(words=[dict(spelling=w, **{"except": list(e)}) for w, e in words],
                phrases=[dict(spelling=p, **{"except": []}) for p in phrases], depends=[list(d) for d in depends])


def book(*sections):
    """book.md text: each section (title, [paragraphs]) as a heading, its pdf comment and its paragraphs."""
    blocks = []
    for k, (title, paras, *comment) in enumerate(sections):
        blocks += [f"## {title}", comment[0] if comment else f"<!-- pdf {k + 1} -->", *paras]
    return blocks


# ---------------------------------------------------------------- words and case

def test_fold_drops_marks_and_case_and_reads_d_bar_as_d():
    assert sp.fold("Tềwa") == sp.fold("TÊWA") == sp.fold("têwa") == "tewa"
    assert sp.fold("Đăm") == sp.fold("Dăm") == "dam"


def test_words_in_note_calls_and_comments_are_not_words():
    assert [s[0] for s in sp.spans("Pụ[^1] đi <!-- pdf 3 --> về")] == ["Pụ", "đi", "về"]


def test_a_replacement_takes_the_case_of_the_word_it_replaces():
    assert sp.cased("Tềwa", "TÊWA") == "TỀWA"
    assert sp.cased("Tềwa", "têwa") == "tềwa"
    assert sp.cased("Tềwa", "Têwa") == "Tềwa"
    assert sp.cased("Tềwa", "TêWa") == "TềWa"


# ---------------------------------------------------------------- applying rules

def test_a_word_rule_respells_every_case_and_leaves_other_words_alone():
    text, changes = sp.respell("Têwa nói: TÊWA! têwa và Mùnô", rules(["Tềwa"]), "Chuyện")
    assert text == "Tềwa nói: TỀWA! tềwa và Mùnô"
    assert changes == [("Têwa", "Tềwa", "Tềwa"), ("TÊWA", "TỀWA", "Tềwa"), ("têwa", "tềwa", "Tềwa")]


def test_a_word_already_spelled_right_is_not_a_change():
    assert sp.respell("Tềwa đi", rules(["Tềwa"]), "Chuyện") == ("Tềwa đi", [])


def test_a_phrase_rule_respells_only_with_its_neighbours_and_punctuation():
    data = rules(phrases=["bồng - bồng"])
    assert sp.respell("con bông - bông đó", data, "X")[0] == "con bồng - bồng đó"
    assert sp.respell("một bông hoa", data, "X")[0] == "một bông hoa"
    assert sp.respell("bông, bông", data, "X")[0] == "bông, bông"


def test_a_phrase_beats_a_word_rule_on_its_words():
    data = rules(words=["Xa"], phrases=["xà lan"])
    assert sp.respell("xa lan và xá", data, "X")[0] == "xà lan và xa"


def test_a_rule_is_skipped_in_the_stories_it_excepts_whatever_their_marks():
    data = rules(words=[("Jamưtui", ["Hoàng tử TêWa MừNô"])])
    assert sp.respell("Jamutui", data, "HOÀNG TỬ TỀWA MỪNÔ")[1] == []
    assert sp.respell("Jamutui", data, "Kathăr ăn phân chó")[0] == "Jamưtui"


def test_apply_changes_headings_and_text_but_not_comments_and_names_raw_titles():
    blocks = book(("TÊWA đi", ["Têwa về."], "<!-- pdf 1 · heading: TÊWA ĐI -->"), ("Khác", ["Têwa ở."]))
    story = sp.story_titles(blocks, book(("Têwa đi", []), ("Khác", [])))
    data = rules(words=[("Tềwa", ["Khác"])])
    changed = sp.apply(blocks, data, story)
    assert {i: new for i, (new, _) in changed.items()} == {0: "## TỀWA đi", 2: "Tềwa về."}


def test_apply_leaves_story_titles_as_set_and_exceptions_name_story_titles():
    blocks = book(("TÊWA đi", ["Têwa về."]), ("Khác", ["Têwa ở."]))
    titles = {1: "TÊWA đi", 2: "Truyện khác"}
    story = sp.story_titles(blocks, book(("Têwa đi", []), ("Khác", [])), titles)
    data = rules(words=[("Tềwa", ["Truyện khác"])])
    changed = sp.apply(blocks, data, story, fixed={0})
    assert {i: new for i, (new, _) in changed.items()} == {2: "Tềwa về."}


def test_covered_names_the_rule_that_decides_a_word():
    data = rules(words=["Tềwa"], phrases=["bồng - bồng"])
    assert sp.covered("Tềwa và bông - bông", 0, data, "X") == "Tềwa"
    assert sp.covered("Tềwa và bông - bông", 8, data, "X") == "bồng - bồng"
    assert sp.covered("một bông", 4, data, "X") is None


def test_the_file_round_trips(tmp_path):
    path = tmp_path / "spellings.yaml"
    data = rules(words=[("Tềwa", ["Chuyện A"])], phrases=["bồng - bồng"], depends=[("thầy", "thấy")])
    sp.save(path, data)
    assert sp.load(path) == data
    assert sp.load(tmp_path / "none.yaml") == sp.empty()


# ---------------------------------------------------------------- pairs

def test_a_word_the_model_and_the_ocr_spell_with_different_marks_is_listed():
    current = book(("Chuyện", ["Têwa Mùnô đi."]))
    raw = book(("Chuyện", ["Tềwa Mừnô đi."]))
    found = sp.find_pairs(current, raw, current, common=set())
    assert [(o["word"], o["ai"], o["ocr"]) for o in found] == [("Têwa", "Têwa", "Tềwa"), ("Mùnô", "Mùnô", "Mừnô")]
    assert found[0]["block"] == 2 and found[0]["start"] == 0 and found[0]["after"] == "Mùnô đi"


def test_a_word_changed_since_the_model_read_it_is_listed_with_the_models_reading():
    current = book(("Chuyện", ["Tềwa đi."]))
    model = book(("Chuyện", ["Têwa đi."]))
    found = sp.find_pairs(current, current, model, common=set())
    assert [(o["word"], o["ai"], o["ocr"]) for o in found] == [("Tềwa", "Têwa", "Tềwa")]


def test_words_with_different_letters_are_not_pairs():
    current = book(("Chuyện", ["Xưa kia"]))
    raw = book(("Chuyện", ["Rua kia"]))
    assert sp.find_pairs(current, raw, current, common=set()) == []


def test_a_heading_is_read_against_the_models_heading_comment():
    current = book(("Bảy chàng trai khoe", ["Họ đi."], "<!-- pdf 1 · heading: BẢY CHÀNG TRAI KHOỂ -->"))
    found = sp.find_pairs(current, current, current, common={"bay", "chang", "trai", "khoe"})
    assert [(o["word"], o["ai"], o["heading"]) for o in found] == [("khoe", "KHOỂ", True)]


def test_a_name_still_spelled_two_ways_in_a_story_is_listed_even_where_all_agree():
    current = book(("Chuyện", ["Samulé đi.", "Samule về."]), ("Khác", ["Samule ở."]))
    found = sp.find_pairs(current, current, current, common=set())
    assert [(o["word"], o["section"], o["name"]) for o in found] == [("Samulé", 0, True), ("Samule", 0, True)]


def test_a_heading_spelling_a_name_its_own_way_does_not_list_the_storys_text():
    current = book(("Hoàng tử TêWa", ["Tềwa đi.", "Tềwa về."]))
    assert sp.find_pairs(current, current, current, common=set()) == []


def test_a_common_word_spelled_two_ways_in_a_story_is_not_listed_by_itself():
    current = book(("Chuyện", ["thầy nói", "nó thấy"]))
    assert sp.find_pairs(current, current, current, common=sp.lower_folds(*current)) == []


# ---------------------------------------------------------------- the model's reading and the OCR line

def test_the_models_reading_undoes_the_names_the_pass_respelled(tmp_path):
    import json
    from vsc_ocr.review.diacritic import model_text
    (tmp_path / "ai_corrections.jsonl").write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in [
        dict(action="edit", before=["Têwa đi."], after=["Tềwa đi."], reason="names as the OCR prints them in this story: Têwa → Tềwa"),
        dict(action="edit", before=["Rua kia"], after=["Xưa kia"], reason="transcribed from the scan"),
    ]) + "\n", encoding="utf-8")
    current = ["## Chuyện", "Tềwa đi.", "Xưa kia"]
    assert model_text(tmp_path, current) == ["## Chuyện", "Têwa đi.", "Xưa kia"]


def test_an_engines_reading_is_the_word_whose_neighbours_match():
    from vsc_ocr.review.diacritic import _word
    line = sp.spans("Têwa nói với Tềwa đi")
    assert _word(line, "tewa", ["voi"], ["di"]) == "Tềwa"
    assert _word(line, "tewa", [], ["noi"]) == "Têwa"
    assert _word(line, "muno", [], []) is None


def test_an_undone_respelling_goes_to_the_block_in_its_own_story(tmp_path):
    import json
    from vsc_ocr.review.diacritic import model_text
    (tmp_path / "ai_corrections.jsonl").write_text(json.dumps(dict(
        action="edit", section="B", before=["Têwa đi."], after=["Tềwa đi."],
        reason="names as the OCR prints them in this story: Têwa → Tềwa"), ensure_ascii=False) + "\n", encoding="utf-8")
    current = ["## A", "Tềwa đi.", "## B", "Tềwa đi."]
    assert model_text(tmp_path, current) == ["## A", "Tềwa đi.", "## B", "Têwa đi."]


def test_books_whose_sections_dont_pair_up_are_refused():
    import pytest
    with pytest.raises(ValueError):
        sp.find_pairs(book(("A", []), ("B", [])), book(("A", [])), book(("A", []), ("B", [])), common=set())
