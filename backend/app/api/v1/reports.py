"""[담당: 장수민] GET /documents/{id}/report (명세 4.16)

router 는 router.py 에 이미 등록돼 있다. 이 파일에 엔드포인트만 추가하면 된다.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/documents", tags=["reports"])
