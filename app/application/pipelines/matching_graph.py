"""
matching_graph.py
=================
LangGraph pipeline for CV-to-job matching — US-22 through US-27, US-31, US-26, US-32.

NOT wired to any API route. The production matching system used by the
frontend is app.services.job_matching.CVJobMatcher (see app/api/v1/routes/
candidates.py and job_postings.py). This module is kept for reference only;
its fast-path thresholds and 2-depth scoring below do not apply to production
matching. All LLM calls in this file go through the LiteLLM Orange proxy only
(settings.litellm_model) — no other provider.

Flow
----
  START
    ↓
  embed_query           ← vectorise JD + skills expanded with equivalences (US-26)
    ↓
  vector_search         ← Milvus top-K with optional partition filter (US-79)
    ↓ (no results → END)
  fetch_cv_content      ← reconstruct full CV text from Milvus chunks
    ↓
  cross_encode_rerank   ← US-23: Cross-Encoder on (JD, cv_text) pairs   [if use_reranking]
    ↓
  llm_score_4criteria   ← US-24+25+32: CoT with dynamic weights + profile description
    ↓
  format_response       ← US-27+28+29: merge scores, ranked list + recruiter advice
    ↓
   END
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections import defaultdict
from typing import Any, Optional

import httpx
from openai import AsyncOpenAI
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from app.config.settings import settings
from app.infrastructure.llm.rate_limit import is_rate_limit_error, rate_limit_wait_seconds
from app.infrastructure.llm.llm_gate import llm_gate
from app.infrastructure.llm.cost_guard import cost_guard

logger = logging.getLogger(__name__)

# Candidates scored per LLM call in llm_score_4criteria, and the threshold
# below which cross_encode_rerank is skipped (see route_after_fetch): the
# rerank step scores every fetched candidate too — it does not shrink the
# set that reaches llm_score_4criteria — so for a pool that already fits in
# one scoring call it is a pure extra LLM call for no precision gain (the
# 4-criteria CoT scoring already evaluates each candidate individually).
_CANDIDATES_PER_LLM_CALL = 10

# Fast-path thresholds on raw vector-similarity score (0-1): when a candidate
# is already unambiguously a strong or weak match by semantic similarity
# alone, paying for a full LLM CoT pass adds no precision — only cost. These
# are calibrated for genuine cosine-similarity embedding scores; while the
# vector store is degraded (e.g. falling back to a flat placeholder score),
# every candidate lands in the "ambiguous" band below and is scored normally.
_OBVIOUS_HIGH_THRESHOLD = 0.85
_OBVIOUS_LOW_THRESHOLD  = 0.25

# Among the remaining "ambiguous" candidates, only the top N by vector
# similarity — the actual finalists a recruiter will read — get the full
# rich narrative analysis (profile, strengths, weaknesses, recommendation
# paragraph). The rest still get a precise numeric score (_LIGHT_SCORING_PROMPT),
# just without the long-form text nobody reads for a non-finalist.
_MAX_FULL_ANALYSIS = 8


# ── US-26 — Semantic skill equivalences ───────────────────────────────────────
# When the JD asks for "Angular", candidates with "React" or "Vue" are also relevant.
# Each key maps to a list of interchangeable alternatives.

_SKILL_GROUPS: list[set[str]] = [
    {"react", "vue", "angular", "svelte", "next.js", "nuxt.js"},
    {"node.js", "nodejs", "node", "express", "nestjs", "fastify"},
    {"python", "python3"},
    {"fastapi", "flask", "django"},
    {"spring", "spring boot", "quarkus"},
    {"typescript", "javascript"},
    {"java", "kotlin"},
    {"swift", "objective-c"},
    {"react native", "flutter", "ionic", "xamarin"},
    {"kubernetes", "k8s", "openshift", "docker swarm"},
    {"docker", "podman", "containerd"},
    {"aws", "azure", "gcp", "cloud"},
    {"tensorflow", "pytorch", "keras", "jax"},
    {"postgresql", "mysql", "mariadb", "sql server", "oracle"},
    {"mongodb", "couchdb", "dynamodb", "firestore"},
    {"redis", "memcached", "dragonflydb"},
    {"elasticsearch", "opensearch", "solr"},
    {"kafka", "rabbitmq", "pulsar", "nats", "activemq"},
    {"graphql", "rest api", "grpc"},
    {"terraform", "ansible", "pulumi", "cloudformation"},
    {"gitlab ci", "github actions", "jenkins", "circleci"},
    {"machine learning", "ml", "deep learning", "dl"},
    {"spark", "databricks", "flink"},
    {"airflow", "prefect", "dagster"},
    {"power bi", "tableau", "looker", "metabase"},
    {"scrum", "agile", "kanban"},
    {"linux", "unix", "bash"},
]

# Precompute: skill → set of equivalents (excluding self)
_EQUIVALENCES: dict[str, list[str]] = {}
for _group in _SKILL_GROUPS:
    for _skill in _group:
        _EQUIVALENCES[_skill] = sorted(_group - {_skill})


def expand_skills_with_equivalences(skills: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    """
    US-26: Returns (expanded_skill_list, equivalence_map_for_prompt).
    expanded_skill_list includes the original skill + known alternatives.
    equivalence_map is passed to the LLM so it accepts equivalent skills.
    """
    expanded: list[str] = []
    equiv_map: dict[str, list[str]] = {}
    seen: set[str] = set()

    for skill in skills:
        key = skill.lower().strip()
        if key not in seen:
            expanded.append(skill)
            seen.add(key)
        alts = _EQUIVALENCES.get(key, [])
        if alts:
            equiv_map[skill] = alts
            for alt in alts:
                if alt not in seen:
                    expanded.append(alt)
                    seen.add(alt)

    return expanded, equiv_map


# ── State ─────────────────────────────────────────────────────────────────────

class MatchingState(TypedDict):
    # ── Inputs ────────────────────────────────────────────────────────────────
    job_description:  str
    required_skills:  list[str]
    top_k:            int
    min_score:        float
    use_reranking:    bool
    # Language for LLM-generated analysis text ("fr" | "en") — follows the UI toggle
    lang:             str
    # US-32 — dynamic weights {skills, experience, education, culture} as floats 0-1
    scoring_weights:  dict[str, float]
    # US-79 — restrict Milvus search to partition(s)
    partition_names:  list[str]

    # ── Phase 1: embed ────────────────────────────────────────────────────────
    query_embedding:  list[float]
    # US-26 — equivalences sent to LLM prompt
    skill_equiv_map:  dict[str, list[str]]

    # ── Phase 2: vector search ────────────────────────────────────────────────
    vector_results:   list[dict]

    # ── Phase 3: fetch full CV content ────────────────────────────────────────
    candidate_texts:  dict[str, str]
    candidate_skills: dict[str, list[str]]

    # ── Phase 4: cross-encoder rerank ─────────────────────────────────────────
    ce_scores:        dict[str, float]

    # ── Phase 5: LLM 4-criteria scoring ──────────────────────────────────────
    llm_evaluations:  list[dict]

    # ── Phase 6: output ───────────────────────────────────────────────────────
    ranked_candidates: list[dict]
    recruiter_advice:  str

    error:            Optional[str]


# ── LLM client (lazy singleton) ───────────────────────────────────────────────

_llm_client: AsyncOpenAI | None = None


def _get_llm_client() -> AsyncOpenAI:
    global _llm_client
    if _llm_client is None:
        _llm_client = AsyncOpenAI(
            api_key=settings.litellm_api_key,
            base_url=settings.litellm_base_url,
            max_retries=0,
            http_client=httpx.AsyncClient(
                verify=False, timeout=settings.llm_timeout_seconds
            ),
        )
    return _llm_client


# ── US-24+25+26+32 — Enriched 4-Criteria CoT Scoring Prompt (batched) ────────
# Multiple candidates are scored per LLM call: the job description, skill
# equivalences and instructions are sent ONCE per batch instead of once per
# candidate, which is where most of the token budget was going. Each
# candidate still gets an independent, precise 4-criteria breakdown —
# only the free-text reasoning fields are kept short to bound the response.

_SCORING_PROMPT = """\
You are a strict senior HR analyst. Evaluate EACH of the {n} candidates below \
independently, step by step, then answer for all of them in a single JSON array.

═══ JOB DESCRIPTION ════════════════════════════════════════════════════════════
{job_description}

Required skills: {required_skills}
════════════════════════════════════════════════════════════════════════════════

═══ SKILL EQUIVALENCES (US-26) ═════════════════════════════════════════════════
The following skills are considered equivalent for scoring purposes:
{equivalences_text}
Accept any equivalent as partial credit (80% of the original).
════════════════════════════════════════════════════════════════════════════════

═══ SCORING WEIGHTS (configured per job) ════════════════════════════════════
Skills: {w_skills}%  |  Experience: {w_exp}%  |  Education: {w_edu}%  |  Culture: {w_cult}%
════════════════════════════════════════════════════════════════════════════════

For EACH candidate, independently:
STEP 1 — SKILLS MATCH (weight {w_skills}%): list matched/missing required skills (exact or equivalent), assign skills_score (0-100).
STEP 2 — EXPERIENCE MATCH (weight {w_exp}%): compare years/relevance vs requirement, assign experience_score (0-100).
STEP 3 — EDUCATION MATCH (weight {w_edu}%): compare degree/field vs requirement, assign education_score (0-100).
STEP 4 — CULTURE / SOFT SKILLS (weight {w_cult}%): evidence of communication/leadership/teamwork, assign culture_score (0-100).
STEP 5 — FINAL SCORE: total_score = round(skills_score*{wf_skills} + experience_score*{wf_exp} + education_score*{wf_edu} + culture_score*{wf_cult}).
recommendation: "selected" if total_score >= 60, "reserve" if 40-59, else "rejected".
STEP 6 — Write the following text fields in {lang_name} ONLY:
- profile_summary: a FULL descriptive paragraph of 5 to 7 sentences — NOT a single line. \
Describe this candidate's technical background with precision (name actual technologies, tools, \
years of experience, degrees found in the CV) and explicitly tie them to the requirements of the \
job description above. Weave the candidate's main strengths AND weaknesses naturally INTO this \
same paragraph (do not present them as a separate list) and wrap each strength or weakness phrase \
in double asterisks so it renders bold, e.g. "**solide expérience AWS et Docker**" or \
"**absence de compétences en Scala**". End the paragraph with a clear technical verdict on fit.
- key_strengths / key_weaknesses: up to 3 / 2 short items — the same points that are bolded \
inside profile_summary above, kept here as well for quick-scan chips.
- recommendation_paragraph: 2-3 sentences of concrete, actionable advice for the recruiter about \
THIS candidate for THIS specific position — e.g. whether to proceed to interview, what to verify, \
what training/ramp-up would be needed, or why to pass. Not a restatement of profile_summary.
- cot_reasoning: 1-2 sentences.
You are scoring {n} candidates in this one response — keep every text field precise and substantive.

═══ CANDIDATES ══════════════════════════════════════════════════════════════
{candidates_block}
════════════════════════════════════════════════════════════════════════════════

Reply ONLY with a valid JSON array of exactly {n} objects, one per candidate, \
in the SAME ORDER as listed above — no markdown outside the bolded phrases described above, \
no commentary:
[
  {{
    "candidate_id":             "<candidate id as given above>",
    "skills_score":             <0-100>,
    "experience_score":         <0-100>,
    "education_score":          <0-100>,
    "culture_score":            <0-100>,
    "total_score":              <0-100>,
    "matched_skills":           ["skill1", "skill2"],
    "missing_skills":           ["skill3"],
    "cot_reasoning":            "<1-2 sentences, in {lang_name}>",
    "recommendation":           "selected|reserve|rejected",
    "profile_summary":          "<5-7 sentences, in {lang_name}, technical, tied to the job description, with **bolded** strengths/weaknesses inline>",
    "key_strengths":            ["<short strength 1>", "<short strength 2>"],
    "key_weaknesses":           ["<short gap 1>"],
    "recommendation_paragraph": "<2-3 sentences, in {lang_name}, actionable advice for this position>"
  }}
]
"""

# Compact variant of the prompt above, used for candidates that are not
# finalists (see _MAX_FULL_ANALYSIS below): same precise 4-criteria numeric
# scoring, but no long-form narrative fields — nobody reads a full profile
# write-up for a candidate that isn't in the running. Cuts output tokens
# substantially without touching scoring precision.
_LIGHT_SCORING_PROMPT = """\
You are a strict senior HR analyst. Evaluate EACH of the {n} candidates below \
independently, step by step, then answer for all of them in a single JSON array.

═══ JOB DESCRIPTION ════════════════════════════════════════════════════════════
{job_description}

Required skills: {required_skills}
════════════════════════════════════════════════════════════════════════════════

═══ SKILL EQUIVALENCES (US-26) ═════════════════════════════════════════════════
{equivalences_text}
Accept any equivalent as partial credit (80% of the original).
════════════════════════════════════════════════════════════════════════════════

═══ SCORING WEIGHTS (configured per job) ════════════════════════════════════
Skills: {w_skills}%  |  Experience: {w_exp}%  |  Education: {w_edu}%  |  Culture: {w_cult}%
════════════════════════════════════════════════════════════════════════════════

For EACH candidate, independently score — these are not finalists, so do NOT \
write long explanations, only a precise numeric verdict:
- skills_score, experience_score, education_score, culture_score (0-100 each)
- total_score = round(skills_score*{wf_skills} + experience_score*{wf_exp} + education_score*{wf_edu} + culture_score*{wf_cult})
- recommendation: "selected" if total_score >= 60, "reserve" if 40-59, else "rejected"
- cot_reasoning: ONE short sentence (max 15 words) justifying total_score

═══ CANDIDATES ══════════════════════════════════════════════════════════════
{candidates_block}
════════════════════════════════════════════════════════════════════════════════

Reply ONLY with a valid JSON array of exactly {n} objects, one per candidate, \
in the SAME ORDER as listed above — no markdown, no commentary:
[
  {{
    "candidate_id":     "<candidate id as given above>",
    "skills_score":     <0-100>,
    "experience_score": <0-100>,
    "education_score":  <0-100>,
    "culture_score":    <0-100>,
    "total_score":      <0-100>,
    "recommendation":   "selected|reserve|rejected",
    "cot_reasoning":    "<max 15 words>"
  }}
]
"""

_ADVICE_PROMPT = """\
You are a senior HR consultant. Based on these candidates evaluated for the job, \
write 3-4 sentences of concrete recruiter advice.

JOB: {job_description}

TOP CANDIDATES SUMMARY:
{summary}

Be specific: mention score ranges, common skill gaps, and concrete next steps.
Reply in plain text only (no JSON, no headers).
"""


# ── JSON helper ───────────────────────────────────────────────────────────────

def _parse_json(raw: str) -> dict:
    raw = re.sub(r"```json\s*", "", raw)
    raw = re.sub(r"```\s*", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
    return {}


def _parse_json_array(raw: str) -> list[dict]:
    raw = re.sub(r"```json\s*", "", raw)
    raw = re.sub(r"```\s*", "", raw).strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                return parsed if isinstance(parsed, list) else []
            except Exception:
                pass
    return []


# ── Graph factory ─────────────────────────────────────────────────────────────

def build_matching_graph(
    embedder,      # IEmbedder
    vector_store,  # IVectorStore
) -> Any:

    # ── Node 1 ────────────────────────────────────────────────────────────────
    async def embed_query(state: MatchingState) -> dict:
        skills = state.get("required_skills") or []
        # US-26: expand skills with known equivalences before embedding
        expanded_skills, equiv_map = expand_skills_with_equivalences(skills)

        jd = state["job_description"]
        if expanded_skills:
            jd = jd + "\nRequired skills (including equivalents): " + ", ".join(expanded_skills)

        t0 = time.monotonic()
        embedding = await embedder.embed_single(jd)
        logger.info(
            "[MatchGraph:embed_query] dim=%d  skills=%d→%d  (%.0fms)",
            len(embedding), len(skills), len(expanded_skills),
            (time.monotonic() - t0) * 1000,
        )
        return {"query_embedding": embedding, "skill_equiv_map": equiv_map}

    # ── Node 2 ────────────────────────────────────────────────────────────────
    async def vector_search(state: MatchingState) -> dict:
        # Only over-fetch by 1.5x, not 3x: vector search + rerank already
        # pre-rank candidates reasonably well, so scoring 3x more candidates
        # than needed through the expensive LLM step wasted most of the
        # token budget on candidates that would never surface in top_k anyway.
        over_k = max(int(state["top_k"] * 1.5), state["top_k"] + 3)
        t0 = time.monotonic()
        partitions = state.get("partition_names") or None

        try:
            raw = await vector_store.search(
                query_embedding=state["query_embedding"],
                top_k=over_k,
                min_score=state["min_score"],
                partition_names=partitions,
            )
            results = [
                {"candidate_id": r.candidate_id, "score": r.score,
                 "filename": r.filename, "excerpt": r.excerpt}
                for r in raw
            ]
            logger.info(
                "[MatchGraph:vector_search] %d candidates via Milvus  (%.0fms)",
                len(results), (time.monotonic() - t0) * 1000,
            )
        except Exception as milvus_err:
            logger.warning(
                "[MatchGraph:vector_search] Milvus unavailable (%s) — "
                "falling back to PostgreSQL candidate list",
                milvus_err,
            )
            from sqlalchemy import select as sa_select
            from app.infrastructure.database.session import AsyncSessionLocal
            from app.infrastructure.database.models import CandidateModel
            async with AsyncSessionLocal() as session:
                rows = await session.execute(
                    sa_select(
                        CandidateModel.candidate_id,
                        CandidateModel.filename,
                    ).where(CandidateModel.full_name.isnot(None))
                    .limit(over_k)
                )
                results = [
                    {"candidate_id": row.candidate_id, "score": 0.5,
                     "filename": row.filename or "", "excerpt": ""}
                    for row in rows
                ]
            logger.info(
                "[MatchGraph:vector_search] %d candidates via PostgreSQL fallback  (%.0fms)",
                len(results), (time.monotonic() - t0) * 1000,
            )

        return {"vector_results": results}

    # ── Node 3 ────────────────────────────────────────────────────────────────
    async def fetch_cv_content(state: MatchingState) -> dict:
        candidate_ids = [r["candidate_id"] for r in state["vector_results"]]
        if not candidate_ids:
            return {"candidate_texts": {}, "candidate_skills": {}}

        t0 = time.monotonic()
        candidate_texts:  dict[str, str]       = {}
        candidate_skills: dict[str, list[str]] = {}

        try:
            chunks = await vector_store.fetch_chunks_by_candidate_ids(candidate_ids)

            by_cid: dict[str, list[dict]] = defaultdict(list)
            for c in chunks:
                by_cid[c["candidate_id"]].append(c)

            for cid, clist in by_cid.items():
                clist.sort(key=lambda x: x.get("chunk_index", 0))
                candidate_texts[cid] = "\n".join(c["text"] for c in clist)
                for c in clist:
                    raw_skills = c.get("skills_json", "[]")
                    try:
                        skills = json.loads(raw_skills) if isinstance(raw_skills, str) else raw_skills
                        if skills:
                            candidate_skills[cid] = skills
                            break
                    except Exception:
                        pass
                if cid not in candidate_skills:
                    candidate_skills[cid] = []

            logger.info(
                "[MatchGraph:fetch_cv_content] %d/%d candidates via Milvus  (%.0fms)",
                len(candidate_texts), len(candidate_ids), (time.monotonic() - t0) * 1000,
            )

        except Exception as milvus_err:
            logger.warning(
                "[MatchGraph:fetch_cv_content] Milvus unavailable (%s) — "
                "falling back to PostgreSQL cv_raw_text",
                milvus_err,
            )

        # Some candidates can come back with zero Milvus chunks even when
        # Milvus itself is reachable (e.g. they were ingested while Milvus
        # was down, so PostgreSQL has them but no vectors were ever stored).
        # That case doesn't raise above, so it must be handled separately —
        # otherwise these candidates silently get NO text at all and the
        # LLM scoring step has nothing to evaluate, degrading everyone
        # missing text down to the same flat vector-only score.
        missing_ids = [cid for cid in candidate_ids if cid not in candidate_texts]
        if missing_ids:
            from sqlalchemy import select as sa_select
            from app.infrastructure.database.session import AsyncSessionLocal
            from app.infrastructure.database.models import CandidateModel

            async with AsyncSessionLocal() as session:
                rows = await session.execute(
                    sa_select(
                        CandidateModel.candidate_id,
                        CandidateModel.cv_raw_text,
                        CandidateModel.full_name,
                        CandidateModel.summary,
                        CandidateModel.skills_json,
                        CandidateModel.seniority_level,
                        CandidateModel.total_years_experience,
                    ).where(CandidateModel.candidate_id.in_(missing_ids))
                )
                for row in rows:
                    cid = row.candidate_id
                    # Use cv_raw_text if available, else build a summary text
                    if row.cv_raw_text:
                        candidate_texts[cid] = row.cv_raw_text
                    else:
                        parts = []
                        if row.full_name:
                            parts.append(f"Name: {row.full_name}")
                        if row.seniority_level:
                            parts.append(f"Level: {row.seniority_level}")
                        if row.total_years_experience:
                            parts.append(f"Experience: {row.total_years_experience} years")
                        if row.summary:
                            parts.append(f"Summary: {row.summary}")
                        candidate_texts[cid] = "\n".join(parts) or "No CV text available"

                    skills_data = row.skills_json or {}
                    if isinstance(skills_data, dict):
                        candidate_skills[cid] = skills_data.get("all_skills", [])
                    else:
                        candidate_skills[cid] = []

            logger.info(
                "[MatchGraph:fetch_cv_content] %d candidates filled from PostgreSQL fallback  (%.0fms)",
                len(missing_ids), (time.monotonic() - t0) * 1000,
            )

        return {"candidate_texts": candidate_texts, "candidate_skills": candidate_skills}

    # ── Node 4 ────────────────────────────────────────────────────────────────
    # Cross-encoder reranking (local Hugging Face model) has been removed —
    # scoring uses only the Orange LiteLLM proxy + vector similarity now.
    # Returning empty ce_scores makes format_response() fall back to its
    # existing vec_score/llm_total-only formula (see Node 6 below).
    async def cross_encode_rerank(state: MatchingState) -> dict:
        return {"ce_scores": {}}

    # ── Node 5 ────────────────────────────────────────────────────────────────
    async def llm_score_4criteria(state: MatchingState) -> dict:
        cv_texts   = state["candidate_texts"]
        jd         = state["job_description"]
        req_skills = ", ".join(state["required_skills"]) if state["required_skills"] else "not specified"
        equiv_map  = state.get("skill_equiv_map", {})
        weights    = state.get("scoring_weights", {})
        lang       = state.get("lang", "fr")
        lang_name  = "English" if lang == "en" else "French"

        # US-32 — get weights (floats 0-1, sum ≈ 1.0)
        wf_skills = weights.get("skills",     0.40)
        wf_exp    = weights.get("experience", 0.30)
        wf_edu    = weights.get("education",  0.20)
        wf_cult   = weights.get("culture",    0.10)

        # US-26 — format equivalences for the prompt
        if equiv_map:
            equiv_lines = "\n".join(
                f"  • {skill} ≈ {', '.join(alts)}"
                for skill, alts in equiv_map.items()
            )
        else:
            equiv_lines = "  None — use exact skill matching."

        if not cv_texts:
            return {"llm_evaluations": []}

        client = _get_llm_client()

        def _fallback_eval(candidate_id: str) -> dict:
            vec_score = next(
                (r["score"] for r in state["vector_results"]
                 if r["candidate_id"] == candidate_id), 0.5
            )
            return {
                "candidate_id":       candidate_id,
                "skills_score":       None,
                "experience_score":   None,
                "education_score":    None,
                "culture_score":      None,
                "total_score":        int(vec_score * 100),
                "matched_skills":     state["candidate_skills"].get(candidate_id, []),
                "missing_skills":     [],
                "cot_reasoning":      "AI scoring unavailable after retries — ranked by vector similarity only.",
                "recommendation":     "unknown",
                "profile_summary":    "Profile analysis unavailable — AI scoring failed after retries.",
                "key_strengths":      [],
                "key_weaknesses":     [],
                "recommendation_paragraph": (
                    f"AI analysis failed for this candidate. "
                    f"Ranked by vector similarity ({vec_score:.0%}) only — recommend manual review."
                ),
                "scoring_failed":     True,
            }

        def _obvious_eval(candidate_id: str, vector_score: float, tier: str) -> dict:
            """Fast-path for candidates whose vector similarity is already
            unambiguous (see _OBVIOUS_HIGH_THRESHOLD / _OBVIOUS_LOW_THRESHOLD).
            Not a failure — scoring_failed stays False — just a deliberate
            skip of the LLM call for a verdict that's already clear."""
            total = round(vector_score * 100)
            if tier == "high":
                recommendation = "selected"
                note = (
                    f"Correspondance sémantique très forte ({vector_score:.0%}) — "
                    "verdict évident, analyse IA détaillée jugée superflue."
                )
            else:
                recommendation = "rejected"
                note = (
                    f"Écart sémantique trop important ({vector_score:.0%}) avec le poste — "
                    "verdict évident, analyse IA détaillée jugée superflue."
                )
            return {
                "candidate_id":       candidate_id,
                "skills_score":       None,
                "experience_score":   None,
                "education_score":    None,
                "culture_score":      None,
                "total_score":        total,
                "matched_skills":     state["candidate_skills"].get(candidate_id, []),
                "missing_skills":     [],
                "cot_reasoning":      note,
                "recommendation":     recommendation,
                "profile_summary":    note,
                "key_strengths":      [],
                "key_weaknesses":     [],
                "recommendation_paragraph": note,
                "scoring_failed":     False,
            }

        async def _score_batch(
            candidate_batch: list[tuple[str, str]],
            prompt_template: str,
            tokens_per_candidate: int,
        ) -> list[dict]:
            ids = [cid for cid, _ in candidate_batch]

            # Pre-flight budget check — read-only, no side effects. If the
            # budget is already exhausted, skip the LLM call entirely (and
            # its retries) instead of paying for a call we already know we
            # can't afford; fall back straight to vector-similarity ranking.
            if not await cost_guard.is_budget_available():
                logger.warning(
                    "[MatchGraph:llm_score] LLM budget exhausted — skipping batch %s (fallback)",
                    [c[:8] for c in ids],
                )
                return [_fallback_eval(cid) for cid in ids]

            candidates_block = "\n\n".join(
                f"── CANDIDATE {i + 1} (ID: {cid}) ──\n{text[:1500]}"
                for i, (cid, text) in enumerate(candidate_batch)
            )
            prompt = prompt_template.format(
                n=len(candidate_batch),
                job_description=jd[:1200],
                required_skills=req_skills,
                equivalences_text=equiv_lines,
                candidates_block=candidates_block,
                lang_name=lang_name,
                w_skills=int(wf_skills * 100),
                w_exp   =int(wf_exp    * 100),
                w_edu   =int(wf_edu    * 100),
                w_cult  =int(wf_cult   * 100),
                wf_skills=round(wf_skills, 2),
                wf_exp   =round(wf_exp,    2),
                wf_edu   =round(wf_edu,    2),
                wf_cult  =round(wf_cult,   2),
            )
            max_retries = settings.llm_retries
            base_delay  = settings.llm_retry_base_delay
            max_tokens  = tokens_per_candidate * len(candidate_batch) + 200
            last_exc: Exception | None = None

            for attempt in range(1, max_retries + 1):
                try:
                    async with llm_gate:
                        resp = await client.chat.completions.create(
                            model=settings.litellm_model,
                            messages=[{"role": "user", "content": prompt}],
                            temperature=0.1,
                            max_tokens=max_tokens,
                        )
                    raw = resp.choices[0].message.content or ""
                    parsed_list = _parse_json_array(raw)
                    if not parsed_list:
                        raise ValueError("empty/invalid JSON array")
                    try:
                        if resp.usage:
                            await cost_guard.check_and_record(
                                prompt_tokens=resp.usage.prompt_tokens,
                                completion_tokens=resp.usage.completion_tokens or 0,
                            )
                    except Exception as guard_exc:
                        logger.warning("[MatchGraph:llm_score] cost_guard failed (non-fatal): %s", guard_exc)

                    # Map results back by candidate_id; fall back to positional
                    # order if the model drifted on the id string.
                    by_returned_id = {
                        e.get("candidate_id"): e for e in parsed_list if isinstance(e, dict)
                    }
                    out: list[dict] = []
                    for i, cid in enumerate(ids):
                        ev = by_returned_id.get(cid)
                        if ev is None and i < len(parsed_list) and isinstance(parsed_list[i], dict):
                            ev = parsed_list[i]
                        if ev is None:
                            out.append(_fallback_eval(cid))
                        else:
                            ev["candidate_id"]  = cid
                            ev["scoring_failed"] = False
                            out.append(ev)
                    return out
                except Exception as exc:
                    last_exc = exc
                    err_str = str(exc)
                    rate_limited = is_rate_limit_error(err_str)
                    if attempt < max_retries and not await cost_guard.is_budget_available():
                        logger.warning(
                            "[MatchGraph:llm_score] budget exhausted mid-retry for %s — "
                            "stopping retries, using fallback",
                            [c[:8] for c in ids],
                        )
                        break
                    if attempt < max_retries:
                        default_delay = base_delay * (2 ** (attempt - 1))
                        delay = (
                            rate_limit_wait_seconds(err_str, default_delay)
                            if rate_limited else default_delay
                        )
                        logger.warning(
                            "[MatchGraph:llm_score] batch %s failed (attempt %d/%d, rate_limit=%s): %s — retrying in %.1fs",
                            [c[:8] for c in ids], attempt, max_retries, rate_limited, exc, delay,
                        )
                        await asyncio.sleep(delay)

            logger.error(
                "[MatchGraph:llm_score] batch %s exhausted all %d retries: %s — using fallback",
                [c[:8] for c in ids], max_retries, last_exc,
            )
            return [_fallback_eval(cid) for cid in ids]

        # Group candidates into multi-candidate calls to conserve the LLM
        # token budget: the job description + instructions are sent ONCE per
        # group instead of once per candidate, and free-text fields are kept
        # short. Batch size covers a typical upload batch (e.g. 12 CVs) in a
        # SINGLE call instead of being split into several redundant ones.
        # Concurrency across groups (when there is more than one) is bounded
        # by the shared llm_gate semaphore — the same gate extraction,
        # reranking and recruiter-advice calls use — instead of a hand-rolled
        # wave-plus-fixed-sleep loop that couldn't see what the rest of the
        # app was doing to the shared Orange proxy quota.
        candidates_per_call = _CANDIDATES_PER_LLM_CALL

        # ── Fast-path + tiered analysis depth ───────────────────────────────
        # 1) Candidates whose vector similarity is already unambiguous skip
        #    the LLM entirely (_obvious_eval) — see threshold comments above.
        # 2) Of the remaining "ambiguous" candidates, only the top
        #    _MAX_FULL_ANALYSIS (by vector similarity) get the full rich
        #    narrative prompt; the rest get the compact _LIGHT_SCORING_PROMPT
        #    — same precise numeric score, no long-form text nobody reads
        #    for a non-finalist.
        vec_score_by_id = {r["candidate_id"]: r["score"] for r in state["vector_results"]}

        obvious_evals: list[dict] = []
        ambiguous_items: list[tuple[str, str]] = []
        for cid, text in cv_texts.items():
            vscore = vec_score_by_id.get(cid, 0.5)
            if vscore >= _OBVIOUS_HIGH_THRESHOLD:
                obvious_evals.append(_obvious_eval(cid, vscore, "high"))
            elif vscore <= _OBVIOUS_LOW_THRESHOLD:
                obvious_evals.append(_obvious_eval(cid, vscore, "low"))
            else:
                ambiguous_items.append((cid, text))

        ambiguous_items.sort(key=lambda item: vec_score_by_id.get(item[0], 0.5), reverse=True)
        finalist_items = ambiguous_items[:_MAX_FULL_ANALYSIS]
        light_items    = ambiguous_items[_MAX_FULL_ANALYSIS:]

        def _make_groups(pool: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
            return [pool[i: i + candidates_per_call] for i in range(0, len(pool), candidates_per_call)]

        finalist_groups = _make_groups(finalist_items)
        light_groups    = _make_groups(light_items)

        evaluations: list[dict] = list(obvious_evals)

        t0 = time.monotonic()
        results = await asyncio.gather(
            *[_score_batch(group, _SCORING_PROMPT, 400) for group in finalist_groups],
            *[_score_batch(group, _LIGHT_SCORING_PROMPT, 120) for group in light_groups],
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, Exception):
                logger.error("[MatchGraph:llm_score] Batch exception: %s", r)
            else:
                evaluations.extend(r)

        logger.info(
            "[MatchGraph:llm_score_4criteria] %d evaluations total — "
            "%d obvious-skip (0 LLM calls), %d full-analysis via %d calls, "
            "%d light-scored via %d calls  (%.0fms)",
            len(evaluations), len(obvious_evals),
            len(finalist_items), len(finalist_groups),
            len(light_items), len(light_groups),
            (time.monotonic() - t0) * 1000,
        )
        return {"llm_evaluations": evaluations}

    # ── Node 6 ────────────────────────────────────────────────────────────────
    async def format_response(state: MatchingState) -> dict:
        vector_by_id = {r["candidate_id"]: r for r in state["vector_results"]}
        ce_scores    = state.get("ce_scores", {})
        evaluations  = {e["candidate_id"]: e for e in state["llm_evaluations"]}
        top_k        = state["top_k"]

        merged: list[dict] = []
        for cid, vec_r in vector_by_id.items():
            vec_score = vec_r["score"]
            ce_score  = ce_scores.get(cid, vec_score)
            llm_eval  = evaluations.get(cid, {})
            llm_total = llm_eval.get("total_score", int(vec_score * 100)) / 100.0

            if state["use_reranking"] and state["ce_scores"]:
                final = 0.25 * vec_score + 0.25 * ce_score + 0.50 * llm_total
            else:
                final = 0.40 * vec_score + 0.60 * llm_total

            merged.append({
                "candidate_id":     cid,
                "filename":         vec_r.get("filename", ""),
                "excerpt":          vec_r.get("excerpt", ""),
                # Scores
                "vector_score":     round(vec_score, 4),
                "ce_score":         round(ce_score, 4),
                "llm_total_score":  round(llm_total, 4),
                "final_score":      round(final, 4),
                # 4-criteria breakdown (US-29)
                "skills_score":     llm_eval.get("skills_score"),
                "experience_score": llm_eval.get("experience_score"),
                "education_score":  llm_eval.get("education_score"),
                "culture_score":    llm_eval.get("culture_score"),
                # Skills detail (US-29)
                "matched_skills":   llm_eval.get("matched_skills", []),
                "missing_skills":   llm_eval.get("missing_skills", []),
                # US-27: AI explanation
                "cot_reasoning":   llm_eval.get("cot_reasoning", ""),
                "recommendation":  llm_eval.get("recommendation", "unknown"),
                # New — AI candidate profile
                "profile_summary":          llm_eval.get("profile_summary", ""),
                "key_strengths":            llm_eval.get("key_strengths", []),
                "key_weaknesses":           llm_eval.get("key_weaknesses", []),
                "recommendation_paragraph": llm_eval.get("recommendation_paragraph", ""),
            })

        merged.sort(key=lambda x: x["final_score"], reverse=True)
        top = merged[:top_k]
        for i, c in enumerate(top, 1):
            c["rank"] = i

        advice = await _generate_recruiter_advice(state["job_description"], top)

        logger.info(
            "[MatchGraph:format_response] top_k=%d  final_scores=%s",
            len(top), [round(c["final_score"], 2) for c in top],
        )
        return {"ranked_candidates": top, "recruiter_advice": advice}

    # ── Routing ───────────────────────────────────────────────────────────────

    def route_after_search(state: MatchingState) -> str:
        return "no_results" if not state["vector_results"] else "fetch_cv_content"

    def route_after_fetch(state: MatchingState) -> str:
        pool_size = len(state["candidate_texts"])
        if state["use_reranking"] and pool_size > _CANDIDATES_PER_LLM_CALL:
            return "cross_encode_rerank"
        return "llm_score_4criteria"

    async def no_results(state: MatchingState) -> dict:
        return {
            "ranked_candidates": [],
            "recruiter_advice":  "No candidates found matching this job description.",
        }

    # ── Build graph ───────────────────────────────────────────────────────────
    graph = StateGraph(MatchingState)

    graph.add_node("embed_query",         embed_query)
    graph.add_node("vector_search",       vector_search)
    graph.add_node("fetch_cv_content",    fetch_cv_content)
    graph.add_node("cross_encode_rerank", cross_encode_rerank)
    graph.add_node("llm_score_4criteria", llm_score_4criteria)
    graph.add_node("format_response",     format_response)
    graph.add_node("no_results",          no_results)

    graph.add_edge(START, "embed_query")
    graph.add_edge("embed_query", "vector_search")
    graph.add_conditional_edges(
        "vector_search", route_after_search,
        {"no_results": "no_results", "fetch_cv_content": "fetch_cv_content"},
    )
    graph.add_conditional_edges(
        "fetch_cv_content", route_after_fetch,
        {"cross_encode_rerank": "cross_encode_rerank",
         "llm_score_4criteria": "llm_score_4criteria"},
    )
    graph.add_edge("cross_encode_rerank", "llm_score_4criteria")
    graph.add_edge("llm_score_4criteria", "format_response")
    graph.add_edge("format_response", END)
    graph.add_edge("no_results", END)

    return graph.compile()


# ── Recruiter advice helper ───────────────────────────────────────────────────

async def _generate_recruiter_advice(job_description: str, top: list[dict]) -> str:
    if not top:
        return "No candidates found matching this job description."

    if not await cost_guard.is_budget_available():
        logger.warning("[MatchGraph] LLM budget exhausted — skipping recruiter advice (fallback)")
        n_sel = sum(1 for c in top if c.get("recommendation") == "selected")
        return (
            f"{n_sel} out of {len(top)} candidate(s) are recommended. "
            "Review individual profiles for full details."
        )

    try:
        summary_lines = [
            f"{i+1}. {c.get('filename', c['candidate_id'][:8])} — "
            f"score={c['final_score']:.0%}  "
            f"skills={c.get('skills_score', '?')}  xp={c.get('experience_score', '?')}  "
            f"strengths={c.get('key_strengths', [])[:2]}  "
            f"missing={c.get('missing_skills', [])[:3]}"
            for i, c in enumerate(top[:5])
        ]
        prompt = _ADVICE_PROMPT.format(
            job_description=job_description[:1000],
            summary="\n".join(summary_lines),
        )
        client = _get_llm_client()
        async with llm_gate:
            resp = await client.chat.completions.create(
                model=settings.litellm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=350,
            )
        if resp.usage:
            try:
                await cost_guard.check_and_record(
                    prompt_tokens=resp.usage.prompt_tokens,
                    completion_tokens=resp.usage.completion_tokens or 0,
                )
            except Exception as guard_exc:
                logger.warning("[MatchGraph] cost_guard record failed (non-fatal): %s", guard_exc)
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.warning("[MatchGraph] Recruiter advice failed: %s", exc)
        n_sel = sum(1 for c in top if c.get("recommendation") == "selected")
        return (
            f"{n_sel} out of {len(top)} candidate(s) are recommended. "
            "Review individual profiles for full details."
        )
