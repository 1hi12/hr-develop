"""
SQLAlchemy ORM models for the HR CV system.

Mapping:
    Candidate        → candidates          (main table)
    Experience       → candidate_experiences
    Education        → candidate_educations
    Skill            → candidate_skills
    ExtractedSkills  → candidate_extracted_skills  (one JSON row per candidate)
    Chunk            → candidate_chunks
    EmbeddedChunk    → stored in Milvus only (vector store) — NOT in Postgres
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.value_objects.seniority import SeniorityLevel


# ─────────────────────────────────────────────────────────────
# Base
# ─────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────
# candidates
# ─────────────────────────────────────────────────────────────

class CandidateModel(Base):
    """
    One row per uploaded CV / candidate.
    All 1-to-many relations (skills, experiences …) cascade on delete.
    """
    __tablename__ = "candidates"

    # ── PK ───────────────────────────────────────────────────
    # FIX: was `id`, actual DB column is `candidate_id`
    candidate_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid, comment="candidate_id (UUID)"
    )

    # ── File info ────────────────────────────────────────────
    filename: Mapped[str] = mapped_column(String(512), nullable=False)

    # ── Personal info ────────────────────────────────────────
    full_name:  Mapped[str | None] = mapped_column(String(256))
    email:      Mapped[str | None] = mapped_column(String(256), index=True)
    phone:      Mapped[str | None] = mapped_column(String(64))

    # ── Identity grouping ─────────────────────────────────────
    # Shared by every CV upload that belongs to the same person (exact match on
    # normalized full_name+email+phone). See app/core/value_objects/identity.py.
    identity_id: Mapped[str] = mapped_column(String(36), nullable=False, default=_uuid, index=True)
    location:   Mapped[str | None] = mapped_column(String(256))
    linkedin:   Mapped[str | None] = mapped_column(String(512))
    github:     Mapped[str | None] = mapped_column(String(512))
    summary:    Mapped[str | None] = mapped_column(Text)

    # ── Languages (simple list → JSONB) ──────────────────────
    # FIX: was `languages`, actual DB column is `languages_json`
    languages_json: Mapped[list] = mapped_column(JSONB, nullable=True, default=list)

    # ── Skills (JSONB) ───────────────────────────────────────
    # FIX: was missing entirely — exists in DB as `skills_json`
    skills_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ── Seniority ─────────────────────────────────────────────
    # FIX: was SAEnum (creates a PG ENUM type) — DB has it as plain VARCHAR
    seniority_level: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=SeniorityLevel.UNKNOWN.value,
        index=True,
    )
    total_years_experience: Mapped[float | None] = mapped_column(Float)

    # ── Extraction metadata ───────────────────────────────────
    extraction_confidence: Mapped[float | None] = mapped_column(Float)
    cv_file_hash: Mapped[str | None] = mapped_column(String(64), index=True, unique=True)
    cv_raw_text:  Mapped[str | None] = mapped_column(Text)

    # ── Application status ────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
        comment="Application status: pending, interviewing, hired, rejected"
    )

    # ── Timestamps ───────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    # ── Relationships ────────────────────────────────────────
    skills:           Mapped[list["SkillModel"]]            = relationship(back_populates="candidate", cascade="all, delete-orphan")
    experiences:      Mapped[list["ExperienceModel"]]       = relationship(back_populates="candidate", cascade="all, delete-orphan")
    educations:       Mapped[list["EducationModel"]]        = relationship(back_populates="candidate", cascade="all, delete-orphan")
    extracted_skills: Mapped["ExtractedSkillsModel | None"] = relationship(back_populates="candidate", cascade="all, delete-orphan", uselist=False)
    chunks:           Mapped[list["ChunkModel"]]            = relationship(back_populates="candidate", cascade="all, delete-orphan")
    cv_files:         Mapped[list["CVFileModel"]]           = relationship(back_populates="candidate", cascade="all, delete-orphan")
    interviews:       Mapped[list["InterviewModel"]]        = relationship(back_populates="candidate", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<CandidateModel candidate_id={self.candidate_id} name={self.full_name!r}>"


# ─────────────────────────────────────────────────────────────
# candidate_skills
# ─────────────────────────────────────────────────────────────

class SkillModel(Base):
    __tablename__ = "candidate_skills"
    __table_args__ = (
        UniqueConstraint("candidate_id", "name", name="uq_candidate_skill_name"),
    )

    id:           Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # FIX: FK was pointing to "candidates.id" → now "candidates.candidate_id"
    candidate_id: Mapped[str] = mapped_column(String(36), ForeignKey("candidates.candidate_id", ondelete="CASCADE"), nullable=False, index=True)

    name:                Mapped[str]          = mapped_column(String(256), nullable=False)
    category:            Mapped[str | None]   = mapped_column(String(128))
    level:               Mapped[str | None]   = mapped_column(String(64))
    years_of_experience: Mapped[float | None] = mapped_column(Float)

    candidate: Mapped["CandidateModel"] = relationship(back_populates="skills")

    def __repr__(self) -> str:
        return f"<SkillModel candidate={self.candidate_id} name={self.name!r}>"


# ─────────────────────────────────────────────────────────────
# candidate_experiences
# ─────────────────────────────────────────────────────────────

class ExperienceModel(Base):
    __tablename__ = "candidate_experiences"

    id:           Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # FIX: FK was pointing to "candidates.id" → now "candidates.candidate_id"
    candidate_id: Mapped[str] = mapped_column(String(36), ForeignKey("candidates.candidate_id", ondelete="CASCADE"), nullable=False, index=True)

    company:         Mapped[str | None] = mapped_column(String(256))
    title:           Mapped[str | None] = mapped_column(String(256))
    start_date:      Mapped[str | None] = mapped_column(String(32))
    end_date:        Mapped[str | None] = mapped_column(String(32))
    duration_months: Mapped[int | None] = mapped_column(Integer)
    description:     Mapped[str | None] = mapped_column(Text)
    location:        Mapped[str | None] = mapped_column(String(256))

    candidate: Mapped["CandidateModel"] = relationship(back_populates="experiences")

    def __repr__(self) -> str:
        return f"<ExperienceModel candidate={self.candidate_id} title={self.title!r}>"


# ─────────────────────────────────────────────────────────────
# candidate_educations
# ─────────────────────────────────────────────────────────────

class EducationModel(Base):
    __tablename__ = "candidate_educations"

    id:           Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # FIX: FK was pointing to "candidates.id" → now "candidates.candidate_id"
    candidate_id: Mapped[str] = mapped_column(String(36), ForeignKey("candidates.candidate_id", ondelete="CASCADE"), nullable=False, index=True)

    institution:     Mapped[str | None] = mapped_column(String(256))
    degree:          Mapped[str | None] = mapped_column(String(256))
    field_of_study:  Mapped[str | None] = mapped_column(String(256))
    graduation_year: Mapped[int | None] = mapped_column(Integer)

    candidate: Mapped["CandidateModel"] = relationship(back_populates="educations")

    def __repr__(self) -> str:
        return f"<EducationModel candidate={self.candidate_id} degree={self.degree!r}>"


# ─────────────────────────────────────────────────────────────
# candidate_extracted_skills  (1-to-1)
# ─────────────────────────────────────────────────────────────

class ExtractedSkillsModel(Base):
    __tablename__ = "candidate_extracted_skills"

    id:           Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # FIX: FK was pointing to "candidates.id" → now "candidates.candidate_id"
    candidate_id: Mapped[str] = mapped_column(String(36), ForeignKey("candidates.candidate_id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    technical:   Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    frameworks:  Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    databases:   Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    devops:      Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    soft_skills: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    languages:   Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    all_skills:  Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    candidate: Mapped["CandidateModel"] = relationship(back_populates="extracted_skills")

    def __repr__(self) -> str:
        return f"<ExtractedSkillsModel candidate={self.candidate_id}>"


# ─────────────────────────────────────────────────────────────
# candidate_chunks
# ─────────────────────────────────────────────────────────────

class ChunkModel(Base):
    __tablename__ = "candidate_chunks"
    __table_args__ = (
        UniqueConstraint("candidate_id", "chunk_id", name="uq_candidate_chunk_id"),
    )

    id:           Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # FIX: FK was pointing to "candidates.id" → now "candidates.candidate_id"
    candidate_id: Mapped[str] = mapped_column(String(36), ForeignKey("candidates.candidate_id", ondelete="CASCADE"), nullable=False, index=True)

    chunk_id:        Mapped[str] = mapped_column(String(128), nullable=False)
    text:            Mapped[str] = mapped_column(Text, nullable=False)
    section:         Mapped[str] = mapped_column(String(128), nullable=False)
    chunk_index:     Mapped[int] = mapped_column(Integer, nullable=False)
    source_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    char_start:      Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    char_end:        Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_metadata:  Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    candidate: Mapped["CandidateModel"] = relationship(back_populates="chunks")

    def __repr__(self) -> str:
        return f"<ChunkModel candidate={self.candidate_id} chunk_id={self.chunk_id!r}>"


# ─────────────────────────────────────────────────────────────
# cv_files
# ─────────────────────────────────────────────────────────────

class CVFileModel(Base):
    __tablename__ = "cv_files"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # FIX: FK was pointing to "candidates.id" → now "candidates.candidate_id"
    candidate_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("candidates.candidate_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[str | None] = mapped_column(String(36), index=True)

    filename:         Mapped[str]       = mapped_column(String(512), nullable=False)
    file_size_bytes:  Mapped[int | None] = mapped_column(BigInteger)
    content_type:     Mapped[str | None] = mapped_column(String(128))
    source:           Mapped[str]       = mapped_column(String(64), nullable=False, default="upload")

    processing_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", index=True
    )

    error_message:  Mapped[str | None]  = mapped_column(Text)
    extracted_data: Mapped[dict | None] = mapped_column(JSONB)

    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    candidate: Mapped["CandidateModel"] = relationship(back_populates="cv_files")

    def __repr__(self) -> str:
        return f"<CVFileModel id={self.id} candidate={self.candidate_id} status={self.processing_status!r}>"


# ─────────────────────────────────────────────────────────────
# job_postings
# ─────────────────────────────────────────────────────────────

class JobPostingModel(Base):
    """
    One row per job posting created by HR.
    Contains job requirements and is used for automatic candidate matching.
    """
    __tablename__ = "job_postings"

    # ── PK ───────────────────────────────────────────────────
    job_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid, comment="job_id (UUID)"
    )

    # ── Basic Info ───────────────────────────────────────────
    title:           Mapped[str]       = mapped_column(String(512), nullable=False)
    description:     Mapped[str | None] = mapped_column(Text)
    department:      Mapped[str | None] = mapped_column(String(128), index=True)
    location:        Mapped[str | None] = mapped_column(String(256))
    employment_type: Mapped[str]       = mapped_column(String(64), nullable=False, default="full-time")  # full-time, part-time, contract
    
    # ── Requirements ─────────────────────────────────────────
    required_skills:  Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    preferred_skills: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    min_years_experience: Mapped[float | None] = mapped_column(Float)
    max_years_experience: Mapped[float | None] = mapped_column(Float)
    seniority_level:  Mapped[str | None] = mapped_column(String(20), index=True)  # junior, mid, senior, etc.
    
    # ── Quota ────────────────────────────────────────────────
    nb_positions: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Status ───────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", index=True
    )  # active, paused, closed, archived

    # ── Metadata ─────────────────────────────────────────────
    created_by: Mapped[str | None] = mapped_column(String(36))

    # ── Timestamps ───────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    def __repr__(self) -> str:
        return f"<JobPostingModel job_id={self.job_id} title={self.title!r} status={self.status!r}>"


# ─────────────────────────────────────────────────────────────
# rh_users  (HR portal accounts)
# ─────────────────────────────────────────────────────────────

class RHUserModel(Base):
    __tablename__ = "rh_users"

    id:              Mapped[int]      = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email:           Mapped[str]      = mapped_column(String(256), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str]      = mapped_column(String(512), nullable=False)
    full_name:       Mapped[str|None] = mapped_column(String(256))
    role:            Mapped[str]      = mapped_column(String(64), nullable=False, default="recruiter")
    is_active:       Mapped[bool]     = mapped_column(Boolean, nullable=False, default=True)
    created_at:      Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    conversations: Mapped[list["ConversationModel"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<RHUserModel id={self.id} email={self.email!r}>"


# ─────────────────────────────────────────────────────────────
# rooms  (SofSalle mock — internal room booking system)
# ─────────────────────────────────────────────────────────────

class RoomModel(Base):
    """Meeting rooms available for in-person interviews (SofSalle mock)."""
    __tablename__ = "rooms"

    room_id:    Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name:       Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    floor:      Mapped[str | None] = mapped_column(String(64))
    building:   Mapped[str | None] = mapped_column(String(128))
    capacity:   Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    equipment:  Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    is_active:  Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    bookings: Mapped[list["InterviewModel"]] = relationship(back_populates="room", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<RoomModel name={self.name!r} floor={self.floor!r}>"


# ─────────────────────────────────────────────────────────────
# interviews
# ─────────────────────────────────────────────────────────────

class InterviewModel(Base):
    """Scheduled interview linked to a candidate."""
    __tablename__ = "interviews"

    interview_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(String(36), ForeignKey("candidates.candidate_id", ondelete="CASCADE"), nullable=False, index=True)
    job_posting_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("job_postings.job_id", ondelete="SET NULL"), nullable=True)

    interview_date: Mapped[str]      = mapped_column(String(10), nullable=False)   # YYYY-MM-DD
    interview_time: Mapped[str]      = mapped_column(String(5),  nullable=False)   # HH:MM
    duration_min:   Mapped[int]      = mapped_column(Integer, nullable=False, default=45)
    format:         Mapped[str]      = mapped_column(String(20), nullable=False, default="online")  # online | onsite

    # Online fields
    platform:     Mapped[str | None] = mapped_column(String(32))   # teams | meet | zoom | custom
    meeting_link: Mapped[str | None] = mapped_column(String(512))

    # Onsite fields
    room_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("rooms.room_id", ondelete="SET NULL"), nullable=True)

    # Status
    status:          Mapped[str] = mapped_column(String(32), nullable=False, default="scheduled")  # scheduled | cancelled | done
    reminder_sent:   Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    email_sent:      Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    interviewer_name: Mapped[str | None] = mapped_column(String(256))
    notes:           Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    candidate: Mapped["CandidateModel"] = relationship(back_populates="interviews")
    room:      Mapped["RoomModel | None"] = relationship(back_populates="bookings")

    def __repr__(self) -> str:
        return f"<InterviewModel id={self.interview_id} candidate={self.candidate_id} date={self.interview_date}>"


# ─────────────────────────────────────────────────────────────
# conversations  (AI Assistant chat history)
# ─────────────────────────────────────────────────────────────

class ConversationModel(Base):
    """Stores AI Assistant conversation history per user."""
    __tablename__ = "ai_conversations"

    conversation_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id:         Mapped[int] = mapped_column(BigInteger, ForeignKey("rh_users.id", ondelete="CASCADE"), nullable=False, index=True)
    title:           Mapped[str] = mapped_column(String(256), nullable=False)
    messages:        Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # [{role, content, timestamp, recommendations}]

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    user: Mapped["RHUserModel"] = relationship(back_populates="conversations")

    def __repr__(self) -> str:
        return f"<ConversationModel id={self.conversation_id} user={self.user_id} title={self.title!r}>"


# ─────────────────────────────────────────────────────────────
# candidate_job_applications  (per-posting candidate decision)
# ─────────────────────────────────────────────────────────────

class CandidateJobApplicationModel(Base):
    """
    Tracks a candidate's status *for one specific job posting*.

    CandidateModel.status stays a single global "last known decision" field
    (used by the general Candidates page), but matching-pool exclusion must
    be scoped per posting here — rejecting a candidate for job A must not
    remove them from the matching pool of job B.
    """
    __tablename__ = "candidate_job_applications"

    id:             Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id:   Mapped[str] = mapped_column(String(36), ForeignKey("candidates.candidate_id", ondelete="CASCADE"), nullable=False, index=True)
    job_posting_id: Mapped[str] = mapped_column(String(36), ForeignKey("job_postings.job_id", ondelete="CASCADE"), nullable=False, index=True)
    status:         Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending | interviewing | hired | rejected
    score:          Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint("candidate_id", "job_posting_id", name="uq_candidate_job_application"),
    )

    def __repr__(self) -> str:
        return f"<CandidateJobApplicationModel candidate={self.candidate_id} job={self.job_posting_id} status={self.status!r}>"
