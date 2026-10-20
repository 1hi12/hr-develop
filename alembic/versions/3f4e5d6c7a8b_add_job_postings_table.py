"""add job_postings table

Revision ID: 3f4e5d6c7a8b
Revises: 2638d3d2e76a
Create Date: 2026-04-10 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3f4e5d6c7a8b'
down_revision: Union[str, Sequence[str], None] = '2638d3d2e76a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create job_postings table."""
    op.create_table('job_postings',
        sa.Column('job_id', sa.String(length=36), nullable=False, comment='job_id (UUID)'),
        sa.Column('title', sa.String(length=512), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('department', sa.String(length=128), nullable=True),
        sa.Column('location', sa.String(length=256), nullable=True),
        sa.Column('employment_type', sa.String(length=64), nullable=False),
        sa.Column('required_skills', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('preferred_skills', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('min_years_experience', sa.Float(), nullable=True),
        sa.Column('max_years_experience', sa.Float(), nullable=True),
        sa.Column('seniority_level', sa.String(length=20), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('created_by', sa.String(length=36), nullable=True),
        sa.Column('salary_min', sa.Integer(), nullable=True),
        sa.Column('salary_max', sa.Integer(), nullable=True),
        sa.Column('salary_currency', sa.String(length=3), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('job_id')
    )
    op.create_index(op.f('ix_job_postings_department'), 'job_postings', ['department'], unique=False)
    op.create_index(op.f('ix_job_postings_seniority_level'), 'job_postings', ['seniority_level'], unique=False)
    op.create_index(op.f('ix_job_postings_status'), 'job_postings', ['status'], unique=False)


def downgrade() -> None:
    """Drop job_postings table."""
    op.drop_index(op.f('ix_job_postings_status'), table_name='job_postings')
    op.drop_index(op.f('ix_job_postings_seniority_level'), table_name='job_postings')
    op.drop_index(op.f('ix_job_postings_department'), table_name='job_postings')
    op.drop_table('job_postings')
