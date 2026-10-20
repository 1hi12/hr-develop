"""
/api/v1/matching — CV-to-job matching endpoint.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_match_use_case
from app.application.use_cases.match_candidates import MatchCandidatesUseCase
from app.application.dtos.match_dto import MatchRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/matching", tags=["Matching"])


@router.post("/match")
async def match_candidates(
    req: MatchRequest,
    use_case: MatchCandidatesUseCase = Depends(get_match_use_case),
):
    """Phases 7-9: Vector search -> LLM rerank -> ranked response."""
    try:
        response = await use_case.execute(req)
        return {"success": True, **response.model_dump()}
    except Exception as e:
        logger.exception("Matching error: %s", e)
        raise HTTPException(status_code=500, detail="Matching failed")
