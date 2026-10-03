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

**6. 서버 실행**
```bash
python -m uvicorn app.main:app --reload
```

**7. 확인**
- Swagger UI: http://127.0.0.1:8000/docs
- 헬스체크: http://127.0.0.1:8000/health
