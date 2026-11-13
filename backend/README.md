### Backend 실행 방법

**1. 가상환경 생성 및 활성화**
```bash
cd coa-spec-checker/backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
```

**2. 의존성 설치**
```bash
pip install --upgrade pip   # Windows : python -m pip install --upgrade pip
pip install -r requirements.txt
```

**3. 환경변수 설정**
```bash
# Windows
copy .env.example .env
# macOS/Linux
cp .env.example .env
```
`.env`를 열고 아래 값을 확인합니다. (Docker로 DB를 띄우면 그대로 사용)
```
DATABASE_URL=postgresql+psycopg://coa:coa@localhost:5432/coa
JWT_SECRET=change-me
ACCESS_TOKEN_EXPIRE_MINUTES=60
LOW_CONFIDENCE_THRESHOLD=0.8
UPLOAD_DIR=storage/uploads
```
`DATABASE_URL`은 반드시 `postgresql+psycopg://`로 시작해야 합니다. `postgresql://`로 쓰면 설치되지 않은 `psycopg2` 드라이버를 찾다가 `ModuleNotFoundError: No module named 'psycopg2'` 에러가 발생합니다.

**4. DB 생성 (최초 1회)**

**방법 A. Docker 사용 (권장)**
```bash
docker compose up -d
```
`docker-compose.yml`에 사용자 `coa`, 비밀번호 `coa`, DB `coa`가 설정되어 있어 별도 생성 작업이 필요 없습니다.

**방법 B. 로컬 PostgreSQL 사용**
* [postgresql.org](https://www.postgresql.org/download/)에서 설치
* 설치 중 superuser(postgres) 비밀번호 설정
```bash
psql -U postgres
CREATE USER coa WITH PASSWORD 'coa';
CREATE DATABASE coa OWNER coa;
\q
```
다른 계정이나 비밀번호를 쓰면 `.env`의 `DATABASE_URL`도 같이 바꿔야 합니다.

**5. 스키마 마이그레이션 적용 (Alembic)**

스키마 관리는 Alembic으로 합니다. `create_all()` 같은 자동 테이블 생성은 쓰지 않으므로, DB 생성 직후 반드시 아래 명령으로 최신 스키마를 적용해야 합니다.
```bash
alembic upgrade head
```
모델(`app/models/*.py`)을 수정했다면 아래 두 명령을 실행하고, 생성된 `alembic/versions/*.py` 파일을 열어 내용을 확인한 뒤 커밋해서 PR에 포함합니다.
```bash
alembic revision --autogenerate -m "변경 내용 설명"
alembic upgrade head
```
이 절차를 건너뛰면 다른 팀원 로컬 DB에서 컬럼 누락으로 인한 500 에러가 발생합니다.

기존 DB를 쓰던 중 코드를 새로 받았다면 서버를 끄고 `alembic upgrade head`를 먼저 실행한 뒤 서버를 다시 시작합니다. 새 컬럼이 없는 채로 서버가 뜨면 문서 업로드와 조회에서 오류가 납니다.

**6. 시드 적재 (최초 1회, 여러 번 실행해도 됨)**
```bash
python -m seeds.seed
```
사용자 계정, 사내 규격 세트·항목, 항목명 매핑 사전을 넣습니다. 이미 있는 데이터는 건너뜁니다.
- 규격 세트: `seeds/data/spec_sets.csv`
- 규격 항목: `seeds/data/spec_items_*.csv` (원자재별로 파일을 나눠도 됩니다)
- 매핑 사전: `seeds/data/item_mappings.csv`

개발용 계정은 아래와 같습니다.
```
관리자  admin / admin1234
사용자  user1 / user1234
        user2 / user1234
```
현재 탄산리튬 D1 규격 값은 임시값입니다. 확정 규격 CSV를 받으면 파일만 바꾸면 됩니다.

**7. 서버 실행**
```bash
python -m uvicorn app.main:app --reload
```

**8. 확인**
- Swagger UI: http://127.0.0.1:8000/docs
- 헬스체크: http://127.0.0.1:8000/health

**9. 테스트**
```bash
pytest -q
```
DB가 필요한 테스트는 같은 서버의 `coa_test` DB를 쓰고, 없으면 자동으로 만듭니다. DB 서버에 연결할 수 없으면 해당 테스트는 건너뜁니다.

**10. AI 추출기 연결 (선택)**

기본값은 목업 추출기(`EXTRACTOR=mock`)로, `app/pipeline/mock_data`의 JSON을 추출 결과로 씁니다. 실제 CoA를 읽으려면 같은 가상환경에 AI 패키지를 설치하고 `.env`에 `EXTRACTOR=ai`를 넣습니다.
```bash
pip install -e ../ai
```
```
EXTRACTOR=ai
```
- 스캔본을 처음 읽을 때 OCR 모델 파일을 내려받으므로 인터넷이 필요합니다
- OCR로 읽은 항목은 신뢰도가 0.75 이하라 모두 '원본 확인'으로 판정되고 로트는 보류됩니다
- LLM 서버를 쓰려면 `.env`에 `LLM_BASE_URL=http://127.0.0.1:8090`을 넣습니다. 자세한 방법은 `ai/README.md`를 참고하세요
- 공급사 문의 초안을 LLM으로 쓰려면 `INQUIRY_DRAFTER=ai`를 넣습니다. 검사에 걸리거나 LLM 서버가 없으면 템플릿으로 대신합니다

**11. 판정 정책 설정 (선택)**

판정 규칙 일부는 팀 결정에 따라 바뀌므로 `.env` 값으로 바꿀 수 있습니다. 비워 두면 기본값이 적용되고, 잘못된 값을 넣으면 서버가 시작할 때 오류로 알려 줍니다. 정책을 바꾸면 이후 판정부터 적용됩니다.
```
REASON_JUDGEMENT={"SPEC_COPIED": "check"}
ND_LIMIT_INCLUSIVE=true
UNMAPPED_AI_ITEM=check
CROSS_RULES=["heavy_metal_total", "na_k_sum"]
```
- `REASON_JUDGEMENT`: 사유코드별 판정 덮어쓰기 (기본 `{}`). 부적합·누락 코드는 바꿀 수 없습니다
- `ND_LIMIT_INCLUSIVE`: 검출한계가 사내 상한과 같으면 적합 (기본 `true`)
- `UNMAPPED_AI_ITEM`: 사내 규격에 없는 AI 추정 항목명을 `check`(확인 필요) 또는 `reference`(참고)로 처리 (기본 `check`)
- `CROSS_RULES`: 켤 교차 규칙. 중금속 총량 → Pb·Cu 판정(`heavy_metal_total`), Na+K 합산 → Na·K 원소별 판정(`na_k_sum`)

**12. 처리 실패·재시도 설정 (선택)**

추출이 오래 걸리거나 실패했을 때의 동작은 `.env` 값으로 바꿀 수 있습니다. 비워 두면 기본값이 적용됩니다.
```
EXTRACTION_TIMEOUT_SEC=300
EXTRACTION_AUTO_RETRIES=1
RESUME_STUCK_ON_START=false
MAX_EXTRACTION_ATTEMPTS=2
```
- `EXTRACTION_TIMEOUT_SEC`: 추출 1회의 제한 시간(초). 넘으면 실패로 처리합니다 (기본 300, 5분)
- `EXTRACTION_AUTO_RETRIES`: 시간 초과나 연결 오류 같은 일시 오류일 때 자동으로 다시 시도하는 횟수 (기본 1). 손상된 파일 같은 영구 오류는 다시 시도하지 않습니다
- `RESUME_STUCK_ON_START`: 서버를 켤 때 처리 중이던 문서를 다시 시작할지 여부 (기본 `false`). `false`이면 실패로만 정리하고, `true`이면 시도 횟수가 상한 안인 문서는 다시 시작합니다
- `MAX_EXTRACTION_ATTEMPTS`: 서버 시작 때 자동으로 다시 시작할 수 있는 시도 상한 (기본 2)

평가 스크립트와 데모 PDF 만들기는 `evaluation/README.md`를 참고하세요.
