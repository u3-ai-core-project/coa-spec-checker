"""[담당: 홍채령] 문서 활동 기록 (운영 정책 1장: 방치 문서).

"값·항목명 수정, 항목 확인, 보류·후속 조치 기록을 하면 기간을 다시 센다. 단순 조회는 제외한다."
쓰기 API 의 공통 저장 지점(review_service._save, approval_service._finish)에서 touch() 를 부른다. 조회 API 는 부르지 않는다.
"""
from sqlalchemy import func

from app.models import Document


def touch(doc: Document) -> None:
    """마지막 활동 시각을 지금으로 바꾸고 방치 표시를 지운다. commit 은 호출한 쪽에서 한다."""
    doc.last_activity_at = func.now()
    doc.stale_notified_at = None
