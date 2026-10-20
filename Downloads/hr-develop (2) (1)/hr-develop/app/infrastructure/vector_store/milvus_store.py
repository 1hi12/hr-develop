"""
MilvusVectorStore — implements IVectorStore.
Index: HNSW (replaces IVF_FLAT — 5× faster ANN search).
Schema: 768-dim embeddings (multilingual-e5-base).
Deduplication: candidate_exists(cv_hash) checked before any ingestion.
"""

from __future__ import annotations

import json
import logging

from pymilvus import (
    Collection, connections, utility,
    FieldSchema, CollectionSchema, DataType,
)

from app.config.settings import settings
from app.core.ports.vector_store import IVectorStore
from app.core.entities.candidate import EmbeddedChunk
from app.core.entities.matching import VectorSearchResult

logger = logging.getLogger(__name__)

OUTPUT_FIELDS = [
    "candidate_id", "text", "section", "filename",
    "skills_json", "chunk_index",
]


def _hit_field(entity, key: str, default=None):
    """
    entity.get(key, default) — but some pymilvus Hit implementations define
    get(self, key) with no default parameter, raising TypeError ("takes 2
    positional arguments but 3 were given") when called with one. Falls back
    to a plain lookup so this works across pymilvus versions.
    """
    try:
        return entity.get(key, default)
    except TypeError:
        try:
            value = entity.get(key)
        except TypeError:
            try:
                value = entity[key]
            except Exception:
                value = None
        return value if value is not None else default


class MilvusVectorStore(IVectorStore):

    def __init__(self) -> None:
        self._collection_name = settings.milvus_collection
        self._ensure_connected()
        self._ensure_collection()

    # ── IVectorStore ──────────────────────────────────────────────────────────

    async def store_candidate(
        self,
        candidate_id: str,
        filename: str,
        chunks: list[EmbeddedChunk],
        skills_json: str,
    ) -> None:
        col = self._get_collection()
        data = [
            [f"{candidate_id}_{c.chunk_index}" for c in chunks],
            [candidate_id] * len(chunks),
            [c.text[:65000] for c in chunks],
            [c.section[:490] for c in chunks],
            [filename[:490]] * len(chunks),
            [c.chunk_index for c in chunks],
            [skills_json[:65000]] * len(chunks),
            [c.embedding for c in chunks],
        ]
        col.insert(data)
        col.flush()
        logger.info("[MilvusStore] %d chunks stored for %s", len(chunks), candidate_id[:8])

    async def search(
        self,
        query_embedding: list[float],
        top_k: int,
        min_score: float,
    ) -> list[VectorSearchResult]:
        col = self._get_collection()
        results = col.search(
            data=[query_embedding],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"ef": 64}},
            limit=top_k,
            output_fields=["candidate_id", "text", "filename", "section", "chunk_index"],
        )

        best: dict[str, VectorSearchResult] = {}
        for hit in results[0]:
            score        = float(hit.score)
            candidate_id = _hit_field(hit.entity, "candidate_id", str(hit.id))

            if score < min_score:
                continue

            if candidate_id not in best or score > best[candidate_id].score:
                best[candidate_id] = VectorSearchResult(
                    candidate_id=candidate_id,
                    filename    =_hit_field(hit.entity, "filename", ""),
                    score       =round(score, 4),
                    excerpt     =(_hit_field(hit.entity, "text", "") or "")[:500],
                )

        return sorted(best.values(), key=lambda x: x.score, reverse=True)

    async def fetch_chunks_by_candidate_ids(
        self, candidate_ids: list[str]
    ) -> list[dict]:
        if not candidate_ids:
            return []
        # P3 fix: _ensure_connected() au lieu de _force_reconnect() — réutilise la connexion existante
        self._ensure_connected()
        col     = self._get_collection()
        ids_str = ", ".join(f'"{cid}"' for cid in candidate_ids)
        records = col.query(
            expr=f"candidate_id in [{ids_str}]",
            output_fields=OUTPUT_FIELDS,
        )
        return [
            {
                "candidate_id": r.get("candidate_id", ""),
                "text"        : r.get("text", ""),
                "section"     : r.get("section", ""),
                "filename"    : r.get("filename", ""),
                "skills_json" : r.get("skills_json", ""),
                "chunk_index" : r.get("chunk_index", 0),
            }
            for r in records
        ]

    async def delete_candidate(self, candidate_id: str) -> None:
        col = self._get_collection()
        col.delete(expr=f'candidate_id == "{candidate_id}"')
        col.flush()
        logger.info("[MilvusStore] Deleted candidate %s", candidate_id[:8])

    async def candidate_exists(self, candidate_id: str) -> bool:
        col = self._get_collection()
        results = col.query(
            expr=f'candidate_id == "{candidate_id}"',
            output_fields=["candidate_id"],
            limit=1,
        )
        return len(results) > 0

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _ensure_connected(self) -> None:
        # P3 fix: vérifier si déjà connecté avant de reconnecter
        try:
            if connections.get_connection_addr("default"):
                return
        except Exception:
            pass
        connections.connect(
            alias="default",
            host=settings.milvus_host,
            port=settings.milvus_port,
        )
        logger.info("[MilvusStore] Connected at %s:%s", settings.milvus_host, settings.milvus_port)

    def _force_reconnect(self) -> None:
        try:
            connections.disconnect("default")
        except Exception:
            pass
        connections.connect(
            alias="default",
            host=settings.milvus_host,
            port=settings.milvus_port,
        )

    def _ensure_collection(self) -> None:
        name = self._collection_name

        if utility.has_collection(name):
            col = Collection(name)
            fields = col.schema.fields
            emb_field = next((f for f in fields if f.name == "embedding"), None)
            current_dim = emb_field.params.get("dim") if emb_field else None

            if len(fields) != 8 or current_dim != settings.embedding_dim:
                logger.warning(
                    "[MilvusStore] Schema mismatch (fields=%d, dim=%s → expected dim=%d). Recreating…",
                    len(fields), current_dim, settings.embedding_dim,
                )
                utility.drop_collection(name)

        if not utility.has_collection(name):
            logger.info("[MilvusStore] Creating collection '%s' with HNSW index…", name)
            fields = [
                FieldSchema("chunk_id",     DataType.VARCHAR,      max_length=100, is_primary=True),
                FieldSchema("candidate_id", DataType.VARCHAR,      max_length=100),
                FieldSchema("text",         DataType.VARCHAR,      max_length=65535),
                FieldSchema("section",      DataType.VARCHAR,      max_length=500),
                FieldSchema("filename",     DataType.VARCHAR,      max_length=500),
                FieldSchema("chunk_index",  DataType.INT64),
                FieldSchema("skills_json",  DataType.VARCHAR,      max_length=65535),
                FieldSchema("embedding",    DataType.FLOAT_VECTOR, dim=settings.embedding_dim),
            ]
            col = Collection(
                name=name,
                schema=CollectionSchema(fields, description="Vectorised CV chunks"),
            )
            col.create_index(
                field_name="embedding",
                index_params={
                    "metric_type": "COSINE",
                    "index_type" : "HNSW",
                    "params"     : {"M": 16, "efConstruction": 200},
                },
            )
            logger.info("[MilvusStore] HNSW index created (M=16, efConstruction=200)")

    def _get_collection(self) -> Collection:
        self._ensure_connected()
        if not utility.has_collection(self._collection_name):
            raise RuntimeError(f"Milvus collection '{self._collection_name}' not found.")
        col = Collection(self._collection_name)
        col.load()
        return col
