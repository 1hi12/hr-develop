"""
interview_prep_graph.py
=======================
LangGraph pipeline for AI-generated interview questions — implements US-53.

Flow
----
  START
    ↓
  load_context         ← validate inputs, extract key info from CV + JD
    ↓
  identify_focus_areas ← find skill gaps, experience gaps, key strengths to probe
    ↓
  generate_questions   ← produce categorised, tailored interview questions
    ↓
  format_output        ← structure for API response
    ↓
   END

Usage
-----
  graph = build_interview_prep_graph()
  result = await graph.ainvoke({
      "candidate_name":  "Alice Martin",
      "cv_text":         "...",      # raw CV text or extracted summary
      "job_description": "...",
      "job_title":       "Senior Backend Engineer",
      "n_questions":     10,         # how many questions to generate (default 10)
  })
  # result["interview_questions"] → list of question dicts
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

class InterviewPrepState(TypedDict):
    # Inputs
    candidate_name:  str
    cv_text:         str
    job_description: str
    job_title:       str
    n_questions:     int

    # Phase 1: context analysis
    candidate_strengths:  list[str]
    skill_gaps:           list[str]
    experience_gaps:      list[str]
    focus_areas:          list[str]

    # Phase 2: generated questions
    # list of {question, type, rationale, difficulty}
    interview_questions:  list[dict]

    error:                Optional[str]


# ── Prompts ───────────────────────────────────────────────────────────────────

_CONTEXT_PROMPT = """\
You are an expert technical recruiter preparing for an interview.

Job Title: {job_title}

Job Description:
{job_description}

Candidate CV:
{cv_text}

Analyze the fit and return ONLY valid JSON:
{{
  "candidate_strengths":  ["<specific strength relevant to this job>"],
  "skill_gaps":           ["<required skill the candidate lacks or hasn't demonstrated>"],
  "experience_gaps":      ["<experience area to probe: unclear duration, missing industry, etc.>"],
  "focus_areas":          ["<key topic to focus on in interview, e.g. 'distributed systems design'>"]
}}
"""

_QUESTIONS_PROMPT = """\
You are a senior technical interviewer. Generate exactly {n_questions} targeted interview \
questions for this candidate.

Job: {job_title}
Candidate: {candidate_name}

Key focus areas: {focus_areas}
Skill gaps to probe: {skill_gaps}
Strengths to validate: {candidate_strengths}

Question types to include (distribute them):
  - "technical"    — tests hard skills, coding, architecture
  - "behavioral"   — STAR-method, past experience (e.g. "Tell me about a time...")
  - "situational"  — hypothetical scenarios relevant to the role
  - "gap_probe"    — directly address a gap or unclear CV section
  - "motivation"   — why this company, why this role, career goals

Return ONLY a valid JSON array with exactly {n_questions} objects:
[
  {{
    "question":   "<the full interview question>",
    "type":       "technical|behavioral|situational|gap_probe|motivation",
    "rationale":  "<why this question is relevant for this candidate — 1 sentence>",
    "difficulty": "easy|medium|hard"
  }},
  ...
]
"""


def _parse_json_array(raw: str) -> list:
    raw = re.sub(r"```json\s*", "", raw)
    raw = re.sub(r"```\s*", "", raw).strip()
    try:
        result = json.loads(raw)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(0))
            if isinstance(result, list):
                return result
        except Exception:
            pass
    return []


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

def build_interview_prep_graph() -> Any:
    client = AsyncOpenAI(
        api_key=settings.litellm_api_key,
        base_url=settings.litellm_base_url,
        http_client=httpx.AsyncClient(verify=False),
    )

    # ── Node 1 ────────────────────────────────────────────────────────────────
    async def load_context(state: InterviewPrepState) -> dict:
        if not state.get("cv_text") or not state.get("job_description"):
            return {"error": "cv_text and job_description are required"}

        prompt = _CONTEXT_PROMPT.format(
            job_title=state.get("job_title", ""),
            job_description=state["job_description"][:2000],
            cv_text=state["cv_text"][:3000],
        )
        try:
            from app.infrastructure.llm.llm_gate import llm_gate
            async with llm_gate:
                resp = await client.chat.completions.create(
                    model=settings.litellm_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=512,
                )
            data = _parse_json(resp.choices[0].message.content or "")
            logger.info(
                "[InterviewGraph:load_context] gaps=%d focus=%d",
                len(data.get("skill_gaps", [])),
                len(data.get("focus_areas", [])),
            )
            return {
                "candidate_strengths": data.get("candidate_strengths", []),
                "skill_gaps":          data.get("skill_gaps", []),
                "experience_gaps":     data.get("experience_gaps", []),
                "focus_areas":         data.get("focus_areas", []),
            }
        except Exception as exc:
            logger.error("[InterviewGraph:load_context] %s", exc)
            return {"error": str(exc)}

    # ── Node 2 ────────────────────────────────────────────────────────────────
    async def generate_questions(state: InterviewPrepState) -> dict:
        if state.get("error"):
            return {}

        n = state.get("n_questions", 10)
        prompt = _QUESTIONS_PROMPT.format(
            n_questions=n,
            job_title=state.get("job_title", ""),
            candidate_name=state.get("candidate_name", "the candidate"),
            focus_areas=", ".join(state.get("focus_areas", [])[:5]),
            skill_gaps=", ".join(state.get("skill_gaps", [])[:5]),
            candidate_strengths=", ".join(state.get("candidate_strengths", [])[:5]),
        )
        try:
            from app.infrastructure.llm.llm_gate import llm_gate
            async with llm_gate:
                resp = await client.chat.completions.create(
                    model=settings.litellm_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.4,
                    max_tokens=2048,
                )
            questions = _parse_json_array(resp.choices[0].message.content or "")
            logger.info(
                "[InterviewGraph:generate_questions] %d questions generated", len(questions)
            )
            return {"interview_questions": questions}
        except Exception as exc:
            logger.error("[InterviewGraph:generate_questions] %s", exc)
            return {"error": str(exc)}

    # ── Node 3 ────────────────────────────────────────────────────────────────
    def format_output(state: InterviewPrepState) -> dict:
        if state.get("error") or not state.get("interview_questions"):
            return {
                "interview_questions": [],
            }
        # Ensure every question has the required fields
        cleaned = []
        for q in state["interview_questions"]:
            if not isinstance(q, dict) or not q.get("question"):
                continue
            cleaned.append({
                "question":   q.get("question", ""),
                "type":       q.get("type", "technical"),
                "rationale":  q.get("rationale", ""),
                "difficulty": q.get("difficulty", "medium"),
            })
        return {"interview_questions": cleaned}

    # ── Routing ───────────────────────────────────────────────────────────────
    def route_after_context(state: InterviewPrepState) -> str:
        return "format_output" if state.get("error") else "generate_questions"

    # ── Build graph ───────────────────────────────────────────────────────────
    graph = StateGraph(InterviewPrepState)

    graph.add_node("load_context",       load_context)
    graph.add_node("generate_questions", generate_questions)
    graph.add_node("format_output",      format_output)

    graph.add_edge(START, "load_context")
    graph.add_conditional_edges(
        "load_context", route_after_context,
        {
            "generate_questions": "generate_questions",
            "format_output":      "format_output",
        },
    )
    graph.add_edge("generate_questions", "format_output")
    graph.add_edge("format_output", END)

    return graph.compile()
