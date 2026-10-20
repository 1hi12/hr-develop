"""JobPostingRepository — CRUD for job_postings table."""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy import select, func

from app.infrastructure.database.models import JobPostingModel
from app.infrastructure.database.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


class JobPostingRepository:

    async def create(
        self,
        title: str,
        description: Optional[str] = None,
        department: Optional[str] = None,
        location: Optional[str] = None,
        employment_type: str = "full-time",
        required_skills: Optional[list] = None,
        preferred_skills: Optional[list] = None,
        min_years_experience: Optional[float] = None,
        max_years_experience: Optional[float] = None,
        seniority_level: Optional[str] = None,
        created_by: Optional[str] = None,
        nb_positions: Optional[int] = None,
    ) -> JobPostingModel:
        job_id = str(uuid.uuid4())
        async with AsyncSessionLocal() as session:
            async with session.begin():
                job = JobPostingModel(
                    job_id=job_id,
                    title=title,
                    description=description,
                    department=department,
                    location=location,
                    employment_type=employment_type,
                    required_skills=required_skills or [],
                    preferred_skills=preferred_skills or [],
                    min_years_experience=min_years_experience,
                    max_years_experience=max_years_experience,
                    seniority_level=seniority_level,
                    status="active",
                    created_by=created_by,
                    nb_positions=nb_positions,
                )
                session.add(job)
            await session.refresh(job)
            return job

    async def get_by_id(self, job_id: str) -> Optional[JobPostingModel]:
        async with AsyncSessionLocal() as session:
            return await session.get(JobPostingModel, job_id)

    async def find_by_title(self, title: str) -> Optional[JobPostingModel]:
        """Return the first non-archived job whose normalised title matches."""
        normalized = title.strip().lower()
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(JobPostingModel)
                .where(
                    func.lower(func.trim(JobPostingModel.title)) == normalized,
                    JobPostingModel.status != "archived",
                )
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def find_by_pdf_hash(self, pdf_hash: str) -> Optional[JobPostingModel]:
        """Return a job that was created from a PDF with this SHA-256 hash."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(JobPostingModel)
                .where(
                    JobPostingModel.pdf_hash == pdf_hash,
                    JobPostingModel.status != "archived",
                )
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def list_all(
        self,
        status: Optional[str] = None,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[JobPostingModel]:
        async with AsyncSessionLocal() as session:
            query = select(JobPostingModel).order_by(JobPostingModel.created_at.desc())
            if status:
                query = query.where(JobPostingModel.status == status)
            elif not include_archived:
                query = query.where(JobPostingModel.status != "archived")
            result = await session.execute(query.limit(limit).offset(offset))
            return list(result.scalars())

    async def update_status(self, job_id: str, status: str) -> Optional[JobPostingModel]:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                job = await session.get(JobPostingModel, job_id)
                if job:
                    job.status = status
            if job:
                await session.refresh(job)
            return job

    async def update(
        self,
        job_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        department: Optional[str] = None,
        location: Optional[str] = None,
        employment_type: Optional[str] = None,
        required_skills: Optional[list] = None,
        preferred_skills: Optional[list] = None,
        min_years_experience: Optional[float] = None,
        max_years_experience: Optional[float] = None,
        seniority_level: Optional[str] = None,
        nb_positions: Optional[int] = None,
    ) -> Optional[JobPostingModel]:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                job = await session.get(JobPostingModel, job_id)
                if not job:
                    return None
                if title is not None:
                    job.title = title
                if description is not None:
                    job.description = description
                if department is not None:
                    job.department = department
                if location is not None:
                    job.location = location
                if employment_type is not None:
                    job.employment_type = employment_type
                if required_skills is not None:
                    job.required_skills = required_skills
                if preferred_skills is not None:
                    job.preferred_skills = preferred_skills
                if min_years_experience is not None:
                    job.min_years_experience = min_years_experience
                if max_years_experience is not None:
                    job.max_years_experience = max_years_experience
                if seniority_level is not None:
                    job.seniority_level = seniority_level
                if nb_positions is not None:
                    job.nb_positions = nb_positions
            if job:
                await session.refresh(job)
            return job

    async def delete(self, job_id: str) -> bool:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                job = await session.get(JobPostingModel, job_id)
                if job:
                    await session.delete(job)
                    logger.info("[JobPostingRepo] Deleted job %s", job_id)
                    return True
        return False
