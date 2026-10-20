"""
jd_enhancement_graph.py
========================
LangGraph pipeline for AI-powered job description improvement — implements US-11.

Flow
----
  START
    ↓
  analyze_jd           ← extract domain, skills, seniority from JD via LLM
    ↓
  suggest_improvements ← suggest missing skills, better wording, attractiveness tips
    ↓
  format_suggestions   ← structure output for API response
    ↓
   END

Usage
-----
  graph = build_jd_enhancement_graph()
  result = await graph.ainvoke({
      "job_title":       "Senior Python Developer",
      "job_description": "We need a dev...",
      "department":      "Engineering",   # optional
  })
  # result["suggestions"] contains the structured AI recommendations
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

import httpx
from openai import AsyncOpenAI
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from app.config.settings import settings

logger = logging.getLogger(__name__)


# ── State ─────────────────────────────────────────────────────────────────────

class JDEnhancementState(TypedDict):
    # Inputs
    job_title:       str
    job_description: str
    department:      str

    # Phase 1: analysis
    detected_domain:     str
    detected_seniority:  str
    detected_skills:     list[str]
    missing_skills:      list[str]
    analysis_notes:      str

    # Phase 2: suggestions
    improved_summary:    str
    skill_additions:     list[str]
    wording_tips:        list[str]
    attractiveness_tips: list[str]

    # Output
    suggestions:         dict

    error:               Optional[str]


# ── Prompts ───────────────────────────────────────────────────────────────────

_ANALYZE_PROMPT = """\
You are a senior HR consultant and technical recruiter. Analyze this job description.

Job Title: {job_title}
Department: {department}

Job Description:
{job_description}

Return ONLY valid JSON:
{{
  "detected_domain":    "<e.g. Backend Development, Data Science, DevOps>",
  "detected_seniority": "<intern|junior|mid|senior|lead>",
  "detected_skills":    ["skill1", "skill2"],
  "missing_skills":     ["<common skills for this role that are NOT mentioned in the JD>"],
  "analysis_notes":     "<2 sentences: main weaknesses of this JD>"
}}
"""

_SUGGEST_PROMPT = """\
You are an expert at writing compelling, inclusive job descriptions that attract top talent.

Job Title: {job_title}
Current Job Description:
{job_description}

Analysis:
- Domain: {detected_domain}
- Missing skills that should be mentioned: {missing_skills}
- Weaknesses: {analysis_notes}

Provide concrete improvements. Return ONLY valid JSON:
{{
  "improved_summary": "<rewritten opening paragraph — 3-4 sentences, engaging and clear>",
  "skill_additions": [
    "<specific skill to add with justification, e.g. 'Add Docker: standard for this role'>",
    "<specific skill to add>"
  ],
  "wording_tips": [
    "<concrete wording change, e.g. 'Replace: required 10 years → preferred 5+ years experience'>",
    "<concrete wording change>"
  ],
  "attractiveness_tips": [
    "<tip to attract better candidates, e.g. 'Add remote work policy'>",
    "<tip>"
  ]
}}
"""


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


# ── Graph factory ─────────────────────────────────────────────────────────────

def build_jd_enhancement_graph() -> Any:
    client = AsyncOpenAI(
        api_key=settings.litellm_api_key,
        base_url=settings.litellm_base_url,
        http_client=httpx.AsyncClient(verify=False),
    )

    # ── Node 1 ────────────────────────────────────────────────────────────────
    async def analyze_jd(state: JDEnhancementState) -> dict:
        prompt = _ANALYZE_PROMPT.format(
            job_title=state["job_title"],
            department=state.get("department", "Not specified"),
            job_description=state["job_description"][:4000],
        )
        try:
            from app.infrastructure.llm.llm_gate import llm_gate
            async with llm_gate:
                resp = await client.chat.completions.create(
                    model=settings.litellm_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=1024,
                )
            data = _parse_json(resp.choices[0].message.content or "")
            logger.info(
                "[JDGraph:analyze_jd] domain=%s  missing_skills=%d",
                data.get("detected_domain"), len(data.get("missing_skills", [])),
            )
            return {
                "detected_domain":    data.get("detected_domain", ""),
                "detected_seniority": data.get("detected_seniority", "mid"),
                "detected_skills":    data.get("detected_skills", []),
                "missing_skills":     data.get("missing_skills", []),
                "analysis_notes":     data.get("analysis_notes", ""),
            }
        except Exception as exc:
            logger.error("[JDGraph:analyze_jd] %s", exc)
            return {"error": str(exc)}

    # ── Node 2 ────────────────────────────────────────────────────────────────
    async def suggest_improvements(state: JDEnhancementState) -> dict:
        if state.get("error"):
            return {}
        prompt = _SUGGEST_PROMPT.format(
            job_title=state["job_title"],
            job_description=state["job_description"][:3000],
            detected_domain=state.get("detected_domain", ""),
            missing_skills=", ".join(state.get("missing_skills", [])[:10]),
            analysis_notes=state.get("analysis_notes", ""),
        )
        try:
            from app.infrastructure.llm.llm_gate import llm_gate
            async with llm_gate:
                resp = await client.chat.completions.create(
                    model=settings.litellm_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=1024,
                )
            data = _parse_json(resp.choices[0].message.content or "")
            logger.info("[JDGraph:suggest_improvements] done")
            return {
                "improved_summary":    data.get("improved_summary", ""),
                "skill_additions":     data.get("skill_additions", []),
                "wording_tips":        data.get("wording_tips", []),
                "attractiveness_tips": data.get("attractiveness_tips", []),
            }
        except Exception as exc:
            logger.error("[JDGraph:suggest_improvements] %s", exc)
            return {"error": str(exc)}

    # ── Node 3 ────────────────────────────────────────────────────────────────
    def format_suggestions(state: JDEnhancementState) -> dict:
        if state.get("error"):
            return {
                "suggestions": {
                    "error": state["error"],
                    "status": "failed",
                }
            }
        suggestions = {
            "status":              "success",
            "analysis": {
                "detected_domain":    state.get("detected_domain", ""),
                "detected_seniority": state.get("detected_seniority", ""),
                "detected_skills":    state.get("detected_skills", []),
                "missing_skills":     state.get("missing_skills", []),
                "analysis_notes":     state.get("analysis_notes", ""),
            },
            "improvements": {
                "improved_summary":    state.get("improved_summary", ""),
                "skill_additions":     state.get("skill_additions", []),
                "wording_tips":        state.get("wording_tips", []),
                "attractiveness_tips": state.get("attractiveness_tips", []),
            },
        }
        return {"suggestions": suggestions}

    # ── Routing ───────────────────────────────────────────────────────────────
    def route_after_analysis(state: JDEnhancementState) -> str:
        return "format_suggestions" if state.get("error") else "suggest_improvements"

    # ── Build graph ───────────────────────────────────────────────────────────
    graph = StateGraph(JDEnhancementState)

    graph.add_node("analyze_jd",           analyze_jd)
    graph.add_node("suggest_improvements", suggest_improvements)
    graph.add_node("format_suggestions",   format_suggestions)

    graph.add_edge(START, "analyze_jd")
    graph.add_conditional_edges(
        "analyze_jd", route_after_analysis,
        {
            "suggest_improvements": "suggest_improvements",
            "format_suggestions":   "format_suggestions",
        },
    )
    graph.add_edge("suggest_improvements", "format_suggestions")
    graph.add_edge("format_suggestions", END)

    return graph.compile()
