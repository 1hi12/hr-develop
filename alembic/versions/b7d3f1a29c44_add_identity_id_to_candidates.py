"""add_identity_id_to_candidates

Revision ID: b7d3f1a29c44
Revises: c3d4e5f6a7b8
Create Date: 2026-07-14 00:00:00.000000

"""
from typing import Sequence, Union
import re
import uuid

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b7d3f1a29c44'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Kept self-contained (not imported from app.core.value_objects.identity) so this
# migration keeps working unchanged even if that module changes later.
_IDENTITY_NAMESPACE = uuid.UUID("6f6a6f0e-6b5a-4b8e-9a2a-8f1a6b2c9d10")


def _normalize_name(name: str | None) -> str:
    if not name:
        return ""
    return re.sub(r"\s+", " ", name.strip().lower())


def _normalize_email(email: str | None) -> str:
    if not email:
        return ""
    return email.strip().lower()


def _normalize_phone(phone: str | None) -> str:
    if not phone:
        return ""
    keep_plus = phone.strip().startswith("+")
    digits = re.sub(r"\D", "", phone)
    return f"+{digits}" if keep_plus else digits


def _compute_identity_id(full_name: str | None, email: str | None, phone: str | None) -> str:
    norm_name  = _normalize_name(full_name)
    norm_email = _normalize_email(email)
    norm_phone = _normalize_phone(phone)
    if not (norm_name and norm_email and norm_phone):
        return str(uuid.uuid4())
    key = f"{norm_name}|{norm_email}|{norm_phone}"
    return str(uuid.uuid5(_IDENTITY_NAMESPACE, key))


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('candidates', sa.Column('identity_id', sa.String(length=36), nullable=True))

    # Backfill: rows sharing normalized (full_name, email, phone) get the same
    # identity_id; rows missing any of the three fields get a random singleton id.
    conn = op.get_bind()
    rows = conn.execute(
        sa.text('SELECT candidate_id, full_name, email, phone FROM candidates')
    ).fetchall()
    for candidate_id, full_name, email, phone in rows:
        identity_id = _compute_identity_id(full_name, email, phone)
        conn.execute(
            sa.text(
                'UPDATE candidates SET identity_id = :identity_id '
                'WHERE candidate_id = :candidate_id'
            ),
            {"identity_id": identity_id, "candidate_id": candidate_id},
        )

    op.alter_column('candidates', 'identity_id', nullable=False)
    op.create_index(op.f('ix_candidates_identity_id'), 'candidates', ['identity_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_candidates_identity_id'), table_name='candidates')
    op.drop_column('candidates', 'identity_id')
