"""documents.retention_until, documents.archived_at — 보관 기간과 보관용 폴더 이동 (운영 정책 1장)

이미 처분 완료(approved)된 문서는 approved_at + 3년으로 보관 기간을 채운다 (기본 RETENTION_YEARS).

Revision ID: 3d973e2701d4
Revises: 4cf049c7e645
Create Date: 2026-11-13 17:55:27.098824

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3d973e2701d4'
down_revision: Union[str, Sequence[str], None] = '4cf049c7e645'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('retention_until', sa.DateTime(timezone=True), nullable=True))
    op.add_column('documents', sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))
    # 기존 처분 완료 문서: 처분일부터 3년 (마이그레이션 시점의 기본값. 설정값과 무관하게 고정)
    op.execute(
        "UPDATE documents SET retention_until = approved_at + interval '3 years' "
        "WHERE status = 'approved' AND approved_at IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column('documents', 'archived_at')
    op.drop_column('documents', 'retention_until')
