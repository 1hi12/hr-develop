"""CVFileRepository — CRUD + status transitions for cv_files table.

processing_status transitions:
    pending → processing → done
                        → failed
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select

from app.infrastructure.database.models import CVFileModel
from app.infrastructure.database.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


class CVFileRepository:

    async def create(
        self,
        candidate_id: str,
        filename: str,
        job_id: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        content_type: Optional[str] = None,
        source: str = "upload",
        tags: Optional[list] = None,
    ) -> CVFileModel:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                cv = CVFileModel(
                    candidate_id=candidate_id,
                    filename=filename,
                    job_id=job_id,
                    file_size_bytes=file_size_bytes,
                    content_type=content_type,
                    source=source,
                    processing_status="pending",
                    tags=tags or [],
                )
                session.add(cv)
                await session.flush()
                await session.refresh(cv)
            logger.info("[CVFileRepo] Created cv_file id=%s candidate=%s", cv.id, candidate_id[:8])
            return cv

    async def get_by_id(self, cv_id: int) -> Optional[CVFileModel]:
        async with AsyncSessionLocal() as session:
            return await session.get(CVFileModel, cv_id)

    async def get_by_candidate(self, candidate_id: str) -> list[CVFileModel]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(CVFileModel)
                .where(CVFileModel.candidate_id == candidate_id)
                .order_by(CVFileModel.created_at.desc())
            )
            return list(result.scalars())

    async def get_latest_for_candidate(self, candidate_id: str) -> Optional[CVFileModel]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(CVFileModel)
                .where(CVFileModel.candidate_id == candidate_id)
                .order_by(CVFileModel.created_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def mark_processing(self, cv_id: int) -> None:
        await self._set_status(cv_id, "processing")

    async def mark_done(self, cv_id: int, extracted_data: Optional[dict] = None) -> None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                cv = await session.get(CVFileModel, cv_id)
                if cv:
                    cv.processing_status = "done"
                    if extracted_data is not None:
                        cv.extracted_data = extracted_data

    async def mark_failed(self, cv_id: int, error_message: str) -> None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                cv = await session.get(CVFileModel, cv_id)
                if cv:
                    cv.processing_status = "failed"
                    cv.error_message = error_message

    async def list_by_status(
        self,
        status: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CVFileModel]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(CVFileModel)
                .where(CVFileModel.processing_status == status)
                .order_by(CVFileModel.created_at.asc())
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars())

    async def delete(self, cv_id: int) -> None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                cv = await session.get(CVFileModel, cv_id)
                if cv:
                    await session.delete(cv)

    async def _set_status(self, cv_id: int, status: str) -> None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                cv = await session.get(CVFileModel, cv_id)
                if cv:
                    cv.processing_status = status
