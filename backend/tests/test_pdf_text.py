from pdf_text import clean_resume_text


def test_bullet_glyphs_become_dashes():
    raw = "\u2022 One\n\u25cf Two\n\uf0b7 Three\n- Four"
    assert clean_resume_text(raw) == "- One\n- Two\n- Three\n- Four"


def test_undecodable_cid_bullets_are_recognized_and_stripped():
    assert clean_resume_text("(cid:127) One\n(cid:127)Two") == "- One\n- Two"
    assert clean_resume_text("hi (cid:9) there") == "hi there"


def test_wrapped_bullets_are_joined_but_new_sections_are_not():
    raw = "- Trained new hires on the\ngrill\nEDUCATION\nCommunity College"
    assert clean_resume_text(raw) == "- Trained new hires on the grill\nEDUCATION\nCommunity College"


def test_extra_blank_lines_are_collapsed():
    assert clean_resume_text("A\n\n\n\n\nB") == "A\n\nB"
