"""
email_service.py
================
SMTP email sender — hiring acceptance + LLM-personalised rejection emails.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from jinja2 import Template

from app.config.settings import settings

logger = logging.getLogger(__name__)

_LOGO_PATH = Path(__file__).parent.parent / "static" / "images" / "sofrecom_logo.png"


def _logo_img_tag(width: int = 72) -> str:
    """Return an inline <img> tag for the Sofrecom logo, or empty string if logo not found."""
    if _LOGO_PATH.exists():
        b64 = base64.b64encode(_LOGO_PATH.read_bytes()).decode()
        return (
            f'<img src="data:image/png;base64,{b64}" alt="Sofrecom" '
            f'width="{width}" style="width:{width}px;height:auto;display:block;'
            f'margin:0 auto 8px;opacity:0.85;">'
        )
    return '<p style="font-weight:700;color:#003087;font-size:13px;">SOFRECOM</p>'


# ─────────────────────────────────────────────────────────────────────────────
# Data container
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CandidateEmailData:
    full_name:           str
    email:               str
    seniority_level:     str                  = "unknown"
    total_years_exp:     Optional[float]      = None
    summary:             Optional[str]        = None
    location:            Optional[str]        = None
    phone:               Optional[str]        = None
    linkedin:            Optional[str]        = None
    github:              Optional[str]        = None
    technical_skills:    list[str]            = field(default_factory=list)
    frameworks:          list[str]            = field(default_factory=list)
    soft_skills:         list[str]            = field(default_factory=list)
    languages:           list[str]            = field(default_factory=list)
    experiences:         list[dict]           = field(default_factory=list)
    educations:          list[dict]           = field(default_factory=list)
    job_title:           Optional[str]        = None


# Female first names for gender detection (Arabic/French context)
_FEMALE_NAMES = {
    "hiba","rania","rana","sara","sarah","nour","noura","ines","amira","fatima",
    "yasmine","yassmine","leila","layla","lina","rima","rim","dina","donia","sonia",
    "asma","asmaa","nadia","sirine","syrine","mariem","mariam","maryem","emna","aya",
    "yousra","olfa","afef","amel","chaima","sana","salma","samia","samira","oumaima",
    "meriem","hajer","hajar","khaoula","maroua","mouna","monia","sabrine","sabrina",
    "wafa","wafaa","zaineb","zeineb","zineb","lobna","hela","houda","nada","rahma",
    "roua","safa","sawsen","siham","souha","wiem","wissem","yosra","zahra","fatma",
    "aicha","aisha","khadija","insaf","jihene","imen","ilhem","ilham","feriel","fedwa",
    "dalila","cyrine","chiraz","chirine","besma","aziza","arwa","arij","anissa",
    "angela","alice","alexia","julie","camille","sophie","lucie","claire","celine",
    "sandrine","isabelle","stephanie","caroline","aurelie","emilie","pauline","manon",
    "lea","lena","lisa","laura","laure","nathalie","valerie","virginie",
}

def _civility(full_name: str) -> str:
    first = full_name.strip().split()[0].lower() if full_name.strip() else ""
    norm  = first.replace("é","e").replace("è","e").replace("ê","e")\
                 .replace("â","a").replace("î","i").replace("ô","o")
    return "Madame" if norm in _FEMALE_NAMES else "Monsieur"


# ─────────────────────────────────────────────────────────────────────────────
# Hiring email builder  (no logo — clean text footer)
# ─────────────────────────────────────────────────────────────────────────────

def _build_interview_email(data: CandidateEmailData) -> tuple[str, str]:
    """Returns (subject, html_body) for the acceptance / hiring notification."""

    name     = data.full_name or "Candidat(e)"
    civility = _civility(name)
    job      = data.job_title or "le poste proposé"
    hr_email = "rh@sofrecom.com"
    subject  = "Félicitations — Votre candidature a été retenue | Sofrecom"
    accord   = "e" if civility == "Madame" else ""

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="font-family:'Segoe UI',Arial,sans-serif;color:#1f2937;background:#f3f4f6;margin:0;padding:0;">

  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:40px 0;">
    <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0"
           style="background:#ffffff;border-radius:14px;
                  box-shadow:0 4px 20px rgba(0,0,0,0.08);overflow:hidden;">

      <!-- TOP ACCENT BAR -->
      <tr>
        <td style="background:#003087;height:5px;font-size:0;line-height:0;">&nbsp;</td>
      </tr>

      <!-- BODY -->
      <tr>
        <td style="padding:44px 48px 36px;">

          <!-- Badge -->
          <table width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 28px 0;">
            <tr>
              <td style="background:#eef6ff;border-radius:8px;padding:16px 20px;
                          border-left:4px solid #003087;">
                <p style="margin:0;font-size:13px;font-weight:700;color:#003087;
                            letter-spacing:1px;text-transform:uppercase;">
                  &#127881;&nbsp; Candidature retenue
                </p>
              </td>
            </tr>
          </table>

          <!-- Salutation -->
          <p style="font-size:17px;font-weight:700;color:#111827;margin:0 0 22px 0;
                    line-height:1.4;">
            {civility} <strong>{name}</strong>,
          </p>

          <!-- Main message -->
          <p style="font-size:15px;line-height:1.85;color:#374151;margin:0 0 18px 0;">
            Nous avons le grand plaisir de vous informer que, suite à l'examen attentif de
            votre dossier de candidature, votre profil a été sélectionné pour le poste de
            <strong style="color:#003087;">« {job} »</strong> au sein de <strong>Sofrecom</strong>.
          </p>

          <p style="font-size:15px;line-height:1.85;color:#374151;margin:0 0 18px 0;">
            Votre parcours professionnel a retenu toute notre attention et nous sommes convaincus
            que vous apporterez une contribution précieuse à nos équipes.
          </p>

          <p style="font-size:15px;line-height:1.85;color:#374151;margin:0 0 28px 0;">
            Notre équipe Ressources Humaines prendra contact avec vous dans les
            <strong>prochains jours</strong> afin de vous communiquer toutes les informations
            relatives à votre intégration — date de prise de poste, documents requis et
            modalités pratiques d'accueil.
          </p>

          <hr style="border:none;border-top:1px solid #e5e7eb;margin:0 0 24px 0;">

          <p style="font-size:15px;margin:0 0 4px 0;color:#374151;">
            Encore toutes nos félicitations, {civility} <strong>{name}</strong>.
            Nous nous réjouissons de vous compter parmi nos collaborateur{accord}s.
          </p>

          <p style="font-size:14px;color:#6b7280;margin:16px 0 4px 0;">
            Pour toute question :
            <a href="mailto:{hr_email}" style="color:#003087;text-decoration:none;font-weight:600;">
              {hr_email}
            </a>
          </p>

          <p style="margin:28px 0 0 0;font-size:15px;color:#374151;">Cordialement,</p>
          <p style="margin:4px 0 0 0;font-weight:700;font-size:15px;color:#003087;">
            L'équipe Ressources Humaines
          </p>
          <p style="margin:2px 0 0 0;font-size:13px;color:#6b7280;">
            Sofrecom &mdash; The Know-How Network
          </p>

        </td>
      </tr>

      <!-- FOOTER — text only, no logo -->
      <tr>
        <td style="background:#f8fafc;border-top:1px solid #e5e7eb;padding:18px 48px;text-align:center;">
          <p style="margin:0 0 4px 0;font-size:12px;font-weight:700;color:#6b7280;
                    letter-spacing:0.5px;">
            SOFRECOM &mdash; THE KNOW-HOW NETWORK
          </p>
          <p style="margin:0 0 4px 0;font-size:11px;color:#9ca3af;">
            <a href="mailto:{hr_email}" style="color:#003087;text-decoration:none;">{hr_email}</a>
            &nbsp;|&nbsp;
            <a href="https://www.sofrecom.com" style="color:#003087;text-decoration:none;">www.sofrecom.com</a>
            &nbsp;|&nbsp; Tunis, Tunisie
          </p>
          <p style="margin:10px 0 0 0;font-size:10px;color:#d1d5db;line-height:1.6;">
            Ce message est confidentiel et destiné uniquement à son destinataire.<br>
            Toute divulgation non autorisée est interdite.
          </p>
        </td>
      </tr>

    </table>
    </td></tr>
  </table>

</body>
</html>"""

    return subject, html


# ─────────────────────────────────────────────────────────────────────────────
# SMTP sender — hiring
# ─────────────────────────────────────────────────────────────────────────────

def send_interview_email_sync(data: CandidateEmailData) -> bool:
    if not settings.smtp_host or not settings.smtp_from_email:
        logger.warning("[EmailService] SMTP not configured — skipping email to %s", data.email)
        return False

    subject, html_body = _build_interview_email(data)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Sofrecom RH <{settings.smtp_from_email}>"
    msg["To"]      = data.email
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
        server.ehlo()
        if settings.smtp_use_tls:
            server.starttls(context=context)
            server.ehlo()
        if settings.smtp_user and settings.smtp_password:
            server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(settings.smtp_from_email, data.email, msg.as_string())
    logger.info("[EmailService] Acceptance email sent to %s (%s)", data.full_name, data.email)
    return True


async def send_interview_email(data: CandidateEmailData) -> bool:
    return await asyncio.to_thread(send_interview_email_sync, data)


# ─────────────────────────────────────────────────────────────────────────────
# EmailService class — rejection + other emails
# ─────────────────────────────────────────────────────────────────────────────

_HIRED_TEMPLATE = Path(__file__).parent.parent / "templates" / "email" / "hired_candidate.html"


class EmailService:

    # ── SMTP helper ───────────────────────────────────────────────────────────

    def _smtp_send(self, msg: MIMEMultipart, recipient: str) -> bool:
        if not settings.smtp_host or not settings.smtp_from_email:
            logger.warning("[EmailService] SMTP not configured — skipping email to %s", recipient)
            return False
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.ehlo()
            if settings.smtp_use_tls:
                server.starttls(context=context)
                server.ehlo()
            if settings.smtp_user and settings.smtp_password:
                server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_from_email, recipient, msg.as_string())
        return True

    # ── Legacy hired-candidate template sender ────────────────────────────────

    def _send_hired_sync(
        self,
        candidate_email: str,
        candidate_name: str,
        job_title: str,
        department: str,
        location: str,
        employment_type: str,
        start_date: str,
    ) -> bool:
        with open(_HIRED_TEMPLATE, "r", encoding="utf-8") as f:
            template = Template(f.read())

        html = template.render(
            candidate_name=candidate_name,
            job_title=job_title,
            department=department,
            location=location,
            employment_type=employment_type,
            start_date=start_date,
            hr_email="rh@sofrecom.com",
            hr_phone="+216 XX XXX XXX",
        )

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Félicitations — Offre d'emploi | {candidate_name}"
        msg["From"] = f"Sofrecom RH <{settings.smtp_from_email}>"
        msg["To"] = candidate_email
        msg.attach(MIMEText(html, "html", "utf-8"))

        result = self._smtp_send(msg, candidate_email)
        if result:
            logger.info("[EmailService] Hired email sent to %s (%s)", candidate_name, candidate_email)
        return result

    async def send_hired_candidate_email(
        self,
        candidate_email: str,
        candidate_name: str,
        job_title: str,
        department: str,
        location: str,
        employment_type: str,
        start_date: str,
    ) -> bool:
        return await asyncio.to_thread(
            self._send_hired_sync,
            candidate_email, candidate_name, job_title,
            department, location, employment_type, start_date,
        )

    # ── Test email ────────────────────────────────────────────────────────────

    def _send_test_sync(self, recipient: str) -> bool:
        html = f"""<!DOCTYPE html>
<html><body style="font-family:sans-serif;max-width:600px;margin:auto;padding:20px;">
  <h2 style="color:#0a2472;">Test Email — Sofrecom RH</h2>
  <p>Cet email confirme que la configuration SMTP est opérationnelle.</p>
  <p style="color:#6b7280;font-size:13px;">Sofrecom — The Know-How Network</p>
</body></html>"""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Test Email — Sofrecom HR System"
        msg["From"] = f"Sofrecom RH <{settings.smtp_from_email}>"
        msg["To"] = recipient
        msg.attach(MIMEText(html, "html", "utf-8"))
        return self._smtp_send(msg, recipient)

    async def send_test_email(self, recipient: str) -> bool:
        return await asyncio.to_thread(self._send_test_sync, recipient)

    # ── LLM rejection message generator ──────────────────────────────────────

    @staticmethod
    def _strip_llm_envelope(text: str) -> str:
        """Remove any greeting / signature the LLM accidentally generated."""
        import re as _re

        lines = text.strip().splitlines()

        # Strip leading greeting / subject lines
        _GREETING = ("chère", "cher ", "madame", "monsieur", "objet :", "objet:", "bonjour", "à :")
        while lines and any(lines[0].strip().lower().startswith(m) for m in _GREETING):
            lines.pop(0)

        # Strip trailing signature lines (also catches "[Votre ...]", "[Your ...]" bracket placeholders)
        _SIGN = (
            "cordialement", "[votre", "[your", "votre nom", "responsable rh",
            "responsable ressources", "l'équipe", "sofrecom", "rh senior",
            "bien cordialement", "avec nos cordiales",
        )
        while lines and (
            any(lines[-1].strip().lower().startswith(m) for m in _SIGN)
            or _re.match(r"^\[.+\]", lines[-1].strip())
        ):
            lines.pop()

        # Drop blank boundary lines
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()

        return "\n\n".join(
            "\n".join(chunk).strip()
            for chunk in [lines]
        )

    def _generate_rejection_message(
        self,
        civility: str,
        name: str,
        job_title: str,
        candidate_skills: list[str] | None = None,
        missing_skills: list[str] | None = None,
        seniority_level: str | None = None,
    ) -> str:
        """Call LLM → 2 clean body paragraphs, no greeting, no signature."""
        try:
            if not settings.litellm_api_key:
                raise ValueError("No LLM API key configured")

            import httpx
            from openai import OpenAI
            client = OpenAI(
                api_key=settings.litellm_api_key,
                base_url=settings.litellm_base_url,
                http_client=httpx.Client(verify=False),
            )

            skills_str        = ", ".join(candidate_skills[:8]) if candidate_skills else "diverses compétences techniques"
            missing_str       = ", ".join(missing_skills[:5])   if missing_skills   else "certaines compétences clés"
            seniority_display = seniority_level or "non spécifié"

            prompt = f"""Tu es RH senior chez Sofrecom. Écris UNIQUEMENT 2 paragraphes de corps d'email de refus, en français professionnel.

Contexte :
- Poste : {job_title} | Niveau : {seniority_display}
- Compétences du candidat : {skills_str}
- Compétences manquantes : {missing_str}

Paragraphe 1 (3 lignes max) : Remercie, cite 1-2 compétences fortes du candidat, annonce avec tact que le profil ne correspond pas encore en mentionnant les compétences manquantes.

Paragraphe 2 (3 lignes max) : Donne 2 recommandations précises et actionnables pour combler les lacunes (nomme des formations, certifications ou outils spécifiques).

RÈGLES ABSOLUES — NE PAS VIOLER :
✗ PAS de salutation : ni "Chère/Cher", "Madame/Monsieur", "Objet :", "Bonjour"
✗ PAS de signature : ni "Cordialement", "[Votre nom]", "Responsable", "Sofrecom", "L'équipe RH"
✗ PAS de conclusion sur "vivier de talents" ou "postuler à l'avenir" (géré séparément)
✓ Commence directement par "Nous vous remercions..." ou "Votre dossier..."
✓ Maximum 2 paragraphes, 6 lignes au total"""

            resp = client.chat.completions.create(
                model=settings.litellm_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.6,
            )
            raw = resp.choices[0].message.content.strip()
            return self._strip_llm_envelope(raw)

        except Exception as exc:
            logger.warning("[EmailService] LLM rejection message failed: %s — using fallback", exc)
            missing_hint = ""
            if missing_skills:
                missing_hint = (
                    f" notamment en <strong>{', '.join(missing_skills[:2])}</strong>"
                )
            return (
                f"Nous vous remercions sincèrement du temps consacré à votre candidature "
                f"pour le poste de <strong>{job_title}</strong> et de l'intérêt que vous portez "
                f"à <strong>Sofrecom</strong>. Votre profil technique témoigne de réelles "
                f"compétences, mais il ne correspond pas encore aux exigences actuelles du "
                f"poste{missing_hint}.<br><br>"
                f"Pour renforcer votre candidature, nous vous recommandons de vous orienter "
                f"vers des formations certifiantes dans les domaines identifiés — des plateformes "
                f"comme Coursera, Udemy ou les certifications officielles constituent d'excellents "
                f"points de départ pour acquérir rapidement les compétences recherchées."
            )

    # ── Rejection email HTML builder (shared by send + preview) ──────────────

    def build_rejection_email(
        self,
        candidate_name: str,
        job_title: str,
        candidate_skills: list[str] | None = None,
        missing_skills:   list[str] | None = None,
        seniority_level:  str | None = None,
    ) -> tuple[str, str]:
        """
        Returns (subject, html_body) — medium-length rejection email, no logos.
        Calls the LLM. Use asyncio.to_thread from async context.
        """
        hr_email = "rh@sofrecom.com"
        name     = candidate_name or "Candidat(e)"
        civility = _civility(name)
        subject  = f"Suite à votre candidature — {job_title} | Sofrecom"

        # ── LLM: 2 clean paragraphs, greeting + signature stripped ────────────
        llm_body = self._generate_rejection_message(
            civility, name, job_title, candidate_skills, missing_skills, seniority_level
        )
        p = 'style="font-size:15px;line-height:1.85;color:#374151;margin:0 0 14px 0;"'
        llm_html = llm_body.replace("\n\n", f'</p><p {p}>').replace("\n", "<br>")

        # ── Missing-skills chips (only when data available) ───────────────────
        missing_block = ""
        if missing_skills:
            chips = "".join(
                f'<span style="display:inline-block;background:#fef2f2;color:#b91c1c;'
                f'border:1px solid #fecaca;border-radius:5px;padding:3px 11px;'
                f'font-size:12px;font-weight:600;margin:2px 4px 2px 0;">{s}</span>'
                for s in missing_skills[:6]
            )
            missing_block = f"""
          <table width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 20px 0;">
            <tr>
              <td style="background:#fff7f7;border-radius:8px;border-left:4px solid #ef4444;
                          padding:14px 18px;">
                <p style="margin:0 0 8px 0;font-size:11px;font-weight:700;color:#b91c1c;
                            letter-spacing:0.8px;text-transform:uppercase;">
                  Compétences à renforcer
                </p>
                <div>{chips}</div>
              </td>
            </tr>
          </table>"""

        footer_logo = _logo_img_tag(72)

        html = f"""<!DOCTYPE html>
<html lang="fr">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;color:#1f2937;background:#f3f4f6;margin:0;padding:0;">

  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:32px 0;">
    <tr><td align="center">
    <table width="580" cellpadding="0" cellspacing="0"
           style="background:#ffffff;border-radius:12px;
                  box-shadow:0 2px 12px rgba(0,0,0,0.07);overflow:hidden;">

      <!-- TOP ACCENT — thin bar only, no logo -->
      <tr>
        <td style="background:#003087;height:4px;font-size:0;line-height:0;">&nbsp;</td>
      </tr>

      <!-- BODY -->
      <tr>
        <td style="padding:36px 44px 30px;">

          <!-- Status label -->
          <table width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 24px 0;">
            <tr>
              <td style="background:#f1f5f9;border-radius:6px;padding:12px 18px;
                          border-left:4px solid #64748b;">
                <p style="margin:0;font-size:12px;font-weight:700;color:#475569;
                            letter-spacing:0.8px;text-transform:uppercase;">
                  Suite à votre candidature &mdash; {job_title}
                </p>
              </td>
            </tr>
          </table>

          <!-- Salutation -->
          <p style="font-size:16px;font-weight:700;color:#111827;margin:0 0 18px 0;">
            {civility} <strong>{name}</strong>,
          </p>

          <!-- LLM body (2 paragraphs only) -->
          <p {p}>{llm_html}</p>

          <!-- Missing-skills chips -->
          {missing_block}

          <!-- Encouragement note (compact) -->
          <p style="font-size:14px;line-height:1.75;color:#4b5563;
                    margin:0 0 24px 0;padding:14px 18px;background:#f8fafc;
                    border-radius:6px;border-left:3px solid #003087;">
            Nous conservons votre dossier dans notre vivier de talents et vous
            invitons à consulter nos prochaines offres sur
            <a href="https://www.sofrecom.com"
               style="color:#003087;text-decoration:none;font-weight:600;">www.sofrecom.com</a>.
          </p>

          <hr style="border:none;border-top:1px solid #e5e7eb;margin:0 0 18px 0;">

          <p style="margin:0 0 2px 0;font-size:14px;color:#374151;">Cordialement,</p>
          <p style="margin:0;font-weight:700;font-size:14px;color:#003087;">
            L'équipe Ressources Humaines — Sofrecom
          </p>
          <p style="margin:4px 0 0 0;font-size:12px;color:#9ca3af;">
            <a href="mailto:{hr_email}"
               style="color:#003087;text-decoration:none;">{hr_email}</a>
          </p>

        </td>
      </tr>

      <!-- FOOTER — medium logo + contact -->
      <tr>
        <td style="background:#f8fafc;border-top:1px solid #e5e7eb;
                    padding:16px 44px;text-align:center;">
          {footer_logo}
          <p style="margin:0 0 3px 0;font-size:11px;font-weight:700;color:#6b7280;
                    letter-spacing:0.6px;text-transform:uppercase;">
            Sofrecom &mdash; The Know-How Network
          </p>
          <p style="margin:0 0 8px 0;font-size:11px;color:#9ca3af;">
            <a href="mailto:{hr_email}"
               style="color:#003087;text-decoration:none;">{hr_email}</a>
            &nbsp;|&nbsp;
            <a href="https://www.sofrecom.com"
               style="color:#9ca3af;text-decoration:none;">www.sofrecom.com</a>
          </p>
          <p style="margin:0;font-size:10px;color:#d1d5db;line-height:1.5;">
            Ce message est confidentiel et destiné uniquement à son destinataire.
          </p>
        </td>
      </tr>

    </table>
    </td></tr>
  </table>

</body>
</html>"""

        return subject, html

    # ── Rejection SMTP sender ─────────────────────────────────────────────────

    def _send_rejection_sync(
        self,
        candidate_email:  str,
        candidate_name:   str,
        job_title:        str,
        candidate_skills: list[str] | None = None,
        missing_skills:   list[str] | None = None,
        seniority_level:  str | None = None,
    ) -> bool:
        subject, html = self.build_rejection_email(
            candidate_name, job_title, candidate_skills, missing_skills, seniority_level
        )
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"Sofrecom RH <{settings.smtp_from_email}>"
        msg["To"]      = candidate_email
        msg.attach(MIMEText(html, "html", "utf-8"))

        result = self._smtp_send(msg, candidate_email)
        if result:
            logger.info(
                "[EmailService] Rejection email sent to %s (%s) for job '%s'",
                candidate_name, candidate_email, job_title,
            )
        return result

    async def send_rejection_email(
        self,
        candidate_email:  str,
        candidate_name:   str,
        job_title:        str,
        candidate_skills: list[str] | None = None,
        missing_skills:   list[str] | None = None,
        seniority_level:  str | None = None,
    ) -> bool:
        return await asyncio.to_thread(
            self._send_rejection_sync,
            candidate_email, candidate_name, job_title,
            candidate_skills, missing_skills, seniority_level,
        )


def get_email_service() -> EmailService:
    return EmailService()
