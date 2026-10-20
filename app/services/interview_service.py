"""
interview_service.py
====================
Interview scheduling service with SofSalle-ready adapter pattern.

Architecture: LocalRoomProvider (active) → swap to SofSalleProvider
when API access is granted. No frontend changes needed.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config.settings import settings
from app.infrastructure.database.models import InterviewModel, RoomModel, CandidateModel, JobPostingModel

logger = logging.getLogger(__name__)

PLATFORM_LABELS = {"teams": "Microsoft Teams", "meet": "Google Meet", "zoom": "Zoom"}
DURATION_LABELS  = {30: "30 min", 45: "45 min", 60: "1 heure"}


# ─────────────────────────────────────────────────────────────────────────────
# Domain DTOs
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RoomInfo:
    room_id:   str
    name:      str
    floor:     Optional[str]
    building:  Optional[str]
    capacity:  int
    equipment: list[str]
    available: bool = True


@dataclass
class ScheduleInterviewRequest:
    candidate_id:    str
    job_posting_id:  Optional[str]
    interview_date:  str          # YYYY-MM-DD
    interview_time:  str          # HH:MM
    duration_min:    int
    format:          str          # "online" | "onsite"
    platform:        Optional[str] = None
    meeting_link:    Optional[str] = None
    room_id:         Optional[str] = None
    interviewer_name: Optional[str] = None
    notes:           Optional[str] = None
    candidate_email: Optional[str] = None
    candidate_name:  Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Room provider abstraction
# ─────────────────────────────────────────────────────────────────────────────

class RoomProvider(ABC):
    @abstractmethod
    async def get_available(
        self, date: str, time: str, duration_min: int, db: AsyncSession
    ) -> list[RoomInfo]: ...

    @abstractmethod
    async def book(
        self, room_id: str, date: str, time: str, duration_min: int, db: AsyncSession
    ) -> bool: ...


def _parse_equipment(val) -> list[str]:
    import json as _json
    if isinstance(val, list):
        return [str(x) for x in val]
    if isinstance(val, str):
        try:
            parsed = _json.loads(val)
            return [str(x) for x in parsed] if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


class LocalRoomProvider(RoomProvider):
    async def get_available(
        self, date: str, time: str, duration_min: int, db: AsyncSession
    ) -> list[RoomInfo]:
        result = await db.execute(select(RoomModel).where(RoomModel.is_active == True))
        rooms  = result.scalars().all()

        try:
            start_dt = datetime.fromisoformat(f"{date}T{time}")
            end_dt   = start_dt + timedelta(minutes=duration_min)
        except ValueError:
            return []

        infos: list[RoomInfo] = []
        for room in rooms:
            bookings_res = await db.execute(
                select(InterviewModel).where(
                    InterviewModel.room_id == room.room_id,
                    InterviewModel.interview_date == date,
                    InterviewModel.status != "cancelled",
                )
            )
            overlaps = bookings_res.scalars().all()

            conflict = False
            for iv in overlaps:
                try:
                    iv_start = datetime.fromisoformat(f"{iv.interview_date}T{iv.interview_time}")
                    iv_end   = iv_start + timedelta(minutes=iv.duration_min)
                    if not (end_dt <= iv_start or start_dt >= iv_end):
                        conflict = True
                        break
                except ValueError:
                    continue

            infos.append(
                RoomInfo(
                    room_id=room.room_id, name=room.name,
                    floor=room.floor, building=room.building,
                    capacity=room.capacity, equipment=_parse_equipment(room.equipment),
                    available=not conflict,
                )
            )
        return infos

    async def book(
        self, room_id: str, date: str, time: str, duration_min: int, db: AsyncSession
    ) -> bool:
        result = await db.execute(select(RoomModel).where(RoomModel.room_id == room_id))
        room   = result.scalar_one_or_none()
        return room is not None and room.is_active


class SofSalleProvider(RoomProvider):
    """
    Plug-in stub — fill in SofSalle API credentials when ready.
    Replace the two methods; zero frontend changes required.
    """
    async def get_available(self, date, time, duration_min, db) -> list[RoomInfo]:
        raise NotImplementedError("SofSalle API not configured yet")

    async def book(self, room_id, date, time, duration_min, db) -> bool:
        raise NotImplementedError("SofSalle API not configured yet")


# ─────────────────────────────────────────────────────────────────────────────
# Interview service
# ─────────────────────────────────────────────────────────────────────────────

class InterviewService:
    def __init__(self, room_provider: RoomProvider | None = None):
        self.rooms = room_provider or LocalRoomProvider()

    async def get_available_rooms(
        self, date: str, time: str, duration_min: int, db: AsyncSession
    ) -> list[RoomInfo]:
        return await self.rooms.get_available(date, time, duration_min, db)

    async def schedule(
        self, req: ScheduleInterviewRequest, db: AsyncSession
    ) -> InterviewModel:
        # Check for existing scheduled interview for this candidate on the same date
        existing = (await db.execute(
            select(InterviewModel)
            .where(InterviewModel.candidate_id == req.candidate_id)
            .where(InterviewModel.interview_date == req.interview_date)
            .where(InterviewModel.status == "scheduled")
        )).scalar_one_or_none()
        if existing:
            raise ValueError(
                f"Ce candidat a déjà un entretien planifié le {req.interview_date} à {existing.interview_time}."
            )

        if req.format == "onsite" and req.room_id:
            await self.rooms.book(
                req.room_id, req.interview_date, req.interview_time, req.duration_min, db
            )

        # Fetch candidate from DB to get email/name if not provided
        candidate_email = req.candidate_email
        candidate_name  = req.candidate_name
        if not candidate_email or not candidate_name:
            res = await db.execute(
                select(CandidateModel).where(CandidateModel.candidate_id == req.candidate_id)
            )
            cand = res.scalar_one_or_none()
            if cand:
                candidate_email = candidate_email or cand.email
                candidate_name  = candidate_name  or cand.full_name

        interview = InterviewModel(
            interview_id=str(uuid.uuid4()),
            candidate_id=req.candidate_id,
            job_posting_id=req.job_posting_id,
            interview_date=req.interview_date,
            interview_time=req.interview_time,
            duration_min=req.duration_min,
            format=req.format,
            platform=req.platform,
            meeting_link=req.meeting_link,
            room_id=req.room_id if req.format == "onsite" else None,
            interviewer_name=req.interviewer_name,
            notes=req.notes,
            status="scheduled",
            email_sent=False,
            reminder_sent=False,
        )
        db.add(interview)
        await db.commit()
        await db.refresh(interview)

        if candidate_email and candidate_name:
            room_name: Optional[str] = None
            if req.format == "onsite" and req.room_id:
                res  = await db.execute(select(RoomModel).where(RoomModel.room_id == req.room_id))
                room = res.scalar_one_or_none()
                room_name = room.name if room else None

            job_title: Optional[str] = None
            if req.job_posting_id:
                res = await db.execute(
                    select(JobPostingModel).where(JobPostingModel.job_id == req.job_posting_id)
                )
                posting = res.scalar_one_or_none()
                if posting:
                    job_title = posting.title

            logger.info(
                "[InterviewService] Sending interview email to %s (%s) for post: %s",
                candidate_name, candidate_email, job_title,
            )
            try:
                ok = await asyncio.to_thread(
                    _send_email_sync,
                    candidate_email,
                    candidate_name,
                    req.interview_date,
                    req.interview_time,
                    req.duration_min,
                    req.format,
                    req.platform,
                    req.meeting_link,
                    room_name,
                    False,
                    job_title,
                )
                if ok:
                    interview.email_sent = True
                    await db.commit()
                    logger.info("[InterviewService] Email sent successfully to %s", candidate_email)
                else:
                    logger.warning("[InterviewService] Email NOT sent to %s (SMTP returned False)", candidate_email)
            except Exception as exc:
                logger.error("[InterviewService] Email send error for %s: %s", candidate_email, exc)
        else:
            logger.warning(
                "[InterviewService] No email sent — candidate_email=%r candidate_name=%r",
                candidate_email, candidate_name,
            )

        return interview

    async def cancel(self, interview_id: str, db: AsyncSession) -> bool:
        res = await db.execute(
            select(InterviewModel).where(InterviewModel.interview_id == interview_id)
        )
        iv = res.scalar_one_or_none()
        if not iv:
            return False
        iv.status = "cancelled"
        await db.commit()
        return True

    async def send_reminders(self, db: AsyncSession) -> int:
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        res = await db.execute(
            select(InterviewModel)
            .options(selectinload(InterviewModel.candidate), selectinload(InterviewModel.room))
            .where(
                InterviewModel.interview_date == tomorrow,
                InterviewModel.status == "scheduled",
                InterviewModel.reminder_sent == False,
            )
        )
        pending = res.scalars().all()

        sent = 0
        for iv in pending:
            if not (iv.candidate and iv.candidate.email):
                continue
            room_name = iv.room.name if iv.room else None
            ok = await asyncio.to_thread(
                _send_email_sync,
                iv.candidate.email,
                iv.candidate.full_name or "Candidat(e)",
                iv.interview_date, iv.interview_time, iv.duration_min,
                iv.format, iv.platform, iv.meeting_link, room_name, True,
            )
            if ok:
                iv.reminder_sent = True
                sent += 1

        await db.commit()
        return sent


# ─────────────────────────────────────────────────────────────────────────────
# Email helpers
# ─────────────────────────────────────────────────────────────────────────────

_FR_DAYS   = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
_FR_MONTHS = ["janvier","février","mars","avril","mai","juin",
              "juillet","août","septembre","octobre","novembre","décembre"]

# Common female first names (Arabic/French context)
_FEMALE_NAMES = {
    "hiba","rania","rana","sara","sarah","nour","noura","ines","amira","fatima",
    "yasmine","yassmine","leila","layla","lina","rima","rim","dina","donia","sonia",
    "sonya","asma","asmaa","nadia","nadya","sirine","syrine","mariem","mariam","maryem",
    "mary","marie","emna","emne","aya","yousra","yousra","olfa","afef","amel","amira",
    "chaima","chaïma","sana","salma","samia","samira","oumaima","meriem","meriam",
    "hajer","hajar","khaoula","maroua","maroua","mouna","monia","sabrine","sabrina",
    "wafa","wafaa","zaineb","zeineb","zineb","lobna","lobna","hela","hella","houda",
    "nada","nahed","nahla","najwa","nihed","rahma","rajaa","randa","rawia","roua",
    "rowaida","rouaa","safa","safaa","sawsen","siham","souha","souheir","wiem","wissem",
    "yosra","zahra","zakia","zina","fatma","fatouma","aicha","aisha","khadija","kalthoum",
    "insaf","jihene","jihen","imen","ilhem","ilham","feriel","fedwa","dalila","cyrine",
    "chiraz","chirine","besma","bechira","azouz","aziza","arwa","arij","anissa","anies",
    "angela","alice","alexia","julie","camille","sophie","lucie","claire","celine",
    "sandrine","isabelle","stephanie","caroline","aurelie","emilie","pauline","manon",
    "lea","lena","lisa","laura","laure","alice","alice","nathalie","valerie","virginie",
}

def _detect_civility(full_name: str) -> str:
    """Return 'Madame' or 'Monsieur' based on the first name."""
    first = full_name.strip().split()[0].lower() if full_name.strip() else ""
    # strip accents for comparison
    normalized = first.replace("é","e").replace("è","e").replace("ê","e")\
                      .replace("â","a").replace("î","i").replace("ô","o")
    return "Madame" if normalized in _FEMALE_NAMES else "Monsieur"

def _fmt_date(d: str) -> str:
    try:
        dt = datetime.fromisoformat(d)
        day_name  = _FR_DAYS[dt.weekday()]
        month_name = _FR_MONTHS[dt.month - 1]
        return f"{day_name} {dt.day} {month_name} {dt.year}"
    except Exception:
        return d


def _build_email_html(
    candidate_name: str,
    interview_date: str,
    interview_time: str,
    duration_min: int,
    fmt: str,
    platform: Optional[str],
    meeting_link: Optional[str],
    room_name: Optional[str],
    is_reminder: bool = False,
    job_title: Optional[str] = None,
) -> tuple[str, str]:
    hr_email  = "rh@sofrecom.com"
    hr_phone  = "+216 71 860 860"
    name      = candidate_name or "Candidat(e)"
    civility  = _detect_civility(name)
    date_fmt  = _fmt_date(interview_date)
    dur_lbl   = DURATION_LABELS.get(duration_min, f"{duration_min} min")
    post_line = f" pour le poste de <strong>{job_title}</strong>" if job_title else ""

    prefix  = "Rappel : " if is_reminder else ""
    subject = f"{prefix}Convocation à un entretien de recrutement — {date_fmt} | Sofrecom"

    # Format block
    if fmt == "online":
        plat_label = PLATFORM_LABELS.get(platform or "", platform or "Visioconférence")
        format_detail = f"En ligne via <strong>{plat_label}</strong>"
        format_icon   = "&#127760;"
        location_row  = f"""
        <tr>
          <td style="padding:14px 20px;border-bottom:1px solid #e8ecf0;">
            <table cellpadding="0" cellspacing="0"><tr>
              <td style="width:36px;vertical-align:top;padding-top:2px;font-size:20px;">&#128279;</td>
              <td>
                <div style="font-size:11px;color:#8492a6;text-transform:uppercase;letter-spacing:0.8px;font-weight:600;margin-bottom:3px;">Lien de connexion</div>
                <div style="font-size:14px;color:#003087;font-weight:600;">
                  {"<a href='" + meeting_link + "' style='color:#003087;text-decoration:underline;word-break:break-all;'>" + meeting_link + "</a>" if meeting_link else "Lien communiqué séparément"}
                </div>
              </td>
            </tr></table>
          </td>
        </tr>""" if meeting_link else ""
    else:
        plat_label    = ""
        format_detail = f"Présentiel — <strong>Siège Sofrecom</strong>"
        format_icon   = "&#127970;"
        location_row  = f"""
        <tr>
          <td style="padding:14px 20px;border-bottom:1px solid #e8ecf0;">
            <table cellpadding="0" cellspacing="0"><tr>
              <td style="width:36px;vertical-align:top;padding-top:2px;font-size:20px;">&#128205;</td>
              <td>
                <div style="font-size:11px;color:#8492a6;text-transform:uppercase;letter-spacing:0.8px;font-weight:600;margin-bottom:3px;">Salle réservée</div>
                <div style="font-size:15px;color:#1a202c;font-weight:700;">{room_name or "À confirmer"}</div>
                <div style="font-size:12px;color:#8492a6;margin-top:2px;">Sofrecom — Tunis, Tunisie</div>
              </td>
            </tr></table>
          </td>
        </tr>"""

    reminder_banner = """
      <tr><td style="background:#fffbeb;border:1px solid #fcd34d;border-radius:8px;padding:14px 20px;margin-bottom:24px;display:block;">
        <p style="margin:0;font-size:14px;color:#92400e;font-weight:600;">
          &#9200; Rappel — Votre entretien a lieu <u>demain</u>. Veuillez confirmer votre présence.
        </p>
      </td></tr>
      <tr><td style="height:20px;"></td></tr>
    """ if is_reminder else ""

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Convocation entretien — Sofrecom</title>
</head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:'Segoe UI',Helvetica,Arial,sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f5;padding:40px 0;">
<tr><td align="center">

  <!-- Card -->
  <table width="600" cellpadding="0" cellspacing="0"
         style="background:#ffffff;border-radius:16px;
                box-shadow:0 4px 24px rgba(0,0,0,0.10);overflow:hidden;">

    <!-- ── TOP ACCENT BAR ── -->
    <tr>
      <td style="background:linear-gradient(90deg,#003087 0%,#1e5fd8 60%,#0ea5e9 100%);
                 height:5px;font-size:0;line-height:0;">&nbsp;</td>
    </tr>

    <!-- ── HEADER ── -->
    <tr>
      <td style="padding:36px 48px 28px;border-bottom:1px solid #edf2f7;">
        <table width="100%" cellpadding="0" cellspacing="0"><tr>
          <td>
            <p style="margin:0 0 6px;font-size:11px;color:#8492a6;text-transform:uppercase;
                      letter-spacing:1.2px;font-weight:600;">Direction des Ressources Humaines</p>
            <h1 style="margin:0;font-size:22px;font-weight:700;color:#003087;line-height:1.3;">
              {"&#128276; Rappel — " if is_reminder else ""}Convocation à un entretien<br>
              <span style="font-size:16px;font-weight:400;color:#4a5568;">de recrutement</span>
            </h1>
          </td>
        </tr></table>
      </td>
    </tr>

    <!-- ── BODY ── -->
    <tr>
      <td style="padding:32px 48px;">

        <table width="100%" cellpadding="0" cellspacing="0">
          {reminder_banner}
        </table>

        <p style="margin:0 0 8px;font-size:15px;color:#4a5568;">{civility},</p>
        <p style="margin:0 0 24px;font-size:22px;font-weight:700;color:#1a202c;">{name},</p>

        <p style="margin:0 0 16px;font-size:15px;line-height:1.8;color:#4a5568;">
          Nous avons étudié votre candidature avec attention et avons le plaisir de vous informer
          que votre profil a retenu toute notre attention{post_line}.
        </p>
        <p style="margin:0 0 28px;font-size:15px;line-height:1.8;color:#4a5568;">
          Dans ce cadre, nous vous prions de bien vouloir vous présenter à un
          <strong style="color:#003087;">entretien de recrutement</strong>
          dont les modalités sont précisées ci-dessous :
        </p>

        <!-- ── DETAILS CARD ── -->
        <table width="100%" cellpadding="0" cellspacing="0"
               style="border:1px solid #e8ecf0;border-radius:12px;overflow:hidden;margin-bottom:28px;">

          <!-- Date -->
          <tr>
            <td style="padding:16px 20px;border-bottom:1px solid #e8ecf0;background:#f8fafc;">
              <table cellpadding="0" cellspacing="0"><tr>
                <td style="width:36px;vertical-align:top;padding-top:2px;font-size:22px;">&#128197;</td>
                <td>
                  <div style="font-size:11px;color:#8492a6;text-transform:uppercase;letter-spacing:0.8px;font-weight:600;margin-bottom:3px;">Date</div>
                  <div style="font-size:16px;color:#1a202c;font-weight:700;">{date_fmt}</div>
                </td>
              </tr></table>
            </td>
          </tr>

          <!-- Heure -->
          <tr>
            <td style="padding:16px 20px;border-bottom:1px solid #e8ecf0;">
              <table cellpadding="0" cellspacing="0"><tr>
                <td style="width:36px;vertical-align:top;padding-top:2px;font-size:22px;">&#128336;</td>
                <td>
                  <div style="font-size:11px;color:#8492a6;text-transform:uppercase;letter-spacing:0.8px;font-weight:600;margin-bottom:3px;">Heure &amp; Durée</div>
                  <div style="font-size:16px;color:#1a202c;font-weight:700;">{interview_time} &nbsp;<span style="font-size:13px;color:#8492a6;font-weight:400;">({dur_lbl})</span></div>
                </td>
              </tr></table>
            </td>
          </tr>

          <!-- Format -->
          <tr>
            <td style="padding:16px 20px;border-bottom:1px solid #e8ecf0;background:#f8fafc;">
              <table cellpadding="0" cellspacing="0"><tr>
                <td style="width:36px;vertical-align:top;padding-top:2px;font-size:22px;">{format_icon}</td>
                <td>
                  <div style="font-size:11px;color:#8492a6;text-transform:uppercase;letter-spacing:0.8px;font-weight:600;margin-bottom:3px;">Format</div>
                  <div style="font-size:15px;color:#1a202c;">{format_detail}</div>
                </td>
              </tr></table>
            </td>
          </tr>

          {location_row}

        </table>

        <!-- ── CHECKLIST ── -->
        <table width="100%" cellpadding="0" cellspacing="0"
               style="background:#eef2ff;border-radius:10px;padding:0;margin-bottom:28px;">
          <tr><td style="padding:20px 24px;">
            <p style="margin:0 0 12px;font-size:13px;font-weight:700;color:#3730a3;
                      text-transform:uppercase;letter-spacing:0.8px;">À prévoir pour l'entretien</p>
            <p style="margin:0 0 6px;font-size:14px;color:#3730a3;">
              &#10003;&nbsp; Une pièce d'identité valide
            </p>
            <p style="margin:0 0 6px;font-size:14px;color:#3730a3;">
              &#10003;&nbsp; Un exemplaire de votre CV à jour
            </p>
            <p style="margin:0;font-size:14px;color:#3730a3;">
              &#10003;&nbsp; Vos diplômes et attestations de travail (si disponibles)
            </p>
          </td></tr>
        </table>

        <p style="margin:0 0 8px;font-size:15px;line-height:1.8;color:#4a5568;">
          En cas d'empêchement ou pour toute question, nous vous remercions de nous contacter
          dans les meilleurs délais :
        </p>
        <p style="margin:0 0 28px;font-size:14px;color:#4a5568;">
          &#9993;&nbsp;
          <a href="mailto:{hr_email}" style="color:#003087;font-weight:600;text-decoration:none;">{hr_email}</a>
          &nbsp;&nbsp;&#9742;&nbsp; <strong>{hr_phone}</strong>
        </p>

        <p style="margin:0 0 4px;font-size:15px;color:#4a5568;">
          Dans l'attente de vous rencontrer, nous vous adressons nos cordiales salutations.
        </p>
        <p style="margin:0 0 4px;font-size:15px;font-weight:700;color:#003087;">L'équipe Recrutement</p>
        <p style="margin:0;font-size:13px;color:#8492a6;">Direction des Ressources Humaines — Sofrecom</p>

      </td>
    </tr>

    <!-- ── FOOTER ── -->
    <tr>
      <td style="background:#f8fafc;border-top:1px solid #edf2f7;padding:24px 48px;">
        <table width="100%" cellpadding="0" cellspacing="0"><tr>
          <td style="text-align:center;">
            <p style="margin:0 0 4px;font-size:11px;font-weight:700;color:#8492a6;
                      letter-spacing:1px;text-transform:uppercase;">Sofrecom — The Know-How Network</p>
            <p style="margin:0;font-size:11px;color:#b0bac6;">
              <a href="mailto:{hr_email}" style="color:#8492a6;text-decoration:none;">{hr_email}</a>
              &nbsp;·&nbsp;
              <a href="https://www.sofrecom.com" style="color:#8492a6;text-decoration:none;">www.sofrecom.com</a>
              &nbsp;·&nbsp; Tunis, Tunisie
            </p>
            <p style="margin:10px 0 0;font-size:10px;color:#c8d0da;line-height:1.6;">
              Ce message est confidentiel et destiné uniquement à son destinataire.
            </p>
          </td>
        </tr></table>
      </td>
    </tr>

    <!-- ── BOTTOM ACCENT BAR ── -->
    <tr>
      <td style="background:linear-gradient(90deg,#003087 0%,#1e5fd8 60%,#0ea5e9 100%);
                 height:3px;font-size:0;line-height:0;">&nbsp;</td>
    </tr>

  </table>

</td></tr>
</table>
</body></html>"""

    return subject, html


def _smtp_send_msg(msg: MIMEMultipart, recipient: str) -> bool:
    if not settings.smtp_host or not settings.smtp_from_email:
        logger.warning("[InterviewService] SMTP not configured — skip %s", recipient)
        return False
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as srv:
            srv.ehlo()
            if settings.smtp_use_tls:
                srv.starttls(context=ctx)
                srv.ehlo()
            if settings.smtp_user and settings.smtp_password:
                srv.login(settings.smtp_user, settings.smtp_password)
            srv.sendmail(settings.smtp_from_email, recipient, msg.as_string())
        logger.info("[InterviewService] SMTP sendmail OK → %s", recipient)
        return True
    except Exception as exc:
        logger.error("[InterviewService] SMTP error for %s: %s", recipient, exc)
        return False


def _send_email_sync(
    candidate_email: str,
    candidate_name:  str,
    interview_date:  str,
    interview_time:  str,
    duration_min:    int,
    fmt:             str,
    platform:        Optional[str],
    meeting_link:    Optional[str],
    room_name:       Optional[str],
    is_reminder:     bool = False,
    job_title:       Optional[str] = None,
) -> bool:
    subject, html = _build_email_html(
        candidate_name, interview_date, interview_time,
        duration_min, fmt, platform, meeting_link, room_name, is_reminder, job_title,
    )
    outer = MIMEMultipart("alternative")
    outer["Subject"] = subject
    outer["From"]    = f"Sofrecom RH <{settings.smtp_from_email}>"
    outer["To"]      = candidate_email
    outer.attach(MIMEText(html, "html", "utf-8"))

    ok = _smtp_send_msg(outer, candidate_email)
    if ok:
        logger.info("[InterviewService] %s → %s", "Reminder" if is_reminder else "Confirmation", candidate_email)
    return ok




# Singleton — shared across the app
interview_service = InterviewService()
