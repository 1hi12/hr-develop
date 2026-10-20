"""
Matching result domain entities.
"""

from pydantic import BaseModel, Field
from typing import Optional


class VectorSearchResult(BaseModel):
    candidate_id: str
    filename:     str
    score:        float
    excerpt:      str = ""
    job_id:       str = ""


class RankedCandidate(BaseModel):
    candidate_id:     str
    filename:         str
    score:            float
    relevance_score:  float
    similarity_score: float
    excerpt:          str = ""
    explanation:      dict = Field(default_factory=dict)
    job_id:           str = ""


class CandidatePresentation(BaseModel):
    rank:             int
    candidate_id:     str
    filename:         str
    score:            float
    relevance_score:  float
    similarity_score: float
    status:           str
    candidate_info:   dict
    presentation:     str
    excerpt:          str = ""


class MatchingResponse(BaseModel):
    candidates:       list[CandidatePresentation]
    recruiter_advice: str
    total_analyzed:   int = 0
