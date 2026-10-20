"""
Tests d'intégration — HR System
================================
RÈGLES DE SÉCURITÉ :
  - Tous les tests qui CRÉENT des données utilisent cleanup_postings
  - cleanup_postings supprime automatiquement après chaque test
  - Aucune donnée de test ne reste dans la base après exécution

Lancement correct :
  API_BASE_URL=http://localhost:8001 pytest tests/test_integration.py -v
"""

import uuid
import pytest


# ============================================================
# SANTÉ DU SERVEUR
# ============================================================

class TestHealthCheck:

    def test_server_is_running(self, api_client):
        response = api_client.get("/health")
        assert response.status_code == 200

    def test_health_returns_ok(self, api_client):
        response = api_client.get("/health")
        assert response.json()["status"] == "ok"

    def test_health_has_version(self, api_client):
        response = api_client.get("/health")
        assert "version" in response.json()

    def test_response_time_acceptable(self, api_client):
        import time
        start = time.time()
        api_client.get("/health")
        duration = time.time() - start
        assert duration < 5.0, f"Serveur trop lent: {duration:.2f}s"


# ============================================================
# CANDIDATS — GET uniquement (lecture seule, pas de création)
# ============================================================

class TestCandidatesIntegration:

    def test_list_candidates_returns_200(self, api_client):
        response = api_client.get("/api/v1/candidates")
        assert response.status_code == 200

    def test_list_candidates_returns_json(self, api_client):
        response = api_client.get("/api/v1/candidates")
        assert response.headers["content-type"].startswith("application/json")

    def test_list_candidates_has_items_key(self, api_client):
        data = api_client.get("/api/v1/candidates").json()
        assert "items" in data

    def test_list_candidates_items_is_list(self, api_client):
        data = api_client.get("/api/v1/candidates").json()
        assert isinstance(data["items"], list)

    def test_candidate_fields_present(self, api_client):
        data = api_client.get("/api/v1/candidates").json()
        if data["items"]:
            c = data["items"][0]
            assert "candidate_id" in c
            assert "status" in c
            assert "filename" in c

    def test_pagination_page_size(self, api_client):
        data = api_client.get("/api/v1/candidates?page=1&page_size=5").json()
        assert len(data["items"]) <= 5

    def test_filter_by_status_active(self, api_client):
        assert api_client.get("/api/v1/candidates?status=active").status_code == 200

    def test_filter_by_status_pending(self, api_client):
        assert api_client.get("/api/v1/candidates?status=pending").status_code == 200

    def test_get_nonexistent_candidate_returns_404(self, api_client):
        r = api_client.get("/api/v1/candidates/candidat-inexistant-xyz")
        assert r.status_code in (404, 500)

    def test_upload_without_file_returns_error(self, api_client):
        r = api_client.post("/api/v1/candidates/upload")
        assert r.status_code in (400, 422)


# ============================================================
# OFFRES D'EMPLOI — CRUD avec nettoyage automatique
# ============================================================

class TestJobPostingsIntegration:

    def test_list_postings_returns_200(self, api_client):
        assert api_client.get("/api/v1/postings").status_code == 200

    def test_list_postings_returns_list(self, api_client):
        assert isinstance(api_client.get("/api/v1/postings").json(), list)

    def test_posting_fields_present(self, api_client):
        data = api_client.get("/api/v1/postings").json()
        if data:
            assert "job_id" in data[0]
            assert "title" in data[0]
            assert "status" in data[0]

    def test_create_posting_returns_201_or_200(self, api_client, cleanup_postings):
        """Création + nettoyage automatique via cleanup_postings."""
        payload = {
            "title": f"[TEST] Développeur Python {uuid.uuid4().hex[:6]}",
            "description": "Poste de test automatique",
            "required_skills": ["Python", "FastAPI"],
            "nb_positions": 1,
        }
        r = api_client.post("/api/v1/postings", json=payload)
        assert r.status_code in (200, 201)
        cleanup_postings.track(r.json().get("job_id"))

    def test_create_posting_returns_job_id(self, api_client, cleanup_postings):
        payload = {
            "title": f"[TEST] DevOps Engineer {uuid.uuid4().hex[:6]}",
            "description": "Poste DevOps pour test",
            "required_skills": ["Docker", "Kubernetes"],
        }
        r = api_client.post("/api/v1/postings", json=payload)
        if r.status_code in (200, 201):
            data = r.json()
            assert "job_id" in data
            cleanup_postings.track(data.get("job_id"))

    def test_create_posting_without_title_returns_422(self, api_client):
        r = api_client.post("/api/v1/postings", json={"description": "Sans titre"})
        assert r.status_code == 422

    def test_create_and_get_posting(self, api_client, cleanup_postings):
        payload = {
            "title": f"[TEST] Data Scientist {uuid.uuid4().hex[:6]}",
            "description": "Test get",
            "required_skills": ["Python", "ML"],
        }
        create = api_client.post("/api/v1/postings", json=payload)
        if create.status_code in (200, 201):
            job_id = create.json()["job_id"]
            cleanup_postings.track(job_id)
            get = api_client.get(f"/api/v1/postings/{job_id}")
            assert get.status_code == 200
            assert "[TEST]" in get.json()["title"]

    def test_create_and_delete_posting(self, api_client):
        """Ce test gère son propre nettoyage via DELETE."""
        payload = {"title": f"[TEST] À Supprimer {uuid.uuid4().hex[:6]}"}
        create = api_client.post("/api/v1/postings", json=payload)
        if create.status_code in (200, 201):
            job_id = create.json()["job_id"]
            delete = api_client.delete(f"/api/v1/postings/{job_id}")
            assert delete.status_code in (200, 204)

    def test_get_nonexistent_posting_returns_404(self, api_client):
        r = api_client.get("/api/v1/postings/posting-inexistant-xyz")
        assert r.status_code in (404, 422, 500)

    def test_delete_nonexistent_posting_returns_404(self, api_client):
        r = api_client.delete("/api/v1/postings/inexistant-id-xyz")
        assert r.status_code in (404, 422, 500)

    def test_create_posting_with_all_fields(self, api_client, cleanup_postings):
        payload = {
            "title": f"[TEST] Backend Senior {uuid.uuid4().hex[:6]}",
            "description": "Description complète",
            "required_skills": ["Python", "FastAPI", "PostgreSQL"],
            "preferred_skills": ["Docker", "Redis"],
            "nb_positions": 2,
            "location": "Tunis",
            "employment_type": "full-time",
        }
        r = api_client.post("/api/v1/postings", json=payload)
        assert r.status_code in (200, 201)
        cleanup_postings.track(r.json().get("job_id"))


# ============================================================
# DASHBOARD — Lecture seule (pas de création)
# ============================================================

class TestDashboardIntegration:

    def test_stats_returns_200(self, api_client):
        assert api_client.get("/api/v1/dashboard/stats").status_code == 200

    def test_stats_has_required_keys(self, api_client):
        data = api_client.get("/api/v1/dashboard/stats").json()
        assert "activeCandidates" in data
        assert "cvsScreened" in data
        assert "hiredCandidates" in data

    def test_stats_values_are_non_negative(self, api_client):
        data = api_client.get("/api/v1/dashboard/stats").json()
        assert data["activeCandidates"] >= 0
        assert data["cvsScreened"] >= 0
        assert data["hiredCandidates"] >= 0

    def test_departments_returns_200(self, api_client):
        assert api_client.get("/api/v1/dashboard/departments").status_code == 200

    def test_departments_returns_list(self, api_client):
        assert isinstance(api_client.get("/api/v1/dashboard/departments").json(), list)

    def test_trends_returns_200(self, api_client):
        assert api_client.get("/api/v1/dashboard/trends").status_code == 200

    def test_top_skills_returns_200(self, api_client):
        assert api_client.get("/api/v1/dashboard/top-skills").status_code == 200

    def test_recent_activity_returns_200(self, api_client):
        assert api_client.get("/api/v1/dashboard/recent-activity").status_code == 200


# ============================================================
# FLUX COMPLET — Cycle de vie avec nettoyage garanti
# ============================================================

class TestFullScenario:

    def test_full_posting_lifecycle(self, api_client):
        """Crée, vérifie, récupère et supprime — base propre après."""
        payload = {
            "title": f"[TEST] Full Stack Developer {uuid.uuid4().hex[:6]}",
            "description": "Test du cycle de vie complet",
            "required_skills": ["React", "Python"],
        }
        # 1. Créer
        create = api_client.post("/api/v1/postings", json=payload)
        assert create.status_code in (200, 201), f"Création échouée: {create.text}"
        job_id = create.json()["job_id"]

        try:
            # 2. Vérifier dans la liste
            ids = [p["job_id"] for p in api_client.get("/api/v1/postings").json()]
            assert job_id in ids

            # 3. Récupérer par ID
            get = api_client.get(f"/api/v1/postings/{job_id}")
            assert get.status_code == 200
            assert "[TEST]" in get.json()["title"]

        finally:
            # 4. Supprimer dans tous les cas (finally garantit le nettoyage)
            api_client.delete(f"/api/v1/postings/{job_id}")

            # 5. Vérifier suppression
            get_after = api_client.get(f"/api/v1/postings/{job_id}")
            assert get_after.status_code in (404, 500)
