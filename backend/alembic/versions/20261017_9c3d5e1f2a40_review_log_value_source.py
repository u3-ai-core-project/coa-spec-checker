"""review log value source: review_logs.value_source 추가 (검수 API 값 입력 출처, v1.4안)

값 수정(edit) 이력에 입력값의 출처(correction | supplier_reply | internal_test)를 남긴다.
CHECK 제약은 autogenerate 가 만들지 않으므로(app/db/base.py 참고) 직접 추가했다.

Revision ID: 9c3d5e1f2a40
Revises: 7b1e4c2a9d10
Create Date: 2026-10-17 11:46:11.250071

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c3d5e1f2a40'
down_revision: Union[str, Sequence[str], None] = '7b1e4c2a9d10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('review_logs', sa.Column('value_source', sa.Enum('correction', 'supplier_reply', 'internal_test', name='value_source', native_enum=False, length=32), nullable=True))
    op.create_check_constraint(
        op.f('ck_review_logs_value_source'), 'review_logs',
        "value_source IN ('correction', 'supplier_reply', 'internal_test')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_review_logs_value_source'), 'review_logs', type_='check')
    op.drop_column('review_logs', 'value_source')
