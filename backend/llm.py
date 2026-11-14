"""All LLM calls live here, so swapping providers is a one-file change."""
import json
import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

load_dotenv()

# Set MOCK_LLM=1 in .env to skip Gemini and return canned rewrites. Handy for building
# the UI without using your free-tier quota or hitting Google's overloads.
MOCK = os.getenv("MOCK_LLM") == "1"

# If this model name errors, pick a current Flash model listed in Google AI Studio
# and set GEMINI_MODEL in your .env file.
MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

# Retry only temporary server-side errors: 500 (server error) and 503 (overloaded).
# Do NOT retry 429 (rate limit): each retry counts against the same per-minute quota.
# Optional: set GEMINI_THINKING_BUDGET=0 in .env to switch off the model's internal
# "thinking" (it can use up the output budget and leave an empty reply).
_budget = os.getenv("GEMINI_THINKING_BUDGET")
THINKING_BUDGET = int(_budget) if _budget not in (None, "") else None

RETRY_CODES = {500, 503}
MAX_ATTEMPTS = 4

# timeout is in milliseconds: fail after 30s instead of hanging forever.
_client = None
if not MOCK:
    _client = genai.Client(
        api_key=os.getenv("GEMINI_API_KEY"),
        http_options=types.HttpOptions(timeout=30_000),
    )

MOCK_RESPONSE = json.dumps(
    {
        "rewrites": [
            {
                "original": "Helped customers at the register",
                "rewritten": "Assisted customers at the register",
                "reason": "Replaced 'helped' with a more precise active verb.",
                "missing_info": "About how many customers did you serve per shift?",
            },
            {
                "original": "Worked with team to prepare food",
                "rewritten": "Collaborated with team members to prepare food",
                "reason": "Used an active verb that reflects teamwork.",
                "missing_info": "About how many orders did your team prepare per shift?",
            },
            {
                "original": "Trained new hires",
                "rewritten": "Trained new hires",
                "reason": "Already clear and active, so left unchanged.",
                "missing_info": "How many new hires did you train?",
            },
            {
                "original": "Reduced page load time by 35% by compressing images",
                "rewritten": "Reduced page load time by 35% by compressing images",
                "reason": "Already strong and quantified, so left unchanged.",
                "missing_info": "",
            },
        ]
    }
)


def _parts(response) -> list:
    try:
        return response.candidates[0].content.parts or []
    except (AttributeError, IndexError, TypeError):
        return []


def _reply_text(response) -> str:
    """Text of the reply. Normally response.text, but some models put their whole answer
    in parts the SDK labels as 'thoughts', which response.text skips, so fall back to those."""
    try:
        text = response.text
    except Exception:
        text = None
    if text:
        return text
    return "\n".join(p.text for p in _parts(response) if getattr(p, "text", None))


class LLMTimeout(Exception):
    """The model didn't answer within the timeout."""


def _is_timeout(exc: Exception) -> bool:
    # Match by class name instead of importing an HTTP library: different versions of the
    # Gemini SDK use different ones (httpx, httpx2), and each has its own TimeoutException.
    return any("timeout" in cls.__name__.lower() for cls in type(exc).__mro__)


class EmptyReply(Exception):
    """The model returned no text. The message says why, when Gemini tells us."""


def _describe_empty(response) -> str:
    parts = []
    feedback = getattr(response, "prompt_feedback", None)
    if feedback and getattr(feedback, "block_reason", None):
        parts.append(f"prompt blocked: {feedback.block_reason}")
    candidates = getattr(response, "candidates", None) or []
    if candidates:
        parts.append(f"finish_reason: {candidates[0].finish_reason}")
    else:
        parts.append("no candidates returned")
    shape = [
        f"{type(p).__name__}(thought={getattr(p, 'thought', None)}, "
        f"chars={len(getattr(p, 'text', None) or '')})"
        for p in _parts(response)
    ]
    if shape:
        parts.append("parts: " + ", ".join(shape))
    usage = getattr(response, "usage_metadata", None)
    if usage:
        parts.append(
            f"thinking_tokens: {getattr(usage, 'thoughts_token_count', None)}, "
            f"output_tokens: {getattr(usage, 'candidates_token_count', None)}"
        )
    return "; ".join(parts)


def _generate(system: str, user: str, use_system: bool, use_json: bool):
    """One Gemini call. Some models don't support a system instruction or JSON mode,
    so both can be switched off; the system prompt is then folded into the message."""
    settings = {"max_output_tokens": 4096, "temperature": 0.3}
    if THINKING_BUDGET is not None:
        settings["thinking_config"] = types.ThinkingConfig(thinking_budget=THINKING_BUDGET)
    if use_system:
        settings["system_instruction"] = system
        contents = user
    else:
        contents = f"{system}\n\n{user}"
    if use_json:
        settings["response_mime_type"] = "application/json"
    return _client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(**settings),
    )


def call_llm(system: str, user: str, mock_response: str | None = None) -> str:
    """Send one prompt to Gemini and return the raw text of the reply.

    - Retries with increasing waits (2s, 4s, 8s) on 500/503 errors.
    - If the model rejects a system instruction or JSON mode (a 400 error), retries once
      without that feature, so models with fewer features still work.
    """
    if MOCK:
        time.sleep(1)  # pretend to think, so the loading state is visible
        return mock_response or MOCK_RESPONSE

    use_system, use_json = True, True
    attempt = 0
    while True:
        try:
            response = _generate(system, user, use_system, use_json)
            text = _reply_text(response)
            if not text:
                raise EmptyReply(_describe_empty(response))
            return text
        except errors.APIError as e:
            message = str(e).lower()

            # Model doesn't support this feature: switch it off and try again right away.
            if e.code == 400 and use_system and (
                "developer instruction" in message or "system instruction" in message
            ):
                use_system = False
                continue
            if e.code == 400 and use_json and (
                "json mode" in message or "mime type" in message
            ):
                use_json = False
                continue

            attempt += 1
            if e.code in RETRY_CODES and attempt < MAX_ATTEMPTS:
                time.sleep(2**attempt)
                continue
            raise
        except Exception as e:
            if _is_timeout(e):
                raise LLMTimeout(str(e)) from e
            raise
