"""[담당: 고도영] INQUIRY_DRAFTER=ai 로 follow-ups 문의 초안 (실제 DB 와 ai/ 패키지 필요).

LLM 서버는 테스트 안에서 띄우는 가짜 OpenAI 호환 서버다 (실제 HTTP).
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytest.importorskip("coa_ai")

from app.core.config import settings  # noqa: E402
from app.core.enums import SpecType  # noqa: E402
from app.models import SpecItem, SpecSet  # noqa: E402

PDF = b"%PDF-1.7\n" + b"0" * 50
MOCK = {"supplier": "알파 리튬", "lot_no": "L-001", "items": [  # 실제 CoA 아님. 규격: Na ≤ 50, Fe ≤ 5 ppm
    {"raw_name": "Na", "normalized_name": "Na", "mapping_source": "dictionary", "raw_value": "80", "unit": "ppm",
     "confidence": 0.95},
    {"raw_name": "Fe", "normalized_name": "Fe", "mapping_source": "dictionary", "raw_value": "none detected",
     "unit": "ppm", "confidence": 0.95},
]}
GOOD = """제목: [CoA 확인 요청] 탄산리튬 Lot L-001

알파 리튬 품질 담당자님께,

1. Na (CoA 기재: "80")
   - 요청: 단위·표기 오류 여부와 재시험 가능 여부를 확인해 주십시오.
2. Fe (CoA 기재: "none detected")
   - 요청: 검출한계 ≤ 5 ppm 또는 정량값을 알려 주십시오.

[담당자 이름]"""


class FakeLLM:
    """고정 답을 돌려주는 OpenAI 호환 서버."""

    def __init__(self, content: str):
        content_bytes = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
        self.requests: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                outer.requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(content_bytes)))
                self.end_headers()
                self.wfile.write(content_bytes)

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def __enter__(self):
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def doc_id(auth_client, db, tmp_path, monkeypatch):
    spec_set = SpecSet(code="T", material_code="LI2CO3", material_name="탄산리튬", is_default=True)
    spec_set.items = [SpecItem(item_name=n, unit="ppm", usl=u, spec_type=SpecType.QUANTITATIVE)
                      for n, u in (("Na", 50), ("Fe", 5))]
    db.add(spec_set)
    db.commit()
    mock_dir = tmp_path / "mock"
    mock_dir.mkdir()
    (mock_dir / "lot1.json").write_text(json.dumps(MOCK, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(settings, "MOCK_EXTRACTION_DIR", str(mock_dir))
    monkeypatch.setattr(settings, "INQUIRY_DRAFTER", "ai")
    r = auth_client.post("/api/v1/documents", files={"file": ("lot1.pdf", PDF)}, data={"material_code": "LI2CO3"})
    return r.json()["data"]["document_id"]


def draft_of(client, doc_id):
    r = client.get(f"/api/v1/documents/{doc_id}/follow-ups")
    assert r.status_code == 200, r.text
    return r.json()["data"]["draft"]


def test_followups_fall_back_without_llm(auth_client, doc_id, monkeypatch):
    monkeypatch.setattr(settings, "LLM_BASE_URL", None)
    draft = draft_of(auth_client, doc_id)
    assert draft["source"] == "template_fallback" and draft["subject"] == "[CoA 확인 요청] 탄산리튬 / Lot L-001"


def test_followups_use_ai_draft(auth_client, doc_id, monkeypatch):
    with FakeLLM(GOOD) as llm:
        monkeypatch.setattr(settings, "LLM_BASE_URL", llm.url)
        draft = draft_of(auth_client, doc_id)
    assert (draft["source"], draft["subject"]) == ("ai", "[CoA 확인 요청] 탄산리튬 Lot L-001")
    assert draft["body"].startswith("알파 리튬 품질 담당자님께,")
    sent = json.loads(llm.requests[0]["messages"][1]["content"])
    assert sent["supplier"] == "알파 리튬"
    assert [r["target"] for r in sent["lots"][0]["requests"]] == ["Na", "Fe"]


def test_followups_reject_invented_numbers(auth_client, doc_id, monkeypatch):
    with FakeLLM(GOOD.replace("[담당자 이름]", "14일 이내 회신이 없으면 입고를 보류합니다.\n\n[담당자 이름]")) as llm:
        monkeypatch.setattr(settings, "LLM_BASE_URL", llm.url)
        draft = draft_of(auth_client, doc_id)
    assert draft["source"] == "template_fallback"
