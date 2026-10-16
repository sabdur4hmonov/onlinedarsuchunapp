"""used refresh tokens for reuse detection

Revision ID: b1d3a7c0e002
Revises: b1d3a7c0e001
Create Date: 2026-10-16 22:22:21.473380

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b1d3a7c0e002'
down_revision: Union[str, None] = 'b1d3a7c0e001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('used_refresh_tokens',
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('session_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('rotated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], name=op.f('fk_used_refresh_tokens_session_id_sessions')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_used_refresh_tokens_user_id_users')),
    sa.PrimaryKeyConstraint('token_hash', name=op.f('pk_used_refresh_tokens'))
    )
    op.create_index(op.f('ix_used_refresh_tokens_session_id'), 'used_refresh_tokens', ['session_id'], unique=False)
    op.create_index(op.f('ix_used_refresh_tokens_user_id'), 'used_refresh_tokens', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_used_refresh_tokens_user_id'), table_name='used_refresh_tokens')
    op.drop_index(op.f('ix_used_refresh_tokens_session_id'), table_name='used_refresh_tokens')
    op.drop_table('used_refresh_tokens')
