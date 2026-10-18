"""[담당: 장수민] spec_sets 테이블 — 사내 규격 세트 (명세 v1.4안 2.5).

규격 세트 = 원자재 + 등급 + 규격 버전 하나의 묶음이다. 예)
    LI2CO3-D1-2023   탄산리튬 D1 (YS/T 582-2023 기반)
    LI2CO3-D3-2023   탄산리튬 D3
    LI2CO3-DEMO-R    실물 CoA 시연용 (CoA 에 실리는 항목만 필수)

왜 세트로 나눴나
  - 기존 spec_items 는 (material_code, item_name) 이 유일해서 같은 원자재에 D1·D3, 2006·2023 버전을
    함께 넣을 수 없었다. 등급·버전 비교(데모 03·04·18로트)와 규격 개정 재판정(S6)을 하려면 세트 단위가 필요하다.
  - 세트를 몇 개 넣을지는 팀 결정 사항(안건 4)이다. D1 하나만 넣어도, 여러 개를 넣어도 같은 구조로 동작한다.

is_default
  - 업로드 때 세트를 지정하지 않으면 해당 원자재의 기본 세트를 쓴다. 원자재마다 기본 세트는 하나만 둔다
    (부분 유일 인덱스 uq_spec_sets_default_per_material).
"""
from datetime import datetime

from sqlalchemy import Boolean, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_col


class SpecSet(Base):
    __tablename__ = "spec_sets"
    __table_args__ = (
        # 원자재마다 기본 세트는 하나 (PostgreSQL 부분 유일 인덱스)
        Index(
            "uq_spec_sets_default_per_material",
            "material_code",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # 세트 식별 코드. 업로드 API 의 spec_set_code, 시드 CSV 의 spec_set_code 와 같은 값
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    material_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # 예: LI2CO3
    material_name: Mapped[str] = mapped_column(String(100), nullable=False)              # 예: 탄산리튬
    grade: Mapped[str | None] = mapped_column(String(20))      # 예: D1, D3, DEMO-R
    version: Mapped[str | None] = mapped_column(String(50))    # 예: YS/T 582-2023
    source: Mapped[str | None] = mapped_column(String(200))    # 세트 전체의 근거 (항목별 근거는 spec_items.source)
    description: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = created_at_col()

    items: Mapped[list["SpecItem"]] = relationship(  # noqa: F821
        back_populates="spec_set", cascade="all, delete-orphan", order_by="SpecItem.id"
    )
