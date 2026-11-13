"""documents 처리 실패·재시도 기록과 추출 작동 시간 (운영 정책 4장, 7장)

attempt_count, failed_stage, error_kind: 추출 시도 횟수와 실패 단계·종류
processing_started_at, processing_finished_at: 마지막 추출 시도의 시작·종료 시각 (실제 작동 시간 지표용)
CHECK 제약은 autogenerate 가 만들지 않으므로(app/db/base.py 참고) 직접 작성했다.

Revision ID: c4d9a2e7f1b8
Revises: 8e4a1c7d3b52
Create Date: 2026-11-13 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c4d9a2e7f1b8'
down_revision: Union[str, Sequence[str], None] = '8e4a1c7d3b52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('attempt_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('documents', sa.Column('failed_stage', sa.String(length=32), nullable=True))
    op.add_column('documents', sa.Column('error_kind', sa.String(length=32), nullable=True))
    op.add_column('documents', sa.Column('processing_started_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('documents', sa.Column('processing_finished_at', sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        op.f('ck_documents_error_kind'), 'documents',
        "error_kind IN ('permanent', 'transient')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_documents_error_kind'), 'documents', type_='check')
    op.drop_column('documents', 'processing_finished_at')
    op.drop_column('documents', 'processing_started_at')
    op.drop_column('documents', 'error_kind')
    op.drop_column('documents', 'failed_stage')
    op.drop_column('documents', 'attempt_count')
