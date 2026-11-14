"""[담당: 홍채령] 운영(production) 환경 비밀키 검사 테스트. DB 불필요."""
import pytest
from pydantic import ValidationError

from app.core.config import Settings

STRONG = "x" * 32


@pytest.mark.parametrize("secret", ["change-me", "short-secret", "x" * 31])
def test_production_rejects_weak_secret(secret):
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None, APP_ENV="production", JWT_SECRET=secret)


def test_production_error_does_not_print_secret():
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, APP_ENV="production", JWT_SECRET="leaky-secret-value")
    assert "leaky-secret-value" not in str(exc.value)


def test_production_accepts_strong_secret():
    assert Settings(_env_file=None, APP_ENV="production", JWT_SECRET=STRONG).APP_ENV == "production"


def test_production_check_ignores_case():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, APP_ENV="Production", JWT_SECRET="change-me")


def test_development_allows_default_secret():
    s = Settings(_env_file=None, JWT_SECRET="change-me")
    assert s.APP_ENV == "development"
