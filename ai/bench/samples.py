"""[담당: 고도영] 모델 테스트 샘플: 텍스트 PDF CoA → 스캔본처럼 만든 이미지 4단계 + 정답 JSON.

정답은 같은 PDF 를 텍스트 경로(coa_ai.extract)로 읽은 결과다. 텍스트 PDF 는 글자가 정확하고,
가상 3장은 이 결과가 정답 라벨과 같음을 확인했다.
열화 값(LEVELS)은 모델을 고를 때(2026-10-18) 쓴 값이다. 결과표를 비교할 수 있게 그대로 둔다.
최신 조건(생성기 v2)은 tools/degrade.py 의 DEFAULT_LEVELS 다.

실물 CoA 는 라이선스 문제로 저장소에 넣지 않으므로 결과는 gitignore 대상인 ai/data/generated/bench 에 쓴다.

    python bench/samples.py
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pymupdf
from PIL import Image, ImageFilter

from coa_ai import ExtractionFailed, extract

AI_DIR = Path(__file__).resolve().parents[1]
REAL_DIR = AI_DIR / "data" / "raw" / "real"
FIXTURES = AI_DIR / "tests" / "fixtures"
OUT = AI_DIR / "data" / "generated" / "bench"

DPI = 200
# 단계 이름: (렌더링 dpi, 후처리)
LEVELS = {
    "original": (DPI, None),
    "lowres": (100, None),                                     # 저해상도 스캔
    "skew": (DPI, lambda im: im.rotate(2, expand=True, fillcolor="white", resample=Image.BICUBIC)),  # 2° 기울기
    "blur": (DPI, lambda im: im.filter(ImageFilter.GaussianBlur(1.5))),  # 초점 흐림
}


def sources() -> list[tuple[Path, str]]:
    """(PDF, 원자재). 가상 CoA 는 수산화리튬, 실물은 탄산리튬."""
    out = [(p, "LIOH") for p in sorted(FIXTURES.glob("COA_*.pdf"))]
    out += [(p, "LI2CO3") for p in sorted(REAL_DIR.glob("*.pdf"))]
    return out


def render(pdf: Path, dpi: int) -> Image.Image:
    with pymupdf.open(pdf) as doc:
        pix = doc[0].get_pixmap(dpi=dpi)
        return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")


def truth(pdf: Path, material: str) -> dict | None:
    try:
        r = extract(pdf, material_code=material)
    except ExtractionFailed:
        return None  # CoA 가 아닌 문서는 모델 테스트에서 뺀다
    d = r.to_dict()
    d["items"] = [{k: i[k] for k in ("raw_name", "normalized_name", "mapping_source", "raw_value", "raw_spec", "unit")}
                  for i in d["items"]]
    return d


def main() -> None:
    (OUT / "images").mkdir(parents=True, exist_ok=True)
    (OUT / "truth").mkdir(parents=True, exist_ok=True)
    manifest = []
    for pdf, material in sources():
        t = truth(pdf, material)
        if t is None:
            continue
        doc_id = pdf.stem
        t["material"] = material
        (OUT / "truth" / f"{doc_id}.json").write_text(json.dumps(t, ensure_ascii=False, indent=1))
        for level, (dpi, post) in LEVELS.items():
            im = render(pdf, dpi)
            if post:
                im = post(im)
            path = OUT / "images" / f"{doc_id}__{level}.png"
            im.save(path)
            manifest.append({"id": f"{doc_id}__{level}", "doc": doc_id, "level": level, "dpi": dpi,
                             "material": material, "image": str(path.relative_to(OUT))})
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    docs = len({m["doc"] for m in manifest})
    print(f"{docs} docs x {len(LEVELS)} levels = {len(manifest)} images -> {OUT}")


if __name__ == "__main__":
    main()
