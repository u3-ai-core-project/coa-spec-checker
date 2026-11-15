"""reissue_decisions 테이블 — 같은 로트 재발행 CoA 의 기준 버전 선택 (운영 정책 8.2)

Revision ID: d7a1e5b3c9f2
Revises: c4d9a2e7f1b8
Create Date: 2026-11-13 13:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd7a1e5b3c9f2'
down_revision: Union[str, Sequence[str], None] = 'c4d9a2e7f1b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'reissue_decisions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('material_code', sa.String(length=32), nullable=False),
        sa.Column('lot_key', sa.String(length=100), nullable=False),
        sa.Column('base_document_id', sa.String(length=36), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['base_document_id'], ['documents.id'],
                                name=op.f('fk_reissue_decisions_base_document_id_documents'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_reissue_decisions_user_id_users')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_reissue_decisions')),
    )
    op.create_index(op.f('ix_reissue_decisions_base_document_id'), 'reissue_decisions', ['base_document_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_reissue_decisions_base_document_id'), table_name='reissue_decisions')
    op.drop_table('reissue_decisions')
