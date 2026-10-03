"""[담당: 장수민] GET /specs, PATCH /specs/{id} (명세 4.20, 4.21)

router 는 router.py 에 이미 등록돼 있다. 이 파일에 엔드포인트만 추가하면 된다.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/specs", tags=["specs"])
