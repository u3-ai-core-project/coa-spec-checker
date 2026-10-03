"""[담당: 공통] 테스트 공통 픽스처. DB 픽스처와 토큰 픽스처는 각 API 작업 때 추가한다."""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)
