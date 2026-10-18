"""[담당: 고도영] 모델 테스트 엔진. 모두 run(image_path, material) -> {머리글 필드..., "items": [...]} 를 돌려준다.

OCR 계열 (참고 사항 5번의 'OCR 단독' 방식): 글줄·단어 좌표를 coa_ai 의 Page 로 바꿔 텍스트 PDF 와 같은
표 복원·머리글·정규화 규칙에 넣는다.
  - RapidOcrEngine   : PaddleOCR(PP-OCR) 모델의 ONNX 판
  - PaddleOcrEngine  : PaddleOCR 원본 (PaddlePaddle)
  - EasyOcrEngine    : EasyOCR (PyTorch)
  - TesseractEngine  : Tesseract 5 (단어 단위 좌표)
  - SuryaEngine      : Surya 2. 블록 위치 + 블록 내용(HTML 표)을 받아 블록 안에 행·열을 배치해 Page 를 만든다
VLM 계열 ('VLM 단독' 방식): GGUF 모델을 llama-server 로 띄우고 이미지 + 지시문으로 JSON 을 받는다.
  - LlamaServerEngine : GLM-OCR, Qwen3.5-2B, LFM2.5-VL-450M, Gemma 4 E2B
  - PaddleOcrVlEngine : PaddleOCR-VL 은 지시문 대신 작업 이름('OCR:', 'Table Recognition:')만 받으므로 OCR 계열처럼 규칙에 넣는다
항목명 정규화는 모두 같은 coa_ai Normalizer 로 한다.
"""
from __future__ import annotations

import base64
import html
import json
import math
import os
import re
import socket
import statistics
import subprocess
import time
from pathlib import Path

import requests
from html.parser import HTMLParser

from coa_ai.classify import classify
from coa_ai.fields import extract_fields
from coa_ai.models import Box, Line, Page, Word
from coa_ai.normalize import Normalizer
from coa_ai.ocr import ocr_to_page, shrink_box, split_words
from coa_ai.table import parse_tables

MODELS = Path(os.environ.get("COA_BENCH_MODELS", Path.home() / ".cache" / "coa-bench" / "models"))
FIELDS = ("supplier", "lot_no", "test_date", "origin", "applied_standard")


def _items(rows: list[tuple[str, str | None, str | None, str | None]], material: str) -> list[dict]:
    norm = Normalizer(material)
    return [{"raw_name": n, "normalized_name": norm.map(n).name, "raw_value": v, "raw_spec": s, "unit": u}
            for n, v, s, u in rows if n]


def _rules(page: Page, material: str) -> dict:
    """OCR 로 만든 Page 를 텍스트 PDF 와 같은 머리글·표 복원·정규화 규칙에 넣는다."""
    pages = [page]
    fields = extract_fields(pages)
    rows = [(r.name, r.value, r.spec, r.unit) for r in parse_tables(pages)]
    out = {f: fields.get(f) for f in FIELDS}
    out["doc_type"] = classify(pages, has_lot=fields["lot_no"] is not None)
    out["items"] = _items(rows, material)
    return out


# ---------------------------------------------------------------------------
# OCR + 규칙
# ---------------------------------------------------------------------------
class RapidOcrEngine:
    name = "rapidocr"

    # PaddleOCR 3.7 OCR 파이프라인(paddlex/configs/pipelines/OCR.yaml)의 검출·인식 설정.
    # RapidOCR 기본값은 긴 변을 2000 으로 줄이고, 정규화가 다르고, 상자를 팽창(dilation)·unclip 1.6 으로 더 부풀린다.
    PADDLE_PARAMS = {
        "Global.max_side_len": 4000, "Global.text_score": 0.0,
        "Det.limit_side_len": 64, "Det.limit_type": "min",
        "Det.mean": [0.485, 0.456, 0.406], "Det.std": [0.229, 0.224, 0.225],
        "Det.thresh": 0.3, "Det.box_thresh": 0.6, "Det.unclip_ratio": 1.5, "Det.use_dilation": False,
    }

    def __init__(self, shrink: float = 0.1, use_cls: bool = False, model: str = "small", paddle_params: bool = False):
        """shrink: OCR 검출 상자를 글줄 높이의 이 비율만큼 안쪽으로 줄인다.
            PP-OCR 검출기는 상자를 글자보다 넓게 부풀려(unclip) 내므로, 그대로 쓰면 '번호' 열과 항목명 사이의
            빈 띠가 사라져 두 열이 붙는다 (가상 B). 0.1 은 이번 샘플을 보고 고른 값이다.
        use_cls: 글줄 방향(0°/180°) 분류. 켜 두면 바로 선 글줄을 뒤집어 '=<5 ppm' 을 'udd g>=' 로 읽는 일이 있다.
            CoA 는 바로 놓인 문서이고 작은 기울기는 ocr_to_page 가 되돌리므로 끈다.
        결과표에는 RapidOCR 기본 설정(shrink=0, use_cls=True) 결과도 함께 싣는다.
        model: PP-OCRv6 검출·인식 모델 크기. 기본(small)은 RapidOCR 기본값, medium 은 PaddleOCR 3.7 기본값과 같은 모델의 ONNX 판.
        paddle_params: 검출 전처리·후처리를 PaddleOCR 원본 설정(PADDLE_PARAMS)으로 맞춘다."""
        from rapidocr import ModelType, OCRVersion, RapidOCR
        size = {"small": ModelType.SMALL, "medium": ModelType.MEDIUM}[model]
        models = {} if model == "small" else {
            "Det.ocr_version": OCRVersion.PPOCRV6, "Det.model_type": size,
            "Rec.ocr_version": OCRVersion.PPOCRV6, "Rec.model_type": size}
        # 스레드 기본값(코어 수만큼)은 M4·Docker 에서 서로 밀려 2~3배 느려진다. 4개가 가장 빨랐다
        self.ocr = RapidOCR(params={"Global.use_cls": use_cls,
                                    "EngineConfig.onnxruntime.intra_op_num_threads": 4,
                                    "EngineConfig.onnxruntime.inter_op_num_threads": 1, **models,
                                    **(self.PADDLE_PARAMS if paddle_params else {})})
        self.shrink = shrink

    def run(self, image: Path, material: str, dpi: int) -> dict:
        res = self.ocr(str(image))
        boxes = [] if res.boxes is None else [[(float(x), float(y)) for x, y in b] for b in res.boxes]
        page = ocr_to_page([shrink_box(b, self.shrink) for b in boxes], list(res.txts or []), dpi)
        return _rules(page, material)


class ProductEngine:
    """제품 경로 그대로: coa_ai.extract(이미지 파일). 업로드와 같이 해상도는 모르는 것으로 보고(A4 폭으로 추정) 돈다.
    CoA 가 아니라고 판단하거나 글자를 못 찾으면 실패(오류)로 기록된다."""
    name = "coa_ai"

    def __init__(self):
        from coa_ai.ocr import load_engine
        load_engine()

    def run(self, image: Path, material: str, dpi: int) -> dict:
        from coa_ai import extract
        return extract(image, material_code=material).to_dict()


class PaddleOcrEngine:
    """PaddleOCR 3.x 원본. RapidOCR 과 같은 이유로 방향 분류·문서 펴기는 끄고 상자를 줄인다."""
    name = "paddleocr"

    def __init__(self, shrink: float = 0.1):
        from paddleocr import PaddleOCR
        # enable_mkldnn: x86 기본값(켜짐)은 PaddlePaddle 3.3.1 에서 oneDNN 오류가 난다 (맥 arm64 는 원래 안 씀)
        self.ocr = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False,
                             use_textline_orientation=False, cpu_threads=4, enable_mkldnn=False)
        self.shrink = shrink

    def run(self, image: Path, material: str, dpi: int) -> dict:
        res = self.ocr.predict(str(image))[0]
        boxes = [[(float(x), float(y)) for x, y in poly] for poly in res["rec_polys"]]
        page = ocr_to_page([shrink_box(b, self.shrink) for b in boxes], list(res["rec_texts"]), dpi)
        return _rules(page, material)


class EasyOcrEngine:
    """EasyOCR. 한국어와 중국어를 한 Reader 에 넣을 수 없어 PaddleOCR 기본값과 같은 중·영 조합을 쓴다."""
    name = "easyocr"

    def __init__(self):
        import easyocr
        import torch
        torch.set_num_threads(4)
        self.reader = easyocr.Reader(["ch_sim", "en"], gpu=False, verbose=False)

    def run(self, image: Path, material: str, dpi: int) -> dict:
        res = self.reader.readtext(str(image))
        boxes = [[(float(x), float(y)) for x, y in b] for b, _, _ in res]
        page = ocr_to_page(boxes, [t for _, t, _ in res], dpi)
        return _rules(page, material)


class TesseractEngine:
    """Tesseract 5. 단어 단위 상자(축 정렬)라 기울기는 같은 줄 단어들의 기울기로 따로 구한다."""
    name = "tesseract"

    def __init__(self, lang: str = "eng+chi_sim+kor"):
        import pytesseract
        self.tess = pytesseract
        self.lang = lang

    def run(self, image: Path, material: str, dpi: int) -> dict:
        d = self.tess.image_to_data(str(image), lang=self.lang, config="--psm 3",
                                    output_type=self.tess.Output.DICT)
        # 단어 상자는 글자 모양에 딱 맞아(소문자는 x높이만) 글자 크기가 작게 잡힌다. 줄 상자(level 4)의 높이로 맞춘다
        line_box = {(d["block_num"][i], d["par_num"][i], d["line_num"][i]): (d["top"][i], d["height"][i])
                    for i in range(len(d["level"])) if d["level"][i] == 4}
        words, lines = [], {}
        for i, text in enumerate(d["text"]):
            if not text.strip() or float(d["conf"][i]) < 0:
                continue
            x, w = d["left"][i], d["width"][i]
            y, h = line_box.get((d["block_num"][i], d["par_num"][i], d["line_num"][i]), (d["top"][i], d["height"][i]))
            words.append(([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], text))
            lines.setdefault((d["block_num"][i], d["par_num"][i], d["line_num"][i]), []).append((x + w / 2, y + h / 2))
        slopes = []
        for pts in lines.values():
            if len(pts) >= 3 and pts[-1][0] - pts[0][0] > 200:
                mx = statistics.mean(p[0] for p in pts)
                my = statistics.mean(p[1] for p in pts)
                den = sum((p[0] - mx) ** 2 for p in pts)
                slopes.append(sum((p[0] - mx) * (p[1] - my) for p in pts) / den)
        angle = math.atan(statistics.median(slopes)) if slopes else 0.0
        page = ocr_to_page([b for b, _ in words], [t for _, t in words], dpi, angle=angle)
        return _rules(page, material)


# ---------------------------------------------------------------------------
# 블록 내용(HTML 표·마크다운 표·글) → Page
# ---------------------------------------------------------------------------
class _RowParser(HTMLParser):
    """HTML 을 행 목록으로: 표 안은 칸 목록, 표 밖 글은 블록 태그·<br> 마다 한 줄."""
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table", "thead", "tbody"}

    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.span = 1
        self.text: list[str] = []

    def _flush_text(self):
        t = " ".join("".join(self.text).split())
        if t:
            self.rows.append([t])
        self.text = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._flush_text()
            self.row = []
        elif tag in ("td", "th"):
            self.cell = []
            self.span = int(dict(attrs).get("colspan") or 1)
        elif tag in self.BLOCK:
            if self.cell is not None:
                self.cell.append("\n")  # 칸 안의 <br/> ('序号<br/>No.') 은 칸 안의 줄바꿈
            else:
                self._flush_text()

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            parts = ("".join(self.cell)).split("\n")
            self.row.append("\n".join(" ".join(t.split()) for t in parts if t.strip()))
            self.row.extend([""] * (self.span - 1))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if any(self.row):
                self.rows.append(self.row)
            self.row = None
        elif tag in self.BLOCK and self.cell is None:
            self._flush_text()

    def handle_data(self, data):
        (self.cell if self.cell is not None else self.text).append(data)


def content_rows(content: str) -> list[list[str]]:
    """모델이 낸 블록 내용 → 행 목록. HTML 표, OTSL(<fcel>), 마크다운 표, 일반 글을 받는다."""
    content = content or ""
    if re.search(r"<(table|tr|td|div|p|br)\b", content, re.I):
        parser = _RowParser()
        parser.feed(content)
        parser.close()
        parser._flush_text()
        return parser.rows
    if re.search(r"<(fcel|ecel|nl)>", content):
        rows = []
        for line in re.split(r"<nl>", content):
            line = _unlatex(line.replace("\\n", " "))
            cells = [html.unescape(c).strip() for c in re.split(r"<(?:fcel|ecel|lcel|ucel|xcel)>", line)[1:]]
            if any(cells):
                rows.append(cells)
        return rows
    rows = []
    for line in _unlatex(content).splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("|") or " | " in line:
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue
            rows.append([re.sub(r"<[^>]+>", " ", c).strip() for c in cells])
        else:
            rows.append([re.sub(r"[#*`]+", "", re.sub(r"<[^>]+>", " ", line)).strip()])
    return rows


_LATEX = [(r"\\leq?", "≤"), (r"\\geq?", "≥"), (r"\\mu", "µ"), (r"\\pm", "±"), (r"\\times", "×"),
          (r"\\[,;! ]", " "), (r"\\\(|\\\)|\\\[|\\\]", ""), (r"\\(?:mathrm|text|rm)\s*", ""),
          (r"_\{?(\d+)\}?", lambda m: m.group(1).translate(str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉"))),
          (r"\^\{?([\d+\-−]+)\}?", lambda m: m.group(1).translate(str.maketrans("0123456789+-−", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻"))),
          (r"[{}]", "")]


def _unlatex(text: str) -> str:
    """OCR VLM 이 수식으로 낸 기호를 글자로: '\\( \\leq 0.40\\% \\)' → '≤ 0.40%', 'CO_3' → 'CO₃'."""
    if "\\" not in text and "_" not in text and "^" not in text:
        return text
    for pat, rep in _LATEX:
        text = re.sub(pat, rep, text)
    return text.replace("\\%", "%")


def _width(cell: str) -> int:
    return max((len(t) for t in cell.split("\n")), default=0)


def blocks_to_page(blocks: list[tuple[tuple[float, float, float, float], str]], dpi: int) -> Page:
    """(블록 상자 px, 내용) 목록 → Page. 블록 안에 행을 고르게 나눠 놓고, 표의 열은 글 길이에 비례한 너비로 놓는다.
    칸마다 글 길이만큼만 상자를 잡아 칸 사이에 빈 띠가 생기게 한다 (표 복원 규칙이 빈 띠로 열을 나눈다)."""
    boxes, texts = [], []
    for (x0, y0, x1, y1), content in blocks:
        rows = content_rows(content)
        if not rows:
            continue
        # 칸 안의 줄바꿈('序号\nNo.')은 실제 문서처럼 위아래 줄로 놓는다 (2단 머리글을 그대로 살린다)
        sub = [max(c.count("\n") + 1 for c in r) if r else 1 for r in rows]
        h = (y1 - y0) / sum(sub)
        # 열 너비는 열 수가 같은 연속 행(한 표)끼리 정한다. 한 칸짜리 긴 줄이 열 너비를 망치지 않게 한다
        groups, start = [], 0
        for i in range(1, len(rows) + 1):
            if i == len(rows) or len(rows[i]) != len(rows[start]):
                groups.append((start, i))
                start = i
        width_of = {}
        for a, b in groups:
            ncol = len(rows[a])
            # 내용이 한 칸뿐인 행(구분 제목, 칸을 합친 결론·비고)은 열 너비 계산에서 뺀다
            body = [r for r in rows[a:b] if sum(1 for c in r if c.strip()) >= 2] or rows[a:b]
            widths = [max(_width(r[c]) for r in body) + 3 for c in range(ncol)]
            for i in range(a, b):
                width_of[i] = widths
        # 글자 높이는 보통 크기(약 10pt), 줄 간격은 글자 높이의 1.8배를 넘지 않게 한다. 쪽 전체가 블록 하나이면
        # 행 높이가 커서 글자가 크게 잡히고(칸 사이 빈 띠가 글자보다 좁아져 칸이 붙는다), 행 사이가 벌어져 표가 끊긴다
        rh = min(0.7 * h, 0.14 * dpi)
        pitch = min(h, 1.8 * rh)
        line_no = 0
        for i, row in enumerate(rows):
            widths = width_of[i]
            total = sum(widths)
            x = x0
            for c, cell in enumerate(row):
                w = (x1 - x0) * widths[c] / total
                for k, part in enumerate(t for t in cell.split("\n") if t.strip()):
                    part = part.strip()
                    ry0 = y0 + (line_no + k) * pitch + (pitch - rh) / 2
                    tw = max(rh, min(w - 1.5 * rh, 0.55 * rh * len(part)))
                    boxes.append([(x, ry0), (x + tw, ry0), (x + tw, ry0 + rh), (x, ry0 + rh)])
                    texts.append(part)
                x += w
            line_no += sub[i]
    return ocr_to_page(boxes, texts, dpi, angle=0.0)


class SuryaEngine:
    """Surya 2: 레이아웃 + 블록별 OCR(표는 HTML). 쪽 하나에 VLM 호출 한 번.
    base_url 이 없으면 Surya 가 받아 둔 GGUF 로 llama-server 를 직접 띄운다 (Surya 권장 슬롯·문맥 크기·별칭 그대로).
    base_url 이 있으면(Docker 등) 그 서버에 붙는다. 서버는 --alias datalab-to/surya-ocr-2 로 떠 있어야 한다."""
    name = "surya"

    def __init__(self, base_url: str | None = None):
        if base_url:
            LlamaServerEngine("surya", base_url=base_url)  # 서버가 모델을 다 올릴 때까지 기다린다
            os.environ["SURYA_INFERENCE_URL"] = f"{base_url}/v1"
        else:
            model, mmproj = SERVERS["surya"]
            os.environ["SURYA_GGUF_LOCAL_MODEL_PATH"] = str(MODELS / model)
            os.environ["SURYA_GGUF_LOCAL_MMPROJ_PATH"] = str(MODELS / mmproj)
        from surya.inference import SuryaInferenceManager
        from surya.recognition import RecognitionPredictor
        self.manager = SuryaInferenceManager()
        self.rec = RecognitionPredictor(self.manager)

    def close(self) -> None:
        for name in ("shutdown", "close", "stop"):
            if callable(getattr(self.manager, name, None)):
                getattr(self.manager, name)()
                return

    def run(self, image: Path, material: str, dpi: int) -> dict:
        from PIL import Image
        pred = self.rec([Image.open(image).convert("RGB")])[0]
        blocks = [(tuple(b.bbox), b.html or "") for b in pred.blocks if not getattr(b, "skipped", False)]
        out = _rules(blocks_to_page(blocks, dpi), material)
        out["raw_text"] = json.dumps([[list(b), c] for b, c in blocks], ensure_ascii=False)[:20000]
        return out


# ---------------------------------------------------------------------------
# VLM (llama-server)
# ---------------------------------------------------------------------------
PROMPT = """This image is a Certificate of Analysis (CoA) for a chemical product.
Extract the header fields and EVERY row of the test results table.
Copy all text exactly as printed. Do not convert units or reformat numbers. Use null when a field is absent.
- supplier: the company that issued the certificate
- lot_no: lot or batch number
- test_date: date of test/analysis as YYYY-MM-DD (null if no test date is printed)
- origin: country of origin
- applied_standard: the product standard or grade the results conform to
- items: one object per test row: name (test item), method (test method column, if any), value (result), spec (specification or limits), unit (unit column)
Return only JSON."""

SCHEMA = {
    "type": "object",
    "properties": {
        **{f: {"type": ["string", "null"]} for f in FIELDS},
        "items": {"type": "array", "items": {
            "type": "object",
            "properties": {k: {"type": ["string", "null"]} for k in ("name", "method", "value", "spec", "unit")},
            "required": ["name", "method", "value", "spec", "unit"],
        }},
    },
    "required": [*FIELDS, "items"],
}

# GLM-OCR 은 모델 카드상 'Text/Table Recognition:' 과 이 정보 추출 형식(JSON 틀)만 지원한다
GLM_PROMPT = "请按下列JSON格式输出图中信息:\n" + json.dumps(
    {**{f: "" for f in FIELDS}, "items": [{"name": "", "method": "", "value": "", "spec": "", "unit": ""}]},
    ensure_ascii=False, indent=4)

VLMS = {
    "glm-ocr": ("GLM-OCR-Q8_0.gguf", "mmproj-GLM-OCR-Q8_0.gguf"),
    "qwen3.5-2b": ("Qwen3.5-2B-Q4_K_M.gguf", "mmproj-F16.gguf"),
    "lfm2.5-vl-450m": ("LFM2.5-VL-450M-Q8_0.gguf", "mmproj-LFM2.5-VL-450m-F16.gguf"),
    "gemma4-e2b": ("gemma-4-E2B_q4_0-it.gguf", "gemma-4-E2B-it-mmproj.gguf"),
    "paddleocr-vl": ("PaddleOCR-VL-1.6-GGUF.gguf", "PaddleOCR-VL-1.6-GGUF-mmproj.gguf"),
}
# llama-server 로 띄우는 모델 전부 (Surya 는 OCR 계열이지만 모델은 같은 방식으로 띄운다)
SERVERS = {**VLMS, "surya": ("surya-2.gguf", "surya-2-mmproj.gguf")}


class LlamaServerEngine:
    """llama-server 를 직접 띄우거나(base_url 없음), 이미 떠 있는 서버(Docker 등)에 붙는다."""

    def __init__(self, name: str, *, base_url: str | None = None, port: int = 8091, use_schema: bool = True,
                 max_tokens: int = 4096):
        self.name = name
        self.use_schema = use_schema
        self.max_tokens = max_tokens
        self.proc = None
        self.base = base_url or f"http://127.0.0.1:{port}"
        if base_url is None:
            model, mmproj = SERVERS[name]
            # 포트에 남은 서버(예: 멈춘 실행의 고아 llama-server)가 있으면 새 서버는 bind 에 실패하고
            # /health 는 남은 서버가 받아 다른 모델로 돌게 된다.
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    raise RuntimeError(f"포트 {port} 에 이미 다른 서버가 떠 있음 ({name}). 먼저 종료할 것")
            self.proc = subprocess.Popen(
                ["llama-server", "-m", str(MODELS / model), "--mmproj", str(MODELS / mmproj),
                 "--port", str(port), "-c", "16384", "-ngl", "99", "--temp", "0", "--no-webui"],
                stdout=subprocess.DEVNULL, stderr=open(Path(os.environ.get("TMPDIR", "/tmp")) / f"llama-{name}.log", "w"))
        self._wait()

    @property
    def pid(self) -> int | None:
        return self.proc.pid if self.proc else None

    def _wait(self, timeout: float = 300) -> None:
        end = time.time() + timeout
        while time.time() < end:
            try:
                if requests.get(f"{self.base}/health", timeout=2).status_code == 200:
                    return
            except requests.RequestException:
                pass
            if self.proc and self.proc.poll() is not None:
                raise RuntimeError(f"llama-server 종료됨 ({self.name})")
            time.sleep(1)
        raise TimeoutError(f"llama-server 준비 안 됨 ({self.name})")

    def close(self) -> None:
        if self.proc:
            self.proc.terminate()
            self.proc.wait(timeout=30)

    def run(self, image: Path, material: str, dpi: int) -> dict:
        b64 = base64.b64encode(image.read_bytes()).decode()
        body = {
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                {"type": "text", "text": GLM_PROMPT if self.name == "glm-ocr" else PROMPT},
            ]}],
            "temperature": 0,
            "max_tokens": self.max_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if self.use_schema:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "coa", "schema": SCHEMA}}
        r = requests.post(f"{self.base}/v1/chat/completions", json=body, timeout=1800)
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"] or ""
        data = parse_json(text)
        out = {f: data.get(f) for f in FIELDS}
        rows = [(i.get("name"), i.get("value"), i.get("spec"), i.get("unit"))
                for i in data.get("items") or [] if isinstance(i, dict)]
        out["items"] = _items(rows, material)
        out["raw_text"] = text[:20000]
        return out


class PaddleOcrVlEngine(LlamaServerEngine):
    """PaddleOCR-VL-1.6: 작업 이름 하나로 쪽 전체를 읽는다.
    - 'Table Recognition:' (기본): 쪽 전체를 OTSL 표(<fcel>, <ecel>, <nl>)로 낸다. 빈 칸이 살아 있어 열이 밀리지 않는다.
    - 'OCR:' : 글 + 'a | b' 표 줄. 빈 칸을 빼먹어 열이 밀리고(가상 D), 표를 한 칸씩 줄로 풀어 내기도 한다(가상 B).
    'Spotting:' 은 위치를 주지 않고 4배 느려 쓰지 않는다. 공식 파이프라인(레이아웃 검출 후 요소별 인식)은
    맥에서 Docker 가 필요해 쓰지 않았다."""

    def __init__(self, *, base_url: str | None = None, port: int = 8093, task: str = "Table Recognition:"):
        super().__init__("paddleocr-vl", base_url=base_url, port=port, use_schema=False)
        self.task = task

    def run(self, image: Path, material: str, dpi: int) -> dict:
        from PIL import Image
        b64 = base64.b64encode(image.read_bytes()).decode()
        body = {"messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            {"type": "text", "text": self.task}]}], "temperature": 0, "max_tokens": self.max_tokens}
        r = requests.post(f"{self.base}/v1/chat/completions", json=body, timeout=1800)
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"] or ""
        w, h = Image.open(image).size
        out = _rules(blocks_to_page([((0, 0, w, h), text)], dpi), material)
        out["raw_text"] = text[:20000]
        return out


def parse_json(text: str) -> dict:
    """모델 출력에서 JSON 객체를 꺼낸다 (```json 감싸기, 앞뒤 설명 허용)."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return {}
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}
