"""
test_precision.py — Calibration harness for AIScorer precision
=================================================================
NOT part of the default unit suite: this hits the REAL Orange LLM proxy
(costs tokens, needs network + settings.litellm_api_key) and every fixture
in fixtures.py is a PLACEHOLDER until a human sets validated=True on it.

Run explicitly, once fixtures are filled in:
    pytest tests/calibration/test_precision.py -v -s

Until then, every case SKIPS (not passes, not fails) — a skip here means
"no ground truth to check against yet", which is the honest state, not a
green check mark that doesn't mean anything.
"""
import pytest

from app.services.job_matching import AIScorer, MultiModelAIEngine
from tests.calibration.fixtures import FIXTURES

pytestmark = pytest.mark.calibration


@pytest.mark.parametrize("case", FIXTURES, ids=[c["id"] for c in FIXTURES])
async def test_scoring_matches_human_expectation(case):
    if not case.get("validated"):
        pytest.skip(
            f"'{case['id']}': expected_score_range is a placeholder, not human-validated — "
            f"see tests/calibration/fixtures.py"
        )

    engine = MultiModelAIEngine()
    scorer = AIScorer(engine)

    ms, justif, matched, missing, strengths, weaknesses, recommendation = await scorer.score(
        job_title           =case["job"]["title"],
        job_description      =case["job"]["description"],
        required_skills      =case["job"]["required_skills"],
        job_seniority         =case["job"]["seniority"],
        candidate_name        =case["candidate"]["name"],
        candidate_skills      =case["candidate"]["skills"],
        candidate_seniority   =case["candidate"]["seniority"],
        years_exp             =case["candidate"]["years_exp"],
        cv_summary            =case["candidate"]["cv_summary"],
    )

    lo, hi = case["expected_score_range"]
    print(
        f"\n[{case['id']}] got final_score={ms.final_score} "
        f"(expected [{lo},{hi}]) — {case['notes']}"
    )
    assert lo <= ms.final_score <= hi, (
        f"{case['id']}: LLM scored {ms.final_score}, human expected [{lo},{hi}]. "
        f"Justification: {justif}"
    )
