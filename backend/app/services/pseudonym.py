"""[담당: 홍채령] 팀 밖에 자료를 공유할 때 사용자 이름 가명 처리 (운영 정책 3장).

"팀 밖에 자료를 공유할 때는 사용자 이름을 제거하거나 가명 처리한다."

사용자 이름이 들어가는 백엔드 출력물은 엑셀 검수 리포트다 (업로드한 사람, 수정·확인 이력 담당자, 처분 이력 담당자, 처분자).
대시보드·평가 스크립트 출력에는 사용자 이름이 없다 (사용자 id 로만 거른다).

    names = Pseudonymizer(db)           # 켜면 이름 → "담당자 A", "담당자 B" ...
    names.user(doc.uploader)            # 이름 칸
    names.text(log.reason)              # 사유 같은 자유 입력 글 안의 이름도 바꾼다

- 같은 파일 안에서는 같은 사람이 늘 같은 가명이다. 처음 나온 순서대로 A, B, C ... (26명 넘으면 AA, AB ...)
- 다른 파일과는 가명이 이어지지 않는다 (파일 여러 개를 모아도 같은 사람인지 맞춰 보기 어렵게)
- 사유 글에서는 등록된 모든 사용자 이름(2글자 이상)을 찾아 바꾼다. 긴 이름부터 바꿔 "김검수"와 "김검"이 겹쳐도 맞게 바꾼다.
  다만 등록되지 않은 사람 이름이나 줄임말·별명은 찾지 못한다. 공유 전에 사유 칸을 한 번 훑어보는 것이 안전하다
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User

LABEL = "담당자"
MIN_NAME_LENGTH = 2  # 한 글자 이름은 다른 낱말 속 글자와 헷갈리므로 자유 글에서는 바꾸지 않는다


def letters(n: int) -> str:
    """0 → A, 25 → Z, 26 → AA, 27 → AB ..."""
    out = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(ord("A") + r) + out
    return out


class Pseudonymizer:
    """enabled=False 면 아무것도 바꾸지 않는다 (사내용 기본)."""

    def __init__(self, db: Session | None = None, *, enabled: bool = True):
        self.enabled = enabled
        self._by_id: dict[int, str] = {}
        self._names: dict[int, str] = {}  # 자유 글에서 찾을 이름 {user_id: 이름}
        if enabled and db is not None:
            self._names = {uid: name for uid, name in db.execute(select(User.id, User.name)) if name}

    def _alias(self, user_id: int) -> str:
        if user_id not in self._by_id:
            self._by_id[user_id] = f"{LABEL} {letters(len(self._by_id))}"
        return self._by_id[user_id]

    def user(self, user: User | None) -> str | None:
        if user is None:
            return None
        if not self.enabled:
            return user.name
        self._names.setdefault(user.id, user.name)
        return self._alias(user.id)

    def text(self, value: str | None) -> str | None:
        if not self.enabled or not value:
            return value
        candidates = sorted(((name, uid) for uid, name in self._names.items() if len(name.strip()) >= MIN_NAME_LENGTH),
                            key=lambda p: -len(p[0]))
        for name, uid in candidates:
            if name in value:
                value = value.replace(name, self._alias(uid))
        return value
