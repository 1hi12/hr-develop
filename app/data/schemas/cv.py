from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class SeniorityLevel(str, Enum):
    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    PRINCIPAL = "principal"
    UNKNOWN = "unknown"


class Skill(BaseModel):
    name: str
    category: Optional[str] = None
    level: Optional[str] = None
    years_of_experience: Optional[float] = None


class Experience(BaseModel):
    company: Optional[str] = None
    title: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    duration_months: Optional[int] = None
    description: Optional[str] = None
    location: Optional[str] = None


class Education(BaseModel):
    institution: Optional[str] = None
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    graduation_year: Optional[int] = None


class Chunk(BaseModel):
    chunk_id: str
    text: str
    section: str
    chunk_index: int
    source_filename: str


class EmbeddedChunk(BaseModel):
    chunk_id: str
    text: str
    section: str
    chunk_index: int
    source_filename: str
    embedding: list[float]
    metadata: dict = Field(default_factory=dict)


class ExtractedSkills(BaseModel):
    technical: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    databases: list[str] = Field(default_factory=list)
    devops: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    all_skills: list[str] = Field(default_factory=list)


class CVExtracted(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    summary: Optional[str] = None
    languages: list[str] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    experiences: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    seniority_level: SeniorityLevel = SeniorityLevel.UNKNOWN
    total_years_experience: Optional[float] = None
    raw_text: Optional[str] = None
    chunks: list[Chunk] = Field(default_factory=list)
    embedded_chunks: list[EmbeddedChunk] = Field(default_factory=list)
    extracted_skills: Optional[ExtractedSkills] = None
    extraction_confidence: Optional[float] = None


class SearchResult(BaseModel):
    chunk_id: str
    text: str
    section: str
    filename: str
    score: float
    matched_skills: list[str] = Field(default_factory=list)
    chunk_index: int = 0


class RankedResult(BaseModel):
    filename: str
    text: str
    section: str
    original_score: float
    rerank_score: float
    final_score: float
    justification: str
    matched_skills: list[str] = Field(default_factory=list)


class CandidatePresentation(BaseModel):
    filename: str
    rank: int
    match_score: float
    match_percentage: int
    profile_summary: str
    key_strengths: list[str]
    matched_skills: list[str]
    missing_skills: list[str]
    recommendation: str
    raw_text_excerpt: str


class MatchingResponse(BaseModel):
    job_description_summary: str
    total_candidates_analyzed: int
    top_candidates: list[CandidatePresentation]
    recruiter_advice: str


class JobDescription(BaseModel):
    title: Optional[str] = None
    text: str
    description: Optional[str] = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    experience_years: Optional[float] = None
    location: Optional[str] = None
