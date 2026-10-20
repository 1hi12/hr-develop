"""
multi_worker_single_adapter.py
==============================
Bridges MultiWorkerExtractor (batch API) ↔ ILLMExtractor (single-CV API).

The existing IngestCVUseCase expects:
    extractor.extract(cv_text) → (general: dict, skills: dict, seniority: dict)

MultiWorkerExtractor works on batches of up to 10 CVs.
This adapter sends a batch of 1 and converts the returned dict back
to the (general, skills, seniority) triple the use-case needs.

Result
------
  general:  { full_name, email, phone, location, linkedin, github,
               summary, languages }
  skills:   { technical, frameworks, databases, devops, soft_skills,
               languages, all_skills }
  seniority:{ seniority_level, total_years_experience,
               experiences, education }
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.ports.llm_extractor import ILLMExtractor
from app.infrastructure.llm.multi_worker_extractor import MultiWorkerExtractor

logger = logging.getLogger(__name__)


class MultiWorkerSingleAdapter(ILLMExtractor):
    """
    Drop-in replacement for GeminiExtractor / OllamaExtractor.
    Internally calls MultiWorkerExtractor with a batch-of-1 so that
    single-file uploads also benefit from the 3-model worker pool.
    """

    def __init__(self) -> None:
        self._worker = MultiWorkerExtractor()

    async def extract(
        self, cv_text: str
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """
        Send cv_text as a single-item batch, then reformat the result
        into the (general, skills, seniority) triple expected by IngestCVUseCase.
        """
        results, model_used = await self._worker.extract_batch([cv_text])
        cv: dict[str, Any] = results[0] if results else {}

        logger.info(
            "[MultiWorkerSingle] Extracted via %s — name=%s skills=%d",
            model_used,
            cv.get("name", "?"),
            len(cv.get("skills", []) or []),
        )

        # ── general info ──────────────────────────────────────────────────────
        general: dict[str, Any] = {
            "full_name": cv.get("name"),
            "email":     cv.get("email"),
            "phone":     cv.get("phone"),
            "location":  cv.get("location"),
            "linkedin":  None,
            "github":    None,
            "summary":   cv.get("summary"),
            "languages": cv.get("languages") or [],
        }

        # ── skills ────────────────────────────────────────────────────────────
        all_skills: list[str] = [
            s for s in (cv.get("skills") or []) if isinstance(s, str) and s.strip()
        ]
        skills: dict[str, Any] = {
            "technical":  all_skills,
            "frameworks": [],
            "databases":  [],
            "devops":     [],
            "soft_skills":[],
            "languages":  cv.get("languages") or [],
            "all_skills": all_skills,
        }

        # ── seniority + experience ─────────────────────────────────────────────
        raw_exps = cv.get("experiences") or []
        experiences = [e for e in raw_exps if isinstance(e, dict)]

        raw_edus = cv.get("education") or []
        education = [e for e in raw_edus if isinstance(e, dict)]

        seniority: dict[str, Any] = {
            "seniority_level":        cv.get("seniority") or "unknown",
            "total_years_experience": cv.get("years_exp"),
            "experiences":            experiences,
            "education":              education,
        }

        return general, skills, seniority
