### AI 추출 (coa_ai) 실행 방법

CoA(시험성적서) PDF·스캔본·이미지에서 머리글 필드와 시험 항목 표를 읽어 서버 판정 입력(`ExtractionInput`)을 만듭니다. 값 해석과 판정은 서버가 하므로, 이 패키지는 원문을 그대로 넘깁니다.

**1. 설치**

백엔드와 같은 가상환경에 설치합니다.
```bash
cd coa-spec-checker/backend
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e "../ai[dev]"
```
스캔본·이미지를 처음 읽을 때 OCR 모델 파일을 내려받으므로 인터넷이 필요합니다. Docker 이미지를 만들 때는 아래 명령으로 미리 받아 두세요. 두 번째는 한글 문서를 다시 읽는 한국어 인식 모델입니다.
```bash
python -c "from coa_ai.ocr import load_engine; load_engine(); load_engine('korean')"
```

**2. 명령줄 실행**
```bash
cd coa-spec-checker/ai
python -m coa_ai tests/fixtures/COA_A_0007.pdf --material LIOH        # 추출 결과 JSON
python -m coa_ai data/raw/real/*.pdf --material LI2CO3                # 여러 파일 점검표
python -m coa_ai tests/fixtures/COA_D_0007.pdf --material LIOH --llm-url http://127.0.0.1:8090   # LLM 단계 포함
```
- `--material`: 원자재 구분 (`LI2CO3`, `LIOH`). 필수입니다
- `--summary`: 파일이 1개여도 점검표로 출력
- `--llm-url`: LLM 서버 주소. 기본값은 환경변수 `LLM_BASE_URL`이고, 없으면 LLM 없이 실행합니다

**3. 백엔드에 연결**

`backend/.env`에 아래 값을 넣고 백엔드를 다시 시작합니다. 기본값은 목업(`mock`)입니다.
```
EXTRACTOR=ai
```
글자가 있는 PDF는 글자를 그대로 읽고, 이미지(PNG·JPG)와 스캔 PDF는 OCR로 읽습니다. OCR로 읽은 항목은 모두 '확인 필요'로 판정되고 로트는 보류됩니다.

**4. 테스트**
```bash
cd coa-spec-checker/ai
pytest -q                                   # 단위 테스트 + 가상 CoA 3장
```
실물 CoA는 라이선스 문제로 저장소에 올리지 않습니다. 실물로 확인하려면 PDF를 `ai/data/raw/real/` 한 폴더에 풀어 쓰세요. 이 폴더는 `.gitignore` 대상입니다.

**5. LLM 서버 띄우기 (선택)**

LLM 서버를 띄우면 규칙이 못 읽은 항목명·결과 칸과 공급사 문의 초안에 LLM을 씁니다. 띄우지 않아도 모든 기능이 규칙·템플릿으로 동작합니다. (모델: Gemma 4 E2B QAT q4_0, 3.3GB)
```bash
hf download google/gemma-4-E2B-it-qat-q4_0-gguf gemma-4-E2B_q4_0-it.gguf --local-dir ~/.cache/coa-bench/models
docker compose -f ai/docker-compose.llm.yml up -d      # 포트 8090, CPU 4스레드, 메모리 약 2GB
```
`backend/.env`에 아래 값을 넣습니다.
```
LLM_BASE_URL=http://127.0.0.1:8090
INQUIRY_DRAFTER=ai
```
- `INQUIRY_DRAFTER=ai`는 AI 문의 초안을 쓸 때만 넣습니다
- 백엔드를 Docker로 띄울 때는 주소를 `http://host.docker.internal:8090`이나 compose 서비스 이름으로 바꿉니다
- 모델 파일을 다른 곳에 두었다면 `COA_LLM_MODELS=폴더 docker compose -f ai/docker-compose.llm.yml up -d`로 지정합니다
- 맥 Docker CPU 4스레드 기준으로 처음 보는 항목명·열린 문장 1개에 약 3~18초, 문의 초안 1통에 약 40초 걸립니다

**6. 열화 처리 도구 (선택)**

평가용 스캔본을 만듭니다. 원본 CoA(PDF·이미지)를 열화 단계별로 글자 층이 없는 PDF로 바꾸고 목록(`manifest.csv`)을 씁니다.
```bash
cd coa-spec-checker/ai
python tools/degrade.py data/raw/real/*.pdf --out data/generated/degraded              # 기본 4단계
python tools/degrade.py a.pdf --out out --levels levels.json --format png             # 단계 직접 지정, PNG
```
- 같은 `--seed`면 같은 결과가 나옵니다
- 단계 설정 JSON 예: `{"fax": {"dpi": 150, "rotate": 1.0, "blur": 0.8, "jpeg_quality": 40}}`. 쓸 수 있는 키는 `tools/degrade.py` 맨 위 설명에 있습니다
- 같은 원본에서 만든 변형본은 개발용과 평가용에 나눠 넣지 마세요
