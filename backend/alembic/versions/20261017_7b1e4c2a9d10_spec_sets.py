"""spec sets: 규격 세트 테이블 추가, spec_items 를 세트 단위로 변경 (명세 v1.4안 2.5)

- spec_sets 신규 (원자재 + 등급 + 버전)
- spec_items: spec_set_id, is_required 추가 / material_code, material_name, grade 제거
              유일 조건 (material_code, item_name) → (spec_set_id, item_name)
- documents.spec_set_id 추가 (판정에 쓴 규격 세트)

기존 데이터 이전
  이미 spec_items 에 행이 있으면 (material_code, material_name, grade) 조합마다 세트를 하나 만들어 옮긴다.
  세트 코드는 "<material_code>-<grade>" (grade 가 없으면 "<material_code>-DEFAULT"),
  원자재별로 id 가 가장 작은 세트를 기본 세트로 둔다. 기존 문서는 해당 원자재의 기본 세트로 연결한다.
  (시드가 비어 있던 상태라 보통은 옮길 행이 없다.)

Revision ID: 7b1e4c2a9d10
Revises: 65d7278a507d
Create Date: 2026-10-17 11:17:21.943242

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7b1e4c2a9d10'
down_revision: Union[str, Sequence[str], None] = '65d7278a507d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. spec_sets
    op.create_table('spec_sets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('material_code', sa.String(length=32), nullable=False),
    sa.Column('material_name', sa.String(length=100), nullable=False),
    sa.Column('grade', sa.String(length=20), nullable=True),
    sa.Column('version', sa.String(length=50), nullable=True),
    sa.Column('source', sa.String(length=200), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_default', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_spec_sets')),
    sa.UniqueConstraint('code', name=op.f('uq_spec_sets_code'))
    )
    op.create_index(op.f('ix_spec_sets_material_code'), 'spec_sets', ['material_code'], unique=False)
    op.create_index('uq_spec_sets_default_per_material', 'spec_sets', ['material_code'], unique=True,
                    postgresql_where=sa.text('is_default'))

    # 2. spec_items 에 새 컬럼 (spec_set_id 는 데이터 이전 후 NOT NULL 로 바꾼다)
    op.add_column('spec_items', sa.Column('spec_set_id', sa.Integer(), nullable=True))
    op.add_column('spec_items', sa.Column('is_required', sa.Boolean(), server_default=sa.text('true'), nullable=False))

    # 3. 기존 행 → 세트로 이전
    op.execute("""
        INSERT INTO spec_sets (code, material_code, material_name, grade, is_default)
        SELECT material_code || '-' || COALESCE(grade, 'DEFAULT'), material_code, MIN(material_name), grade, false
        FROM spec_items
        GROUP BY material_code, grade
    """)
    op.execute("""
        UPDATE spec_sets s SET is_default = true
        WHERE s.id = (SELECT MIN(id) FROM spec_sets t WHERE t.material_code = s.material_code)
    """)
    op.execute("""
        UPDATE spec_items i SET spec_set_id = s.id
        FROM spec_sets s
        WHERE s.material_code = i.material_code AND s.grade IS NOT DISTINCT FROM i.grade
    """)
    op.alter_column('spec_items', 'spec_set_id', nullable=False)

    # 4. 제약·인덱스 교체, 옛 컬럼 제거
    op.drop_index(op.f('ix_spec_items_material_code'), table_name='spec_items')
    op.drop_constraint(op.f('uq_spec_items_material_code_item_name'), 'spec_items', type_='unique')
    op.create_index(op.f('ix_spec_items_spec_set_id'), 'spec_items', ['spec_set_id'], unique=False)
    op.create_unique_constraint(op.f('uq_spec_items_spec_set_id_item_name'), 'spec_items', ['spec_set_id', 'item_name'])
    op.create_foreign_key(op.f('fk_spec_items_spec_set_id_spec_sets'), 'spec_items', 'spec_sets',
                          ['spec_set_id'], ['id'], ondelete='CASCADE')
    op.drop_column('spec_items', 'grade')
    op.drop_column('spec_items', 'material_name')
    op.drop_column('spec_items', 'material_code')

    # 5. documents.spec_set_id (기존 문서는 원자재 기본 세트로 연결)
    op.add_column('documents', sa.Column('spec_set_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_documents_spec_set_id'), 'documents', ['spec_set_id'], unique=False)
    op.create_foreign_key(op.f('fk_documents_spec_set_id_spec_sets'), 'documents', 'spec_sets', ['spec_set_id'], ['id'])
    op.execute("""
        UPDATE documents d SET spec_set_id = s.id
        FROM spec_sets s
        WHERE s.material_code = d.material_code AND s.is_default
    """)


def downgrade() -> None:
    # documents
    op.drop_constraint(op.f('fk_documents_spec_set_id_spec_sets'), 'documents', type_='foreignkey')
    op.drop_index(op.f('ix_documents_spec_set_id'), table_name='documents')
    op.drop_column('documents', 'spec_set_id')

    # spec_items 옛 컬럼 복원 (세트 정보를 다시 펼친다)
    op.add_column('spec_items', sa.Column('material_code', sa.VARCHAR(length=32), nullable=True))
    op.add_column('spec_items', sa.Column('material_name', sa.VARCHAR(length=100), nullable=True))
    op.add_column('spec_items', sa.Column('grade', sa.VARCHAR(length=20), nullable=True))
    op.execute("""
        UPDATE spec_items i SET material_code = s.material_code, material_name = s.material_name, grade = s.grade
        FROM spec_sets s WHERE s.id = i.spec_set_id
    """)
    # 같은 원자재에 세트가 여러 개면 (material_code, item_name) 유일 조건을 만들 수 없으므로 기본 세트 외 항목은 지운다
    op.execute("""
        DELETE FROM spec_items i USING spec_sets s
        WHERE s.id = i.spec_set_id AND NOT s.is_default
    """)
    op.alter_column('spec_items', 'material_code', nullable=False)
    op.alter_column('spec_items', 'material_name', nullable=False)

    op.drop_constraint(op.f('fk_spec_items_spec_set_id_spec_sets'), 'spec_items', type_='foreignkey')
    op.drop_constraint(op.f('uq_spec_items_spec_set_id_item_name'), 'spec_items', type_='unique')
    op.drop_index(op.f('ix_spec_items_spec_set_id'), table_name='spec_items')
    op.create_unique_constraint(op.f('uq_spec_items_material_code_item_name'), 'spec_items', ['material_code', 'item_name'])
    op.create_index(op.f('ix_spec_items_material_code'), 'spec_items', ['material_code'], unique=False)
    op.drop_column('spec_items', 'is_required')
    op.drop_column('spec_items', 'spec_set_id')

    # spec_sets
    op.drop_index('uq_spec_sets_default_per_material', table_name='spec_sets', postgresql_where=sa.text('is_default'))
    op.drop_index(op.f('ix_spec_sets_material_code'), table_name='spec_sets')
    op.drop_table('spec_sets')
