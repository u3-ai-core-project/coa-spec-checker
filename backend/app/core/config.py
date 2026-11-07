"""[담당: 공통(장수민 생성, 둘 다 수정)] 환경설정. 값은 .env 또는 환경변수에서 읽는다."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # DB
    DATABASE_URL: str = "postgresql+psycopg://coa:coa@localhost:5432/coa"

    # 인증 (명세 1장: access token 60분, 리프레시 토큰 없음)
    JWT_SECRET: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # 판정 (명세 1장: confidence < 0.8 이면 신뢰도 낮음)
    LOW_CONFIDENCE_THRESHOLD: float = 0.8

    # DB 세션 시간대. 일시 값이 +09:00 오프셋으로 응답된다 (명세 1장 예시)
    DB_TIMEZONE: str = "Asia/Seoul"

    # 파일
    UPLOAD_DIR: str = "storage/uploads"
    MAX_UPLOAD_MB: int = 20
    MAX_BATCH_FILES: int = 20   # 일괄 접수 한 번에 올릴 수 있는 CoA 수 (멘토님 UC01 "CoA 1~20개")

    # AI 추출기. "mock" 이면 app/pipeline/mock_data 의 JSON 을 결과로 사용 (AI 파트 연결 전)
    EXTRACTOR: str = "mock"
    MOCK_EXTRACTION_DIR: str = "app/pipeline/mock_data"

    # 산화물 → 원소 환산 계수 (명세 2.2). 원소 질량 / 산화물 질량 (원자량으로 계산, 소수 넷째 자리)
    OXIDE_TO_ELEMENT: dict[str, float] = {
        "Na2O": 0.7419,   # Na
        "K2O": 0.8301,    # K  = 2×39.098 / 94.196
        "CaO": 0.7147,    # Ca
        "MgO": 0.6031,    # Mg = 24.305 / 40.304
        "Fe2O3": 0.6994,  # Fe
    }

    # ---- 판정 정책 (v1.4안). 팀 결정에 따라 바꾸는 값. 자세한 설명은 app/services/judgement/policy.py ----
    # 사유코드별 판정 덮어쓰기. 예) {"SPEC_COPIED": "check"}  (.env 에서는 JSON 문자열로)
    # 비워 두면 API 명세 기준 기본값을 쓴다. 부적합·누락 코드는 바꿀 수 없다.
    REASON_JUDGEMENT: dict[str, str] = {}
    # 검출 안 됨: 검출한계 == 사내 상한일 때 적합으로 볼지 (True: 이하면 적합, False: 미만이어야 적합)
    ND_LIMIT_INCLUSIVE: bool = True
    # 사내 규격에 없는 항목 중 AI 가 항목명을 추정한 것: "check"(확인 필요, 기본) | "reference"(참고, 판정 안 함)
    # 멘토님 판정표 "항목명 모호·화학종 불명 → 확인 필요" (10.25 기본값 변경)
    UNMAPPED_AI_ITEM: str = "check"
    # 켜 둘 교차 규칙 (여러 항목을 함께 보는 규칙). 사용 가능: heavy_metal_total, na_k_sum
    CROSS_RULES: list[str] = ["heavy_metal_total", "na_k_sum"]
    # 중금속 총량 규칙에 쓰는 사내 표준 항목명 (규격 시드·매핑 사전의 normalized_name 과 같아야 함)
    HEAVY_METAL_TOTAL_NAME: str = "중금속 총량"
    HEAVY_METAL_TARGET_NAME: str = "Pb"
    # 중금속 총량(Pb 기준)만으로는 값을 알 수 없는 다른 중금속. 사내 필수 항목인데 CoA 에 없고 총량만 있으면 확인 필요
    # (총량은 Pb 기준으로 잰 값이라 Pb 상한 판단에만 쓰고, 다른 금속의 상한 판단에는 쓰지 않는다. 생성기 v2 AMBIGUOUS_ANALYTE)
    HEAVY_METAL_OTHER_NAMES: list[str] = ["Cu"]
    # Na+K 합산 규칙에 쓰는 사내 표준 항목명. 합산 줄의 normalized_name 이 NA_K_SUM_NAME 이어야 규칙이 적용된다.
    # 원소별 판정: 합산 ≤ 그 원소 상한이면 그 원소 적합, 아니면 그 원소만 SUM_ONLY (10.25 회의 결정 2)
    NA_K_SUM_NAME: str = "Na+K"
    NA_K_SUM_ELEMENTS: list[str] = ["Na", "K"]

    # 이상 패턴 identical_values: 같은 협력사의 다른 로트 하나와 실측값이 이 개수 이상 같을 때만 경고 (10.25 회의 결정 4).
    # 정수 ppm 값이 우연히 1~2개 같은 경우를 거르고, 결과표가 통째로 반복된 경우(멘토님 데모 20)만 잡는다.
    IDENTICAL_VALUES_MIN_MATCHES: int = 3

    # 공급사 문의 초안 생성기 (v1.4안 4.22). "template" 이면 inquiry_draft.TemplateDrafter,
    # "ai" 면 app.pipeline.ai_drafter.AIDrafter (LLM_BASE_URL 필요, 실패하면 템플릿으로 대체).
    INQUIRY_DRAFTER: str = "template"
    # LLM 서버 주소 (ai/docker-compose.llm.yml 의 Gemma 서버, 예: http://127.0.0.1:8090).
    # 비워 두면 LLM 없이 동작한다: 처음 보는 항목명은 제안 없이 확인 필요, 문의 초안은 템플릿.
    LLM_BASE_URL: str | None = None

    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
