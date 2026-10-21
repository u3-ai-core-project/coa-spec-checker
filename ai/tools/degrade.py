"""[담당: 고도영] 열화 처리 도구: CoA(PDF·이미지) → 열화 단계별 스캔본 + 목록 CSV (AI 추출 업무 분담 '열화 처리 스크립트').

    python tools/degrade.py data/raw/real/*.pdf --out data/generated/degraded
    python tools/degrade.py a.pdf --out out --levels levels.json --format png

- 단계마다 글자 층이 없는 PDF(쪽 전부)를 만든다. 업로드 API 에 그대로 넣으면 OCR 경로로 읽힌다. --format png 면 첫 쪽 이미지.
- 단계 설정(JSON): {"단계 이름": {"dpi": 200, "rotate": 2.0, "blur": 1.5, "jpeg_quality": 60}, ...}
  dpi 는 필수, 나머지는 선택. rotate 는 반시계 방향 도(캔버스를 넓힘), blur 는 가우시안 반경, jpeg_quality 는 JPEG 로 한 번 저장했다 읽기.
- 기본값(DEFAULT_LEVELS)은 모델 테스트(bench/samples.py LEVELS)와 같은 임시값이다. 소성훈 님 열화 조건 표를 받으면 JSON 만 바꾼다.
- manifest.csv 의 group 은 원본 이름이다. 같은 원본에서 만든 변형본은 개발용·평가용에 나눠 넣지 않는다 (기획안 v2 10장 분리 원칙).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path

import pymupdf
from PIL import Image, ImageFilter

DEFAULT_LEVELS: dict[str, dict] = {
    "original": {"dpi": 200},
    "lowres": {"dpi": 100},
    "skew": {"dpi": 200, "rotate": 2.0},
    "blur": {"dpi": 200, "blur": 1.5},
}
_KEYS = {"dpi", "rotate", "blur", "jpeg_quality"}


def load_levels(path: str | Path) -> dict[str, dict]:
    levels = json.loads(Path(path).read_text(encoding="utf-8"))
    for name, p in levels.items():
        unknown = set(p) - _KEYS
        if unknown or "dpi" not in p:
            raise ValueError(f"단계 '{name}' 설정 오류: 모르는 키 {sorted(unknown)} / dpi 필수 (쓸 수 있는 키: {sorted(_KEYS)})")
    return levels


def degrade(sources: list[Path], out_dir: Path, *, levels: dict[str, dict] | None = None,
            fmt: str = "pdf") -> list[dict]:
    """원본마다 단계별 파일을 out_dir/<원본 이름>/<단계>.<pdf|png> 로 쓰고 manifest.csv 행 목록을 돌려준다."""
    levels = levels or DEFAULT_LEVELS
    out_dir = Path(out_dir)
    rows = []
    for src in sources:
        src = Path(src)
        (out_dir / src.stem).mkdir(parents=True, exist_ok=True)
        for name, params in levels.items():
            pages = [_apply(im, params) for im in _render(src, params["dpi"])]
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


def _render(src: Path, dpi: int) -> list[Image.Image]:
    with pymupdf.open(src) as doc:  # 이미지 파일도 pymupdf 가 1쪽 문서로 연다
        return [Image.open(io.BytesIO(p.get_pixmap(dpi=dpi).tobytes("png"))).convert("RGB") for p in doc]


def _apply(im: Image.Image, p: dict) -> Image.Image:
    if p.get("rotate"):
        im = im.rotate(p["rotate"], expand=True, fillcolor="white", resample=Image.BICUBIC)
    if p.get("blur"):
        im = im.filter(ImageFilter.GaussianBlur(p["blur"]))
    if p.get("jpeg_quality"):
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=int(p["jpeg_quality"]))
        im = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
    return im


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
    args = ap.parse_args(argv)
    rows = degrade(args.files, args.out, levels=load_levels(args.levels) if args.levels else None, fmt=args.format)
    print(f"{len({r['group'] for r in rows})}개 원본 × {len(rows) // max(1, len({r['group'] for r in rows}))}단계 "
          f"= {len(rows)}개 → {args.out}")


if __name__ == "__main__":
    main()
