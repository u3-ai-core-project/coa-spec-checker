"""[담당: 고도영] 열화 처리 도구: CoA(PDF·이미지) → 열화 단계별 스캔본 + 목록 CSV (AI 추출 업무 분담 '열화 처리 스크립트').

    python tools/degrade.py data/raw/real/*.pdf --out data/generated/degraded
    python tools/degrade.py a.pdf --out out --levels levels.json --format png

- 단계마다 글자 층이 없는 PDF(쪽 전부)를 만든다. 업로드 API 에 그대로 넣으면 OCR 경로로 읽힌다. --format png 면 첫 쪽 이미지.
- 단계 설정(JSON): {"단계 이름": {"dpi": 200, "rotate": 2.0, "blur": 1.5, "jpeg_quality": 60}, ...}
  dpi 는 필수, 나머지는 선택. rotate 는 반시계 방향 도(캔버스 크기는 그대로), blur 는 가우시안 반경,
  jpeg_quality 는 JPEG 로 한 번 저장했다 읽기, gray 는 회색조, noise 는 종이 얼룩 같은 잡음 세기,
  source_dpi 는 이 해상도로 그린 뒤 dpi 로 줄이기.
  값을 목록으로 적으면 원본·단계마다 뽑는다. dpi 는 목록 중 하나, rotate·blur·jpeg_quality 는 [최소, 최대] 범위(rotate 는 방향도 무작위).
  실제로 뽑힌 값은 manifest.csv 의 params 에 남고, 같은 --seed 면 같은 값이 나온다(잡음 무늬는 매번 다르다).
- 기본값(DEFAULT_LEVELS)은 생성기 v2(ai/generator/coa_degrade.py)와 같은 조건이다. 생성기는 첫 쪽만 그리고
  pypdfium2 가 필요해, 실물 CoA(여러 쪽)용으로 PyMuPDF 로 같은 조건을 다시 적었다.
- manifest.csv 의 group 은 원본 이름이다. 같은 원본에서 만든 변형본은 개발용·평가용에 나눠 넣지 않는다 (기획안 v2 10장 분리 원칙).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import random
from pathlib import Path

import pymupdf
from PIL import Image, ImageChops, ImageFilter

DEFAULT_LEVELS: dict[str, dict] = {
    "original": {"dpi": 200},
    "lowres": {"source_dpi": 200, "dpi": [72, 75, 80, 90], "gray": True, "jpeg_quality": [35, 55]},
    "skew": {"dpi": 150, "rotate": [1.5, 4.0], "noise": 18, "jpeg_quality": [60, 80]},
    "blur": {"dpi": 150, "blur": [1.2, 2.0], "jpeg_quality": [60, 80]},
}
_KEYS = {"dpi", "source_dpi", "gray", "rotate", "blur", "noise", "jpeg_quality"}


def load_levels(path: str | Path) -> dict[str, dict]:
    levels = json.loads(Path(path).read_text(encoding="utf-8"))
    for name, p in levels.items():
        unknown = set(p) - _KEYS
        if unknown or "dpi" not in p:
            raise ValueError(f"단계 '{name}' 설정 오류: 모르는 키 {sorted(unknown)} / dpi 필수 (쓸 수 있는 키: {sorted(_KEYS)})")
    return levels


def degrade(sources: list[Path], out_dir: Path, *, levels: dict[str, dict] | None = None,
            fmt: str = "pdf", seed: int = 42) -> list[dict]:
    """원본마다 단계별 파일을 out_dir/<원본 이름>/<단계>.<pdf|png> 로 쓰고 manifest.csv 행 목록을 돌려준다."""
    levels = levels or DEFAULT_LEVELS
    out_dir = Path(out_dir)
    rows = []
    for src in sources:
        src = Path(src)
        (out_dir / src.stem).mkdir(parents=True, exist_ok=True)
        for name, spec in levels.items():
            params = _sample(spec, random.Random(f"{seed}:{src.name}:{name}"))
            pages = [_apply(im, params) for im in _render(src, params)]
            rel = Path(src.stem) / f"{name}.{fmt}"
            if fmt == "png":
                pages[0].save(out_dir / rel)
            else:
                _save_pdf(pages, params["dpi"], out_dir / rel)
            rows.append({"group": src.stem, "source": src.name, "level": name, "file": rel.as_posix(),
                         "params": json.dumps(params, ensure_ascii=False)})
    with open(out_dir / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["group", "source", "level", "file", "params"])
        w.writeheader()
        w.writerows(rows)
    return rows


def _sample(spec: dict, rng: random.Random) -> dict:
    """범위로 적은 값을 이번 원본·단계에 쓸 값 하나로 정한다."""
    p = dict(spec)
    if isinstance(p["dpi"], list):
        p["dpi"] = rng.choice(p["dpi"])
    if isinstance(p.get("rotate"), list):
        p["rotate"] = round(rng.uniform(*p["rotate"]) * rng.choice([-1, 1]), 2)
    if isinstance(p.get("blur"), list):
        p["blur"] = round(rng.uniform(*p["blur"]), 2)
    if isinstance(p.get("jpeg_quality"), list):
        p["jpeg_quality"] = rng.randint(*p["jpeg_quality"])
    return p


def _render(src: Path, p: dict) -> list[Image.Image]:
    dpi = p.get("source_dpi", p["dpi"])
    mode = "L" if p.get("gray") else "RGB"
    with pymupdf.open(src) as doc:  # 이미지 파일도 pymupdf 가 1쪽 문서로 연다
        pages = [Image.open(io.BytesIO(page.get_pixmap(dpi=dpi).tobytes("png"))).convert(mode) for page in doc]
    if dpi == p["dpi"]:
        return pages
    return [im.resize((int(im.width * p["dpi"] / dpi), int(im.height * p["dpi"] / dpi)), Image.BILINEAR) for im in pages]


def _apply(im: Image.Image, p: dict) -> Image.Image:
    if p.get("rotate"):
        im = im.rotate(p["rotate"], fillcolor="white", resample=Image.BICUBIC)
    if p.get("blur"):
        im = im.filter(ImageFilter.GaussianBlur(p["blur"]))
    if p.get("noise"):
        im = _noise(im, p["noise"])
    if p.get("jpeg_quality"):
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=int(p["jpeg_quality"]))
        im = Image.open(io.BytesIO(buf.getvalue())).convert(im.mode)
    return im


def _noise(im: Image.Image, amount: float) -> Image.Image:
    """종이 얼룩 같은 옅은 잡음 (생성기 v2 와 같은 식)."""
    n = Image.effect_noise(im.size, amount).point(lambda v: 255 - max(0, v - 128) // 3)
    return ImageChops.multiply(im, n.convert(im.mode))


def _save_pdf(pages: list[Image.Image], dpi: int, path: Path) -> None:
    doc = pymupdf.open()
    for im in pages:
        buf = io.BytesIO()
        im.save(buf, "PNG")
        page = doc.new_page(width=im.width * 72 / dpi, height=im.height * 72 / dpi)
        page.insert_image(page.rect, stream=buf.getvalue())
    doc.save(path)
    doc.close()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python tools/degrade.py", description="CoA 열화 단계별 스캔본 만들기")
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--levels", type=Path, help="단계 설정 JSON (없으면 기본 4단계)")
    ap.add_argument("--format", choices=["pdf", "png"], default="pdf")
    ap.add_argument("--seed", type=int, default=42, help="범위로 적은 값을 뽑을 시드")
    args = ap.parse_args(argv)
    rows = degrade(args.files, args.out, levels=load_levels(args.levels) if args.levels else None, fmt=args.format,
                   seed=args.seed)
    print(f"{len({r['group'] for r in rows})}개 원본 × {len(rows) // max(1, len({r['group'] for r in rows}))}단계 "
          f"= {len(rows)}개 → {args.out}")


if __name__ == "__main__":
    main()
