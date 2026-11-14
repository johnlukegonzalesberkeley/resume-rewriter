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


def call_llm(system: str, user: str) -> str:
    """Send one prompt to Gemini and return the raw text of the reply.

    Retries a few times with increasing waits (2s, 4s, 8s) on 500/503 errors.
    """
    if MOCK:
        time.sleep(1)  # pretend to think, so the loading state is visible
        return MOCK_RESPONSE

    for attempt in range(MAX_ATTEMPTS):
        try:
            response = _client.models.generate_content(
                model=MODEL,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    max_output_tokens=2000,
                    temperature=0.3,
                    response_mime_type="application/json",
                ),
            )
            return response.text or ""
        except errors.APIError as e:
            last_try = attempt == MAX_ATTEMPTS - 1
            if e.code in RETRY_CODES and not last_try:
                time.sleep(2 ** (attempt + 1))
                continue
            raise
    return ""
