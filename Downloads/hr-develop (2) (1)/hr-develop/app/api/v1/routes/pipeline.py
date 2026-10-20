"""
/api/v1/pipeline — Bulk CV processing pipeline with WebSocket streaming.

Endpoints
---------
  POST /api/v1/pipeline/upload
      Accepts up to 1 000 PDF/DOCX files via multipart form.
      Starts the async pipeline and returns a job_id immediately.

  GET  /api/v1/pipeline/status/{job_id}
      Returns { done, total, percent, status }.

  WS   /api/v1/pipeline/ws/{job_id}
      Client connects after upload.  Receives two event types:

      {"event": "cv_processed",  "data": { index, total, cv, candidate_id,
                                            model_used, processing_time_ms,
                                            chunks_count, skills_count, seniority }}
      {"event": "progress",      "data": { done, total, percent }}
      {"event": "done",          "data": { total, done, errors }}
      {"event": "cv_error",      "data": { filename, error }}

Pipeline (per job)
------------------
  1. Parse each PDF locally with DocumentParser  (pdfplumber → pymupdf fallback)
  2. SHA-256 hash → check PostgreSQL, then SQLite text cache (instant emit on hit)
  3. Group uncached CVs into dynamically-sized batches:
     batch_size = clamp(ceil(n_to_process / 20), 5, 25) — targets ~20 LLM calls
     regardless of upload volume (see Step 3 in _run_pipeline).
  4. asyncio.Queue feeds settings.pipeline_num_workers parallel workers — all
     calling the SAME extractor (MultiWorkerExtractor), which sends every
     batch through the Orange LiteLLM proxy (openai/gpt-4o-mini) as ONE
     streamed call (extract_batch_stream): each CV's JSON object is parsed
     and yielded to the worker as soon as it completes in the stream, so a
     5-CV batch doesn't wait for CV #5 before storing/emitting CV #1. Still
     exactly one LLM call for the whole batch. No other LLM provider is used.
  5. 429 (before anything has streamed) → sleep until the proxy's own quota
     reset time → retry up to PIPELINE_MAX_RETRIES times (handled inside
     MultiWorkerExtractor). Confidence < 0.25 (0 of name/email/skills/
     experiences filled) → one solo re-extraction of that single CV,
     recovering batch-level misalignment without retrying the whole batch.
  6. Per CV: chunk → embed (Orange proxy, text-embedding-3-small) → store
     Milvus + PostgreSQL
  7. Emit WebSocket event as soon as each CV is ready
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.agent.tools.cv_extractor.chunker import LoadedDocument, chunk_document
from app.config.settings import settings
from app.core.entities.candidate import (
    Candidate, Chunk, EmbeddedChunk, Experience, Education,
)
from app.core.value_objects.seniority import SeniorityLevel
from app.core.value_objects.skill import ExtractedSkills, Skill
from app.infrastructure.database.models import CandidateModel, ExtractedSkillsModel
from app.infrastructure.database.session import AsyncSessionLocal
from app.infrastructure.llm.multi_worker_extractor import MultiWorkerExtractor
from app.infrastructure.parsers.document_parser import DocumentParser
from app.infrastructure.repositories.candidate_repo import CandidateRepository
from app.services.cv_pipeline import cache as cv_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipeline", tags=["Pipeline"])

# ── In-memory job registry ────────────────────────────────────────────────────
# job_id → { queue, total, done, errors, status }

_jobs: dict[str, dict[str, Any]] = {}


# ── Helpers — domain entity assembly ─────────────────────────────────────────

def _extraction_confidence(cv_data: dict) -> float:
    """Quick 0-1 confidence signal: fraction of (name, email, skills, experiences) present."""
    filled = sum([
        bool(cv_data.get("name")),
        bool(cv_data.get("email")),
        bool(cv_data.get("skills")),
        bool(cv_data.get("experiences")),
    ])
    return round(filled / 4.0, 2)


def _batch_cv_to_candidate(
    cv_data: dict,
    raw_text: str,
    candidate_id: str,
    filename: str,
) -> Candidate:
    """Convert a batch-extracted CV dict to a Candidate domain entity."""

    # Skills
    skills_list: list[str] = cv_data.get("skills", []) or []
    skills_objs = [
        Skill(name=s) for s in skills_list if isinstance(s, str) and s.strip()
    ]

    # Experiences
    experiences: list[Experience] = []
    for exp in (cv_data.get("experiences", []) or []):
        if not isinstance(exp, dict):
            continue
        try:
            experiences.append(
                Experience(
                    company=exp.get("company", ""),
                    title=exp.get("title", ""),
                    start_date=exp.get("start_date"),
                    end_date=exp.get("end_date"),
                    duration_months=exp.get("duration_months"),
                    description=exp.get("description", ""),
                    location=exp.get("location"),
                )
            )
        except Exception:
            pass

    # Education
    education: list[Education] = []
    for edu in (cv_data.get("education", []) or []):
        if not isinstance(edu, dict):
            continue
        try:
            education.append(
                Education(
                    institution=edu.get("institution", ""),
                    degree=edu.get("degree", ""),
                    field_of_study=edu.get("field_of_study"),
                    graduation_year=edu.get("graduation_year"),
                )
            )
        except Exception:
            pass

    # Seniority
    try:
        seniority = SeniorityLevel(cv_data.get("seniority") or "unknown")
    except ValueError:
        seniority = SeniorityLevel.UNKNOWN

    # Skills structure
    all_skills = skills_list
    extracted_skills = ExtractedSkills(
        technical=skills_list,
        frameworks=[],
        databases=[],
        devops=[],
        soft_skills=[],
        languages=cv_data.get("languages", []) or [],
        all_skills=all_skills,
    )

    filled = sum([
        bool(cv_data.get("name")),
        bool(cv_data.get("email")),
        bool(all_skills),
        bool(experiences),
    ])
    confidence = round(filled / 4.0, 2)

    return Candidate(
        candidate_id=candidate_id,
        filename=filename,
        full_name=cv_data.get("name"),
        email=cv_data.get("email"),
        phone=cv_data.get("phone"),
        location=cv_data.get("location"),
        summary=cv_data.get("summary"),
        languages=cv_data.get("languages", []) or [],
        skills=skills_objs,
        experiences=experiences,
        education=education,
        seniority_level=seniority,
        total_years_experience=cv_data.get("years_exp"),
        raw_text=raw_text,
        extracted_skills=extracted_skills,
        extraction_confidence=confidence,
    )


# ── Per-CV store + emit ───────────────────────────────────────────────────────

async def _store_and_emit(
    *,
    filename: str,
    cv_data: dict,
    raw_text: str,
    candidate_id: str,
    ws_queue: asyncio.Queue,
    index: int,
    total: int,
    model_used: str,
    job_state: dict,
    processing_time_ms: int = 0,
    file_hash: str = "",
) -> None:
    """
    Chunk → embed → store in Milvus/PostgreSQL, then push WebSocket events.
    Storage failures are non-fatal: the cv_processed event is always emitted.
    file_hash is saved to cv_file_hash so future uploads skip re-embedding.
    """
    from app.api.dependencies import get_embedder, get_vector_store
    from sqlalchemy import text as sa_text

    chunks_count = 0
    skills_count = len(cv_data.get("skills", []) or [])

    try:
        # ── Candidate entity ──────────────────────────────────────────────────
        candidate = _batch_cv_to_candidate(cv_data, raw_text, candidate_id, filename)

        # ── Chunking ──────────────────────────────────────────────────────────
        # Off the event loop: chunk_document's semantic path opens its own nested
        # asyncio loop (chunker.py:_get_embeddings), which raises "Cannot run the
        # event loop while another loop is running" if called directly from here
        # (already inside uvicorn's loop) — same fix already used in
        # ingestion_graph.py's extract_and_chunk node.
        doc = LoadedDocument(filename=filename, raw_text=raw_text)
        raw_chunks = await asyncio.to_thread(chunk_document, doc)
        chunks_count = len(raw_chunks)

        # ── Embedding ─────────────────────────────────────────────────────────
        embedder = get_embedder()
        texts = [c.text for c in raw_chunks]
        vectors = await embedder.embed_texts(texts) if texts else []

        embedded_chunks = [
            EmbeddedChunk(
                chunk_id=c.chunk_id,
                text=c.text,
                section=c.section,
                chunk_index=c.chunk_index,
                source_filename=c.source_filename,
                embedding=vectors[i],
                metadata=c.metadata,
            )
            for i, c in enumerate(raw_chunks)
        ]

        cv_chunks = [
            Chunk(
                chunk_id=c.chunk_id,
                text=c.text,
                section=c.section,
                chunk_index=c.chunk_index,
                source_filename=c.source_filename,
            )
            for c in raw_chunks
        ]

        candidate.chunks = cv_chunks
        candidate.embedded_chunks = embedded_chunks

        # ── Vector store ──────────────────────────────────────────────────────
        vector_store = get_vector_store()
        all_skills = cv_data.get("skills", []) or []
        await vector_store.store_candidate(
            candidate_id=candidate_id,
            filename=filename,
            chunks=embedded_chunks,
            skills_json=json.dumps(all_skills),
        )

        # ── PostgreSQL ────────────────────────────────────────────────────────
        candidate_repo = CandidateRepository()
        await candidate_repo.save(candidate)

        # ── Persist hash so future uploads skip re-embedding ──────────────────
        if file_hash:
            async with AsyncSessionLocal() as session:
                await session.execute(
                    sa_text(
                        "UPDATE candidates SET cv_file_hash = :h "
                        "WHERE candidate_id = :cid AND cv_file_hash IS NULL"
                    ),
                    {"h": file_hash, "cid": candidate_id},
                )
                await session.commit()

        logger.info(
            "[Pipeline] Stored %s — chunks=%d skills=%d seniority=%s",
            filename, chunks_count, skills_count, candidate.seniority_level.value,
        )

    except Exception as exc:
        logger.error("[Pipeline] Storage error for %s: %s", filename, exc)

    # ── Update job state ──────────────────────────────────────────────────────
    job_state["done"] += 1
    percent = round(job_state["done"] / total * 100, 1)

    # ── Emit cv_processed ─────────────────────────────────────────────────────
    await ws_queue.put({
        "event": "cv_processed",
        "data": {
            "index": index,
            "total": total,
            "cv": {
                "name": cv_data.get("name"),
                "email": cv_data.get("email"),
                "phone": cv_data.get("phone"),
                "location": cv_data.get("location"),
                "summary": cv_data.get("summary"),
                "skills": cv_data.get("skills", []) or [],
                "experiences": cv_data.get("experiences", []) or [],
                "education": cv_data.get("education", []) or [],
                "languages": cv_data.get("languages", []) or [],
                "certifications": cv_data.get("certifications", []) or [],
                "seniority": cv_data.get("seniority"),
                "years_exp": cv_data.get("years_exp"),
                "detected_lang": cv_data.get("detected_lang", "FR"),
            },
            "candidate_id": candidate_id,
            "filename": filename,
            "model_used": model_used,
            "processing_time_ms": processing_time_ms,
            "chunks_count": chunks_count,
            "skills_count": skills_count,
            "seniority": cv_data.get("seniority", "unknown"),
        },
    })

    # ── Emit progress ─────────────────────────────────────────────────────────
    await ws_queue.put({
        "event": "progress",
        "data": {"done": job_state["done"], "total": total, "percent": percent},
    })


# ── Main pipeline coroutine ───────────────────────────────────────────────────

async def _fetch_existing_by_hashes(
    hash_map: dict[str, tuple[str, str]],   # hash → (filename, candidate_id)
) -> dict[str, dict]:
    """
    Batch-query PostgreSQL for candidates whose cv_file_hash is in hash_map.
    Returns a mapping  hash → existing candidate dict  for duplicates found.
    """
    if not hash_map:
        return {}
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CandidateModel)
            .options(selectinload(CandidateModel.extracted_skills))
            .where(CandidateModel.cv_file_hash.in_(list(hash_map.keys())))
        )
        rows = list(result.scalars())

    existing: dict[str, dict] = {}
    for row in rows:
        if not row.cv_file_hash:
            continue
        skills: list[str] = []
        if row.extracted_skills:
            skills = row.extracted_skills.all_skills or []
        existing[row.cv_file_hash] = {
            "candidate_id": row.candidate_id,
            "name":         row.full_name,
            "email":        row.email,
            "phone":        row.phone,
            "location":     row.location,
            "summary":      row.summary,
            "skills":       skills,
            "seniority":    row.seniority_level or "unknown",
            "years_exp":    row.total_years_experience,
            "languages":    row.languages_json or [],
            "experiences":  [],
            "education":    [],
            "certifications": [],
            "detected_lang": "FR",
            "created_at":   row.created_at.isoformat() if row.created_at else None,
        }
    return existing


async def _run_pipeline(
    job_id: str,
    file_data: list[tuple[str, bytes]],   # [(filename, raw_bytes), ...]
) -> None:
    job_state = _jobs.get(job_id)
    if not job_state:
        return

    ws_queue: asyncio.Queue = job_state["queue"]
    total = len(file_data)
    parser = DocumentParser()
    extractor = MultiWorkerExtractor()

    # ── Step 1: Parse all PDFs locally ───────────────────────────────────────
    parsed: list[tuple[str, str, str, str]] = []   # (filename, text, candidate_id, hash)

    for filename, file_bytes in file_data:
        try:
            text = parser.parse(file_bytes, filename)
            file_hash = hashlib.sha256(file_bytes).hexdigest()
            parsed.append((filename, text, str(uuid.uuid4()), file_hash))
        except Exception as exc:
            logger.error("[Pipeline] Parse error %s: %s", filename, exc)
            job_state["errors"] += 1
            job_state["done"] += 1
            await ws_queue.put({
                "event": "cv_error",
                "data": {"filename": filename, "error": str(exc)},
            })

    # ── Step 2: SHA-256 dedup — skip CVs already stored in PostgreSQL ─────────
    # Build hash → (filename, candidate_id) map for batch DB lookup
    hash_map = {h: (fn, cid) for fn, _, cid, h in parsed}
    existing_by_hash = await _fetch_existing_by_hashes(hash_map)

    to_process: list[tuple[str, str, str]] = []     # (filename, text, candidate_id)
    emit_index = 0

    for filename, text, candidate_id, file_hash in parsed:
        # ── Already in DB → emit instantly, skip embedding ───────────────────
        if file_hash in existing_by_hash:
            existing = existing_by_hash[file_hash]
            existing_cid = existing["candidate_id"]
            logger.info(
                "[Pipeline] SHA-256 dedup HIT: %s → candidate %s (skip re-embed)",
                filename, existing_cid[:8],
            )
            job_state["done"] += 1
            percent = round(job_state["done"] / total * 100, 1)
            await ws_queue.put({
                "event": "cv_processed",
                "data": {
                    "index": emit_index,
                    "total": total,
                    "cv": {
                        "name":         existing["name"],
                        "email":        existing["email"],
                        "phone":        existing["phone"],
                        "location":     existing["location"],
                        "summary":      existing["summary"],
                        "skills":       existing["skills"],
                        "experiences":  existing["experiences"],
                        "education":    existing["education"],
                        "languages":    existing["languages"],
                        "certifications": existing["certifications"],
                        "seniority":    existing["seniority"],
                        "years_exp":    existing["years_exp"],
                        "detected_lang": existing["detected_lang"],
                    },
                    "candidate_id":       existing_cid,
                    "filename":           filename,
                    "model_used":         "dedup_cache",
                    "processing_time_ms": 0,
                    "chunks_count":       0,
                    "skills_count":       len(existing["skills"]),
                    "seniority":          existing["seniority"],
                    "already_exists":     True,
                    "created_at":         existing.get("created_at"),
                },
            })
            await ws_queue.put({
                "event": "progress",
                "data": {"done": job_state["done"], "total": total, "percent": percent},
            })
            emit_index += 1
            continue

        # ── Not in DB → check text cache (avoids LLM call, still embeds) ─────
        cached = await cv_cache.get_cached(text)
        if cached:
            logger.info("[Pipeline] Text cache HIT: %s", filename)
            await _store_and_emit(
                filename=filename,
                cv_data=cached,
                raw_text=text,
                candidate_id=candidate_id,
                ws_queue=ws_queue,
                index=emit_index,
                total=total,
                model_used="cache",
                job_state=job_state,
                file_hash=file_hash,
            )
            emit_index += 1
        else:
            to_process.append((filename, text, candidate_id, file_hash))

    # ── Step 3: Dynamic batching — target ~20 LLM calls regardless of volume ──
    n_to_process = len(to_process)
    if n_to_process > 0:
        batch_size = max(5, min(25, -(-n_to_process // 20)))  # ceil(n/20), clamped
    else:
        batch_size = settings.pipeline_batch_size
    n_batches = -(-n_to_process // batch_size) if n_to_process else 0
    logger.info(
        "[Pipeline] Dynamic batch: %d CVs → batch_size=%d → ~%d LLM calls",
        n_to_process, batch_size, n_batches,
    )
    batches = [
        to_process[i: i + batch_size]
        for i in range(0, n_to_process, batch_size)
    ]

    # asyncio.Queue feeds settings.pipeline_num_workers parallel workers
    batch_queue: asyncio.Queue = asyncio.Queue()
    for i, batch in enumerate(batches):
        await batch_queue.put((i, batch))

    # ── Step 4: Worker coroutines ─────────────────────────────────────────────
    batch_index_counter = [emit_index]  # mutable wrapper for shared counter
    batch_lock = asyncio.Lock()

    async def worker(worker_id: int) -> None:
        while True:
            try:
                batch_num, batch = batch_queue.get_nowait()
            except asyncio.QueueEmpty:
                return

            texts = [text for _, text, _, _ in batch]
            t0 = time.monotonic()

            # Streamed: each CV is stored/emitted the moment its JSON object
            # completes in the response, instead of waiting for the whole
            # batch — still exactly one LLM call for the whole batch.
            # extract_batch_stream always yields exactly len(texts) items on
            # its own; this wrapper is only a safety net so an unexpected
            # crash still fills the remaining slots instead of hanging the
            # job (job_state["done"] would never reach total otherwise).
            async def _iter_stream():
                seen = 0
                try:
                    async for item in extractor.extract_batch_stream(texts):
                        seen += 1
                        yield item
                except Exception as exc:
                    logger.error("[Worker %d] Batch %d stream failed: %s", worker_id, batch_num, exc)
                for k in range(seen, len(batch)):
                    yield k, {}, "error"

            async for k, cv_data, model_name in _iter_stream():
                filename, text, candidate_id, fhash = batch[k]

                # Confidence-based solo retry: a batch call can drop/misalign one
                # CV (JSON array desync) while the others come out fine. Retrying
                # just that one CV alone is far cheaper than retrying the whole
                # batch, and only fires on near-total extraction failures
                # (confidence < 0.25 = 0 of the 4 tracked fields filled).
                if _extraction_confidence(cv_data) < 0.25:
                    try:
                        solo_results, solo_model = await extractor.extract_batch([text])
                    except Exception as exc:
                        logger.warning("[Worker %d] Solo retry failed for %s: %s", worker_id, filename, exc)
                        solo_results = []
                    if solo_results and _extraction_confidence(solo_results[0]) > _extraction_confidence(cv_data):
                        logger.info(
                            "[Worker %d] Solo retry recovered %s (confidence %.2f → %.2f)",
                            worker_id, filename,
                            _extraction_confidence(cv_data), _extraction_confidence(solo_results[0]),
                        )
                        cv_data = solo_results[0]
                        model_name = f"{solo_model}+solo_retry"

                # Cache result for future identical CVs
                if cv_data:
                    try:
                        await cv_cache.set_cached(text, cv_data, filename)
                    except Exception:
                        pass

                async with batch_lock:
                    idx = batch_index_counter[0]
                    batch_index_counter[0] += 1

                await _store_and_emit(
                    filename=filename,
                    cv_data=cv_data,
                    raw_text=text,
                    candidate_id=candidate_id,
                    ws_queue=ws_queue,
                    index=idx,
                    total=total,
                    model_used=model_name,
                    job_state=job_state,
                    processing_time_ms=int((time.monotonic() - t0) * 1000),
                    file_hash=fhash,
                )

    # Run settings.pipeline_num_workers parallel workers
    await asyncio.gather(*(worker(i) for i in range(settings.pipeline_num_workers)))

    # ── Step 5: Signal completion ─────────────────────────────────────────────
    job_state["status"] = "done"
    await ws_queue.put({
        "event": "done",
        "data": {
            "total": total,
            "done": job_state["done"],
            "errors": job_state["errors"],
        },
    })
    logger.info("[Pipeline] Job %s complete — %d/%d CVs", job_id, job_state["done"], total)


# ── REST endpoints ────────────────────────────────────────────────────────────

@router.post("/upload")
async def bulk_upload(files: list[UploadFile] = File(...)) -> JSONResponse:
    """
    Accept up to 1 000 PDF/DOCX files, start the pipeline, return job_id.
    The client should immediately connect to /pipeline/ws/{job_id}.
    """
    if not files:
        return JSONResponse({"error": "No files provided"}, status_code=400)
    if len(files) > 1000:
        return JSONResponse({"error": "Maximum 1 000 files per job"}, status_code=400)

    # Read all bytes eagerly (files are in-memory multipart)
    file_data: list[tuple[str, bytes]] = []
    for f in files:
        raw = await f.read()
        file_data.append((f.filename or "unknown.pdf", raw))

    job_id = str(uuid.uuid4())
    ws_queue: asyncio.Queue = asyncio.Queue()

    _jobs[job_id] = {
        "queue": ws_queue,
        "total": len(file_data),
        "done": 0,
        "errors": 0,
        "status": "running",
    }

    # Fire-and-forget — pipeline runs in background
    asyncio.create_task(_run_pipeline(job_id, file_data))

    logger.info("[Pipeline] Job %s started — %d files", job_id, len(file_data))
    return JSONResponse({"job_id": job_id, "total": len(file_data)})


@router.get("/status/{job_id}")
async def get_status(job_id: str) -> JSONResponse:
    """Return current progress for a pipeline job."""
    state = _jobs.get(job_id)
    if not state:
        return JSONResponse({"error": "Job not found"}, status_code=404)

    total = state["total"]
    done = state["done"]
    percent = round(done / total * 100, 1) if total else 0.0

    return JSONResponse({
        "job_id": job_id,
        "total": total,
        "done": done,
        "percent": percent,
        "errors": state["errors"],
        "status": state["status"],
    })


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@router.websocket("/ws/{job_id}")
async def websocket_pipeline(websocket: WebSocket, job_id: str) -> None:
    """
    Real-time streaming of pipeline results.
    Events are pushed as soon as each CV is ready — no waiting for the full batch.
    """
    await websocket.accept()
    logger.info("[WS] Client connected to job %s", job_id)

    state = _jobs.get(job_id)
    if not state:
        await websocket.send_json({"event": "error", "data": {"message": "Job not found"}})
        await websocket.close()
        return

    ws_queue: asyncio.Queue = state["queue"]

    try:
        while True:
            try:
                # Poll queue with a short timeout so we can detect disconnects
                message = await asyncio.wait_for(ws_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # Send keepalive ping to detect disconnected clients
                try:
                    await websocket.send_json({"event": "ping"})
                except Exception:
                    break
                continue

            await websocket.send_json(message)

            if message.get("event") == "done":
                break

    except WebSocketDisconnect:
        logger.info("[WS] Client disconnected from job %s", job_id)
    except Exception as exc:
        logger.error("[WS] Error on job %s: %s", job_id, exc)
    finally:
        # Clean up completed jobs after a delay to allow late reconnects
        asyncio.create_task(_cleanup_job(job_id, delay=300))


async def _cleanup_job(job_id: str, delay: int = 300) -> None:
    await asyncio.sleep(delay)
    _jobs.pop(job_id, None)
    logger.debug("[Pipeline] Job %s cleaned up", job_id)
