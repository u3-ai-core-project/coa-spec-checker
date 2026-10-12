"""[담당: 장수민] 판정별 집계(summary)와 로트 권고 (명세 2.4).

  fail 1개 이상                              → reject (불합격 권고)
  fail 없음, undetermined·missing·check 있음 → hold   (보류 권고)
  모두 pass                                  → approve (승인 권고)
"""
from collections import Counter
from collections.abc import Iterable

from app.core.enums import Judgement, LotRecommendation
from app.schemas.extraction import ExtractionItem, Summary


def summarize(items: Iterable[ExtractionItem]) -> Summary:
    c = Counter(i.judgement for i in items)
    return Summary(**{j.value: c.get(j, 0) for j in Judgement})


def recommend(summary: Summary) -> LotRecommendation:
    if summary.fail > 0:
        return LotRecommendation.REJECT
    if summary.undetermined or summary.missing or summary.check:
        return LotRecommendation.HOLD
    return LotRecommendation.APPROVE


# 보류 권고일 때 화면에 보여줄 후속 조치 안내 (명세 2.4, 엑셀 리포트에도 사용)
FOLLOW_UP_GUIDE = {
    Judgement.UNDETERMINED: "협력사에 실측값 요청",
    Judgement.MISSING: "자체 시험 또는 추가 데이터 요청",
    Judgement.CHECK: "원본 확인",
}
