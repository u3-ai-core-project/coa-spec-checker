"""[담당: 홍채령] login_failures 테이블 — 로그인 실패 횟수와 잠금 (운영 정책 3단계).

(아이디 소문자, 접속 IP) 한 쌍마다 한 줄. DB 에 두므로 서버를 다시 켜도 잠금이 유지된다.
IP 까지 묶는 이유: 다른 PC 에서 남의 아이디로 일부러 틀려서 진짜 사용자를 잠그지 못하게 하려고.
없는 아이디도 똑같이 센다 (어떤 아이디가 있는지 알아낼 수 없게).
비밀번호는 저장하지 않는다.
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LoginFailure(Base):
    __tablename__ = "login_failures"
    __table_args__ = (UniqueConstraint("username", "ip", name="uq_login_failures_username_ip"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # 소문자로 저장
    ip: Mapped[str] = mapped_column(String(64), nullable=False)
    fail_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
