"""[담당: 홍채령] 이상 패턴 (4.17)"""
from typing import Literal

from pydantic import BaseModel

# 명세 v1.4안 4.17 에서 남는 유형은 identical_values, at_spec_limit 이다.
# at_spec_limit 은 기획안 v2 와 명세가 달라 확정 전이라 아직 넣지 않았다 (2026-10-25).
AnomalyType = Literal["identical_values"]


class AnomalyOut(BaseModel):
    type: AnomalyType
    item_name: str | None
    message: str
    related_document_ids: list[str]
