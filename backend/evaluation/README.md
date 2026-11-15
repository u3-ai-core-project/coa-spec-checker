### 평가 스크립트 실행 방법

정답 라벨과 시스템 출력을 비교해 추출·판정 정확도를 계산합니다. 서버를 띄우지 않고 파일만 읽습니다.

**1. 환경 준비**

백엔드 가상환경을 활성화하고 패키지를 설치합니다. (백엔드 실행 방법 1~2번과 같습니다)
```bash
cd coa-spec-checker/backend
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**2. 평가 실행**
```bash
python -m evaluation.run --gt <정답 라벨 폴더> --pred <시스템 출력 폴더>
python -m evaluation.run --gt <정답 라벨 폴더> --pred <시스템 출력 폴더> --baseline <베이스라인 출력 폴더>
```
- 폴더 안에는 문서 1건당 JSON 1개를 넣습니다. 파일 이름(확장자 제외) 또는 `document_id`로 정답과 출력을 짝짓습니다.
- 시스템 출력은 `GET /documents/{id}/extraction` 응답이나 AI 추출 결과(`ExtractionInput`)를 그대로 저장하면 됩니다. AI 추출 결과만 넣으면 판정 지표는 계산되지 않습니다.
- `--baseline`: 규칙 베이스라인 출력 폴더. 시스템 출력과 같은 형식이며, 넣으면 지표를 나란히 비교합니다.
- `--out`: 리포트 저장 폴더. 기본값은 `evaluation/reports/<시각>`
- `--threshold`: 신뢰도 기준값. 기본값은 `.env`의 `LOW_CONFIDENCE_THRESHOLD`
- `--policy`: 시스템 출력을 만든 서버의 판정 정책 JSON. 기본값은 이 컴퓨터 `.env`의 값

형식을 확인하고 싶으면 예시 파일로 먼저 실행해 보세요. (`examples/`는 형식 예시용 가상 값입니다)
```bash
python -m evaluation.run --gt evaluation/examples/gt --pred evaluation/examples/pred --baseline evaluation/examples/baseline
```

**3. 결과 확인**

`evaluation/reports/<시각>/report.md`, `report.json`이 만들어집니다. 이 폴더는 git에 올라가지 않습니다.

### 데모 PDF 만들기

수용 테스트와 같은 시나리오 값(`tests/fixtures/demo20_scenarios.json`)으로 시연용 가상 CoA PDF를 만듭니다. 시나리오는 22개이고 PDF는 24개가 만들어집니다.

**1. 패키지 설치**
```bash
cd coa-spec-checker/backend
pip install -r requirements.txt
pip install -e ../ai
```

**2. PDF 만들기**
```bash
python -m evaluation.demo20_pdfs
python -m evaluation.demo20_pdfs --out <저장 폴더>
```
기본 저장 위치는 `evaluation/reports/demo20_pdfs/`입니다.

```
demo01.pdf ~ demo19.pdf                          1~19번 (로트 DEMO-L01 ~ DEMO-L19)
demo20_DEMO-L20-1.pdf ~ demo20_DEMO-L20-3.pdf    20번 (같은 협력사의 로트 3개)
demo21.pdf, demo22.pdf                           21, 22번
```

**3. 실제 추출로 업로드**

`backend/.env`에 `EXTRACTOR=ai`를 넣고 백엔드를 다시 시작한 뒤, 업로드 화면에서 PDF를 올립니다.
```
EXTRACTOR=ai
```
- 12번: 입고 로트를 `DEMO-L99`로 등록해야 로트 불일치가 나옵니다.
- 17번: 글자 층이 없는 흐린 스캔본이라 OCR로 읽고, 확인 필요와 보류가 나옵니다.
- 18번: 규격 세트를 `LI2CO3-2013`으로 지정합니다.
- 20번: 로트 3개를 모두 올려야 같은 값 반복 경고가 나옵니다.
- 21번: 규격 세트를 `LI2CO3-SUPPLIER-V1`으로 지정하면 적합이고, 지정하지 않으면(기본 D1) 부적합입니다.
- 22번: 수산화리튬 CoA라서 원자재를 `LIOH`로 고르고 규격 세트는 지정하지 않습니다. (기본 `LIOH-BG-V1` 적용)

PDF는 단순한 표 형식 하나이며 실제 협력사 양식이 아닙니다.
