from pydantic import BaseModel


class IngestCVRequest(BaseModel):
    candidate_id: str
    filename:     str
    file_bytes:   bytes
    job_id:       str = ""

    model_config = {"arbitrary_types_allowed": True}


class IngestCVResult(BaseModel):
    candidate_id: str
    filename:     str
    chunks_count: int
    skills_count: int
    confidence:   float
    status:       str = "success"
    full_name:    str = ""
    email:        str = ""
    seniority:    str = ""
    years_exp:    float = 0.0
