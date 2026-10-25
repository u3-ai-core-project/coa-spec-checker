"""[담당: 홍채령] 이상 패턴 계산 (읽기 전용)

명세 4.17: 요청 시점에 기존 테이블을 읽어 계산하고 DB 에 쓰지 않는다. 판정과 로트 권고에는 영향을 주지 않고
검수 화면에 참고 경고로만 보여 준다. 멘토님 기준에 따라 '위조' 같은 표현은 쓰지 않는다.
"""
import math
import re

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.enums import ReasonCode, ValueQualifier
from app.models import Document
from app.schemas.anomaly import AnomalyOut
from app.services import document_service
from app.services.judgement.value_parser import UnitConversionError, convert_unit, is_spec_text_as_result

_NUM_UNIT = re.compile(r"(?<![A-Za-z\d.])(?P<num>\d+(?:\.\d+)?|\.\d+)\s*(?P<unit>%|ppm|ppb|mg/kg|μg/kg|µg/kg|wt%)?", re.IGNORECASE)


def get_anomalies(db: Session, document_id: str) -> list[AnomalyOut]:
    doc = document_service.get_document(db, document_id)
    return _identical_values(db, doc) + _at_spec_limit(doc)


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", "", text or "").casefold()


def _items(doc: Document) -> list[dict]:
    return doc.extraction.result.get("items", []) if doc.extraction else []


def _reported_values(doc: Document) -> dict[str, tuple[str, str]]:
    """{항목명: (정리한 원문 값, 원문 값)}. 실측값(exact)만 본다.

    '< 20', 검출 안 됨, 규격 문구 복사 같은 값은 로트가 달라도 같게 적히는 게 자연스러워서 뺀다.
    """
    values = {}
    for item in _items(doc):
        raw = item.get("raw_value")
        if item.get("value_qualifier") == ValueQualifier.EXACT and raw and item.get("reason_code") != ReasonCode.SPEC_COPIED:
            values.setdefault(item["normalized_name"], (_norm(raw), raw.strip()))
    return values


def _identical_values(db: Session, doc: Document) -> list[AnomalyOut]:
    """같은 협력사의 다른 로트와 항목 값이 소수점까지 같음 (명세 4.17 identical_values).

    협력사·로트번호는 documents 테이블 값을 쓴다 (업로드 입력 또는 추출 결과). 어느 하나라도 없으면 비교하지 않는다.
    같은 로트번호의 다른 문서(같은 CoA 재업로드)는 비교 대상에서 뺀다.
    """
    if not doc.supplier or not doc.lot_no:
        return []
    mine = _reported_values(doc)
    if not mine:
        return []

    others = db.scalars(
        select(Document)
        .options(selectinload(Document.extraction))
        .where(Document.id != doc.id, Document.material_code == doc.material_code, Document.lot_no.is_not(None))
        .order_by(Document.uploaded_at)
    )
    matches: dict[str, list[Document]] = {}
    for other in others:
        if _norm(other.supplier) != _norm(doc.supplier) or _norm(other.lot_no) == _norm(doc.lot_no):
            continue
        theirs = _reported_values(other)
        for name, (value, _) in mine.items():
            if name in theirs and theirs[name][0] == value:
                matches.setdefault(name, []).append(other)

    anomalies = []
    for name, (_, raw) in mine.items():
        if name not in matches:
            continue
        lots = ", ".join(dict.fromkeys(d.lot_no for d in matches[name]))
        anomalies.append(AnomalyOut(
            type="identical_values",
            item_name=name,
            message=f"다른 로트({lots})와 값이 같습니다. {name} {raw}",
            related_document_ids=[d.id for d in matches[name]],
        ))
    return anomalies


def _numbers(text: str) -> list[tuple[float, str | None]]:
    return [(float(m["num"]), m["unit"]) for m in _NUM_UNIT.finditer(text.replace(",", ""))]


def _at_spec_limit(doc: Document) -> list[AnomalyOut]:
    """값이 협력사 규격 경계와 정확히 같음 (명세 4.17 at_spec_limit).

    협력사 규격은 CoA 의 규격 칸 원문(raw_spec)이다 (사내 규격이 아님). 규격 칸에 적힌 숫자를 경계로 보고
    ('≤ 50 ppm', '99.5 % min', '0.5-1.0' 등), 실측값(exact)이 그중 하나와 같으면 경고한다.
    단위가 서로 다르면 환산해서 비교하고, 환산할 수 없으면 비교하지 않는다.
    결과 칸이 규격 문구와 같은 경우는 규격 복사(SPEC_COPIED)라 여기서 다루지 않는다.
    """
    anomalies = []
    for item in _items(doc):
        raw, spec = item.get("raw_value"), item.get("raw_spec")
        if (item.get("value_qualifier") != ValueQualifier.EXACT or not raw or not spec
                or item.get("reason_code") == ReasonCode.SPEC_COPIED or is_spec_text_as_result(raw, spec)):
            continue
        values = _numbers(raw)
        if len(values) != 1:
            continue
        value, value_unit = values[0]
        value_unit = value_unit or item.get("unit")
        for bound, bound_unit in _numbers(spec):
            try:
                bound = convert_unit(bound, bound_unit or item.get("unit"), value_unit)
            except UnitConversionError:
                continue
            if math.isclose(value, bound, rel_tol=1e-9, abs_tol=1e-12):
                name = item["normalized_name"]
                anomalies.append(AnomalyOut(
                    type="at_spec_limit",
                    item_name=name,
                    message=f"값이 협력사 규격 경계와 같습니다. {name} {raw.strip()} (협력사 규격 {spec.strip()})",
                    related_document_ids=[],
                ))
                break
    return anomalies
