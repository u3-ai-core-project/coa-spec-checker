"""열화 처리 도구: CoA → 단계별 스캔본(글자 층 없는 PDF 또는 PNG) + 목록 CSV."""
import csv
import json

import pymupdf
from PIL import Image

from coa_ai import extract
from tools.degrade import DEFAULT_LEVELS, degrade, load_levels


def test_each_level_becomes_image_only_pdf(fixture_pdf, tmp_path):
    rows = degrade([fixture_pdf("COA_A_0007.pdf")], tmp_path)
    assert [r["level"] for r in rows] == list(DEFAULT_LEVELS)
    for r in rows:
        with pymupdf.open(tmp_path / r["file"]) as doc:
            assert len(doc) == 1 and not doc[0].get_text().strip()  # 스캔본처럼 글자 층이 없다
    with open(tmp_path / "manifest.csv", encoding="utf-8") as f:
        manifest = list(csv.DictReader(f))
    # 같은 원본의 변형본은 group 으로 묶어 개발용·평가용에 나눠 넣지 않게 한다
    assert {m["group"] for m in manifest} == {"COA_A_0007"} and len(manifest) == 4
    assert json.loads(manifest[2]["params"]) == DEFAULT_LEVELS["skew"]


def test_png_output_sizes(fixture_pdf, tmp_path):
    rows = degrade([fixture_pdf("COA_A_0007.pdf")], tmp_path, fmt="png")
    size = {r["level"]: Image.open(tmp_path / r["file"]).size for r in rows}
    assert abs(size["lowres"][0] * 2 - size["original"][0]) <= 2   # 100 dpi vs 200 dpi
    assert size["skew"][0] > size["original"][0]                    # 기울이면 캔버스가 넓어진다
    assert size["blur"] == size["original"]


def test_custom_levels_from_json(fixture_pdf, tmp_path):
    path = tmp_path / "levels.json"
    path.write_text(json.dumps({"fax": {"dpi": 150, "rotate": 1.0, "blur": 0.8, "jpeg_quality": 40}}))
    levels = load_levels(path)
    rows = degrade([fixture_pdf("COA_D_0007.pdf")], tmp_path / "out", levels=levels, fmt="png")
    assert [r["level"] for r in rows] == ["fax"]
    assert (tmp_path / "out" / rows[0]["file"]).exists()


def test_unknown_level_key_is_rejected(tmp_path):
    import pytest
    path = tmp_path / "levels.json"
    path.write_text(json.dumps({"bad": {"dpi": 200, "sharpen": 2}}))
    with pytest.raises(ValueError, match="sharpen"):
        load_levels(path)


def test_degraded_pdf_is_read_by_ocr(fixture_pdf, tmp_path):
    rows = degrade([fixture_pdf("COA_A_0007.pdf")], tmp_path, levels={"original": DEFAULT_LEVELS["original"]})
    r = extract(tmp_path / rows[0]["file"], material_code="LIOH")
    assert r.lot_no == "SL25-0008" and len(r.items) == 15
