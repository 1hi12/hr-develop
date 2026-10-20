"""
cost_guard.py
=============
LLM cost guard — tracks token usage in Redis and enforces hard limits.

Default limits are aligned to the Orange proxy's OWN account quota (its 429
error body reports "Limit type: tokens. Current limit: 10000" for its
window), not an arbitrary internal ceiling — the previous defaults
(500k/hour) were ~50x looser than the real constraint, so this guard
recorded usage but never actually tripped before Orange's own 429 did.

Known approximation: Orange's window appears to be a ROLLING window (429
"resets at" timestamps aren't aligned to :00), while the buckets below are
keyed by CALENDAR hour/day. Near the top of an hour, our bucket can read
"empty" while Orange's real rolling window still holds usage from the
previous ~60 minutes — so is_budget_available() can say yes right before
Orange still says no. Tightening the limit below is a mitigation, not a
guarantee.

Keys in Redis:
  llm:tokens:hourly:{YYYY-MM-DDTHH}    — calendar-hour usage counter  (TTL 2h)
  llm:tokens:daily:{YYYY-MM-DD}        — calendar-day usage counter   (TTL 48h)
  llm:blocked:hourly:{YYYY-MM-DDTHH}   — how many calls is_budget_available()
                                          blocked this hour (TTL 2h) — check
                                          this via get_usage() to see whether
                                          the limits above are actually
                                          firing, instead of guessing.
  llm:blocked:daily:{YYYY-MM-DD}       — same, per day (TTL 48h)

Usage:
    await cost_guard.check_and_record(prompt_tokens=800, completion_tokens=400)

Configure limits in .env:
    LLM_MAX_TOKENS_PER_HOUR=9000
    LLM_MAX_TOKENS_PER_DAY=180000
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Default limits — override via env vars
_MAX_TOKENS_HOUR = int(getattr(settings, "llm_max_tokens_per_hour", 500_000))
_MAX_TOKENS_DAY  = int(getattr(settings, "llm_max_tokens_per_day",  5_000_000))
_WARN_PCT        = 0.8   # log warning at 80% of limit


class LLMBudgetExceeded(Exception):
    """Raised when the token budget is exhausted."""
    def __init__(self, window: str, used: int, limit: int):
        super().__init__(
            f"LLM budget exceeded ({window}): {used:,} / {limit:,} tokens used. "
            "Uploads are paused until the window resets."
        )
        self.window = window
        self.used   = used
        self.limit  = limit


class CostGuard:
    """
    Records token usage per LLM call and raises LLMBudgetExceeded
    before executing a call that would exceed the configured limits.
    """

    def __init__(
        self,
        max_tokens_per_hour: int = _MAX_TOKENS_HOUR,
        max_tokens_per_day:  int = _MAX_TOKENS_DAY,
    ) -> None:
        self.max_hour = max_tokens_per_hour
        self.max_day  = max_tokens_per_day

    # ── Public API ─────────────────────────────────────────────────────────

    async def check_and_record(
        self,
        prompt_tokens: int,
        completion_tokens: int = 0,
    ) -> None:
        """
        Check current usage, raise if limits exceeded, then record the tokens.
        Call this BEFORE the LLM request (fail-fast) or AFTER (record actual use).

        We call it AFTER with actual token counts for accuracy.
        """
        total = prompt_tokens + completion_tokens
        now   = datetime.now(timezone.utc)

        hour_key = f"llm:tokens:hourly:{now.strftime('%Y-%m-%dT%H')}"
        day_key  = f"llm:tokens:daily:{now.strftime('%Y-%m-%d')}"

        try:
            client = aioredis.from_url(settings.redis_url, decode_responses=True)
            async with client:
                pipe = client.pipeline()
                pipe.incrby(hour_key, total)
                pipe.expire(hour_key, 7_200)    # 2-hour TTL
                pipe.incrby(day_key, total)
                pipe.expire(day_key, 172_800)   # 48-hour TTL
                results = await pipe.execute()

            hour_used = int(results[0])
            day_used  = int(results[2])

            self._maybe_warn("hourly", hour_used, self.max_hour)
            self._maybe_warn("daily",  day_used,  self.max_day)

            if hour_used > self.max_hour:
                raise LLMBudgetExceeded("hourly", hour_used, self.max_hour)

            if day_used > self.max_day:
                raise LLMBudgetExceeded("daily", day_used, self.max_day)

        except LLMBudgetExceeded:
            raise
        except Exception as exc:
            # Redis down → log and allow the request (non-blocking)
            logger.warning("[CostGuard] Redis unavailable, skipping cost check: %s", exc)

    async def is_budget_available(self) -> bool:
        """Read-only pre-flight check: True if neither the hourly nor daily limit is exceeded."""
        usage = await self.get_usage()
        if not usage:
            return True  # Redis unavailable — fail open, same as check_and_record
        available = usage["hour_used"] < self.max_hour and usage["day_used"] < self.max_day
        if not available:
            logger.warning(
                "[CostGuard] Budget check BLOCKED a call — hour=%s/%s (%.0f%%) day=%s/%s (%.0f%%)",
                f"{usage['hour_used']:,}", f"{self.max_hour:,}", usage["hour_pct"],
                f"{usage['day_used']:,}", f"{self.max_day:,}", usage["day_pct"],
            )
            await self._record_block()
        return available

    async def get_usage(self) -> dict:
        """Return current token usage + block counts for monitoring/dashboards."""
        now      = datetime.now(timezone.utc)
        hour_key = f"llm:tokens:hourly:{now.strftime('%Y-%m-%dT%H')}"
        day_key  = f"llm:tokens:daily:{now.strftime('%Y-%m-%d')}"
        blocked_hour_key = f"llm:blocked:hourly:{now.strftime('%Y-%m-%dT%H')}"
        blocked_day_key  = f"llm:blocked:daily:{now.strftime('%Y-%m-%d')}"
        try:
            client = aioredis.from_url(settings.redis_url, decode_responses=True)
            async with client:
                hour_used    = int(await client.get(hour_key) or 0)
                day_used     = int(await client.get(day_key)  or 0)
                hour_blocked = int(await client.get(blocked_hour_key) or 0)
                day_blocked  = int(await client.get(blocked_day_key)  or 0)
            return {
                "hour_used":    hour_used,
                "hour_limit":   self.max_hour,
                "hour_pct":     round(hour_used / self.max_hour * 100, 1),
                "day_used":     day_used,
                "day_limit":    self.max_day,
                "day_pct":      round(day_used / self.max_day * 100, 1),
                # How many times is_budget_available() has actually blocked a
                # call — the factual signal for whether the limits above are
                # well calibrated, instead of guessing from usage % alone.
                "hour_blocked_count": hour_blocked,
                "day_blocked_count":  day_blocked,
            }
        except Exception as exc:
            logger.warning("[CostGuard] Could not fetch usage: %s", exc)
            return {}

    async def _record_block(self) -> None:
        """Increment the hourly/daily counters of how often the pre-flight
        check blocked a call. Never raises — monitoring must not break the
        caller's fallback path."""
        now = datetime.now(timezone.utc)
        blocked_hour_key = f"llm:blocked:hourly:{now.strftime('%Y-%m-%dT%H')}"
        blocked_day_key  = f"llm:blocked:daily:{now.strftime('%Y-%m-%d')}"
        try:
            client = aioredis.from_url(settings.redis_url, decode_responses=True)
            async with client:
                pipe = client.pipeline()
                pipe.incr(blocked_hour_key)
                pipe.expire(blocked_hour_key, 7_200)
                pipe.incr(blocked_day_key)
                pipe.expire(blocked_day_key, 172_800)
                await pipe.execute()
        except Exception as exc:
            logger.warning("[CostGuard] Could not record budget block: %s", exc)

    # ── Internal ───────────────────────────────────────────────────────────

    def _maybe_warn(self, window: str, used: int, limit: int) -> None:
        pct = used / limit if limit else 0
        if pct >= _WARN_PCT:
            logger.warning(
                "[CostGuard] LLM %s usage at %.0f%% (%s / %s tokens)",
                window, pct * 100, f"{used:,}", f"{limit:,}",
            )


# ── Singleton ─────────────────────────────────────────────────────────────────

cost_guard = CostGuard()
