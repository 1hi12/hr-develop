"""
ingest_task.py
==============
ARQ background task for CV ingestion.
Decouples CV processing from the HTTP request lifecycle:
  - HTTP returns immediately with job_id + candidate_id
  - This task runs in a separate ARQ worker process
  - Retries are handled automatically by ARQ on failure
"""

import logging

from app.application.dtos.ingest_dto import IngestCVRequest
from app.api.dependencies import get_ingest_use_case
from app.infrastructure.repositories.cv_file_repo import CVFileRepository

logger = logging.getLogger(__name__)


async def task_ingest_cv(
    ctx: dict,
    candidate_id: str,
    file_bytes: bytes,
    filename: str,
    job_id: str = "",
) -> dict:
    """
    ARQ task function.
    ctx is injected by the ARQ worker (contains startup state if needed).

    Lifecycle written to cv_files:
      pending  (created at upload time, in cvs.py)
      processing  ← set here before use case runs
      done        ← set here on success
      failed      ← set here on exception
    """
    logger.info(
        "[task_ingest_cv] Starting: candidate_id=%s | file=%s",
        candidate_id[:8], filename,
    )

    cv_repo = CVFileRepository()

    # Find the cv_files record created at upload time
    cv_file = await cv_repo.get_latest_for_candidate(candidate_id)
    cv_file_id = cv_file.id if cv_file else None

    if cv_file_id:
        await cv_repo.mark_processing(cv_file_id)
    
    # NOTE: WebSocket broadcasts disabled for synchronous uploads (/api/v1/candidates/upload)
    # The HTTP response already handles notifications. WebSocket is only needed for true async bulk processing.

    use_case = get_ingest_use_case()

    try:
        result = await use_case.execute(
            IngestCVRequest(
                candidate_id=candidate_id,
                filename=filename,
                file_bytes=file_bytes,
                job_id=job_id,
            )
        )
    except Exception as exc:
        if cv_file_id:
            await cv_repo.mark_failed(cv_file_id, str(exc))
        raise

    if cv_file_id:
        await cv_repo.mark_done(cv_file_id)

    # Invalidate all matching caches — new candidate may affect every job's ranking
    try:
        from app.services.matching_cache import invalidate_all
        await invalidate_all()
    except Exception as cache_exc:
        logger.warning("[task_ingest_cv] Cache invalidation failed (non-fatal): %s", cache_exc)

    # NOTE: WebSocket broadcast disabled for synchronous uploads
    # HTTP response is sufficient for UI updates

    logger.info(
        "[task_ingest_cv] Done: candidate_id=%s | chunks=%d | confidence=%.2f",
        candidate_id[:8], result.chunks_count, result.confidence,
    )

    return result.model_dump()
