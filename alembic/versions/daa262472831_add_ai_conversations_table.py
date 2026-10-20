"""add_ai_conversations_table

Revision ID: daa262472831
Revises: f7a8b9c0d1e2
Create Date: 2026-06-02 12:43:39.178476

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'daa262472831'
down_revision: Union[str, Sequence[str], None] = 'b7d3f1a29c44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Créer rh_users si n'existe pas
    op.execute("""
        CREATE TABLE IF NOT EXISTS rh_users (
            id BIGSERIAL PRIMARY KEY,
            email VARCHAR(256) NOT NULL UNIQUE,
            hashed_password VARCHAR(512) NOT NULL,
            full_name VARCHAR(256),
            role VARCHAR(64) NOT NULL DEFAULT 'recruiter',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
        );
    """)
    
    op.create_index('ix_rh_users_email', 'rh_users', ['email'], unique=True, if_not_exists=True)
    
    # Créer ai_conversations
    op.create_table(
        'ai_conversations',
        sa.Column('conversation_id', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.BigInteger, sa.ForeignKey('rh_users.id'), nullable=False, index=True),
        sa.Column('title', sa.String(512), nullable=False),
        sa.Column('messages', postgresql.JSONB, nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Index pour améliorer les performances
    op.execute("CREATE INDEX IF NOT EXISTS ix_ai_conversations_user_id ON ai_conversations (user_id)")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS ix_ai_conversations_user_id")
    op.drop_table('ai_conversations')
