"""[담당: 홍채령] 정답 라벨·시스템 출력 형식과 읽기.

- 정답 라벨(GTDocument): 문서 1건당 JSON 1개. 형식은 README '정답 라벨 형식'.
- 시스템 출력(PredDocument): 서버 GET /documents/{id}/extraction 응답(ExtractionResult) 또는
  AI 추출 결과(ExtractionInput)를 그대로 읽는다. {"success", "data"} 로 감싼 응답도 된다.

필드를 '안 적음'과 'null' 로 구분한다. 예) 항목에 reason_code 키가 없으면 사유코드는 채점하지 않고,
"reason_code": null 이면 "사유코드 없음(적합)"이 정답이다. 라벨이 단계적으로 채워져도 채점할 수 있게 하기 위해서다.
"""
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.enums import Judgement, LotRecommendation

# 머리글 필드. 시스템 출력에서는 문서 최상위에 있다 (ExtractionResult). 라벨은 header 아래에 둔다.
HEADER_FIELDS = ("supplier", "lot_no", "test_date", "origin", "applied_standard")


class GTItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    normalized_name: str
    raw_value: str | None = None
    unit: str | None = None
    converted_value: float | str | None = None
    judgement: Judgement | None = None
    reason_code: str | None = None  # 라벨에 새 코드가 먼저 생길 수 있어 enum 으로 묶지 않는다


class GTDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")

    document_id: str
    material_code: str | None = None                       # 예: LI2CO3, LIOH
    source: Literal["real", "synthetic"] | None = None     # 실물 / 합성(가상 CoA)
    form: str | None = None                                # 양식 (예: A, B, D, Fisher)
    degradation: str | None = None                         # 열화 단계 (예: original, low_res, skew, blur)
    header: dict[str, str | None] = {}
    items: list[GTItem]
    lot_recommendation: LotRecommendation | None = None
    document_issues: list[str] = []

    def labeled(self, field: str) -> bool:
        return field in self.model_fields_set

    def item_labeled(self, item: GTItem, field: str) -> bool:
        return field in item.model_fields_set


class PredItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    normalized_name: str
    raw_value: str | None = None
    unit: str | None = None
    converted_value: float | str | None = None
    judgement: str | None = None
    reason_code: str | None = None
    confidence: float | None = None
    mapping_source: str | None = None  # "spec" 이면 서버가 만든 누락 항목 (CoA 에 없는 항목)


class PredDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")

    document_id: str
    header: dict[str, str | None] = {}
    items: list[PredItem] = []
    lot_recommendation: str | None = None
    document_issues: list[str] = []

    @field_validator("document_issues", mode="before")
    @classmethod
    def _issue_codes(cls, v: Any) -> list[str]:
        # 서버는 [{"code": ..., "message": ...}] 로 준다
        return [i["code"] if isinstance(i, dict) else i for i in (v or [])]


def _unwrap(raw: dict) -> dict:
    if isinstance(raw, dict) and "data" in raw and "success" in raw:
        return raw["data"]
    return raw


def parse_prediction(raw: dict, fallback_id: str) -> PredDocument:
    raw = dict(_unwrap(raw))
    header = dict(raw.get("header") or {})
    for f in HEADER_FIELDS:
        if f in raw and f not in header:
            header[f] = None if raw[f] is None else str(raw[f])
    raw["header"] = header
    raw.setdefault("document_id", fallback_id)
    return PredDocument.model_validate(raw)


def parse_ground_truth(raw: dict, fallback_id: str) -> GTDocument:
    raw = dict(raw)
    raw.setdefault("document_id", fallback_id)
    return GTDocument.model_validate(raw)


def _load_dir(path: Path, parse) -> dict[str, Any]:
    files = sorted(path.glob("*.json")) if path.is_dir() else [path]
    docs = {}
    for f in files:
        doc = parse(json.loads(f.read_text(encoding="utf-8")), f.stem)
        if doc.document_id in docs:
            raise ValueError(f"document_id 중복: {doc.document_id} ({f})")
        docs[doc.document_id] = doc
    return docs


def load_ground_truth(path: Path) -> dict[str, GTDocument]:
    return _load_dir(path, parse_ground_truth)


def load_predictions(path: Path) -> dict[str, PredDocument]:
    return _load_dir(path, parse_prediction)
