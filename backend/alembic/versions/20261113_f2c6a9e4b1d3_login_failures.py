"""login_failures 테이블 — 로그인 실패 횟수와 잠금 (운영 정책 3단계)

Revision ID: f2c6a9e4b1d3
Revises: e5b8c3d1a7f4
Create Date: 2026-11-13 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f2c6a9e4b1d3'
down_revision: Union[str, Sequence[str], None] = 'e5b8c3d1a7f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'login_failures',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=100), nullable=False),
        sa.Column('ip', sa.String(length=64), nullable=False),
        sa.Column('fail_count', sa.Integer(), nullable=False),
        sa.Column('last_failed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username', 'ip', name='uq_login_failures_username_ip'),
    )
    op.create_index(op.f('ix_login_failures_username'), 'login_failures', ['username'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_login_failures_username'), table_name='login_failures')
    op.drop_table('login_failures')
