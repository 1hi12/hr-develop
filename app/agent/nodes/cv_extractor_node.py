"""
NŒUD LANGGRAPH — cv_extractor_node
Orchestre toute l'extraction CV 
Reçoit le state LangGraph, appelle le pipeline, met à jour le state.
"""

import logging
from typing import Any

from app.agent.tools.cv_extractor.extractor import extract_cv

logger = logging.getLogger(__name__)


async def cv_extractor_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Nœud LangGraph — Extraction CV complète.

    State attendu en entrée :
        file_bytes    (bytes) : contenu binaire du fichier
        filename      (str)   : nom du fichier
        candidate_id  (str)   : identifiant unique candidat

    State retourné :
        cv_extracted      : objet CVExtracted (ou None si erreur)
        extraction_error  : message d'erreur (ou None si succès)
    """
    file_bytes   : bytes = state.get("file_bytes")
    filename     : str   = state.get("filename", "unknown.pdf")
    candidate_id : str   = state.get("candidate_id", "unknown")

    logger.info(f"[Node] cv_extractor_node — candidate_id={candidate_id} | file={filename}")

    if not file_bytes:
        return {
            **state,
            "cv_extracted": None,
            "extraction_error": "file_bytes manquant dans le state LangGraph",
        }

    try:
        cv_extracted = await extract_cv(file_bytes=file_bytes, filename=filename)

        logger.info(
            f"[Node] Extraction réussie — candidate_id={candidate_id} "
            f"| confidence={cv_extracted.extraction_confidence}"
        )

        return {
            **state,
            "cv_extracted":    cv_extracted,
            "extraction_error": None,
        }

    except Exception as e:
        logger.exception(f"[Node] Erreur extraction — candidate_id={candidate_id} : {e}")
        return {
            **state,
            "cv_extracted":    None,
            "extraction_error": str(e),
        }
