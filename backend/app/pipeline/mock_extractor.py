"""[담당: 장수민] AI 파트 완성 전까지 쓰는 목업 추출기.

업로드한 파일 이름(확장자 제외)과 같은 이름의 JSON 이 mock_data 폴더에 있으면 그것을,
없으면 default.json 을 추출 결과로 돌려준다. JSON 형식은 ExtractionInput (명세 2.1 의 AI 필드).

예) CoA_Chengxin_L240901.pdf 업로드 → mock_data/CoA_Chengxin_L240901.json
정답 라벨 JSON 을 이 폴더에 넣으면 업로드부터 판정까지 실제 흐름을 그대로 시험할 수 있다.
"""
import json
from pathlib import Path

from app.pipeline.extractor import ExtractionError
from app.schemas.extraction import ExtractionInput


class MockExtractor:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir

    def extract(self, file_path: Path, *, material_code: str, original_name: str | None = None) -> ExtractionInput:
        stem = Path(original_name or file_path.name).stem
        candidate = self.data_dir / f"{stem}.json"
        path = candidate if candidate.exists() else self.data_dir / "default.json"
        if not path.exists():
            raise ExtractionError("목업 추출 데이터가 없습니다")
        return ExtractionInput.model_validate(json.loads(path.read_text(encoding="utf-8")))
