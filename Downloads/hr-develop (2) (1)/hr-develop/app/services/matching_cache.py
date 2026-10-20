"""
Redis-backed cache for job matching results.

Keys (per language, since the LLM analysis text is language-specific):
  matching:results:{job_id}:{lang}  → serialised MatchingResponse JSON  (TTL 24 h)
  matching:meta:{job_id}:{lang}     → { last_matched_at, candidate_count, candidate_ids_hash }
  matching:pair:{job_hash}:{lang}:{candidate_id}:{candidate_hash}
                                     → one cached LLM score (TTL 7 days)

The results/meta cache above is all-or-nothing per job: a SINGLE new or
changed candidate anywhere invalidates the whole pool (see is_cache_stale),
forcing every candidate to be re-scored even though only one changed. The
pair cache fixes that: job_hash + candidate_hash are baked directly into the
key, so a candidate's score is reused for free as long as neither their data
nor the job's own fields changed — and a content change simply produces a
different key (old entries expire via TTL) rather than needing explicit
invalidation.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis

from app.config.settings import settings
from app.infrastructure.circuit_breaker import redis_breaker, CircuitBreakerOpen

logger = logging.getLogger(__name__)

CACHE_TTL = 86_400  # 24 hours
PAIR_CACHE_TTL = 7 * 86_400  # 7 days — content-addressed, safe to keep longer


def _results_key(job_id: str, lang: str = "fr") -> str:
    return f"matching:results:{job_id}:{lang}"


def _meta_key(job_id: str, lang: str = "fr") -> str:
    return f"matching:meta:{job_id}:{lang}"


def _hash_candidates(candidate_ids: list[str]) -> str:
    joined = ",".join(sorted(candidate_ids))
    return hashlib.sha256(joined.encode()).hexdigest()[:16]


async def _get_client() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


# ── Read ──────────────────────────────────────────────────────────────────────

async def get_cached_results(job_id: str, lang: str = "fr") -> Optional[dict]:
    """Return cached MatchingResponse dict or None."""
    try:
        async with redis_breaker:
            client = await _get_client()
            async with client:
                raw = await client.get(_results_key(job_id, lang))
                if raw is None:
                    return None
                return json.loads(raw)
    except CircuitBreakerOpen:
        logger.warning("[MatchCache] Redis circuit OPEN — skipping cache read for job %s", job_id)
        return None
    except Exception as exc:
        logger.warning("[MatchCache] get_cached_results failed: %s", exc)
        return None


async def get_cached_meta(job_id: str, lang: str = "fr") -> Optional[dict]:
    """Return { last_matched_at, candidate_count, candidate_ids_hash } or None."""
    try:
        async with redis_breaker:
            client = await _get_client()
            async with client:
                raw = await client.get(_meta_key(job_id, lang))
                if raw is None:
                    return None
                return json.loads(raw)
    except CircuitBreakerOpen:
        logger.warning("[MatchCache] Redis circuit OPEN — skipping meta read for job %s", job_id)
        return None
    except Exception as exc:
        logger.warning("[MatchCache] get_cached_meta failed: %s", exc)
        return None


# ── Write ─────────────────────────────────────────────────────────────────────

async def set_cached_results(
    job_id: str,
    results: dict,
    candidate_ids: list[str],
    lang: str = "fr",
) -> None:
    """Store results + meta with 24-hour TTL."""
    try:
        async with redis_breaker:
            client = await _get_client()
            meta = {
                "last_matched_at": datetime.now(timezone.utc).isoformat(),
                "candidate_count": len(candidate_ids),
                "candidate_ids_hash": _hash_candidates(candidate_ids),
            }
            async with client:
                pipe = client.pipeline()
                pipe.set(_results_key(job_id, lang), json.dumps(results), ex=CACHE_TTL)
                pipe.set(_meta_key(job_id, lang), json.dumps(meta), ex=CACHE_TTL)
                await pipe.execute()
        logger.info("[MatchCache] Stored results for job %s/%s (%d candidates)", job_id, lang, len(candidate_ids))
    except CircuitBreakerOpen:
        logger.warning("[MatchCache] Redis circuit OPEN — cache write skipped for job %s", job_id)
    except Exception as exc:
        logger.warning("[MatchCache] set_cached_results failed: %s", exc)


# ── Invalidate ────────────────────────────────────────────────────────────────

async def invalidate(job_id: str) -> None:
    """Delete cached results for a job, in all languages (e.g. after new CV ingested)."""
    try:
        async with redis_breaker:
            client = await _get_client()
            async with client:
                keys = [k for lang in ("fr", "en") for k in (_results_key(job_id, lang), _meta_key(job_id, lang))]
                await client.delete(*keys)
        logger.info("[MatchCache] Invalidated cache for job %s", job_id)
    except CircuitBreakerOpen:
        logger.warning("[MatchCache] Redis circuit OPEN — invalidate skipped for job %s", job_id)
    except Exception as exc:
        logger.warning("[MatchCache] invalidate failed: %s", exc)


async def invalidate_all() -> None:
    """Delete ALL matching caches (called after any new CV is added)."""
    try:
        async with redis_breaker:
            client = await _get_client()
            async with client:
                keys = await client.keys("matching:*")
                if keys:
                    await client.delete(*keys)
        logger.info("[MatchCache] Invalidated all matching caches (%d keys)", len(keys) if keys else 0)
    except CircuitBreakerOpen:
        logger.warning("[MatchCache] Redis circuit OPEN — invalidate_all skipped")
    except Exception as exc:
        logger.warning("[MatchCache] invalidate_all failed: %s", exc)


# ── Per-(candidate, job) score cache ─────────────────────────────────────────

def job_content_hash(job_title: str, job_description: str, required_skills: list[str], job_seniority: Optional[str]) -> str:
    """Changes whenever the job fields that actually affect scoring change."""
    parts = [job_title, job_description or "", ",".join(sorted(required_skills or [])), job_seniority or ""]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def candidate_content_hash(
    skills: list[str], seniority: str, years_exp, cv_summary: str, experience_titles: str = "",
) -> str:
    """Changes whenever the candidate fields that actually affect scoring change."""
    parts = [
        ",".join(sorted(skills or [])), seniority or "", str(years_exp or ""),
        cv_summary or "", experience_titles or "",
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _pair_key(job_hash: str, lang: str, candidate_id: str, candidate_hash: str) -> str:
    return f"matching:pair:{job_hash}:{lang}:{candidate_id}:{candidate_hash}"


async def get_cached_pair_scores(
    job_hash: str,
    lang: str,
    candidates: list[tuple[str, str]],  # [(candidate_id, candidate_hash), ...]
) -> dict[str, dict]:
    """Batch-fetch cached scores. Returns {candidate_id: score_dict} for hits only."""
    if not candidates:
        return {}
    try:
        async with redis_breaker:
            client = await _get_client()
            async with client:
                keys = [_pair_key(job_hash, lang, cid, chash) for cid, chash in candidates]
                values = await client.mget(keys)
        hits: dict[str, dict] = {}
        for (cid, _chash), raw in zip(candidates, values):
            if raw is not None:
                try:
                    hits[cid] = json.loads(raw)
                except json.JSONDecodeError:
                    continue
        if hits:
            logger.info("[MatchCache] Pair cache: %d/%d candidates reused", len(hits), len(candidates))
        return hits
    except CircuitBreakerOpen:
        logger.warning("[MatchCache] Redis circuit OPEN — skipping pair cache read")
        return {}
    except Exception as exc:
        logger.warning("[MatchCache] get_cached_pair_scores failed: %s", exc)
        return {}


async def set_cached_pair_score(
    job_hash: str,
    lang: str,
    candidate_id: str,
    candidate_hash: str,
    score_dict: dict,
) -> None:
    """Cache one candidate's score for this exact (job content, candidate content) pair."""
    try:
        async with redis_breaker:
            client = await _get_client()
            async with client:
                await client.set(
                    _pair_key(job_hash, lang, candidate_id, candidate_hash),
                    json.dumps(score_dict),
                    ex=PAIR_CACHE_TTL,
                )
    except CircuitBreakerOpen:
        logger.warning("[MatchCache] Redis circuit OPEN — pair cache write skipped for %s", candidate_id)
    except Exception as exc:
        logger.warning("[MatchCache] set_cached_pair_score failed: %s", exc)


# ── Candidate snapshot ────────────────────────────────────────────────────────

async def fetch_all_candidate_ids() -> list[str]:
    """Fetch all candidate IDs from the DB (used for staleness check)."""
    from sqlalchemy import select
    from app.infrastructure.database.models import CandidateModel
    from app.infrastructure.database.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CandidateModel.candidate_id).order_by(CandidateModel.candidate_id)
        )
        return [str(row[0]) for row in result.all()]


# ── Staleness check ───────────────────────────────────────────────────────────

async def is_cache_stale(job_id: str, current_candidate_ids: list[str], lang: str = "fr") -> bool:
    """Return True if candidate set changed since last cache fill."""
    meta = await get_cached_meta(job_id, lang)
    if meta is None:
        return True
    current_hash = _hash_candidates(current_candidate_ids)
    current_count = len(current_candidate_ids)
    if meta.get("candidate_count") != current_count:
        return True
    if meta.get("candidate_ids_hash") != current_hash:
        return True
    return False
