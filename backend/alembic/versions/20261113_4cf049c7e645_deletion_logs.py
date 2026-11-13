"""deletion_logs 테이블 — 문서 삭제 기록과 삭제 직전 처분·검수 이력 요약 (운영 정책 1장)

문서가 지워져도 남아야 하므로 document_id 에 FK 를 걸지 않는다.

Revision ID: 4cf049c7e645
Revises: f2c6a9e4b1d3
Create Date: 2026-11-13 17:46:30.405042

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '4cf049c7e645'
down_revision: Union[str, Sequence[str], None] = 'f2c6a9e4b1d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('deletion_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.String(length=36), nullable=True),
    sa.Column('file_name', sa.String(length=255), nullable=False),
    sa.Column('file_size', sa.BigInteger(), nullable=True),
    sa.Column('file_sha256', sa.String(length=64), nullable=True),
    sa.Column('material_code', sa.String(length=32), nullable=True),
    sa.Column('supplier', sa.String(length=200), nullable=True),
    sa.Column('lot_no', sa.String(length=100), nullable=True),
    sa.Column('received_lot_no', sa.String(length=100), nullable=True),
    sa.Column('batch_id', sa.String(length=36), nullable=True),
    sa.Column('status_at_delete', sa.String(length=32), nullable=True),
    sa.Column('uploaded_by', sa.Integer(), nullable=True),
    sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.Integer(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('rule', sa.Enum('manual', 'auto_failed_7d', 'auto_orphan_file', 'batch_delete', name='deletion_rule', native_enum=False, length=32), nullable=False),
    sa.Column('approval_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('review_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.CheckConstraint("rule IN ('manual', 'auto_failed_7d', 'auto_orphan_file', 'batch_delete')", name=op.f('ck_deletion_logs_rule')),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], name=op.f('fk_deletion_logs_deleted_by_users')),
    sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], name=op.f('fk_deletion_logs_uploaded_by_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_deletion_logs'))
    )
    op.create_index(op.f('ix_deletion_logs_document_id'), 'deletion_logs', ['document_id'], unique=False)
    op.create_index(op.f('ix_deletion_logs_lot_no'), 'deletion_logs', ['lot_no'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_deletion_logs_lot_no'), table_name='deletion_logs')
    op.drop_index(op.f('ix_deletion_logs_document_id'), table_name='deletion_logs')
    op.drop_table('deletion_logs')
