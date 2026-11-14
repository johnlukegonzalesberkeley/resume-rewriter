from pydantic import BaseModel, Field


class RewriteRequest(BaseModel):
    resume_text: str = Field(..., min_length=1, description="Raw resume text")
    job_description: str = Field(..., min_length=1, description="Target job posting")


class BulletRewrite(BaseModel):
    original: str
    rewritten: str
    reason: str
    missing_info: str = ""  # a question for the user when a real metric is missing


class RewriteResponse(BaseModel):
    rewrites: list[BulletRewrite]