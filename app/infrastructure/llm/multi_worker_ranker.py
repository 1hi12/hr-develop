"""
multi_worker_ranker.py
======================
RAG-based ranker using gpt-4o (primary) with Llama 3.1 8B fallback.

Pipeline
--------
  1. Retrieve CV text chunks from Milvus (already fetched by the use-case)
  2. Reconstruct full CV text per candidate from its chunks
  3. Compute vector cosine similarity (embedding-level pre-ranking)
  4. Send job description + CV texts to gpt-4o via LiteLLM proxy
  5. Return per-candidate: exact score, analytical description, why chosen,
     matched / missing skills, experience assessment

Each candidate response
-----------------------
  cv_id              : candidate UUID
  score              : int 0-100
  recommendation     : "selected" | "reserve" | "rejected"
  cv_summary         : 2-3 sentence profile description
  why_chosen         : why this candidate does/doesn't match
  matched_skills     : skills from the CV that match the job
  missing_skills     : required skills the candidate lacks
  technical_fit      : float 0.0-1.0
  culture_fit        : float 0.0-1.0
  growth_fit         : float 0.0-1.0
  experience_assessment: seniority / years vs job requirements
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import ssl
import time
import warnings
from collections import defaultdict
from typing import Any

import httpx
import numpy as np
from openai import AsyncOpenAI

# ── SSL override for corporate / proxy network ────────────────────────────────
os.environ["PYTHONHTTPSVERIFY"]  = "0"
os.environ["REQUESTS_CA_BUNDLE"] = ""
os.environ["SSL_CERT_FILE"]      = ""
warnings.filterwarnings("ignore")
ssl._create_default_https_context = ssl._create_unverified_context  # type: ignore[attr-defined]
ssl.create_default_context = lambda *a, **kw: ssl._create_unverified_context(*a, **kw)  # type: ignore[attr-defined]

from app.config.settings import settings
from app.core.ports.llm_ranker import ILLMRanker
from app.core.ports.vector_store import IVectorStore
from app.core.ports.embedder import IEmbedder
from app.core.entities.job import JobDescription

logger = logging.getLogger(__name__)

# ── RAG scoring prompt ────────────────────────────────────────────────────────

_RANK_PROMPT = """\
You are a strict senior HR analyst. Evaluate each CV against the job description.
You MUST apply the seniority rules below before computing the score.

═══ SENIORITY RULES (MANDATORY) ═══════════════════════════════════
• The job requires: {required_seniority}
• Seniority levels (low → high): intern < junior < mid < senior < lead < executive
• If the candidate's level is MORE THAN ONE STEP below the requirement:
    → score MUST NOT exceed 35
    → recommendation MUST be "rejected"
• If the candidate's level is exactly one step below:
    → score MUST NOT exceed 55
    → recommendation = "reserve"
• Seniority match or above → score can reach 100
• "Stagiaire", "étudiant", "apprenti", "intern" = intern level
════════════════════════════════════════════════════════════════════

JOB DESCRIPTION:
{job_description}

---

CVs TO EVALUATE (separated by ===CV_SEP===):
{cvs_block}

---

Return a JSON array with exactly {n} objects, one per CV, in the SAME ORDER:

{{
  "cv_id"                 : "<copy the exact CV ID shown above>",
  "score"                 : <integer 0-100>,
  "recommendation"        : "selected" | "reserve" | "rejected",
  "candidate_seniority"   : "<detected level: intern|junior|mid|senior|lead|executive>",
  "cv_summary"            : "<2-3 sentences: who is this person, their background>",
  "why_chosen"            : "<2-3 sentences explaining the score — mention seniority gap if any>",
  "matched_skills"        : ["skill1", "skill2", ...],
  "missing_skills"        : ["skill1", ...],
  "technical_fit"         : <float 0.0-1.0>,
  "culture_fit"           : <float 0.0-1.0>,
  "growth_fit"            : <float 0.0-1.0>,
  "experience_assessment" : "<years of experience vs requirement, seniority gap explanation>"
}}

IMPORTANT: Reply ONLY with a valid JSON array. No markdown, no commentary.
"""


# ── JSON helpers ──────────────────────────────────────────────────────────────

def _parse_ranking(raw: str, expected: int) -> list[dict]:
    cleaned = re.sub(r"```json\s*", "", raw)
    cleaned = re.sub(r"```\s*",     "", cleaned).strip()
    try:
        result = json.loads(cleaned)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            # LLM returned a single object instead of a 1-element array
            return [result]
    except json.JSONDecodeError:
        pass
    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(0))
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
    # Try extracting a single object
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(0))
            if isinstance(result, dict):
                return [result]
        except json.JSONDecodeError:
            pass
    logger.warning("[MultiWorkerRanker] JSON parse failed. Raw (300 chars): %s", raw[:300])
    return []


# ── Seniority helpers ─────────────────────────────────────────────────────────

_SENIORITY_ORDER = ["intern", "junior", "mid", "senior", "lead", "executive"]

# French + English keywords per level
_SENIORITY_KEYWORDS: dict[str, list[str]] = {
    "intern":    ["intern", "stagiaire", "stage", "apprenti", "alternant",
                  "étudiant", "student", "trainee", "apprentice"],
    "junior":    ["junior", "jr.", "jr ", "débutant", "entry level",
                  "entry-level", "moins de 2 ans", "0-2 ans", "1 an"],
    "mid":       ["mid", "intermédiaire", "confirmé", "2-5 ans", "3 ans",
                  "4 ans", "5 ans"],
    "senior":    ["senior", "sr.", "sr ", "expérimenté", "experienced",
                  "5+ ans", "6 ans", "7 ans", "8 ans", "10 ans"],
    "lead":      ["lead", "principal", "staff", "architect", "head of",
                  "directeur technique", "tech lead", "team lead",
                  "responsable technique"],
    "executive": ["executive", "vp ", "vice president", "cto", "cio",
                  "c-level", "directeur général", "chief"],
}

def _detect_required_seniority(text: str) -> str:
    """Detect required seniority from job title / description (FR + EN)."""
    t = text.lower()
    # Check from highest to lowest to pick the right level
    for level in reversed(_SENIORITY_ORDER):
        if any(kw in t for kw in _SENIORITY_KEYWORDS[level]):
            return level
    return "mid"

def _detect_candidate_seniority(llm_level: str, db_level: str) -> str:
    """Resolve candidate seniority: prefer LLM detection, fallback to DB."""
    clean = (llm_level or "").lower().strip()
    # Normalise French/English to canonical level
    for level, keywords in _SENIORITY_KEYWORDS.items():
        if clean == level or any(kw in clean for kw in keywords):
            return level
    # Fallback to DB
    db = (db_level or "").lower().strip()
    for level, keywords in _SENIORITY_KEYWORDS.items():
        if db == level or any(kw in db for kw in keywords):
            return level
    return "mid"

def _seniority_hard_cap(candidate_level: str, required_level: str) -> float | None:
    """
    Hard-cap the score when the candidate is below the requirement.
    Returns None when no cap applies (same level or above).
    """
    try:
        c_idx = _SENIORITY_ORDER.index(candidate_level)
        r_idx = _SENIORITY_ORDER.index(required_level)
    except ValueError:
        return None
    gap = r_idx - c_idx
    if gap >= 3:   # intern vs senior/lead → absolute cap 20%
        return 0.20
    if gap == 2:   # junior vs senior, intern vs mid → cap 35%
        return 0.35
    if gap == 1:   # mid vs senior, junior vs mid → soft cap 55%
        return 0.55
    return None    # on level or above → no cap


# ── MultiWorkerRanker ─────────────────────────────────────────────────────────

class MultiWorkerRanker(ILLMRanker):
    """
    RAG ranker using Qwen2-72B via vLLM (OpenAI-compatible).
    Milvus chunk retrieval → LLM analytical scoring.
    """

    def __init__(self, vector_store: IVectorStore, embedder: IEmbedder) -> None:
        self._vector_store = vector_store
        self._embedder     = embedder
        self._semaphore    = asyncio.Semaphore(settings.llm_max_concurrency)
        self._litellm_client = AsyncOpenAI(
            api_key=settings.litellm_api_key,
            base_url=settings.litellm_base_url,
            max_retries=0,
            http_client=httpx.AsyncClient(verify=False),
        )
        logger.info("MultiWorkerRanker initialised (Qwen2-72B via vLLM at %s)", settings.litellm_base_url)

    # ── ILLMRanker ────────────────────────────────────────────────────────────

    async def rank(
        self,
        job_description: JobDescription,
        cv_ids: list[str],
        job_title: str = "",
    ) -> tuple[list[dict], list[str]]:
        thinking: list[str] = []
        if not cv_ids:
            return [], thinking

        # ── Step 1: Retrieve CV chunks from Milvus ────────────────────────────
        thinking.append(f"Retrieving chunks for {len(cv_ids)} candidate(s)…")
        raw_chunks = await self._vector_store.fetch_chunks_by_candidate_ids(cv_ids)
        cv_texts   = self._build_cv_texts(raw_chunks)
        thinking.append(f"{len(cv_texts)} candidate(s) with text after retrieval.")

        if not cv_texts:
            thinking.append("No CV text found in vector store — vector fallback.")
            return [], thinking

        # ── Step 2: Vector cosine similarity (pre-rank, used as fallback) ─────
        thinking.append("Computing vector similarities…")
        sim_scores = await self._cosine_similarities(job_description, cv_texts)

        # ── Step 3: Detect required seniority from job title ─────────────────
        required_seniority = _detect_required_seniority(job_title or job_description.text)
        thinking.append(f"Required seniority detected: {required_seniority}")

        # ── Step 4: LLM analytical scoring (in batches) ──────────────────────
        batch_size  = settings.reranking_batch_size
        ids_list    = list(cv_texts.keys())
        all_results : list[dict] = []

        for i in range(0, len(ids_list), batch_size):
            batch_ids  = ids_list[i : i + batch_size]
            batch_text = {cid: cv_texts[cid] for cid in batch_ids}
            bn = i // batch_size + 1
            bt = (len(ids_list) + batch_size - 1) // batch_size
            thinking.append(f"LLM batch {bn}/{bt} — {len(batch_ids)} CV(s)…")
            batch_out = await self._score_batch(
                job_description, batch_text, job_title, sim_scores, required_seniority
            )
            all_results.extend(batch_out)

        # ── Step 4: Sort and filter ───────────────────────────────────────────
        all_results.sort(key=lambda x: x["relevance_score"], reverse=True)
        selected = [
            r for r in all_results
            if r["relevance_score"] >= settings.selection_threshold
        ]
        thinking.append(
            f"{len(selected)}/{len(all_results)} candidate(s) above threshold "
            f"({settings.selection_threshold:.0%})."
        )
        logger.info(
            "[MultiWorkerRanker] %d/%d selected (threshold=%.2f)",
            len(selected), len(all_results), settings.selection_threshold,
        )
        return selected, thinking

    # ── Chunk reconstruction ──────────────────────────────────────────────────

    def _build_cv_texts(self, raw_chunks: list[dict]) -> dict[str, str]:
        grouped: dict[str, list[tuple[int, str]]] = defaultdict(list)
        for item in raw_chunks:
            if not isinstance(item, dict):
                continue
            cid  = str(item.get("candidate_id") or "unknown")
            text = str(item.get("text") or "")
            idx  = int(item.get("chunk_index", 0) or 0)
            grouped[cid].append((idx, text))

        result: dict[str, str] = {}
        for cid, chunks in grouped.items():
            chunks.sort(key=lambda x: x[0])
            result[cid] = "\n".join(t for _, t in chunks if t.strip())

        logger.info(
            "[MultiWorkerRanker] %d chunks → %d candidates",
            len(raw_chunks), len(result),
        )
        return result

    # ── Vector similarity ─────────────────────────────────────────────────────

    async def _cosine_similarities(
        self, jd: JobDescription, cv_texts: dict[str, str]
    ) -> dict[str, float]:
        jd_vec = np.array(await self._embedder.embed_single(jd.text), dtype=np.float32)
        scores: dict[str, float] = {}
        for cid, text in cv_texts.items():
            if not text.strip():
                scores[cid] = 0.0
                continue
            cv_vec = np.array(
                await self._embedder.embed_single(text[:8000]), dtype=np.float32
            )
            norm = np.linalg.norm(jd_vec) * np.linalg.norm(cv_vec)
            scores[cid] = float(np.dot(jd_vec, cv_vec) / norm) if norm > 0 else 0.0
        return scores

    # ── LLM batch scoring ─────────────────────────────────────────────────────

    async def _score_batch(
        self,
        jd: JobDescription,
        batch: dict[str, str],
        job_title: str,
        sim_scores: dict[str, float],
        required_seniority: str = "not specified",
    ) -> list[dict]:
        jd_text = jd.text
        if job_title:
            jd_text = f"Position: {job_title}\n\n{jd_text}"

        cvs_block = "\n===CV_SEP===\n".join(
            f"CV ID: {cid}\n{text[:3500]}" for cid, text in batch.items()
        )
        prompt = _RANK_PROMPT.format(
            job_description=jd_text,
            cvs_block=cvs_block,
            n=len(batch),
            required_seniority=required_seniority,
        )

        raw = await self._call_llm(prompt)
        parsed = _parse_ranking(raw, len(batch))

        if not parsed:
            logger.warning("[MultiWorkerRanker] LLM returned no results → vector fallback")
            return [self._fallback(cid, sim_scores.get(cid, 0.0)) for cid in batch]

        results: list[dict] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            cid       = str(item.get("cv_id", ""))
            raw_score = item.get("score", 0)
            # Normalise score to 0-1 (LLM returns 0-100)
            if isinstance(raw_score, (int, float)) and raw_score > 1:
                relevance = round(raw_score / 100, 4)
            else:
                relevance = round(float(raw_score or 0), 4)

            # ── Seniority hard cap ────────────────────────────────────────────
            llm_cand_level = item.get("candidate_seniority", "")
            cand_level     = _detect_candidate_seniority(llm_cand_level, "")
            cap            = _seniority_hard_cap(cand_level, required_seniority)
            if cap is not None and relevance > cap:
                logger.info(
                    "[MultiWorkerRanker] Seniority cap: %s (candidate=%s, required=%s) "
                    "%.0f%% → %.0f%%",
                    cid[:8], cand_level, required_seniority,
                    relevance * 100, cap * 100,
                )
                relevance = cap

            sim       = sim_scores.get(cid, 0.0)
            tech_fit  = round(float(item.get("technical_fit") or relevance), 4)
            cult_fit  = round(float(item.get("culture_fit")   or sim),       4)
            grow_fit  = round(float(item.get("growth_fit")    or sim),       4)

            # Apply cap to all fit dimensions too
            if cap is not None:
                tech_fit = min(tech_fit, cap)
                cult_fit = min(cult_fit, cap)
                grow_fit = min(grow_fit, cap)

            if cap is not None:
                rec = "rejected" if cap <= 0.35 else "reserve"
            else:
                rec = item.get("recommendation",
                               "selected" if relevance >= settings.selection_threshold else "rejected")

            why = item.get("why_chosen", "")
            if cap is not None:
                gap_note = (
                    f" ⚠ Seniority gap: job requires {required_seniority}, "
                    f"candidate is {cand_level}."
                )
                why = (why or "") + gap_note

            expl = {
                "status"              : rec,
                "candidate_seniority" : cand_level,
                "required_seniority"  : required_seniority,
                "cv_summary"          : item.get("cv_summary",            ""),
                "why_chosen"          : why,
                "matched_skills"      : item.get("matched_skills",        []),
                "missing_skills"      : item.get("missing_skills",        []),
                "experience"          : item.get("experience_assessment", ""),
                "explanation"         : why,
                "candidate_info"      : {"name": cid, "email": "N/A", "phone": "N/A", "path": ""},
            }
            results.append({
                "cv_id"           : cid,
                "relevance_score" : relevance,
                "similarity_score": round(sim, 4),
                "technical_fit"   : round(tech_fit, 4),
                "culture_fit"     : round(cult_fit, 4),
                "growth_fit"      : round(grow_fit, 4),
                "explanation"     : expl,
            })

        # For any CV the LLM missed, add a vector fallback entry
        returned_ids = {r["cv_id"] for r in results}
        for cid in batch:
            if cid not in returned_ids:
                results.append(self._fallback(cid, sim_scores.get(cid, 0.0)))

        return results

    # ── LLM call — Qwen2-72B via vLLM ───────────────────────────────────────────

    async def _call_llm(self, prompt: str) -> str:
        for attempt in range(1, settings.llm_retries + 1):
            try:
                async with self._semaphore:
                    t0   = time.monotonic()
                    resp = await self._litellm_client.chat.completions.create(
                        model=settings.litellm_model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.0,
                        max_tokens=8192,
                    )
                    ms = int((time.monotonic() - t0) * 1000)
                logger.info("[MultiWorkerRanker] %s scored batch in %d ms", settings.litellm_model, ms)
                return resp.choices[0].message.content or ""
            except Exception as exc:
                if "429" in str(exc) and attempt < settings.llm_retries:
                    await asyncio.sleep(60)
                    continue
                logger.warning(
                    "[MultiWorkerRanker] %s attempt %d failed: %s",
                    settings.litellm_model, attempt, exc,
                )
                if attempt == settings.llm_retries:
                    break
                await asyncio.sleep(2 ** attempt)

        logger.error("[MultiWorkerRanker] Qwen2 failed — vector fallback for batch")
        return ""

    # ── Vector fallback entry ─────────────────────────────────────────────────

    def _fallback(self, cv_id: str, sim: float) -> dict:
        rec = "selected" if sim >= settings.selection_threshold else "rejected"
        return {
            "cv_id"           : cv_id,
            "relevance_score" : round(sim, 4),
            "similarity_score": round(sim, 4),
            "technical_fit"   : round(sim, 4),
            "culture_fit"     : round(sim, 4),
            "growth_fit"      : round(sim, 4),
            "explanation": {
                "status"        : rec,
                "cv_summary"    : "",
                "why_chosen"    : "Score based on vector similarity (LLM unavailable).",
                "matched_skills": [],
                "missing_skills": [],
                "experience"    : "",
                "explanation"   : "Score based on vector similarity (LLM unavailable).",
                "candidate_info": {"name": cv_id, "email": "N/A", "phone": "N/A", "path": ""},
            },
        }
