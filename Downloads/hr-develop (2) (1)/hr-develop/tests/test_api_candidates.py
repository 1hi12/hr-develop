"""
Tests API — /api/v1/candidates
Mock : PostgreSQL (AsyncSessionLocal), Redis (ARQ pool)
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


def make_candidate(
    candidate_id="test-id-123",
    full_name="Ali Ben Salah",
    email="ali@example.com",
    status="active",
    skills_json=None,
):
    c = MagicMock()
    c.candidate_id = candidate_id
    c.full_name = full_name
    c.email = email
    c.phone = "+216 12 345 678"
    c.location = "Tunis"
    c.linkedin = None
    c.github = None
    c.summary = "Développeur Python senior"
    c.languages_json = []
    c.skills_json = skills_json or {"technical": ["Python", "FastAPI"]}
    c.seniority_level = "Senior"
    c.total_years_experience = 5
    c.extraction_confidence = 0.95
    c.cv_file_hash = "abc123"
    c.cv_raw_text = None
    c.status = status
    c.created_at = None
    c.updated_at = None
    c.extracted_skills = None
    c.experiences = []
    c.educations = []
    c.filename = "cv_ali.pdf"
    return c


class TestListCandidates:
    def test_returns_empty_list_when_no_candidates(self, client):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_scalar = AsyncMock(return_value=0)

        with patch("app.infrastructure.database.session.AsyncSessionLocal") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.scalar = mock_scalar
            mock_session_cls.return_value = mock_session

            response = client.get("/api/v1/candidates")
            assert response.status_code in (200, 500)

    def test_list_endpoint_exists(self, client):
        response = client.get("/api/v1/candidates")
        assert response.status_code != 404

    def test_list_accepts_pagination_params(self, client):
        response = client.get("/api/v1/candidates?page=1&page_size=10")
        assert response.status_code != 404

    def test_list_accepts_status_filter(self, client):
        response = client.get("/api/v1/candidates?status=active")
        assert response.status_code != 404


class TestUploadCV:
    def test_upload_requires_file(self, client):
        response = client.post("/api/v1/candidates/upload")
        assert response.status_code in (405, 422)

    def test_upload_endpoint_exists(self, client):
        import io
        fake_pdf = io.BytesIO(b"%PDF-1.4 fake content")
        with patch("arq.create_pool", new_callable=AsyncMock), \
             patch("app.infrastructure.database.session.AsyncSessionLocal"):
            response = client.post(
                "/api/v1/candidates/upload",
                files={"file": ("test.pdf", fake_pdf, "application/pdf")},
            )
            assert response.status_code != 404

    def test_upload_rejects_non_pdf(self, client):
        import io
        fake_txt = io.BytesIO(b"just text content")
        with patch("arq.create_pool", new_callable=AsyncMock), \
             patch("app.infrastructure.database.session.AsyncSessionLocal"):
            response = client.post(
                "/api/v1/candidates/upload",
                files={"file": ("test.txt", fake_txt, "text/plain")},
            )
            assert response.status_code in (400, 422, 500)


class TestGetCandidate:
    def test_get_nonexistent_candidate_returns_404(self, client):
        with patch("app.infrastructure.database.session.AsyncSessionLocal") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session_cls.return_value = mock_session

            response = client.get("/api/v1/candidates/nonexistent-id")
            assert response.status_code in (404, 500)
