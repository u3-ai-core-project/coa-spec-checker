"""[담당: 고도영] 문서 유형 분류: coa / spec_sheet(규격서) / web_page(웹페이지 캡처) / other.

CoA 근거 3가지 중 2가지 이상이면 CoA 로 본다.
  ① 첫 페이지 위쪽의 CoA 제목 (띄어 쓴 'C E R T I F I C A T E …' 도 인정)
  ② 로트·배치 번호
  ③ 결과 열이 있는 시험 항목 표 머리글
CoA 를 다른 문서로 잘못 막지 않는 것을 우선한다. 웹페이지는 로트 번호가 없을 때만 웹페이지로 본다.
"""
from __future__ import annotations

from coa_ai.models import Page
from coa_ai.table import compact, find_headers

# 이 집합에 든 유형만 추출을 계속한다. 팀이 Nanotrun 같은 웹페이지 결과표를 받기로 하면 "web_page" 를 추가한다.
ACCEPTED_DOC_TYPES = {"coa"}

_TITLE_WORDS = ("certificateofanalysis", "analysiscertificate", "certificateofquality", "qualitycertificate",
                "certificateofconformance", "检验报告", "检测报告", "分析报告", "质量证明", "시험성적서", "성적서",
                "품질검사")
_SPEC_WORDS = ("productdatasheet", "technicaldatasheet", "productspecification", "specificationsheet",
               "salesspecification", "typicalanalysis", "typicalproperties", "규격서", "规格书", "技术规格")
_WEB_WORDS = ("home", "products", "contactus", "aboutus", "blog", "news", "sitemap", "inquiry",
              "getthelatestprice", "addtocart", "privacy")


def classify(pages: list[Page], *, has_lot: bool) -> str:
    first = next((p for p in pages if p.lines), None)
    if first is None:
        return "other"
    top = compact(" ".join(ln.text for ln in first.lines if ln.baseline <= first.height * 0.4))
    page1 = compact(" ".join(ln.text for ln in first.lines))
    every = compact(" ".join(ln.text for p in pages for ln in p.lines))

    has_title = any(w in top for w in _TITLE_WORDS)
    has_result_header = any("result" in h.roles for p in pages[:2] for h in find_headers(p.lines))
    web_hits = sum(w in every for w in _WEB_WORDS)
    is_web = "pdfmyurl" in every or web_hits >= 4

    if is_web and not has_lot:
        return "web_page"
    if has_title + has_lot + has_result_header >= 2:
        return "coa"
    if any(w in page1 for w in _SPEC_WORDS):
        return "spec_sheet"
    return "other"
