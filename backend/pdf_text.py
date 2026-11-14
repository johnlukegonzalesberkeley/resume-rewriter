"""Turn a resume PDF into plain text the user can review before rewriting."""
import io
import re

import pdfplumber

MAX_PDF_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_PDF_PAGES = 5

BULLET_GLYPHS = "•●▪■◦○∙‣⁃·"

# Some PDFs have bullet glyphs the reader can't decode, and it prints them as "(cid:127)".
CID_AT_START = re.compile(r"^\(cid:\d+\)\s*")
CID_ANYWHERE = re.compile(r"\(cid:\d+\)")


class PdfProblem(Exception):
    """A PDF we can't use, with the HTTP status and a message that is safe to show."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _is_bullet(ch: str) -> bool:
    # Word-exported PDFs often use a private-use character for the bullet.
    return ch in BULLET_GLYPHS or 0xE000 <= ord(ch) <= 0xF8FF


def clean_resume_text(raw: str) -> str:
    """Tidy text pulled from a PDF: normalize bullets to '- ' and re-join wrapped lines."""
    lines: list[str] = []
    prev_was_bullet = False
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append("")
            prev_was_bullet = False
            continue
        if CID_AT_START.match(stripped):
            # An undecodable glyph at the start of a line is almost always a bullet.
            stripped = "- " + CID_AT_START.sub("", stripped)
        stripped = re.sub(r"[ \t]{2,}", " ", CID_ANYWHERE.sub("", stripped)).strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            lines.append(stripped)
            prev_was_bullet = True
        elif _is_bullet(stripped[0]):
            lines.append("- " + stripped[1:].lstrip())
            prev_was_bullet = True
        elif prev_was_bullet and stripped[0].islower():
            # A bullet that wrapped onto a second line: join it back together.
            lines[-1] = lines[-1] + " " + stripped
        else:
            lines.append(stripped)
            prev_was_bullet = False
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def extract_pdf_text(data: bytes) -> tuple[str, int]:
    """Read a PDF held in memory. Returns (cleaned text, page count) or raises PdfProblem."""
    if len(data) > MAX_PDF_BYTES:
        raise PdfProblem(413, "That PDF is over 5 MB.")
    if not data.startswith(b"%PDF-"):
        raise PdfProblem(422, "That file doesn't look like a PDF.")

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = len(pdf.pages)
            if pages > MAX_PDF_PAGES:
                raise PdfProblem(
                    422,
                    f"That PDF has {pages} pages. Please use one with {MAX_PDF_PAGES} or fewer.",
                )
            raw = "\n".join((page.extract_text() or "") for page in pdf.pages)
    except PdfProblem:
        raise
    except Exception:
        raise PdfProblem(
            422, "Could not read this PDF. It may be damaged or password-protected."
        )

    text = clean_resume_text(raw)
    if not text:
        raise PdfProblem(
            422,
            "No text found in this PDF. It may be a scan or an image, "
            "so please paste your resume text instead.",
        )
    return text, pages
