
"""
cv_service.py
=============
FIX : jointure candidate_id correcte entre résultats Milvus et résultats LLM.
FIX2 : fallback vectoriel copie score → relevance_score pour éviter score 0%
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import List, Optional

from fastapi import UploadFile
from pymilvus import Collection, connections, utility

from app.agent.tools.cv_extractor.embedder import embed_single_query
from app.data.schemas.cv import JobDescription
from app.services.ranking_service import compare_cvs_to_job
from app.workers.cv_processing_worker import process_cv_task

logger = logging.getLogger(__name__)

COLLECTION_NAME    = "cv_chunks"
MILVUS_HOST        = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT        = int(os.getenv("MILVUS_PORT", "19530"))
TOP_K_DEFAULT      = 50
SELECTION_THRESHOLD = 0.35   # ✅ FIX : abaissé de 0.6 → 0.35


# ───────────────────────────────────────────────────────────────────────────
# HELPERS MILVUS
# ───────────────────────────────────────────────────────────────────────────

def _ensure_connection() -> None:
    try:
        existing = connections.get_connection_addr("default")
        if existing:
            return
    except Exception:
        pass
    connections.connect(alias="default", host=MILVUS_HOST, port=MILVUS_PORT)
    logger.info("✅ Milvus connecté à %s:%s", MILVUS_HOST, MILVUS_PORT)


def _get_collection() -> Collection:
    _ensure_connection()
    if not utility.has_collection(COLLECTION_NAME):
        raise RuntimeError(
            f"Collection Milvus '{COLLECTION_NAME}' introuvable. "
            "Le worker d'ingestion a-t-il tourné ?"
        )
    col = Collection(COLLECTION_NAME)
    col.load()
    return col


# ───────────────────────────────────────────────────────────────────────────
# HELPER FALLBACK
# ───────────────────────────────────────────────────────────────────────────

def _build_fallback(search_results: List[dict], top_k: int) -> List[dict]:
    """
    ✅ FIX : copie score → relevance_score et similarity_score
    pour que generate_response affiche les vrais scores au lieu de 0%.
    """
    fallback = []
    for c in search_results[:top_k]:
        c_copy = dict(c)
        vec_score = c.get("score", 0.0)
        c_copy["relevance_score"]  = vec_score
        c_copy["similarity_score"] = vec_score
        c_copy["explanation"] = {
            "status": "selected" if vec_score >= SELECTION_THRESHOLD else "rejected",
            "candidate_info": {
                "name" : c.get("filename", c.get("candidate_id", "")),
                "email": "N/A",
                "phone": "N/A",
                "path" : c.get("filename", ""),
            },
            "explanation": "Évaluation automatique (fallback vectoriel).",
        }
        fallback.append(c_copy)
    return fallback


# ───────────────────────────────────────────────────────────────────────────
# PHASE 1→6 : INGESTION
# ───────────────────────────────────────────────────────────────────────────

async def upload_and_process_cv(
    file: UploadFile,
    job_id: Optional[str] = None,
    candidate_id: Optional[str] = None,
    websocket_client_id: Optional[str] = None,
) -> dict:
    filename     = file.filename or "unknown"
    file_bytes   = await file.read()
    candidate_id = candidate_id or str(uuid.uuid4())

    return await process_cv_task(
        file_bytes=file_bytes,
        filename=filename,
        candidate_id=candidate_id,
        job_id=job_id,
        websocket_client_id=websocket_client_id,
    )


# ───────────────────────────────────────────────────────────────────────────
# PHASE 7 : RECHERCHE VECTORIELLE
# ───────────────────────────────────────────────────────────────────────────

async def search_candidates(
    job_description: str,
    required_skills: List[str],
    top_k: int = TOP_K_DEFAULT,
    min_score: float = 0.3,   # ✅ FIX : abaissé de 0.5 → 0.3
) -> List[dict]:
    """
    Recherche vectorielle dans Milvus.
    Retourne le meilleur chunk par candidate_id avec son score cosinus.
    """
    query_text = job_description
    if required_skills:
        query_text += "\nCompétences requises : " + ", ".join(required_skills)

    query_vector: list[float] = await embed_single_query(query_text)

    try:
        collection = _get_collection()
        results = collection.search(
            data=[query_vector],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"nprobe": 16}},
            limit=top_k,
            output_fields=["candidate_id", "text", "filename", "section", "chunk_index"],
        )
    except Exception as e:
        logger.exception("[cv_service] Erreur recherche Milvus : %s", e)
        raise

    # Garde le meilleur chunk par candidate_id
    best: dict[str, dict] = {}
    for hit in results[0]:
        score        = float(hit.score)
        candidate_id = hit.entity.get("candidate_id", str(hit.id))

        if score < min_score:
            continue

        if candidate_id not in best or score > best[candidate_id]["score"]:
            best[candidate_id] = {
                "candidate_id": candidate_id,
                "filename"    : hit.entity.get("filename", ""),
                "job_id"      : "",
                "score"       : round(score, 4),
                "excerpt"     : (hit.entity.get("text") or "")[:500],
            }

    sorted_candidates = sorted(best.values(), key=lambda x: x["score"], reverse=True)
    logger.info(
        "[cv_service] Recherche Milvus → %d candidats uniques (top_k=%d, min_score=%.2f)",
        len(sorted_candidates), top_k, min_score,
    )
    return sorted_candidates


# ───────────────────────────────────────────────────────────────────────────
# PHASE 8 : RERANKING LLM
# ───────────────────────────────────────────────────────────────────────────

async def rerank_candidates(
    search_results: List[dict],
    job_description: str,
    required_skills: List[str],
    top_k: int = 5,
) -> List[dict]:
    """
    Reranking LLM des candidats issus de la recherche vectorielle.
    La jointure se fait sur candidate_id.
    """
    if not search_results:
        return []

    jd     = JobDescription(text=job_description)
    cv_ids = [c["candidate_id"] for c in search_results]

    logger.info("[cv_service] Reranking LLM pour %d candidats : %s",
                len(cv_ids), [cid[:8] for cid in cv_ids])

    try:
        selected_candidates, thinking_log = await compare_cvs_to_job(
            job_description=jd,
            cv_ids=cv_ids,
            job_title="",
        )
        for msg in thinking_log:
            logger.info("[ranking_log] %s", msg)

    except Exception as e:
        logger.exception("[cv_service] Erreur reranking LLM : %s", e)
        logger.warning("[cv_service] Fallback : ordre vectoriel conservé")
        return _build_fallback(search_results, top_k)   # ✅ FIX

    if not selected_candidates:
        logger.info("[cv_service] Aucun candidat retenu après reranking → fallback vectoriel")
        return _build_fallback(search_results, top_k)   # ✅ FIX

    # Jointure sur candidate_id
    meta_by_id: dict[str, dict] = {c["candidate_id"]: c for c in search_results}
    ranked: List[dict] = []

    for item in selected_candidates[:top_k]:
        cid         = str(item.get("cv_id", ""))
        meta        = meta_by_id.get(cid, {})
        explanation = item.get("explanation", {})

        if isinstance(explanation, str):
            explanation = {"explanation": explanation, "status": "selected"}

        # Si le LLM n'a pas retourné le bon cv_id, on essaie un match partiel
        if not meta:
            for known_id in meta_by_id:
                if cid in known_id or known_id in cid:
                    meta = meta_by_id[known_id]
                    logger.warning(
                        "[cv_service] Match partiel cv_id : LLM='%s' → Milvus='%s'",
                        cid, known_id,
                    )
                    break

        ranked.append({
            "candidate_id"    : cid,
            "filename"        : meta.get("filename", explanation.get("candidate_info", {}).get("path", "")),
            "job_id"          : meta.get("job_id", ""),
            "score"           : meta.get("score", 0.0),
            "relevance_score" : item.get("relevance_score", 0.0),
            "similarity_score": item.get("similarity_score", 0.0),
            "excerpt"         : meta.get("excerpt", ""),
            "explanation"     : explanation,
        })

    logger.info("[cv_service] Reranking OK → %d candidats retenus, scores=%s",
                len(ranked),
                [(r["candidate_id"][:8], r["relevance_score"]) for r in ranked])
    return ranked


# ───────────────────────────────────────────────────────────────────────────
# PHASE 9 : RÉPONSE FINALE
# ───────────────────────────────────────────────────────────────────────────

async def generate_response(
    ranked_results: List[dict],
    job_description: str,
    required_skills: List[str],
) -> dict:
    if not ranked_results:
        return {"candidates": [], "recruiter_advice": "Aucun candidat à analyser."}

    skills_str = ", ".join(required_skills) if required_skills else "non spécifiées"
    formatted_candidates: List[dict] = []

    for rank, candidate in enumerate(ranked_results, start=1):
        explanation = candidate.get("explanation", {})
        if isinstance(explanation, str):
            explanation = {"explanation": explanation, "status": "selected"}

        candidate_info = explanation.get("candidate_info") or {
            "name" : candidate.get("filename", candidate["candidate_id"]),
            "email": "N/A",
            "phone": "N/A",
            "path" : candidate.get("filename", ""),
        }

        formatted_candidates.append({
            "rank"            : rank,
            "candidate_id"    : candidate["candidate_id"],
            "filename"        : candidate.get("filename", ""),
            "score"           : candidate.get("score", 0.0),
            "relevance_score" : candidate.get("relevance_score", 0.0),
            "similarity_score": candidate.get("similarity_score", 0.0),
            "status"          : explanation.get("status", "selected"),
            "candidate_info"  : candidate_info,
            "presentation"    : explanation.get("explanation", "Analyse indisponible."),
            "excerpt"         : candidate.get("excerpt", ""),
        })

    # ✅ FIX : seuil abaissé de 0.6 → SELECTION_THRESHOLD (0.35)
    n_selected = sum(1 for c in formatted_candidates if c.get("relevance_score", 0) >= SELECTION_THRESHOLD)
    avg_score  = (
        sum(c.get("relevance_score", 0) for c in formatted_candidates) / len(formatted_candidates)
        if formatted_candidates else 0.0
    )

    recruiter_advice = (
        f"{n_selected} candidat(s) sur {len(formatted_candidates)} dépassent le seuil "
        f"de pertinence (score moyen : {avg_score:.0%}). "
        f"Compétences recherchées : {skills_str}. "
        "Consultez les fiches individuelles pour le détail des adéquations."
    )

    logger.info(
        "[cv_service] Réponse finale : %d candidats, %d retenus, score moyen %.2f",
        len(formatted_candidates), n_selected, avg_score,
    )
    return {
        "candidates"      : formatted_candidates,
        "recruiter_advice": recruiter_advice,
    }


# ───────────────────────────────────────────────────────────────────────────
# UTILITAIRE : STATUT
# ───────────────────────────────────────────────────────────────────────────

async def get_cv_status(candidate_id: str) -> dict:
    try:
        collection = _get_collection()
        results = collection.query(
            expr=f'candidate_id == "{candidate_id}"',
            output_fields=["candidate_id", "filename"],
            limit=1,
        )
        if results:
            return {
                "candidate_id": candidate_id,
                "status"      : "indexed",
                "filename"    : results[0].get("filename", ""),
            }
        return {"candidate_id": candidate_id, "status": "not_found"}
    except Exception as e:
        logger.exception("[cv_service] Erreur status : %s", e)
        return {"candidate_id": candidate_id, "status": "error", "detail": str(e)}
