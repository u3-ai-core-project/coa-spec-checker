"""[담당: 장수민] POST /documents, GET /documents, GET /documents/{id}, GET /documents/{id}/file (명세 4.4~4.7)

router 는 router.py 에 이미 등록돼 있다. 이 파일에 엔드포인트만 추가하면 된다.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/documents", tags=["documents"])
