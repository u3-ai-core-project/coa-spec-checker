"""review log respec: review_logs.action 에 respec 추가 (문서 규격 세트 변경 이력)

검수 화면에서 문서의 규격 세트를 바꿔 다시 판정(POST /documents/{id}/rejudge, apply=true)하면
review_logs 에 action='respec' 이력을 남긴다. action 은 VARCHAR + CHECK 라서 CHECK 제약만 다시 만든다.
CHECK 제약은 autogenerate 가 만들지 않으므로(app/db/base.py 참고) 직접 작성했다.

Revision ID: 8e4a1c7d3b52
Revises: 5243f455842c
Create Date: 2026-11-10 09:10:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '8e4a1c7d3b52'
down_revision: Union[str, Sequence[str], None] = '5243f455842c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(op.f('ck_review_logs_action'), 'review_logs', type_='check')
    op.create_check_constraint(
        op.f('ck_review_logs_action'), 'review_logs',
        "action IN ('edit', 'confirm', 'rename', 'respec')",
    )


def downgrade() -> None:
    # 이전 제약은 respec 을 허용하지 않으므로 규격 세트 변경 이력은 지운다 (되돌리면 이 이력은 사라진다)
    op.execute("DELETE FROM review_logs WHERE action = 'respec'")
    op.drop_constraint(op.f('ck_review_logs_action'), 'review_logs', type_='check')
    op.create_check_constraint(
        op.f('ck_review_logs_action'), 'review_logs',
        "action IN ('edit', 'confirm', 'rename')",
    )
