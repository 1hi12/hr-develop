"""add_nb_positions_to_job_postings

Revision ID: f7a8b9c0d1e2
Revises: e14646e22863
Create Date: 2026-05-16 10:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, Sequence[str], None] = 'e14646e22863'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add nb_positions column to job_postings table
    op.add_column('job_postings', sa.Column('nb_positions', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove nb_positions column from job_postings table
    op.drop_column('job_postings', 'nb_positions')
