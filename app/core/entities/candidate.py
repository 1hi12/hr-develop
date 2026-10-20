"""
Candidate domain entity.

This is the canonical definition. All other layers (infra, API) derive
their models from this or map to/from it. No external library imports
beyond pydantic.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional

from app.core.value_objects.seniority import SeniorityLevel
from app.core.value_objects.skill import Skill, ExtractedSkills


class Experience(BaseModel):
    company:          Optional[str] = None
    title:            Optional[str] = None
    start_date:       Optional[str] = None
    end_date:         Optional[str] = None
    duration_months:  Optional[int] = None
    description:      Optional[str] = None
    location:         Optional[str] = None


class Education(BaseModel):
    institution:     Optional[str] = None
    degree:          Optional[str] = None
    field_of_study:  Optional[str] = None
    graduation_year: Optional[int] = None


class Chunk(BaseModel):
    chunk_id:        str
    text:            str
    section:         str
    chunk_index:     int
    source_filename: str
    char_start:      int = 0
    char_end:        int = 0
    metadata:        dict = Field(default_factory=dict)


class EmbeddedChunk(BaseModel):
    chunk_id:        str
    text:            str
    section:         str
    chunk_index:     int
    source_filename: str
    embedding:       list[float]
    metadata:        dict = Field(default_factory=dict)


class Candidate(BaseModel):
    """
    Fully assembled candidate after CV extraction.
    candidate_id is set by the ingestion caller (UUID).
    """
    candidate_id:           str
    identity_id:            Optional[str] = None
    filename:               str
    full_name:              Optional[str] = None
    email:                  Optional[str] = None
    phone:                  Optional[str] = None
    location:               Optional[str] = None
    linkedin:               Optional[str] = None
    github:                 Optional[str] = None
    summary:                Optional[str] = None
    languages:              list[str] = Field(default_factory=list)
    skills:                 list[Skill] = Field(default_factory=list)
    experiences:            list[Experience] = Field(default_factory=list)
    education:              list[Education] = Field(default_factory=list)
    seniority_level:        SeniorityLevel = SeniorityLevel.UNKNOWN
    total_years_experience: Optional[float] = None
    raw_text:               Optional[str] = None
    chunks:                 list[Chunk] = Field(default_factory=list)
    embedded_chunks:        list[EmbeddedChunk] = Field(default_factory=list)
    extracted_skills:       Optional[ExtractedSkills] = None
    extraction_confidence:  Optional[float] = Field(None, ge=0.0, le=1.0)
