"""
multi_worker_extractor.py
=========================
Single-worker extractor using GPT-4o-mini via the Orange LiteLLM proxy
(OpenAI-compatible), same access point as the ranker/matching services.

Batch protocol
--------------
• Input  : list of raw CV texts (max 10)
• Prompt : texts joined by "---CV_SEPARATOR---"
• Output : JSON array of N objects, one per CV
• Fields : name, email, phone, location, summary, skills[], experiences[],
           education[], languages[], certifications[], seniority, years_exp
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
from abc import ABC, abstractmethod
from typing import Any

# ── SSL override for corporate / proxy network ────────────────────────────────
import os as _os
_os.environ["PYTHONHTTPSVERIFY"]  = "0"
_os.environ["REQUESTS_CA_BUNDLE"] = ""
_os.environ["SSL_CERT_FILE"]      = ""
warnings.filterwarnings("ignore")
ssl._create_default_https_context = ssl._create_unverified_context  # type: ignore[attr-defined]
ssl.create_default_context = lambda *a, **kw: ssl._create_unverified_context(*a, **kw)  # type: ignore[attr-defined]

import httpx
from openai import AsyncOpenAI

from app.config.settings import settings
from app.core.ports.llm_extractor import ILLMExtractor
from app.infrastructure.llm.rate_limit import is_rate_limit_error, rate_limit_wait_seconds

logger = logging.getLogger(__name__)

# ── Batch prompt ──────────────────────────────────────────────────────────────

_BATCH_PROMPT_TEMPLATE = """\
You receive {n} CVs separated by "---CV_SEPARATOR---".
Extract ALL information from EACH CV as a JSON array of exactly {n} objects.
Each object MUST have every field below — use null when missing, never skip:

  name           : string | null
  email          : string | null
  phone          : string | null
  location       : string | null
  summary        : string | null   (2-4 sentences)
  skills         : string[]        (flat list of ALL technical + soft skills)
  experiences    : array of {{company, title, start_date, end_date, description, is_internship}}
                   IMPORTANT: include ALL experiences — internships (stage, PFE, PFA, alternance,
                   intern, stagiaire) AND full-time jobs. Set is_internship=true for internships.
  education      : array of {{institution, degree, field_of_study, graduation_year}}
  languages      : string[]
  certifications : string[]
  seniority      : "intern" | "junior" | "mid" | "senior" | "lead" | "executive" | null
                   Rules (STRICTLY follow):
                   - "intern"  : ONLY short stages/PFE/PFA (< 6 months, no real job title)
                   - "junior"  : apprentissage, alternance, or 0-2 years of real work experience
                   - "mid"     : 2-5 years of real work experience
                   - "senior"  : 5-10 years
                   - "lead"    : 10+ years or management role
                   NOTE: "Apprenti Ingénieur", "alternant", "apprenti" = junior NOT intern
  years_exp      : integer | null
                   Count FULL years of work experience. Rules:
                   - Short stage/PFE/PFA only (< 6 months) → 0
                   - Alternance/apprentissage → counts as real experience (round to nearest year)
                   - Sum all non-internship positions and round to integer
  detected_lang  : "FR" | "EN"

Detect language automatically (FR or EN).
Reply ONLY with a valid JSON array — no markdown, no commentary, nothing else.

CVs:
{cvs}"""


def _build_prompt(cv_texts: list[str]) -> str:
    truncated = [t[:10_000] for t in cv_texts]
    combined  = "\n---CV_SEPARATOR---\n".join(truncated)
    return _BATCH_PROMPT_TEMPLATE.format(n=len(cv_texts), cvs=combined)


# ── JSON helpers ──────────────────────────────────────────────────────────────

def _parse_json_array(raw: str, expected: int) -> list[dict]:
    cleaned = re.sub(r"```json\s*", "", raw)
    cleaned = re.sub(r"```\s*",     "", cleaned).strip()
    try:
        result = json.loads(cleaned)
        if isinstance(result, list):
            return _pad(result, expected)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(0))
            if isinstance(result, list):
                return _pad(result, expected)
        except json.JSONDecodeError:
            pass
    logger.warning("[MultiWorker] JSON parse failed. Raw (200 chars): %s", raw[:200])
    return [{} for _ in range(expected)]


def _pad(lst: list, expected: int) -> list[dict]:
    result = [item if isinstance(item, dict) else {} for item in lst]
    while len(result) < expected:
        result.append({})
    return result[:expected]


class _StreamingArrayParser:
    """
    Incrementally parses a top-level JSON array of objects out of a token
    stream, yielding each object the moment its closing brace arrives —
    without waiting for the rest of the array or the response to finish.
    Tolerates a leading ```json fence: everything before the first '[' is
    discarded rather than parsed.
    """

    def __init__(self) -> None:
        self._started = False    # seen the array's opening '['
        self._depth = 0          # brace depth while inside the current object
        self._in_string = False
        self._escape = False
        self._current = ""

    def feed(self, text: str) -> list[dict]:
        """Append streamed text; return any objects completed by it, in order."""
        completed: list[dict] = []
        for ch in text:
            if not self._started:
                if ch == "[":
                    self._started = True
                continue

            if self._depth == 0:
                if ch == "{":
                    self._depth = 1
                    self._current = ch
                continue  # skip commas/whitespace/']' between objects

            self._current += ch
            if self._in_string:
                if self._escape:
                    self._escape = False
                elif ch == "\\":
                    self._escape = True
                elif ch == '"':
                    self._in_string = False
                continue

            if ch == '"':
                self._in_string = True
            elif ch == "{":
                self._depth += 1
            elif ch == "}":
                self._depth -= 1
                if self._depth == 0:
                    try:
                        obj = json.loads(self._current)
                        if isinstance(obj, dict):
                            completed.append(obj)
                    except json.JSONDecodeError:
                        logger.warning("[MultiWorker] Stream: failed to parse one CV object")
                    self._current = ""
        return completed


def _scaled_max_tokens(n: int) -> int:
    """
    Scale the output token budget with batch size instead of always
    reserving 8192: a 5-CV batch's JSON rarely needs more than ~4-5k tokens,
    and some proxies count the REQUESTED max_tokens (not actual usage)
    against the rate-limit window — always asking for 8192 wastes quota
    headroom on small batches and makes 429s more likely, not less.
    """
    return min(8192, n * 900 + 300)


# ── Worker base ───────────────────────────────────────────────────────────────

class _BaseWorker(ABC):
    name: str

    @abstractmethod
    async def call(self, prompt: str, n: int) -> list[dict]:
        """Call the LLM and return exactly n dicts (empty on failure)."""
        ...


# ── Orange LiteLLM proxy worker (GPT-4o-mini — sole worker) ─────────────────

class _OrangeProxyWorker(_BaseWorker):
    """Sole worker: GPT-4o-mini (or whatever settings.litellm_model is) via the
    Orange LiteLLM proxy — same access point used by the ranker/matching services."""

    name = "orange-litellm-proxy"

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.litellm_api_key,
            base_url=settings.litellm_base_url,
            max_retries=0,
            http_client=httpx.AsyncClient(verify=False),
        )
        self._model = settings.litellm_model

    async def call(self, prompt: str, n: int) -> list[dict]:
        from app.infrastructure.llm.cost_guard import cost_guard
        from app.infrastructure.llm.llm_gate import llm_gate

        # Pre-flight budget check — skip the call entirely (no cost) if the
        # budget is already exhausted, instead of only recording after the
        # fact and letting _call_with_retry retry into more spend.
        if not await cost_guard.is_budget_available():
            logger.warning(
                "[MultiWorker] %s skipped — LLM budget exhausted (%d CVs → fallback)",
                self.name, n,
            )
            return [{} for _ in range(n)]

        # Shared process-wide gate (not a per-instance semaphore): every CV
        # upload creates a fresh MultiWorkerExtractor, so a per-instance
        # semaphore never throttled two concurrent uploads against each
        # other — both could hit the Orange proxy's small token quota at
        # the same instant. llm_gate is a single module-level semaphore
        # shared by every instance, so concurrent uploads now queue instead
        # of racing.
        max_tokens = _scaled_max_tokens(n)

        async with llm_gate:
            t0 = time.monotonic()
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=max_tokens,
            )
            elapsed_ms = int((time.monotonic() - t0) * 1000)
        raw = response.choices[0].message.content or ""
        logger.info("[MultiWorker] %s extracted %d CVs in %d ms", self.name, n, elapsed_ms)
        if response.usage:
            from app.infrastructure.llm.cost_guard import cost_guard
            await cost_guard.check_and_record(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens or 0,
            )
        return _parse_json_array(raw, n)

    async def call_stream(self, prompt: str, n: int):
        """
        Same call as `call()`, but streams the completion and yields each CV
        dict as soon as its JSON object is complete in the response — instead
        of waiting for the whole batch to finish. Still exactly one LLM call.
        Always yields exactly n items (later ones are {} if the stream ends
        early or a slot fails to parse).
        """
        from app.infrastructure.llm.cost_guard import cost_guard
        from app.infrastructure.llm.llm_gate import llm_gate

        if not await cost_guard.is_budget_available():
            logger.warning(
                "[MultiWorker] %s skipped — LLM budget exhausted (%d CVs → fallback)",
                self.name, n,
            )
            for _ in range(n):
                yield {}
            return

        max_tokens = _scaled_max_tokens(n)
        parser = _StreamingArrayParser()
        yielded = 0

        async with llm_gate:
            t0 = time.monotonic()
            # Not all OpenAI-compatible proxies support stream_options (used
            # to get a usage record in the final chunk) — omitted so an
            # unsupported-param rejection can't break streaming outright.
            # cost_guard still gets its pre-flight is_budget_available()
            # check above; it just won't record this call's exact usage.
            stream = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=max_tokens,
                stream=True,
            )
            async for event in stream:
                if event.choices:
                    delta = event.choices[0].delta.content
                    if delta:
                        for obj in parser.feed(delta):
                            if yielded < n:
                                yielded += 1
                                yield obj
                usage = getattr(event, "usage", None)
                if usage:
                    await cost_guard.check_and_record(
                        prompt_tokens=usage.prompt_tokens,
                        completion_tokens=usage.completion_tokens or 0,
                    )
            elapsed_ms = int((time.monotonic() - t0) * 1000)

        logger.info(
            "[MultiWorker] %s streamed %d/%d CVs in %d ms", self.name, yielded, n, elapsed_ms,
        )
        for _ in range(n - yielded):
            yield {}


# ── Worker factory ────────────────────────────────────────────────────────────

def _make_workers() -> list[_BaseWorker]:
    if not settings.litellm_api_key:
        logger.error("[MultiWorker] litellm_api_key not configured — extraction will fail!")
        return []

    logger.info("[MultiWorker] Using Orange LiteLLM proxy — model=%s", settings.litellm_model)
    return [_OrangeProxyWorker()]


# ── MultiWorkerExtractor ──────────────────────────────────────────────────────

class MultiWorkerExtractor(ILLMExtractor):
    """
    Batch extraction via the Orange LiteLLM proxy (single worker).
    Implements ILLMExtractor so it works for both single-file upload and bulk pipeline.
    """

    def __init__(self) -> None:
        self._workers  = _make_workers()
        self._rr_lock  = asyncio.Lock()
        self._rr_index = 0

    # ── Batch API ─────────────────────────────────────────────────────────────

    async def extract_batch(
        self, cv_texts: list[str]
    ) -> tuple[list[dict[str, Any]], str]:
        """
        Extract structured data from up to 10 CV texts in one LLM call.
        Tries workers in round-robin order; falls back to the next if one fails.
        Returns (results_list, model_name).
        """
        if not cv_texts:
            return [], "none"

        if not self._workers:
            logger.error("[MultiWorker] No workers available — returning empty batch")
            return [{} for _ in cv_texts], "no_workers"

        prompt = _build_prompt(cv_texts)
        n      = len(cv_texts)

        # Start from the current round-robin position, try all workers
        async with self._rr_lock:
            start = self._rr_index
            self._rr_index = (self._rr_index + 1) % len(self._workers)

        for i in range(len(self._workers)):
            worker = self._workers[(start + i) % len(self._workers)]
            results = await self._call_with_retry(worker, prompt, n)
            if any(results):          # at least one non-empty CV extracted
                return results, worker.name
            logger.warning(
                "[MultiWorker] %s returned empty — falling back to next worker", worker.name
            )

        logger.error("[MultiWorker] All workers failed — returning empty batch")
        return [{} for _ in cv_texts], "all_failed"

    async def extract_batch_stream(self, cv_texts: list[str]):
        """
        Same one-LLM-call-per-batch protocol as extract_batch, but yields
        (index, cv_data, model_name) for each CV as soon as its JSON object
        is parsed out of the streamed response — so the caller can store/emit
        each CV as it becomes ready instead of waiting for the whole batch.

        Retries with backoff only apply before anything has streamed yet (a
        429/connection error on the first byte). If the stream fails partway
        through, already-yielded CVs are not re-sent — remaining slots are
        yielded as {} and left to the confidence-based solo retry (see
        pipeline.py) to recover individually.
        """
        if not cv_texts:
            return

        if not self._workers:
            logger.error("[MultiWorker] No workers available — returning empty batch")
            for i in range(len(cv_texts)):
                yield i, {}, "no_workers"
            return

        prompt = _build_prompt(cv_texts)
        n      = len(cv_texts)
        worker = self._workers[0]
        max_retries = settings.pipeline_max_retries
        rate_wait   = settings.pipeline_rate_limit_wait
        yielded = 0

        for attempt in range(1, max_retries + 1):
            try:
                async for cv in worker.call_stream(prompt, n):
                    yield yielded, cv, worker.name
                    yielded += 1
                return
            except Exception as exc:
                if yielded > 0:
                    logger.error(
                        "[MultiWorker] Stream failed after %d/%d CVs already delivered: %s",
                        yielded, n, exc,
                    )
                    break
                err_str = str(exc)
                if attempt < max_retries:
                    delay = (
                        rate_limit_wait_seconds(err_str, rate_wait)
                        if is_rate_limit_error(err_str) else 2 ** attempt
                    )
                    logger.warning(
                        "[MultiWorker] Stream attempt %d/%d failed: %s — retrying in %.1fs",
                        attempt, max_retries, exc, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "[MultiWorker] Stream exhausted all %d retries: %s", max_retries, exc,
                    )

        for i in range(yielded, n):
            yield i, {}, "all_failed"

    # ── ILLMExtractor interface (single-CV) ──────────────────────────────────

    async def extract(
        self, cv_text: str
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """ILLMExtractor implementation — calls extract_batch with a single CV."""
        results, model_used = await self.extract_batch([cv_text])
        cv: dict[str, Any]  = results[0] if results else {}

        logger.info(
            "[MultiWorker/single] Extracted via %s — name=%s skills=%d",
            model_used, cv.get("name", "?"), len(cv.get("skills") or []),
        )

        all_skills: list[str] = [
            s for s in (cv.get("skills") or []) if isinstance(s, str) and s.strip()
        ]

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

        skills: dict[str, Any] = {
            "technical":   all_skills,
            "frameworks":  [],
            "databases":   [],
            "devops":      [],
            "soft_skills": [],
            "languages":   cv.get("languages") or [],
            "all_skills":  all_skills,
        }

        seniority: dict[str, Any] = {
            "seniority_level":        cv.get("seniority") or "unknown",
            "total_years_experience": cv.get("years_exp"),
            "experiences":  [e for e in (cv.get("experiences") or []) if isinstance(e, dict)],
            "education":    [e for e in (cv.get("education")   or []) if isinstance(e, dict)],
        }

        return general, skills, seniority

    # ── Retry logic ───────────────────────────────────────────────────────────

    async def _call_with_retry(
        self, worker: _BaseWorker, prompt: str, n: int
    ) -> list[dict[str, Any]]:
        max_retries  = settings.pipeline_max_retries
        rate_wait    = settings.pipeline_rate_limit_wait

        for attempt in range(1, max_retries + 1):
            try:
                return await worker.call(prompt, n)

            except Exception as exc:
                err_str = str(exc)
                is_rate_limit = is_rate_limit_error(err_str)

                if is_rate_limit and attempt < max_retries:
                    # Prefer the proxy's own "Limit resets at" timestamp over the
                    # fixed rate_wait — a flat 15s sleep is often shorter than the
                    # real quota reset window, so every retry still 429s and the
                    # CV ends up saved with an empty extraction ("Unknown").
                    delay = rate_limit_wait_seconds(err_str, rate_wait)
                    logger.warning(
                        "[MultiWorker] 429 from %s (attempt %d/%d) — sleeping %.1fs",
                        worker.name, attempt, max_retries, delay,
                    )
                    await asyncio.sleep(delay)
                elif attempt < max_retries:
                    logger.error(
                        "[MultiWorker] %s call failed (attempt %d/%d): %s",
                        worker.name, attempt, max_retries, exc,
                    )
                    await asyncio.sleep(2 ** attempt)
                else:
                    logger.error(
                        "[MultiWorker] %s exhausted all %d retries: %s",
                        worker.name, max_retries, exc,
                    )

        return [{} for _ in range(n)]
