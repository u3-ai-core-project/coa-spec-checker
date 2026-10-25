"""batches receipts: 일괄 접수 테이블 추가 (batches, receipts, documents.batch_id. 멘토님 UC01·UC07, 명세 v1.4 4.4-1)

CoA 여러 건과 입고 정보 CSV 를 한 번에 올린다. 입고 행은 file_name 또는 CoA 로트번호로 문서와 연결한다.
spec_change_logs(f46fa442fcb9) 다음 리비전이다.

Revision ID: 5243f455842c
Revises: f46fa442fcb9
Create Date: 2026-10-25 13:40:28.834212

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5243f455842c'
down_revision: Union[str, Sequence[str], None] = 'f46fa442fcb9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('batches',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('material_code', sa.String(length=32), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_batches_created_by_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_batches'))
    )
    op.create_index(op.f('ix_batches_created_by'), 'batches', ['created_by'], unique=False)
    op.create_table('receipts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('batch_id', sa.String(length=36), nullable=False),
    sa.Column('receipt_id', sa.String(length=100), nullable=False),
    sa.Column('supplier', sa.String(length=200), nullable=True),
    sa.Column('material_code', sa.String(length=32), nullable=False),
    sa.Column('received_lot_no', sa.String(length=100), nullable=False),
    sa.Column('spec_set_code', sa.String(length=64), nullable=True),
    sa.Column('received_date', sa.Date(), nullable=True),
    sa.Column('file_name', sa.String(length=255), nullable=True),
    sa.Column('document_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['batch_id'], ['batches.id'], name=op.f('fk_receipts_batch_id_batches'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], name=op.f('fk_receipts_document_id_documents'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_receipts')),
    sa.UniqueConstraint('batch_id', 'receipt_id', name=op.f('uq_receipts_batch_id_receipt_id'))
    )
    op.create_index(op.f('ix_receipts_batch_id'), 'receipts', ['batch_id'], unique=False)
    op.create_index(op.f('ix_receipts_document_id'), 'receipts', ['document_id'], unique=False)
    op.add_column('documents', sa.Column('batch_id', sa.String(length=36), nullable=True))
    op.create_index(op.f('ix_documents_batch_id'), 'documents', ['batch_id'], unique=False)
    op.create_foreign_key(op.f('fk_documents_batch_id_batches'), 'documents', 'batches', ['batch_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint(op.f('fk_documents_batch_id_batches'), 'documents', type_='foreignkey')
    op.drop_index(op.f('ix_documents_batch_id'), table_name='documents')
    op.drop_column('documents', 'batch_id')
    op.drop_index(op.f('ix_receipts_document_id'), table_name='receipts')
    op.drop_index(op.f('ix_receipts_batch_id'), table_name='receipts')
    op.drop_table('receipts')
    op.drop_index(op.f('ix_batches_created_by'), table_name='batches')
    op.drop_table('batches')
