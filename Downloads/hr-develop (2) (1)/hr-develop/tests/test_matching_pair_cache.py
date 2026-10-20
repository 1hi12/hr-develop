"""
Tests unitaires — cache par paire (candidat, poste)
=====================================================
Fonctions pures testées : job_content_hash, candidate_content_hash
(matching_cache.py) et _score_tuple_to_cache_dict / _cache_dict_to_score_tuple
(job_matching.py). Aucun LLM, aucun Redis réel.
"""
import pytest

from app.services.matching_cache import job_content_hash, candidate_content_hash
from app.services.job_matching import (
    MatchingScore,
    _score_tuple_to_cache_dict,
    _cache_dict_to_score_tuple,
)

pytestmark = pytest.mark.unit


class TestJobContentHash:
    def test_same_inputs_same_hash(self):
        h1 = job_content_hash("Dev", "desc", ["Python", "SQL"], "mid")
        h2 = job_content_hash("Dev", "desc", ["Python", "SQL"], "mid")
        assert h1 == h2

    def test_skill_order_does_not_matter(self):
        h1 = job_content_hash("Dev", "desc", ["Python", "SQL"], "mid")
        h2 = job_content_hash("Dev", "desc", ["SQL", "Python"], "mid")
        assert h1 == h2

    def test_description_change_changes_hash(self):
        h1 = job_content_hash("Dev", "desc A", ["Python"], "mid")
        h2 = job_content_hash("Dev", "desc B", ["Python"], "mid")
        assert h1 != h2

    def test_required_skills_change_changes_hash(self):
        h1 = job_content_hash("Dev", "desc", ["Python"], "mid")
        h2 = job_content_hash("Dev", "desc", ["Python", "Go"], "mid")
        assert h1 != h2

    def test_seniority_change_changes_hash(self):
        h1 = job_content_hash("Dev", "desc", ["Python"], "mid")
        h2 = job_content_hash("Dev", "desc", ["Python"], "senior")
        assert h1 != h2

    def test_none_seniority_does_not_crash(self):
        assert job_content_hash("Dev", "desc", ["Python"], None)


class TestCandidateContentHash:
    def test_same_inputs_same_hash(self):
        h1 = candidate_content_hash(["Python", "SQL"], "mid", 3, "summary")
        h2 = candidate_content_hash(["Python", "SQL"], "mid", 3, "summary")
        assert h1 == h2

    def test_skill_order_does_not_matter(self):
        h1 = candidate_content_hash(["Python", "SQL"], "mid", 3, "summary")
        h2 = candidate_content_hash(["SQL", "Python"], "mid", 3, "summary")
        assert h1 == h2

    def test_new_skill_changes_hash(self):
        h1 = candidate_content_hash(["Python"], "mid", 3, "summary")
        h2 = candidate_content_hash(["Python", "Docker"], "mid", 3, "summary")
        assert h1 != h2

    def test_seniority_change_changes_hash(self):
        h1 = candidate_content_hash(["Python"], "mid", 3, "summary")
        h2 = candidate_content_hash(["Python"], "senior", 3, "summary")
        assert h1 != h2

    def test_years_exp_change_changes_hash(self):
        h1 = candidate_content_hash(["Python"], "mid", 3, "summary")
        h2 = candidate_content_hash(["Python"], "mid", 5, "summary")
        assert h1 != h2

    def test_summary_change_changes_hash(self):
        h1 = candidate_content_hash(["Python"], "mid", 3, "summary A")
        h2 = candidate_content_hash(["Python"], "mid", 3, "summary B")
        assert h1 != h2

    def test_none_years_exp_does_not_crash(self):
        assert candidate_content_hash(["Python"], "mid", None, "summary")

    def test_experience_titles_change_changes_hash(self):
        h1 = candidate_content_hash(["Python"], "mid", 3, "summary", "Dev @ Acme")
        h2 = candidate_content_hash(["Python"], "mid", 3, "summary", "Lead Dev @ Acme")
        assert h1 != h2

    def test_experience_titles_defaults_to_empty(self):
        h1 = candidate_content_hash(["Python"], "mid", 3, "summary")
        h2 = candidate_content_hash(["Python"], "mid", 3, "summary", "")
        assert h1 == h2


class TestScoreTupleCacheRoundTrip:
    def test_round_trip_preserves_all_fields(self):
        ms = MatchingScore(
            skill_score=72.3,
            seniority_multiplier=0.85,
            final_score=68.1,
            seniority_gap=-1,
            skill_coverage=0.6,
            cross_encoder_score=-1.0,
        )
        original = (
            ms, "Bonne correspondance", ["Python"], ["Go"],
            ["Solide en Python"], ["Manque Go"], "À considérer",
        )

        cache_dict = _score_tuple_to_cache_dict(original)
        restored = _cache_dict_to_score_tuple(cache_dict)

        restored_ms = restored[0]
        assert restored_ms.skill_score == ms.to_dict()["skill_score"]
        assert restored_ms.final_score == ms.to_dict()["final_score"]
        assert restored_ms.seniority_gap == ms.seniority_gap
        assert restored[1:] == original[1:]

    def test_cache_dict_is_json_serializable(self):
        import json
        ms = MatchingScore(50.0, 1.0, 50.0, 0, 0.5, -1.0)
        result = (ms, "j", [], [], [], [], "")
        d = _score_tuple_to_cache_dict(result)
        # Must not raise — this is what actually gets stored in Redis.
        json.dumps(d)
