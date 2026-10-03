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

    # AI 추출기. "mock" 이면 app/pipeline/mock_data 의 JSON 을 결과로 사용 (AI 파트 연결 전)
    EXTRACTOR: str = "mock"
    MOCK_EXTRACTION_DIR: str = "app/pipeline/mock_data"

    # 산화물 → 원소 환산 계수 (명세 2.2). 원소 질량 / 산화물 질량
    OXIDE_TO_ELEMENT: dict[str, float] = {
        "Na2O": 0.7419,   # Na
        "CaO": 0.7147,    # Ca
        "Fe2O3": 0.6994,  # Fe
    }

    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
