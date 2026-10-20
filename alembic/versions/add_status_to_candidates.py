"""Add status field to candidates table

Revision ID: add_status_to_candidates
Revises: 3f4e5d6c7a8b
Create Date: 2026-04-12

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_status_to_candidates'
down_revision = '3f4e5d6c7a8b'
branch_labels = None
depends_on = None


def upgrade():
    # Add status column to candidates table
    op.add_column('candidates', 
        sa.Column('status', sa.String(20), nullable=False, server_default='pending')
    )
    
    # Create index on status for faster filtering
    op.create_index('idx_candidates_status', 'candidates', ['status'])


def downgrade():
    op.drop_index('idx_candidates_status', table_name='candidates')
    op.drop_column('candidates', 'status')
