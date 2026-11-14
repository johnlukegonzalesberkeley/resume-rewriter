"""All LLM calls live here, so swapping providers is a one-file change."""
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# If this model name errors, pick a current Flash model listed in Google AI Studio
# and set GEMINI_MODEL in your .env file.
MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def call_llm(system: str, user: str) -> str:
    """Send one prompt to Gemini and return the raw text of the reply."""
    response = _client.models.generate_content(
        model=MODEL,
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=2000,
            temperature=0.3,
            response_mime_type="application/json",  # ask for JSON output
        ),
    )
    return response.text or ""
