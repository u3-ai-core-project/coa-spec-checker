# AI 추출 (coa_ai)

CoA(시험성적서) PDF·스캔본·이미지에서 머리글 필드와 시험 항목 표를 읽어 서버 판정 입력(`ExtractionInput`, API 명세 2.1의 AI 필드)을 만듭니다.
값 해석(부등호, ND, 단위 환산)과 판정은 서버가 하므로, 이 패키지는 원문을 그대로 넘깁니다.

## 설치

백엔드와 같은 가상환경에 설치합니다.

```bash
cd coa-spec-checker/backend
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e "../ai[dev]"
```

백엔드에서 실제 추출기를 쓰려면 `backend/.env`에 `EXTRACTOR=ai`를 넣습니다. 기본값은 목업(`mock`)입니다.

스캔본·이미지를 처음 읽을 때 OCR 모델 파일을 내려받으므로 인터넷이 필요합니다. Docker 이미지를 만들 때는 `python -c "from coa_ai.ocr import load_engine; load_engine(); load_engine('korean')"`로 미리 받아 두세요. 두 번째는 한글 문서를 다시 읽는 한국어 인식 모델입니다.

## 실행

```bash
cd ai
python -m coa_ai tests/fixtures/COA_A_0007.pdf --material LIOH        # 추출 결과 JSON
python -m coa_ai data/raw/real/*.pdf --material LI2CO3                # 여러 파일 점검표
python -m coa_ai tests/fixtures/COA_D_0007.pdf --material LIOH --llm-url http://127.0.0.1:8090   # LLM 단계 포함
```

## 열화 처리 도구 (`tools/degrade.py`)

평가용 스캔본을 만듭니다. 원본 CoA(PDF·이미지)를 열화 단계별로 글자 층이 없는 PDF로 바꾸고 목록(`manifest.csv`)을 씁니다.

```bash
cd ai
python tools/degrade.py data/raw/real/*.pdf --out data/generated/degraded              # 기본 4단계
python tools/degrade.py a.pdf --out out --levels levels.json --format png             # 단계 직접 지정, PNG
```
- 기본 단계는 모델 테스트와 같은 임시값입니다: 원본 200dpi, 저해상도 100dpi, 기울기 2°, 흐림(가우시안 1.5).
- 단계 설정 JSON 예: `{"fax": {"dpi": 150, "rotate": 1.0, "blur": 0.8, "jpeg_quality": 40}}`. 소성훈 님 열화 조건 표를 받으면 이 JSON만 바꾸면 됩니다.
- `manifest.csv`의 `group`은 원본 이름입니다. 같은 원본에서 만든 변형본은 개발용과 평가용에 나눠 넣지 마세요(기획안 v2 분리 원칙).

## 테스트

```bash
cd ai
pytest -q                                   # 단위 테스트 + 가상 CoA 3장
```

실물 CoA는 라이선스 문제로 저장소에 올리지 않습니다. PDF도, 실물에서 옮긴 값을 정답으로 적은 테스트도 넣지 않습니다. 모델 테스트(`bench/`)에서 실물을 쓰려면 노션 「CoA 레퍼런스 추가 조사」에 첨부된 `CoA_데이터_정리본.zip`의 PDF를 `ai/data/raw/real/`에 한 폴더로 풀어 쓰세요. 이 폴더는 `.gitignore` 대상입니다.

## 처리 흐름

| 단계 | 파일 | 하는 일 |
| --- | --- | --- |
| 1 | `pdf_text.py` | 글자 좌표로 줄을 다시 만들고, 첨자를 `Li₂CO₃`·`SO₄²⁻`처럼 복원 |
| 1 | `ocr.py` | 이미지 파일과 글자 없는 PDF 쪽(스캔본)은 OCR(RapidOCR, PP-OCRv6 small ONNX)로 읽어 같은 줄 구조로 바꿈. 기울어진 스캔은 바로 세워 읽음. 한글을 못 읽은 흔적('0|')이 3개 이상인 쪽은 한국어 인식 모델로 다시 읽어 한글 글줄만 바꿈 |
| 2 | `fields.py`, `dates.py` | 머리글 필드(로트, 시험일, 원산지, 협력사, 적용 규격)와 날짜(YYYY-MM-DD) |
| 3 | `classify.py` | 문서 유형: CoA·규격서·웹페이지·기타. CoA가 아니면 사유와 함께 실패 |
| 4 | `table.py` | 표 머리글 → 열(빈 세로 띠) → 행. 머리글이 없으면 '이름 값' 목록·'기호 값' 격자 |
| 5 | `normalize.py`, `vocab.json` | 항목명 정규화: DB 매핑 → 사전 → 규칙 → 유사도 → (LLM 제안) |
| 6 | `meaning.py` | 결과 칸 의미: 숫자·부등호·검출 안 됨·규격 복사·합격 문구·서술 + 근거 한 줄 |
| 7 | `selfcheck.py` | 자체 검증: 틀렸을 가능성이 높은 항목(스캔 잡음 글자, 같은 쪽 중복 값, 단위 종류 충돌, 칸 뒤바뀜, 상한의 50배 이상)은 확인 필요 + 이유 |
| 8 | `pipeline.py` | 단계 연결, 신뢰도·좌표 계산. 표 구조화 함수는 교체 가능 |
| - | `llm.py`, `inquiry.py` | LLM 서버 클라이언트, 공급사 문의 초안 (아래 'LLM 기능') |

결과에는 `ExtractionInput` 필드 외에 서버가 아직 쓰지 않는 칸도 들어 있습니다. 서버는 이 칸들을 버립니다(`extra="ignore"`).
- 문서: `doc_type`, `product_name`, `issue_date`, `expiry_date`, `retest_date`(Suggested retest date·复检日期·재시험일). `doc_type` 을 뺀 넷은 PR #5가 요청한 제품 불일치·날짜 충돌(`DATE_CONFLICT`) 탐지용으로, 서버 `ExtractionInput` 의 같은 이름 칸으로 들어갑니다(서버 칸은 별도 PR `feat/backend/extraction-doc-fields`).
- 항목: `value_kind`, `value_reason`, `check_reasons` (아래 '팀 제안')

## 표준 항목명 (normalized_name)

서버는 `normalized_name`이 사내 규격 `spec_items.item_name`과 같을 때만 판정합니다. 규격 시드를 만들 때 아래 이름을 그대로 써 주세요.

| 구분 | 표준 항목명 |
| --- | --- |
| 원소 | Na, K, Ca, Mg, Fe, Cu, Mn, Si, Ni, Cr, Zn, Pb, Al, B |
| 그 외 | 순도(탄산리튬 함량), LiOH 함량, 탄산, 황산염, 염화물, 질산염, 수분, 강열감량, 외관, 중금속 총량, 불용분, 자성이물, 입도 D10, 입도 D50, 입도 D90, 입도 D99, Na+K(합산 줄) |

- 사전 키는 소성훈 님 정답 라벨 코드(na, so4, co3 …)를 따릅니다. 이름을 바꾸려면 `vocab.json`의 `name`만 고치면 됩니다.
- 이름은 백엔드 규격 시드(`backend/seeds/data`)와 같습니다. 염소 이온은 `염화물`, 중금속은 `중금속 총량`입니다.
- `Heavy metals (as Pb)`는 중금속 총량이므로 Pb가 아니라 `중금속 총량`으로 보냅니다. 서버 교차 규칙이 이 값을 Pb 판정에 씁니다.
- `Sodium + Potassium (Na+K)`, `钠+钾` 같은 합산 줄은 `Na+K`로 보냅니다. 서버 합산 규칙이 Na, K를 원소별로 판정합니다. 앞 단어(Sodium)나 앞 한자(钠)만 보고 `Na`로 보내지 않습니다.
- `Assay`는 탄산리튬(LI2CO3)에서만 `순도`로 보냅니다. 수산화리튬(LIOH)은 LiOH·H₂O 함량일 수 있어 자동 매핑하지 않습니다.
- 산화물은 서버가 환산하는 것(Na₂O, K₂O, CaO, MgO, Fe₂O₃)만 원소로 보냅니다. 서버는 `raw_name`의 화학식을 보고 환산하므로, 화학식 없이 'oxide'·'氧化'만 적힌 이름(`Potassium oxide`)은 원소로 짐작하지 않고 원문 그대로 보냅니다(확인 필요).
- `강열감량`은 loss on ignition입니다. 건조감량(loss on drying)과 다른 항목이라 매핑하지 않습니다.

## 신뢰도

텍스트 PDF는 글자 자체가 정확하므로, 신뢰도는 구조와 매핑이 얼마나 확실한지로 정합니다. 서버 기준(0.8) 미만은 '확인 필요'가 됩니다.

| 경우 | 신뢰도 |
| --- | --- |
| 머리글 있는 표, 깨끗한 행, 사전 매핑 | 0.95 |
| 칸 보정(단위 칸의 글을 항목명으로 되돌림), 결과 값이 여러 줄 | 0.85 |
| 머리글 없는 목록·격자 | 0.7 |
| 유사도 매핑, LLM 제안, 매핑 못 함 | 0.6 이하 |
| 스캔본·이미지(OCR)로 읽은 항목 | 0.75 이하 |
| 자체 검증에 걸린 항목 (`check_reasons` 에 이유) | 0.75 이하 |

OCR은 글자를 틀릴 수 있고(모델 테스트 152장에서 찾은 항목의 값은 모두 맞았지만, 실제 스캔본은 더 거칠 수 있음), 틀린 글자도 OCR 점수가 높게 나와 가려낼 수 없습니다. 그래서 OCR로 읽은 항목은 모두 '확인 필요'로 보내 담당자가 원본과 대조하게 합니다. 한 문서 안에서도 글자 있는 쪽은 위 표대로, OCR로 읽은 쪽만 0.75 이하가 됩니다.

`bbox`는 결과 칸 위치이며 0~1 비율, 왼쪽 위 기준, page는 1부터입니다. 스캔본은 원본 이미지 기준이며, 기울어진 스캔도 바로 세우기 전 위치로 되돌려 냅니다.

## 아직 못 하는 것 (다음 단계)

- 90°·180° 돌아간 스캔과 5°를 넘는 기울기는 확인하지 않았습니다.
- 웹페이지 캡처(Nanotrun)는 지금은 CoA가 아닌 것으로 막습니다. 팀에서 받기로 하면 `classify.py`의 `ACCEPTED_DOC_TYPES`에 `"web_page"`를 넣습니다.
- 월·연도만 있는 날짜(08-2025)는 읽지 않습니다. 시험일 라벨이 없는 양식은 `test_date`가 null입니다.

## LLM 기능 (선택)

LLM 서버를 띄우면 규칙이 못 읽은 것만 LLM에 묻습니다. 띄우지 않아도 모든 기능이 규칙·템플릿으로 돌아갑니다.

| 기능 | LLM 이 하는 일 | 규칙·코드가 하는 일 | LLM 이 없거나 실패하면 |
| --- | --- | --- | --- |
| 항목명 정규화 (★4) | 사전·규칙·유사도가 못 찾은 항목명에 표준 항목명 제안. 후보 목록 + '없음' 중 하나만 고를 수 있음 | 사전·규칙·유사도. 표준 목록 밖 원소 기호 하나(`Ti`, `Co²⁺`)는 묻지 않고 그대로 둠 | 원문 항목명 그대로 |
| 결과 의미 분류 (★3) | 규칙 표에 없는 열린 문장(`Satisfactory`, `approx. 12 ppm (ICP)`)의 종류 | 부등호 단어(max, NMT, 이하, 不大于 …)·검출 안 됨 표기(BDL, < LOD, 未检出 …) 읽기, 규격 복사 여부 비교 | 숫자 없는 글은 서술, 못 읽은 숫자 표기는 `null` |
| 공급사 문의 초안 (★8) | 서버 판정 결과의 요청 목록으로 메일 초안 작성 | 입력에 없는 숫자, 빠진 로트·항목·요청 수치, 표, 처분 단정 표현 검사 | 백엔드가 템플릿 초안으로 대신함 (`source=template_fallback`) |

- LLM 제안 항목명은 신뢰도 0.6 이하라 항상 '확인 필요'입니다. 잘못 제안해도 자동으로 확정되지 않고, 담당자가 확정하면 매핑 사전에 쌓여 다음부터는 사전으로 바로 잡힙니다.
- LLM은 부등호 단어 대응과 숫자 비교를 하지 않습니다. 모델 테스트에서 Gemma가 "max"를 "≥"로 바꾸는 등 틀렸기 때문입니다. LLM이 답한 숫자는 원문에 글자 그대로 있을 때만 받아들입니다.
- LLM이 정한 의미의 근거(`value_reason`)는 "AI 판단: "으로 시작합니다.

**띄우는 법** (모델: Gemma 4 E2B QAT q4_0, 3.3GB, 모델 테스트 결과는 `bench/README.md`)
```bash
hf download google/gemma-4-E2B-it-qat-q4_0-gguf gemma-4-E2B_q4_0-it.gguf --local-dir ~/.cache/coa-bench/models
docker compose -f ai/docker-compose.llm.yml up -d      # 포트 8090, CPU 4스레드, 메모리 약 2GB
```
백엔드 `.env`에 `LLM_BASE_URL=http://127.0.0.1:8090`을 넣고, AI 문의 초안을 쓰려면 `INQUIRY_DRAFTER=ai`도 넣습니다. 백엔드를 Docker로 띄울 때는 주소를 `http://host.docker.internal:8090`이나 compose 서비스 이름으로 바꿉니다. 모델 파일을 다른 곳에 두었다면 `COA_LLM_MODELS=폴더 docker compose ...`로 지정합니다.

**시간**: 맥 Docker CPU 4스레드 기준 처음 보는 항목명·열린 문장 1개에 약 3~18초, 문의 초안 1통에 약 40초입니다. 문서 1건에서 LLM에 묻는 횟수는 최대 12번이고, 넘으면 나머지는 규칙 결과만 씁니다. 같은 질문은 기억해서 다시 묻지 않습니다. 서버에 연결할 수 없으면 60초 동안 묻지 않고 바로 규칙으로 진행합니다.

### 팀 제안: 항목 칸 3개 추가 (`value_kind`, `value_reason`, `check_reasons`)

AI 결과 항목에 아래 세 칸을 추가로 넣고 있습니다. 서버 `ExtractedItem`은 모르는 칸을 버리므로(`extra="ignore"`) 지금은 판정에 영향이 없습니다. 팀에서 받기로 하면 스키마에 두 칸을 넣으면 됩니다.

| 칸 | 값 | 예 |
| --- | --- | --- |
| `value_kind` | `number` 숫자 결과 / `bound` 부등호 결과 / `nd` 검출 안 됨 / `spec_copy` 결과 칸에 규격 조건을 다시 적음 / `pass_text` 합격 문구 / `description` 서술 / `null` 읽지 못함 | 결과 "Max 20 ppm", 규격 "≤ 20 ppm" → `spec_copy` |
| `value_reason` | 근거 한 줄 | "규격 칸과 같은 조건(<= 20 ppm)을 결과 칸에 다시 적음" |
| `check_reasons` | 자체 검증에 걸린 이유 목록 (걸리면 신뢰도 0.75 이하) | ["값에 스캔 잡음으로 보이는 글자가 있음('0|')"] |

- `check_reasons`를 받으면 서버의 '추출 신뢰도 낮음(0.75)' 대신 왜 확인해야 하는지를 검수 화면에 보여 줄 수 있습니다.
- 받으면 좋은 점: 서버 규격 복사 판정(`SPEC_COPIED`)은 지금 글자가 같을 때만 잡습니다. `value_kind=spec_copy`를 쓰면 "Max 20 ppm"과 "≤ 20 ppm", "NMT 20 ppm"처럼 표기만 다른 복사도 잡을 수 있습니다. 검수 화면에서는 근거 문장을 그대로 보여 줄 수 있습니다.
- 공급사용 요청 문구(`inquiry_draft.SUPPLIER_REQUEST`)가 없는 사유코드는 담당자용 해결 조건이 메일에 그대로 들어갑니다. 문구를 채우면 템플릿과 AI 초안이 함께 좋아집니다.

## 라이선스

PDF 처리에 쓰는 PyMuPDF는 AGPL-3.0입니다. 외부에 공개하는 서비스로 배포하면 소스 공개 의무가 생깁니다.
OCR에 쓰는 RapidOCR과 PP-OCR 모델은 Apache-2.0, ONNX Runtime은 MIT입니다.
LLM 기능에 쓰는 Gemma 4 E2B는 Apache-2.0, llama.cpp는 MIT입니다.
