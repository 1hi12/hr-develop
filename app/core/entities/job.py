"""
JobDescription domain entity.
"""

from pydantic import BaseModel, Field
from typing import Optional


class JobDescription(BaseModel):
    job_id:          Optional[str] = None
    title:           Optional[str] = None
    text:            str
    description:     Optional[str] = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    experience_years: Optional[float] = None
    location:        Optional[str] = None
