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
    skew = json.loads(manifest[2]["params"])
    assert skew["dpi"] == 150 and 1.5 <= abs(skew["rotate"]) <= 4 and 60 <= skew["jpeg_quality"] <= 80


def test_png_output_sizes(fixture_pdf, tmp_path):
    rows = degrade([fixture_pdf("COA_A_0007.pdf")], tmp_path, fmt="png")
    size = {r["level"]: Image.open(tmp_path / r["file"]).size for r in rows}
    assert 72 / 200 - 0.01 <= size["lowres"][0] / size["original"][0] <= 90 / 200 + 0.01  # 72~90 dpi vs 200 dpi
    assert size["skew"] == size["blur"]                             # 150 dpi, 기울여도 캔버스는 그대로 (생성기 v2)
    assert abs(size["blur"][0] * 200 - size["original"][0] * 150) <= 200


def test_default_levels_follow_generator_v2():
    # 생성기 v2 (ai/generator/coa_degrade.py) 와 같은 조건
    assert DEFAULT_LEVELS["lowres"] == {"source_dpi": 200, "dpi": [72, 75, 80, 90], "gray": True, "jpeg_quality": [35, 55]}
    assert DEFAULT_LEVELS["skew"] == {"dpi": 150, "rotate": [1.5, 4.0], "noise": 18, "jpeg_quality": [60, 80]}
    assert DEFAULT_LEVELS["blur"] == {"dpi": 150, "blur": [1.2, 2.0], "jpeg_quality": [60, 80]}


def test_same_seed_gives_same_conditions(fixture_pdf, tmp_path):
    src = [fixture_pdf("COA_A_0007.pdf")]
    a = degrade(src, tmp_path / "a", seed=7)
    b = degrade(src, tmp_path / "b", seed=7)
    c = degrade(src, tmp_path / "c", seed=8)
    assert [r["params"] for r in a] == [r["params"] for r in b]
    assert [r["params"] for r in a] != [r["params"] for r in c]


def test_ranges_are_sampled_for_each_source(fixture_pdf, tmp_path):
    rows = degrade([fixture_pdf("COA_A_0007.pdf"), fixture_pdf("COA_D_0007.pdf")], tmp_path, seed=1)
    lows = [json.loads(r["params"]) for r in rows if r["level"] == "lowres"]
    assert all(isinstance(p["dpi"], int) and p["gray"] is True for p in lows)
    assert lows[0] != lows[1]


def test_gray_level_saves_gray_image(fixture_pdf, tmp_path):
    degrade([fixture_pdf("COA_A_0007.pdf")], tmp_path, levels={"low": DEFAULT_LEVELS["lowres"]}, fmt="png")
    assert Image.open(tmp_path / "COA_A_0007" / "low.png").mode == "L"


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
