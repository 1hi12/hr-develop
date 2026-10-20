"""
IngestCVUseCase
===============
Orchestrates CV ingestion via LangGraph pipeline.

Deduplication:
  SHA-256(file_bytes) → candidate_id
  If candidate_exists(hash) in Milvus → return cached result, skip everything.
  Same CV uploaded 10 times = LLM + embedding runs exactly once.

Parallel storage:
  Milvus.store_candidate() + candidate_repo.save() run simultaneously.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid

from app.application.pipelines.ingestion_graph import build_ingestion_graph
from app.application.dtos.ingest_dto import IngestCVRequest, IngestCVResult
from app.core.entities.candidate import (
    Candidate, Chunk, EmbeddedChunk, Experience, Education,
)
from app.core.value_objects.identity import compute_identity_id
from app.core.ports.candidate_repo import ICandidateRepository
from app.core.ports.document_parser import IDocumentParser
from app.core.ports.embedder import IEmbedder
from app.core.ports.llm_extractor import ILLMExtractor
from app.core.ports.vector_store import IVectorStore
from app.core.value_objects.seniority import SeniorityLevel
from app.core.value_objects.skill import Skill, ExtractedSkills

logger = logging.getLogger(__name__)


class IngestCVUseCase:

    def __init__(
        self,
        parser:         IDocumentParser,
        extractor:      ILLMExtractor,
        embedder:       IEmbedder,
        vector_store:   IVectorStore,
        candidate_repo: ICandidateRepository,
    ) -> None:
        self._parser         = parser
        self._extractor      = extractor
        self._embedder       = embedder
        self._vector_store   = vector_store
        self._candidate_repo = candidate_repo
        self._graph = build_ingestion_graph(
            parser, extractor, embedder, vector_store
        )

    async def execute(self, request: IngestCVRequest) -> IngestCVResult:
        logger.info("[IngestCV] Starting: %s", request.filename)

        # Use the candidate_id provided by the caller (already created in PostgreSQL).
        # We compute the hash only for Milvus dedup check.
        candidate_id = request.candidate_id
        sha_bytes    = hashlib.sha256(request.file_bytes).digest()
        cv_hash      = str(uuid.UUID(bytes=sha_bytes[:16]))

        # P2 fix: utiliser cv_hash (SHA-256 du fichier) et non candidate_id (UUID PostgreSQL)
        # candidate_id est différent à chaque upload — cv_hash identifie le fichier de façon unique
        if await self._vector_store.candidate_exists(cv_hash):
            logger.info("[IngestCV] Duplicate CV — returning cached result")
            return await self._return_cached(cv_hash, request.filename)

        # ── LangGraph pipeline (parallel LLM + chunking) ──────────────────────
        state = await self._graph.ainvoke({
            "file_bytes":     request.file_bytes,
            "filename":       request.filename,
            "candidate_id":   candidate_id,
            "cv_hash":        cv_hash,
            "is_duplicate":   False,
            "raw_text":       "",
            "general":        {},
            "skills_raw":     {},
            "seniority_raw":  {},
            "chunks":         [],
            "embedded_chunks": [],
            "error":          None,
        })

        if state.get("error"):
            raise ValueError(state["error"])

        # ── Assemble domain entity ─────────────────────────────────────────────
        candidate = self._assemble(
            request        =request,
            candidate_id   =candidate_id,
            raw_text       =state["raw_text"],
            general        =state["general"],
            skills_raw     =state["skills_raw"],
            seniority_raw  =state["seniority_raw"],
            chunks         =state["chunks"],
            embedded_chunks=state["embedded_chunks"],
        )

        # ── Parallel storage: Milvus + PostgreSQL simultaneously ──────────────
        skills_json = json.dumps(
            candidate.extracted_skills.all_skills
            if candidate.extracted_skills else []
        )
        await asyncio.gather(
            self._vector_store.store_candidate(
                candidate_id=candidate.candidate_id,
                filename    =candidate.filename,
                chunks      =candidate.embedded_chunks,
                skills_json =skills_json,
            ),
            self._candidate_repo.save(candidate),
        )

        logger.info(
            "[IngestCV] Done: %s | chunks=%d | skills=%d | confidence=%.2f",
            request.filename,
            len(candidate.embedded_chunks),
            len(candidate.extracted_skills.all_skills) if candidate.extracted_skills else 0,
            candidate.extraction_confidence or 0.0,
        )

        return IngestCVResult(
            candidate_id =candidate.candidate_id,
            filename     =candidate.filename,
            chunks_count =len(candidate.embedded_chunks),
            skills_count =len(candidate.extracted_skills.all_skills) if candidate.extracted_skills else 0,
            confidence   =candidate.extraction_confidence or 0.0,
            full_name    =candidate.full_name or "",
            email        =candidate.email or "",
            seniority    =candidate.seniority_level.value,
            years_exp    =candidate.total_years_experience or 0.0,
        )

    # ── Cached result for duplicate CVs ───────────────────────────────────────

    async def _return_cached(self, cv_hash: str, filename: str) -> IngestCVResult:
        candidate = await self._candidate_repo.get_by_id(cv_hash)
        if candidate:
            return IngestCVResult(
                candidate_id =cv_hash,
                filename     =candidate.filename,
                chunks_count =len(candidate.chunks) if candidate.chunks else 0,
                skills_count =len(candidate.extracted_skills.all_skills) if candidate.extracted_skills else 0,
                confidence   =candidate.extraction_confidence or 0.0,
                status       ="duplicate",
                full_name    =candidate.full_name or "",
                email        =candidate.email or "",
                seniority    =candidate.seniority_level.value,
                years_exp    =candidate.total_years_experience or 0.0,
            )
        return IngestCVResult(
            candidate_id=cv_hash,
            filename    =filename,
            chunks_count=0,
            skills_count=0,
            confidence  =0.0,
            status      ="duplicate",
        )

    # ── Domain entity assembly ─────────────────────────────────────────────────

    def _assemble(
        self,
        request:         IngestCVRequest,
        candidate_id:    str,
        raw_text:        str,
        general:         dict,
        skills_raw:      dict,
        seniority_raw:   dict,
        chunks:          list,
        embedded_chunks: list[EmbeddedChunk],
    ) -> Candidate:
        # P1 fix: "skills" clé n'existe plus — lire depuis all_skills avec fallback
        skills = []
        for s in skills_raw.get("all_skills", skills_raw.get("skills", [])):
            try:
                skills.append(Skill(name=str(s)) if isinstance(s, str) else Skill(**s))
            except Exception:
                pass

        experiences = []
        for exp in seniority_raw.get("experiences", []):
            try:
                experiences.append(Experience(**exp))
            except Exception:
                pass

        education = []
        for edu in seniority_raw.get("education", []):
            try:
                education.append(Education(**edu))
            except Exception:
                pass

        try:
            seniority = SeniorityLevel(seniority_raw.get("seniority_level", "unknown"))
        except ValueError:
            seniority = SeniorityLevel.UNKNOWN

        extracted_skills = ExtractedSkills(
            technical  =skills_raw.get("technical", []),
            frameworks =skills_raw.get("frameworks", []),
            databases  =skills_raw.get("databases", []),
            devops     =skills_raw.get("devops", []),
            soft_skills=skills_raw.get("soft_skills", []),
            languages  =skills_raw.get("languages", []),
            all_skills =skills_raw.get("all_skills", []),
        )

        cv_chunks = [
            Chunk(
                chunk_id       =c.chunk_id,
                text           =c.text,
                section        =c.section,
                chunk_index    =c.chunk_index,
                source_filename=c.source_filename,
            )
            for c in chunks
        ]

        filled = sum([
            bool(general.get("full_name")),
            bool(general.get("email")),
            bool(extracted_skills.all_skills),
            bool(experiences),
        ])
        confidence = round(filled / 4.0, 2)

        return Candidate(
            candidate_id          =candidate_id,
            identity_id           =compute_identity_id(
                general.get("full_name"), general.get("email"), general.get("phone"),
            ),
            filename              =request.filename,
            full_name             =general.get("full_name"),
            email                 =general.get("email"),
            phone                 =general.get("phone"),
            location              =general.get("location"),
            linkedin              =general.get("linkedin"),
            github                =general.get("github"),
            summary               =general.get("summary"),
            languages             =general.get("languages", []),
            skills                =skills,
            experiences           =experiences,
            education             =education,
            seniority_level       =seniority,
            total_years_experience=seniority_raw.get("total_years_experience"),
            raw_text              =raw_text,
            chunks                =cv_chunks,
            embedded_chunks       =embedded_chunks,
            extracted_skills      =extracted_skills,
            extraction_confidence =confidence,
        )
