import json
import os

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from google.genai import errors as genai_errors
from pydantic import ValidationError

from llm import MOCK, EmptyReply, call_llm
from mock import build_mock_regenerate, build_mock_rewrites
from models import BulletRewrite, RegenerateRequest, RewriteRequest, RewriteResponse
from pdf_text import MAX_PDF_BYTES, PdfProblem, extract_pdf_text
from prompts import (
    REGENERATE_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_regenerate_prompt,
    build_user_prompt,
)

load_dotenv()

app = FastAPI(title="Resume Rewriter API")

# Which frontend addresses may call this API from a browser. Set ALLOWED_ORIGINS to a
# comma-separated list when the frontend is deployed somewhere else.
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


def extract_json(text: str) -> dict:
    """Find the JSON answer in the model's reply.

    Tries each '{' as a possible start, so it still works when the reply has stray text
    or reasoning with braces before the real JSON. Objects nested inside an object that
    already parsed are skipped. Prefers the LAST object that looks like our answer,
    since a final answer comes after any drafts.
    """
    decoder = json.JSONDecoder()
    found = []
    i = 0
    while True:
        i = text.find("{", i)
        if i == -1:
            break
        try:
            obj, length = decoder.raw_decode(text[i:])
        except json.JSONDecodeError:
            i += 1
            continue
        if isinstance(obj, dict):
            found.append(obj)
        i += length  # skip past this object, so nested objects aren't picked up
    if not found:
        raise ValueError("No JSON object found in model output")
    for key in ("rewrites", "rewritten"):
        for obj in reversed(found):
            if key in obj:
                return obj
    return found[-1]


def ask_llm(system: str, user: str, mock_response: str | None = None) -> dict:
    """Call the model and return its reply as a dict, turning failures into HTTP errors."""
    try:
        raw = call_llm(system, user, mock_response)
    except EmptyReply as e:
        print(f"[empty reply] {e}")
        raise HTTPException(
            status_code=502,
            detail=f"The model returned an empty reply ({e}). Try again, or set "
            "GEMINI_THINKING_BUDGET=0 in backend/.env and restart the backend.",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Gemini took too long to respond (over 30 seconds). Try again in a moment.",
        )
    except genai_errors.APIError as e:
        if e.code == 429:
            raise HTTPException(
                status_code=429,
                detail="Gemini free-tier rate limit reached (about 5 requests per minute). "
                "Wait a minute and try again.",
            )
        raise HTTPException(status_code=502, detail=f"Gemini API error: {e}")

    try:
        return extract_json(raw)
    except (ValueError, json.JSONDecodeError) as e:
        # Show what the model actually said, to make parse failures easy to debug.
        preview = raw[:300] if raw else "(empty reply)"
        print(f"[parse error] model output was: {raw[:1000]!r}")
        raise HTTPException(
            status_code=502,
            detail=f"Could not parse model output: {e}. Model said: {preview}",
        )


@app.get("/health")
def health():
    # "mock" lets the frontend show a demo-mode banner instead of passing off
    # placeholder text as real AI output.
    return {"status": "ok", "mock": MOCK}


@app.post("/rewrite", response_model=RewriteResponse)
def rewrite(req: RewriteRequest):
    data = ask_llm(
        SYSTEM_PROMPT,
        build_user_prompt(req.resume_text, req.job_description),
        mock_response=build_mock_rewrites(req.resume_text),
    )
    try:
        return RewriteResponse(**data)
    except ValidationError as e:
        raise HTTPException(status_code=502, detail=f"Could not parse model output: {e}")


@app.post("/regenerate", response_model=BulletRewrite)
def regenerate(req: RegenerateRequest):
    """Rewrite one bullet using a real detail the user typed in."""
    data = ask_llm(
        REGENERATE_SYSTEM_PROMPT,
        build_regenerate_prompt(req.original, req.user_detail, req.job_description),
        mock_response=build_mock_regenerate(req.original, req.user_detail),
    )
    # Tolerate the model wrapping its answer in {"rewrites": [...]} anyway.
    if "rewrites" in data and data["rewrites"]:
        data = data["rewrites"][0]
    try:
        result = BulletRewrite(**data)
    except ValidationError as e:
        raise HTTPException(status_code=502, detail=f"Could not parse model output: {e}")
    result.original = req.original  # never let the model change the original text
    return result


@app.post("/extract-pdf")
def extract_pdf(file: UploadFile = File(...)):
    """Read a resume PDF in memory (nothing is saved) and return its text."""
    data = file.file.read(MAX_PDF_BYTES + 1)
    try:
        text, pages = extract_pdf_text(data)
    except PdfProblem as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return {"text": text, "pages": pages}
