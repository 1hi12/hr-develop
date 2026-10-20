"""
ranking_service.py
==================
FIX COMPLET :
  - fetch_selected_cvs retourne 340 chunks (liste de dicts)
  - Chaque chunk : {chunk_id, candidate_id, text, section, filename, ...}
  - On regroupe les chunks par candidate_id et on concatène les textes
  - Le cv_id envoyé au LLM = candidate_id réel Milvus
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import defaultdict
from typing import Any

import numpy as np
from dotenv import load_dotenv

from app.data.schemas.cv import JobDescription
from app.agent.tools.cv_extractor.embedder import embed_single_query
from app.agent.tools.cv_extractor.language_detection import (
    detect_language,
    get_localized_prompts,
    get_localized_thinking_messages,
)
from app.services.retrieval_service import fetch_selected_cvs
from app.config.settings import settings

load_dotenv()
logger = logging.getLogger(__name__)

# ───────────────────────────────────────────────────────────────────────────
# CONFIG
# ───────────────────────────────────────────────────────────────────────────

# ✅ Migration to LiteLLM proxy Orange

MODEL_NAME: str             = settings.litellm_model  # "openai/gpt-4o"
SELECTION_THRESHOLD: float  = 0.35
DEFAULT_BATCH_SIZE: int     = 5
LLM_RETRIES: int            = 3
LLM_RETRY_BASE_DELAY: float = 2.0

# Initialize LiteLLM client
import httpx
from openai import AsyncOpenAI

_client = AsyncOpenAI(
    api_key=settings.litellm_api_key,
    base_url=settings.litellm_base_url,
    http_client=httpx.AsyncClient(verify=False),  # SSL disabled for corporate proxy
)


logger.info("[ranking] LiteLLM client initialized (model=%s)", MODEL_NAME)


# ───────────────────────────────────────────────────────────────────────────
# NORMALISATION DES CHUNKS MILVUS -> dict[candidate_id -> texte_complet]
# ───────────────────────────────────────────────────────────────────────────

def _normalize_cv_texts(raw: Any) -> dict[str, str]:
    """
    Schéma Milvus réel :
      chunk_id | candidate_id | text | section | filename | chunk_index | skills_json | embedding

    fetch_selected_cvs retourne une liste de ces chunks.
    On regroupe par candidate_id en triant par chunk_index pour
    reconstituer le texte complet de chaque CV.
    """
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}

    if not isinstance(raw, list):
        logger.error("[ranking] Format inattendu : %s", type(raw))
        return {}

    grouped: dict[str, list[tuple[int, str]]] = defaultdict(list)

    for item in raw:
        if not isinstance(item, dict):
            continue

        candidate_id = (
            item.get("candidate_id")
            or item.get("cv_id")
            or item.get("id")
            or "unknown"
        )
        text = (
            item.get("text")
            or item.get("chunk_text")
            or item.get("content")
            or ""
        )
        chunk_index = int(item.get("chunk_index", 0) or 0)
        grouped[str(candidate_id)].append((chunk_index, str(text)))

    result: dict[str, str] = {}
    for candidate_id, chunks in grouped.items():
        chunks.sort(key=lambda x: x[0])
        full_text = "\n".join(t for _, t in chunks if t.strip())
        result[candidate_id] = full_text

    logger.info(
        "[ranking] Normalisation : %d chunks -> %d candidats uniques",
        len(raw), len(result),
    )
    for cid, txt in list(result.items())[:3]:
        logger.debug("[ranking] Candidat %s -> %d chars", cid, len(txt))

    return result


# ───────────────────────────────────────────────────────────────────────────
# HELPERS LLM
# ───────────────────────────────────────────────────────────────────────────

async def _call_llm(prompt: str) -> str:
    """Call LiteLLM via AsyncOpenAI with retry logic."""
    from app.infrastructure.llm.llm_gate import llm_gate
    for attempt in range(1, LLM_RETRIES + 1):
        try:
            async with llm_gate:
                response = await _client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=4096,
                )
                return response.choices[0].message.content or ""
                
        except Exception as exc:
            err_str = str(exc)
            
            # Rate limit 429 → wait longer
            if "429" in err_str:
                wait = 60 if attempt == 1 else 120
                logger.warning("[ranking] Rate limit 429 - waiting %ds...", wait)
                await asyncio.sleep(wait)
                continue

            if attempt == LLM_RETRIES:
                logger.error("[ranking] LLM failed after %d attempts: %s", LLM_RETRIES, exc)
                raise
            
            delay = LLM_RETRY_BASE_DELAY * (2 ** (attempt - 1))
            logger.warning("[ranking] Attempt %d/%d (%s) - retry %.1fs",
                           attempt, LLM_RETRIES, exc, delay)
            await asyncio.sleep(delay)
    return ""

def _extract_json(raw: str) -> Any:
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if match:
        raw = match.group(1)
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        brace = re.search(r"\[[\s\S]*\]|\{[\s\S]*\}", raw)
        if brace:
            try:
                return json.loads(brace.group())
            except json.JSONDecodeError:
                pass
    logger.warning("[ranking] JSON LLM invalide : %s", raw[:200])
    return None


# ───────────────────────────────────────────────────────────────────────────
# SCORING VECTORIEL
# ───────────────────────────────────────────────────────────────────────────

async def compute_similarity_scores(
    job_description: JobDescription,
    cv_texts: dict[str, str],
) -> dict[str, float]:
    jd_np = np.array(await embed_single_query(job_description.text), dtype=np.float32)
    scores: dict[str, float] = {}
    for cv_id, text in cv_texts.items():
        if not text.strip():
            scores[cv_id] = 0.0
            continue
        cv_np = np.array(await embed_single_query(text[:8000]), dtype=np.float32)
        norm  = np.linalg.norm(jd_np) * np.linalg.norm(cv_np)
        scores[cv_id] = float(np.dot(jd_np, cv_np) / norm) if norm > 0 else 0.0
    logger.info("[ranking] Scores vectoriels : %s",
                {k: round(v, 3) for k, v in scores.items()})
    return scores


# ───────────────────────────────────────────────────────────────────────────
# PROMPT BUILDER
# ───────────────────────────────────────────────────────────────────────────

def _build_ranking_prompt(
    job_description: JobDescription,
    cv_texts: dict[str, str],
    job_title: str = "",
    language: str = "fr",
) -> str:
    prompts   = get_localized_prompts(language)
    system    = prompts.get("system", "Tu es un expert RH charge d'evaluer des CVs.")
    title_str = f" : {job_title}" if job_title else ""

    cvs_block = "\n\n".join(
        f"=== CV ID: {cv_id} ===\n{text[:3000]}"
        for cv_id, text in cv_texts.items()
    )

    instructions = (
        "Evalue chaque CV par rapport a la fiche de poste.\n"
        "Pour chaque CV, retourne un objet JSON avec exactement ces champs :\n"
        "{\n"
        '  "cv_id": "<reprendre EXACTEMENT l identifiant CV ID indique ci-dessus>",\n'
        '  "relevance_score": <float entre 0.0 et 1.0>,\n'
        '  "similarity_score": <float entre 0.0 et 1.0>,\n'
        '  "explanation": {\n'
        '    "status": "selected" si relevance_score >= 0.6 sinon "rejected",\n'
        '    "candidate_info": {\n'
        '      "name": "<nom du candidat extrait du CV>",\n'
        '      "email": "<email ou N/A>",\n'
        '      "phone": "<telephone ou N/A>",\n'
        '      "path": "<filename>"\n'
        "    },\n"
        '    "explanation": "<synthese en 2-3 phrases des points forts/faibles>"\n'
        "  }\n"
        "}\n\n"
        "IMPORTANT : Retourne UNIQUEMENT un tableau JSON valide ([]), "
        "sans texte avant ni apres."
    )

    return (
        f"{system}\n\n"
        f"## Fiche de poste{title_str}\n"
        f"{job_description.text}\n\n"
        f"## CVs a evaluer\n"
        f"{cvs_block}\n\n"
        f"## Instructions\n"
        f"{instructions}"
    )


# ───────────────────────────────────────────────────────────────────────────
# BATCH
# ───────────────────────────────────────────────────────────────────────────

def _fallback_entry(cv_id: str, sim: float) -> dict:
    return {
        "cv_id"           : cv_id,
        "relevance_score" : round(sim, 4),
        "similarity_score": round(sim, 4),
        "explanation"     : {
            "status"        : "selected" if sim >= SELECTION_THRESHOLD else "rejected",
            "candidate_info": {"name": cv_id, "email": "N/A", "phone": "N/A", "path": ""},
            "explanation"   : "Evaluation automatique (fallback vectoriel).",
        },
    }


async def _rank_batch(
    job_description: JobDescription,
    batch_cv_texts: dict[str, str],
    job_title: str,
    language: str,
    similarity_scores: dict[str, float],
) -> list[dict]:
    prompt = _build_ranking_prompt(job_description, batch_cv_texts, job_title, language)
    logger.debug("[ranking] Prompt sent to LLM (%d chars)", len(prompt))

    raw    = await _call_llm(prompt)
    logger.debug("[ranking] LLM raw response: %s", raw[:300])

    parsed = _extract_json(raw)

    if not isinstance(parsed, list):
        logger.warning("[ranking] LLM response not a list -> fallback to vector scoring. Raw=%s", raw[:200])
        return [_fallback_entry(cid, similarity_scores.get(cid, 0.0)) for cid in batch_cv_texts]

    results: list[dict] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        cv_id       = str(item.get("cv_id", ""))
        relevance   = float(item.get("relevance_score", 0.0))
        similarity  = float(item.get("similarity_score", similarity_scores.get(cv_id, 0.0)))
        explanation = item.get("explanation", {})
        if isinstance(explanation, str):
            explanation = {"explanation": explanation}
        explanation.setdefault(
            "status", "selected" if relevance >= SELECTION_THRESHOLD else "rejected"
        )
        results.append({
            "cv_id"           : cv_id,
            "relevance_score" : round(relevance, 4),
            "similarity_score": round(similarity, 4),
            "explanation"     : explanation,
        })

    logger.info("[ranking] Batch resultats LLM : %s",
                [(r["cv_id"][:8], r["relevance_score"]) for r in results])
    return results


# ───────────────────────────────────────────────────────────────────────────
# POINT D'ENTREE — attendu par cv_service.py
# ───────────────────────────────────────────────────────────────────────────

async def compare_cvs_to_job(
    job_description: JobDescription,
    cv_ids: list[str],
    job_title: str = "",
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> tuple[list[dict], list[str]]:
    thinking_log: list[str] = []
    if not cv_ids:
        return [], thinking_log

    thinking_log.append(f"Recuperation de {len(cv_ids)} CV(s)...")
    raw_cvs = await fetch_selected_cvs(cv_ids)

    logger.info("[ranking] fetch_selected_cvs -> type=%s, len=%s",
                type(raw_cvs).__name__,
                len(raw_cvs) if hasattr(raw_cvs, "__len__") else "?")

    cv_texts: dict[str, str] = _normalize_cv_texts(raw_cvs)

    if not cv_texts:
        thinking_log.append("Aucun texte de CV recupere apres normalisation.")
        return [], thinking_log

    thinking_log.append(f"{len(cv_texts)} candidat(s) avec texte disponible.")

    language = detect_language(job_description.text)
    thinking_log.append(f"Langue detectee : {language}")

    thinking_log.append("Calcul des similarites vectorielles...")
    similarity_scores = await compute_similarity_scores(job_description, cv_texts)

    all_results: list[dict] = []
    ids_list      = list(cv_texts.keys())
    total_batches = (len(ids_list) + batch_size - 1) // batch_size

    for i in range(0, len(ids_list), batch_size):
        batch_ids   = ids_list[i: i + batch_size]
        batch_texts = {cid: cv_texts[cid] for cid in batch_ids}
        batch_num   = i // batch_size + 1
        thinking_log.append(
            f"Analyse LLM - batch {batch_num}/{total_batches} ({len(batch_ids)} CVs)..."
        )
        all_results.extend(
            await _rank_batch(
                job_description, batch_texts, job_title, language, similarity_scores
            )
        )

    all_results.sort(key=lambda x: x["relevance_score"], reverse=True)
    selected = [r for r in all_results if r["relevance_score"] >= SELECTION_THRESHOLD]

    msgs = get_localized_thinking_messages(language)
    thinking_log.append(msgs.get("done", f"{len(selected)} candidat(s) selectionne(s)."))

    logger.info("[ranking] %d/%d selectionnes (seuil=%.2f)",
                len(selected), len(all_results), SELECTION_THRESHOLD)
    return selected, thinking_log
