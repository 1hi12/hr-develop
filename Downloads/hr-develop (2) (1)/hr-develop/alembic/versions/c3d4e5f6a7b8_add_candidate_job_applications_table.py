"""add_candidate_job_applications_table

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-07-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'candidate_job_applications',
        sa.Column('id',             sa.String(36), primary_key=True),
        sa.Column('candidate_id',   sa.String(36),
                  sa.ForeignKey('candidates.candidate_id', ondelete='CASCADE'), nullable=False),
        sa.Column('job_posting_id', sa.String(36),
                  sa.ForeignKey('job_postings.job_id', ondelete='CASCADE'), nullable=False),
        sa.Column('status',         sa.String(20), nullable=False, server_default='pending'),
        sa.Column('score',          sa.Float(),    nullable=True),
        sa.Column('created_at',     sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at',     sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.UniqueConstraint('candidate_id', 'job_posting_id', name='uq_candidate_job_application'),
    )
    op.create_index('ix_candidate_job_applications_candidate_id', 'candidate_job_applications', ['candidate_id'])
    op.create_index('ix_candidate_job_applications_job_posting_id', 'candidate_job_applications', ['job_posting_id'])


def downgrade() -> None:
    op.drop_index('ix_candidate_job_applications_job_posting_id', table_name='candidate_job_applications')
    op.drop_index('ix_candidate_job_applications_candidate_id', table_name='candidate_job_applications')
    op.drop_table('candidate_job_applications')
