import json

from mock import build_mock_regenerate, build_mock_rewrites, extract_bullets


def test_extract_bullets_prefers_marked_bullets():
    text = "Header Line Here\n- First bullet point\n- Second bullet point"
    assert extract_bullets(text) == ["First bullet point", "Second bullet point"]


def test_extract_bullets_without_markers_skips_short_headings():
    text = "EXPERIENCE\nLed a team of four to build a tracker"
    assert extract_bullets(text) == ["Led a team of four to build a tracker"]


def test_extract_bullets_is_capped():
    text = "\n".join(f"- bullet number {i}" for i in range(20))
    assert len(extract_bullets(text)) == 8


def test_build_mock_rewrites_returns_none_when_nothing_found():
    assert build_mock_rewrites("Hi") is None


def test_build_mock_regenerate_includes_the_detail():
    data = json.loads(build_mock_regenerate("Original", "40 per shift"))
    assert data["original"] == "Original"
    assert "40 per shift" in data["rewritten"]
