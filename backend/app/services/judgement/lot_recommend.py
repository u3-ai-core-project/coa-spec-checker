"""[담당: 장수민] 판정별 집계(summary)와 로트 권고 (명세 2.4, v1.4안 2.4).

우선순위 (기획안 v2 7.1)
  fail 1개 이상                                          → reject (불합격 권고)
  fail 없음, document_issues 또는 undetermined·missing·check → hold   (보류 권고)
  모두 pass, document_issues 없음                        → approve (승인 권고)

부적합과 문서 정합성 오류가 함께 있으면 불합격 권고가 우선이다. 두 사유는 결과 JSON 에 모두 남는다.
"""
from collections import Counter
from collections.abc import Iterable

from app.core.enums import Judgement, LotRecommendation
from app.schemas.extraction import DocumentIssue, ExtractionItem, Summary


def summarize(items: Iterable[ExtractionItem]) -> Summary:
    c = Counter(i.judgement for i in items)
    return Summary(**{j.value: c.get(j, 0) for j in Judgement})


def recommend(summary: Summary, issues: Iterable[DocumentIssue] = ()) -> LotRecommendation:
    if summary.fail > 0:
        return LotRecommendation.REJECT
    if any(True for _ in issues) or summary.undetermined or summary.missing or summary.check:
        return LotRecommendation.HOLD
    return LotRecommendation.APPROVE


# 보류 권고일 때 화면에 보여줄 판정별 후속 조치 안내 (명세 2.4, 엑셀 리포트에도 사용).
# v1.4안부터는 항목별 resolution(해결 조건)이 더 구체적이므로, 새 화면·리포트는 resolution.condition 을 쓴다.
FOLLOW_UP_GUIDE = {
    Judgement.UNDETERMINED: "협력사에 실측값 요청",
    Judgement.MISSING: "자체 시험 또는 추가 데이터 요청",
    Judgement.CHECK: "원본 확인",
}
