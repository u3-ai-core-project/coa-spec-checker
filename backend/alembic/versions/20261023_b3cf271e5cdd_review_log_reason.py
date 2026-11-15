"""review log reason: review_logs.reason 추가 (값 수정 사유, 명세 v1.4 4.9)

값 수정(edit)은 사유를 필수로 받고, 항목명 수정(rename)은 선택, 확인(confirm)은 null 이다.
기존 이력은 null 로 둔다.

Revision ID: b3cf271e5cdd
Revises: b2e8f4a61c37
Create Date: 2026-10-23 12:27:30.651983

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3cf271e5cdd'
down_revision: Union[str, Sequence[str], None] = 'b2e8f4a61c37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('review_logs', sa.Column('reason', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('review_logs', 'reason')
