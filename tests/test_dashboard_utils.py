"""
Tests unitaires — _classify_department (dashboard.py)
Aucun mock nécessaire : fonction pure.
"""
import pytest
from app.api.v1.routes.dashboard import _classify_department


class TestClassifyDepartment:
    def test_returns_stored_department_if_set(self):
        assert _classify_department("Finance", "n/a") == "Finance"

    def test_ignores_title_if_department_set(self):
        assert _classify_department("Marketing", "DevOps Engineer") == "Marketing"

    def test_devops_from_title(self):
        assert _classify_department(None, "DevOps Engineer") == "IT"

    def test_data_science_from_title(self):
        assert _classify_department(None, "Machine Learning Engineer") == "Data Science"

    def test_data_engineering_from_title(self):
        assert _classify_department(None, "Data Engineer") == "Data Engineering"

    def test_frontend_from_title(self):
        assert _classify_department(None, "Frontend React Developer") == "Frontend"

    def test_backend_from_title(self):
        assert _classify_department(None, "Backend FastAPI Developer") == "Backend"

    def test_fullstack_from_title(self):
        assert _classify_department(None, "Fullstack Developer") == "Fullstack"

    def test_mobile_from_title(self):
        assert _classify_department(None, "Mobile iOS Developer") == "Mobile"

    def test_cybersecurity_from_title(self):
        assert _classify_department(None, "Security Analyst") == "Cybersécurité"

    def test_qa_from_title(self):
        assert _classify_department(None, "QA Test Engineer") == "QA / Testing"

    def test_rh_from_title(self):
        assert _classify_department(None, "HR Manager talent acquisition") == "RH"

    def test_unknown_returns_autre(self):
        assert _classify_department(None, "Responsable cuisine") == "Autre"

    def test_none_title_returns_autre(self):
        assert _classify_department(None, None) == "Autre"

    def test_empty_department_uses_title(self):
        assert _classify_department("", "DevOps Engineer") == "IT"

    def test_whitespace_department_uses_title(self):
        assert _classify_department("   ", "DevOps Engineer") == "IT"
