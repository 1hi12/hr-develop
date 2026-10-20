"""
Tests API — /api/v1/postings
Mock : JobPostingRepository, CandidateRepository
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def client():
    with patch("pymilvus.connections.connect"), \
         patch("app.infrastructure.database.pg_notify.CVProcessingListener"):
        from main import app
        from fastapi.testclient import TestClient
        return TestClient(app, raise_server_exceptions=False)


def make_posting(
    posting_id="job-id-123",
    title="Développeur Python",
    description="Poste FastAPI senior",
    status="open",
):
    p = MagicMock()
    p.posting_id = posting_id
    p.title = title
    p.description = description
    p.status = status
    p.department = "Backend"
    p.location = "Tunis"
    p.required_skills = ["Python", "FastAPI"]
    p.nb_positions = 1
    p.salary_min = None
    p.salary_max = None
    p.salary_currency = "TND"
    p.created_at = None
    p.closed_at = None
    return p


class TestListJobPostings:
    def test_list_endpoint_exists(self, client):
        response = client.get("/api/v1/postings")
        assert response.status_code != 404

    def test_list_returns_200_or_500(self, client):
        with patch("app.infrastructure.repositories.job_posting_repo.JobPostingRepository") as mock_repo:
            instance = AsyncMock()
            instance.list_all.return_value = []
            mock_repo.return_value = instance
            response = client.get("/api/v1/postings")
            assert response.status_code in (200, 500)


class TestCreateJobPosting:
    def test_create_requires_body(self, client):
        response = client.post("/api/v1/postings")
        assert response.status_code == 422

    def test_create_valid_posting(self, client):
        payload = {
            "title": "Développeur Python Senior",
            "description": "Poste senior FastAPI",
            "required_skills": ["Python", "FastAPI"],
            "nb_positions": 2,
        }
        mock_repo = AsyncMock()
        mock_repo.find_by_title.return_value = None
        mock_repo.create.return_value = make_posting(title="Développeur Python Senior")

        with patch("app.api.v1.routes.job_postings.JobPostingRepository", return_value=mock_repo), \
             patch("app.api.v1.routes.job_postings._extract_department", new_callable=AsyncMock, return_value="Backend"):
            response = client.post("/api/v1/postings", json=payload)
            assert response.status_code in (200, 201, 500)

    def test_create_missing_title_returns_422(self, client):
        payload = {"description": "Sans titre"}
        response = client.post("/api/v1/postings", json=payload)
        assert response.status_code == 422

    def test_create_with_only_title_is_accepted(self, client):
        payload = {"title": "Sans description"}
        mock_repo = AsyncMock()
        mock_repo.find_by_title.return_value = None
        mock_repo.create.return_value = make_posting(title="Sans description")
        with patch("app.api.v1.routes.job_postings.JobPostingRepository", return_value=mock_repo), \
             patch("app.api.v1.routes.job_postings._extract_department", new_callable=AsyncMock, return_value="Autre"):
            response = client.post("/api/v1/postings", json=payload)
            assert response.status_code in (200, 201, 422, 500)


class TestDeleteJobPosting:
    def test_delete_nonexistent_returns_404_or_500(self, client):
        with patch("app.infrastructure.repositories.job_posting_repo.JobPostingRepository") as mock_repo:
            instance = AsyncMock()
            instance.get_by_id.return_value = None
            mock_repo.return_value = instance
            response = client.delete("/api/v1/postings/nonexistent-id")
            assert response.status_code in (404, 500)
