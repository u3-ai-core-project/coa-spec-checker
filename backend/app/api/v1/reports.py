"""[담당: 장수민] GET /documents/{id}/report (명세 4.16)

요청할 때마다 엑셀을 새로 만들어 돌려준다. 생성 규칙은 report_service 에 있다.
파일명에 한글이 들어가므로 Content-Disposition 에 filename*(UTF-8) 을 함께 넣는다 (RFC 6266).
프론트는 main.py 의 expose_headers 설정 덕분에 이 헤더를 읽을 수 있다.
"""
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.services import report_service

router = APIRouter(prefix="/documents", tags=["reports"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/{document_id}/report", response_class=Response, responses={200: {"content": {XLSX: {}}}})
def download_report(
    document_id: str,
    pseudonymize: bool = Query(False, description="운영 정책 3장: 팀 밖 공유용. 사용자 이름을 '담당자 A' 같은 가명으로 바꾼다"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """엑셀 검수 리포트 (로트 1건 = 1시트 + 문의 초안 시트). 미처분 문서는 처분 칸을 비워서 출력한다.

    ?pseudonymize=true 면 이름 칸(업로드·담당자·처분자)과 사유 글 속 등록 사용자 이름을 가명으로 바꾸고, 파일명 끝에 _가명 을 붙인다.
    기본(false)은 사내용으로 실명 그대로다.
    """
    content, file_name = report_service.generate_report(db, document_id, pseudonymize=pseudonymize)
    disposition = f"attachment; filename=\"coa_report.xlsx\"; filename*=UTF-8''{quote(file_name)}"
    return Response(content=content, media_type=XLSX, headers={"Content-Disposition": disposition})
