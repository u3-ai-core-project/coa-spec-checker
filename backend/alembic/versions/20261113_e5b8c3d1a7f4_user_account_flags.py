"""users.is_active, users.must_change_password — 계정 비활성화, 첫 로그인 비밀번호 변경 (운영 정책 2단계)

기존 계정은 활성(is_active=true), 비밀번호 변경 필요 없음(must_change_password=false) 으로 채워진다.

Revision ID: e5b8c3d1a7f4
Revises: d7a1e5b3c9f2
Create Date: 2026-11-13 17:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e5b8c3d1a7f4'
down_revision: Union[str, Sequence[str], None] = 'd7a1e5b3c9f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column('users', sa.Column('must_change_password', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    op.drop_column('users', 'must_change_password')
    op.drop_column('users', 'is_active')
