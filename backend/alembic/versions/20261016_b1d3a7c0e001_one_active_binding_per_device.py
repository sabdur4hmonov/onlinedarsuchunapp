"""one active binding per device

Revision ID: b1d3a7c0e001
Revises: e56df9d0e0af
Create Date: 2026-10-16 22:22:21.473380

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b1d3a7c0e001'
down_revision: Union[str, None] = 'e56df9d0e0af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A device_id can be ACTIVELY bound to only one account (reset rows are ignored)
    op.create_index('uq_devices_active_device_id', 'devices', ['device_id'], unique=True, postgresql_where=sa.text('is_active'))


def downgrade() -> None:
    op.drop_index('uq_devices_active_device_id', table_name='devices', postgresql_where=sa.text('is_active'))
