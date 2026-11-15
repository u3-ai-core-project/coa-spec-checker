"""[담당: 고도영] AI 공급사 문의 초안 생성기 — followup_service.get_drafter() 에 INQUIRY_DRAFTER=ai 로 연결.

PR #5 의 LotRequest(요청 목록)를 coa_ai.draft_inquiry 입력으로 바꿔 LLM 초안을 받는다.
초안 검사(입력에 없는 숫자, 빠진 항목·조건 등)에 걸리거나 LLM 이 없으면 coa_ai.InquiryDraftError 가 나고,
followup_service 가 템플릿으로 대신한다 (source=template_fallback).
"""
import coa_ai

from app.pipeline.llm_client import get_llm
from app.services.inquiry_draft import SUPPLIER_REQUEST, LotRequest


class AIDrafter:
    source = "ai"

    def draft(self, supplier: str | None, lots: list[LotRequest]) -> tuple[str, str]:
        llm = get_llm()
        if llm is None:
            raise coa_ai.InquiryDraftError("LLM 서버 주소(LLM_BASE_URL)가 없습니다")
        return coa_ai.draft_inquiry(supplier, self.to_inquiry_lots(lots), llm)

    @staticmethod
    def to_inquiry_lots(lots: list[LotRequest]) -> list[dict]:
        """해결 조건(condition)은 담당자용 문구라, 템플릿과 같이 공급사용 요청 문구가 있으면 그것을 쓴다."""
        return [
            {"lot_no": lot.lot_no, "material_name": lot.material_name, "requests": [
                {"target": ln.target, "label": ln.label, "why": ln.why,
                 "request": SUPPLIER_REQUEST.get(ln.code, ln.condition), "raw_value": ln.raw_value}
                for ln in lot.lines
            ]}
            for lot in lots if lot.lines
        ]
