from pydantic import BaseModel, Field


class MatchRequest(BaseModel):
    job_description: str
    required_skills: list[str] = []
    top_k:           int   = Field(default=5, ge=1)
    min_score:       float = Field(default=0.3, ge=0.0, le=1.0)
    use_reranking:   bool  = True


class MatchResponse(BaseModel):
    candidates:       list[dict]
    recruiter_advice: str
