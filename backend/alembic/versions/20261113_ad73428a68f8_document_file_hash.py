"""documents.file_sha256, documents.duplicate_of — 같은 파일 다시 올리기 경고 (운영 정책 1장)

기존 문서는 원본 파일을 읽을 수 있으면 해시를 채운다. 파일이 없거나 못 읽으면 비워 둔다 (경고 대상에서 빠질 뿐).

Revision ID: ad73428a68f8
Revises: 2caf8269a66b
Create Date: 2026-11-13 18:36:26.791522

"""
from typing import Sequence, Union

import hashlib
from pathlib import Path

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ad73428a68f8'
down_revision: Union[str, Sequence[str], None] = '2caf8269a66b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('file_sha256', sa.String(length=64), nullable=True))
    op.add_column('documents', sa.Column('duplicate_of', sa.String(length=36), nullable=True))
    op.create_index(op.f('ix_documents_file_sha256'), 'documents', ['file_sha256'], unique=False)
    op.create_foreign_key(op.f('fk_documents_duplicate_of_documents'), 'documents', 'documents', ['duplicate_of'], ['id'], ondelete='SET NULL')

    # 기존 파일 해시 채우기 (읽을 수 있는 파일만). 경로는 서버를 실행하는 폴더(backend) 기준 상대 경로일 수 있다
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, file_path FROM documents WHERE file_sha256 IS NULL")).fetchall()
    for doc_id, file_path in rows:
        try:
            h = hashlib.sha256()
            with Path(file_path).open("rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
        except (OSError, TypeError):
            continue
        conn.execute(sa.text("UPDATE documents SET file_sha256 = :h WHERE id = :id"), {"h": h.hexdigest(), "id": doc_id})


def downgrade() -> None:
    op.drop_constraint(op.f('fk_documents_duplicate_of_documents'), 'documents', type_='foreignkey')
    op.drop_index(op.f('ix_documents_file_sha256'), table_name='documents')
    op.drop_column('documents', 'duplicate_of')
    op.drop_column('documents', 'file_sha256')
