#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
가상 CoA(Certificate of Analysis) 생성기
=========================================
CoA_Form.docx(Form-320) 양식의 빈칸(베이지색 칸)을 채워서, 내용이 조금씩 다른
가상 CoA를 원하는 개수만큼 만든다.

  - 고정 필드 : COMPANY ADDRESS, CONTACTS, File Location, LABORATORY MANAGER(서명란)
                -> 모든 CoA에 같은 내용 (아래 FIXED 에서 수정)
  - 가변 필드 : Issue date, Certificate Number, Supplier, Product Code/Name,
                Manufacturer's Batch No, Sydco's Lab. Batch No,
                Date of Manufacture, Expiry Date, DATE OF RELEASE, Date Printed
  - Results   : 양식의 Specifications 칸(예: "Less than 20 ppm")을 읽어 규격 한계를 알아낸 뒤
                시험 항목마다 현실적인 값을 넣는다. 일부 CoA에는 규격 이탈 값을 일부러 섞는다.
  - 정답 기록 : 채운 값과 합/불 결과를 ground_truth.json / ground_truth.csv 로 저장

칸 위치를 외워서 채우지 않고 라벨 글자('Certificate Number', 'Results' 등)를 찾아서 채운다.
양식의 칸은 높이가 고정돼 있어서 글자가 길면 잘리므로, 칸 너비에 맞게 글자 크기를 자동으로 줄인다.

사용법
------
    pip install python-docx
    python generate_coa.py --template CoA_Form.docx --count 100 --out output
    python generate_coa.py --template CoA_Form.docx --count 100 --out output --pdf

옵션
    --count N        만들 CoA 개수 (기본 20)
    --seed S         난수 시드. 같은 시드면 항상 같은 결과 (기본 42)
    --fail-rate R    규격 이탈 항목이 들어간 CoA 비율 0~1
                     (생략하면 공급사별 fail_rate 사용, 평균 약 20%. 0이면 전부 합격)
    --start/--end    제조일 범위 YYYY-MM-DD (기본 2025-09-01 ~ 2026-08-31)
    --pdf            PDF도 생성 (LibreOffice 또는 MS Word + `pip install docx2pdf` 필요)

결과물
    output/docx/COA_0001.docx ...   채워진 CoA
    output/pdf/COA_0001.pdf ...     (--pdf 사용 시)
    output/ground_truth.json        문서별 전체 정답 (필드 + 항목별 결과 + 합/불)
    output/ground_truth.csv         문서 x 시험항목 한 줄씩 (엑셀에서 바로 열림)
"""

import argparse
import calendar
import copy
import csv
import io
import json
import random
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

try:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
except ImportError:
    sys.exit("python-docx 가 필요합니다:  pip install python-docx")


# =============================================================================
# 1. 설정 — 대부분 여기만 고치면 된다 (회사·사람·주소는 모두 가상)
# =============================================================================

# ── 1-1. 고정 필드: 모든 CoA에 똑같이 들어가는 내용 ─────────────────────────
FIXED = {
    "company_address": [
        "Sydco Co., Ltd. - QC Laboratory",
        "12, Gasang-ro 3beon-gil, Danwon-gu, Ansan-si,",
        "Gyeonggi-do 15600, Republic of Korea",
    ],
    "contacts": [
        "Tel: +82-31-555-0142",
        "Fax: +82-31-555-0143",
        "E-mail: qc.lab@sydco.example.com",
    ],
    "file_location": r"\\QMS\QC\CoA\Form-320",
    "lab_manager": "Dr. Seo-yeon Park",          # 서명란(Signature)에 들어가는 이름
}

# ── 1-2. 공급사(협력사) 목록 ──────────────────────────────────────────────────
#   batch_format     : 제조사 배치번호 형식 ({yy}{mm}{dd}=제조일, {seq}=일련번호)
#   shelf_life_months: 유효기한 = 제조일 + N개월
#   fail_rate        : 이 공급사 CoA 중 규격 이탈 항목이 들어갈 비율
#   impurity_level   : 불순물 수준 배율 (1.0 = 보통, 클수록 한계에 가까운 값이 자주 나옴)
#   weight           : 전체 CoA 중 이 공급사가 나오는 빈도 가중치
SUPPLIERS = [
    dict(name="Arvelle Chemical Co., Ltd.", product_code="AC-SBC-100",
         product_name="Sodium Bicarbonate BP", batch_format="AC{yy}{mm}{seq:03d}",
         shelf_life_months=36, fail_rate=0.10, impurity_level=0.85, weight=3),
    dict(name="Teramis Fine Chemicals Inc.", product_code="TFC-2231",
         product_name="Sodium Hydrogen Carbonate", batch_format="T{yy}{mm}{dd}{seq:02d}",
         shelf_life_months=24, fail_rate=0.15, impurity_level=1.00, weight=3),
    dict(name="Selmora Materials Co., Ltd.", product_code="SM-NAB-25",
         product_name="Sodium Bicarbonate (BP)", batch_format="SM{yy}-{seq:04d}",
         shelf_life_months=36, fail_rate=0.25, impurity_level=1.10, weight=2),
    dict(name="Nobrix Industrial Co., Ltd.", product_code="NBX-SB01",
         product_name="Sodium Bicarbonate, BP", batch_format="NB{yy}{mm}-{seq:03d}",
         shelf_life_months=24, fail_rate=0.35, impurity_level=1.25, weight=2),
]

# ── 1-3. 번호 · 날짜 형식 ─────────────────────────────────────────────────────
CERT_NO_FORMAT = "COA-{year}-{seq:04d}"      # Certificate Number
LAB_BATCH_FORMAT = "SL{yy}-{seq:04d}"        # Sydco's Lab. Batch No
DATE_FORMAT = "{d:02d}-{mon}-{y}"            # 14-Mar-2026   (예: "{y}-{m:02d}-{d:02d}" -> 2026-03-14)
RELEASE_AFTER_MFG_DAYS = (3, 12)             # 제조일 -> DATE OF RELEASE(= Issue date) 까지 일수
PRINT_AFTER_RELEASE_DAYS = (0, 3)            # DATE OF RELEASE -> Date Printed 까지 일수

# ── 1-4. 시험 항목별 결과값 규칙 ──────────────────────────────────────────────
# 규격 한계(예: "Less than 20 ppm" -> 20)는 양식의 Specifications 칸에서 자동으로 읽는다.
# 여기에는 '합격 로트에서 흔히 나오는 값의 범위'와 표기 방식만 적는다.
#   typical  : 정상값 범위 (하한, 상한)      decimals : 소수 자릿수
#   fmt      : 결과 칸 표기 ({v} 자리에 숫자) impurity : False 면 공급사 impurity_level 무시
NUMERIC_PROFILES = {
    "Carbonates":   dict(typical=(8.0, 8.4), decimals=1, fmt="pH {v}", impurity=False),
    "Ammonium":     dict(typical=(2.0, 12.0), decimals=1, fmt="{v} ppm"),
    "Calcium":      dict(typical=(15, 70), decimals=0, fmt="{v} ppm"),
    "Arsenic":      dict(typical=(0.10, 0.90), decimals=2, fmt="{v} ppm"),
    "Heavy Metals": dict(typical=(0.2, 1.2), decimals=1, fmt="{v} ppm"),
    "Iron":         dict(typical=(2.0, 11.0), decimals=1, fmt="{v} ppm"),
    "Sulphates":    dict(typical=(20, 95), decimals=0, fmt="{v} ppm"),
    "Chlorides":    dict(typical=(10, 85), decimals=0, fmt="{v} ppm"),
}

# 정성 항목(규격 'Conforms')의 합격 표기. 가끔 'Complies'로 쓰는 경우를 섞는다.
QUALITATIVE_PASS_TEXTS = ["Conforms", "Conforms", "Conforms", "Conforms", "Complies"]
# 정성 항목 중 불합격이 나올 수 있는 항목과 그때의 표기
QUALITATIVE_FAIL_TEXTS = {
    "Appearance": "Does not conform (yellowish lumps)",
    "Appearance of solution": "Does not conform (opalescent)",
    "Micro Status": "Does not conform (TAMC above limit)",
}

NEAR_LIMIT_RATE = 0.03                  # 합격이지만 한계에 바짝 붙은 값(한계의 85~97%)이 나올 확률(항목별)
FAIL_ITEM_COUNT_WEIGHTS = {1: 7, 2: 3}  # 이탈 CoA 한 장에 들어가는 이탈 항목 수의 비율 (1개:2개 = 7:3)
QUALITATIVE_FAIL_WEIGHT = 0.3           # 이탈 항목을 고를 때 정성 항목의 가중치 (수치 항목 = 1)

# ── 1-5. 칸별 글자 크기(pt). 칸보다 글자가 길면 자동으로 줄어든다(최소 6pt) ──────
FONT_PT = dict(info=9.5, result=9.5, issue_date=9, release_date=9.5, signature=11,
               address=9, contacts=9, file_location=8, date_printed=8)


# =============================================================================
# 2. 가상 데이터 만들기
# =============================================================================

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def fmt_date(d):
    return DATE_FORMAT.format(d=d.day, m=d.month, y=d.year, mon=MONTHS[d.month - 1])


def add_months(d, months):
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def key(text):
    """라벨 비교용: 소문자 + 영문/숫자만 남김 ("Manufacturer’s Batch No" -> "manufacturersbatchno")"""
    return re.sub(r"[^0-9a-z]", "", text.lower())


_QUAL_SPEC = re.compile(r"^\s*(conforms?|complies|pass(es)?|positive)\s*$", re.I)
_MAX_SPEC = re.compile(
    r"(less\s+than|not\s+more\s+than|nmt|max(?:imum)?\.?|≤|<=|<)\s*(ph)?\s*"
    r"(\d+(?:\.\d+)?)\s*([a-zµμ%/]+)?", re.I)


def parse_spec(spec_text):
    """양식의 규격 문구 해석. 'Conforms' -> 정성, 'Less than 20 ppm' -> 상한 20 ppm"""
    if _QUAL_SPEC.match(spec_text):
        return {"type": "qualitative"}
    m = _MAX_SPEC.search(spec_text)
    if m:
        word = re.sub(r"\s+", " ", m.group(1).lower())
        unit = m.group(4) or ""
        is_ph = bool(m.group(2)) or unit.lower() == "ph"
        return {"type": "max",
                "op": "<" if word in ("less than", "<") else "<=",
                "limit": float(m.group(3)),
                "unit": "pH" if is_ph else unit}
    return {"type": "unknown"}


def build_test_defs(form_rows):
    """양식에서 읽은 (시험항목, 규격) 목록 + NUMERIC_PROFILES -> 값 생성 규칙"""
    profiles = {key(k): v for k, v in NUMERIC_PROFILES.items()}
    defs = []
    for name, spec_text in form_rows:
        spec = parse_spec(spec_text)
        d = {"name": name, "spec_text": spec_text, **spec}
        if spec["type"] == "unknown":
            print(f"[경고] '{name}' 규격 '{spec_text}'을(를) 해석하지 못해 정성 항목(Conforms)으로 처리합니다.")
            d["type"] = "qualitative"
        if d["type"] == "max":
            lim, is_ph = d["limit"], d["unit"] == "pH"
            prof = profiles.get(key(name))
            if prof is None:  # 규칙이 없는 새 항목 -> 한계 기준으로 무난한 기본값
                prof = dict(typical=(lim - 0.6, lim - 0.2) if is_ph else (0.1 * lim, 0.6 * lim),
                            decimals=1 if (is_ph or lim < 10) else 0,
                            fmt="pH {v}" if is_ph else ("{v} " + d["unit"]).strip(),
                            impurity=not is_ph)
            lo, hi = prof["typical"]
            hi = min(hi, lim - 0.1 if is_ph else 0.8 * lim)   # 양식 규격이 바뀌어도 정상값은 한계 안쪽
            d.update(typical=(min(lo, hi), hi), decimals=prof["decimals"],
                     fmt=prof["fmt"], impurity=prof.get("impurity", True))
        defs.append(d)
    return defs


def gen_numeric(t, case, level, rng):
    """case: normal(정상) / near_limit(한계 근접 합격) / out_of_spec(규격 이탈)"""
    lim, dec, is_ph = t["limit"], t["decimals"], t["unit"] == "pH"
    step = 10 ** -dec
    if case == "normal":
        lo, hi = t["typical"]
        v = rng.triangular(lo, hi, lo + 0.4 * (hi - lo))
        if t["impurity"]:
            v *= level
        v = min(v, lim - 0.1 if is_ph else 0.8 * lim)
    elif case == "near_limit":
        v = lim - rng.uniform(0.05, 0.2) if is_ph else lim * rng.uniform(0.85, 0.97)
    else:
        v = lim + rng.uniform(0.1, 0.5) if is_ph else lim * rng.uniform(1.05, 1.6)
    v = round(v, dec)
    # 반올림 때문에 합/불이 뒤바뀌거나 한계값과 딱 같아지지 않도록 보정
    if case == "out_of_spec" and v <= lim:
        v = round(lim + step, dec)
    if case != "out_of_spec" and v >= lim:
        v = round(lim - step, dec)
    return max(v, step)


def judge(t, value, text):
    """규격 대비 합/불 (생성 의도와 별개로 다시 계산해서 기록)"""
    if t["type"] == "max":
        ok = value < t["limit"] if t["op"] == "<" else value <= t["limit"]
    else:
        ok = bool(re.match(r"(conforms?|complies|pass|positive)\b", text, re.I))
    return "PASS" if ok else "FAIL"


def make_results(test_defs, supplier, fail_rate, rng):
    qual_fail = {key(k): v for k, v in QUALITATIVE_FAIL_TEXTS.items()}
    level = supplier.get("impurity_level", 1.0) * rng.uniform(0.85, 1.15)   # 로트마다 조금씩 다름

    # (1) 이 CoA에서 규격을 벗어나게 만들 항목 고르기
    fail_names = set()
    if rng.random() < fail_rate:
        pool = [t for t in test_defs if t["type"] == "max" or key(t["name"]) in qual_fail]
        weights = [1.0 if t["type"] == "max" else QUALITATIVE_FAIL_WEIGHT for t in pool]
        k = rng.choices(list(FAIL_ITEM_COUNT_WEIGHTS), weights=list(FAIL_ITEM_COUNT_WEIGHTS.values()))[0]
        while pool and len(fail_names) < min(k, len(pool)):
            fail_names.add(rng.choices(pool, weights=weights)[0]["name"])

    # (2) 항목별 결과 만들기
    results = []
    for t in test_defs:
        failing = t["name"] in fail_names
        if t["type"] == "max":
            case = "out_of_spec" if failing else ("near_limit" if rng.random() < NEAR_LIMIT_RATE else "normal")
            value = gen_numeric(t, case, level, rng)
            text = t["fmt"].format(v=f"{value:.{t['decimals']}f}")
        else:
            case = "out_of_spec" if failing else "normal"
            value = None
            text = qual_fail.get(key(t["name"]), "Does not conform") if failing else rng.choice(QUALITATIVE_PASS_TEXTS)
        results.append({
            "test": t["name"], "result_text": text, "value": value,
            "unit": t.get("unit", ""), "spec_text": t["spec_text"],
            "spec_type": t["type"], "spec_limit": t.get("limit"),
            "case": case, "judgement": judge(t, value, text),
        })
    return results


def make_records(count, test_defs, rng, start, end, fail_rate=None):
    """CoA 한 장 = 레코드 하나. 번호는 출하일(DATE OF RELEASE) 순서대로 매긴다."""
    span = (end - start).days
    recs = []
    for _ in range(count):
        sup = rng.choices(SUPPLIERS, weights=[s.get("weight", 1) for s in SUPPLIERS])[0]
        mfg = start + timedelta(days=rng.randint(0, span))
        release = mfg + timedelta(days=rng.randint(*RELEASE_AFTER_MFG_DAYS))
        recs.append(dict(sup=sup, mfg=mfg, release=release,
                         printed=release + timedelta(days=rng.randint(*PRINT_AFTER_RELEASE_DAYS)),
                         expiry=add_months(mfg, sup["shelf_life_months"])))
    recs.sort(key=lambda r: (r["release"], r["mfg"]))

    cert_seq, lab_seq, lot_seq = {}, {}, {}

    def bump(counter, k, start_range, step_range):
        # 다른 원료의 CoA도 함께 발행되므로 번호가 1씩이 아니라 띄엄띄엄 증가
        counter[k] = counter[k] + rng.randint(*step_range) if k in counter else rng.randint(*start_range)
        return counter[k]

    for i, r in enumerate(recs, 1):
        sup, mfg, rel = r["sup"], r["mfg"], r["release"]
        r["doc_id"] = f"COA_{i:04d}"
        r["fields"] = {
            "issue_date": fmt_date(rel),
            "certificate_number": CERT_NO_FORMAT.format(
                year=rel.year, yy=f"{rel.year % 100:02d}", seq=bump(cert_seq, rel.year, (10, 90), (1, 6))),
            "supplier": sup["name"],
            "product_code": sup["product_code"],
            "product_name": sup["product_name"],
            "manufacturer_batch_no": sup["batch_format"].format(
                yy=f"{mfg.year % 100:02d}", mm=f"{mfg.month:02d}", dd=f"{mfg.day:02d}",
                seq=bump(lot_seq, (sup["name"], mfg.year), (1, 20), (1, 3))),
            "lab_batch_no": LAB_BATCH_FORMAT.format(
                year=rel.year, yy=f"{rel.year % 100:02d}", seq=bump(lab_seq, rel.year, (100, 400), (1, 4))),
            "date_of_manufacture": fmt_date(mfg),
            "expiry_date": fmt_date(r["expiry"]),
            "date_of_release": fmt_date(rel),
            "date_printed": fmt_date(r["printed"]),
        }
        r["dates_iso"] = {"date_of_manufacture": mfg.isoformat(), "expiry_date": r["expiry"].isoformat(),
                          "date_of_release": rel.isoformat(), "date_printed": r["printed"].isoformat()}
        rate = sup["fail_rate"] if fail_rate is None else fail_rate
        r["results"] = make_results(test_defs, sup, rate, rng)
    return recs


# =============================================================================
# 3. 양식(docx) 채우기
# =============================================================================
# 이 양식은 모든 요소가 페이지에 고정 배치된 표로 되어 있고, 입력칸은 베이지색(F8F1DF) 칸이다.
#   - 기본 정보 표 / Results 표 : 라벨 오른쪽 칸
#   - Issue date, File Location, Date Printed : 라벨 다음에 오는 작은 상자
#   - DATE OF RELEASE, LABORATORY MANAGER     : 점선 위의 상자 (서명란은 'Signature' 상자)
#   - COMPANY ADDRESS, CONTACTS                : 라벨 아래 베이지색 영역

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
DASH_LINE = re.compile(r"^\s*[-_–—.]{5,}\s*$")

# Arial(Helvetica) 글자 폭 (1000 단위, 문자 코드 32~126) — 칸에 글자가 들어가는지 계산할 때 사용
_ARIAL_W = [int(x) for x in (
    "278 278 355 556 556 889 667 191 333 333 389 584 278 333 278 278 "
    "556 556 556 556 556 556 556 556 556 556 278 278 584 584 584 556 "
    "1015 667 667 722 722 667 611 778 722 278 500 667 556 833 722 778 "
    "667 778 722 667 611 722 667 944 667 667 611 278 278 278 469 556 "
    "333 556 556 500 556 556 278 556 556 222 222 500 222 833 556 556 "
    "556 556 333 500 278 556 500 722 500 500 500 334 260 334 584").split()]


def text_width_twips(text, pt):
    units = sum(_ARIAL_W[ord(c) - 32] if 32 <= ord(c) <= 126 else 600 for c in text)
    return units / 1000 * pt * 20


def fit_pt(text, pt, width_twips, min_pt=6.0):
    """글자가 칸 너비를 넘으면 0.5pt씩 줄인다 (칸 높이가 고정이라 줄바꿈되면 잘리기 때문)"""
    if not width_twips:
        return pt
    while pt > min_pt and text_width_twips(text, pt) > width_twips * 0.95:
        pt -= 0.5
    return pt


def text_of(el):
    return "".join(t.text or "" for t in el.iter(W + "t"))


def ancestor(el, tag):
    el = el.getparent()
    while el is not None and el.tag != W + tag:
        el = el.getparent()
    return el


def own_paragraphs(tc):
    """칸 안의 문단 (중첩된 표 안의 문단은 제외)"""
    return [p for p in tc.iter(W + "p") if ancestor(p, "tc") is tc]


def cell_text(tc):
    return "".join(text_of(p) for p in own_paragraphs(tc))


def cell_text_width(tc):
    """칸에서 글자가 들어갈 수 있는 너비(twips) = 칸 너비 - 좌우 여백"""
    tcW = tc.find(f"{W}tcPr/{W}tcW")
    if tcW is None or tcW.get(W + "type", "dxa") != "dxa":
        return None
    width = int(tcW.get(W + "w"))
    tbl = ancestor(tc, "tbl")
    for side in ("left", "right"):
        mar = tc.find(f"{W}tcPr/{W}tcMar/{W}{side}")
        if mar is None and tbl is not None:
            mar = tbl.find(f"{W}tblPr/{W}tblCellMar/{W}{side}")
        width -= int(mar.get(W + "w")) if mar is not None else 108
    return width


def make_run(text, pt, italic=False):
    r = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    if italic:
        rpr.append(OxmlElement("w:i"))
    for tag in ("w:sz", "w:szCs"):
        el = OxmlElement(tag)
        el.set(qn("w:val"), str(int(round(pt * 2))))
        rpr.append(el)
    r.append(rpr)
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = text
    r.append(t)
    return r


def set_para(p, align=None, line=None, before=None, after=None):
    ppr = p.get_or_add_pPr()
    if line is not None or before is not None or after is not None:
        sp = ppr.get_or_add_spacing()
        if line is not None:
            sp.set(qn("w:line"), str(int(line)))
            sp.set(qn("w:lineRule"), "exact")
        if before is not None:
            sp.set(qn("w:before"), str(int(before)))
        if after is not None:
            sp.set(qn("w:after"), str(int(after)))
    if align == "center":
        ppr.jc_val = WD_ALIGN_PARAGRAPH.CENTER


def write_cell(tc, text, pt, align=None, italic=False):
    """칸의 첫 문단 내용을 text 로 바꾼다 (문단 서식은 양식 그대로 유지)"""
    paras = own_paragraphs(tc)
    if paras:
        p = paras[0]
    else:
        p = OxmlElement("w:p")
        tc.append(p)
    for child in list(p):
        if child.tag != W + "pPr":
            p.remove(child)
    p.append(make_run(text, fit_pt(text, pt, cell_text_width(tc)), italic))
    set_para(p, align=align)


def find_label_paragraphs(body, pattern):
    """라벨 문단 찾기. pattern 은 key() 로 정규화한 글자에 대한 정규식"""
    rx = re.compile(pattern)
    exact = [p for p in body.iter(W + "p") if rx.fullmatch(key(text_of(p)))]
    return exact or [p for p in body.iter(W + "p") if rx.search(key(text_of(p)))]


def fill_right_cell(body, pattern, text, pt):
    """[라벨 | 값] 형태 표: 라벨 칸 바로 오른쪽 칸에 쓴다"""
    rx, n = re.compile(pattern), 0
    for tc in list(body.iter(W + "tc")):
        if rx.fullmatch(key(cell_text(tc))):
            nxt = tc.getnext()
            while nxt is not None and nxt.tag != W + "tc":
                nxt = nxt.getnext()
            if nxt is not None:
                write_cell(nxt, text, pt)
                n += 1
    return n


def _is_box(tbl):
    cells = list(tbl.iter(W + "tc"))
    if len(cells) != 1:
        return False
    shd = cells[0].find(f"{W}tcPr/{W}shd")
    shaded = shd is not None and (shd.get(W + "fill") or "auto").upper() not in ("AUTO", "FFFFFF")
    return shaded or not cell_text(cells[0]).strip()


def find_box(label_p, direction):
    """라벨이 든 표의 앞(prev)/뒤(next)에 있는 입력 상자(칸 1개짜리 표)를 찾는다. 점선 표는 건너뛴다."""
    tbl = ancestor(label_p, "tbl")
    if tbl is None:
        return None
    el = tbl.getnext() if direction == "next" else tbl.getprevious()
    for _ in range(4):
        if el is None:
            return None
        if el.tag == W + "tbl":
            if DASH_LINE.match(text_of(el)):
                pass
            elif _is_box(el):
                return next(el.iter(W + "tc"))
            else:
                return None
        elif el.tag == W + "p" and text_of(el).strip():
            return None
        el = el.getnext() if direction == "next" else el.getprevious()
    return None


def fill_box(body, pattern, direction, text, pt, italic=False):
    n = 0
    for p in find_label_paragraphs(body, pattern):
        box = find_box(p, direction)
        if box is not None:
            write_cell(box, text, pt, align="center", italic=italic)
            n += 1
    return n


def sign_box(body, name, pt):
    """LABORATORY MANAGER 점선 위 'Signature' 상자에 이름을 서명처럼 넣는다 ('Signature' 안내문구는 유지)"""
    n = 0
    for p in find_label_paragraphs(body, r"laboratorymanager"):
        box = find_box(p, "prev")
        if box is None:
            continue
        paras = own_paragraphs(box)
        hint = next((q for q in paras if key(text_of(q)) == "signature"), None)
        if hint is None:
            write_cell(box, name, pt, align="center", italic=True)
        else:
            sig = OxmlElement("w:p")
            hint.addprevious(sig)
            set_para(sig, align="center", line=round(pt * 20 * 1.35), before=0, after=0)
            sig.append(make_run(name, fit_pt(name, pt, cell_text_width(box)), italic=True))
            set_para(hint, before=40)
        n += 1
    return n


def fill_block_below(body, pattern, lines, pt):
    """COMPANY ADDRESS / CONTACTS: 라벨 아래 베이지색 영역(높이 고정 문단 1개)을
    같은 색·같은 전체 높이를 유지한 여러 줄로 바꿔서 채운다."""
    n = 0
    for label in find_label_paragraphs(body, pattern):
        block = label.getnext()
        while block is not None and block.tag != W + "p":
            block = block.getnext()
        tc = ancestor(label, "tc")
        width = cell_text_width(tc) if tc is not None else None
        if block is None or block.find(f"{W}pPr/{W}shd") is None:   # 양식이 다르면 라벨 아래에 줄만 추가
            anchor = label
            for line in lines:
                p = OxmlElement("w:p")
                p.append(make_run(line, fit_pt(line, pt, width)))
                anchor.addnext(p)
                anchor = p
            n += 1
            continue
        sp = block.find(f"{W}pPr/{W}spacing")
        total = int(sp.get(W + "line")) if sp is not None and sp.get(W + "line") else 1320
        pad = 80
        line_h = min(round(pt * 20 * 1.3), (total - 2 * pad) // max(len(lines), 1))
        heights = [pad] + [line_h] * len(lines) + [total - pad - line_h * len(lines)]
        texts = [None] + list(lines) + [None]
        ppr = block.find(W + "pPr")
        for h, text in zip(heights, texts):
            if h <= 0:
                continue
            p = OxmlElement("w:p")
            p.append(copy.deepcopy(ppr))           # 베이지색 음영 유지
            set_para(p, line=h, before=0, after=0)
            if text:
                p.append(make_run(text, fit_pt(text, pt, width)))
            block.addprevious(p)
        block.getparent().remove(block)
        n += 1
    return n


def iter_result_rows(body):
    """Tests / Results / Specifications 표에서 (시험항목, 규격, 결과칸) 을 차례로 돌려준다"""
    for tbl in body.iter(W + "tbl"):
        rows = tbl.findall(W + "tr")
        for h, tr in enumerate(rows):
            keys = [key(cell_text(tc)) for tc in tr.findall(W + "tc")]
            ti = next((i for i, k in enumerate(keys) if k in ("test", "tests", "testitem", "testitems")), None)
            ri = next((i for i, k in enumerate(keys) if k.startswith("result")), None)
            if ti is None or ri is None:
                continue
            si = next((i for i, k in enumerate(keys) if k.startswith("spec")), None)
            for row in rows[h + 1:]:
                cells = row.findall(W + "tc")
                if len(cells) <= max(ti, ri):
                    continue
                name = cell_text(cells[ti]).strip()
                spec = cell_text(cells[si]).strip() if si is not None and si < len(cells) else ""
                if name:
                    yield name, spec, cells[ri]
            return


# 기본 정보 표의 라벨(정규식, key() 기준) -> 필드
INFO_FIELDS = [
    (r"certificatenumber", "certificate_number"),
    (r"supplier", "supplier"),
    (r"productcode", "product_code"),
    (r"manufacturersbatchno", "manufacturer_batch_no"),
    (r"productname", "product_name"),
    (r".*labbatchno", "lab_batch_no"),              # "Sydco's Lab. Batch No"
    (r"dateofmanufacture", "date_of_manufacture"),
    (r"expirydate", "expiry_date"),
]


def fill_document(doc, rec):
    """레코드 하나로 양식 하나를 채운다. 못 찾은 라벨 목록을 돌려준다."""
    body, f, missing = doc.element.body, rec["fields"], []

    for pattern, field in INFO_FIELDS:
        if not fill_right_cell(body, pattern, f[field], FONT_PT["info"]):
            missing.append(field)

    results = {key(r["test"]): r["result_text"] for r in rec["results"]}
    written = 0
    for name, _spec, tc in iter_result_rows(body):
        if key(name) in results:
            write_cell(tc, results[key(name)], FONT_PT["result"], align="center")
            written += 1
    if written < len(results):
        missing.append(f"Results ({written}/{len(results)} 항목만 채움)")

    jobs = [
        (fill_box, (body, r"issuedate", "next", f["issue_date"], FONT_PT["issue_date"]), "Issue date"),
        (fill_box, (body, r"dateofrelease", "prev", f["date_of_release"], FONT_PT["release_date"]), "DATE OF RELEASE"),
        (fill_box, (body, r"filelocation", "next", FIXED["file_location"], FONT_PT["file_location"]), "File Location"),
        (fill_box, (body, r"dateprinted", "next", f["date_printed"], FONT_PT["date_printed"]), "Date Printed"),
        (sign_box, (body, FIXED["lab_manager"], FONT_PT["signature"]), "LABORATORY MANAGER"),
        (fill_block_below, (body, r"companyaddress", FIXED["company_address"], FONT_PT["address"]), "COMPANY ADDRESS"),
        (fill_block_below, (body, r"contacts", FIXED["contacts"], FONT_PT["contacts"]), "CONTACTS"),
    ]
    for func, args, label in jobs:
        if not func(*args):
            missing.append(label)
    return missing


def read_form_tests(template_bytes):
    doc = Document(io.BytesIO(template_bytes))
    rows = [(name, spec) for name, spec, _ in iter_result_rows(doc.element.body)]
    if not rows:
        sys.exit("양식에서 'Tests / Results' 표를 찾지 못했습니다. 템플릿 파일을 확인하세요.")
    return rows


# =============================================================================
# 4. PDF 변환 · 정답 파일
# =============================================================================

def find_soffice():
    for name in ("soffice", "libreoffice"):
        if shutil.which(name):
            return shutil.which(name)
    for p in (r"C:\Program Files\LibreOffice\program\soffice.exe",
              r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
              "/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        if Path(p).exists():
            return p
    return None


def convert_to_pdf(docx_dir, pdf_dir):
    """PDF 변환. 실패해도 docx와 정답 파일은 그대로 남도록 오류를 안내만 하고 넘어간다."""
    files = sorted(docx_dir.glob("COA_*.docx"))
    soffice = find_soffice()
    try:
        if soffice:
            profile = tempfile.mkdtemp(prefix="lo_profile_")   # 열려 있는 LibreOffice 와 충돌하지 않도록 별도 프로필
            try:
                for i in range(0, len(files), 50):
                    subprocess.run([soffice, f"-env:UserInstallation={Path(profile).as_uri()}", "--headless",
                                    "--convert-to", "pdf", "--outdir", str(pdf_dir), *map(str, files[i:i + 50])],
                                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            finally:
                shutil.rmtree(profile, ignore_errors=True)
            return "LibreOffice"
        try:
            from docx2pdf import convert      # Windows/Mac + MS Word
        except ImportError:
            print("[안내] PDF 변환 도구가 없어 docx만 만들었습니다. "
                  "LibreOffice를 설치하거나 `pip install docx2pdf`(MS Word 필요) 후 --pdf 로 다시 실행하세요.")
            return None
        convert(str(docx_dir), str(pdf_dir))
        return "MS Word (docx2pdf)"
    except Exception as e:
        print(f"[안내] PDF 변환에 실패해 docx만 만들었습니다 ({e}). "
              "MS Word 또는 LibreOffice가 설치돼 있는지 확인하세요.")
        return None


def write_ground_truth(recs, out_dir, pdf_done):
    items = []
    for r in recs:
        failed = [x["test"] for x in r["results"] if x["judgement"] == "FAIL"]
        items.append({
            "doc_id": r["doc_id"],
            "docx": f"docx/{r['doc_id']}.docx",
            "pdf": f"pdf/{r['doc_id']}.pdf" if pdf_done else None,
            "fields": r["fields"],
            "dates_iso": r["dates_iso"],
            "results": r["results"],
            "overall_judgement": "FAIL" if failed else "PASS",
            "failed_tests": failed,
        })
    (out_dir / "ground_truth.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    cols = ["doc_id", "certificate_number", "supplier", "manufacturer_batch_no", "test", "result_text",
            "value", "unit", "spec_text", "spec_limit", "case", "judgement", "overall_judgement"]
    with open(out_dir / "ground_truth.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for it in items:
            for x in it["results"]:
                w.writerow({"doc_id": it["doc_id"], **{k: it["fields"][k] for k in cols[1:4]},
                            **{k: x[k] for k in cols[4:12]}, "overall_judgement": it["overall_judgement"]})
    return items


# =============================================================================
# 5. 실행
# =============================================================================

def main():
    ap = argparse.ArgumentParser(description="CoA_Form.docx 양식으로 가상 CoA 여러 장 생성")
    ap.add_argument("--template", default="CoA_Form.docx", help="양식 파일 경로 (기본: CoA_Form.docx)")
    ap.add_argument("--count", type=int, default=20, help="만들 CoA 개수 (기본 20)")
    ap.add_argument("--out", default="output", help="결과 폴더 (기본 output)")
    ap.add_argument("--seed", type=int, default=42, help="난수 시드 (기본 42)")
    ap.add_argument("--fail-rate", type=float, default=None,
                    help="규격 이탈 CoA 비율 0~1 (생략 시 공급사별 설정)")
    ap.add_argument("--start", default="2025-09-01", help="제조일 범위 시작 YYYY-MM-DD")
    ap.add_argument("--end", default="2026-08-31", help="제조일 범위 끝 YYYY-MM-DD")
    ap.add_argument("--pdf", action="store_true", help="PDF도 생성")
    args = ap.parse_args()

    template = Path(args.template)
    if not template.exists():
        sys.exit(f"양식 파일을 찾을 수 없습니다: {template}")
    if args.fail_rate is not None and not 0 <= args.fail_rate <= 1:
        sys.exit("--fail-rate 는 0~1 사이 값이어야 합니다.")
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    if end < start:
        sys.exit("--end 가 --start 보다 빠릅니다.")

    rng = random.Random(args.seed)
    template_bytes = template.read_bytes()
    test_defs = build_test_defs(read_form_tests(template_bytes))
    recs = make_records(args.count, test_defs, rng, start, end, args.fail_rate)

    out = Path(args.out)
    docx_dir, pdf_dir = out / "docx", out / "pdf"
    docx_dir.mkdir(parents=True, exist_ok=True)
    for d in (docx_dir, pdf_dir):            # 이전 실행에서 만든 COA_숫자 파일만 정리
        if d.exists():
            for f in d.iterdir():
                if re.fullmatch(r"COA_\d+\.(docx|pdf)", f.name):
                    f.unlink()

    for i, rec in enumerate(recs):
        doc = Document(io.BytesIO(template_bytes))
        missing = fill_document(doc, rec)
        if i == 0 and missing:
            print("[경고] 양식에서 다음 칸을 찾지 못해 비워 두었습니다:", ", ".join(missing))
        doc.save(str(docx_dir / f"{rec['doc_id']}.docx"))

    engine = None
    if args.pdf:
        pdf_dir.mkdir(exist_ok=True)
        engine = convert_to_pdf(docx_dir, pdf_dir)

    items = write_ground_truth(recs, out, pdf_done=bool(engine))

    n_fail = sum(it["overall_judgement"] == "FAIL" for it in items)
    n_near = sum(x["case"] == "near_limit" for r in recs for x in r["results"])
    by_sup = Counter(r["sup"]["name"] for r in recs)
    fail_sup = Counter(r["sup"]["name"] for r, it in zip(recs, items) if it["overall_judgement"] == "FAIL")
    print(f"[완료] 가상 CoA {len(recs)}장 -> {docx_dir}" + (f"  (PDF: {pdf_dir}, {engine})" if engine else ""))
    print(f"       규격 이탈 포함 {n_fail}장 ({n_fail / max(len(recs), 1):.0%}),  한계 근접 합격값 {n_near}개")
    for s in SUPPLIERS:
        if by_sup[s["name"]]:
            print(f"       - {s['name']}: {by_sup[s['name']]}장 (이탈 {fail_sup[s['name']]}장)")
    print(f"       정답 파일: {out / 'ground_truth.csv'}, {out / 'ground_truth.json'}")


if __name__ == "__main__":
    main()
