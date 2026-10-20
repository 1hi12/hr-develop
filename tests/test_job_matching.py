"""
Tests unitaires — job_matching.py
Fonctions pures testées : _seniority_multiplier, compute_match_score, MatchingScore.to_dict
Aucun LLM, aucun mock réseau.
"""
import pytest
from app.services.job_matching import (
    _seniority_multiplier,
    compute_match_score,
    MatchingScore,
)


class TestSeniorityMultiplier:
    """Tests pour _seniority_multiplier(gap) → float"""

    def test_gap_zero_returns_1(self):
        assert _seniority_multiplier(0) == 1.00

    def test_gap_positive_returns_1(self):
        assert _seniority_multiplier(1) == 1.00

    def test_gap_positive_large_returns_1(self):
        assert _seniority_multiplier(5) == 1.00

    def test_gap_minus_1_returns_070(self):
        assert _seniority_multiplier(-1) == 0.70

    def test_gap_minus_2_returns_040(self):
        assert _seniority_multiplier(-2) == 0.40

    def test_gap_minus_3_returns_010(self):
        assert _seniority_multiplier(-3) == 0.10

    def test_gap_minus_4_returns_0(self):
        assert _seniority_multiplier(-4) == 0.00

    def test_gap_minus_5_returns_0(self):
        assert _seniority_multiplier(-5) == 0.00

    def test_result_is_float(self):
        assert isinstance(_seniority_multiplier(0), float)

    def test_result_between_0_and_1(self):
        for gap in range(-6, 4):
            result = _seniority_multiplier(gap)
            assert 0.0 <= result <= 1.0, f"Valeur hors bornes pour gap={gap}: {result}"


class TestComputeMatchScore:
    """Tests pour compute_match_score() → MatchingScore"""

    # ── Retourne un MatchingScore ──────────────────────────────
    def test_returns_matching_score_instance(self):
        result = compute_match_score(0.8, "senior", "senior")
        assert isinstance(result, MatchingScore)

    # ── Scores de base ─────────────────────────────────────────
    def test_perfect_cosine_same_seniority_high_score(self):
        result = compute_match_score(1.0, "senior", "senior", skill_coverage=1.0)
        assert result.final_score >= 90.0

    def test_zero_cosine_zero_coverage_low_score(self):
        result = compute_match_score(0.0, "junior", "senior", skill_coverage=0.0)
        assert result.final_score <= 30.0

    def test_score_between_0_and_100(self):
        result = compute_match_score(0.7, "mid", "mid", skill_coverage=0.6)
        assert 0.0 <= result.final_score <= 100.0

    # ── Seniority gap ──────────────────────────────────────────
    def test_senior_vs_junior_requirement_no_penalty(self):
        result = compute_match_score(0.8, "senior", "junior", skill_coverage=0.8)
        assert result.seniority_gap > 0
        assert result.seniority_multiplier == 1.00

    def test_junior_vs_senior_requirement_penalty(self):
        result = compute_match_score(0.8, "junior", "senior", skill_coverage=0.8)
        assert result.seniority_gap < 0
        assert result.seniority_multiplier < 1.00

    def test_intern_vs_senior_hard_cap(self):
        result = compute_match_score(1.0, "intern", "senior", skill_coverage=1.0)
        assert result.final_score <= 45.0

    def test_intern_vs_expert_hard_cap(self):
        result = compute_match_score(1.0, "intern", "expert", skill_coverage=1.0)
        assert result.final_score <= 25.0

    # ── Coverage cap ───────────────────────────────────────────
    def test_zero_coverage_caps_score_at_15(self):
        result = compute_match_score(1.0, "senior", "senior", skill_coverage=0.0)
        assert result.final_score <= 15.0

    def test_low_coverage_caps_score(self):
        result = compute_match_score(1.0, "senior", "senior", skill_coverage=0.05)
        assert result.final_score <= 25.0

    def test_no_required_skills_ignores_coverage(self):
        result = compute_match_score(0.9, "senior", "senior", skill_coverage=-1.0)
        assert result.final_score > 50.0

    # ── Cross-encoder ──────────────────────────────────────────
    def test_with_cross_encoder_score(self):
        result = compute_match_score(
            0.7, "senior", "senior",
            skill_coverage=0.8,
            cross_encoder_score=0.9,
        )
        assert result.final_score >= 70.0

    def test_cross_encoder_minus1_means_not_used(self):
        result = compute_match_score(0.7, "mid", "mid", skill_coverage=0.7, cross_encoder_score=-1.0)
        assert result.cross_encoder_score == -1.0

    # ── Seniority inconnu ──────────────────────────────────────
    def test_unknown_seniority_treated_as_mid(self):
        result_unknown = compute_match_score(0.7, "unknown", "mid", skill_coverage=0.7)
        result_mid = compute_match_score(0.7, "mid", "mid", skill_coverage=0.7)
        assert result_unknown.final_score == result_mid.final_score

    def test_none_seniority_handled(self):
        result = compute_match_score(0.7, None, None, skill_coverage=0.7)
        assert 0.0 <= result.final_score <= 100.0

    # ── Champs du MatchingScore ────────────────────────────────
    def test_skill_score_is_cosine_times_100(self):
        result = compute_match_score(0.75, "mid", "mid")
        assert result.skill_score == pytest.approx(75.0, abs=0.1)

    def test_seniority_gap_is_correct(self):
        result = compute_match_score(0.8, "junior", "senior", skill_coverage=0.8)
        assert result.seniority_gap == -2

    def test_skill_coverage_stored(self):
        result = compute_match_score(0.8, "mid", "mid", skill_coverage=0.65)
        assert result.skill_coverage == pytest.approx(0.65)


class TestMatchingScoreToDict:
    """Tests pour MatchingScore.to_dict()"""

    def test_to_dict_returns_dict(self):
        result = compute_match_score(0.8, "senior", "senior", skill_coverage=0.9)
        assert isinstance(result.to_dict(), dict)

    def test_to_dict_has_all_keys(self):
        result = compute_match_score(0.8, "senior", "senior", skill_coverage=0.9)
        d = result.to_dict()
        expected_keys = [
            "skill_score",
            "seniority_multiplier",
            "final_score",
            "seniority_gap",
            "skill_coverage",
            "cross_encoder_score",
        ]
        for key in expected_keys:
            assert key in d, f"Clé manquante: {key}"

    def test_to_dict_values_are_rounded(self):
        result = compute_match_score(0.8333, "mid", "mid", skill_coverage=0.6666)
        d = result.to_dict()
        assert d["skill_score"] == round(d["skill_score"], 1)
        assert d["skill_coverage"] == round(d["skill_coverage"], 2)

    def test_to_dict_final_score_between_0_and_100(self):
        result = compute_match_score(0.9, "senior", "mid", skill_coverage=0.85)
        d = result.to_dict()
        assert 0.0 <= d["final_score"] <= 100.0
