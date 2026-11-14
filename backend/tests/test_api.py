import io

import pytest
from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

import main

client = TestClient(main.app)

RESUME = """Crew Member, Sample Cafe
- Helped customers at the register
- Worked with team to prepare food
- Reduced wait times by 20% by reorganizing the line"""


def make_pdf(lines: list[str], pages: int = 1) -> bytes:
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=letter)
    for _ in range(pages):
        y = 750
        for line in lines:
            pdf.drawString(72, y, line)
            y -= 18
        pdf.showPage()
    pdf.save()
    return buf.getvalue()


def upload(data: bytes, name: str = "resume.pdf"):
    return client.post("/extract-pdf", files={"file": (name, data, "application/pdf")})


# ---------- health ----------


def test_health_reports_demo_mode():
    body = client.get("/health").json()
    assert body == {"status": "ok", "mock": True}


# ---------- /rewrite ----------


def test_rewrite_in_demo_mode_uses_the_pasted_bullets():
    res = client.post("/rewrite", json={"resume_text": RESUME, "job_description": "Analyst"})
    assert res.status_code == 200
    rewrites = res.json()["rewrites"]
    assert [r["original"] for r in rewrites] == [
        "Helped customers at the register",
        "Worked with team to prepare food",
        "Reduced wait times by 20% by reorganizing the line",
    ]
    assert rewrites[0]["rewritten"] == "Assisted customers at the register"
    # Only the bullet without a number gets a follow-up question.
    assert rewrites[0]["missing_info"] != ""
    assert rewrites[2]["missing_info"] == ""


def test_rewrite_falls_back_to_sample_when_no_bullets_found():
    res = client.post("/rewrite", json={"resume_text": "Hi", "job_description": "x"})
    assert res.status_code == 200
    assert len(res.json()["rewrites"]) >= 1


@pytest.mark.parametrize(
    "payload",
    [
        {"resume_text": "", "job_description": "x"},
        {"resume_text": "x", "job_description": ""},
        {"resume_text": "x" * 30_001, "job_description": "x"},
        {"resume_text": "x", "job_description": "x" * 15_001},
        {"resume_text": "x"},
    ],
)
def test_rewrite_rejects_bad_input(payload):
    assert client.post("/rewrite", json=payload).status_code == 422


# ---------- /regenerate ----------


def test_regenerate_keeps_original_and_uses_detail():
    res = client.post(
        "/regenerate",
        json={
            "original": "Helped customers at the register",
            "user_detail": "about 40 per shift",
            "job_description": "Analyst",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["original"] == "Helped customers at the register"
    assert "about 40 per shift" in body["rewritten"]


def test_regenerate_never_lets_the_model_change_the_original(monkeypatch):
    monkeypatch.setattr(
        main,
        "call_llm",
        lambda *a, **k: '{"original": "CHANGED", "rewritten": "r", "reason": "x", "missing_info": ""}',
    )
    res = client.post(
        "/regenerate",
        json={"original": "Real original", "user_detail": "d", "job_description": "j"},
    )
    assert res.json()["original"] == "Real original"


def test_regenerate_rejects_empty_detail():
    res = client.post(
        "/regenerate", json={"original": "a", "user_detail": "", "job_description": "j"}
    )
    assert res.status_code == 422


# ---------- model-failure handling ----------


def test_empty_model_reply_becomes_a_clear_502(monkeypatch):
    def boom(*a, **k):
        raise main.EmptyReply("finish_reason: MAX_TOKENS")

    monkeypatch.setattr(main, "call_llm", boom)
    res = client.post("/rewrite", json={"resume_text": RESUME, "job_description": "x"})
    assert res.status_code == 502
    assert "empty reply" in res.json()["detail"]


def test_unparseable_model_reply_shows_what_the_model_said(monkeypatch):
    monkeypatch.setattr(main, "call_llm", lambda *a, **k: "Sure! Here you go: nothing")
    res = client.post("/rewrite", json={"resume_text": RESUME, "job_description": "x"})
    assert res.status_code == 502
    assert "Sure! Here you go" in res.json()["detail"]


def test_timeout_becomes_a_504_with_plain_message(monkeypatch):
    def slow(*a, **k):
        raise main.LLMTimeout("took too long")

    monkeypatch.setattr(main, "call_llm", slow)
    res = client.post("/rewrite", json={"resume_text": RESUME, "job_description": "x"})
    assert res.status_code == 504
    assert "too long" in res.json()["detail"]


def test_rate_limit_becomes_a_429_with_plain_message(monkeypatch):
    from google.genai import errors

    def limited(*a, **k):
        raise errors.ClientError(429, {"error": {"code": 429, "message": "quota"}})

    monkeypatch.setattr(main, "call_llm", limited)
    res = client.post("/rewrite", json={"resume_text": RESUME, "job_description": "x"})
    assert res.status_code == 429
    assert "rate limit" in res.json()["detail"].lower()


# ---------- extract_json ----------


def test_extract_json_handles_fences_and_stray_text():
    assert main.extract_json('```json\n{"rewrites": []}\n```') == {"rewrites": []}
    assert main.extract_json('Sure! {"rewrites": []} hope that helps') == {"rewrites": []}


def test_extract_json_prefers_the_final_answer_over_drafts():
    text = (
        'Plan: output {"original": "draft"} then finish.\n'
        '{"rewrites": [{"original": "a", "rewritten": "b", "reason": "r"}]}'
    )
    assert "rewrites" in main.extract_json(text)


def test_extract_json_does_not_return_a_nested_object():
    text = '{"rewrites": [{"original": "a", "rewritten": "b", "reason": "r"}]}'
    assert list(main.extract_json(text)) == ["rewrites"]


def test_extract_json_raises_when_there_is_no_json():
    with pytest.raises(ValueError):
        main.extract_json("no json here")


# ---------- PDF upload ----------


def test_pdf_upload_extracts_text_and_normalizes_bullets():
    lines = [
        "Jordan Lee",
        "\u2022 Helped customers at the register",
        "\u2022 Trained new hires on the grill and then",
        "continued to cover closing shifts",
    ]
    res = upload(make_pdf(lines))
    assert res.status_code == 200
    body = res.json()
    assert body["pages"] == 1
    assert "- Helped customers at the register" in body["text"]
    # The wrapped bullet is joined back into one line.
    assert "- Trained new hires on the grill and then continued to cover closing shifts" in body["text"]
    assert "cid:" not in body["text"]


def test_pdf_upload_rejects_a_file_that_is_not_a_pdf():
    assert upload(b"hello world").status_code == 422


def test_pdf_upload_rejects_a_file_over_5mb():
    assert upload(b"%PDF-" + b"0" * (5 * 1024 * 1024 + 10)).status_code == 413


def test_pdf_upload_rejects_a_pdf_with_no_text():
    res = upload(make_pdf([]))
    assert res.status_code == 422
    assert "No text found" in res.json()["detail"]


def test_pdf_upload_rejects_too_many_pages():
    res = upload(make_pdf(["hi"], pages=6))
    assert res.status_code == 422
    assert "6 pages" in res.json()["detail"]


def test_pdf_upload_rejects_a_corrupt_pdf():
    assert upload(b"%PDF-1.4 garbage garbage").status_code == 422
