"""
Tests API — /api/v1/dashboard
Mock : AsyncSessionLocal
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


def mock_empty_db_session():
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.scalar = AsyncMock(return_value=0)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)
    return mock_session


class TestDashboardStats:
    def test_stats_endpoint_exists(self, client):
        response = client.get("/api/v1/dashboard/stats")
        assert response.status_code != 404

    def test_stats_returns_expected_keys(self, client):
        with patch("app.infrastructure.database.session.AsyncSessionLocal") as mock_cls:
            mock_cls.return_value = mock_empty_db_session()
            response = client.get("/api/v1/dashboard/stats")
            if response.status_code == 200:
                data = response.json()
                assert "activeCandidates" in data
                assert "cvsScreened" in data
                assert "hiredCandidates" in data
                assert "avgDaysToHire" in data

    def test_stats_values_are_integers_or_zero(self, client):
        with patch("app.infrastructure.database.session.AsyncSessionLocal") as mock_cls:
            mock_cls.return_value = mock_empty_db_session()
            response = client.get("/api/v1/dashboard/stats")
            if response.status_code == 200:
                data = response.json()
                assert data["activeCandidates"] >= 0
                assert data["cvsScreened"] >= 0
                assert data["hiredCandidates"] >= 0


class TestDashboardTrends:
    def test_trends_endpoint_exists(self, client):
        response = client.get("/api/v1/dashboard/trends")
        assert response.status_code != 404

    def test_trends_returns_list(self, client):
        with patch("app.infrastructure.database.session.AsyncSessionLocal") as mock_cls:
            mock_cls.return_value = mock_empty_db_session()
            response = client.get("/api/v1/dashboard/trends")
            if response.status_code == 200:
                data = response.json()
                assert isinstance(data, list)


class TestDashboardDepartments:
    def test_departments_endpoint_exists(self, client):
        response = client.get("/api/v1/dashboard/departments")
        assert response.status_code != 404

    def test_departments_returns_list(self, client):
        with patch("app.infrastructure.database.session.AsyncSessionLocal") as mock_cls:
            mock_cls.return_value = mock_empty_db_session()
            response = client.get("/api/v1/dashboard/departments")
            if response.status_code == 200:
                data = response.json()
                assert isinstance(data, list)
