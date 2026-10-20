# app/workers/cv_processing_worker.py

import logging
import os
import uuid
import json
import asyncio
from typing import Optional

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Milvus configuration from environment variables
MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT = int(os.getenv("MILVUS_PORT", "19530"))


async def process_cv_task(
    file_bytes: bytes,
    filename: str,
    candidate_id: str,
    job_id: Optional[str] = None,
    websocket_client_id: Optional[str] = None,
) -> dict:
    from app.agent.tools.cv_extractor.parser import parse_file
    from app.agent.tools.cv_extractor.llm_extractor import extract_info_gemini
    from app.agent.tools.cv_extractor.chunker import chunk_document, LoadedDocument
    from app.agent.tools.cv_extractor.embedder import embed_texts

    # ── Phase 2 : Parsing ────────────────────────────
    raw_text = parse_file(file_bytes, filename)
    if not raw_text or len(raw_text.strip()) < 50:
        raise ValueError("Fichier vide ou texte trop court")
    logger.info(f"[Worker] Phase 2 — {len(raw_text)} caractères extraits")

    # ── Phase 3 : Extraction LLM ─────────────────────
    cv_info, cv_skills_data, cv_seniority = await extract_info_gemini(raw_text)
    cv_skills = cv_skills_data.get("skills", [])
    logger.info(f"[Worker] Phase 3 — {len(cv_skills)} compétences extraites")

    # ── Phase 4 : Chunking sémantique ────────────────
    doc = LoadedDocument(filename=filename, raw_text=raw_text)
    chunks = chunk_document(doc)
    logger.info(f"[Worker] Phase 4 — {len(chunks)} chunks créés")

    # ── Phase 5 : Embedding ───────────────────────────
    texts = [c.text for c in chunks]
    vectors = await embed_texts(texts)

    # ── Phase 6 : Stockage Milvus ─────────────────────
    await _store_in_milvus(
        chunks=chunks,
        vectors=vectors,
        candidate_id=candidate_id,
        filename=filename,
        skills=cv_skills,
    )

    return {
        "candidate_id": candidate_id,
        "filename":     filename,
        "job_id":       job_id,
        "cv_id":        str(uuid.uuid4()),
        "chunks_count": len(chunks),
        "skills_count": len(cv_skills),
        "skills":       cv_skills,
        "full_name":    cv_info.get("full_name", ""),
        "email":        cv_info.get("email", ""),
        "seniority":    cv_seniority.get("seniority_level", ""),
        "years_exp":    cv_seniority.get("total_years_experience", 0),
        "status":       "success",
    }


# ──────────────────────────────────────────────────────────
# Stockage Milvus
# ──────────────────────────────────────────────────────────

async def _store_in_milvus(
    chunks: list,
    vectors: list,
    candidate_id: str,
    filename: str,
    skills: list,
) -> None:
    try:
        from pymilvus import (
            Collection, connections, utility,
            FieldSchema, CollectionSchema, DataType
        )

        # 1. Connexion
        connections.connect(host=MILVUS_HOST, port=MILVUS_PORT)
        collection_name = "cv_chunks"

        # 2. Vérification du schéma — on veut 8 champs désormais
        if utility.has_collection(collection_name):
            col_check = Collection(collection_name)
            if len(col_check.schema.fields) != 8:
                logger.warning(
                    f"[Worker] Schéma incorrect ({len(col_check.schema.fields)} champs). "
                    "Suppression et recréation..."
                )
                utility.drop_collection(collection_name)

        # 3. Création si inexistante
        if not utility.has_collection(collection_name):
            logger.info(f"[Worker] Création de la collection '{collection_name}' avec 8 champs...")
            fields = [
                FieldSchema(name="chunk_id",     dtype=DataType.VARCHAR, max_length=100, is_primary=True),
                FieldSchema(name="candidate_id", dtype=DataType.VARCHAR, max_length=100),  # ← ajouté
                FieldSchema(name="text",         dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="section",      dtype=DataType.VARCHAR, max_length=500),
                FieldSchema(name="filename",     dtype=DataType.VARCHAR, max_length=500),
                FieldSchema(name="chunk_index",  dtype=DataType.INT64),
                FieldSchema(name="skills_json",  dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="embedding",    dtype=DataType.FLOAT_VECTOR, dim=settings.embedding_dim),
            ]
            schema = CollectionSchema(fields, description="Chunks de CV vectorisés")
            col = Collection(name=collection_name, schema=schema)

            index_params = {
                "metric_type": "COSINE",
                "index_type":  "IVF_FLAT",
                "params":      {"nlist": 128},
            }
            col.create_index(field_name="embedding", index_params=index_params)
        else:
            col = Collection(collection_name)

        # 4. Charger la collection
        col.load()

        # 5. Préparation des données — ordre STRICT : 8 listes
        skills_str = json.dumps([
            s if isinstance(s, str) else s.get("name", "")
            for s in skills
        ])

        data = [
            [f"{candidate_id}_{c.chunk_index}" for c in chunks],  # 1. chunk_id
            [candidate_id] * len(chunks),                         # 2. candidate_id
            [c.text[:65000] for c in chunks],                     # 3. text
            [c.section[:490] for c in chunks],                    # 4. section
            [filename[:490]] * len(chunks),                       # 5. filename
            [c.chunk_index for c in chunks],                      # 6. chunk_index
            [skills_str[:65000]] * len(chunks),                   # 7. skills_json
            vectors,                                              # 8. embedding
        ]

        # 6. Insertion
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, col.insert, data)
        await loop.run_in_executor(None, col.flush)

        logger.info(f"[Worker] ✅ Milvus — {len(chunks)} chunks insérés (8 champs).")

    except Exception as e:
        logger.error(f"[Worker] ❌ Erreur fatale Milvus : {str(e)}")
        raise
