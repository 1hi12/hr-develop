"""
CandidateRepository — implements ICandidateRepository.
Persists structured candidate data to PostgreSQL.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy import select, delete

from app.core.ports.candidate_repo import ICandidateRepository
from app.core.entities.candidate import Candidate, Experience, Education
from app.core.value_objects.seniority import SeniorityLevel
from app.core.value_objects.skill import ExtractedSkills
from app.infrastructure.database.models import CandidateModel, ExperienceModel, EducationModel
from app.infrastructure.database.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


class CandidateRepository(ICandidateRepository):

    async def save(self, candidate: Candidate) -> None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                skills_json = None
                if candidate.extracted_skills:
                    skills_json = candidate.extracted_skills.model_dump()

                # Every CV upload is its own row (candidate_id), independent of whether
                # other CVs belong to the same person. Grouping by person happens at
                # read time via identity_id (see app/core/value_objects/identity.py
                # and CandidateModel.identity_id) — not by merging rows here.
                existing = await session.get(CandidateModel, candidate.candidate_id)
                identity_id = candidate.identity_id or str(uuid.uuid4())

                if existing:
                    existing.filename               = candidate.filename
                    existing.full_name              = candidate.full_name
                    existing.email                  = candidate.email
                    existing.phone                  = candidate.phone
                    existing.identity_id            = identity_id
                    existing.location               = candidate.location
                    existing.linkedin               = candidate.linkedin
                    existing.github                 = candidate.github
                    existing.summary                = candidate.summary
                    existing.seniority_level        = candidate.seniority_level.value
                    existing.total_years_experience = candidate.total_years_experience
                    existing.extraction_confidence  = candidate.extraction_confidence
                    existing.skills_json            = skills_json
                    existing.languages_json         = candidate.languages
                    existing.cv_raw_text            = candidate.raw_text
                else:
                    session.add(CandidateModel(
                        candidate_id           =candidate.candidate_id,
                        identity_id            =identity_id,
                        filename               =candidate.filename,
                        full_name              =candidate.full_name,
                        email                  =candidate.email,
                        phone                  =candidate.phone,
                        location               =candidate.location,
                        linkedin               =candidate.linkedin,
                        github                 =candidate.github,
                        summary                =candidate.summary,
                        seniority_level        =candidate.seniority_level.value,
                        total_years_experience =candidate.total_years_experience,
                        extraction_confidence  =candidate.extraction_confidence,
                        skills_json            =skills_json,
                        languages_json         =candidate.languages,
                        cv_raw_text            =candidate.raw_text,
                    ))

                # Delete and re-insert experiences and education
                await session.execute(
                    delete(ExperienceModel).where(
                        ExperienceModel.candidate_id == candidate.candidate_id
                    )
                )
                await session.execute(
                    delete(EducationModel).where(
                        EducationModel.candidate_id == candidate.candidate_id
                    )
                )

                for exp in candidate.experiences:
                    session.add(ExperienceModel(
                        candidate_id   =candidate.candidate_id,
                        company        =exp.company,
                        title          =exp.title,
                        start_date     =exp.start_date,
                        end_date       =exp.end_date,
                        duration_months=exp.duration_months,
                        description    =exp.description,
                        location       =exp.location,
                    ))

                for edu in candidate.education:
                    session.add(EducationModel(
                        candidate_id   =candidate.candidate_id,
                        institution    =edu.institution,
                        degree         =edu.degree,
                        field_of_study =edu.field_of_study,
                        graduation_year=edu.graduation_year,
                    ))

        logger.info(
            "[CandidateRepo] Saved: %s (%s)",
            candidate.candidate_id[:8], candidate.full_name or "unknown",
        )

    async def get_by_id(self, candidate_id: str) -> Optional[Candidate]:
        async with AsyncSessionLocal() as session:
            row = await session.get(CandidateModel, candidate_id)
            if not row:
                return None

            exp_result = await session.execute(
                select(ExperienceModel).where(
                    ExperienceModel.candidate_id == candidate_id
                )
            )
            edu_result = await session.execute(
                select(EducationModel).where(
                    EducationModel.candidate_id == candidate_id
                )
            )

            experiences = [
                Experience(
                    company=e.company, title=e.title,
                    start_date=e.start_date, end_date=e.end_date,
                    duration_months=e.duration_months,
                    description=e.description, location=e.location,
                )
                for e in exp_result.scalars()
            ]
            education = [
                Education(
                    institution=e.institution, degree=e.degree,
                    field_of_study=e.field_of_study,
                    graduation_year=e.graduation_year,
                )
                for e in edu_result.scalars()
            ]

            extracted_skills = None
            if row.skills_json:
                try:
                    extracted_skills = ExtractedSkills(**row.skills_json)
                except Exception:
                    pass

            try:
                seniority = SeniorityLevel(row.seniority_level)
            except ValueError:
                seniority = SeniorityLevel.UNKNOWN

            return Candidate(
                candidate_id           =row.candidate_id,
                identity_id            =row.identity_id,
                filename               =row.filename,
                full_name              =row.full_name,
                email                  =row.email,
                phone                  =row.phone,
                location               =row.location,
                linkedin               =row.linkedin,
                github                 =row.github,
                summary                =row.summary,
                languages              =row.languages_json or [],
                seniority_level        =seniority,
                total_years_experience =row.total_years_experience,
                extraction_confidence  =row.extraction_confidence,
                extracted_skills       =extracted_skills,
                experiences            =experiences,
                education              =education,
            )

    async def delete(self, candidate_id: str) -> None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    delete(ExperienceModel).where(
                        ExperienceModel.candidate_id == candidate_id
                    )
                )
                await session.execute(
                    delete(EducationModel).where(
                        EducationModel.candidate_id == candidate_id
                    )
                )
                await session.execute(
                    delete(CandidateModel).where(
                        CandidateModel.candidate_id == candidate_id
                    )
                )
        logger.info("[CandidateRepo] Deleted: %s", candidate_id[:8])
