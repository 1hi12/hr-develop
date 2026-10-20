"""
/api/v1/dashboard — HR dashboard endpoints.

Frontend API contract:
    GET /dashboard            → active_candidates, CVs Screened, Hired, Avg Days, charts, departments
    GET /dashboard/stats      → activeCandidates, cvsScreened, hiredCandidates, avgDaysToHire
    GET /dashboard/departments → [{name, value}]
    GET /dashboard/trends     → [{label, value}]
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from sqlalchemy import Date, cast, func, select

from app.infrastructure.database.models import CandidateModel, CVFileModel, JobPostingModel, InterviewModel
from app.infrastructure.database.session import AsyncSessionLocal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


# ── Department classifier (keyword-based) ────────────────────────────────────

def _classify_department(department: str | None, title: str | None) -> str:
    """Return department. Use stored value if set, otherwise derive from job title."""
    if department and department.strip():
        return department.strip()
    t = (title or "").lower()
    if any(k in t for k in ["devops", "sre", "cloud", "infra", "platform", "ops",
                              "kubernetes", "docker", "terraform", "ansible"]):
        return "IT"
    if any(k in t for k in ["data scien", "machine learning", "deep learning",
                              "nlp", " ia", " ai ", "artificial intelligence"]):
        return "Data Science"
    if any(k in t for k in ["data engineer", "data analyst", "analytics",
                              " bi ", "etl", "business intel", "data pipeline"]):
        return "Data Engineering"
    if any(k in t for k in ["security", "sécurité", "cybersec",
                              "pentest", "soc ", "cyber"]):
        return "Cybersécurité"
    if any(k in t for k in ["frontend", "react", "vue", "angular",
                              "ui ", "ux ", "web designer"]):
        return "Frontend"
    if any(k in t for k in ["backend", " api", "django", "fastapi",
                              "spring", "node", "php", "golang"]):
        return "Backend"
    if any(k in t for k in ["fullstack", "full stack", "full-stack"]):
        return "Fullstack"
    if any(k in t for k in ["mobile", "ios", "android",
                              "flutter", "react native", "swift"]):
        return "Mobile"
    if any(k in t for k in ["rh", "ressources humaines", "recrutement",
                              "hr ", "talent", "paie", "people ops"]):
        return "RH"
    if any(k in t for k in ["product manager", "chef de projet",
                              "scrum", "agile", " po ", " pm "]):
        return "Product / Projet"
    if any(k in t for k in ["qa", "quality assurance", "test engineer", "qualité"]):
        return "QA / Testing"
    if any(k in t for k in ["software", "developer", "développeur",
                              "engineer", "architect", "ingénieur"]):
        return "IT"
    return "Autre"


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _fetch_stats() -> dict:
    """Core stats shared by /dashboard and /dashboard/stats."""
    async with AsyncSessionLocal() as session:

        # active candidates = all candidates in DB
        active_candidates = await session.scalar(
            select(func.count()).select_from(CandidateModel)
        ) or 0

        # CVs screened = cv_files with status done
        cvs_screened = await session.scalar(
            select(func.count()).select_from(CVFileModel)
            .where(CVFileModel.processing_status == "done")
        ) or 0

        # hired = candidates with status='hired'
        hired_candidates = await session.scalar(
            select(func.count()).select_from(CandidateModel)
            .where(CandidateModel.status == "hired")
        ) or 0

        # avg days to hire: average days from candidate creation to hired status change
        avg_days_result = await session.scalar(
            select(
                func.avg(
                    func.extract(
                        "epoch",
                        CandidateModel.updated_at - CandidateModel.created_at
                    ) / 86400.0
                )
            ).where(CandidateModel.status == "hired")
        )
        avg_days_to_hire = round(float(avg_days_result), 1) if avg_days_result else 0.0

    return {
        "active_candidates": active_candidates,
        "cvs_screened":      cvs_screened,
        "hired_candidates":  hired_candidates,
        "avg_days_to_hire":  avg_days_to_hire,
    }


async def _fetch_departments() -> list[dict]:
    """Count active job postings per department.
    - department set in DB → use directly.
    - department NULL → classify from job title keywords.
    Percentages based on total active job postings count."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(JobPostingModel.department, JobPostingModel.title)
            .where(JobPostingModel.status != "archived")
        )
        rows = result.all()

    counts: dict[str, int] = {}
    for row in rows:
        dept = _classify_department(row.department, row.title)
        counts[dept] = counts.get(dept, 0) + 1

    total = sum(counts.values()) or 1
    sorted_depts = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    return [
        {"label": dept, "value": round(cnt / total * 100)}
        for dept, cnt in sorted_depts
    ]


async def _fetch_trends(period: Optional[str] = None) -> list[dict]:
    """CV uploads + interviews grouped by period → [{label, value, interviews}], zero-filled for missing buckets.

    period: '1d'=7 daily buckets, '1w'=8 weekly, '1m'=30 daily,
            '3m'=13 weekly, '6m'/None=6 monthly.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if period == "1d":
        since = now - timedelta(days=7)
        trunc_unit, pg_fmt = "day", "DD Mon"
        buckets = [(now - timedelta(days=i)).strftime("%d %b") for i in range(6, -1, -1)]
    elif period == "1w":
        since = now - timedelta(weeks=8)
        trunc_unit, pg_fmt = "week", "DD Mon"
        buckets = []
        for i in range(7, -1, -1):
            d = now - timedelta(weeks=i)
            monday = d - timedelta(days=d.weekday())
            buckets.append(monday.strftime("%d %b"))
    elif period == "1m":
        since = now - timedelta(days=30)
        trunc_unit, pg_fmt = "day", "DD Mon"
        buckets = [(now - timedelta(days=i)).strftime("%d %b") for i in range(29, -1, -1)]
    elif period == "3m":
        since = now - timedelta(days=90)
        trunc_unit, pg_fmt = "week", "DD Mon"
        buckets = []
        for i in range(12, -1, -1):
            d = now - timedelta(weeks=i)
            monday = d - timedelta(days=d.weekday())
            buckets.append(monday.strftime("%d %b"))
    else:
        # Default / "6m": last 6 months grouped by month
        since = now - timedelta(days=180)
        trunc_unit, pg_fmt = "month", "Mon YYYY"
        buckets = []
        for i in range(5, -1, -1):
            year, month = now.year, now.month - i
            while month <= 0:
                month += 12
                year -= 1
            buckets.append(datetime(year, month, 1).strftime("%b %Y"))

    async with AsyncSessionLocal() as session:
        trunc_expr = func.date_trunc(trunc_unit, CVFileModel.created_at)
        result = await session.execute(
            select(
                func.to_char(trunc_expr, pg_fmt).label("label"),
                func.count().label("value"),
            )
            .where(CVFileModel.created_at >= since)
            .group_by(trunc_expr)
            .order_by(trunc_expr)
        )
        rows = result.all()

        interview_date_expr = cast(InterviewModel.interview_date, Date)
        interview_trunc_expr = func.date_trunc(trunc_unit, interview_date_expr)
        interview_result = await session.execute(
            select(
                func.to_char(interview_trunc_expr, pg_fmt).label("label"),
                func.count().label("value"),
            )
            .where(interview_date_expr >= since.date())
            .group_by(interview_trunc_expr)
            .order_by(interview_trunc_expr)
        )
        interview_rows = interview_result.all()

    db_data = {str(row.label).strip(): int(row.value) for row in rows}
    interview_data = {str(row.label).strip(): int(row.value) for row in interview_rows}

    # Deduplicate buckets (edge case: same label in different years) preserving order
    seen: set[str] = set()
    unique_buckets: list[str] = []
    for b in buckets:
        if b not in seen:
            seen.add(b)
            unique_buckets.append(b)

    return [
        {"label": b, "value": db_data.get(b, 0), "interviews": interview_data.get(b, 0)}
        for b in unique_buckets
    ]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("")
async def get_dashboard(email: Optional[str] = None):
    """
    Full dashboard payload consumed by the frontend home page.

    Response:
        active_candidates   : number
        cvs_screened        : number   (labelled "CVs Screened" on frontend)
        hired_candidates    : number   (labelled "Hired Candidates")
        avg_days_to_hire    : number   (labelled "Avg. Days to Hire")
        charts              : array of chart objects
        departments         : [{name, value}]
    """
    try:
        stats       = await _fetch_stats()
        departments = await _fetch_departments()
        trends      = await _fetch_trends()

        charts = [
            {
                "chart_type": "line",
                "title":      "CV Upload Trends",
                "sub_title":  "Monthly CV submissions",
                "dataset":    trends,
            },
            {
                "chart_type": "bar",
                "title":      "Candidates by Seniority",
                "sub_title":  "Distribution across levels",
                "dataset":    departments,
            },
        ]

        return {
            "active_candidates": stats["active_candidates"],
            "cvs_screened":      stats["cvs_screened"],
            "hired_candidates":  stats["hired_candidates"],
            "avg_days_to_hire":  stats["avg_days_to_hire"],
            "charts":            charts,
            "departments":       departments,
        }
    except Exception as e:
        logger.exception("Dashboard error: %s", e)
        raise HTTPException(status_code=500, detail="Dashboard unavailable")


@router.get("/stats")
async def get_stats(period: Optional[str] = None):
    """
    Stat cards for the frontend.

    Response:
        activeCandidates : number
        cvsScreened      : number
        hiredCandidates  : number
        avgDaysToHire    : number
    """
    try:
        stats = await _fetch_stats()
        return {
            "activeCandidates": stats["active_candidates"],
            "cvsScreened":      stats["cvs_screened"],
            "hiredCandidates":  stats["hired_candidates"],
            "avgDaysToHire":    stats["avg_days_to_hire"],
        }
    except Exception as e:
        logger.exception("Stats error: %s", e)
        raise HTTPException(status_code=500, detail="Stats unavailable")


@router.get("/departments")
async def get_departments():
    """
    Hiring distribution by department (from job postings).

    Response: [{label: string, value: number}]
    """
    try:
        return await _fetch_departments()
    except Exception as e:
        logger.exception("Departments error: %s", e)
        raise HTTPException(status_code=500, detail="Departments unavailable")


@router.get("/trends/details")
async def get_trends_details(date: str, period: Optional[str] = None):
    """
    Candidates whose CV was submitted in the given trend bucket.

    Response: [{candidate_id, full_name, email, phone, location,
                status, seniority_level, total_years_experience, created_at}]
    """
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        label = date.strip()

        if period in ("1d", "1m"):
            # "DD Mon" label, daily bucket
            dt = None
            for year in [now.year, now.year - 1]:
                try:
                    candidate = datetime.strptime(f"{label} {year}", "%d %b %Y")
                    if candidate <= now + timedelta(days=1):
                        dt = candidate
                        break
                except ValueError:
                    pass
            if dt is None:
                raise HTTPException(status_code=400, detail="Invalid date label")
            since, until = dt, dt + timedelta(days=1)

        elif period in ("1w", "3m"):
            # "DD Mon" label, weekly bucket (Monday of week)
            dt = None
            for year in [now.year, now.year - 1]:
                try:
                    candidate = datetime.strptime(f"{label} {year}", "%d %b %Y")
                    if candidate <= now + timedelta(weeks=1):
                        dt = candidate
                        break
                except ValueError:
                    pass
            if dt is None:
                raise HTTPException(status_code=400, detail="Invalid date label")
            since, until = dt, dt + timedelta(weeks=1)

        else:
            # "Mon YYYY" label, monthly bucket
            try:
                dt = datetime.strptime(label, "%b %Y")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date label")
            since = dt
            until = dt.replace(month=dt.month % 12 + 1) if dt.month < 12 else dt.replace(year=dt.year + 1, month=1)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(CandidateModel)
                .where(CandidateModel.created_at >= since)
                .where(CandidateModel.created_at < until)
                .order_by(CandidateModel.created_at.desc())
            )
            candidates = result.scalars().all()

        return [
            {
                "candidate_id":          str(c.candidate_id),
                "full_name":             c.full_name or "",
                "email":                 c.email,
                "phone":                 c.phone,
                "location":              c.location,
                "status":                c.status,
                "seniority_level":       c.seniority_level,
                "total_years_experience": c.total_years_experience,
                "created_at":            c.created_at.isoformat() if c.created_at else None,
            }
            for c in candidates
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Trends details error: %s", e)
        raise HTTPException(status_code=500, detail="Trend details unavailable")


@router.get("/trends")
async def get_trends(period: Optional[str] = None):
    """
    CV upload and interview evolution over time.

    Response: [{label: string, value: number, interviews: number}]
    """
    try:
        return await _fetch_trends(period)
    except Exception as e:
        logger.exception("Trends error: %s", e)
        raise HTTPException(status_code=500, detail="Trends unavailable")

@router.get("/top-skills")
async def get_top_skills(limit: int = 5):
    """
    Most requested skills across all active job postings.

    Response: [{
        skill: string,
        count: number
    }]
    """
    try:
        async with AsyncSessionLocal() as session:
            # Get all active job postings with their required skills
            result = await session.execute(
                select(
                    JobPostingModel.required_skills
                )
                .where(JobPostingModel.status.in_(["active", "open"]))
            )
            
            rows = result.all()
            
            # Count skill occurrences
            skill_counts = {}
            
            for row in rows:
                if not row.required_skills:
                    continue
                    
                for skill in row.required_skills:
                    skill_lower = skill.lower().strip()
                    if not skill_lower:
                        continue
                        
                    # Count occurrences
                    skill_counts[skill_lower] = skill_counts.get(skill_lower, 0) + 1
            
            # Convert to list and sort by count
            skills_list = [
                {
                    "skill": skill.title(),
                    "count": count
                }
                for skill, count in skill_counts.items()
            ]
            
            skills_list.sort(key=lambda x: x["count"], reverse=True)
            return skills_list[:limit]
            
    except Exception as e:
        logger.exception("Top skills error: %s", e)
        raise HTTPException(status_code=500, detail="Top skills unavailable")


@router.get("/recent-activity")
async def get_recent_activity(limit: int = 5):
    """
    Recent activity timeline: candidate additions and job postings.

    Response: [{
        id: string,
        type: "candidate_added" | "job_posted",
        title: string,
        timestamp: datetime
    }]
    """
    try:
        async with AsyncSessionLocal() as session:
            activities = []
            
            # Recent candidates (last 14 days)
            candidate_result = await session.execute(
                select(
                    CandidateModel.candidate_id,
                    CandidateModel.full_name,
                    CandidateModel.created_at
                )
                .where(CandidateModel.created_at >= datetime.now() - timedelta(days=14))
                .order_by(CandidateModel.created_at.desc())
                .limit(limit)
            )
            
            for row in candidate_result.all():
                activities.append({
                    "id": f"candidate_{row.candidate_id}",
                    "type": "candidate_added",
                    "title": row.full_name or "Nouveau candidat",
                    "timestamp": row.created_at.isoformat() if row.created_at else None
                })
            
            # Recent job postings (last 14 days)
            job_result = await session.execute(
                select(
                    JobPostingModel.job_id,
                    JobPostingModel.title,
                    JobPostingModel.created_at
                )
                .where(JobPostingModel.created_at >= datetime.now() - timedelta(days=14))
                .order_by(JobPostingModel.created_at.desc())
                .limit(limit)
            )
            
            for row in job_result.all():
                activities.append({
                    "id": f"job_{row.job_id}",
                    "type": "job_posted",
                    "title": row.title,
                    "timestamp": row.created_at.isoformat() if row.created_at else None
                })
            
            # Sort all activities by timestamp and limit
            activities.sort(key=lambda x: x["timestamp"] or "", reverse=True)
            return activities[:limit]
            
    except Exception as e:
        logger.exception("Recent activity error: %s", e)
        raise HTTPException(status_code=500, detail="Recent activity unavailable")


# ─────────────────────────────────────────────────────────────────────────────
# Advanced HR Intelligence endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/kpis")
async def get_advanced_kpis():
    """
    Advanced KPIs for HR Intelligence Dashboard.
    Returns conversion rates, weekly trends, and pipeline metrics.
    """
    try:
        async with AsyncSessionLocal() as session:
            now   = datetime.now(timezone.utc)
            week_start      = now - timedelta(days=now.weekday())
            prev_week_start = week_start - timedelta(days=7)

            # ── Candidates this week vs last week ──────────────────────────
            cands_this_week = (await session.execute(
                select(func.count()).select_from(CandidateModel)
                .where(CandidateModel.created_at >= week_start)
            )).scalar_one()

            cands_prev_week = (await session.execute(
                select(func.count()).select_from(CandidateModel)
                .where(CandidateModel.created_at >= prev_week_start)
                .where(CandidateModel.created_at < week_start)
            )).scalar_one()

            # ── Interviews this week vs last week ─────────────────────────
            interviews_this_week = (await session.execute(
                select(func.count()).select_from(InterviewModel)
                .where(InterviewModel.created_at >= week_start)
            )).scalar_one()

            interviews_prev_week = (await session.execute(
                select(func.count()).select_from(InterviewModel)
                .where(InterviewModel.created_at >= prev_week_start)
                .where(InterviewModel.created_at < week_start)
            )).scalar_one()

            # ── Conversion rate CV → entretien ───────────────────────────
            total_candidates = (await session.execute(
                select(func.count()).select_from(CandidateModel)
            )).scalar_one()

            total_interviews = (await session.execute(
                select(func.count()).select_from(InterviewModel)
            )).scalar_one()

            conversion_rate = round(
                (total_interviews / total_candidates * 100) if total_candidates else 0, 1
            )

            conv_this_week = round(
                (interviews_this_week / cands_this_week * 100) if cands_this_week else 0, 1
            )
            conv_prev_week = round(
                (interviews_prev_week / cands_prev_week * 100) if cands_prev_week else 0, 1
            )

            # ── Active postings ───────────────────────────────────────────
            active_postings = (await session.execute(
                select(func.count()).select_from(JobPostingModel)
                .where(JobPostingModel.status.in_(["active", "open"]))
            )).scalar_one()

            # ── Hired this week ───────────────────────────────────────────
            hired_this_week = (await session.execute(
                select(func.count()).select_from(CandidateModel)
                .where(CandidateModel.status == "hired")
                .where(CandidateModel.created_at >= week_start)
            )).scalar_one()

            # ── Avg days to hire ──────────────────────────────────────────
            hired_candidates = (await session.execute(
                select(CandidateModel.created_at)
                .where(CandidateModel.status == "hired")
            )).scalars().all()

            avg_days_to_hire = 0
            if hired_candidates:
                deltas = [(now - c.replace(tzinfo=timezone.utc) if c.tzinfo is None else now - c).days
                          for c in hired_candidates]
                avg_days_to_hire = round(sum(deltas) / len(deltas))

            return {
                "conversion_rate":       conversion_rate,
                "conv_this_week":        conv_this_week,
                "conv_prev_week":        conv_prev_week,
                "interviews_this_week":  interviews_this_week,
                "interviews_prev_week":  interviews_prev_week,
                "candidates_this_week":  cands_this_week,
                "candidates_prev_week":  cands_prev_week,
                "active_postings":       active_postings,
                "hired_this_week":       hired_this_week,
                "avg_days_to_hire":      avg_days_to_hire,
                "total_candidates":      total_candidates,
                "total_interviews":      total_interviews,
            }
    except Exception as e:
        logger.exception("KPIs error: %s", e)
        raise HTTPException(status_code=500, detail="KPIs unavailable")


@router.get("/alerts")
async def get_alerts():
    """
    Smart alerts: job postings in difficulty (open too long, no interviews).
    Returns list of alerts ordered by severity: critical > warning > info.
    """
    try:
        async with AsyncSessionLocal() as session:
            now = datetime.now(timezone.utc)

            open_postings = (await session.execute(
                select(JobPostingModel).where(JobPostingModel.status.in_(["active", "open"]))
            )).scalars().all()

            alerts = []
            for posting in open_postings:
                created = posting.created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                days_open = (now - created).days

                interview_count = (await session.execute(
                    select(func.count()).select_from(InterviewModel)
                    .where(InterviewModel.job_posting_id == posting.job_id)
                )).scalar_one()

                if days_open >= 2 and interview_count == 0:
                    alerts.append({
                        "posting_id":       posting.job_id,
                        "posting_title":    posting.title,
                        "days_open":        days_open,
                        "interview_count":  interview_count,
                        "severity":         "critical",
                        "message":          f"Poste ouvert depuis {days_open} jours sans aucun entretien planifié",
                    })
                elif days_open >= 2 and interview_count < 3:
                    alerts.append({
                        "posting_id":       posting.job_id,
                        "posting_title":    posting.title,
                        "days_open":        days_open,
                        "interview_count":  interview_count,
                        "severity":         "critical",
                        "message":          f"Poste ouvert depuis {days_open} jours — seulement {interview_count} entretien(s)",
                    })
                elif days_open >= 1 and interview_count == 0:
                    alerts.append({
                        "posting_id":       posting.job_id,
                        "posting_title":    posting.title,
                        "days_open":        days_open,
                        "interview_count":  interview_count,
                        "severity":         "warning",
                        "message":          f"Poste ouvert depuis {days_open} jours sans entretien planifié",
                    })
                elif days_open >= 0 and interview_count == 0:
                    display_days = max(1, days_open)
                    alerts.append({
                        "posting_id":       posting.job_id,
                        "posting_title":    posting.title,
                        "days_open":        display_days,
                        "interview_count":  interview_count,
                        "severity":         "info",
                        "message":          f"Poste ouvert depuis {display_days} jours — aucun entretien encore",
                    })

            severity_order = {"critical": 0, "warning": 1, "info": 2}
            alerts.sort(key=lambda a: (severity_order[a["severity"]], -a["days_open"]))
            return alerts

    except Exception as e:
        logger.exception("Alerts error: %s", e)
        raise HTTPException(status_code=500, detail="Alerts unavailable")


@router.get("/posting-performance")
async def get_posting_performance():
    """
    Per-posting performance: interviews, hired, days open.
    Returns list of open postings with their recruitment funnel metrics.
    """
    try:
        async with AsyncSessionLocal() as session:
            now = datetime.now(timezone.utc)

            postings = (await session.execute(
                select(JobPostingModel)
                .where(JobPostingModel.status.in_(["active", "open"]))
                .order_by(JobPostingModel.created_at.desc())
                .limit(10)
            )).scalars().all()

            result = []
            for posting in postings:
                created = posting.created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                days_open = (now - created).days

                interview_count = (await session.execute(
                    select(func.count()).select_from(InterviewModel)
                    .where(InterviewModel.job_posting_id == posting.job_id)
                )).scalar_one()

                hired_count = (await session.execute(
                    select(func.count()).select_from(InterviewModel)
                    .join(CandidateModel, InterviewModel.candidate_id == CandidateModel.candidate_id)
                    .where(InterviewModel.job_posting_id == posting.job_id)
                    .where(CandidateModel.status == "hired")
                )).scalar_one()

                health = (
                    "critical" if days_open >= 45 and interview_count == 0
                    else "warning"  if days_open >= 30 and interview_count < 2
                    else "good"
                )

                result.append({
                    "job_id":          posting.job_id,
                    "title":           posting.title,
                    "department":      posting.department,
                    "days_open":       days_open,
                    "interview_count": interview_count,
                    "hired_count":     hired_count,
                    "health":          health,
                })

            return result

    except Exception as e:
        logger.exception("Posting performance error: %s", e)
        raise HTTPException(status_code=500, detail="Posting performance unavailable")


@router.get("/funnel")
async def get_recruitment_funnel():
    """Recruitment funnel: CVs → Interviewed → Hired."""
    try:
        async with AsyncSessionLocal() as session:
            total_cvs = (await session.execute(
                select(func.count()).select_from(CandidateModel)
            )).scalar_one()

            total_interviewed = (await session.execute(
                select(func.count(CandidateModel.candidate_id.distinct()))
                .select_from(CandidateModel)
                .join(InterviewModel, InterviewModel.candidate_id == CandidateModel.candidate_id)
            )).scalar_one()

            total_hired = (await session.execute(
                select(func.count()).select_from(CandidateModel)
                .where(CandidateModel.status == "hired")
            )).scalar_one()

            total_rejected = (await session.execute(
                select(func.count()).select_from(CandidateModel)
                .where(CandidateModel.status == "rejected")
            )).scalar_one()

            total_pending = total_cvs - total_interviewed - total_hired - total_rejected

            return {
                "stages": [
                    {"label": "CVs reçus",   "value": total_cvs,         "color": "#6366f1"},
                    {"label": "Entretiens",  "value": total_interviewed,  "color": "#8b5cf6"},
                    {"label": "Embauchés",   "value": total_hired,        "color": "#10b981"},
                    {"label": "Refusés",     "value": total_rejected,     "color": "#ef4444"},
                ],
                "pending": max(total_pending, 0),
            }
    except Exception as e:
        logger.exception("Funnel error: %s", e)
        raise HTTPException(status_code=500, detail="Funnel unavailable")


@router.get("/today")
async def get_today_widget():
    """Today's interviews and pending decisions."""
    try:
        async with AsyncSessionLocal() as session:
            today_str = datetime.now().strftime("%Y-%m-%d")

            today_interviews_rows = (await session.execute(
                select(InterviewModel, CandidateModel)
                .join(CandidateModel, InterviewModel.candidate_id == CandidateModel.candidate_id)
                .where(InterviewModel.interview_date == today_str)
                .where(InterviewModel.status == "scheduled")
                .order_by(InterviewModel.interview_time)
            )).all()

            # Deduplicate: keep only first interview per candidate
            seen_candidates: set[str] = set()
            today_interviews = []
            for iv, cand in today_interviews_rows:
                if cand.candidate_id not in seen_candidates:
                    seen_candidates.add(cand.candidate_id)
                    today_interviews.append({
                        "interview_id":   iv.interview_id,
                        "candidate_name": cand.full_name,
                        "time":           iv.interview_time,
                        "format":         iv.format,
                        "platform":       iv.platform,
                        "duration_min":   iv.duration_min,
                    })

            # Candidates in "interviewing" status for more than 5 days without decision
            cutoff = datetime.now(timezone.utc) - timedelta(days=5)
            pending_rows = (await session.execute(
                select(CandidateModel)
                .where(CandidateModel.status == "interviewing")
                .where(CandidateModel.created_at <= cutoff)
                .order_by(CandidateModel.created_at)
                .limit(5)
            )).scalars().all()

            pending_decisions = [
                {
                    "candidate_id":   c.candidate_id,
                    "name":           c.full_name,
                    "days_waiting":   (datetime.now(timezone.utc) - (c.created_at.replace(tzinfo=timezone.utc) if c.created_at.tzinfo is None else c.created_at)).days,
                }
                for c in pending_rows
            ]

            return {
                "today_interviews":  today_interviews,
                "pending_decisions": pending_decisions,
            }
    except Exception as e:
        logger.exception("Today widget error: %s", e)
        raise HTTPException(status_code=500, detail="Today widget unavailable")


@router.get("/weekly-trend")
async def get_weekly_trend():
    """CVs and interviews per week for the last 4 weeks."""
    try:
        async with AsyncSessionLocal() as session:
            now = datetime.now(timezone.utc)
            weeks = []
            for i in range(3, -1, -1):
                week_end   = now - timedelta(days=i * 7)
                week_start = week_end - timedelta(days=7)
                label = f"S-{i}" if i > 0 else "Cette sem."

                cvs = (await session.execute(
                    select(func.count()).select_from(CandidateModel)
                    .where(CandidateModel.created_at >= week_start)
                    .where(CandidateModel.created_at < week_end)
                )).scalar_one()

                interviews = (await session.execute(
                    select(func.count()).select_from(InterviewModel)
                    .where(InterviewModel.created_at >= week_start)
                    .where(InterviewModel.created_at < week_end)
                )).scalar_one()

                weeks.append({"label": label, "cvs": cvs, "interviews": interviews})

            return weeks
    except Exception as e:
        logger.exception("Weekly trend error: %s", e)
        raise HTTPException(status_code=500, detail="Weekly trend unavailable")


MONTH_LABELS_FR = [
    "Jan", "Fév", "Mar", "Avr", "Mai", "Juin",
    "Juil", "Août", "Sep", "Oct", "Nov", "Déc",
]


@router.get("/status-by-month")
async def get_status_by_month(year: int):
    """Candidates received/interviewing/hired per month, grouped by current status."""
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(
                    func.extract("month", CandidateModel.created_at),
                    CandidateModel.status,
                    func.count(),
                )
                .where(func.extract("year", CandidateModel.created_at) == year)
                .group_by(func.extract("month", CandidateModel.created_at), CandidateModel.status)
            )
            counts = {(int(m), status): c for m, status, c in result.all()}

            return {
                "labels":    MONTH_LABELS_FR,
                "received":  [sum(counts.get((m, s), 0) for s in ("pending", "interviewing", "hired", "rejected")) for m in range(1, 13)],
                "interview": [counts.get((m, "interviewing"), 0) for m in range(1, 13)],
                "hired":     [counts.get((m, "hired"), 0) for m in range(1, 13)],
            }
    except Exception as e:
        logger.exception("Status by month error: %s", e)
        raise HTTPException(status_code=500, detail="Status by month unavailable")


@router.get("/status-by-day")
async def get_status_by_day(year: int, month: int):
    """Candidates received/interviewing/hired per day of a given month."""
    try:
        import calendar
        days_in_month = calendar.monthrange(year, month)[1]

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(
                    func.extract("day", CandidateModel.created_at),
                    CandidateModel.status,
                    func.count(),
                )
                .where(func.extract("year", CandidateModel.created_at) == year)
                .where(func.extract("month", CandidateModel.created_at) == month)
                .group_by(func.extract("day", CandidateModel.created_at), CandidateModel.status)
            )
            counts = {(int(d), status): c for d, status, c in result.all()}

            return {
                "labels":    [str(d) for d in range(1, days_in_month + 1)],
                "received":  [sum(counts.get((d, s), 0) for s in ("pending", "interviewing", "hired", "rejected")) for d in range(1, days_in_month + 1)],
                "interview": [counts.get((d, "interviewing"), 0) for d in range(1, days_in_month + 1)],
                "hired":     [counts.get((d, "hired"), 0) for d in range(1, days_in_month + 1)],
            }
    except Exception as e:
        logger.exception("Status by day error: %s", e)
        raise HTTPException(status_code=500, detail="Status by day unavailable")


@router.get("/team")
async def get_team():
    """Active RH team members shown on the dashboard team widget."""
    try:
        from app.infrastructure.database.models import RHUserModel

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(RHUserModel)
                .where(RHUserModel.is_active.is_(True))
                .order_by(RHUserModel.full_name)
            )
            users = result.scalars().all()

            def initials(name: str | None) -> str:
                if not name:
                    return "?"
                parts = [p for p in name.split(" ") if p]
                return "".join(p[0] for p in parts[:2]).upper()

            return [
                {
                    "id":        u.id,
                    "full_name": u.full_name or u.email,
                    "email":     u.email,
                    "role":      u.role,
                    "initials":  initials(u.full_name),
                }
                for u in users
            ]
    except Exception as e:
        logger.exception("Team error: %s", e)
        raise HTTPException(status_code=500, detail="Team unavailable")


@router.get("/llm-usage")
async def get_llm_usage():
    """
    Current LLM token budget usage (Orange proxy), shared across extraction,
    matching, ranking, and email generation. Returns {} if Redis is unavailable.
    """
    from app.infrastructure.llm.cost_guard import cost_guard
    return await cost_guard.get_usage()
