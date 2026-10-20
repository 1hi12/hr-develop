"""AIMatchRepository — CRUD for ai_matches table."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select, delete

from app.infrastructure.database.models import AIMatchModel
from app.infrastructure.database.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


class AIMatchRepository:

    async def save(
        self,
        candidate_id: str,
        job_id: str,
        score_skills: Optional[float],
        score_experience: Optional[float],
        score_education: Optional[float],
        score_other: Optional[float],
        total_score: Optional[float],
        rank_position: Optional[int] = None,
        matched_skills: Optional[list] = None,
        missing_skills: Optional[list] = None,
        ai_payload: Optional[dict] = None,
        llm_justification: Optional[str] = None,
    ) -> AIMatchModel:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                match = AIMatchModel(
                    candidate_id=candidate_id,
                    job_id=job_id,
                    score_skills=score_skills,
                    score_experience=score_experience,
                    score_education=score_education,
                    score_other=score_other,
                    total_score=total_score,
                    rank_position=rank_position,
                    matched_skills=matched_skills or [],
                    missing_skills=missing_skills or [],
                    ai_payload=ai_payload,
                    llm_justification=llm_justification,
                )
                session.add(match)
            await session.refresh(match)
            return match

    async def get_by_job(
        self,
        job_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AIMatchModel]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(AIMatchModel)
                .where(AIMatchModel.job_id == job_id)
                .order_by(AIMatchModel.total_score.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars())

    async def get_by_candidate_and_job(
        self,
        candidate_id: str,
        job_id: str,
    ) -> Optional[AIMatchModel]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(AIMatchModel)
                .where(
                    AIMatchModel.candidate_id == candidate_id,
                    AIMatchModel.job_id == job_id,
                )
                .order_by(AIMatchModel.created_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def delete_for_job(self, job_id: str) -> None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    delete(AIMatchModel).where(AIMatchModel.job_id == job_id)
                )
        logger.info("[AIMatchRepo] Cleared matches for job %s", job_id)
