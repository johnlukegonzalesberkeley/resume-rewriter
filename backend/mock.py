"""Placeholder responses for demo mode (MOCK_LLM=1). No AI is involved.

They are built from what the user pasted, so the UI behaves realistically: bullets
match the input, some get a changed first word, and bullets without a number get a
follow-up question.
"""
import json
import re

STRONGER_VERBS = {
    "helped": "Assisted",
    "worked": "Collaborated",
    "did": "Completed",
    "made": "Prepared",
}


def extract_bullets(resume_text: str, limit: int = 8) -> list[str]:
    lines = [ln.strip() for ln in resume_text.splitlines() if ln.strip()]
    dashed = [ln[2:].strip() for ln in lines if ln.startswith(("- ", "• "))]
    # No bullet markers? Treat longer lines as bullets, which skips short headings.
    bullets = dashed or [ln for ln in lines if len(ln.split()) >= 4]
    return bullets[:limit]


def build_mock_rewrites(resume_text: str) -> str | None:
    """JSON for /rewrite, or None if no bullets were found (the caller falls back)."""
    bullets = extract_bullets(resume_text)
    if not bullets:
        return None
    rewrites = []
    for bullet in bullets:
        first, _, rest = bullet.partition(" ")
        new_first = STRONGER_VERBS.get(first.lower())
        rewritten = f"{new_first} {rest}".strip() if new_first else bullet
        has_number = bool(re.search(r"\d", bullet))
        rewrites.append(
            {
                "original": bullet,
                "rewritten": rewritten,
                "reason": "Demo mode: placeholder rewrite, no AI was used.",
                "missing_info": (
                    "" if has_number else "Can you add a real number or detail for this bullet?"
                ),
            }
        )
    return json.dumps({"rewrites": rewrites})


def build_mock_regenerate(original: str, user_detail: str) -> str:
    return json.dumps(
        {
            "original": original,
            "rewritten": f"{original} ({user_detail})",
            "reason": "Demo mode: appended your detail to the original bullet, no AI was used.",
            "missing_info": "",
        }
    )
