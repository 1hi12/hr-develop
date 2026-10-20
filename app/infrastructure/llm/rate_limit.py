"""
rate_limit.py
==============
Helpers for backing off from 429 responses returned by the Orange LiteLLM
proxy. The proxy's error payload includes the exact UTC timestamp at which
the token quota resets (e.g. "Limit resets at: 2026-07-01 08:19:49 UTC"),
so we parse it and wait precisely until then instead of guessing with a
fixed/exponential delay that may be shorter than the real reset window.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

_RESET_AT_RE = re.compile(
    r"resets at:\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*UTC", re.IGNORECASE
)


def is_rate_limit_error(err_str: str) -> bool:
    return "429" in err_str or "rate limit" in err_str.lower()


def rate_limit_wait_seconds(err_str: str, default: float, cap: float = 40.0) -> float:
    """
    Return how long to sleep before retrying a 429.
    Prefers the proxy's own "resets at" timestamp; falls back to `default`
    when the message can't be parsed. Always clamped to [0.5, cap] seconds.
    """
    match = _RESET_AT_RE.search(err_str)
    if match:
        try:
            reset_at = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
            delta = (reset_at - datetime.now(timezone.utc)).total_seconds()
            return max(0.5, min(delta + 0.5, cap))
        except ValueError:
            pass
    return max(0.5, min(default, cap))
