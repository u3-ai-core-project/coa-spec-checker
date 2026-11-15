"""[담당: 홍채령] GET /documents/{id}/anomalies (명세 4.17, 확장)

router 는 router.py 에 이미 등록돼 있다. 이 파일에 엔드포인트만 추가하면 된다.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.response import ok
from app.db.session import get_db
from app.models import User
from app.schemas.anomaly import AnomalyOut
from app.schemas.common import ApiResponse
from app.services import anomaly_service

router = APIRouter(prefix="/documents", tags=["anomalies"])


@router.get("/{document_id}/anomalies", response_model=ApiResponse[list[AnomalyOut]])
def get_anomalies(document_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """이상 패턴 참고 경고. 판정·로트 권고에는 영향을 주지 않는다. 추출 전 문서는 빈 목록."""
    return ok(anomaly_service.get_anomalies(db, document_id))
