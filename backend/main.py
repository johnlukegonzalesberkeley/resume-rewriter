import json
import httpx

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google.genai import errors as genai_errors
from pydantic import ValidationError

from llm import call_llm
from models import RewriteRequest, RewriteResponse
from prompts import SYSTEM_PROMPT, build_user_prompt

app = FastAPI(title="Resume Rewriter API")

# Lets the React dev server (a different origin) call this API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def extract_json(text: str) -> dict:
    """Pull the JSON object out of the model's reply, even if it adds stray text."""
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in model output")
    return json.loads(text[start : end + 1])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/rewrite", response_model=RewriteResponse)
def rewrite(req: RewriteRequest):
    try:
        raw = call_llm(SYSTEM_PROMPT, build_user_prompt(req.resume_text, req.job_description))
    except genai_errors.APIError as e:
        raise HTTPException(status_code=502, detail=f"Gemini API error: {e}")

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Gemini took too long to respond (over 30 seconds). Try again in a moment.",
        )
    try:
        return RewriteResponse(**extract_json(raw))
    except (ValueError, json.JSONDecodeError, ValidationError) as e:
        raise HTTPException(status_code=502, detail=f"Could not parse model output: {e}")