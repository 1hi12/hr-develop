"""
Retrieval Service
=================
Fetches CVs from Milvus vector database.
"""
from __future__ import annotations

import logging
import os

from pymilvus import Collection, connections, utility

from app.data.schemas.cv import JobDescription
from app.agent.tools.cv_extractor.embedder import embed_single_query

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration Milvus
# ---------------------------------------------------------------------------

MILVUS_HOST: str = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT = int(os.getenv("MILVUS_PORT", "19530"))
COLLECTION_NAME: str = os.getenv("MILVUS_COLLECTION", "cv_chunks")
TOP_K: int = int(os.getenv("RETRIEVAL_TOP_K", "50"))
OUTPUT_FIELDS: list[str] = ["candidate_id", "text", "section", "filename", "skills_json", "embedding"]


# ---------------------------------------------------------------------------
# Connexion Milvus — singleton sécurisé
# ---------------------------------------------------------------------------

def _ensure_connected() -> None:
    try:
        existing = connections.get_connection_addr("default")
        if existing:
            logger.debug("Milvus déjà connecté : %s", existing)
            return
    except Exception:
        pass

    try:
        connections.connect(
            alias="default",
            host=MILVUS_HOST,
            port=MILVUS_PORT,
        )
        logger.info("✅ Milvus connecté à %s:%s", MILVUS_HOST, MILVUS_PORT)
    except Exception as exc:
        logger.error("❌ Connexion Milvus échouée : %s", exc)
        raise


def _force_reconnect() -> None:
    """Force une nouvelle connexion Milvus (utilisé pour le reranking)."""
    try:
        connections.disconnect("default")
    except Exception:
        pass

    connections.connect(
        alias="default",
        host=MILVUS_HOST,
        port=MILVUS_PORT,
    )
    logger.info("✅ Milvus reconnecté à %s:%s", MILVUS_HOST, MILVUS_PORT)


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------

async def get_best_cvs(job_description: JobDescription) -> list[dict]:
    """
    Embed la description du poste puis lance une recherche vectorielle dans Milvus.
    """
    logger.info("Recherche des %d meilleurs CVs", TOP_K)

    job_embedding: list[float] = await embed_single_query(job_description.text)

    _ensure_connected()
    collection = Collection(COLLECTION_NAME)
    collection.load()

    search_params = {"metric_type": "COSINE", "params": {"nprobe": 16}}

    results = collection.search(
        data=[job_embedding],
        anns_field="embedding",
        param=search_params,
        limit=TOP_K,
        output_fields=OUTPUT_FIELDS,
    )

    hits = results[0] if results else []
    cvs: list[dict] = []

    for hit in hits:
        entity = hit.entity
        cvs.append(
            {
                "candidate_id": entity.get("candidate_id", hit.id),
                "score": hit.score,
                "text": entity.get("text", ""),
                "section": entity.get("section", ""),
                "filename": entity.get("filename", ""),
                "skills_json": entity.get("skills_json", ""),
                "embedding": entity.get("embedding", []),
            }
        )

    logger.info("%d CVs récupérés depuis Milvus", len(cvs))
    return cvs


async def vector_search_by_embedding(
    query_embedding: list[float],
    top_k: int = 50
) -> list[dict]:
    """
    Recherche vectorielle directe dans Milvus avec un embedding fourni.
    Utilisé par le project team recommender.
    """
    logger.info(f"Recherche vectorielle de {top_k} meilleurs candidats")

    _ensure_connected()
    collection = Collection(COLLECTION_NAME)

    # Charger la collection si elle contient des données
    if collection.num_entities > 0:
        try:
            collection.load(_async=False, _refresh=True, _timeout=10)
            logger.info(f"Collection '{COLLECTION_NAME}' chargée ({collection.num_entities} entités)")
        except Exception as e:
            logger.warning(f"Chargement échoué (peut-être déjà chargée): {e}")
    else:
        logger.info(f"Collection '{COLLECTION_NAME}' vide, pas de recherche possible")
        return []

    search_params = {"metric_type": "COSINE", "params": {"nprobe": 16}}

    logger.info("Lancement de la recherche vectorielle...")
    results = collection.search(
        data=[query_embedding],
        anns_field="embedding",
        param=search_params,
        limit=top_k,
        output_fields=OUTPUT_FIELDS,
    )

    hits = results[0] if results else []
    chunks: list[dict] = []

    for hit in hits:
        entity = hit.entity
        chunks.append(
            {
                "candidate_id": entity.get("candidate_id", hit.id),
                "score": hit.score,
                "distance": 1.0 - hit.score,  # Pour compatibilité
                "text": entity.get("text", ""),
                "section": entity.get("section", ""),
                "filename": entity.get("filename", ""),
                "skills_json": entity.get("skills_json", ""),
                "embedding": entity.get("embedding", []),
            }
        )

    logger.info(f"✅ {len(chunks)} chunks récupérés depuis Milvus")
    return chunks


async def fetch_selected_cvs(candidate_ids: list[str]) -> list[dict]:
    """
    Récupère les CVs complets par leurs IDs depuis Milvus.
    """
    if not candidate_ids:
        return []

    logger.info("Récupération de %d CVs par ID", len(candidate_ids))

    _force_reconnect()

    if not utility.has_collection(COLLECTION_NAME):
        logger.error("❌ Collection '%s' introuvable !", COLLECTION_NAME)
        raise ValueError(f"Collection '{COLLECTION_NAME}' not found")

    collection = Collection(COLLECTION_NAME)
    collection.load()

    ids_expr = ", ".join(f'"{cid}"' for cid in candidate_ids)
    expr = f"candidate_id in [{ids_expr}]"

    results = collection.query(
        expr=expr,
        output_fields=OUTPUT_FIELDS,
    )

    cvs: list[dict] = []
    for record in results:
        cvs.append(
            {
                "candidate_id": record.get("candidate_id", ""),
                "text": record.get("text", ""),
                "section": record.get("section", ""),
                "filename": record.get("filename", ""),
                "skills_json": record.get("skills_json", ""),
                "embedding": record.get("embedding", []),
            }
        )

    logger.info("%d CVs récupérés", len(cvs))
    return cvs
