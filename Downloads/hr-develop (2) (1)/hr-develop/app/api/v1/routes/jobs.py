"""
/api/v1/jobs — Full CRUD for job postings + AI matching endpoints.
Frontend maps /api/postings → these routes via main.py shims.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select


from app.infrastructure.database.models import (
    CandidateModel,
    ExtractedSkillsModel,
    JobPostingModel,
)
from app.infrastructure.database.session import AsyncSessionLocal
from app.application.dtos.match_dto import MatchRequest


_SENIORITY_ORDER = ["intern", "junior", "mid", "senior", "lead", "executive"]

_DB_SENIORITY_MAP: dict[str, str] = {
    "intern": "intern", "stagiaire": "intern", "stage": "intern",
    "apprenti": "intern", "alternant": "intern", "étudiant": "intern", "trainee": "intern",
    "junior": "junior", "débutant": "junior",
    "mid": "mid", "intermédiaire": "mid", "confirmé": "mid",
    "senior": "senior", "expérimenté": "senior",
    "lead": "lead", "principal": "lead", "staff": "lead", "architect": "lead",
    "executive": "executive", "vp": "executive", "cto": "executive", "cio": "executive",
}


def _detect_required_seniority(text: str) -> str:
    """Detect required seniority level from job title (FR + EN)."""
    t = text.lower()
    if any(w in t for w in ("lead", "principal", "staff", "architect", "head of",
                             "directeur technique", "tech lead", "team lead")):
        return "lead"
    if any(w in t for w in ("executive", "vp ", "vice president", "cto", "cio", "chief")):
        return "executive"
    if any(w in t for w in ("senior", "sr.", "sr ", "expérimenté", "experienced", "confirmé")):
        return "senior"
    if any(w in t for w in ("junior", "jr.", "jr ", "débutant", "entry level", "entry-level")):
        return "junior"
    if any(w in t for w in ("intern", "stagiaire", "stage", "apprenti", "alternant", "étudiant")):
        return "intern"
    return "mid"


def _normalize_db_seniority(raw: str) -> str:
    """Map DB seniority_level string to canonical level (handles FR/EN variants)."""
    if not raw:
        return ""
    t = raw.lower().strip()
    for key, level in _DB_SENIORITY_MAP.items():
        if t == key or t.startswith(key):
            return level
    return ""


_SENIORITY_LABELS: dict[str, str] = {
    "intern":    "Stagiaire",
    "junior":    "Junior",
    "mid":       "Confirmé",
    "senior":    "Senior",
    "lead":      "Lead",
    "executive": "Directeur",
}


def _seniority_score(candidate_level: str, required_level: str) -> float:
    """
    Composante séniorité (0.0 → 1.0) pour la formule 60/40.
    • Même niveau ou au-dessus → 1.0
    • 1 niveau en-dessous     → 0.50
    • 2 niveaux en-dessous    → 0.15
    • 3+ niveaux en-dessous   → 0.0
    """
    try:
        c_idx = _SENIORITY_ORDER.index(candidate_level)
        r_idx = _SENIORITY_ORDER.index(required_level)
    except ValueError:
        return 0.5   # niveau inconnu → neutre
    gap = r_idx - c_idx
    if gap <= 0:
        return 1.0
    if gap == 1:
        return 0.50
    if gap == 2:
        return 0.15
    return 0.0


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["Jobs"])

# In-memory cache: job_id → last match result
_match_results_cache: dict[str, dict] = {}
# Per-job locks: prevent React StrictMode double-POST from running the pipeline twice
_match_locks: dict[str, asyncio.Lock] = {}


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class JobCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    skills: list[str] = []
    department: Optional[str] = None
    location: Optional[str] = None
    status: str = "active"


class JobUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    skills: Optional[list[str]] = None
    department: Optional[str] = None
    location: Optional[str] = None
    status: Optional[str] = None


class JobStatusRequest(BaseModel):
    status: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialize(job: JobPostingModel, candidate_count: int = 0) -> dict:
    """Convert DB model to frontend-expected shape."""
    skills = job.required_skills or []
    return {
        "id":          job.job_id,
        "title":       job.title,
        "description": job.description or "",
        "department":  job.department,
        "location":    job.location,
        "status":      job.status,
        "skills": [
            {"id": str(i), "name": s}
            for i, s in enumerate(skills)
        ],
        "applicants": candidate_count,
        "createdAt": job.created_at.isoformat() if job.created_at else None,
        "updatedAt": job.updated_at.isoformat() if job.updated_at else None,
    }


def _make_avatar(name: str) -> str:
    """Generate 2-letter avatar initials from a full name."""
    if not name or name in ("N/A", "unknown"):
        return "??"
    parts = name.strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return name[:2].upper()


async def _fetch_candidate_db_info(candidate_ids: list[str]) -> dict[str, dict]:
    """Fetch candidate rows (with skills) from PostgreSQL for match enrichment."""
    if not candidate_ids:
        return {}

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CandidateModel, ExtractedSkillsModel)
            .outerjoin(
                ExtractedSkillsModel,
                CandidateModel.candidate_id == ExtractedSkillsModel.candidate_id,
            )
            .where(CandidateModel.candidate_id.in_(candidate_ids))
        )
        rows = result.all()

    info: dict[str, dict] = {}
    for candidate, ext_skills in rows:
        all_skills: list[str] = []
        if ext_skills and ext_skills.all_skills:
            all_skills = list(ext_skills.all_skills)
        info[candidate.candidate_id] = {
            "full_name":             candidate.full_name,
            "email":                 candidate.email,
            "filename":              candidate.filename,
            "seniority_level":       candidate.seniority_level,
            "total_years_experience": candidate.total_years_experience,
            "all_skills":            all_skills,
        }
    return info


# ── CRUD Routes ───────────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create_job(req: JobCreateRequest):
    """Create a new job posting."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    job_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as session:
        async with session.begin():
            job = JobPostingModel(
                job_id=job_id,
                title=req.title,
                description=req.description,
                department=req.department,
                location=req.location,
                status=req.status,
                required_skills=req.skills,
                preferred_skills=[],
                scoring_weights={"skills": 0.4, "experience": 0.3, "education": 0.2, "other": 0.1},
                created_at=now,
                updated_at=now,
            )
            session.add(job)
    logger.info("[Jobs] Created job %s: %s", job_id[:8], req.title)
    return _serialize(job)


@router.get("")
async def list_jobs(
    status: Optional[str] = None,
    department: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """List all job postings with optional filters."""
    async with AsyncSessionLocal() as session:
        query = select(JobPostingModel).order_by(JobPostingModel.created_at.desc())
        if status:
            query = query.where(JobPostingModel.status == status)
        if department:
            query = query.where(JobPostingModel.department == department)
        if q:
            query = query.where(JobPostingModel.title.ilike(f"%{q}%"))
        query = query.limit(limit).offset(offset)
        result = await session.execute(query)
        jobs = list(result.scalars())

        # Total processed candidates in the system (used as applicant count for all jobs)
        total_candidates = await session.scalar(
            select(func.count()).select_from(CandidateModel)
        ) or 0

    return [_serialize(j, total_candidates) for j in jobs]


@router.get("/{job_id}")
async def get_job(job_id: str):
    """Get a single job posting by ID."""
    async with AsyncSessionLocal() as session:
        job = await session.get(JobPostingModel, job_id)
        total_candidates = await session.scalar(
            select(func.count()).select_from(CandidateModel)
        ) or 0
    if not job:
        raise HTTPException(status_code=404, detail="Job posting not found")
    return _serialize(job, total_candidates)


@router.put("/{job_id}")
async def update_job(job_id: str, req: JobUpdateRequest):
    """Update a job posting (full or partial update)."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            job = await session.get(JobPostingModel, job_id)
            if not job:
                raise HTTPException(status_code=404, detail="Job posting not found")
            if req.title is not None:
                job.title = req.title
            if req.description is not None:
                job.description = req.description
            if req.skills is not None:
                job.required_skills = req.skills
            if req.department is not None:
                job.department = req.department
            if req.location is not None:
                job.location = req.location
            if req.status is not None:
                job.status = req.status
        await session.refresh(job)
    return _serialize(job)


@router.delete("/{job_id}", status_code=204)
async def delete_job(job_id: str):
    """Delete a job posting."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            job = await session.get(JobPostingModel, job_id)
            if not job:
                raise HTTPException(status_code=404, detail="Job posting not found")
            await session.delete(job)
    _match_results_cache.pop(job_id, None)
    logger.info("[Jobs] Deleted job %s", job_id[:8])


@router.patch("/{job_id}/status")
async def update_job_status(job_id: str, req: JobStatusRequest):
    """Update only the status of a job posting."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            job = await session.get(JobPostingModel, job_id)
            if not job:
                raise HTTPException(status_code=404, detail="Job posting not found")
            job.status = req.status
        await session.refresh(job)
    return _serialize(job)


# ── AI Match endpoints ────────────────────────────────────────────────────────

@router.post("/{job_id}/match")
async def match_job(job_id: str, force: bool = False):
    """
    Run the full AI matching pipeline for a job posting.
    - Embeds job description → vector search → LLM reranking
    - Enriches results with PostgreSQL candidate data
    - Caches result in memory (use force=true to recompute)
    Returns ranked candidates with overall_score, technical_fit, culture_fit, growth_fit.
    """
    # Per-job lock: the entire pipeline runs inside the lock so that a React
    # StrictMode double-POST never runs two pipelines in parallel.
    # Second caller waits, then hits the cache and returns instantly.
    if job_id not in _match_locks:
        _match_locks[job_id] = asyncio.Lock()

    async with _match_locks[job_id]:
        # Re-check cache inside the lock — second caller returns immediately
        if not force and job_id in _match_results_cache:
            result = dict(_match_results_cache[job_id])
            result["from_cache"] = True
            return result

        async with AsyncSessionLocal() as session:
            job = await session.get(JobPostingModel, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job posting not found")

        # Build the job description text for the AI engine
        skills_list = job.required_skills or []
        # Detect required seniority from title — passed explicitly so the ranker
        # can enforce hard score caps (intern vs senior = max 20%, etc.)
        req_seniority = _detect_required_seniority(job.title)

        job_text = (
            f"Position: {job.title}\n"
            f"Required seniority level: {req_seniority}\n"
        )
        if job.description:
            job_text += f"\n{job.description}"
        if skills_list:
            job_text += f"\n\nRequired skills: {', '.join(skills_list)}"
        if job.location:
            job_text += f"\nLocation: {job.location}"

        # Run AI matching pipeline
        from app.api.dependencies import get_match_use_case
        use_case = get_match_use_case()

        req = MatchRequest(
            job_description=job_text,
            job_title=job.title,
            required_skills=skills_list,
            top_k=20,
            min_score=0.0,   # let ranker decide via seniority caps
            use_reranking=True,
        )

        start_time = time.time()
        try:
            match_response = await use_case.execute(req)
        except Exception as e:
            logger.exception("[Jobs/match] AI pipeline failed for job %s: %s", job_id[:8], e)
            raise HTTPException(status_code=500, detail=f"AI matching failed: {str(e)}")

        elapsed = round(time.time() - start_time, 2)
        logger.info("[Jobs/match] Completed in %.1fs — %d candidates", elapsed, len(match_response.candidates))

        # Enrich results with real candidate data from PostgreSQL
        candidate_ids = [c["candidate_id"] for c in match_response.candidates]
        db_info = await _fetch_candidate_db_info(candidate_ids)

        candidates_out = []
        for c in match_response.candidates:
            cid    = c["candidate_id"]
            db_c   = db_info.get(cid, {})
            _raw_expl = c.get("explanation") or {}
            expl: dict = _raw_expl if isinstance(_raw_expl, dict) else {"explanation": str(_raw_expl)}

            # ── Candidate identity ────────────────────────────────────────────
            c_info = expl.get("candidate_info") or {}
            name = (
                db_c.get("full_name")
                or c_info.get("name")
                or db_c.get("filename")
                or cid[:8]
            )
            exp_years = db_c.get("total_years_experience")
            db_raw_seniority = db_c.get("seniority_level") or ""
            cand_canonical   = _normalize_db_seniority(db_raw_seniority) or "mid"
            # Libellé séniorité affiché (FR) : Stagiaire / Junior / Confirmé / Senior …
            seniority_label = _SENIORITY_LABELS.get(cand_canonical, "—")

            # ── Scores bruts du LLM ───────────────────────────────────────────
            llm_overall    = c.get("relevance_score", c.get("score", 0.0))
            technical_fit  = float(c.get("technical_fit", llm_overall) or llm_overall)
            culture_fit    = float(c.get("culture_fit")  or llm_overall)
            growth_fit     = float(c.get("growth_fit")   or llm_overall)

            # ── Formule 60 % compétences + 40 % séniorité ────────────────────
            # competence_score = technical_fit du LLM (0.0–1.0), représente
            #   la correspondance des compétences avec le poste.
            # seniority_s      = score mathématique basé sur l'écart de niveau :
            #   même niveau → 1.0 | -1 → 0.50 | -2 → 0.15 | -3+ → 0.0
            seniority_s = _seniority_score(cand_canonical, req_seniority)
            overall     = round(0.6 * min(technical_fit, 1.0) + 0.4 * seniority_s, 4)

            # Répercuter le ratio séniorité sur les autres dimensions
            culture_fit = round(min(culture_fit, 1.0) * (0.6 + 0.4 * seniority_s), 4)
            growth_fit  = round(min(growth_fit, 1.0)  * (0.6 + 0.4 * seniority_s), 4)
            technical_fit = round(min(technical_fit, 1.0), 4)

            _gap_note = ""
            if seniority_s < 1.0:
                logger.info(
                    "[Jobs/match] Formule 60/40 : %s (candidat=%s, poste=%s) "
                    "séniorité=%.0f%% → score=%.0f%%",
                    cid[:8], cand_canonical, req_seniority,
                    seniority_s * 100, overall * 100,
                )
                _gap_note = (
                    f" ⚠ Écart de séniorité : le poste exige {req_seniority}, "
                    f"le candidat est {cand_canonical}."
                )

            # ── Skills tags: LLM matched_skills > DB all_skills > job skills ──
            llm_matched: list[str] = expl.get("matched_skills") or []
            skills_tags: list[str] = (llm_matched or db_c.get("all_skills", []))[:6]
            if not skills_tags:
                skills_tags = skills_list[:3]

            # ── Analytical description ────────────────────────────────────────
            cv_summary   = expl.get("cv_summary")   or db_c.get("summary") or ""
            why_chosen   = (expl.get("why_chosen") or expl.get("explanation") or "") + _gap_note
            presentation = why_chosen or cv_summary or (
                f"Compétences : {', '.join(skills_tags[:6])}" if skills_tags else ""
            )

            candidates_out.append({
                "id":                 cid,
                "name":               name,
                "title":              seniority_label,
                "experience":         seniority_label,
                "experience_years":   exp_years,
                "skills":             skills_tags,
                "matched_skills":     llm_matched,
                "missing_skills":     expl.get("missing_skills") or [],
                "matchScore":         round(overall * 100),
                "overall_score":      round(overall, 4),
                "technical_fit":      round(technical_fit * 100),
                "culture_fit":        round(culture_fit * 100),
                "growth_fit":         round(growth_fit * 100),
                "rank":               c["rank"],
                "avatar":             _make_avatar(name),
                "cv_summary":         cv_summary,
                "why_chosen":         why_chosen,
                "experience_assessment": expl.get("experience") or "",
                "explanation":        presentation,
                "status":             expl.get("status", "selected"),
                "contact":            "Contact",
            })

        # Compute job-level aggregate scores (average of top 3)
        top = candidates_out[:3]
        def _avg(field: str) -> int:
            vals = [c[field] for c in top if c[field]]
            return round(sum(vals) / len(vals)) if vals else 0

        result = {
            "job_id":             job_id,
            "job_title":          job.title,
            "job_department":     job.department or "Engineering",
            "job_location":       job.location or "N/A",
            "job_type":           "Full-time",
            "technical_fit":      _avg("technical_fit"),
            "culture_fit":        _avg("culture_fit"),
            "growth_fit":         _avg("growth_fit"),
            "candidates":         candidates_out,
            "recruiter_advice":   match_response.recruiter_advice,
            "total_candidates":   len(candidates_out),
            "processing_time_seconds": elapsed,
            "from_cache":         False,
        }

        _match_results_cache[job_id] = result
        return result


@router.get("/{job_id}/match/results")
async def get_match_results(job_id: str):
    """Return the last cached match results for a job."""
    if job_id not in _match_results_cache:
        raise HTTPException(
            status_code=404,
            detail="No results found. Call POST /{job_id}/match first.",
        )
    result = dict(_match_results_cache[job_id])
    result["from_cache"] = True
    return result


@router.get("/{job_id}/candidates")
async def get_job_candidates(job_id: str):
    """
    Return candidates for a job posting.
    Returns cached results instantly if available.
    On first call: runs the full AI matching pipeline automatically.
    """
    if job_id in _match_results_cache:
        return _match_results_cache[job_id].get("candidates", [])
    # First call → run matching synchronously
    result = await match_job(job_id)
    return result.get("candidates", [])
