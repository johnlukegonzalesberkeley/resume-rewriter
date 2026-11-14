from pydantic import BaseModel, Field


class RewriteRequest(BaseModel):
    resume_text: str = Field(..., min_length=1, max_length=30_000, description="Raw resume text")
    job_description: str = Field(
        ..., min_length=1, max_length=15_000, description="Target job posting"
    )


class BulletRewrite(BaseModel):
    original: str
    rewritten: str
    reason: str
    missing_info: str = ""  # a question for the user when a real metric is missing


class RewriteResponse(BaseModel):
    rewrites: list[BulletRewrite]


class RegenerateRequest(BaseModel):
    original: str = Field(..., min_length=1, max_length=1_000, description="The original bullet")
    user_detail: str = Field(
        ..., min_length=1, max_length=500, description="A real fact the user added"
    )
    job_description: str = Field(
        ..., min_length=1, max_length=15_000, description="Target job posting"
    )
