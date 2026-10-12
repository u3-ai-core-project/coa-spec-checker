"""[담당: 장수민] DeclarativeBase 와 공통 컬럼 헬퍼.

모델을 새로 만들면 app/models/__init__.py 에 import 를 추가해야 Alembic autogenerate 가 인식한다.
"""
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, Enum as SAEnum, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# 제약조건 이름 규칙. 마이그레이션에서 이름이 매번 같게 나오도록 고정한다.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def str_enum(enum_cls: type[StrEnum], name: str):
    """StrEnum 을 VARCHAR 로 저장. DB 에는 .value(소문자 등) 가 들어간다.

    CHECK 제약은 enum_check() 로 __table_args__ 에 따로 선언한다.
    (create_constraint=True 를 쓰면 Alembic autogenerate 가 CHECK 를 두 번 만든다.)
    """
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=False,
        length=32,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


def enum_check(column: str, enum_cls: type[StrEnum]) -> CheckConstraint:
    """컬럼 값이 enum 값 중 하나인지 DB 에서 검사. 이름은 ck_<table>_<column>."""
    values = ", ".join(f"'{m.value}'" for m in enum_cls)
    return CheckConstraint(f"{column} IN ({values})", name=column)


def created_at_col() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
