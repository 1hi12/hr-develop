import asyncio
import json
import logging
import os
import re
from typing import Any

import certifi
import httpx
from openai import AsyncOpenAI

from app.config.settings import settings
from app.agent.prompts.extraction_prompt import (
    GENERAL_INFO_PROMPT,
    SKILLS_EXTRACTION_PROMPT,
    SENIORITY_PROMPT,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# Configuration API
# ──────────────────────────────────────────────────────────
def _get_client() -> AsyncOpenAI:
    """Create client with correct API key from settings (lazy initialization)."""
    return AsyncOpenAI(
        api_key=settings.litellm_api_key,  # Use LiteLLM API key
        base_url=settings.litellm_base_url,  # Use LiteLLM proxy URL
        http_client=httpx.AsyncClient(verify=certifi.where()),
    )

# Client will be lazily initialized on first use
_client: AsyncOpenAI | None = None

# ──────────────────────────────────────────────────────────
# Appel LLM générique
# ──────────────────────────────────────────────────────────

async def _call_gemini (prompt: str, cv_text: str) -> dict[str, Any]:
    """Appel LiteLLM (OpenAI via Orange Proxy) avec parsing JSON robuste."""
    global _client
    
    # Lazy initialization of client
    if _client is None:
        _client = _get_client()
        logger.info("[LLM] Client initialized with model: %s", settings.litellm_model)
    
    user_content = prompt.format(cv_text=cv_text[:16000])

    try:
        response = await _client.chat.completions.create(
            model=settings.litellm_model,
            messages=[
                {"role": "system", "content": "You are a precise CV parsing assistant. Answer only with valid JSON."},
                {"role": "user",   "content": user_content},
            ],
            temperature=0.1,
            max_tokens=4096,
        )

        raw = response.choices[0].message.content
        if raw is None:
            logger.warning("[LLM] Empty response from LiteLLM")
            return {}
        return _parse_json(raw.strip())

    except Exception as e:
        logger.error(f"[LLM] Erreur appel LiteLLM : {e}")
        return {}


def _parse_json(raw: str) -> dict[str, Any]:
    """Nettoie et parse la réponse JSON (très tolérant)."""
    raw = re.sub(r"```json\s*", "", raw)
    raw = re.sub(r"```\s*", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL | re.MULTILINE)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
    logger.warning(f"[LLM] JSON invalide : {raw[:200]}…")
    return {}


# ──────────────────────────────────────────────────────────
# Extraction compétences (Phase 4)
# ──────────────────────────────────────────────────────────

async def extract_skills_gemini (cv_text: str) -> dict[str, Any]:
    """Extrait les compétences structurées via gemini 3-235B-A22B."""
    if not cv_text or len(cv_text.strip()) < 50:
        return _empty_skills()

    data = await _call_gemini (SKILLS_EXTRACTION_PROMPT, cv_text)

    if not data:
        return _fallback_regex(cv_text)

    technical   = _clean_list(data.get("technical", []))
    frameworks  = _clean_list(data.get("frameworks", []))
    databases   = _clean_list(data.get("databases", []))
    devops      = _clean_list(data.get("devops", []))
    soft        = _clean_list(data.get("soft_skills", []))
    languages   = _clean_list(data.get("languages", []))
    all_skills  = list(dict.fromkeys(technical + frameworks + databases + devops))

    logger.info(
        f"[LLM] Skills extraits — tech={len(technical)}, "
        f"frameworks={len(frameworks)}, total={len(all_skills)}"
    )

    return {
        "technical":   technical,
        "frameworks":  frameworks,
        "databases":   databases,
        "devops":      devops,
        "soft_skills": soft,
        "languages":   languages,
        "all_skills":  all_skills,
    }


# ──────────────────────────────────────────────────────────
# Extraction infos générales + séniorité (3 appels parallèles)
# ──────────────────────────────────────────────────────────

async def extract_info_gemini (
    cv_text: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """
    3 appels gemini 3 en parallèle :
      - general_info
      - skills_data
      - seniority_data
    """
    results = await asyncio.gather(
        _call_gemini (GENERAL_INFO_PROMPT, cv_text),
        _call_gemini (SKILLS_EXTRACTION_PROMPT, cv_text),
        _call_gemini (SENIORITY_PROMPT, cv_text),
        return_exceptions=True,
    )

    general   = results[0] if not isinstance(results[0], Exception) else {}
    skills    = results[1] if not isinstance(results[1], Exception) else {}
    seniority = results[2] if not isinstance(results[2], Exception) else {}

    logger.info(
        f"[LLM] 3 appels parallèles terminés — "
        f"general={bool(general)}, skills={bool(skills)}, seniority={bool(seniority)}"
    )

    return (
        general   if isinstance(general,   dict) else {},
        skills    if isinstance(skills,    dict) else {},
        seniority if isinstance(seniority, dict) else {},
    )


# ──────────────────────────────────────────────────────────
# Utilitaires
# ──────────────────────────────────────────────────────────

def _clean_list(items: list[Any]) -> list[str]:
    return [str(i).strip() for i in items if isinstance(i, str) and i.strip()]


def _empty_skills() -> dict[str, Any]:
    return {
        "technical": [], "frameworks": [], "databases": [],
        "devops": [], "soft_skills": [], "languages": [], "all_skills": [],
    }


_KNOWN_SKILLS: list[str] = [
    "Python", "JavaScript", "TypeScript", "Java", "C++", "Go", "Rust",
    "FastAPI", "Django", "Flask", "React", "Vue", "Angular", "Next.js",
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch",
    "Docker", "Kubernetes", "AWS", "GCP", "Azure", "Git", "Linux",
    "TensorFlow", "PyTorch", "LangChain", "Milvus",
    "REST", "GraphQL", "WebSocket", "Kafka",
]


def _fallback_regex(cv_text: str) -> dict[str, Any]:
    found = [
        s for s in _KNOWN_SKILLS
        if re.search(rf"\b{re.escape(s)}\b", cv_text, re.IGNORECASE)
    ]
    logger.info(f"[LLM] Fallback regex — {len(found)} skills trouvés")
    return {**_empty_skills(), "technical": found, "all_skills": found}
