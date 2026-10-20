"""
/api/v1/emails — Email notification endpoints for candidates.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.infrastructure.database.models import CandidateModel, JobPostingModel
from app.infrastructure.database.session import AsyncSessionLocal
from app.services.email_service import get_email_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/emails", tags=["Emails"])


# ── Request schemas ───────────────────────────────────────────────────────────


class SendHiredEmailRequest(BaseModel):
    """Request to send hired candidate email."""

    candidate_id: str
    job_id: Optional[str] = None
    custom_message: Optional[str] = None
    start_date: Optional[str] = "À définir"


class TestEmailRequest(BaseModel):
    """Request to send test email."""

    recipient_email: str


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/send-hired-notification")
async def send_hired_notification(req: SendHiredEmailRequest):
    """
    Send professional congratulations email to a hired candidate.

    This endpoint:
    - Fetches candidate details from database
    - Optionally fetches job details if job_id is provided
    - Sends a professional HTML email with Sofrecom branding
    - Does NOT include candidate competencies/skills in the email
    - Updates candidate status to 'hired' if not already set

    Args:
        req: Request containing candidate_id and optional job_id

    Returns:
        Success message with email details
    """
    # Fetch candidate
    async with AsyncSessionLocal() as session:
        async with session.begin():
            candidate = await session.get(CandidateModel, req.candidate_id)
            if not candidate:
                raise HTTPException(
                    status_code=404, detail=f"Candidate {req.candidate_id} not found"
                )

            # Validate email exists
            if not candidate.email:
                raise HTTPException(
                    status_code=400,
                    detail=f"Candidate {candidate.full_name or req.candidate_id} has no email address",
                )

            # Fetch job details if provided
            job: Optional[JobPostingModel] = None
            if req.job_id:
                job = await session.get(JobPostingModel, req.job_id)
                if not job:
                    logger.warning(f"Job {req.job_id} not found, using default values")

            # Update candidate status to hired
            if candidate.status != "hired":
                candidate.status = "hired"
                logger.info(f"Updated candidate {candidate.candidate_id} status to 'hired'")

    # Prepare email data
    candidate_name = candidate.full_name or "Candidat(e)"
    job_title = job.title if job else "Nouveau poste"
    department = job.department if job else "Engineering"
    location = job.location if job else "Tunis, Tunisie"
    employment_type = job.employment_type.upper() if job else "CDI - Temps plein"

    # Send email
    email_service = get_email_service()
    try:
        success = await email_service.send_hired_candidate_email(
            candidate_email=candidate.email,
            candidate_name=candidate_name,
            job_title=job_title,
            department=department,
            location=location,
            employment_type=employment_type,
            start_date=req.start_date,
        )

        if not success:
            raise HTTPException(
                status_code=500, detail="Failed to send email. Check server logs."
            )

        logger.info(
            f"Hired notification sent to {candidate.email} ({candidate_name}) for {job_title}"
        )

        return {
            "status": "success",
            "message": f"Email de félicitations envoyé à {candidate_name}",
            "recipient": candidate.email,
            "job_title": job_title,
            "candidate_id": req.candidate_id,
            "job_id": req.job_id,
        }

    except Exception as e:
        logger.error(f"Failed to send hired email: {e}")
        raise HTTPException(
            status_code=500, detail=f"Erreur lors de l'envoi de l'email: {str(e)}"
        )


@router.post("/send-test-email")
async def send_test_email(req: TestEmailRequest):
    """
    Send a test email to verify email configuration.

    Args:
        req: Request containing recipient email address

    Returns:
        Success message
    """
    email_service = get_email_service()

    try:
        success = await email_service.send_test_email(req.recipient_email)

        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to send test email. Check SMTP configuration.",
            )

        return {
            "status": "success",
            "message": f"Email de test envoyé à {req.recipient_email}",
            "recipient": req.recipient_email,
        }

    except Exception as e:
        logger.error(f"Failed to send test email: {e}")
        raise HTTPException(
            status_code=500, detail=f"Erreur lors de l'envoi de l'email de test: {str(e)}"
        )


@router.get("/preview-template")
async def preview_template():
    """
    Generate a preview of the hired candidate email template.

    Returns:
        HTML preview of the email template
    """
    from pathlib import Path
    from jinja2 import Template

    templates_dir = Path(__file__).parent.parent.parent.parent / "templates" / "email"
    template_path = templates_dir / "hired_candidate.html"

    if not template_path.exists():
        raise HTTPException(status_code=404, detail="Template not found")

    with open(template_path, "r", encoding="utf-8") as f:
        template_content = f.read()

    # Render with sample data
    template = Template(template_content)
    html = template.render(
        candidate_name="Jean Dupont",
        job_title="Ingénieur Logiciel Senior",
        department="Engineering",
        location="Tunis, Tunisie",
        employment_type="CDI - Temps plein",
        start_date="01 Juin 2026",
        hr_email="rh@sofrecom.com",
        hr_phone="+216 XX XXX XXX",
    )

    from fastapi.responses import HTMLResponse

    return HTMLResponse(content=html)
