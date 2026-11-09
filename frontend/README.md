### Frontend 실행 방법

React + Vite + TypeScript 기반입니다. Node.js 22에서 확인했습니다.

**1. 패키지 설치**
```bash
cd coa-spec-checker/frontend
npm install
```

**2. 환경변수 파일 생성**
```bash
# Windows
copy .env.example .env
# macOS/Linux
cp .env.example .env
```
`.env`를 열고 값을 확인합니다.
```
VITE_API_BASE_URL=http://localhost:8000
VITE_USE_MOCK=true
```
- `VITE_API_BASE_URL`: 백엔드 주소. 뒤에 `/api/v1`은 자동으로 붙습니다
- `VITE_USE_MOCK`: 검수·규격 관리 화면이 목업 API를 쓸지 정합니다. 기본값은 `true`(목업)이고, 실제 백엔드에 연결하려면 `false`로 바꿉니다

**3. 백엔드 연동 (실제 백엔드를 쓸 때)**

`backend/README.md`를 보고 백엔드를 먼저 실행합니다. (http://localhost:8000) 백엔드 `CORS_ORIGINS` 기본값에 `http://localhost:5173`이 들어 있어 별도 설정은 필요 없습니다.

**4. 개발 서버 실행**
```bash
npm run dev
```
- 로컬호스트: http://localhost:5173/
- 로그인 계정은 백엔드 시드 계정을 씁니다. (관리자 `admin / admin1234`, 사용자 `user1 / user1234`)

**5. 검수·규격 관리 화면만 단독으로 확인 (선택)**

백엔드 없이 목업 데이터로 화면만 볼 수 있는 개발용 페이지입니다. `VITE_USE_MOCK=true`일 때만 동작하고, 로그인 화면 없이 바로 들어갑니다.
```
http://localhost:5173/dev.html?as=user#/inspection     사용자 · 검수
http://localhost:5173/dev.html?as=admin#/specs         관리자 · 규격 관리
```

**6. 빌드 및 검사**
```bash
npm run build      # 타입 검사 후 dist/ 에 빌드
npm run lint       # ESLint
npm run preview    # 빌드 결과 미리보기
```
