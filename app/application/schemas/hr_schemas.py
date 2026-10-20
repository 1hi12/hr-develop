"""
Pydantic API schemas for all HR entities.
These are request/response models — separate from SQLAlchemy ORM models
and from core domain entities.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Shared ─────────────────────────────────────────────────────────────────

class ScoringWeights(BaseModel):
    skills:     float = Field(0.4, ge=0.0, le=1.0)
    experience: float = Field(0.3, ge=0.0, le=1.0)
    education:  float = Field(0.2, ge=0.0, le=1.0)
    other:      float = Field(0.1, ge=0.0, le=1.0)

    @field_validator("other")
    @classmethod
    def weights_sum_to_one(cls, v: float, info) -> float:
        total = sum([
            info.data.get("skills",     0.0),
            info.data.get("experience", 0.0),
            info.data.get("education",  0.0),
            v,
        ])
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Scoring weights must sum to 1.0, got {total:.4f}")
        return v


# ── RH Users ───────────────────────────────────────────────────────────────

class RHUserCreate(BaseModel):
    email:    EmailStr
    password: str = Field(min_length=8)
    full_name: Optional[str] = None
    role: str = "recruiter"

    @field_validator("role")
    @classmethod
    def valid_role(cls, v: str) -> str:
        if v not in ("admin", "recruiter", "viewer"):
            raise ValueError("role must be admin, recruiter, or viewer")
        return v


class RHUserResponse(BaseModel):
    id:         int
    email:      str
    full_name:  Optional[str]
    role:       str
    is_active:  bool
    created_at: datetime

    model_config = {"from_attributes": True}


class RHUserUpdatePassword(BaseModel):
    current_password: str
    new_password:     str = Field(min_length=8)


# ── Job Postings ───────────────────────────────────────────────────────────

class JobPostingCreate(BaseModel):
    title:            str = Field(min_length=1, max_length=255)
    department:       Optional[str] = None
    location:         Optional[str] = None
    description:      Optional[str] = None
    required_skills:  list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    scoring_weights:  ScoringWeights = Field(default_factory=ScoringWeights)


class JobPostingUpdate(BaseModel):
    title:            Optional[str] = None
    department:       Optional[str] = None
    location:         Optional[str] = None
    description:      Optional[str] = None
    required_skills:  Optional[list[str]] = None
    preferred_skills: Optional[list[str]] = None
    scoring_weights:  Optional[ScoringWeights] = None
    status:           Optional[str] = None

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("open", "closed", "draft", "archived"):
            raise ValueError("status must be open, closed, draft, or archived")
        return v


class JobPostingResponse(BaseModel):
    job_id:           str
    title:            str
    department:       Optional[str]
    location:         Optional[str]
    description:      Optional[str]
    required_skills:  list[str]
    preferred_skills: list[str]
    scoring_weights:  dict
    status:           str
    created_by:       Optional[int]
    created_at:       datetime
    updated_at:       Optional[datetime]

    model_config = {"from_attributes": True}


# ── CV Files ───────────────────────────────────────────────────────────────

class CVFileResponse(BaseModel):
    id:                int
    candidate_id:      str
    job_id:            Optional[str]
    filename:          str
    file_size_bytes:   Optional[int]
    content_type:      Optional[str]
    source:            str
    processing_status: str
    error_message:     Optional[str]
    tags:              list[str]
    created_at:        datetime
    updated_at:        Optional[datetime]

    model_config = {"from_attributes": True}


class CVFileStatusUpdate(BaseModel):
    processing_status: str
    error_message:     Optional[str] = None

    @field_validator("processing_status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        if v not in ("pending", "processing", "done", "failed"):
            raise ValueError("processing_status must be pending, processing, done, or failed")
        return v


# ── AI Matches ─────────────────────────────────────────────────────────────

class AIMatchResponse(BaseModel):
    id:               int
    candidate_id:     str
    job_id:           str
    score_skills:     Optional[float]
    score_experience: Optional[float]
    score_education:  Optional[float]
    score_other:      Optional[float]
    total_score:      Optional[float]
    rank_position:    Optional[int]
    matched_skills:   list[str]
    missing_skills:   list[str]
    llm_justification:Optional[str]
    created_at:       datetime

    model_config = {"from_attributes": True}


class AIMatchCreate(BaseModel):
    candidate_id:      str
    job_id:            str
    score_skills:      Optional[float] = None
    score_experience:  Optional[float] = None
    score_education:   Optional[float] = None
    score_other:       Optional[float] = None
    total_score:       Optional[float] = None
    rank_position:     Optional[int]   = None
    matched_skills:    list[str]       = Field(default_factory=list)
    missing_skills:    list[str]       = Field(default_factory=list)
    ai_payload:        Optional[dict]  = None
    llm_justification: Optional[str]  = None


# ── Recruitment Pipeline ───────────────────────────────────────────────────

class PipelineCreate(BaseModel):
    candidate_id: str
    job_id:       str
    stage:        str = "sourced"
    notes:        Optional[str] = None
    assigned_to:  Optional[int] = None

    @field_validator("stage")
    @classmethod
    def valid_stage(cls, v: str) -> str:
        valid = {"sourced","screening","technical","hr_interview","offer","hired","rejected"}
        if v not in valid:
            raise ValueError(f"stage must be one of {valid}")
        return v


class PipelineAdvance(BaseModel):
    stage: str
    notes: Optional[str] = None

    @field_validator("stage")
    @classmethod
    def valid_stage(cls, v: str) -> str:
        valid = {"sourced","screening","technical","hr_interview","offer","hired","rejected"}
        if v not in valid:
            raise ValueError(f"stage must be one of {valid}")
        return v


class PipelineResponse(BaseModel):
    id:           int
    candidate_id: str
    job_id:       str
    stage:        str
    notes:        Optional[str]
    assigned_to:  Optional[int]
    created_at:   datetime
    updated_at:   Optional[datetime]

    model_config = {"from_attributes": True}


# ── Interviews ─────────────────────────────────────────────────────────────

class InterviewCreate(BaseModel):
    pipeline_id:    int
    candidate_id:   str
    job_id:         Optional[str] = None
    interviewer_id: Optional[int] = None
    scheduled_at:   datetime
    interview_type: str = "technical"
    location_url:   Optional[str] = None

    @field_validator("interview_type")
    @classmethod
    def valid_type(cls, v: str) -> str:
        valid = {"technical","hr","cultural","pair_programming","case_study"}
        if v not in valid:
            raise ValueError(f"interview_type must be one of {valid}")
        return v


class InterviewFeedback(BaseModel):
    rating:   int = Field(ge=1, le=5)
    feedback: Optional[str] = None
    status:   str = "completed"

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        if v not in ("scheduled","completed","cancelled","no_show"):
            raise ValueError("invalid interview status")
        return v


class InterviewResponse(BaseModel):
    id:             int
    pipeline_id:    int
    candidate_id:   str
    job_id:         Optional[str]
    interviewer_id: Optional[int]
    scheduled_at:   datetime
    interview_type: str
    location_url:   Optional[str]
    rating:         Optional[int]
    feedback:       Optional[str]
    status:         str
    created_at:     datetime
    updated_at:     Optional[datetime]

    model_config = {"from_attributes": True}


# ── Notifications ──────────────────────────────────────────────────────────

class NotificationResponse(BaseModel):
    id:         int
    user_id:    int
    title:      str
    body:       Optional[str]
    link:       Optional[str]
    is_read:    bool
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationCreate(BaseModel):
    user_id: int
    title:   str = Field(min_length=1, max_length=255)
    body:    Optional[str] = None
    link:    Optional[str] = None


# ── Emails ─────────────────────────────────────────────────────────────────

class EmailCreate(BaseModel):
    recipient:    EmailStr
    subject:      str = Field(min_length=1, max_length=500)
    body_html:    Optional[str] = None
    body_text:    Optional[str] = None
    candidate_id: Optional[str] = None
    job_id:       Optional[str] = None


class EmailResponse(BaseModel):
    id:           int
    recipient:    str
    subject:      str
    status:       str
    error_detail: Optional[str]
    sent_at:      Optional[datetime]
    candidate_id: Optional[str]
    job_id:       Optional[str]
    created_at:   datetime

    model_config = {"from_attributes": True}
