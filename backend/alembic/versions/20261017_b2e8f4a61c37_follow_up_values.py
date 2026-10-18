"""follow up values: 보류 후속 조치(follow_up) 값 3개 추가 (명세 v1.4안 4.13)

request_single_value(개별값 요청), request_reissue(CoA 재발행 요청), request_correct_coa(올바른 CoA 요청)
follow_up 은 VARCHAR + CHECK 로 저장하므로(app/db/base.py) CHECK 제약만 바꾸면 된다.
autogenerate 는 CHECK 변경을 감지하지 못해 직접 작성했다.

Revision ID: b2e8f4a61c37
Revises: 9c3d5e1f2a40
Create Date: 2026-10-17 11:55:00

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b2e8f4a61c37'
down_revision: Union[str, Sequence[str], None] = '9c3d5e1f2a40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD = ('request_actual_value', 'request_detection_limit', 'internal_test', 'other')
NEW = ('request_actual_value', 'request_detection_limit', 'internal_test',
       'request_single_value', 'request_reissue', 'request_correct_coa', 'other')


def _replace_check(values: tuple[str, ...]) -> None:
    op.drop_constraint(op.f('ck_approval_logs_follow_up'), 'approval_logs', type_='check')
    allowed = ", ".join(f"'{v}'" for v in values)
    op.create_check_constraint(op.f('ck_approval_logs_follow_up'), 'approval_logs', f"follow_up IN ({allowed})")


def upgrade() -> None:
    _replace_check(NEW)


def downgrade() -> None:
    # 새 값으로 기록된 보류 이력은 되돌릴 수 없으므로 other 로 바꾼다
    op.execute(
        "UPDATE approval_logs SET follow_up = 'other' "
        "WHERE follow_up IN ('request_single_value', 'request_reissue', 'request_correct_coa')"
    )
    _replace_check(OLD)
