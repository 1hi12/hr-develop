"""
Tests unitaires — skill_normalizer.py
Aucun mock nécessaire : fonctions pures.
"""
import pytest
from app.services.skill_normalizer import normalize_skill, normalize_skills, skill_overlap_score


class TestNormalizeSkill:
    def test_alias_js(self):
        assert normalize_skill("js") == "JavaScript"

    def test_alias_case_insensitive(self):
        assert normalize_skill("JS") == "JavaScript"

    def test_alias_typescript(self):
        assert normalize_skill("ts") == "TypeScript"

    def test_alias_react(self):
        assert normalize_skill("reactjs") == "React"

    def test_alias_python(self):
        assert normalize_skill("py") == "Python"

    def test_alias_postgres(self):
        assert normalize_skill("postgres") == "PostgreSQL"

    def test_alias_kubernetes(self):
        assert normalize_skill("k8s") == "Kubernetes"

    def test_alias_aws(self):
        assert normalize_skill("aws") == "AWS"

    def test_alias_docker(self):
        assert normalize_skill("docker") == "Docker"

    def test_unknown_skill_returns_as_is(self):
        assert normalize_skill("SomeUnknownSkill") == "SomeUnknownSkill"

    def test_strips_whitespace(self):
        assert normalize_skill("  js  ") == "JavaScript"

    def test_empty_string_returns_empty(self):
        assert normalize_skill("") == ""


class TestNormalizeSkills:
    def test_normalizes_list(self):
        result = normalize_skills(["js", "ts", "docker"])
        assert "JavaScript" in result
        assert "TypeScript" in result
        assert "Docker" in result

    def test_deduplicates(self):
        result = normalize_skills(["js", "javascript", "JS"])
        assert result.count("JavaScript") == 1

    def test_removes_empty_strings(self):
        result = normalize_skills(["js", "", "  ", "docker"])
        assert "" not in result
        assert "  " not in result
        assert len(result) == 2

    def test_empty_list(self):
        assert normalize_skills([]) == []

    def test_preserves_unknown_skills(self):
        result = normalize_skills(["MyCustomSkill"])
        assert "MyCustomSkill" in result


class TestSkillOverlapScore:
    def test_full_match(self):
        score = skill_overlap_score(["Python", "Docker"], ["Python", "Docker"])
        assert score == 1.0

    def test_partial_match(self):
        score = skill_overlap_score(["Python", "Docker", "Redis"], ["Python", "Docker"])
        assert score == 1.0

    def test_no_match(self):
        score = skill_overlap_score(["Java", "Spring"], ["Python", "Docker"])
        assert score == 0.0

    def test_empty_required_skills(self):
        score = skill_overlap_score(["Python"], [])
        assert score == 1.0

    def test_empty_candidate_skills(self):
        score = skill_overlap_score([], ["Python", "Docker"])
        assert score == 0.0

    def test_case_insensitive_match(self):
        score = skill_overlap_score(["python", "DOCKER"], ["Python", "Docker"])
        assert score == 1.0

    def test_alias_match(self):
        score = skill_overlap_score(["js"], ["JavaScript"])
        assert score == 1.0

    def test_score_is_between_0_and_1(self):
        score = skill_overlap_score(["Python"], ["Python", "Docker", "Redis"])
        assert 0.0 <= score <= 1.0
