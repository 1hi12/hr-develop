"""
Tests de Performance — HR System
Outil : Locust
URL   : http://localhost:8000

Scénarios testés :
  - Health check
  - Liste candidats
  - Liste offres d'emploi
  - Dashboard stats
  - Créer + Supprimer une offre
"""

from locust import HttpUser, task, between
import uuid


class HRSystemUser(HttpUser):
    host = "http://localhost:8000"
    wait_time = between(1, 3)  # attente entre 1 et 3 secondes entre chaque requête

    # ── Santé du serveur ──────────────────────────────────────
    @task(1)
    def health_check(self):
        self.client.get("/health", name="GET /health")

    # ── Candidats ─────────────────────────────────────────────
    @task(4)
    def list_candidates(self):
        self.client.get("/api/v1/candidates", name="GET /candidates")

    @task(2)
    def list_candidates_with_pagination(self):
        self.client.get(
            "/api/v1/candidates?page=1&page_size=10",
            name="GET /candidates (pagination)"
        )

    @task(2)
    def list_candidates_filter_active(self):
        self.client.get(
            "/api/v1/candidates?status=active",
            name="GET /candidates (filtre actif)"
        )

    # ── Offres d'emploi ───────────────────────────────────────
    @task(4)
    def list_postings(self):
        self.client.get("/api/v1/postings", name="GET /postings")

    @task(3)
    def create_and_delete_posting(self):
        title = f"Perf Test {uuid.uuid4().hex[:8]}"
        payload = {
            "title": title,
            "description": "Test de charge locust",
            "required_skills": ["Python", "FastAPI"],
        }
        with self.client.post(
            "/api/v1/postings",
            json=payload,
            name="POST /postings",
            catch_response=True
        ) as response:
            if response.status_code in (200, 201):
                job_id = response.json().get("job_id")
                if job_id:
                    self.client.delete(
                        f"/api/v1/postings/{job_id}",
                        name="DELETE /postings/{id}"
                    )
                response.success()
            elif response.status_code == 409:
                response.success()  # doublon accepté
            else:
                response.failure(f"Erreur: {response.status_code}")

    # ── Dashboard ─────────────────────────────────────────────
    @task(3)
    def dashboard_stats(self):
        self.client.get("/api/v1/dashboard/stats", name="GET /dashboard/stats")

    @task(2)
    def dashboard_departments(self):
        self.client.get(
            "/api/v1/dashboard/departments",
            name="GET /dashboard/departments"
        )

    @task(2)
    def dashboard_trends(self):
        self.client.get(
            "/api/v1/dashboard/trends",
            name="GET /dashboard/trends"
        )

    @task(1)
    def dashboard_top_skills(self):
        self.client.get(
            "/api/v1/dashboard/top-skills",
            name="GET /dashboard/top-skills"
        )
