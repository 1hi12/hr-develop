"""
REPOSITORY — cv_repo
INSERT dans les 3 tables PostgreSQL :
  cv_profiles    : informations générales
  cv_skills      : compétences extraites
  cv_experiences : expériences professionnelles
"""

import logging
import uuid
from typing import Optional

logger = logging.getLogger(__name__)
FieldSchema(name="candidate_id", dtype=DataType.VARCHAR, max_length=100)

async def save_cv_to_db(
    candidate_id: str,
    cv_extracted,
    filename: str,
    job_id: Optional[str] = None,
    db=None,
) -> dict:
    from app.data.postgres.session import get_db_session

    if db is None:
        async with get_db_session() as session:
            return await _insert(session, candidate_id, cv_extracted, filename, job_id)
    return await _insert(db, candidate_id, cv_extracted, filename, job_id)


async def _insert(db, candidate_id, cv, filename, job_id):
    from sqlalchemy import text

    cv_id = str(uuid.uuid4())

    # ── cv_profiles ──────────────────────────────────────
    await db.execute(text("""
        INSERT INTO cv_profiles (
            id, candidate_id, job_id, filename,
            full_name, email, phone, location,
            linkedin, github, summary,
            seniority_level, total_years_experience,
            extraction_confidence, raw_text
        ) VALUES (
            :id, :candidate_id, :job_id, :filename,
            :full_name, :email, :phone, :location,
            :linkedin, :github, :summary,
            :seniority_level, :total_years_experience,
            :extraction_confidence, :raw_text
        )
        ON CONFLICT (candidate_id) DO UPDATE SET
            full_name = EXCLUDED.full_name,
            seniority_level = EXCLUDED.seniority_level,
            extraction_confidence = EXCLUDED.extraction_confidence,
            updated_at = NOW()
    """), {
        "id": cv_id, "candidate_id": candidate_id, "job_id": job_id,
        "filename": filename, "full_name": cv.full_name, "email": cv.email,
        "phone": cv.phone, "location": cv.location, "linkedin": cv.linkedin,
        "github": cv.github, "summary": cv.summary,
        "seniority_level": cv.seniority_level.value,
        "total_years_experience": cv.total_years_experience,
        "extraction_confidence": cv.extraction_confidence,
        "raw_text": cv.raw_text,
    })

    # ── cv_skills ────────────────────────────────────────
    await db.execute(text("DELETE FROM cv_skills WHERE cv_id = :cv_id"), {"cv_id": cv_id})
    for skill in cv.skills:
        await db.execute(text("""
            INSERT INTO cv_skills (id, cv_id, name, category, level, years_of_experience)
            VALUES (:id, :cv_id, :name, :category, :level, :years)
        """), {
            "id": str(uuid.uuid4()), "cv_id": cv_id,
            "name": skill.name, "category": skill.category,
            "level": skill.level, "years": skill.years_of_experience,
        })

    # ── cv_experiences ───────────────────────────────────
    await db.execute(text("DELETE FROM cv_experiences WHERE cv_id = :cv_id"), {"cv_id": cv_id})
    for exp in cv.experiences:
        await db.execute(text("""
            INSERT INTO cv_experiences (
                id, cv_id, company, title, start_date,
                end_date, duration_months, description, location
            ) VALUES (
                :id, :cv_id, :company, :title, :start_date,
                :end_date, :duration_months, :description, :location
            )
        """), {
            "id": str(uuid.uuid4()), "cv_id": cv_id,
            "company": exp.company, "title": exp.title,
            "start_date": exp.start_date, "end_date": exp.end_date,
            "duration_months": exp.duration_months,
            "description": exp.description, "location": exp.location,
        })

    await db.commit()
    logger.info(f"[Repo] CV sauvegardé — cv_id={cv_id}")
    return {"cv_id": cv_id, "candidate_id": candidate_id}
