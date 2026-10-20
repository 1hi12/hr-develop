"""
/api/v1/cvs — CV ingestion, status, and deletion endpoints.
"""

import uuid
import logging
from typing import Optional

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.config.settings import settings
from app.infrastructure.vector_store.milvus_store import MilvusVectorStore
from app.infrastructure.repositories.candidate_repo import CandidateRepository
from app.infrastructure.repositories.cv_file_repo import CVFileRepository
from app.api.dependencies import get_vector_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cvs", tags=["CVs"])


async def get_arq_pool() -> ArqRedis:
    return await create_pool(RedisSettings.from_dsn(settings.redis_url))


def get_candidate_repo() -> CandidateRepository:
    return CandidateRepository()


@router.post("/upload")
async def upload_cv(
    file:         UploadFile = File(...),
    job_id:       Optional[str] = Form(None),
    candidate_id: Optional[str] = Form(None),
    arq: ArqRedis = Depends(get_arq_pool),
):
    """
    Enqueue CV ingestion as a background task.
    Returns immediately with candidate_id and job_id for status polling.
    """
    file_bytes  = await file.read()
    resolved_id = candidate_id or str(uuid.uuid4())

    try:
        # 1️⃣ PREMIER - créer le candidat dans PostgreSQL
        from app.core.entities.candidate import Candidate
        from app.core.value_objects.seniority import SeniorityLevel
        candidate_repo = CandidateRepository()
        await candidate_repo.save(Candidate(
            candidate_id=resolved_id,
            filename=file.filename or "unknown",
            seniority_level=SeniorityLevel.UNKNOWN,
        ))

        # 2️⃣ DEUXIÈME - créer cv_files
        cv_repo = CVFileRepository()
        await cv_repo.create(
            candidate_id=resolved_id,
            filename=file.filename or "unknown",
            job_id=job_id or None,
            file_size_bytes=len(file_bytes),
            content_type=file.content_type,
            source="upload",
        )

        # 3️⃣ TROISIÈME - envoyer le job ARQ
        job = await arq.enqueue_job(
            "task_ingest_cv",
            resolved_id,
            file_bytes,
            file.filename or "unknown",
            job_id or "",
        )
        return {
            "success"      : True,
            "candidate_id" : resolved_id,
            "job_id"       : job.job_id,
            "status"       : "queued",
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception("Upload enqueue error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/status/{candidate_id}")
async def get_cv_status(
    candidate_id: str,
    job_id:       Optional[str] = None,
    arq: ArqRedis = Depends(get_arq_pool),
    store: MilvusVectorStore = Depends(get_vector_store),
):
    """
    Returns accurate processing status:
      queued | processing | indexed | failed | not_found
    """
    try:
        if job_id:
            job = await arq.job(job_id)
            if job:
                job_status = await job.status()
                status_map = {
                    "queued"     : "queued",
                    "in_progress": "processing",
                    "deferred"   : "queued",
                }
                mapped = status_map.get(str(job_status))
                if mapped:
                    return {
                        "success"      : True,
                        "candidate_id" : candidate_id,
                        "status"       : mapped,
                    }

        exists = await store.candidate_exists(candidate_id)
        return {
            "success"      : True,
            "candidate_id" : candidate_id,
            "status"       : "indexed" if exists else "not_found",
        }
    except Exception as e:
        logger.exception("Status check error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{candidate_id}")
async def delete_candidate(
    candidate_id: str,
    store: MilvusVectorStore = Depends(get_vector_store),
    repo:  CandidateRepository = Depends(get_candidate_repo),
):
    """
    GDPR delete: removes all candidate data from both Milvus and Postgres.
    """
    try:
        await store.delete_candidate(candidate_id)
        await repo.delete(candidate_id)
        return {"success": True, "candidate_id": candidate_id, "status": "deleted"}
    except Exception as e:
        logger.exception("Delete error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
