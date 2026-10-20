"""RecruitmentPipelineRepository — CRUD + stage transitions."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select

from app.infrastructure.database.models import RecruitmentPipelineModel
from app.infrastructure.database.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

PIPELINE_STAGES = [
    "sourced", "screening", "technical", "hr_interview", "offer", "hired", "rejected"
]


class RecruitmentPipelineRepository:

    async def create(
        self,
        candidate_id: str,
        job_id: str,
        stage: str = "sourced",
        notes: Optional[str] = None,
        assigned_to: Optional[int] = None,
    ) -> RecruitmentPipelineModel:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                entry = RecruitmentPipelineModel(
                    candidate_id=candidate_id,
                    job_id=job_id,
                    stage=stage,
                    notes=notes,
                    assigned_to=assigned_to,
                )
                session.add(entry)
            await session.refresh(entry)
            logger.info(
                "[PipelineRepo] Created entry id=%s candidate=%s stage=%s",
                entry.id, candidate_id[:8], stage,
            )
            return entry

    async def get_by_id(self, entry_id: int) -> Optional[RecruitmentPipelineModel]:
        async with AsyncSessionLocal() as session:
            return await session.get(RecruitmentPipelineModel, entry_id)

    async def get_by_candidate_and_job(
        self,
        candidate_id: str,
        job_id: str,
    ) -> Optional[RecruitmentPipelineModel]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(RecruitmentPipelineModel)
                .where(
                    RecruitmentPipelineModel.candidate_id == candidate_id,
                    RecruitmentPipelineModel.job_id == job_id,
                )
                .order_by(RecruitmentPipelineModel.created_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def get_by_job(
        self,
        job_id: str,
        stage: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RecruitmentPipelineModel]:
        async with AsyncSessionLocal() as session:
            q = select(RecruitmentPipelineModel).where(
                RecruitmentPipelineModel.job_id == job_id
            )
            if stage:
                q = q.where(RecruitmentPipelineModel.stage == stage)
            q = q.order_by(RecruitmentPipelineModel.updated_at.desc()).limit(limit).offset(offset)
            result = await session.execute(q)
            return list(result.scalars())

    async def advance_stage(self, entry_id: int, new_stage: str, notes: Optional[str] = None) -> None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                entry = await session.get(RecruitmentPipelineModel, entry_id)
                if entry:
                    entry.stage = new_stage
                    if notes is not None:
                        entry.notes = notes

    async def assign(self, entry_id: int, user_id: int) -> None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                entry = await session.get(RecruitmentPipelineModel, entry_id)
                if entry:
                    entry.assigned_to = user_id
