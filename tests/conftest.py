"""
conftest.py — Configuration globale des tests
==============================================
PROTECTION BASE DE DONNÉES :
  - Tests unitaires  : mocks uniquement, aucune DB touchée
  - Tests intégration: base isolée cv_db_test OBLIGATOIRE
  - Jamais sur cv_db (base réelle)
"""

import os
import pytest
import asyncpg
import asyncio
from unittest.mock import AsyncMock, patch

# ── Constante : URL de base API pour les tests d'intégration ─────────────────
API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

# ── Constante : DB test isolée ────────────────────────────────────────────────
TEST_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/cv_db_test"
)

# ── GARDE DE SÉCURITÉ : empêcher les tests sur la base réelle ─────────────────
_FORBIDDEN_DBS = ["cv_db", "cv_db_prod"]

def _check_db_safety():
    """Bloque l'exécution si la DATABASE_URL pointe vers la base réelle."""
    db_url = os.environ.get("DATABASE_URL", "")
    for forbidden in _FORBIDDEN_DBS:
        if db_url.endswith(f"/{forbidden}") or f"/{forbidden}?" in db_url:
            pytest.exit(
                f"\n🚨 DANGER : DATABASE_URL pointe vers '{forbidden}' (base réelle).\n"
                f"   Utilisez cv_db_test pour les tests d'intégration.\n"
                f"   Exemple : DATABASE_URL=postgresql://postgres:postgres@localhost:5432/cv_db_test pytest\n",
                returncode=1,
            )


# ── Fixtures tests UNITAIRES (mocks, aucune DB) ───────────────────────────────

@pytest.fixture
def client():
    """Client de test avec toutes les dépendances mockées — aucune DB réelle."""
    with patch("app.infrastructure.database.session.AsyncSessionLocal"), \
         patch("pymilvus.connections.connect"), \
         patch("app.infrastructure.database.pg_notify.CVProcessingListener"):
        from main import app
        from fastapi.testclient import TestClient
        return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def mock_session():
    """Session SQLAlchemy mockée pour les tests unitaires."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


# ── Fixture : client HTTP pour tests d'intégration ───────────────────────────

@pytest.fixture(scope="session")
def api_client():
    """Client HTTP pointant vers le serveur de test (API_BASE_URL)."""
    import httpx
    with httpx.Client(base_url=API_BASE_URL, timeout=30) as c:
        yield c


# ── Fixture : nettoyage automatique des offres d'emploi créées ───────────────

@pytest.fixture
def cleanup_postings(api_client):
    """
    Collecte les job_id créés pendant un test et les supprime après.
    Usage :
        def test_create(api_client, cleanup_postings):
            r = api_client.post("/api/v1/postings", json={...})
            cleanup_postings.track(r.json()["job_id"])
    """
    created_ids = []

    class Tracker:
        def track(self, job_id: str):
            if job_id:
                created_ids.append(job_id)

    tracker = Tracker()
    yield tracker

    # Nettoyage automatique après le test
    for job_id in created_ids:
        try:
            api_client.delete(f"/api/v1/postings/{job_id}")
        except Exception:
            pass


# ── Fixture : nettoyage global en fin de session ─────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def cleanup_all_test_data(api_client):
    """Supprime TOUTES les données de test restantes après la session complète."""
    yield

    # Supprimer directement via DB si des données "Test..." restent
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/cv_db_test"
    )
    # Uniquement sur bases de test autorisées
    if any(safe in db_url for safe in ["cv_db_test", "cv_db_uat"]):
        try:
            async def _cleanup():
                # Convertir asyncpg URL (retirer +asyncpg si présent)
                pg_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
                conn = await asyncpg.connect(pg_url)
                deleted = await conn.execute("DELETE FROM job_postings WHERE title LIKE 'Test%'")
                if deleted != "DELETE 0":
                    print(f"\n[conftest] Nettoyage final : {deleted} enregistrement(s) supprimé(s)")
                await conn.close()
            asyncio.get_event_loop().run_until_complete(_cleanup())
        except Exception as e:
            print(f"\n[conftest] Nettoyage final échoué (non-bloquant): {e}")
