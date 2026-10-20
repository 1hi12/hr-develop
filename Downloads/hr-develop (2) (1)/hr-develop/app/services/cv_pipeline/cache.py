"""
cv_pipeline/cache.py
====================
SQLite-based SHA-256 cache for batch-extracted CV data.

Keyed by SHA-256 of the raw CV text → if the same PDF is re-uploaded,
the extraction result is returned instantly without any LLM call.

Uses aiosqlite for non-blocking async access inside the FastAPI event loop.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

# Cache database location (project root — committed to .gitignore)
CACHE_DB_PATH = Path("cv_pipeline_cache.db")

_init_lock = asyncio.Lock()
_initialized = False


# ── Initialisation ────────────────────────────────────────────────────────────

async def _ensure_initialized() -> None:
    global _initialized
    if _initialized:
        return
    async with _init_lock:
        if _initialized:
            return
        async with aiosqlite.connect(CACHE_DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS cv_cache (
                    hash       TEXT    PRIMARY KEY,
                    result     TEXT    NOT NULL,
                    filename   TEXT,
                    created_at REAL    NOT NULL
                )
            """)
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_cv_cache_created "
                "ON cv_cache(created_at)"
            )
            await db.commit()
        _initialized = True
        logger.info("[Cache] SQLite initialized at %s", CACHE_DB_PATH.resolve())


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


# ── Public API ────────────────────────────────────────────────────────────────

async def get_cached(cv_text: str) -> dict | None:
    """Return the cached extraction result for *cv_text*, or None on miss."""
    await _ensure_initialized()
    h = _sha256(cv_text)
    async with aiosqlite.connect(CACHE_DB_PATH) as db:
        async with db.execute(
            "SELECT result FROM cv_cache WHERE hash = ?", (h,)
        ) as cursor:
            row = await cursor.fetchone()
    if row:
        logger.debug("[Cache] HIT  %s…", h[:12])
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            logger.warning("[Cache] Corrupt entry for %s…, treating as miss", h[:12])
            return None
    logger.debug("[Cache] MISS %s…", h[:12])
    return None


async def set_cached(cv_text: str, result: dict, filename: str = "") -> None:
    """Persist *result* for *cv_text* so future uploads skip the LLM call."""
    await _ensure_initialized()
    h = _sha256(cv_text)
    async with aiosqlite.connect(CACHE_DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO cv_cache (hash, result, filename, created_at) "
            "VALUES (?, ?, ?, ?)",
            (h, json.dumps(result, ensure_ascii=False), filename, time.time()),
        )
        await db.commit()
    logger.debug("[Cache] SET  %s… (%s)", h[:12], filename)


async def cache_stats() -> dict:
    """Return basic stats (total entries, oldest, newest)."""
    await _ensure_initialized()
    async with aiosqlite.connect(CACHE_DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*), MIN(created_at), MAX(created_at) FROM cv_cache"
        ) as cursor:
            row = await cursor.fetchone()
    count, oldest, newest = row if row else (0, None, None)
    return {"total_entries": count, "oldest_ts": oldest, "newest_ts": newest}
