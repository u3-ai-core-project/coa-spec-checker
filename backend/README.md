# # Backend

### 실행 방법

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
`.env` 열고 아래 값 확인 (Docker로 DB를 띄우면 그대로 사용):
```
DATABASE_URL=postgresql+psycopg://coa:coa@localhost:5432/coa
JWT_SECRET=change-me
ACCESS_TOKEN_EXPIRE_MINUTES=60
LOW_CONFIDENCE_THRESHOLD=0.8
UPLOAD_DIR=storage/uploads
```
`DATABASE_URL`은 반드시 `postgresql+psycopg://`로 시작해야 합니다. `postgresql://`로 쓰면 SQLAlchemy가 설치되지 않은 `psycopg2` 드라이버를 찾다가 `ModuleNotFoundError: No module named 'psycopg2'` 에러가 발생합니다.

**4. DB 생성(최초 1회)**

**방법 A. Docker 사용 (권장)**
```bash
docker compose up -d
```
`docker-compose.yml`에 사용자 `coa`, 비밀번호 `coa`, DB `coa`가 설정되어 있어 별도 생성 작업이 필요 없습니다.

**방법 B. 로컬 PostgreSQL 사용**
* [postgresql.org](https://www.postgresql.org/download/) 에서 설치
* 설치 중 superuser(postgres) 비밀번호 설정
```bash
psql -U postgres
CREATE USER coa WITH PASSWORD 'coa';
CREATE DATABASE coa OWNER coa;
\q
```
다른 계정이나 비밀번호를 쓰면 `.env`의 `DATABASE_URL`도 같이 바꿔야 합니다.

**5. 스키마 마이그레이션 적용 (Alembic)**

이 프로젝트는 스키마 관리를 Alembic으로 합니다. `create_all()` 같은 자동 테이블 생성은 쓰지 않으므로, DB 생성 직후 반드시 아래 명령으로 최신 스키마를 적용해야 합니다.
```bash
alembic upgrade head
```

**모델(`app/models/*.py`)을 수정한 사람은 반드시** 아래 두 명령을 실행하고, 생성된 `alembic/versions/*.py` 파일을 열어 내용을 확인한 뒤 커밋해서 PR에 포함해야 합니다.
```bash
alembic revision --autogenerate -m "변경 내용 설명"
alembic upgrade head
```
이 절차를 건너뛰면 다른 팀원 로컬 DB에서 컬럼 누락으로 인한 500 에러가 발생합니다.

**5-1. 시드 적재 (최초 1회, 여러 번 실행해도 됨)**
```bash
python -m seeds.seed
```
사용자 계정, 사내 규격 세트·항목, 항목명 매핑 사전을 넣습니다. 이미 있는 데이터는 건너뜁니다.
- 규격 세트: `seeds/data/spec_sets.csv` (원자재 + 등급 + 버전, 원자재별 기본 세트 1개)
- 규격 항목: `seeds/data/spec_items_*.csv` (원자재별로 파일을 나눠도 됨)
- 매핑 사전: `seeds/data/item_mappings.csv`

현재 탄산리튬 D1 값은 **임시값**입니다. 확정 규격 CSV를 받으면 파일만 바꾸면 됩니다.

**6. 서버 실행**
```bash
python -m uvicorn app.main:app --reload
```

**7. 확인**
- Swagger UI: http://127.0.0.1:8000/docs
- 헬스체크: http://127.0.0.1:8000/health

**8. AI 추출기 연결 (선택)**

기본값은 목업 추출기(`EXTRACTOR=mock`)로, `app/pipeline/mock_data`의 JSON을 추출 결과로 씁니다. 실제 CoA를 읽으려면 같은 가상환경에 AI 패키지를 설치하고 `.env`에 `EXTRACTOR=ai`를 넣습니다.
```bash
pip install -e ../ai
```
```
EXTRACTOR=ai
```
- 글자가 있는 PDF는 글자를 그대로 읽고, 이미지(PNG·JPG)와 스캔 PDF는 OCR로 읽습니다. OCR로 읽은 항목은 신뢰도가 0.75 이하라 모두 '원본 확인'으로 판정되고 로트는 보류됩니다.
- 스캔본을 처음 읽을 때 OCR 모델 파일을 내려받으므로 인터넷이 필요합니다.
- AI 패키지 설명과 표준 항목명 표는 `ai/README.md`에 있습니다.
- LLM 기능(선택): `ai/docker-compose.llm.yml`로 LLM 서버를 띄우고 `.env`에 `LLM_BASE_URL=http://127.0.0.1:8090`을 넣으면, 처음 보는 항목명에 표준 항목명을 제안합니다(항상 확인 필요). `INQUIRY_DRAFTER=ai`를 넣으면 follow-ups의 문의 초안을 LLM이 쓰고, 검사에 걸리거나 서버가 없으면 템플릿으로 대신합니다(`source=template_fallback`). 비워 두면 지금처럼 동작합니다.

### 판정 정책 설정 (v1.4안)

판정 규칙 일부는 팀 결정에 따라 바뀌므로 `.env` 설정값으로 바꿀 수 있게 했습니다. 비워 두면 API 명세 기준 기본값입니다.
규칙은 사유코드(`reason_code`)만 내고, 사유코드 → 판정(5종) 대응은 `app/services/judgement/policy.py`의 정책 표가 정합니다.

| 설정 | 기본값 | 의미 |
| --- | --- | --- |
| `REASON_JUDGEMENT` | `{}` | 사유코드별 판정 덮어쓰기. 예: `{"SPEC_COPIED": "check"}`. 부적합·누락 코드는 바꿀 수 없음 |
| `ND_LIMIT_INCLUSIVE` | `true` | 검출 안 됨: 검출한계 == 사내 상한이면 적합 |
| `UNMAPPED_AI_ITEM` | `reference` | 사내 규격에 없는 AI 추정 항목명: `reference`(참고) / `check`(확인 필요) |
| `CROSS_RULES` | `["heavy_metal_total", "na_k_sum"]` | 켤 교차 규칙. 중금속 총량 → Pb·Cu 판정, Na+K 합산 → Na·K 원소별 판정 |

잘못된 값을 넣으면 서버가 시작할 때 오류로 알려 줍니다. 정책을 바꾸면 이후 판정부터 적용됩니다.

판정 관련 파일 (`app/services/judgement/`)
- `item_judge.py`: 항목 1개 판정 (사유코드 → 판정, 해결 조건)
- `policy.py`: 판정 정책
- `resolutions.py`: 사유코드별 해결 조건 문구·수치
- `cross_rules.py`: 여러 항목을 함께 보는 규칙 (중금속 총량 → Pb·Cu, Na+K 합산 → Na·K 원소별)
- `engine.py`: 문서 1건 전체 판정 (DB 없이 호출 가능 → 평가 스크립트에서 바로 사용 가능)
