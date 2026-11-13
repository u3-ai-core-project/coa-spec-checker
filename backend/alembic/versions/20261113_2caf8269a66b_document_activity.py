"""documents.last_activity_at, documents.stale_notified_at — 방치 문서 표시 (운영 정책 1장)

기존 문서의 마지막 활동은 업로드·검수 이력·처분 이력 중 가장 늦은 시각으로 채운다.

Revision ID: 2caf8269a66b
Revises: 3d973e2701d4
Create Date: 2026-11-13 18:08:20.527342

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2caf8269a66b'
down_revision: Union[str, Sequence[str], None] = '3d973e2701d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('last_activity_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('documents', sa.Column('stale_notified_at', sa.DateTime(timezone=True), nullable=True))
    # 기존 문서: 업로드, 마지막 검수(review_logs), 마지막 처분·보류·취소(approval_logs) 중 가장 늦은 시각
    op.execute("""
        UPDATE documents d SET last_activity_at = GREATEST(
            d.uploaded_at,
            COALESCE((SELECT max(r.reviewed_at) FROM review_logs r WHERE r.document_id = d.id), d.uploaded_at),
            COALESCE((SELECT max(a.created_at) FROM approval_logs a WHERE a.document_id = d.id), d.uploaded_at)
        )
    """)


def downgrade() -> None:
    op.drop_column('documents', 'stale_notified_at')
    op.drop_column('documents', 'last_activity_at')
