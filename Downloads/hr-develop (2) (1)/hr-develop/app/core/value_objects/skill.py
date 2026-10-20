from pydantic import BaseModel
from typing import Optional


class Skill(BaseModel):
    name: str
    category: Optional[str] = None
    level: Optional[str] = None
    years_of_experience: Optional[float] = None


class ExtractedSkills(BaseModel):
    technical:  list[str] = []
    frameworks: list[str] = []
    databases:  list[str] = []
    devops:     list[str] = []
    soft_skills: list[str] = []
    languages:  list[str] = []
    all_skills: list[str] = []
