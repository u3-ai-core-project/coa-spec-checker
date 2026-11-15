#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
양식 D 생성기 — 호주 리튬 정제사(가상) Corvane Lithium 전자 발행(LIMS) CoA (영문)
================================================================================
COA_D_0007.pdf 와 같은 생김새로 내용만 바꿔 원하는 장수만큼 PDF 를 만든다.
원자재는 탄산리튬(기본) 또는 수산화리튬(--material lioh).

양식 D 의 특징 (판독 프로그램이 신경 써야 할 점)
  - 규격이 Min / Max 두 칸으로 나뉨 -> 두 칸을 합쳐 읽어야 함
  - 표 중간에 구분 행 ASSAY / ANIONS / TRACE METALS / PHYSICAL (시험 항목 아님)
  - 날짜가 미국식 MM/DD/YYYY   예) 03/07/2026 = 3월 7일
  - 불순물 단위 mg/kg (= ppm), 자성이물 ppb, 검출한계 미만 <0.5
  - 사내 규격에 없는 Ni, Cr, Zn, (Al), D10, D90 은 Status 가 'Report' (판정 대상 아님)
  - 예외 표기: 'ND', 'ND (LOD 0.5)', '<10', 'Sodium (as Na2O)', 'Sodium + Potassium (Na+K)'
  - 도장·손서명 없음. 'Electronically approved by ...' 전자 승인 + 바코드
  - 협력사 Status 는 항상 Pass / RELEASED -> 사내 규격으로만 잡히는 숨은 불합격만 나옴

사용법 (옵션은 세 양식 모두 같음. 자세한 설명은 README.md)
    pip install reportlab pillow pypdfium2
    python gen_D.py                                # 탄산리튬 30장, 정상 60 %, 열화 4단계 -> output_D_li2co3/
    python gen_D.py --material lioh                # 수산화리튬 -> output_D_lioh/
    python gen_D.py --count 200 --normal-rate 0.7  # 정상 70 %
    python gen_D.py --reason-weights OUT_OF_SPEC=3,SUM_ONLY=2,DATE_CONFLICT=0
    python gen_D.py --degrade original             # 열화본 없이 원본만
    python gen_D.py --fail-rate 0.25               # v1 처럼 숨은 불합격만 25 %

결과물
    pdf/<dev|eval>/<original|lowres|skew|blur>/...   CoA PDF (원본 + 열화본, 개발용/평가용 폴더로 나뉨)
    ground_truth.json / ground_truth_docs.csv / ground_truth_items.csv   정답 라벨
    receipts.csv        가상 입고 정보        variants.csv   열화본 목록
"""

import sys
from datetime import timedelta

from coa_common import (CUSTOMER, MATERIAL, Seq, draw_text, factor, fmt_date, fmt_num, font, hexcolor, make_dates,
                        nice, run, wrap)

TEMPLATE = "D"
DATE_FMT = "{m:02d}/{d:02d}/{y}"
ALLOW_BOTH = False         # Status 가 항상 Pass -> 숨은 불합격만
ISSUE_ANCHOR = "test"      # DATE_CONFLICT: Issued < Tested

SUPPLIER = dict(name="Corvane Lithium Refining Pty Ltd", impurity_level=1.0, shelf_life_months=12)

FIXED = dict(
    company="Corvane Lithium Refining Pty Ltd", company_sub="Battery Chemicals Division · Kwinana Refinery",
    address="Lot 21 Corvane Drive, Kwinana Beach WA 6167, Australia", tel="+61 8 5550 2140",
    email="quality@corvane-lithium.example.au", abn="00 000 000 000", form_no="QA-F-0311 Rev 6",
    approvers=[("J. Whitfield", "Quality Assurance Manager"), ("M. Okafor", "QC Laboratory Supervisor")],
)
PRODUCT = {
    "lioh": dict(product="Lithium Hydroxide Monohydrate", grade="Battery Grade, Micronized (LHM-BG-M)",
                 material_no="100045812", spec_ref="CVL-SPEC-LHM-BG Rev 4", lot_prefix="KB"),
    "li2co3": dict(product="Lithium Carbonate", grade="Battery Grade, Micronized (LC-BG-M)",
                   material_no="100046207", spec_ref="CVL-SPEC-LC-BG Rev 2", lot_prefix="KC"),
}

# ── 시험 항목표 (원자재별) ───────────────────────────────────────────────────────
#   sec : 이 항목부터 시작하는 구분 행     mn / mx : Min · Max 칸에 찍히는 글자
#   lsl/usl : 협력사 규격 한계(표준 단위)   lsl/usl 이 없으면 Status = Report
ITEMS_BY_MATERIAL = {
    "lioh": [
        dict(id="appearance", sec="ASSAY", label="Appearance", method="Visual", unit="—",
             spec="White crystalline powder"),
        dict(id="lioh", label="LiOH (as LiOH)", method="Potentiometric titration", unit="% w/w", dec=2, mn="56.50",
             mx="57.50", spec="56.50 – 57.50", lsl=56.5, usl=57.5),
        dict(id="co3", label="Carbonate (as CO3)", method="Potentiometric titration", unit="% w/w", dec=2, mx="0.50",
             spec="≤ 0.50", usl=0.50),
        dict(id="cl", sec="ANIONS", label="Chloride (Cl)", method="Ion chromatography", unit="mg/kg", dec=0, mx="30",
             spec="≤ 30", usl=30),
        dict(id="so4", label="Sulfate (SO4)", method="Ion chromatography", unit="mg/kg", dec=0, mx="100",
             spec="≤ 100", usl=100),
        dict(id="na", sec="TRACE METALS", label="Sodium (Na)", method="ICP-OES", unit="mg/kg", dec=0, mx="40",
             spec="≤ 40", usl=40),
        dict(id="k", label="Potassium (K)", method="ICP-OES", unit="mg/kg", dec=1, mx="20", spec="≤ 20", usl=20),
        dict(id="ca", label="Calcium (Ca)", method="ICP-OES", unit="mg/kg", dec=1, mx="20", spec="≤ 20", usl=20),
        dict(id="mg", label="Magnesium (Mg)", method="ICP-OES", unit="mg/kg", dec=1, mx="10", spec="≤ 10", usl=10),
        dict(id="fe", label="Iron (Fe)", method="ICP-OES", unit="mg/kg", dec=1, mx="5", spec="≤ 5", usl=5),
        dict(id="cu", label="Copper (Cu)", method="ICP-OES", unit="mg/kg", dec=2, mx="1", spec="≤ 1", usl=1),
        dict(id="mn", label="Manganese (Mn)", method="ICP-OES", unit="mg/kg", dec=1, mx="5", spec="≤ 5", usl=5),
        dict(id="si", label="Silicon (Si)", method="ICP-OES", unit="mg/kg", dec=0, mx="40", spec="≤ 40", usl=40),
        dict(id="ni", label="Nickel (Ni)", method="ICP-OES", unit="mg/kg", dec=1, spec="(report)"),
        dict(id="cr", label="Chromium (Cr)", method="ICP-OES", unit="mg/kg", dec=1, spec="(report)"),
        dict(id="zn", label="Zinc (Zn)", method="ICP-OES", unit="mg/kg", dec=1, spec="(report)"),
        dict(id="mag", sec="PHYSICAL", label="Magnetic impurities", method="Magnetic sep./ICP-OES", unit="ppb",
             dec=0, mx="100", spec="≤ 100", usl=100),
        dict(id="d10", label="Particle size D10", method="Laser diffraction", unit="µm", dec=1, spec="(report)"),
        dict(id="d50", label="Particle size D50", method="Laser diffraction", unit="µm", dec=1, mn="3.0", mx="20.0",
             spec="3.0 – 20.0", lsl=3, usl=20),
        dict(id="d90", label="Particle size D90", method="Laser diffraction", unit="µm", dec=1, spec="(report)"),
    ],
    # 탄산리튬: 협력사 사내 규격(가상). YS/T 582-2023 D1 급과 비슷하되 일부 항목은 조금 엄격
    "li2co3": [
        dict(id="appearance", sec="ASSAY", label="Appearance", method="Visual", unit="—", spec="White powder"),
        dict(id="li2co3", label="Li2CO3 (as Li2CO3)", method="Acid-base titration", unit="% w/w", dec=2,
             mn="99.50", spec="≥ 99.50", lsl=99.5),
        dict(id="h2o", label="Moisture (105 °C)", method="Gravimetric", unit="% w/w", dec=2, mx="0.25",
             spec="≤ 0.25", usl=0.25),
        dict(id="cl", sec="ANIONS", label="Chloride (Cl)", method="Ion chromatography", unit="mg/kg", dec=0, mx="40",
             spec="≤ 40", usl=40),
        dict(id="so4", label="Sulfate (SO4)", method="Ion chromatography", unit="mg/kg", dec=0, mx="800",
             spec="≤ 800", usl=800),
        dict(id="na", sec="TRACE METALS", label="Sodium (Na)", method="ICP-OES", unit="mg/kg", dec=0, mx="250",
             spec="≤ 250", usl=250),
        dict(id="k", label="Potassium (K)", method="ICP-OES", unit="mg/kg", dec=1, mx="30", spec="≤ 30", usl=30),
        dict(id="ca", label="Calcium (Ca)", method="ICP-OES", unit="mg/kg", dec=1, mx="60", spec="≤ 60", usl=60),
        dict(id="mg", label="Magnesium (Mg)", method="ICP-OES", unit="mg/kg", dec=1, mx="80", spec="≤ 80", usl=80),
        dict(id="fe", label="Iron (Fe)", method="ICP-OES", unit="mg/kg", dec=1, mx="8", spec="≤ 8", usl=8),
        dict(id="cu", label="Copper (Cu)", method="ICP-OES", unit="mg/kg", dec=2, mx="3", spec="≤ 3", usl=3),
        dict(id="mn", label="Manganese (Mn)", method="ICP-OES", unit="mg/kg", dec=2, mx="3", spec="≤ 3", usl=3),
        dict(id="si", label="Silicon (Si)", method="ICP-OES", unit="mg/kg", dec=1, mx="25", spec="≤ 25", usl=25),
        dict(id="ni", label="Nickel (Ni)", method="ICP-OES", unit="mg/kg", dec=1, spec="(report)"),
        dict(id="cr", label="Chromium (Cr)", method="ICP-OES", unit="mg/kg", dec=1, spec="(report)"),
        dict(id="zn", label="Zinc (Zn)", method="ICP-OES", unit="mg/kg", dec=1, spec="(report)"),
        dict(id="al", label="Aluminium (Al)", method="ICP-OES", unit="mg/kg", dec=1, spec="(report)"),
        dict(id="mag", sec="PHYSICAL", label="Magnetic impurities", method="Magnetic sep./ICP-OES", unit="ppb",
             dec=0, mx="300", spec="≤ 300", usl=300),
        dict(id="d10", label="Particle size D10", method="Laser diffraction", unit="µm", dec=1, spec="(report)"),
        dict(id="d50", label="Particle size D50", method="Laser diffraction", unit="µm", dec=1, mn="3.0", mx="8.0",
             spec="3.0 – 8.0", lsl=3, usl=8),
        dict(id="d90", label="Particle size D90", method="Laser diffraction", unit="µm", dec=1, spec="(report)"),
    ],
}
for _items in ITEMS_BY_MATERIAL.values():          # 각 항목이 어느 구분 행 아래인지 (줄이 빠져도 구분 행을 그리려고)
    _grp = None
    for _it in _items:
        _grp = _it.get("sec", _grp)
        _it["group"] = _grp

WORDS = dict(appearance_pass=["Conforms"], appearance_fail="Off-white, agglomerates", value="{t}", lod="<{t}",
             nd="ND", nd_lod="ND (LOD {t})")
STATUS_WORD = {"PASS": "Pass", "FAIL": "Fail", "REF": "Report"}
NOTES = ('Notes: (1) "<" denotes result below the limit of quantitation (LOQ). (2) Magnetic impurities = sum of Fe, '
         'Cr, Ni, Zn recovered by magnetic separation. (3) Trace metals Ni, Cr and Zn are reported for information '
         'only. (4) Results relate only to the batch tested. Methods are in-house methods validated against '
         'GB/T 11064 and ASTM E1479.')

FIELD_NAMES = [("coa_no", "CoA No."), ("issue_date", "Issued"), ("product", "Product"),
               ("material_no", "Material No."), ("grade", "Grade"), ("lot_no", "Batch / Lot"),
               ("mfg_date", "Manufactured"), ("retest_date", "Retest Date"), ("customer", "Customer"),
               ("po_no", "Customer PO"), ("so_no", "Sales Order"), ("net_weight", "Net Weight"),
               ("packaging", "Packaging"), ("sample_date", "Sampled"), ("test_date", "Tested"),
               ("approver", "Electronically approved by"), ("approved_at", "Approved at"),
               ("signature_id", "Signature ID")]


# =============================================================================
# 예외를 넣을 때 쓰는 양식별 표기 (coa_common 의 예외 주입이 부름)
# =============================================================================

def relabel(it, kind, ox=None):
    """kind: oxide(산화물 기준) / combined(Na+K) / heavy(중금속)"""
    if kind == "oxide":
        return dict(it, label=f"{it['label'].split(' (')[0]} (as {ox[0]})")
    if kind == "combined":
        return dict(it, label="Sodium + Potassium (Na+K)")
    return dict(it, label="Heavy metals (as Pb)", method="Colorimetric (as Pb)")


def make_spec(it, usl_std):
    mx = fmt_num(nice(usl_std * factor(it), up=True))
    return dict(spec=f"≤ {mx}", mx=mx, mn=None, usl=usl_std)


def set_issue_date(d, new):
    f = d["fields"]
    f["issue_date"] = fmt_date(new, DATE_FMT)
    f["approved_at"] = f"{f['issue_date']} {f['approved_at'].split(' ', 1)[1]}"


# =============================================================================
# 문서 머리글 만들기 (시험 결과표와 예외는 coa_common.run 이 만든다)
# =============================================================================

def make_docs(args):
    rng = args.rng
    pr = PRODUCT[MATERIAL["key"]]
    items = ITEMS_BY_MATERIAL[MATERIAL["key"]]
    lots = sorted((make_dates(rng, args.start, args.end, SUPPLIER["shelf_life_months"]) for _ in range(args.count)),
                  key=lambda r: (r["issue"], r["mfg"]))
    seq = Seq(rng)
    docs = []
    for i, r in enumerate(lots, 1):
        mfg, iss = r["mfg"], r["issue"]
        bags = rng.choice([24, 36, 40])
        appr = rng.choice(FIXED["approvers"])
        f = {
            "coa_no": f"CVL-COA-{iss.year}-{seq.next(('coa', iss.year), (1200, 1900), (2, 9)):05d}",
            "issue_date": fmt_date(iss, DATE_FMT), "product": pr["product"],
            "material_no": pr["material_no"], "grade": pr["grade"],
            "lot_no": f"{pr['lot_prefix']}{mfg:%y}-{mfg.timetuple().tm_yday:03d}-"
                      f"{seq.next(('lot', mfg), (1, 3), (1, 2)):02d}",
            "mfg_date": fmt_date(mfg, DATE_FMT), "retest_date": fmt_date(r["expiry"], DATE_FMT),
            "customer": CUSTOMER,
            "po_no": f"PO-SYD-{iss.year % 100:02d}{seq.next(('po', iss.year), (100, 300), (1, 6)):04d}",
            "so_no": f"SO {rng.randint(4100000, 4199999)}",
            "net_weight": f"{bags * 500:,} kg ({bags} × 500 kg)",
            "packaging": rng.choice(["FIBC 500 kg, PE liner, N2 purged", "FIBC 500 kg, Al-laminated liner"]),
            "sample_date": fmt_date(r["test"] - timedelta(days=1), DATE_FMT), "test_date": fmt_date(r["test"], DATE_FMT),
            "approver": f"{appr[0]}, {appr[1]}",
            "approved_at": f"{fmt_date(iss, DATE_FMT)} {rng.randint(8, 17):02d}:{rng.randint(0, 59):02d} AWST",
            "signature_id": "".join(rng.choice("0123456789ABCDEF") for _ in range(16)),
        }
        doc_id = f"COA_{TEMPLATE}_{i:04d}"
        dates = {k: r[k] for k in ("mfg", "test", "issue", "printed", "expiry")}
        docs.append(dict(doc_id=doc_id, supplier=SUPPLIER["name"], fields=f, dates=dates, items=items,
                         level=SUPPLIER["impurity_level"] * rng.uniform(0.85, 1.15), printed_conclusion="RELEASED",
                         approver=appr))
    return docs


# =============================================================================
# PDF 그리기 (A4)
# =============================================================================
PAGE_W, PAGE_H = 595.0, 842.0
DARK = "#0E3B33"
MINT = "#4FAE8B"
GOLD = "#C9A646"
SEC_BG = "#E5EFEB"
TEXT = "#1A1A1A"
MUTED = "#666666"


def T(y_top):
    return PAGE_H - y_top


def logo(c, cx, cy, r):
    c.saveState()
    c.setStrokeColor(hexcolor("#FFFFFF"))
    c.setFillColor(hexcolor(DARK))
    c.setLineWidth(1.6)
    c.circle(cx, cy, r, stroke=1, fill=1)
    for pts, col in (([(-0.62, -0.2), (-0.2, 0.32), (0.05, 0.02), (-0.15, -0.2)], "#FFFFFF"),
                     ([(-0.45, -0.2), (0.12, 0.38), (0.66, -0.2)], MINT)):
        p = c.beginPath()
        for k, (x, y) in enumerate(pts):
            p.moveTo(cx + x * r, cy + y * r) if k == 0 else p.lineTo(cx + x * r, cy + y * r)
        p.close()
        c.setFillColor(hexcolor(col))
        c.drawPath(p, stroke=0, fill=1)
    c.setFillColor(hexcolor(GOLD))
    c.rect(cx - 0.62 * r, cy - 0.34 * r, 1.24 * r, 0.09 * r, stroke=0, fill=1)
    c.restoreState()


def draw_doc(path, d, rng=None):
    pr = PRODUCT[MATERIAL["key"]]
    from reportlab.graphics.barcode import code128
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas
    sans, bold, mono = font("sans"), font("sans-b"), font("mono")
    f = d["fields"]
    dark, text, muted, white = hexcolor(DARK), hexcolor(TEXT), hexcolor(MUTED), hexcolor("#FFFFFF")
    c = canvas.Canvas(str(path), pagesize=(PAGE_W, PAGE_H))
    c.setTitle("Certificate of Analysis")
    c.setAuthor(d["supplier"])

    # ── 머리 띠 ───────────────────────────────────────────────
    c.setFillColor(dark)
    c.rect(0, T(76), PAGE_W, 76, stroke=0, fill=1)
    c.setFillColor(hexcolor(MINT))
    c.rect(0, T(80.5), 370, 4.5, stroke=0, fill=1)
    c.setFillColor(hexcolor(GOLD))
    c.rect(370, T(80.5), PAGE_W - 370, 4.5, stroke=0, fill=1)
    logo(c, 59.5, T(39), 18.5)
    draw_text(c, 89, T(38.5), FIXED["company"], bold, 13.5, color=white)
    draw_text(c, 89, T(49.5), FIXED["company_sub"], sans, 7.3, color=white, char_space=0.3)
    draw_text(c, 555, T(38.5), "CERTIFICATE OF ANALYSIS", sans, 15, "right", white, char_space=1.3)
    tail = f"  |  Issued {f['issue_date']}"
    w_tail = stringWidth(tail, sans, 8.3)
    draw_text(c, 555, T(51), tail, sans, 8.3, "right", white)
    w_no = draw_text(c, 555 - w_tail, T(51), f["coa_no"], bold, 8.3, "right", white)
    draw_text(c, 555 - w_tail - w_no, T(51), "CoA No. ", sans, 8.3, "right", white)

    # ── PRODUCT / SHIPMENT ───────────────────────────────────
    blocks = [(40, "PRODUCT", [("Product", f["product"]), ("Material No.", f["material_no"]), ("Grade", f["grade"]),
                                ("Batch / Lot", f["lot_no"]), ("Manufactured", f["mfg_date"]),
                                ("Retest Date", f["retest_date"])]),
              (309, "SHIPMENT", [("Customer", f["customer"]), ("Customer PO", f["po_no"]), ("Sales Order", f["so_no"]),
                                 ("Net Weight", f["net_weight"]), ("Packaging", f["packaging"]),
                                 ("Sampled / Tested", f"{f['sample_date']} / {f['test_date']}")])]
    for x, title, rows in blocks:
        draw_text(c, x, T(103.5), title, bold, 7.5, color=dark, char_space=1.4)
        c.setStrokeColor(dark)
        c.setLineWidth(0.6)
        c.line(x, T(109), x + 247, T(109))
        for k, (lab, val) in enumerate(rows):
            y = T(120.5 + k * 12.6)
            draw_text(c, x, y, lab, sans, 8.4, color=muted)
            draw_text(c, x + 85, y, val, bold, 8.4, color=text)

    # 바코드 (로트 번호)
    bc = code128.Code128(f["lot_no"], barHeight=25, barWidth=0.95, quiet=False)
    bc.drawOn(c, 47, T(219))
    draw_text(c, 40, T(226), " ".join(f["lot_no"]).replace("  ", " "), mono, 6.5, color=text, char_space=0.8)

    # ── 시험 결과 표 ──────────────────────────────────────────
    x0, x1 = 40, 556
    top = 233.0
    c.setFillColor(dark)
    c.rect(x0, T(top + 17.5), x1 - x0, 17.5, stroke=0, fill=1)
    hy = T(top + 11.8)
    for xx, h, al in ((44, "Parameter", "left"), (177, "Method", "left"), (290.5, "Unit", "center"),
                      (355, "Min", "right"), (400, "Max", "right"), (463, "Result", "right"),
                      (511.5, "Status", "center")):
        draw_text(c, xx, hy, h, bold, 7.8, al, white)
    y = top + 17.5
    group = None
    for r in d["rows"]:
        it = r["it"]
        if it.get("group") != group:
            group = it.get("group")
            c.setFillColor(hexcolor(SEC_BG))
            c.rect(x0, T(y + 13.8), x1 - x0, 13.8, stroke=0, fill=1)
            draw_text(c, 44, T(y + 9.6), group, bold, 7.2, color=dark, char_space=1.5)
            c.setStrokeColor(hexcolor("#9DB5AC"))
            c.setLineWidth(0.5)
            c.line(x0, T(y + 13.8), x1, T(y + 13.8))
            y += 13.8
        h = 15.0
        base = T(y + 10.3)
        draw_text(c, 44, base, r["printed_name"], sans, 8.3, color=text)
        draw_text(c, 177, base + 0.6, r["method"], sans, 7.3, color=muted)
        draw_text(c, 290.5, base, r["unit"], sans, 8.3, "center", text)
        if r["item_id"] == "appearance":
            lines = wrap(r["spec"], sans, 7.3, 75)
            for k, line in enumerate(lines):
                draw_text(c, 359.5, T(y + 6.6 + k * 7.6), line, sans, 7.3, "center", text)
        else:
            if it.get("mn"):
                draw_text(c, 355, base, it["mn"], sans, 8.3, "right", text)
            if it.get("mx"):
                draw_text(c, 400, base, it["mx"], sans, 8.3, "right", text)
        draw_text(c, 463, base, r["result"], bold, 8.3, "right", text)
        draw_text(c, 511.5, base, STATUS_WORD[r["supplier"]], sans, 7.8, "center", text)
        y += h
        c.setStrokeColor(hexcolor("#D5D9D7"))
        c.setLineWidth(0.5)
        c.line(x0, T(y), x1, T(y))
    c.setStrokeColor(text)
    c.setLineWidth(0.9)
    c.line(x0, T(y), x1, T(y))

    # ── Notes ────────────────────────────────────────────────
    y += 14
    for k, line in enumerate(wrap(NOTES, sans, 7.2, x1 - x0)):
        draw_text(c, x0, T(y + k * 11), line, sans, 7.2, color=text)

    # ── 출하 판정 / 전자 승인 ────────────────────────────────
    y = max(y + 40, 660)
    c.setStrokeColor(dark)
    c.setLineWidth(1.2)
    c.rect(40, T(y + 66), 277, 66, stroke=1, fill=0)
    draw_text(c, 50, T(y + 13), "BATCH DISPOSITION", sans, 7, color=muted, char_space=1.3)
    draw_text(c, 50, T(y + 30), d["printed_conclusion"], bold, 14, color=dark)
    draw_text(c, 50, T(y + 42), f"Conforms to {pr['spec_ref']}", sans, 7.4, color=text)
    c.setFillColor(hexcolor("#F3F4F4"))
    c.rect(334, T(y + 66), 222, 66, stroke=0, fill=1)
    name, title = d["approver"]
    draw_text(c, 343, T(y + 13), "Electronically approved by", sans, 7.4, color=text)
    wn = draw_text(c, 343, T(y + 28), name, bold, 9.5, color=text)
    draw_text(c, 343 + wn, T(y + 28), f", {title}", sans, 7.6, color=text)
    draw_text(c, 343, T(y + 40), f["approved_at"], sans, 7.6, color=text)
    draw_text(c, 343, T(y + 52), f"Signature ID {f['signature_id']}", mono, 6.6, color=muted)

    # ── 바닥글 ───────────────────────────────────────────────
    y = 793
    c.setStrokeColor(hexcolor("#BFC5C3"))
    c.setLineWidth(0.6)
    c.line(40, T(y), 556, T(y))
    draw_text(c, 40, T(y + 10), f"{FIXED['company']} · {FIXED['address']}", sans, 7, color=text)
    draw_text(c, 40, T(y + 21), f"T {FIXED['tel']} · {FIXED['email']} · ABN {FIXED['abn']}", sans, 7, color=text)
    draw_text(c, 556, T(y + 10), FIXED["form_no"], sans, 7, "right", text)
    draw_text(c, 556, T(y + 21), "Page 1 of 1 · Generated by LIMS · valid without handwritten signature", sans, 7,
              "right", text)
    draw_text(c, 556, T(PAGE_H - 12), "SYNTHETIC TEST DOCUMENT · fictitious company · for AI training only",
              sans, 5, "right", hexcolor("#9a9a9a"))
    c.showPage()
    c.save()


def main():
    run(sys.modules[__name__], "양식 D (호주 정제사 LIMS CoA) 가상 CoA 생성기", "output_D")


if __name__ == "__main__":
    main()
