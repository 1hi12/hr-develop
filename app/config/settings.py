import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Milvus ────────────────────────────────────────────────
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_collection: str = "cv_chunks"
    retrieval_top_k: int = 50

    # ── Orange LiteLLM Proxy (sole LLM + embedding access point) ──────────
    litellm_api_key: str = ""
    litellm_base_url: str = "https://management.llmproxy.ai.orange"
    litellm_model: str = "openai/gpt-4o-mini"  # Model for extraction & ranking

    # ── LLM concurrency & retry ───────────────────────────────
    llm_max_concurrency: int = 5
    llm_retries: int = 3
    llm_retry_base_delay: float = 3.0

    # ── Multi-worker pipeline ─────────────────────────────────
    pipeline_batch_size: int = 10
    pipeline_num_workers: int = 5
    pipeline_max_retries: int = 3
    pipeline_rate_limit_wait: int = 60

    # ── Embeddings (via Orange LiteLLM proxy) ─────────────────
    embedding_model: str = "openai/text-embedding-3-small"
    embedding_batch_size: int = 32
    embedding_dim: int = 1536

    # ── Chunking ──────────────────────────────────────────────
    semantic_chunk_size: int = 450
    similarity_threshold: float = 0.78
    fallback_chunk_size: int = 600
    fallback_chunk_overlap: int = 100

    # ── Matching / Ranking ────────────────────────────────────
    selection_threshold: float = 0.35
    min_score_default: float = 0.3
    reranking_batch_size: int = 5

    # ── Database ──────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/cv_db"

    # ── Redis / ARQ ───────────────────────────────────────────
    redis_url: str = "redis://localhost:6379"

    # ── CORS ──────────────────────────────────────────────────
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",  # Vite dev server
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",  # Vite dev server
        "http://127.0.0.1:8080",
    ]

    # ── Azure AD Authentication ───────────────────────────────
    azure_tenant_id: str = "90c7a20a-f34b-40bf-bc48-b9253b6f5d20"
    azure_client_id: str = "f3b0c575-99b4-496d-8aa3-d925fa1d6d87"

    # ── LLM cost limits ───────────────────────────────────────
    # Aligned to the Orange proxy's OWN account quota, not an arbitrary
    # internal ceiling: its 429 error body reports "Limit type: tokens.
    # Current limit: 10000" for its rolling window. 500_000 never tripped in
    # practice because it was 50x looser than the real constraint — cost_guard
    # was recording usage but never actually protecting against the thing
    # that was causing 429s. Set just below 10k so our own pre-flight check
    # (is_budget_available) fires before Orange's, not after.
    llm_max_tokens_per_hour: int = 9_000
    # No confirmed daily cap has been observed from Orange — this is an
    # estimate (24h x hourly limit, with margin), not a verified figure.
    llm_max_tokens_per_day:  int = 180_000

    # ── SMTP Email ────────────────────────────────────────────
    smtp_host:       str  = ""
    smtp_port:       int  = 587
    smtp_use_tls:    bool = True
    smtp_user:       str  = ""
    smtp_password:   str  = ""
    smtp_from_email: str  = ""

    @property
    def database_url_asyncpg(self) -> str:
        """
        Raw asyncpg DSN (no SQLAlchemy dialect prefix).
        Used by the pg_notify listener which connects via asyncpg directly.
        """
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


@lru_cache
def get_settings() -> Settings:
    """
    Returns a cached Settings singleton.
    Fails fast at startup if any required env var is missing or invalid.
    """
    return Settings()


# Module-level singleton — import this everywhere instead of os.getenv()
settings = get_settings()


