"""
Tests UAT — API FastAPI (httpx)
Vérifie tous les endpoints REST de l'application HR
"""
import os
import uuid
import pytest
import httpx

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
client  = httpx.Client(base_url=API_URL, timeout=30)


# ── Santé ────────────────────────────────────────────────────

class TestSante:

    def test_health_ok(self):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_openapi_accessible(self):
        r = client.get("/openapi.json")
        assert r.status_code == 200
        assert "paths" in r.json()


# ── Candidats ────────────────────────────────────────────────

class TestAPICandidats:

    def test_liste_candidats_200(self):
        r = client.get("/api/v1/candidates")
        assert r.status_code == 200
        assert "items" in r.json()

    def test_liste_candidats_structure(self):
        r = client.get("/api/v1/candidates")
        items = r.json()["items"]
        if items:
            c = items[0]
            assert "candidate_id" in c
            assert "status" in c
            assert "filename" in c

    def test_filtre_status_pending(self):
        r = client.get("/api/v1/candidates?status=pending")
        assert r.status_code == 200

    def test_filtre_status_active(self):
        r = client.get("/api/v1/candidates?status=active")
        assert r.status_code == 200

    def test_candidat_inexistant_404(self):
        r = client.get("/api/v1/candidates/candidat-inexistant-999")
        assert r.status_code in (404, 500)

    def test_upload_sans_fichier_422(self):
        r = client.post("/api/v1/candidates/upload")
        assert r.status_code in (400, 422)

    def test_upload_vrai_pdf(self):
        import io
        # PDF minimal valide
        pdf = io.BytesIO(b"%PDF-1.4\n1 0 obj<</Type /Catalog>>endobj")
        r   = client.post(
            "/api/v1/candidates/upload",
            files={"file": ("cv_test.pdf", pdf, "application/pdf")},
        )
        assert r.status_code in (200, 201, 202)

    def test_status_invalide_rejete(self):
        r = client.get("/api/v1/candidates")
        items = r.json().get("items", [])
        if not items:
            pytest.skip("Aucun candidat")
        cid = items[0]["candidate_id"]
        r   = client.patch(
            f"/api/v1/candidates/{cid}/status",
            json={"status": "statut_invalide"},
        )
        assert r.status_code in (400, 422)

    def test_statuts_valides_acceptes(self):
        r = client.get("/api/v1/candidates")
        items = r.json().get("items", [])
        if not items:
            pytest.skip("Aucun candidat")
        cid = items[0]["candidate_id"]
        for statut in ["pending", "interviewing", "rejected"]:
            res = client.patch(
                f"/api/v1/candidates/{cid}/status",
                json={"status": statut},
            )
            assert res.status_code == 200


# ── Offres d'emploi ──────────────────────────────────────────

class TestAPIOffres:

    def test_liste_offres_200(self):
        r = client.get("/api/v1/postings")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_creer_offre_minimale(self):
        r = client.post("/api/v1/postings", json={
            "title": f"UAT API {uuid.uuid4().hex[:6]}"
        })
        assert r.status_code in (200, 201)
        assert "job_id" in r.json()
        client.delete(f"/api/v1/postings/{r.json()['job_id']}")

    def test_creer_offre_complete(self):
        r = client.post("/api/v1/postings", json={
            "title":           f"UAT Complet {uuid.uuid4().hex[:6]}",
            "description":     "Poste senior Python",
            "required_skills": ["Python", "FastAPI", "Docker"],
            "location":        "Tunis",
            "nb_positions":    2,
        })
        assert r.status_code in (200, 201)
        client.delete(f"/api/v1/postings/{r.json()['job_id']}")

    def test_sans_titre_422(self):
        r = client.post("/api/v1/postings", json={"description": "sans titre"})
        assert r.status_code == 422

    def test_get_offre_par_id(self):
        cr = client.post("/api/v1/postings", json={
            "title": f"UAT Get {uuid.uuid4().hex[:6]}"
        })
        job_id = cr.json()["job_id"]
        r      = client.get(f"/api/v1/postings/{job_id}")
        assert r.status_code == 200
        assert r.json()["job_id"] == job_id
        client.delete(f"/api/v1/postings/{job_id}")

    def test_fermer_offre(self):
        cr     = client.post("/api/v1/postings", json={"title": f"UAT Close {uuid.uuid4().hex[:6]}"})
        job_id = cr.json()["job_id"]
        r      = client.patch(f"/api/v1/postings/{job_id}/status", json={"status": "closed"})
        assert r.status_code == 200
        assert r.json()["status"] == "closed"
        client.delete(f"/api/v1/postings/{job_id}")

    def test_supprimer_offre(self):
        cr     = client.post("/api/v1/postings", json={"title": f"UAT Del {uuid.uuid4().hex[:6]}"})
        job_id = cr.json()["job_id"]
        r      = client.delete(f"/api/v1/postings/{job_id}")
        assert r.status_code in (200, 204)


# ── Dashboard ────────────────────────────────────────────────

class TestAPIDashboard:

    def test_stats_200(self):
        r = client.get("/api/v1/dashboard/stats")
        assert r.status_code == 200

    def test_stats_champs_requis(self):
        data = client.get("/api/v1/dashboard/stats").json()
        for champ in ["activeCandidates", "cvsScreened", "hiredCandidates"]:
            assert champ in data

    def test_departments_liste(self):
        r = client.get("/api/v1/dashboard/departments")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_trends_liste(self):
        r = client.get("/api/v1/dashboard/trends")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_top_skills_200(self):
        assert client.get("/api/v1/dashboard/top-skills").status_code == 200

    def test_recent_activity_200(self):
        assert client.get("/api/v1/dashboard/recent-activity").status_code == 200
