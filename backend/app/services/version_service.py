"""[담당: 홍채령] 추출·판정 근거 버전 기록 (운영 정책 6장).

"추출 결과에 어떤 모델과 프로그램 버전으로 읽었는지 저장한다.
 (모델을 바꾼 뒤에는 예전 결과가 어느 모델의 것인지 알 수 없다. 판정마다 규격 세트 버전을 남기는 것과 같은 이유이다.)"

AI 결과 JSON(extraction_results.result, 명세 2.1)은 팀 합의 없이 바꾸지 않는다. 그래서 버전은 따로
extraction_results.versions(JSONB) 에 백엔드가 적는다. 생김새:

    {
      "extraction": {                       # 문서를 "읽었을" 때 (추출할 때마다 새로 씀, 다시 처리하면 바뀜)
        "read_at": "...",
        "backend_version": "1.4.0",         # app.__version__
        "extractor": "ai",                  # 설정 EXTRACTOR (mock | ai)
        "ai_package": {"name": "coa-ai", "version": "0.1.0"},   # 설치된 패키지 정보. 없으면 null
        "llm": {"configured": true, "host": "127.0.0.1:8090", "model": null},  # 주소는 호스트:포트만 (경로·계정 없음)
        "mapping_dictionary": {"material_code": "LI2CO3", "count": 31, "latest_created_at": "...", "hash": "1a2b3c4d5e6f"},
        "inquiry_drafter": "template",      # 그때 설정된 문의 초안 생성기
        "ai_reported": {}                   # AI 결과에 버전 같은 칸이 있으면 그대로 (지금은 없음)
      },
      "judgement": {                        # 판정할 때마다 (추출·검수 수정·규격 세트 변경·규격 수정 후 재판정)
        "judged_at": "...", "trigger": "extraction" | "review" | "respec" | "spec_change",
        "backend_version": "1.4.0",
        "spec_set": {"id": 1, "code": "LI2CO3-D1-2023", "version": "YS/T 582-2023", "rules_hash": "..."},
        "policy_hash": "..."                # 판정 정책 설정(.env 의 REASON_JUDGEMENT 등)을 줄인 값
      },
      "history": [ {"judgement": {...}, "extraction": {...}} ]   # 바뀌기 전 기록 (최근 HISTORY_MAX 개)
    }

- 근거(백엔드 버전·규격 세트·규칙·정책)가 같은 채로 다시 판정하면(예: 담당자 값 수정) judged_at·trigger 만 바꾸고 history 를 늘리지 않는다
- 근거가 바뀌거나 문서를 다시 읽으면 이전 기록을 history 에 남긴다
- hash 는 내용을 줄인 지문(SHA-256 앞 12자리)이다. 같은 내용이면 늘 같고, 하나라도 바뀌면 달라진다
"""
import dataclasses
import enum
import hashlib
import json
from datetime import datetime, timezone
from importlib import metadata
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import __version__
from app.core.config import settings
from app.models import Document, ItemMapping, SpecSet
from app.services.judgement.policy import default_policy
from app.services.judgement.spec_rule import SpecRule

HISTORY_MAX = 20
AI_PACKAGE = "coa-ai"
# AI 결과에 이런 이름의 칸이 생기면 ai_reported 에 그대로 남긴다 (지금 coa_ai 결과에는 없음)
AI_VERSION_KEYS = ("model", "model_name", "model_version", "engine", "engine_version", "version", "pipeline_version")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _plain(value):
    """JSON 으로 바꿀 수 있게 (열거형 → 값, 튜플 → 리스트, 딕셔너리 키 → 문자열)."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        value = {f.name: getattr(value, f.name) for f in dataclasses.fields(value)}
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, dict) or hasattr(value, "items") and not isinstance(value, (str, bytes)):
        return {str(_plain(k)): _plain(v) for k, v in sorted(value.items(), key=lambda kv: str(_plain(kv[0])))}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [_plain(v) for v in value]
        return sorted(items, key=str) if isinstance(value, (set, frozenset)) else items
    return value


def fingerprint(value) -> str:
    text = json.dumps(_plain(value), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# 읽은 근거 (추출)
# ---------------------------------------------------------------------------
def ai_package_info() -> dict | None:
    """설치된 coa-ai 패키지 이름·버전 (ai/pyproject.toml 의 version). 설치 안 됐으면 None."""
    try:
        return {"name": AI_PACKAGE, "version": metadata.version(AI_PACKAGE)}
    except metadata.PackageNotFoundError:
        return None


def llm_info() -> dict:
    """LLM 서버 정보. 주소는 호스트:포트만 남긴다 (경로·계정·질의 문자열은 버림). 모델 이름은 coa_ai 가 아직 알려 주지 않는다."""
    url = settings.LLM_BASE_URL
    if not url:
        return {"configured": False, "host": None, "model": None}
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return {"configured": True, "host": host or None, "model": None}


def mapping_version(db: Session, material_code: str) -> dict:
    """그 원자재의 매핑 사전 버전: 개수, 마지막 추가 시각, 내용 지문 (항목이 하나라도 바뀌면 지문이 달라진다)."""
    rows = db.execute(
        select(ItemMapping.raw_name, ItemMapping.normalized_name, ItemMapping.source)
        .where(ItemMapping.material_code == material_code)
        .order_by(ItemMapping.raw_name, ItemMapping.normalized_name)
    ).all()
    latest = db.scalar(select(func.max(ItemMapping.created_at)).where(ItemMapping.material_code == material_code))
    return {
        "material_code": material_code,
        "count": len(rows),
        "latest_created_at": latest.isoformat() if latest else None,
        "hash": fingerprint([[r.raw_name, r.normalized_name, r.source] for r in rows]),
    }


def extraction_record(db: Session, doc: Document, ai_output: dict | None = None) -> dict:
    reported = {k: ai_output[k] for k in AI_VERSION_KEYS if ai_output and ai_output.get(k) is not None}
    return {
        "read_at": _now(),
        "backend_version": __version__,
        "extractor": settings.EXTRACTOR,
        "ai_package": ai_package_info() if settings.EXTRACTOR == "ai" else None,
        "llm": llm_info() if settings.EXTRACTOR == "ai" else {"configured": False, "host": None, "model": None},
        "mapping_dictionary": mapping_version(db, doc.material_code),
        "inquiry_drafter": settings.INQUIRY_DRAFTER,
        "ai_reported": _plain(reported),
    }


# ---------------------------------------------------------------------------
# 판정 근거
# ---------------------------------------------------------------------------
def policy_hash() -> str:
    """판정에 쓰는 정책 설정 지문. 정책 객체 + 정책 객체 밖에서 판정에 쓰는 설정."""
    return fingerprint({
        "policy": default_policy(),
        "oxide_to_element": settings.OXIDE_TO_ELEMENT,
        "identical_values_min_matches": settings.IDENTICAL_VALUES_MIN_MATCHES,
    })


def judgement_record(spec_set: SpecSet | None, rules: list[SpecRule], trigger: str) -> dict:
    """spec_set: 판정에 실제로 쓴 규격 세트 (문서에 연결이 없으면 원자재 기본 세트)."""
    return {
        "judged_at": _now(),
        "trigger": trigger,
        "backend_version": __version__,
        "spec_set": {"id": spec_set.id, "code": spec_set.code, "version": spec_set.version,
                     "rules_hash": fingerprint(sorted(rules, key=lambda r: r.item_name))} if spec_set else None,
        "policy_hash": policy_hash(),
    }


def _basis(judgement: dict | None) -> tuple | None:
    if not judgement:
        return None
    return judgement.get("backend_version"), json.dumps(judgement.get("spec_set"), sort_keys=True), judgement.get("policy_hash")


def record(doc: Document, *, judgement: dict, extraction: dict | None = None) -> dict:
    """doc.extraction.versions 를 새로 쓴다. extraction 을 주면 다시 읽은 것(추출). commit 은 호출한 쪽에서."""
    old = dict(doc.extraction.versions or {}) if doc.extraction is not None else {}
    history = list(old.get("history") or [])
    prev_j, prev_e = old.get("judgement"), old.get("extraction")
    reread = extraction is not None and prev_e is not None
    if reread or (prev_j and _basis(prev_j) != _basis(judgement)):
        entry = {"judgement": prev_j}
        if reread:
            entry["extraction"] = prev_e
        history = (history + [entry])[-HISTORY_MAX:]
    new = {"extraction": extraction if extraction is not None else prev_e, "judgement": judgement, "history": history}
    doc.extraction.versions = new  # 새 dict 로 바꿔 넣어야 SQLAlchemy 가 바뀐 것을 안다
    return new
