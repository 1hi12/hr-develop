"""
/api/v1/candidates — CV upload with SHA-256 deduplication + CRUD.
 
Upload flow:
  1. Receive file, compute SHA-256 hash
  2. Query PostgreSQL for cv_file_hash — if found → 200 already_exists (no duplicate stored)
  3. If new → create candidate row (with hash), create cv_files row, enqueue ARQ task
  4. The ARQ worker runs the existing full LLM+embedding pipeline
  5. Return 201 created immediately (processing happens in background)
"""
 
from __future__ import annotations
 
import asyncio
import hashlib
import logging
import uuid
from typing import Optional
 
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select, or_, func
from sqlalchemy.orm import selectinload
 
from app.config.settings import settings
from app.infrastructure.database.models import (
    CandidateModel, CVFileModel, ExperienceModel, EducationModel,
    CandidateJobApplicationModel,
)
from app.infrastructure.database.session import AsyncSessionLocal
from app.core.value_objects.seniority import SeniorityLevel
 
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/candidates", tags=["Candidates"])
 
 
# ── Serializer ────────────────────────────────────────────────────────────────
 
def _candidate_to_dict(c: CandidateModel) -> dict:
    # Extract skills list — prefer extracted_skills.all_skills, fallback to skills_json
    skills: list[str] = []
    if hasattr(c, "extracted_skills") and c.extracted_skills:
        skills = c.extracted_skills.all_skills or []
    elif c.skills_json and isinstance(c.skills_json, dict):
        skills = (
            c.skills_json.get("all_skills")
            or c.skills_json.get("technical", [])
            or []
        )
 
    # Score proxy: extraction_confidence × 100, clamped 0-100
    raw_confidence = c.extraction_confidence or 0.0
    score = min(100, max(0, round(raw_confidence * 100)))
 
    # Always return an integer — never null (0 for interns or unknown)
    seniority = c.seniority_level or "unknown"
    raw_exp = c.total_years_experience
    years_exp: int = int(round(raw_exp)) if raw_exp is not None else 0

    return {
        "candidate_id":           c.candidate_id,
        "identity_id":             c.identity_id,
        "full_name":               c.full_name,
        "email":                   c.email,
        "phone":                   c.phone,
        "location":                c.location,
        "filename":                c.filename,
        "seniority_level":         seniority,
        "total_years_experience":  years_exp,
        "extraction_confidence":   c.extraction_confidence,
        "created_at":              c.created_at.isoformat() if c.created_at else None,
        "skills":                  skills,
        "status":                  c.status or "pending",
        "summary":                 c.summary,
        "linkedin":                c.linkedin,
        "github":                  c.github,
        "languages":               c.languages_json or [],
    }


def _group_to_dict(identity_id: str, members: list[CandidateModel]) -> dict:
    """One row per person: representative fields come from the most recent CV,
    with every linked CV nested underneath (see list_candidates())."""
    representative = members[0]  # members are pre-sorted created_at desc
    return {
        "identity_id": identity_id,
        "full_name":   representative.full_name,
        "email":       representative.email,
        "phone":       representative.phone,
        "cv_count":    len(members),
        "candidates":  [_candidate_to_dict(c) for c in members],
    }


# ── Background ingestion helper ───────────────────────────────────────────────
 
async def _run_ingestion(candidate_id: str, file_bytes: bytes, filename: str) -> None:
    """
    Run the full LLM+embedding+Milvus+Postgres pipeline in the background.
    Called directly via FastAPI BackgroundTasks — no separate ARQ worker needed.
    """
    from app.workers.tasks.ingest_task import task_ingest_cv
    try:
        logger.info("[Candidates] Starting background ingestion for %s", candidate_id[:8])
        await task_ingest_cv(
            ctx={},
            candidate_id=candidate_id,
            file_bytes=file_bytes,
            filename=filename,
            job_id="",
        )
        logger.info("[Candidates] Background ingestion done for %s", candidate_id[:8])
    except Exception as exc:
        logger.error("[Candidates] Background ingestion failed for %s: %s", candidate_id[:8], exc)
 
 
# ── Routes ────────────────────────────────────────────────────────────────────
 
@router.post("/upload")
async def upload_cv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """
    Upload a CV with SHA-256 deduplication.
    Runs the FULL pipeline synchronously (parse → LLM → embed → Milvus → Postgres).
    Returns a response with all pipeline results so the frontend can display them.
 
    Returns 200 + {status: "already_exists"} for duplicate files.
    Returns 201 + full pipeline result for new files.
    """
    file_bytes = await file.read()
    file_hash  = hashlib.sha256(file_bytes).hexdigest()
    filename   = file.filename or "unknown.pdf"
 
    # ── Step 1: Duplicate detection ───────────────────────────────────────────
    # FIX: serialise to a plain dict INSIDE the session so that accessing
    # the `extracted_skills` relationship never touches a detached instance.
    existing_dict: dict | None = None
    existing_meta: dict | None = None          # lightweight fields needed outside
 
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CandidateModel)
            .options(selectinload(CandidateModel.extracted_skills))  # eager-load relationship
            .where(CandidateModel.cv_file_hash == file_hash)
        )
        existing = result.scalar_one_or_none()
        if existing:
            # Capture everything we need while the session (and instance) are alive.
            existing_dict = _candidate_to_dict(existing)
            existing_meta = {
                "candidate_id":  existing.candidate_id,
                "full_name":     existing.full_name or "N/A",
                "seniority":     existing.seniority_level or "unknown",
                "filename":      existing.filename,
            }
 
    # Session is now closed — we only touch plain dicts from here on.
    if existing_dict is not None:
        name = existing_meta["full_name"]
        logger.info(
            "[Candidates/upload] Duplicate detected for %s (hash=%.8s)", name, file_hash
        )
        return JSONResponse(
            status_code=200,
            content={
                "success":      True,
                "job_id":       None,
                "status":       "already_exists",
                "message":      f"Ce CV appartient déjà à {name}",
                "candidate_id": existing_meta["candidate_id"],
                "full_name":    existing_meta["full_name"],
                "seniority":    existing_meta["seniority"],
                "filename":     existing_meta["filename"],
                "candidate":    existing_dict,
            },
        )
 
    # ── Step 2: Create candidate row with hash ────────────────────────────────
    candidate_id = str(uuid.uuid4())
 
    async with AsyncSessionLocal() as session:
        async with session.begin():
            candidate = CandidateModel(
                candidate_id    =candidate_id,
                filename        =filename,
                seniority_level =SeniorityLevel.UNKNOWN.value,
                cv_file_hash    =file_hash,
            )
            session.add(candidate)
 
    # ── Step 3: Create cv_files row ───────────────────────────────────────────
    async with AsyncSessionLocal() as session:
        async with session.begin():
            cv_file = CVFileModel(
                candidate_id     =candidate_id,
                filename         =filename,
                file_size_bytes  =len(file_bytes),
                content_type     =file.content_type,
                source           ="upload",
                processing_status="pending",
            )
            session.add(cv_file)
 
    # ── Step 4: Run full pipeline SYNCHRONOUSLY ───────────────────────────────
    # We await it directly (not as background task) so we can return real results.
    chunks_count = 0
    skills_count = 0
    full_name    = None
    seniority    = SeniorityLevel.UNKNOWN.value
 
    try:
        from app.workers.tasks.ingest_task import task_ingest_cv
        from app.infrastructure.llm.cost_guard import LLMBudgetExceeded
        logger.info("[Candidates/upload] Running pipeline for %s", candidate_id[:8])
        result = await task_ingest_cv(
            ctx={},
            candidate_id=candidate_id,
            file_bytes=file_bytes,
            filename=filename,
            job_id="",
        )
        chunks_count = result.get("chunks_count", 0)
        skills_count = result.get("skills_count", 0)
        full_name    = result.get("full_name") or None
        seniority    = result.get("seniority") or SeniorityLevel.UNKNOWN.value
        logger.info(
            "[Candidates/upload] Pipeline done — chunks=%d, skills=%d, name=%s",
            chunks_count, skills_count, full_name,
        )
    except LLMBudgetExceeded as budget_err:
        logger.error("[Candidates/upload] LLM budget exceeded: %s", budget_err)
        raise HTTPException(
            status_code=429,
            detail=str(budget_err),
        )
    except Exception as exc:
        logger.error("[Candidates/upload] Pipeline failed for %s: %s", candidate_id[:8], exc)
        # Don't crash — candidate row was already created; partial result is returned
 
    return JSONResponse(
        status_code=201,
        content={
            "success":      True,
            "job_id":       None,
            "status":       "created",
            "message":      f"CV traité — {skills_count} compétences extraites",
            "candidate_id": candidate_id,
            "filename":     filename,
            "chunks_count": chunks_count,
            "skills_count": skills_count,
            "full_name":    full_name or "N/A",
            "seniority":    seniority,
            "candidate": {
                "id":           candidate_id,
                "candidate_id": candidate_id,
                "filename":     filename,
                "full_name":    full_name,
                "seniority":    seniority,
            },
        },
    )
 
 
@router.get("")
async def list_candidates(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    search: Optional[str] = None,
    status: Optional[str] = None,
):
    """
    List candidates grouped by identity (one row per person).
    A person matches the search/status filters if ANY of their linked CVs do;
    all of that person's CVs are then returned nested under "candidates".
    """
    async with AsyncSessionLocal() as session:
        filters = []
        if search:
            term = f"%{search}%"
            filters.append(
                or_(
                    CandidateModel.full_name.ilike(term),
                    CandidateModel.email.ilike(term),
                    CandidateModel.location.ilike(term),
                )
            )
        if status:
            filters.append(CandidateModel.status == status)

        # ── Step 1: paginate over distinct identities, not raw CV rows ────────
        identity_q = (
            select(
                CandidateModel.identity_id,
                func.max(CandidateModel.created_at).label("latest"),
            )
            .group_by(CandidateModel.identity_id)
        )
        if filters:
            identity_q = identity_q.where(*filters)

        count_result = await session.execute(
            select(func.count()).select_from(identity_q.subquery())
        )
        total = count_result.scalar_one()

        page_result = await session.execute(
            identity_q.order_by(func.max(CandidateModel.created_at).desc())
            .limit(limit)
            .offset(offset)
        )
        page_identity_ids = [row[0] for row in page_result.all()]

        if not page_identity_ids:
            return {"items": [], "total": total, "limit": limit, "offset": offset}

        # ── Step 2: fetch every CV belonging to those identities ──────────────
        rows_result = await session.execute(
            select(CandidateModel)
            .options(selectinload(CandidateModel.extracted_skills))
            .where(CandidateModel.identity_id.in_(page_identity_ids))
            .order_by(CandidateModel.created_at.desc())
        )
        rows = list(rows_result.scalars())

    members_by_identity: dict[str, list[CandidateModel]] = {}
    for row in rows:
        members_by_identity.setdefault(row.identity_id, []).append(row)

    items = [
        _group_to_dict(identity_id, members_by_identity[identity_id])
        for identity_id in page_identity_ids
        if identity_id in members_by_identity
    ]

    # ── Disambiguate identities that share the exact same full_name ──────────
    # (different people, same name — e.g. two "Ines Dahmeni" with different
    # email/phone). Computed fresh on every request, not stored, so it always
    # reflects the current data — display only, e.g. "Ines Dahmeni (1)"/"(2)".
    names_in_page = {item["full_name"] for item in items if item["full_name"]}
    if names_in_page:
        async with AsyncSessionLocal() as session:
            collision_result = await session.execute(
                select(
                    CandidateModel.identity_id,
                    CandidateModel.full_name,
                    func.min(CandidateModel.created_at).label("first_seen"),
                )
                .where(CandidateModel.full_name.in_(names_in_page))
                .group_by(CandidateModel.identity_id, CandidateModel.full_name)
                .order_by(func.min(CandidateModel.created_at).asc())
            )
            name_to_identity_ids: dict[str, list[str]] = {}
            for identity_id, full_name, _first_seen in collision_result.all():
                name_to_identity_ids.setdefault(full_name, []).append(identity_id)

        suffix_by_identity: dict[str, str] = {}
        for full_name, identity_ids in name_to_identity_ids.items():
            if len(identity_ids) > 1:
                for idx, iid in enumerate(identity_ids, start=1):
                    suffix_by_identity[iid] = f"{full_name} ({idx})"

        for item in items:
            if item["identity_id"] in suffix_by_identity:
                item["full_name"] = suffix_by_identity[item["identity_id"]]

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
 
 
@router.get("/{candidate_id}")
async def get_candidate(candidate_id: str):
    """Get a single candidate by ID."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CandidateModel)
            .options(selectinload(CandidateModel.extracted_skills))
            .where(CandidateModel.candidate_id == candidate_id)
        )
        candidate = result.scalar_one_or_none()
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")
        return _candidate_to_dict(candidate)


@router.get("/{candidate_id}/cv-download")
async def download_cv(candidate_id: str):
    """Download the candidate's CV as a plain-text file (extracted raw text)."""
    from fastapi.responses import Response
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CandidateModel.cv_raw_text, CandidateModel.filename, CandidateModel.full_name)
            .where(CandidateModel.candidate_id == candidate_id)
        )
        row = result.one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Candidate not found")
        cv_raw_text, filename, full_name = row
        if not cv_raw_text:
            raise HTTPException(status_code=404, detail="CV text not available")
        # Serve as a downloadable text file
        safe_name = (full_name or filename or "cv").replace(" ", "_")
        download_filename = f"CV_{safe_name}.txt"
        return Response(
            content=cv_raw_text.encode("utf-8"),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{download_filename}"'},
        )


@router.get("/{candidate_id}/email-preview")
async def preview_interview_email(candidate_id: str):
    """
    Returns the personalized HTML email that would be sent to this candidate.
    Useful to verify the content before triggering the 'hired' status.
    """
    from fastapi.responses import HTMLResponse
    from app.services.email_service import CandidateEmailData, _build_interview_email
 
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CandidateModel)
            .options(
                selectinload(CandidateModel.extracted_skills),
                selectinload(CandidateModel.experiences),
                selectinload(CandidateModel.educations),
            )
            .where(CandidateModel.candidate_id == candidate_id)
        )
        candidate = result.scalar_one_or_none()
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")
 
        # Build same CandidateEmailData as in status update
        tech_skills: list[str] = []
        frameworks:  list[str] = []
        soft_skills: list[str] = []
        if candidate.extracted_skills:
            tech_skills = candidate.extracted_skills.technical  or []
            frameworks  = candidate.extracted_skills.frameworks  or []
            soft_skills = candidate.extracted_skills.soft_skills or []
        elif isinstance(candidate.skills_json, dict):
            tech_skills = candidate.skills_json.get("technical", [])
            frameworks  = candidate.skills_json.get("frameworks", [])
            soft_skills = candidate.skills_json.get("soft_skills", [])
 
        languages: list[str] = []
        if candidate.extracted_skills:
            languages = candidate.extracted_skills.languages or []
        if not languages and candidate.languages_json:
            languages = [
                (lg if isinstance(lg, str) else lg.get("language", ""))
                for lg in candidate.languages_json if lg
            ]
 
        exps = sorted(candidate.experiences or [], key=lambda e: e.start_date or "", reverse=True)
        edus = sorted(candidate.educations  or [], key=lambda e: e.graduation_year or 0, reverse=True)
 
        email_data = CandidateEmailData(
            full_name        = candidate.full_name or "Candidat(e)",
            email            = candidate.email or "(aucun email dans le CV)",
            seniority_level  = candidate.seniority_level or "unknown",
            total_years_exp  = candidate.total_years_experience,
            summary          = candidate.summary,
            location         = candidate.location,
            phone            = candidate.phone,
            linkedin         = candidate.linkedin,
            github           = candidate.github,
            technical_skills = tech_skills,
            frameworks       = frameworks,
            soft_skills      = soft_skills,
            languages        = languages,
            experiences      = [{"title": e.title, "company": e.company, "start_date": e.start_date, "end_date": e.end_date} for e in exps],
            educations       = [{"degree": e.degree, "field_of_study": e.field_of_study, "institution": e.institution, "graduation_year": e.graduation_year} for e in edus],
        )
 
    subject, html = _build_interview_email(email_data)
 
    # Wrap with a banner showing send target
    banner = f"""
    <div style="background:#1e293b;color:#f8fafc;padding:12px 20px;font-family:monospace;
                font-size:13px;position:sticky;top:0;z-index:99;">
      <strong>📧 PREVIEW</strong> &nbsp;|&nbsp;
      À : <strong>{email_data.email}</strong> &nbsp;|&nbsp;
      Objet : {subject}
    </div>
    """
    return HTMLResponse(content=banner + html)
 
 
@router.get("/{candidate_id}/rejection-email-preview")
async def preview_rejection_email(candidate_id: str, job_id: Optional[str] = None):
    """
    Returns the personalised LLM rejection email that would be sent to this candidate.
    Pass ?job_id=<uuid> to include missing-skills analysis for a specific job posting.
    """
    from fastapi.responses import HTMLResponse
    from app.services.email_service import get_email_service

    # ── Fetch candidate ───────────────────────────────────────────────────────
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CandidateModel)
            .options(selectinload(CandidateModel.extracted_skills))
            .where(CandidateModel.candidate_id == candidate_id)
        )
        candidate = result.scalar_one_or_none()
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")

        candidate_skills: list[str] = []
        if candidate.extracted_skills:
            candidate_skills = candidate.extracted_skills.all_skills or []
        elif isinstance(candidate.skills_json, dict):
            candidate_skills = (
                candidate.skills_json.get("all_skills")
                or candidate.skills_json.get("technical", [])
                or []
            )

        name            = candidate.full_name or "Candidat(e)"
        email_addr      = candidate.email or "(aucun email)"
        seniority_level = candidate.seniority_level

    # ── Fetch job posting (optional) ──────────────────────────────────────────
    from app.infrastructure.database.models import JobPostingModel
    job_title      = "le poste"
    missing_skills: list[str] | None = None

    if job_id:
        async with AsyncSessionLocal() as session:
            jp_res = await session.execute(
                select(JobPostingModel).where(JobPostingModel.job_id == job_id)
            )
            job = jp_res.scalar_one_or_none()
            if job:
                job_title       = job.title
                required        = job.required_skills or []
                if required and candidate_skills:
                    cand_lower     = {s.lower() for s in candidate_skills}
                    missing_skills = [s for s in required if s.lower() not in cand_lower]

    # ── Build email HTML (calls LLM in thread) ────────────────────────────────
    email_service = get_email_service()
    subject, html = await asyncio.to_thread(
        email_service.build_rejection_email,
        name, job_title, candidate_skills, missing_skills, seniority_level,
    )

    banner = f"""
    <div style="background:#7f1d1d;color:#fef2f2;padding:12px 20px;font-family:monospace;
                font-size:13px;position:sticky;top:0;z-index:99;">
      <strong>📧 PREVIEW REFUS</strong> &nbsp;|&nbsp;
      À : <strong>{email_addr}</strong> &nbsp;|&nbsp;
      Objet : {subject}
    </div>
    """
    return HTMLResponse(content=banner + html)


@router.post("/test-email")
async def test_email(data: dict):
    """
    Test endpoint — sends a sample interview email immediately.
    Body: { "to": "someone@example.com" }
    """
    from app.services.email_service import CandidateEmailData, send_interview_email_sync
    to = data.get("to")
    if not to:
        raise HTTPException(status_code=422, detail="Field 'to' (email address) is required")
 
    sample = CandidateEmailData(
        full_name        = "Chihi Dorsaf",
        email            = to,
        seniority_level  = "junior",
        total_years_exp  = 2.0,
        summary          = "Développeuse Python passionnée par le Machine Learning et les APIs REST.",
        location         = "Tunis, Tunisie",
        linkedin         = "https://linkedin.com/in/chihi-dorsaf",
        technical_skills = ["Python", "JavaScript", "Java", "SQL"],
        frameworks       = ["Django", "FastAPI", "React"],
        soft_skills      = ["Communication", "Autonomie"],
        languages        = ["Arabe (natif)", "Français (courant)", "Anglais (B2)"],
        experiences      = [
            {"title": "Développeuse Backend", "company": "TechStart", "start_date": "2023-01", "end_date": "Présent"},
        ],
        educations       = [
            {"degree": "Licence Informatique", "field_of_study": "Génie Logiciel",
             "institution": "ENSI Manouba", "graduation_year": 2022},
        ],
    )
 
    success = await asyncio.to_thread(send_interview_email_sync, sample)
    if success:
        return {"status": "sent", "to": to}
    raise HTTPException(status_code=500, detail="Email failed — check SMTP config and server logs")
 
 
async def _upsert_candidate_job_application(session, candidate_id: str, job_posting_id: str, status: str) -> None:
    """Insert or update the per-posting decision row for (candidate_id, job_posting_id)."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = pg_insert(CandidateJobApplicationModel).values(
        candidate_id=candidate_id,
        job_posting_id=job_posting_id,
        status=status,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_candidate_job_application",
        set_={"status": status, "updated_at": func.now()},
    )
    await session.execute(stmt)


@router.patch("/{candidate_id}/status")
async def update_candidate_status(candidate_id: str, data: dict):
    """Update candidate application status: pending | interviewing | hired | rejected.
    When status becomes 'hired':
    - A personalized interview invitation email is sent to the hired candidate.
    - If job_posting_id is provided, rejection emails are sent to all other matched
      candidates for that job who are not already hired or rejected."""
    allowed_statuses = {"pending", "interviewing", "hired", "rejected"}
    new_status = data.get("status")
    job_posting_id: str | None = data.get("job_posting_id")
    if not new_status or new_status not in allowed_statuses:
        raise HTTPException(status_code=422, detail=f"Status must be one of: {allowed_statuses}")
 
    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                select(CandidateModel)
                .options(
                    selectinload(CandidateModel.extracted_skills),
                    selectinload(CandidateModel.experiences),
                    selectinload(CandidateModel.educations),
                )
                .where(CandidateModel.candidate_id == candidate_id)
            )
            candidate = result.scalar_one_or_none()
            if not candidate:
                raise HTTPException(status_code=404, detail="Candidate not found")
 
            previous_status = candidate.status
            candidate.status = new_status

            # Per-posting decision — scoped to job_posting_id so a rejection
            # on this job never removes the candidate from other postings'
            # matching pools (see app/services/job_matching.py _prepare_candidates).
            if job_posting_id and new_status in ("hired", "rejected"):
                await _upsert_candidate_job_application(session, candidate_id, job_posting_id, new_status)

            # Build email data while session is open (all relations accessible)
            email_data = None
            if new_status == "hired" and previous_status != "hired" and candidate.email:
                from app.services.email_service import CandidateEmailData
 
                # Skills from extracted_skills (preferred) or skills_json fallback
                tech_skills: list[str] = []
                frameworks:  list[str] = []
                soft_skills: list[str] = []
                if candidate.extracted_skills:
                    tech_skills = candidate.extracted_skills.technical  or []
                    frameworks  = candidate.extracted_skills.frameworks  or []
                    soft_skills = candidate.extracted_skills.soft_skills or []
                elif isinstance(candidate.skills_json, dict):
                    tech_skills = candidate.skills_json.get("technical", [])
                    frameworks  = candidate.skills_json.get("frameworks", [])
                    soft_skills = candidate.skills_json.get("soft_skills", [])
 
                # Languages (from extracted_skills or languages_json)
                languages: list[str] = []
                if candidate.extracted_skills:
                    languages = candidate.extracted_skills.languages or []
                if not languages and candidate.languages_json:
                    languages = [
                        (lg if isinstance(lg, str) else lg.get("language", ""))
                        for lg in candidate.languages_json
                        if lg
                    ]
 
                # Experiences sorted by start_date desc
                exps = sorted(
                    candidate.experiences or [],
                    key=lambda e: e.start_date or "",
                    reverse=True,
                )
                exp_dicts = [
                    {
                        "title":      e.title,
                        "company":    e.company,
                        "start_date": e.start_date,
                        "end_date":   e.end_date,
                    }
                    for e in exps
                ]
 
                # Educations sorted by graduation_year desc
                edus = sorted(
                    candidate.educations or [],
                    key=lambda e: e.graduation_year or 0,
                    reverse=True,
                )
                edu_dicts = [
                    {
                        "degree":          e.degree,
                        "field_of_study":  e.field_of_study,
                        "institution":     e.institution,
                        "graduation_year": e.graduation_year,
                    }
                    for e in edus
                ]
 
                # Fetch job title if job_posting_id is provided
                job_title_str: str | None = None
                if job_posting_id:
                    from app.infrastructure.database.models import JobPostingModel as _JPM
                    jp_res = await session.execute(
                        select(_JPM).where(_JPM.job_id == job_posting_id)
                    )
                    jp = jp_res.scalar_one_or_none()
                    if jp:
                        job_title_str = jp.title

                email_data = CandidateEmailData(
                    full_name        = candidate.full_name or "Candidat(e)",
                    email            = candidate.email,
                    seniority_level  = candidate.seniority_level or "unknown",
                    total_years_exp  = candidate.total_years_experience,
                    summary          = candidate.summary,
                    location         = candidate.location,
                    phone            = candidate.phone,
                    linkedin         = candidate.linkedin,
                    github           = candidate.github,
                    technical_skills = tech_skills,
                    frameworks       = frameworks,
                    soft_skills      = soft_skills,
                    languages        = languages,
                    experiences      = exp_dicts,
                    educations       = edu_dicts,
                    job_title        = job_title_str,
                )
 
        candidate_dict = _candidate_to_dict(candidate)

    email_sent = False
    email_error: str | None = None

    # Send acceptance email when hired
    if email_data is not None:
        from app.services.email_service import send_interview_email
        try:
            email_sent = await send_interview_email(email_data)
            if email_sent:
                logger.info(
                    "[CandidateStatus] Acceptance email sent to %s (%s)",
                    email_data.full_name, email_data.email,
                )
            else:
                email_error = "Échec SMTP — vérifiez la configuration email"
                logger.error("[CandidateStatus] SMTP failed for %s", email_data.email)
        except Exception as exc:
            email_error = str(exc)
            logger.error("[CandidateStatus] Email error for %s: %s", email_data.email, exc)
    elif new_status == "hired" and previous_status != "hired":
        email_error = "Aucune adresse email pour ce candidat"
        logger.warning(
            "[CandidateStatus] No email address for candidate %s — email not sent",
            candidate_id,
        )

    # Send rejection email when manually set to 'rejected'
    if new_status == "rejected" and previous_status != "rejected" and candidate_dict.get("email"):
        try:
            await _send_single_rejection_email(
                candidate_email=candidate_dict["email"],
                candidate_name=candidate_dict.get("full_name") or "Candidat(e)",
                job_posting_id=job_posting_id,
                candidate_skills=candidate_dict.get("skills") or [],
                seniority_level=candidate_dict.get("seniority_level"),
            )
            email_sent = True
        except Exception as exc:
            email_error = str(exc)
            logger.error("[CandidateStatus] Rejection email error: %s", exc)
    elif new_status == "rejected" and previous_status != "rejected":
        email_error = "Aucune adresse email pour ce candidat"

    # Invalidate matching cache so the next fetch returns up-to-date statuses
    if previous_status != new_status:
        from app.services import matching_cache as mc
        if job_posting_id:
            asyncio.create_task(mc.invalidate(job_posting_id))
        else:
            asyncio.create_task(mc.invalidate_all())

    # Send rejection emails to all other matched candidates for the same job posting
    if new_status == "hired" and previous_status != "hired" and job_posting_id:
        asyncio.create_task(
            _send_rejection_emails_for_job(
                job_posting_id=job_posting_id,
                hired_candidate_id=candidate_id,
            )
        )

    return {**candidate_dict, "email_sent": email_sent, "email_error": email_error}


async def _send_single_rejection_email(
    candidate_email: str,
    candidate_name: str,
    job_posting_id: str | None,
    candidate_skills: list[str] | None = None,
    seniority_level: str | None = None,
) -> None:
    """Send a personalized LLM rejection email to a manually-rejected candidate."""
    from app.services.email_service import get_email_service

    job_title       = "le poste"
    required_skills: list[str] = []

    if job_posting_id:
        try:
            from app.infrastructure.database.models import JobPostingModel
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(JobPostingModel).where(JobPostingModel.job_id == job_posting_id)
                )
                job = result.scalar_one_or_none()
                if job:
                    job_title       = job.title
                    required_skills = job.required_skills or []
        except Exception as exc:
            logger.warning("[SingleRejection] Could not fetch job details: %s", exc)

    # Compute missing skills as simple set difference
    missing_skills: list[str] | None = None
    if required_skills and candidate_skills:
        cand_lower    = {s.lower() for s in candidate_skills}
        missing_skills = [s for s in required_skills if s.lower() not in cand_lower]

    try:
        email_service = get_email_service()
        await email_service.send_rejection_email(
            candidate_email  = candidate_email,
            candidate_name   = candidate_name,
            job_title        = job_title,
            candidate_skills = candidate_skills,
            missing_skills   = missing_skills,
            seniority_level  = seniority_level,
        )
    except Exception as exc:
        logger.error("[SingleRejection] Failed to send rejection email to %s: %s", candidate_email, exc)


async def _send_rejection_emails_for_job(job_posting_id: str, hired_candidate_id: str) -> None:
    """
    Mark all other matched candidates as 'rejected' for this job posting, but
    ONLY once the posting's quota (nb_positions) has actually been filled —
    mirrors the frontend's quota check (job-matching.tsx) so hiring one
    candidate out of several open positions doesn't wipe out every other
    matched candidate for the job.
    """
    from sqlalchemy import update as sa_update
    from app.infrastructure.database.models import JobPostingModel, CandidateJobApplicationModel
    from app.services.job_matching import get_cv_job_matcher

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(JobPostingModel).where(JobPostingModel.job_id == job_posting_id)
            )
            job = result.scalar_one_or_none()

        if not job:
            logger.warning("[AutoReject] Job posting %s not found", job_posting_id)
            return

        if not job.nb_positions:
            logger.info(
                "[AutoReject] Job '%s' has no quota set — skipping mass auto-reject", job.title,
            )
            return

        async with AsyncSessionLocal() as session:
            hired_result = await session.execute(
                select(CandidateJobApplicationModel.candidate_id).where(
                    CandidateJobApplicationModel.job_posting_id == job_posting_id,
                    CandidateJobApplicationModel.status == "hired",
                )
            )
            hired_candidate_ids = {cid for (cid,) in hired_result.all()}
            # The just-hired candidate's own row may not exist yet the very
            # first time this runs, or may have been missed by the query
            # above under concurrent writes — always include it explicitly.
            hired_candidate_ids.add(hired_candidate_id)

        if len(hired_candidate_ids) < job.nb_positions:
            logger.info(
                "[AutoReject] Job '%s' quota not yet reached (%d/%d hired) — skipping mass auto-reject",
                job.title, len(hired_candidate_ids), job.nb_positions,
            )
            return

        # Run matching to get the ranked candidate IDs + per-candidate skills for this job
        matcher = get_cv_job_matcher()
        match_results = await matcher.match(
            job_title=job.title,
            job_description=job.description or "",
            required_skills=job.required_skills or [],
            job_seniority=job.seniority_level,
            top_k=50,
            min_score=0.25,
            generate_ai_desc=False,
            job_posting_id=job_posting_id,
        )

        # Build per-candidate skills lookup from match results — exclude EVERY
        # candidate already hired for this job, not just the one that
        # triggered this particular call (a job can reach quota over several
        # separate hire actions).
        skills_by_id: dict[str, dict] = {
            r.candidate_id: {
                "candidate_skills": r.candidate_skills,
                "missing_skills":   r.missing_skills,
                "seniority":        r.seniority,
            }
            for r in match_results
            if r.candidate_id not in hired_candidate_ids
        }

        # Collect candidate IDs to reject (exclude everyone hired)
        candidate_ids = list(skills_by_id.keys())
        if not candidate_ids:
            return

        # Fetch their current status from DB
        async with AsyncSessionLocal() as session:
            db_result = await session.execute(
                select(CandidateModel.candidate_id, CandidateModel.status)
                .where(CandidateModel.candidate_id.in_(candidate_ids))
            )
            rows = db_result.all()

        # Reject everyone else not already hired for this job (hired_candidate_ids excluded above)
        to_reject_ids = [cid for cid, status in rows if status != "rejected"]
        if not to_reject_ids:
            return

        # Bulk update status to 'rejected' in DB — global field (Candidates page
        # display) AND per-posting row (matching-pool exclusion for THIS job only,
        # so these candidates remain matchable for every other job posting).
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    sa_update(CandidateModel)
                    .where(CandidateModel.candidate_id.in_(to_reject_ids))
                    .values(status="rejected")
                )
                for cid in to_reject_ids:
                    await _upsert_candidate_job_application(session, cid, job_posting_id, "rejected")

        logger.info(
            "[AutoReject] Marked %d candidates as rejected for job '%s'",
            len(to_reject_ids), job.title,
        )

        # Send personalized rejection emails to all auto-rejected candidates
        async with AsyncSessionLocal() as session:
            db_result = await session.execute(
                select(CandidateModel.candidate_id, CandidateModel.full_name, CandidateModel.email)
                .where(CandidateModel.candidate_id.in_(to_reject_ids))
            )
            candidates_to_notify = db_result.all()

        from app.services.email_service import get_email_service
        email_service = get_email_service()
        for cand_id, full_name, email in candidates_to_notify:
            if email:
                info = skills_by_id.get(cand_id, {})
                try:
                    await email_service.send_rejection_email(
                        candidate_email  = email,
                        candidate_name   = full_name or "Candidat(e)",
                        job_title        = job.title,
                        candidate_skills = info.get("candidate_skills"),
                        missing_skills   = info.get("missing_skills"),
                        seniority_level  = info.get("seniority"),
                    )
                except Exception as mail_exc:
                    logger.warning("[AutoReject] Failed to send rejection email to %s: %s", email, mail_exc)

    except Exception as exc:
        logger.error("[AutoReject] Unexpected error: %s", exc)


@router.put("/{candidate_id}")
async def update_candidate(candidate_id: str, data: dict):
    """Partial update of candidate fields."""
    allowed = {"full_name", "email", "phone", "location", "seniority_level"}
    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                select(CandidateModel)
                .options(selectinload(CandidateModel.extracted_skills))
                .where(CandidateModel.candidate_id == candidate_id)
            )
            candidate = result.scalar_one_or_none()
            if not candidate:
                raise HTTPException(status_code=404, detail="Candidate not found")
            for key, value in data.items():
                if key in allowed:
                    setattr(candidate, key, value)
        return _candidate_to_dict(candidate)
 
 
@router.delete("/{candidate_id}", status_code=204)
async def delete_candidate(candidate_id: str):
    """Delete candidate from PostgreSQL and best-effort remove from Milvus."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            candidate = await session.get(CandidateModel, candidate_id)
            if not candidate:
                raise HTTPException(status_code=404, detail="Candidate not found")
            await session.delete(candidate)
 
    # Remove from Milvus (best-effort — don't fail the request if Milvus is unavailable)
    try:
        from app.infrastructure.vector_store.milvus_store import MilvusVectorStore
        store = MilvusVectorStore()
        await store.delete_candidate(candidate_id)
    except Exception as e:
        logger.warning("[Candidates] Milvus delete failed for %s: %s", candidate_id[:8], e)
 
    logger.info("[Candidates] Deleted candidate %s", candidate_id[:8])
 
 
@router.post("/cleanup-milvus")
async def cleanup_milvus_orphans():
    """
    Remove vectors from Milvus whose candidate_id no longer exists in PostgreSQL.
    Safe to run at any time — does not touch the PostgreSQL candidates table.
    Returns counts of orphaned IDs found and deleted.
    """
    from app.infrastructure.vector_store.milvus_store import MilvusVectorStore
 
    # 1. Fetch all candidate_ids currently in Milvus
    store = MilvusVectorStore()
    try:
        col = store._get_collection()
        milvus_rows = col.query(
            expr="candidate_id != ''",
            output_fields=["candidate_id"],
            limit=16384,
        )
    except Exception as e:
        logger.warning("[CleanupMilvus] Could not query Milvus: %s", e)
        return {"status": "error", "detail": str(e), "deleted": 0}
 
    milvus_ids: set[str] = {r["candidate_id"] for r in milvus_rows}
 
    if not milvus_ids:
        return {"status": "ok", "milvus_count": 0, "orphaned": 0, "deleted": 0}
 
    # 2. Find which ones are missing from PostgreSQL
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CandidateModel.candidate_id).where(
                CandidateModel.candidate_id.in_(list(milvus_ids))
            )
        )
        pg_ids: set[str] = {row[0] for row in result}
 
    orphaned_ids = milvus_ids - pg_ids
    deleted = 0
 
    for cid in orphaned_ids:
        try:
            col.delete(expr=f'candidate_id == "{cid}"')
            deleted += 1
            logger.info("[CleanupMilvus] Deleted orphan vectors for candidate %s", cid[:8])
        except Exception as e:
            logger.warning("[CleanupMilvus] Failed to delete orphan %s: %s", cid[:8], e)
 
    if orphaned_ids:
        try:
            col.flush()
        except Exception:
            pass
 
    logger.info(
        "[CleanupMilvus] Done — milvus_ids=%d, pg_ids=%d, orphaned=%d, deleted=%d",
        len(milvus_ids), len(pg_ids), len(orphaned_ids), deleted,
    )
    return {
        "status":      "ok",
        "milvus_count": len(milvus_ids),
        "pg_count":    len(pg_ids),
        "orphaned":    len(orphaned_ids),
        "deleted":     deleted,
    }
 
 
@router.post("/reindex")
async def reindex_candidates(background_tasks: BackgroundTasks):
    """
    Re-run the full pipeline (LLM extraction + embedding + Milvus storage)
    for all candidates that have a cv_file_hash but missing skills in
    candidate_extracted_skills. Used to backfill existing candidates.
    """
    from sqlalchemy import select as sa_select
    from app.infrastructure.database.models import ExtractedSkillsModel
 
    async with AsyncSessionLocal() as session:
        # Find candidates with no row in candidate_extracted_skills
        result = await session.execute(
            sa_select(CandidateModel)
            .outerjoin(
                ExtractedSkillsModel,
                CandidateModel.candidate_id == ExtractedSkillsModel.candidate_id,
            )
            .where(ExtractedSkillsModel.candidate_id.is_(None))
            .where(CandidateModel.cv_file_hash.isnot(None))
        )
        candidates_to_reindex = list(result.scalars())
 
    if not candidates_to_reindex:
        return {"status": "nothing_to_do", "count": 0}
 
    # Kick off re-index in background
    async def _do_reindex():
        from app.workers.tasks.ingest_task import task_ingest_cv
        success = 0
        failed  = 0
        for c in candidates_to_reindex:
            # We can't re-run without the original file bytes.
            # Best effort: re-run extraction from cv_raw_text if stored.
            if not c.cv_raw_text:
                logger.warning("[Reindex] No raw text for %s — skip", c.candidate_id[:8])
                failed += 1
                continue
            try:
                # Re-run pipeline with synthetic bytes from raw text
                fake_bytes = c.cv_raw_text.encode("utf-8")
                await task_ingest_cv(
                    ctx={},
                    candidate_id=c.candidate_id,
                    file_bytes=fake_bytes,
                    filename=c.filename or "reindex.txt",
                    job_id="",
                )
                success += 1
            except Exception as exc:
                logger.error("[Reindex] Failed for %s: %s", c.candidate_id[:8], exc)
                failed += 1
        logger.info("[Reindex] Done — success=%d, failed=%d", success, failed)
 
    background_tasks.add_task(_do_reindex)
 
    return {
        "status":  "started",
        "count":   len(candidates_to_reindex),
        "message": f"Re-indexing {len(candidates_to_reindex)} candidates in background",
    }
