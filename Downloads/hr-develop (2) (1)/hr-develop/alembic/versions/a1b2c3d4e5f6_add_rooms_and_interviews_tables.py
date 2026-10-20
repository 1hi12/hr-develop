"""add_rooms_and_interviews_tables

Revision ID: a1b2c3d4e5f6
Revises: f7a8b9c0d1e2
Create Date: 2026-06-12 00:00:00.000000

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEFAULT_ROOMS = [
    {"name": "Salle Atlas",   "floor": "1", "building": "Bât. A", "capacity": 6,  "equipment": ["projector", "whiteboard"]},
    {"name": "Salle Toubkal", "floor": "2", "building": "Bât. A", "capacity": 10, "equipment": ["projector", "tv", "webcam"]},
    {"name": "Salle Rif",     "floor": "1", "building": "Bât. B", "capacity": 4,  "equipment": ["whiteboard"]},
    {"name": "Salle Sahara",  "floor": "3", "building": "Bât. A", "capacity": 8,  "equipment": ["projector", "phone"]},
    {"name": "Salle Mogador", "floor": "2", "building": "Bât. B", "capacity": 6,  "equipment": ["tv", "whiteboard"]},
]


def upgrade() -> None:
    rooms_table = op.create_table(
        'rooms',
        sa.Column('room_id',    sa.String(36),  primary_key=True),
        sa.Column('name',       sa.String(128), nullable=False, unique=True),
        sa.Column('floor',      sa.String(64),  nullable=True),
        sa.Column('building',   sa.String(128), nullable=True),
        sa.Column('capacity',   sa.Integer(),   nullable=False, server_default='4'),
        sa.Column('equipment',  JSONB(),         nullable=False, server_default='[]'),
        sa.Column('is_active',  sa.Boolean(),   nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
    )

    # Seed default rooms immediately after table creation
    import json
    op.bulk_insert(rooms_table, [
        {
            "room_id":   str(uuid.uuid4()),
            "name":      r["name"],
            "floor":     r["floor"],
            "building":  r["building"],
            "capacity":  r["capacity"],
            "equipment": json.dumps(r["equipment"]),
            "is_active": True,
        }
        for r in _DEFAULT_ROOMS
    ])

    op.create_table(
        'interviews',
        sa.Column('interview_id',     sa.String(36),  primary_key=True),
        sa.Column('candidate_id',     sa.String(36),
                  sa.ForeignKey('candidates.candidate_id', ondelete='CASCADE'), nullable=False),
        sa.Column('job_posting_id',   sa.String(36),
                  sa.ForeignKey('job_postings.job_id', ondelete='SET NULL'), nullable=True),
        sa.Column('room_id',          sa.String(36),
                  sa.ForeignKey('rooms.room_id', ondelete='SET NULL'), nullable=True),
        sa.Column('interview_date',   sa.String(10),  nullable=False),
        sa.Column('interview_time',   sa.String(5),   nullable=False),
        sa.Column('duration_min',     sa.Integer(),   nullable=False, server_default='45'),
        sa.Column('format',           sa.String(16),  nullable=False),
        sa.Column('platform',         sa.String(32),  nullable=True),
        sa.Column('meeting_link',     sa.Text(),      nullable=True),
        sa.Column('interviewer_name', sa.String(128), nullable=True),
        sa.Column('notes',            sa.Text(),      nullable=True),
        sa.Column('status',           sa.String(32),  nullable=False, server_default='scheduled'),
        sa.Column('email_sent',       sa.Boolean(),   nullable=False, server_default='false'),
        sa.Column('reminder_sent',    sa.Boolean(),   nullable=False, server_default='false'),
        sa.Column('created_at',       sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at',       sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
    )


def downgrade() -> None:
    op.drop_table('interviews')
    op.drop_table('rooms')
