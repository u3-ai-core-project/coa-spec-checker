"""[담당: 홍채령] 이상 패턴 (4.17)"""
from typing import Literal

from pydantic import BaseModel

# 명세 v1.4안 4.17 에서 남는 유형 (lot_mismatch·issued_before_test 는 document_issues, spec_text_as_result 는 SPEC_COPIED 로 이동)
AnomalyType = Literal["identical_values", "at_spec_limit"]


class AnomalyOut(BaseModel):
    type: AnomalyType
    item_name: str | None
    message: str
    related_document_ids: list[str]
