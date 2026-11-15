#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
양식 A 생성기 — Form-320 (Sydco 사내 양식, 영문)
=================================================
협력사 4곳(가상)이 우리 회사(Sydco) 양식 Form-320 에 시험 결과를 채워 보내는 CoA.
COA_A_0007.pdf 와 같은 생김새로, 내용만 바꿔 원하는 장수만큼 PDF 를 만든다.
원자재는 탄산리튬(기본) 또는 수산화리튬(--material lioh).

양식 A 의 특징 (판독 프로그램이 신경 써야 할 점)
  - 결과 칸에 단위가 같이 찍힘   예) 12.5 ppm, 0.36 %, 26 ppb
  - 규격 표기  ≤ 50 ppm  /  56.5 – 57.5 %
  - 날짜  27-Dec-2025 (일-월약어-년)
  - 검출한계 미만은  < 0.20 ppm
  - 협력사 판정 칸이 없음 -> 협력사 규격까지 벗어난 불합격(fail_both)도 나옴
  - 협력사 규격이 사내 규격보다 느슨한 항목 -> 숨은 불합격 (수산화리튬: CO3, Na, K, Ca, Fe, Mn, Si, D50 /
    탄산리튬: Li2CO3 함량, Na, K, Ca, Mg, Fe, Si, SO4, Cl, 수분, 자성이물, D50)
  - 예외 표기: 'N.D.', 'N.D. (LOD 2 ppm)', '< 20 ppm', 'Sodium (as Na2O)', 'Heavy metals (as Pb)'

사용법 (옵션은 세 양식 모두 같음. 자세한 설명은 README.md)
    pip install reportlab pillow pypdfium2
    python gen_A.py                                # 탄산리튬 30장, 정상 60 %, 열화 4단계 -> output_A_li2co3/
    python gen_A.py --material lioh                # 수산화리튬 -> output_A_lioh/
    python gen_A.py --count 200 --normal-rate 0.7  # 정상 70 %
    python gen_A.py --reason-weights OUT_OF_SPEC=3,SUM_ONLY=2,DATE_CONFLICT=0
    python gen_A.py --degrade original             # 열화본 없이 원본만
    python gen_A.py --fail-rate 0.25               # v1 처럼 숨은 불합격만 25 %

결과물
    pdf/<dev|eval>/<original|lowres|skew|blur>/...   CoA PDF (원본 + 열화본, 개발용/평가용 폴더로 나뉨)
    ground_truth.json / ground_truth_docs.csv / ground_truth_items.csv   정답 라벨
    receipts.csv        가상 입고 정보        variants.csv   열화본 목록
"""

import sys

from coa_common import (MATERIAL, Seq, draw_text, fmt_date, fmt_num, font, hexcolor, make_dates, nice, run)

TEMPLATE = "A"
DATE_FMT = "{d:02d}-{mon}-{y}"
ALLOW_BOTH = True          # 협력사 판정 칸이 없어 협력사 규격까지 벗어난 불합격도 만든다
ISSUE_ANCHOR = "mfg"       # 시험일 칸이 없어 DATE_CONFLICT 는 '발행·출고일 < 제조일' 로 만든다

# ── 협력사 (모두 가상) ─────────────────────────────────────────────────────────────
#   product : 원자재별 (제품 코드, 제품명)      impurity_level : 불순물 수준 (1.0 = 보통)
SUPPLIERS = [
    dict(name="Arvelle Lithium Pty Ltd", batch_format="AL{yy}{mm}{seq:03d}", shelf_life_months=12,
         impurity_level=0.85, weight=3,
         product={"lioh": ("AL-LHM-BG1", "LiOH·H2O, Battery Grade"), "li2co3": ("AL-LC-BG5", "Li2CO3, Battery Grade")}),
    dict(name="Teramis Lithium Inc.", batch_format="T{yy}{mm}{dd}{seq:02d}", shelf_life_months=12,
         impurity_level=1.00, weight=3,
         product={"lioh": ("TL-LiOH-H2O-B", "LiOH·H2O BG Micronized"),
                  "li2co3": ("TL-Li2CO3-BM", "Li2CO3 BG Micronized")}),
    dict(name="Selmora Lithium S.A.", batch_format="SL{yy}-{seq:04d}", shelf_life_months=24,
         impurity_level=1.10, weight=2,
         product={"lioh": ("SLC-LHM-25", "LiOH Monohydrate (BG)"), "li2co3": ("SLC-LC-99", "Lithium Carbonate (BG)")}),
    dict(name="Nobrix Materials Ltd.", batch_format="NB{yy}{mm}-{seq:03d}", shelf_life_months=12,
         impurity_level=1.25, weight=2,
         product={"lioh": ("NBX-LHM-M", "Lithium Hydroxide BG"), "li2co3": ("NBX-LC-M", "Lithium Carbonate BG")}),
]

# ── 시험 항목표 (원자재별, 문서에 찍히는 순서 그대로) ───────────────────────────────────
#   label : 문서 항목명 ( _{ } 아래첨자, ^{ } 위첨자 )   unit : 문서 단위   dec : 소수 자릿수
#   spec  : 문서에 찍히는 협력사 규격    lsl/usl : 그 규격의 한계 (표준 단위)
ITEMS_BY_MATERIAL = {
    "lioh": [
        dict(id="appearance", label="Appearance", method="Visual", unit="-", spec="White crystalline powder"),
        dict(id="lioh", label="Lithium Hydroxide (as LiOH)", method="Titration (HCl)", unit="%", dec=2,
             spec="56.5 – 57.5 %", lsl=56.5, usl=57.5),
        dict(id="co3", label="Carbonate (as CO_{3})", method="Titration", unit="%", dec=2, spec="≤ 0.40 %", usl=0.40),
        dict(id="na", label="Sodium (Na)", method="ICP-OES", unit="ppm", dec=1, spec="≤ 50 ppm", usl=50),
        dict(id="k", label="Potassium (K)", method="ICP-OES", unit="ppm", dec=1, spec="≤ 30 ppm", usl=30),
        dict(id="ca", label="Calcium (Ca)", method="ICP-OES", unit="ppm", dec=1, spec="≤ 20 ppm", usl=20),
        dict(id="mg", label="Magnesium (Mg)", method="ICP-OES", unit="ppm", dec=1, spec="≤ 10 ppm", usl=10),
        dict(id="fe", label="Iron (Fe)", method="ICP-OES", unit="ppm", dec=1, spec="≤ 7 ppm", usl=7),
        dict(id="cu", label="Copper (Cu)", method="ICP-OES", unit="ppm", dec=2, spec="≤ 1 ppm", usl=1),
        dict(id="mn", label="Manganese (Mn)", method="ICP-OES", unit="ppm", dec=1, spec="≤ 10 ppm", usl=10),
        dict(id="si", label="Silicon (Si)", method="ICP-OES", unit="ppm", dec=1, spec="≤ 50 ppm", usl=50),
        dict(id="cl", label="Chloride (Cl^{-})", method="Ion Chromatography", unit="ppm", dec=1, spec="≤ 20 ppm",
             usl=20),
        dict(id="so4", label="Sulfate (SO_{4}^{2-})", method="Ion Chromatography", unit="ppm", dec=0,
             spec="≤ 80 ppm", usl=80),
        dict(id="mag", label="Magnetic Impurities", method="ICP-OES (magnet)", unit="ppb", dec=0, spec="≤ 50 ppb",
             usl=50),
        dict(id="d50", label="Particle Size D50", method="Laser Diffraction", unit="μm", dec=1, spec="3 – 20 µm",
             lsl=3, usl=20),
    ],
    # 탄산리튬: 협력사 규격은 YS/T 582-2023 D1 급 수준 (Nanotrun 시험성적서 표기와 같은 한도)
    "li2co3": [
        dict(id="appearance", label="Appearance", method="Visual", unit="-", spec="White powder"),
        dict(id="li2co3", label="Lithium Carbonate (as Li_{2}CO_{3})", method="Titration (HCl)", unit="%", dec=2,
             spec="≥ 99.5 %", lsl=99.5),
        dict(id="na", label="Sodium (Na)", method="ICP-OES", unit="ppm", dec=1, spec="≤ 250 ppm", usl=250),
        dict(id="k", label="Potassium (K)", method="ICP-OES", unit="ppm", dec=1, spec="≤ 50 ppm", usl=50),
        dict(id="ca", label="Calcium (Ca)", method="ICP-OES", unit="ppm", dec=1, spec="≤ 80 ppm", usl=80),
        dict(id="mg", label="Magnesium (Mg)", method="ICP-OES", unit="ppm", dec=1, spec="≤ 80 ppm", usl=80),
        dict(id="fe", label="Iron (Fe)", method="ICP-OES", unit="ppm", dec=1, spec="≤ 10 ppm", usl=10),
        dict(id="cu", label="Copper (Cu)", method="ICP-OES", unit="ppm", dec=2, spec="≤ 3 ppm", usl=3),
        dict(id="mn", label="Manganese (Mn)", method="ICP-OES", unit="ppm", dec=2, spec="≤ 3 ppm", usl=3),
        dict(id="si", label="Silicon (Si)", method="ICP-OES", unit="ppm", dec=1, spec="≤ 30 ppm", usl=30),
        dict(id="so4", label="Sulfate (SO_{4}^{2-})", method="Ion Chromatography", unit="ppm", dec=0,
             spec="≤ 800 ppm", usl=800),
        dict(id="cl", label="Chloride (Cl^{-})", method="Ion Chromatography", unit="ppm", dec=1, spec="≤ 50 ppm",
             usl=50),
        dict(id="h2o", label="Moisture (105 °C)", method="Loss on drying", unit="%", dec=2, spec="≤ 0.25 %",
             usl=0.25),
        dict(id="mag", label="Magnetic Impurities", method="ICP-OES (magnet)", unit="ppb", dec=0, spec="≤ 300 ppb",
             usl=300),
        dict(id="d50", label="Particle Size D50", method="Laser Diffraction", unit="μm", dec=1, spec="3 – 8 µm",
             lsl=3, usl=8),
    ],
}

# 결과 칸에 찍히는 표기
WORDS = dict(appearance_pass=["Conforms", "Conforms", "Complies"], appearance_fail="Off-white, lumps present",
             value="{t} {u}", lod="< {t} {u}", nd="N.D.", nd_lod="N.D. (LOD {t} {u})")

# 모든 A 양식에 똑같이 찍히는 고정 칸
FIXED = dict(
    address=["Sydco Co., Ltd. - QC Laboratory", "12, Gasang-ro 3beon-gil, Danwon-gu, Ansan-si,",
             "Gyeonggi-do 15600, Republic of Korea"],
    contacts=["Tel: +82-31-555-0142", "Fax: +82-31-555-0143", "E-mail: qc.lab@sydco.example.com"],
    file_location=r"\\QMS\QC\CoA\Form-320", lab_manager="Dr. Seo-yeon Park",
)

# 정답 라벨에 들어갈 머리글 필드 (key, 설명)
FIELD_NAMES = [("issue_date", "Issue date"), ("certificate_no", "Certificate Number"), ("supplier", "Supplier"),
               ("product_code", "Product Code"), ("product_name", "Product Name"),
               ("lot_no", "Manufacturer's Batch No"), ("lab_batch_no", "Sydco's Lab. Batch No"),
               ("mfg_date", "Date of Manufacture"), ("expiry_date", "Expiry Date"),
               ("release_date", "Date of Release"), ("printed_date", "Date Printed")]


# =============================================================================
# 예외를 넣을 때 쓰는 양식별 표기 (coa_common 의 예외 주입이 부름)
# =============================================================================

def relabel(it, kind, ox=None):
    """항목 줄의 이름을 바꾼 새 항목 정의.  kind: oxide(산화물 기준) / combined(Na+K) / heavy(중금속)"""
    if kind == "oxide":
        return dict(it, label=f"{it['label'].split(' (')[0]} (as {ox[1]})")
    if kind == "combined":
        return dict(it, label="Sodium + Potassium (Na+K)")
    return dict(it, label="Heavy metals (as Pb)", method="Sulfide colorimetry")


def make_spec(it, usl_std):
    """표준 단위 상한 -> 이 양식의 규격 글자"""
    return dict(spec=f"≤ {fmt_num(nice(usl_std * 1.0, up=True))} {it['unit']}", usl=usl_std)


def set_issue_date(d, new):
    d["fields"]["issue_date"] = d["fields"]["release_date"] = fmt_date(new, DATE_FMT)


# =============================================================================
# 문서 머리글 만들기 (시험 결과표와 예외는 coa_common.run 이 만든다)
# =============================================================================

def make_docs(args):
    rng = args.rng
    items = ITEMS_BY_MATERIAL[MATERIAL["key"]]
    lots = []
    for _ in range(args.count):
        sup = rng.choices(SUPPLIERS, weights=[s["weight"] for s in SUPPLIERS])[0]
        lots.append(dict(sup=sup, **make_dates(rng, args.start, args.end, sup["shelf_life_months"])))
    lots.sort(key=lambda r: (r["issue"], r["mfg"]))          # 번호가 날짜순으로 커지게
    seq = Seq(rng)
    docs = []
    for i, r in enumerate(lots, 1):
        sup, mfg, iss = r["sup"], r["mfg"], r["issue"]
        code, name = sup["product"][MATERIAL["key"]]
        f = {
            "issue_date": fmt_date(iss, DATE_FMT),
            "certificate_no": f"COA-{iss.year}-{seq.next(('cert', iss.year), (10, 90), (1, 6)):04d}",
            "supplier": sup["name"], "product_code": code, "product_name": name,
            "lot_no": sup["batch_format"].format(yy=f"{mfg.year % 100:02d}", mm=f"{mfg.month:02d}",
                                                 dd=f"{mfg.day:02d}", seq=seq.next((sup["name"], mfg.year),
                                                                                   (1, 20), (1, 3))),
            "lab_batch_no": f"SL{iss.year % 100:02d}-{seq.next(('lab', iss.year), (100, 400), (1, 4)):04d}",
            "mfg_date": fmt_date(mfg, DATE_FMT), "expiry_date": fmt_date(r["expiry"], DATE_FMT),
            "release_date": fmt_date(iss, DATE_FMT), "printed_date": fmt_date(r["printed"], DATE_FMT),
        }
        doc_id = f"COA_{TEMPLATE}_{i:04d}"
        dates = {k: r[k] for k in ("mfg", "test", "issue", "printed", "expiry")}
        docs.append(dict(doc_id=doc_id, supplier=sup["name"], fields=f, dates=dates, items=items,
                         level=sup["impurity_level"] * rng.uniform(0.85, 1.15), printed_conclusion=None))
    return docs


# =============================================================================
# PDF 그리기 (좌표 단위 pt, 위에서부터 잰 값을 T() 로 바꿔 씀)
# =============================================================================
PAGE_W, PAGE_H = 635.0, 780.0          # 원본 Word 양식 용지 크기
FILL = "#FAF0DC"                       # 채워 넣는 칸의 연한 베이지 배경
LINE = "#000000"


def T(y_top):
    return PAGE_H - y_top


def cell_text(c, x0, x1, top, bot, text, fname, size, align="left", pad=5):
    base = T(bot) + (bot - top - size * 0.72) / 2
    x = {"left": x0 + pad, "center": (x0 + x1) / 2, "right": x1 - pad}[align]
    draw_text(c, x, base, text, fname, size, align)


def fill_rect(c, x0, top, x1, bot, color=FILL):
    c.setFillColor(hexcolor(color))
    c.rect(x0, T(bot), x1 - x0, bot - top, stroke=0, fill=1)


def draw_doc(path, d, rng=None):
    from reportlab.pdfgen import canvas
    sans, bold, ital = font("sans"), font("sans-b"), font("sans-i")
    f = d["fields"]
    c = canvas.Canvas(str(path), pagesize=(PAGE_W, PAGE_H))
    c.setTitle("Template-Certificate of Analysis")
    c.setAuthor(d["supplier"])
    c.setFillColor(hexcolor("#000000"))

    # 오른쪽 위 양식 번호 + 발행일
    draw_text(c, 511, T(43), "Form-320", bold, 9.5)
    draw_text(c, 511, T(54), "Issue date:", bold, 9.5)
    fill_rect(c, 502, 60, 578, 75)
    c.setFillColor(hexcolor("#000000"))
    cell_text(c, 502, 578, 60, 75, f["issue_date"], sans, 8.5, "center")

    # 제목
    draw_text(c, 338, T(67), "Template-Certificate of Analysis", bold, 13, "center")
    draw_text(c, 338, T(81), "(Ref. SOP LAB-030)", sans, 10.5, "center")
    draw_text(c, 338, T(108), "CERTIFICATE OF ANALYSIS", bold, 13, "center")

    # 머리글 표 (4행 x 4열)
    cols = [84, 214, 330, 463, 588]
    top, rh = 126.5, 17.2
    info = [("Certificate Number", f["certificate_no"], "Supplier:", f["supplier"]),
            ("Product Code", f["product_code"], "Manufacturer’s Batch No", f["lot_no"]),
            ("Product Name", f["product_name"], "Sydco’s Lab. Batch No", f["lab_batch_no"]),
            ("Date of Manufacture", f["mfg_date"], "Expiry Date", f["expiry_date"])]
    for r, row in enumerate(info):
        y0, y1 = top + r * rh, top + (r + 1) * rh
        fill_rect(c, cols[1], y0, cols[2], y1)
        fill_rect(c, cols[3], y0, cols[4], y1)
        c.setFillColor(hexcolor("#000000"))
        for k, txt in enumerate(row):
            cell_text(c, cols[k], cols[k + 1], y0, y1, txt, bold if k % 2 == 0 else sans, 9.5)
    c.setStrokeColor(hexcolor(LINE))
    c.setLineWidth(0.5)
    for r in range(5):
        c.line(cols[0], T(top + r * rh), cols[-1], T(top + r * rh))
    for x in cols:
        c.line(x, T(top), x, T(top + 4 * rh))
    c.setLineWidth(1.4)
    c.rect(cols[0], T(top + 4 * rh), cols[-1] - cols[0], 4 * rh, stroke=1, fill=0)

    c.setFillColor(hexcolor("#000000"))
    draw_text(c, 86, T(216), "The undersigned hereby certifies the following data to be true specification of the "
                             "obtained results of tests", bold, 8.3)
    draw_text(c, 86, T(228), "and assays.", bold, 8.3)

    # 시험 결과 표
    cols = [84, 228, 323, 448, 587]
    top, hh, rh = 244.5, 17.5, 15.1
    for k, h in enumerate(["Tests", "Method", "Results", "Specifications"]):
        cell_text(c, cols[k], cols[k + 1], top, top + hh, h, bold, 11, "center")
    for n, r in enumerate(d["rows"]):
        y0 = top + hh + n * rh
        y1 = y0 + rh
        fill_rect(c, cols[2], y0, cols[3], y1)
        c.setFillColor(hexcolor("#000000"))
        cell_text(c, cols[0], cols[1], y0, y1, r["it"]["label"], sans, 9.5)
        cell_text(c, cols[1], cols[2], y0, y1, r["method"], sans, 8)
        cell_text(c, cols[2], cols[3], y0, y1, r["result"], sans, 9.5, "center")
        cell_text(c, cols[3], cols[4], y0, y1, r["spec"], sans, 9.5)
    bottom = top + hh + len(d["rows"]) * rh
    c.setStrokeColor(hexcolor(LINE))
    c.setLineWidth(0.5)
    for n in range(len(d["rows"]) + 1):
        c.line(cols[0], T(top + hh + n * rh), cols[-1], T(top + hh + n * rh))
    for x in cols[1:-1]:
        c.line(x, T(top), x, T(bottom))
    c.setLineWidth(1.4)
    c.rect(cols[0], T(bottom), cols[-1] - cols[0], bottom - top, stroke=1, fill=0)

    # 출고일 / 실험실 책임자 서명
    y = bottom + 15
    fill_rect(c, 404, y, 523, y + 41)
    fill_rect(c, 85, y + 25, 175, y + 41)
    c.setFillColor(hexcolor("#000000"))
    draw_text(c, 463, T(y + 19), FIXED["lab_manager"], ital, 11, "center")
    draw_text(c, 463, T(y + 32), "Signature", sans, 7, "center")
    draw_text(c, 130, T(y + 37), f["release_date"], sans, 9.5, "center")
    c.setDash(1, 1)
    c.setLineWidth(0.5)
    c.line(85, T(y + 43), 148, T(y + 43))
    c.line(404, T(y + 43), 488, T(y + 43))
    c.setDash()
    draw_text(c, 85, T(y + 56), "DATE OF RELEASE", bold, 9.5)
    draw_text(c, 404, T(y + 56), "LABORATORY MANAGER", bold, 9.5)

    # 회사 주소 / 연락처 상자
    y = bottom + 106
    fill_rect(c, 89, y + 13, 587, y + 77)
    c.setFillColor(hexcolor("#000000"))
    draw_text(c, 89, T(y + 11), "COMPANY ADDRESS:", bold, 10.5)
    draw_text(c, 350, T(y + 11), "CONTACTS:", bold, 8.5)
    for k, line in enumerate(FIXED["address"]):
        draw_text(c, 89, T(y + 25 + k * 11.5), line, sans, 8.8)
    for k, line in enumerate(FIXED["contacts"]):
        draw_text(c, 350, T(y + 25 + k * 11.5), line, sans, 8.8)
    c.setLineWidth(1.2)
    c.rect(89, T(y + 85), 498, 85, stroke=1, fill=0)
    c.setLineWidth(0.6)
    c.line(349, T(y), 349, T(y + 85))

    # 바닥글
    y = 745
    fill_rect(c, 142, y - 10, 286, y + 3)
    fill_rect(c, 363, y - 10, 454, y + 3)
    c.setFillColor(hexcolor("#000000"))
    draw_text(c, 85, T(y), "File Location:", sans, 7.8)
    draw_text(c, 214, T(y), FIXED["file_location"], sans, 7.8, "center")
    draw_text(c, 308, T(y), "Date Printed:", sans, 7.8)
    draw_text(c, 408, T(y), f["printed_date"], sans, 7.8, "center")
    draw_text(c, 502, T(y), "Page 1 of 1", bold, 7.8)
    draw_text(c, PAGE_W - 20, T(PAGE_H - 8), "SYNTHETIC TEST DOCUMENT · fictitious company · for AI training only",
              sans, 5, "right", hexcolor("#9a9a9a"))
    c.showPage()
    c.save()


def main():
    run(sys.modules[__name__], "양식 A (Form-320) 가상 CoA 생성기", "output_A")


if __name__ == "__main__":
    main()
