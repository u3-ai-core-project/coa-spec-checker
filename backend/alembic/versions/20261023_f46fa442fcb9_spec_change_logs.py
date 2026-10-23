"""spec change logs: spec_change_logs 테이블 추가 (규격 변경 이력·사유, 명세 v1.4 4.21)

PATCH /specs/{id} 로 바뀐 값(변경 전·후), 사유, 수정자를 남긴다. 규격 항목을 지우면 이력도 함께 지운다.
작업 2(review_logs.reason, b3cf271e5cdd) 다음 리비전이다.

Revision ID: f46fa442fcb9
Revises: b3cf271e5cdd
Create Date: 2026-10-23 12:31:53.631479

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f46fa442fcb9'
down_revision: Union[str, Sequence[str], None] = 'b3cf271e5cdd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('spec_change_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('spec_item_id', sa.Integer(), nullable=False),
    sa.Column('before_value', sa.Text(), nullable=False),
    sa.Column('after_value', sa.Text(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['spec_item_id'], ['spec_items.id'], name=op.f('fk_spec_change_logs_spec_item_id_spec_items'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_spec_change_logs_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_spec_change_logs'))
    )
    op.create_index(op.f('ix_spec_change_logs_spec_item_id'), 'spec_change_logs', ['spec_item_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_spec_change_logs_spec_item_id'), table_name='spec_change_logs')
    op.drop_table('spec_change_logs')
