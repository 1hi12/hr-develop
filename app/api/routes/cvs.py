import logging
from typing import Optional, List
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

import app.services.cv_service as cv_service
from app.websocket.ws_ingestion import register_connection, unregister_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cvs", tags=["CVs"])


# ─────────────────────────────────────────
# SCHÉMAS
# ─────────────────────────────────────────

class MatchRequest(BaseModel):
    job_description: str
    required_skills: List[str] = []
    top_k: int = Field(default=5, ge=1)
    min_score: float = Field(default=0.5, ge=0.0, le=1.0)
    use_reranking: bool = True


# ─────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────

@router.post("/upload")
async def upload_cv(
    file: UploadFile = File(...),
    job_id: Optional[str] = Form(None),
    candidate_id: Optional[str] = Form(None),
    websocket_client_id: Optional[str] = Form(None),
):
    """Phase 1→6 : Ingestion rapide — stockage Milvus uniquement."""
    try:
        result = await cv_service.upload_and_process_cv(
            file=file,
            job_id=job_id,
            candidate_id=candidate_id,
            websocket_client_id=websocket_client_id,
        )
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception(f"[Route] Erreur upload : {e}")
        raise HTTPException(status_code=500, detail="Erreur interne")


@router.post("/match")
async def match_candidates(req: MatchRequest):
    """Phase 7→9 : Recherche vectorielle + Reranking + Analyse IA."""
    try:
        # 1. Recherche vectorielle dans Milvus
        search_results = await cv_service.search_candidates(
            job_description=req.job_description,
            required_skills=req.required_skills,
            top_k=req.top_k * 2,   # sur-sélection pour le reranking
            min_score=req.min_score,
        )

        if not search_results:
            return {
                "success": True,
                "candidates": [],
                "recruiter_advice": "Aucun candidat trouvé pour cette offre.",
            }

        # 2. Reranking via ranking_service (Orange proxy)
        if req.use_reranking:
            ranked = await cv_service.rerank_candidates(
                search_results=search_results,
                job_description=req.job_description,
                required_skills=req.required_skills,
                top_k=req.top_k,
            )
        else:
            ranked = search_results[: req.top_k]

        # 3. Génération de la réponse finale (présentation + conseil recruteur)
        response = await cv_service.generate_response(
            ranked_results=ranked,
            job_description=req.job_description,
            required_skills=req.required_skills,
        )

        return {"success": True, **response}

    except Exception as e:
        logger.exception(f"[Route] Erreur matching : {e}")
        raise HTTPException(status_code=500, detail="Erreur matching")


@router.get("/status/{candidate_id}")
async def get_cv_status(candidate_id: str):
    """Vérifie la présence d'un CV dans Milvus."""
    try:
        status = await cv_service.get_cv_status(candidate_id)
        return {"success": True, "data": status}
    except Exception as e:
        logger.exception(f"[Route] Erreur status : {e}")
        raise HTTPException(status_code=500, detail="Erreur statut")
