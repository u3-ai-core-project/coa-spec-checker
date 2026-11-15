"""[담당: 고도영] 공급사 문의 메일 초안 (기획안 v2 ★8 예외 설명·조치 생성).

입력은 서버 판정 결과로 만든 요청 목록이다 (백엔드 inquiry_draft.LotRequest 를 dict 로 바꾼 것).
  lots = [{"lot_no", "material_name", "requests": [{"target", "label", "why", "request", "raw_value"}]}]
  request 는 공급사에 요청할 것 (백엔드 SUPPLIER_REQUEST, 없으면 해결 조건 문구)

LLM 이 쓴 글을 코드가 검사하고, 하나라도 걸리면 InquiryDraftError 를 던진다.
백엔드(followup_service)는 이 예외를 받으면 템플릿 초안으로 대신한다 (source=template_fallback).
  - 입력에 없는 숫자 (근거 인용 정확도 100% 목표)
  - 빠진 로트 번호·요청 항목명·요청 문구 속 숫자
  - 표(|), 처분 단정(반품·폐기 등. 처분은 담당자가 정한다), 제목 줄 없음
"""
from __future__ import annotations

import json
import re

from coa_ai.llm import DRAFT_TIMEOUT

DISPOSITION_WORDS = ("반품", "폐기", "불합격 처리", "입고 거부")

DRAFT_SYSTEM = """너는 2차전지 원료 입고 QC 담당자를 대신해 공급사에 보낼 CoA 확인 요청 메일 초안을 쓴다.
규칙:
- 입력의 요청 항목을 빠짐없이 로트별로 쓴다. 여러 로트는 메일 1통에 묶는다.
- 숫자, 로트 번호, CoA 원문 값은 입력에 있는 것만 그대로 옮긴다. 입력에 없는 숫자·날짜·기한·판정을 지어내지 않는다.
- 항목마다 무엇이 문제인지(why)와 공급사에 요청할 것(request)을 쓴다.
- 반품·폐기·불합격 처리 같은 처분은 쓰지 않는다. 처분은 담당자가 정한다.
- 정중한 한국어 업무 메일로 쓰고, 서명은 "[담당자 이름]"으로 둔다. 표(|)는 쓰지 않고 번호 목록으로 쓴다.
형식: 첫 줄에 "제목: ...", 빈 줄 다음에 본문."""

_NUMBER = re.compile(r"(?<![A-Za-z0-9.])\d+(?:\.\d+)?(?![A-Za-z0-9])")
_LIST_MARK = re.compile(r"^\s*\d+[.)]\s", re.M)


class InquiryDraftError(Exception):
    """초안을 만들지 못함 (LLM 없음, 형식 오류, 검사 실패). 부르는 쪽은 템플릿으로 대신한다."""


def numbers(text: str) -> set[float]:
    """글 속 숫자. 번호 목록 표시('1. ')와 '2차전지'는 뺀다."""
    text = _LIST_MARK.sub(" ", re.sub(r"2\s*차\s*전지", " ", text))
    return {float(n) for n in _NUMBER.findall(text)}


def draft_inquiry(supplier: str | None, lots: list[dict], llm) -> tuple[str, str]:
    """(제목, 본문). llm 은 coa_ai.llm.LLMClient."""
    if llm is None:
        raise InquiryDraftError("LLM 서버가 없습니다")
    user = json.dumps({"supplier": supplier or "공급사", "lots": lots}, ensure_ascii=False, indent=1)
    raw = llm.text_chat(DRAFT_SYSTEM, user, max_tokens=1500, timeout=DRAFT_TIMEOUT)
    if not raw:
        raise InquiryDraftError("LLM 응답 없음")
    subject, body = _split(raw)
    problems = check_draft(subject, body, supplier, lots)
    if problems:
        raise InquiryDraftError("초안 검사 실패: " + "; ".join(problems))
    return subject, body


def _split(raw: str) -> tuple[str, str]:
    lines = raw.strip().splitlines()
    first = lines[0].lstrip("# *").strip() if lines else ""
    if not first.startswith("제목"):
        raise InquiryDraftError("초안 검사 실패: 첫 줄에 제목 없음")
    subject = first.split(":", 1)[-1].strip().strip("*").strip()
    body = "\n".join(lines[1:]).strip()
    if not subject or not body:
        raise InquiryDraftError("초안 검사 실패: 제목 또는 본문이 비었음")
    return subject, body


def check_draft(subject: str, body: str, supplier: str | None, lots: list[dict]) -> list[str]:
    """초안 문제 목록. 빈 목록이면 통과."""
    text = f"{subject}\n{body}"
    problems = []
    requests = [r for lot in lots for r in lot["requests"]]
    allowed = numbers(json.dumps({"supplier": supplier, "lots": lots}, ensure_ascii=False))
    allowed |= {float(len(lots)), float(len(requests))}
    invented = sorted(numbers(text) - allowed)
    if invented:
        problems.append("입력에 없는 숫자 " + ", ".join(f"{n:g}" for n in invented))

    for lot in lots:
        if lot.get("lot_no") and lot["lot_no"] not in text:
            problems.append(f"로트 번호 {lot['lot_no']} 없음")
        for r in lot["requests"]:
            target = r["target"]
            if not re.search(rf"(?<![A-Za-z]){re.escape(target)}(?![a-z])", text):
                problems.append(f"요청 항목 {target} 없음")
            for n in sorted(numbers(r.get("request") or "") - numbers(text)):
                problems.append(f"{target} 요청 수치 {n:g} 없음")

    if "|" in text:
        problems.append("표(|) 사용")
    problems += [f"처분 단정 표현 '{w}'" for w in DISPOSITION_WORDS if w in text]
    return problems
