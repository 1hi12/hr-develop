"""
llm_gate.py
===========
Single process-wide concurrency gate for Orange LiteLLM proxy calls, sized
by settings.llm_max_concurrency.

Used by:
  - MultiWorkerExtractor (app/infrastructure/llm/multi_worker_extractor.py)
    — both the bulk pipeline and the single-CV upload path create a fresh
    MultiWorkerExtractor per call, so a per-instance semaphore never
    throttled two concurrent uploads against each other; this shared
    module-level gate does.
  - job_matching.MultiModelAIEngine (matching/scoring) — so a CV upload
    running at the same time as a matching request queues behind the same
    gate instead of both racing the Orange quota independently.
  - (dead) app/application/pipelines/matching_graph.py, not wired to any
    API route.

NOT yet used by ranking_service.py, interview_prep_graph.py,
jd_enhancement_graph.py or email_service.py — those still have their own
separate concurrency handling (or none), so those specific features can
still burst past the real Orange quota independently of everything above.
"""
from __future__ import annotations

import asyncio

from app.config.settings import settings

llm_gate = asyncio.Semaphore(settings.llm_max_concurrency)
