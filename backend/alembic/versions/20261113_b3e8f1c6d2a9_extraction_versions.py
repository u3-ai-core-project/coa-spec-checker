"""extraction_results.versions — 추출·판정 근거 버전 기록 (운영 정책 6장)

기존 결과는 어떤 버전으로 읽었는지 알 수 없으므로 비워 둔다 (null). 다시 처리하거나 재판정하면 채워진다.

Revision ID: b3e8f1c6d2a9
Revises: ad73428a68f8
Create Date: 2026-11-13 20:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b3e8f1c6d2a9'
down_revision: Union[str, Sequence[str], None] = 'ad73428a68f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('extraction_results', sa.Column('versions', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('extraction_results', 'versions')
