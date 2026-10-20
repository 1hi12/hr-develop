"""
MatchCandidatesUseCase
======================
Orchestrates Phases 7-9: vector search -> LLM rerank -> response.
Depends only on port interfaces.
"""

from __future__ import annotations

import logging

from app.config.settings import settings
from app.core.ports.vector_store import IVectorStore
from app.core.ports.llm_ranker import ILLMRanker
from app.core.ports.embedder import IEmbedder
from app.core.entities.job import JobDescription
from app.application.dtos.match_dto import MatchRequest, MatchResponse

logger = logging.getLogger(__name__)


class MatchCandidatesUseCase:

    def __init__(
        self,
        embedder:     IEmbedder,
        vector_store: IVectorStore,
        ranker:       ILLMRanker,
    ) -> None:
        self._embedder     = embedder
        self._vector_store = vector_store
        self._ranker       = ranker

    async def execute(self, request: MatchRequest) -> MatchResponse:
        logger.info(
            "[MatchCandidates] top_k=%d, min_score=%.2f, reranking=%s",
            request.top_k, request.min_score, request.use_reranking,
        )

        # Phase 7: vector search
        query_text = request.job_description
        if request.required_skills:
            query_text += "\nRequired skills: " + ", ".join(request.required_skills)

        query_embedding = await self._embedder.embed_single(query_text)

        search_results = await self._vector_store.search(
            query_embedding=query_embedding,
            top_k=request.top_k * 2,  # over-select for reranking
            min_score=request.min_score,
        )

        if not search_results:
            return MatchResponse(
                candidates=[],
                recruiter_advice="No candidates found for this job description.",
            )

        # Phase 8: LLM reranking (or pure vector order)
        if request.use_reranking:
            jd     = JobDescription(text=request.job_description)
            cv_ids = [r.candidate_id for r in search_results]

            try:
                selected, thinking_log = await self._ranker.rank(
                    job_description=jd,
                    cv_ids=cv_ids,
                )
                for msg in thinking_log:
                    logger.info("[thinking] %s", msg)
            except Exception as e:
                logger.exception("LLM reranking failed: %s — using vector order", e)
                selected = []

            if selected:
                ranked = self._merge_reranked(selected[:request.top_k], search_results)
            else:
                ranked = self._vector_fallback(search_results, request.top_k)
        else:
            ranked = self._vector_fallback(search_results, request.top_k)

        # Phase 9: format response
        return self._format_response(ranked, request)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _merge_reranked(
        self,
        selected: list[dict],
        search_results: list,
    ) -> list[dict]:
        meta_by_id = {r.candidate_id: r for r in search_results}
        merged = []

        for item in selected:
            cid  = str(item.get("cv_id", ""))
            meta = meta_by_id.get(cid)
            expl = item.get("explanation", {})

            if isinstance(expl, str):
                expl = {"explanation": expl, "status": "selected"}

            if not meta:
                for known_id, known_meta in meta_by_id.items():
                    if cid in known_id or known_id in cid:
                        meta = known_meta
                        break

            merged.append({
                "candidate_id"    : cid,
                "filename"        : meta.filename if meta else expl.get("candidate_info", {}).get("path", ""),
                "score"           : meta.score if meta else 0.0,
                "relevance_score" : item.get("relevance_score", 0.0),
                "similarity_score": item.get("similarity_score", 0.0),
                "excerpt"         : meta.excerpt if meta else "",
                "explanation"     : expl,
            })

        return merged

    def _vector_fallback(self, search_results: list, top_k: int) -> list[dict]:
        return [
            {
                "candidate_id"    : r.candidate_id,
                "filename"        : r.filename,
                "score"           : r.score,
                "relevance_score" : r.score,
                "similarity_score": r.score,
                "excerpt"         : r.excerpt,
                "explanation"     : {
                    "status"        : "selected" if r.score >= settings.selection_threshold else "rejected",
                    "candidate_info": {
                        "name" : r.filename,
                        "email": "N/A",
                        "phone": "N/A",
                        "path" : r.filename,
                    },
                    "explanation": "Automatic evaluation (vector fallback).",
                },
            }
            for r in search_results[:top_k]
        ]

    def _format_response(
        self, ranked: list[dict], request: MatchRequest
    ) -> MatchResponse:
        skills_str = ", ".join(request.required_skills) if request.required_skills else "not specified"
        candidates = []

        for rank, c in enumerate(ranked, start=1):
            expl = c.get("explanation", {})
            if isinstance(expl, str):
                expl = {"explanation": expl, "status": "selected"}

            candidate_info = expl.get("candidate_info") or {
                "name" : c.get("filename", c["candidate_id"]),
                "email": "N/A",
                "phone": "N/A",
                "path" : c.get("filename", ""),
            }

            candidates.append({
                "rank"            : rank,
                "candidate_id"    : c["candidate_id"],
                "filename"        : c.get("filename", ""),
                "score"           : c.get("score", 0.0),
                "relevance_score" : c.get("relevance_score", 0.0),
                "similarity_score": c.get("similarity_score", 0.0),
                "status"          : expl.get("status", "selected"),
                "candidate_info"  : candidate_info,
                "presentation"    : expl.get("explanation", "Analysis unavailable."),
                "excerpt"         : c.get("excerpt", ""),
            })

        n_selected = sum(
            1 for c in candidates
            if c.get("relevance_score", 0) >= settings.selection_threshold
        )
        avg_score = (
            sum(c.get("relevance_score", 0) for c in candidates) / len(candidates)
            if candidates else 0.0
        )

        recruiter_advice = (
            f"{n_selected} candidate(s) out of {len(candidates)} exceed the relevance threshold "
            f"(average score: {avg_score:.0%}). "
            f"Required skills: {skills_str}. "
            "Review individual profiles for full skill match details."
        )

        return MatchResponse(candidates=candidates, recruiter_advice=recruiter_advice)
