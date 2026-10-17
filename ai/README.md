# AI 추출 (coa_ai)

CoA(시험성적서) PDF에서 머리글 필드와 시험 항목 표를 읽어 서버 판정 입력(`ExtractionInput`, API 명세 2.1의 AI 필드)을 만듭니다.
값 해석(부등호, ND, 단위 환산)과 판정은 서버가 하므로, 이 패키지는 원문을 그대로 넘깁니다.

## 설치

백엔드와 같은 가상환경에 설치합니다.

```bash
cd coa-spec-checker/backend
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e "../ai[dev]"
```

백엔드에서 실제 추출기를 쓰려면 `backend/.env`에 `EXTRACTOR=ai`를 넣습니다. 기본값은 목업(`mock`)입니다.

## 실행

```bash
cd ai
python -m coa_ai tests/fixtures/COA_A_0007.pdf --material LIOH        # 추출 결과 JSON
python -m coa_ai data/raw/real/*.pdf --material LI2CO3                # 여러 파일 점검표
```

## 테스트

```bash
cd ai
pytest -q                                   # 단위 테스트 + 가상 CoA 3장
COA_REAL_DIR=data/raw/real pytest -q        # 실물 CoA 까지
```

실물 CoA는 라이선스 문제로 저장소에 올리지 않습니다. 노션 「CoA 레퍼런스 추가 조사」에 첨부된 `CoA_데이터_정리본.zip`의 PDF를 `ai/data/raw/real/`에 한 폴더로 풀어 쓰세요. 이 폴더는 `.gitignore` 대상입니다.

## 처리 흐름

| 단계 | 파일 | 하는 일 |
| --- | --- | --- |
| 1 | `pdf_text.py` | 글자 좌표로 줄을 다시 만들고, 첨자를 `Li₂CO₃`·`SO₄²⁻`처럼 복원 |
| 2 | `fields.py`, `dates.py` | 머리글 필드(로트, 시험일, 원산지, 협력사, 적용 규격)와 날짜(YYYY-MM-DD) |
| 3 | `classify.py` | 문서 유형: CoA·규격서·웹페이지·기타. CoA가 아니면 사유와 함께 실패 |
| 4 | `table.py` | 표 머리글 → 열(빈 세로 띠) → 행. 머리글이 없으면 '이름 값' 목록·'기호 값' 격자 |
| 5 | `normalize.py`, `vocab.json` | 항목명 정규화: DB 매핑 → 사전 → 규칙 → 유사도 |
| 6 | `pipeline.py` | 단계 연결, 신뢰도·좌표 계산. 표 구조화 함수는 교체 가능(스캔본 단계에서 OCR/VLM 연결) |

## 표준 항목명 (normalized_name)

서버는 `normalized_name`이 사내 규격 `spec_items.item_name`과 같을 때만 판정합니다. 규격 시드를 만들 때 아래 이름을 그대로 써 주세요.

| 구분 | 표준 항목명 |
| --- | --- |
| 원소·이온 | Na, K, Ca, Mg, Fe, Cu, Mn, Si, Ni, Cr, Zn, Pb, Al, B, Cl |
| 그 외 | 순도(탄산리튬 함량), LiOH 함량, 탄산, 황산염, 질산염, 수분, 외관, 중금속, 불용분, 자성이물, 입도 D10, 입도 D50, 입도 D90 |

- 사전 키는 소성훈 님 정답 라벨 코드(na, so4, co3 …)를 따릅니다. 이름을 바꾸려면 `vocab.json`의 `name`만 고치면 됩니다.
- `Heavy metals (as Pb)`는 중금속 총량이므로 Pb가 아니라 `중금속`으로 보냅니다.
- `Assay`는 탄산리튬(LI2CO3)에서만 `순도`로 보냅니다. 수산화리튬(LIOH)은 LiOH·H₂O 함량일 수 있어 자동 매핑하지 않습니다.
- 산화물은 서버가 환산하는 것(Na₂O, CaO, Fe₂O₃)만 원소로 보냅니다.

## 신뢰도

텍스트 PDF는 글자 자체가 정확하므로, 신뢰도는 구조와 매핑이 얼마나 확실한지로 정합니다. 서버 기준(0.8) 미만은 '확인 필요'가 됩니다.

| 경우 | 신뢰도 |
| --- | --- |
| 머리글 있는 표, 깨끗한 행, 사전 매핑 | 0.95 |
| 칸 보정(단위 칸의 글을 항목명으로 되돌림), 결과 값이 여러 줄 | 0.85 |
| 머리글 없는 목록·격자 | 0.7 |
| 유사도 매핑, 매핑 못 함 | 0.6 이하 |

`bbox`는 결과 칸 위치이며 0~1 비율, 왼쪽 위 기준, page는 1부터입니다.

## 아직 못 하는 것 (다음 단계)

- 이미지(PNG·JPG)와 글자 없는 스캔 PDF: "이미지·스캔본 추출은 아직 지원하지 않습니다"로 실패합니다. OCR/VLM 단계에서 다룹니다.
- LLM 기능: 정규화 보완, 결과 의미 보조, 공급사 문의 초안
- 웹페이지 캡처(Nanotrun)는 지금은 CoA가 아닌 것으로 막습니다. 팀에서 받기로 하면 `classify.py`의 `ACCEPTED_DOC_TYPES`에 `"web_page"`를 넣습니다.
- 월·연도만 있는 날짜(08-2025)는 읽지 않습니다. 시험일 라벨이 없는 양식은 `test_date`가 null입니다.

## 라이선스

PDF 처리에 쓰는 PyMuPDF는 AGPL-3.0입니다. 외부에 공개하는 서비스로 배포하면 소스 공개 의무가 생깁니다.
