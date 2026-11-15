# -*- coding: utf-8 -*-
"""
CoA 열화본 만들기 (4단계: 원본 · 저해상도 · 기울기 · 흐림)
==========================================================
원본(글자 PDF) 한 장에서 스캔·팩스로 받은 것 같은 그림 PDF 를 만든다. 열화본에는 글자 레이어가 없어 OCR 이 필요하다.

  original : 생성기가 그린 글자 PDF 그대로
  lowres   : 70~90 dpi 회색조로 낮춰 저장 (팩스·저화질 스캔)
  skew     : 150 dpi 로 그린 뒤 1.5~4° 기울이고 잡음을 조금 섞음 (비뚤게 놓고 스캔)
  blur     : 150 dpi 로 그린 뒤 가우스 흐림 1.2~2.0 px (초점 안 맞은 스캔·사진)

PDF 를 그림으로 바꿀 때 pypdfium2 를 쓰고 (pip install pypdfium2), 없으면 poppler 의 pdftoppm 을 쓴다.
둘 다 없으면 열화본은 건너뛰고 원본만 남긴다.

열화본은 원본과 같은 분할(dev/eval) 폴더에 들어간다. 그래서 같은 원본에서 나온 변형본이 개발용과 평가용에 섞이지 않는다.
"""

import io
import shutil
import subprocess
import tempfile
from pathlib import Path

_WARNED = set()


def _warn(msg):
    if msg not in _WARNED:
        print("  (주의) " + msg)
        _WARNED.add(msg)


def render(pdf_path, dpi, gray=False):
    """PDF 첫 쪽 -> PIL 그림.  못 하면 None"""
    from PIL import Image
    try:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(str(pdf_path))
        img = pdf[0].render(scale=dpi / 72).to_pil()
        pdf.close()
    except ImportError:
        if not shutil.which("pdftoppm"):
            _warn("pypdfium2 도 pdftoppm 도 없어 열화본을 만들지 못했습니다. pip install pypdfium2 를 실행하세요.")
            return None
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["pdftoppm", "-r", str(dpi), "-png", "-singlefile", str(pdf_path), f"{tmp}/p"], check=True)
            img = Image.open(f"{tmp}/p.png")
            img.load()
    img = img.convert("L" if gray else "RGB")
    return img


def _jpeg(img, quality):
    from PIL import Image
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return Image.open(io.BytesIO(buf.getvalue()))


def _noise(img, rng, amount):
    """종이 얼룩 같은 옅은 잡음"""
    from PIL import Image, ImageChops
    n = Image.effect_noise(img.size, amount).point(lambda v: 255 - max(0, v - 128) // 3)
    if img.mode == "RGB":
        n = n.convert("RGB")
    return ImageChops.multiply(img, n)


def degrade(src, level, rng):
    """(그림, 기록할 값들) 을 돌려준다"""
    from PIL import Image, ImageFilter
    if level == "lowres":
        dpi = rng.choice([72, 75, 80, 90])
        img = render(src, 200, gray=True)
        if img is None:
            return None, {}
        w, h = img.size
        img = img.resize((int(w * dpi / 200), int(h * dpi / 200)), Image.BILINEAR)
        q = rng.randint(35, 55)
        return _jpeg(img, q), dict(dpi=dpi, jpeg_quality=q)
    dpi = 150
    img = render(src, dpi)
    if img is None:
        return None, {}
    if level == "skew":
        angle = round(rng.uniform(1.5, 4.0) * rng.choice([-1, 1]), 2)
        img = img.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=(255, 255, 255))
        img = _noise(img, rng, 18)
        q = rng.randint(60, 80)
        return _jpeg(img, q), dict(dpi=dpi, angle=angle, jpeg_quality=q)
    if level == "blur":
        radius = round(rng.uniform(1.2, 2.0), 2)
        img = img.filter(ImageFilter.GaussianBlur(radius))
        q = rng.randint(60, 80)
        return _jpeg(img, q), dict(dpi=dpi, blur_radius=radius, jpeg_quality=q)
    raise ValueError(level)


def make_variants(src, out_root, d, levels, rng):
    """
    원본 src 에서 levels 의 열화본을 만들고 목록을 돌려준다.
    파일 위치: pdf/<split>/<level>/<doc_id>_<level>.pdf   (original 은 pdf/<split>/original/<doc_id>.pdf)
    """
    out = [dict(file=d["file"], doc_id=d["doc_id"], split=d["split"], degrade="original", text_layer=True)]
    for level in levels:
        if level == "original":
            continue
        img, info = degrade(src, level, rng)
        if img is None:
            continue
        rel = f"pdf/{d['split']}/{level}/{d['doc_id']}_{level}.pdf"
        path = Path(out_root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path, "PDF", resolution=info.get("dpi", 150))
        out.append(dict(file=rel, doc_id=d["doc_id"], split=d["split"], degrade=level, text_layer=False, **info))
    return out
