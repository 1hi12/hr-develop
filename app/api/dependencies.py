"""
dependencies.py
===============
Single wiring point: binds every port interface to its concrete
infrastructure implementation.

Rules:
  - Only this file knows which concrete class implements which port.
  - @lru_cache singletons (embedder, vector_store, ranker) are created
    exactly once per process lifetime.
  - Route handlers receive use-case instances via FastAPI Depends().
"""

from functools import lru_cache

from app.infrastructure.parsers.document_parser import DocumentParser
from app.infrastructure.embeddings.openai_embedder import OpenAIEmbedder
from app.infrastructure.llm.multi_worker_single_adapter import MultiWorkerSingleAdapter
from app.infrastructure.llm.multi_worker_ranker import MultiWorkerRanker
from app.infrastructure.vector_store.milvus_store import MilvusVectorStore
from app.infrastructure.repositories.candidate_repo import CandidateRepository
from app.core.ports.embedder import IEmbedder

from app.application.use_cases.ingest_cv import IngestCVUseCase
from app.application.use_cases.match_candidates import MatchCandidatesUseCase


# ── Singletons ───────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_embedder() -> OpenAIEmbedder:
    return OpenAIEmbedder()


@lru_cache(maxsize=1)
def get_vector_store() -> MilvusVectorStore:
    return MilvusVectorStore()


@lru_cache(maxsize=1)
def get_extractor() -> MultiWorkerSingleAdapter:
    return MultiWorkerSingleAdapter()


@lru_cache(maxsize=1)
def get_ranker() -> MultiWorkerRanker:
    return MultiWorkerRanker(
        vector_store=get_vector_store(),
        embedder=get_embedder(),
    )


# ── Use case factories ───────────────────────────────────────────────────────

def get_ingest_use_case() -> IngestCVUseCase:
    return IngestCVUseCase(
        parser=DocumentParser(),
        extractor=get_extractor(),
        embedder=get_embedder(),
        vector_store=get_vector_store(),
        candidate_repo=CandidateRepository(),
    )


def get_match_use_case() -> MatchCandidatesUseCase:
    return MatchCandidatesUseCase(
        embedder=get_embedder(),
        vector_store=get_vector_store(),
        ranker=get_ranker(),
    )


# ── Mock Authentication (AI Assistant — VITE_AUTH_MODE=mock) ─────────────────

async def get_current_user() -> dict:
    """
    Mock user pour développement sans SSO.
    Retourne toujours l'utilisateur Rana Atouani (id=1).

    TODO: Remplacer par vraie authentification SSO quand accès disponibles.
    """
    return {
        "id": 1,
        "email": "rana.atouani@sofrecom.com",
        "full_name": "Rana Atouani",
        "role": "recruiter"
    }
