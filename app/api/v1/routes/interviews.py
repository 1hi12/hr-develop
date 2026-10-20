"""
interviews.py — Interview scheduling & room management endpoints.

GET  /api/v1/rooms/available      — rooms free for a given slot
GET  /api/v1/rooms                — all active rooms
POST /api/v1/rooms                — create a room (admin)
POST /api/v1/interviews           — schedule an interview
GET  /api/v1/interviews           — list interviews (filter by candidate_id)
GET  /api/v1/interviews/{id}      — interview detail
DELETE /api/v1/interviews/{id}    — cancel interview
POST /api/v1/interviews/reminders — send day-before reminders
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.infrastructure.database.session import AsyncSessionLocal
from app.infrastructure.database.models import InterviewModel, RoomModel, CandidateModel, JobPostingModel
from app.services.interview_service import interview_service, ScheduleInterviewRequest

router = APIRouter(tags=["interviews"])


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic schemas
# ─────────────────────────────────────────────────────────────────────────────

class RoomCreate(BaseModel):
    name:      str
    floor:     Optional[str] = None
    building:  Optional[str] = None
    capacity:  int = 6
    equipment: list[str] = []


class RoomResponse(BaseModel):
    room_id:   str
    name:      str
    floor:     Optional[str]
    building:  Optional[str]
    capacity:  int
    equipment: list[str]
    available: bool = True


class ScheduleRequest(BaseModel):
    candidate_id:     str
    job_posting_id:   Optional[str] = None
    interview_date:   str
    interview_time:   str
    duration_min:     int = 45
    format:           str
    platform:         Optional[str] = None
    meeting_link:     Optional[str] = None
    room_id:          Optional[str] = None
    interviewer_name: Optional[str] = None
    notes:            Optional[str] = None
    candidate_email:  Optional[str] = None
    candidate_name:   Optional[str] = None


class InterviewResponse(BaseModel):
    interview_id:     str
    candidate_id:     str
    job_posting_id:   Optional[str]
    interview_date:   str
    interview_time:   str
    duration_min:     int
    format:           str
    platform:         Optional[str]
    meeting_link:     Optional[str]
    room_id:          Optional[str]
    room_name:        Optional[str] = None
    status:           str
    email_sent:       bool
    reminder_sent:    bool
    interviewer_name: Optional[str]
    notes:            Optional[str]
    created_at:       str
    candidate_name:   Optional[str] = None
    job_title:        Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Rooms
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/rooms/available", response_model=list[RoomResponse])
async def get_available_rooms(
    date:         str = Query(..., description="YYYY-MM-DD"),
    time:         str = Query(..., description="HH:MM"),
    duration_min: int = Query(45),
):
    async with AsyncSessionLocal() as db:
        rooms = await interview_service.get_available_rooms(date, time, duration_min, db)
    return [
        RoomResponse(
            room_id=r.room_id, name=r.name, floor=r.floor,
            building=r.building, capacity=r.capacity,
            equipment=r.equipment, available=r.available,
        )
        for r in rooms
    ]


@router.get("/rooms", response_model=list[RoomResponse])
async def list_rooms():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(RoomModel).where(RoomModel.is_active == True))
        rows   = result.scalars().all()
    return [
        RoomResponse(
            room_id=r.room_id, name=r.name, floor=r.floor,
            building=r.building, capacity=r.capacity,
            equipment=list(r.equipment or []), available=True,
        )
        for r in rows
    ]


@router.post("/rooms", response_model=RoomResponse, status_code=201)
async def create_room(body: RoomCreate):
    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(RoomModel).where(RoomModel.name == body.name))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Room name already exists")
        room = RoomModel(
            room_id=str(uuid.uuid4()),
            name=body.name,
            floor=body.floor,
            building=body.building,
            capacity=body.capacity,
            equipment=body.equipment,
        )
        db.add(room)
        await db.commit()
        await db.refresh(room)
    return RoomResponse(
        room_id=room.room_id, name=room.name, floor=room.floor,
        building=room.building, capacity=room.capacity,
        equipment=list(room.equipment or []),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Interviews
# ─────────────────────────────────────────────────────────────────────────────

def _to_resp(
    iv: InterviewModel,
    candidate_name: Optional[str] = None,
    job_title: Optional[str] = None,
) -> InterviewResponse:
    return InterviewResponse(
        interview_id=iv.interview_id,
        candidate_id=iv.candidate_id,
        job_posting_id=iv.job_posting_id,
        interview_date=iv.interview_date,
        interview_time=iv.interview_time,
        duration_min=iv.duration_min,
        format=iv.format,
        platform=iv.platform,
        meeting_link=iv.meeting_link,
        room_id=iv.room_id,
        room_name=iv.room.name if iv.room else None,
        status=iv.status,
        email_sent=iv.email_sent,
        reminder_sent=iv.reminder_sent,
        interviewer_name=iv.interviewer_name,
        notes=iv.notes,
        created_at=iv.created_at.isoformat(),
        candidate_name=candidate_name,
        job_title=job_title,
    )


@router.post("/interviews", response_model=InterviewResponse, status_code=201)
async def schedule_interview(body: ScheduleRequest):
    req = ScheduleInterviewRequest(
        candidate_id=body.candidate_id,
        job_posting_id=body.job_posting_id,
        interview_date=body.interview_date,
        interview_time=body.interview_time,
        duration_min=body.duration_min,
        format=body.format,
        platform=body.platform,
        meeting_link=body.meeting_link,
        room_id=body.room_id,
        interviewer_name=body.interviewer_name,
        notes=body.notes,
        candidate_email=body.candidate_email,
        candidate_name=body.candidate_name,
    )
    async with AsyncSessionLocal() as db:
        try:
            iv = await interview_service.schedule(req, db)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))

    return InterviewResponse(
        interview_id=iv.interview_id,
        candidate_id=iv.candidate_id,
        job_posting_id=iv.job_posting_id,
        interview_date=iv.interview_date,
        interview_time=iv.interview_time,
        duration_min=iv.duration_min,
        format=iv.format,
        platform=iv.platform,
        meeting_link=iv.meeting_link,
        room_id=iv.room_id,
        room_name=None,
        status=iv.status,
        email_sent=iv.email_sent,
        reminder_sent=iv.reminder_sent,
        interviewer_name=iv.interviewer_name,
        notes=iv.notes,
        created_at=iv.created_at.isoformat(),
    )


@router.get("/interviews", response_model=list[InterviewResponse])
async def list_interviews(candidate_id: Optional[str] = Query(None)):
    async with AsyncSessionLocal() as db:
        q = (
            select(InterviewModel)
            .options(selectinload(InterviewModel.room))
            .order_by(InterviewModel.interview_date.desc(), InterviewModel.interview_time.desc())
        )
        if candidate_id:
            q = q.where(InterviewModel.candidate_id == candidate_id)
        result = await db.execute(q)
        rows   = result.scalars().all()

        candidate_ids  = {r.candidate_id for r in rows}
        job_posting_ids = {r.job_posting_id for r in rows if r.job_posting_id}

        names_by_id = {}
        if candidate_ids:
            cand_result = await db.execute(
                select(CandidateModel.candidate_id, CandidateModel.full_name)
                .where(CandidateModel.candidate_id.in_(candidate_ids))
            )
            names_by_id = {cid: name for cid, name in cand_result.all()}

        titles_by_id = {}
        if job_posting_ids:
            job_result = await db.execute(
                select(JobPostingModel.job_id, JobPostingModel.title)
                .where(JobPostingModel.job_id.in_(job_posting_ids))
            )
            titles_by_id = {jid: title for jid, title in job_result.all()}

    return [
        _to_resp(
            r,
            candidate_name=names_by_id.get(r.candidate_id),
            job_title=titles_by_id.get(r.job_posting_id) if r.job_posting_id else None,
        )
        for r in rows
    ]


@router.get("/interviews/{interview_id}", response_model=InterviewResponse)
async def get_interview(interview_id: str):
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(InterviewModel)
            .options(selectinload(InterviewModel.room))
            .where(InterviewModel.interview_id == interview_id)
        )
        iv = result.scalar_one_or_none()
    if not iv:
        raise HTTPException(status_code=404, detail="Interview not found")
    return _to_resp(iv)


@router.delete("/interviews/{interview_id}", status_code=204)
async def cancel_interview(interview_id: str):
    async with AsyncSessionLocal() as db:
        ok = await interview_service.cancel(interview_id, db)
    if not ok:
        raise HTTPException(status_code=404, detail="Interview not found")


@router.post("/interviews/reminders")
async def trigger_reminders():
    async with AsyncSessionLocal() as db:
        count = await interview_service.send_reminders(db)
    return {"reminders_sent": count}
