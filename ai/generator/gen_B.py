#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
양식 B 생성기 — 중국 리튬 정제사(가상) 产品检验报告单 (중문/영문)
==================================================================
瑞澜锂业(宜春)有限公司 Ruilan Lithium 이 보내는 검사보고서. COA_B_0005.pdf 와 같은 생김새로
내용만 바꿔 원하는 장수만큼 PDF 를 만든다. 원자재는 탄산리튬(기본) 또는 수산화리튬(--material lioh).

양식 B 의 특징 (판독 프로그램이 신경 써야 할 점)
  - 항목명이 중국어 + 영어   예) 钠 Na, 碳酸根 CO₃²⁻
  - 불순물을 % 로 표기       예) Na 0.0018 %  = 18 ppm  (x 10000)
  - 자성이물 단위 μg/kg (= ppb)
  - 규격 표기  ≤0.0050 / 56.5～57.5 (전각 물결표)
  - 날짜 2026-02-21,  검출한계 미만 <0.00002
  - 사내 규격에 없는 항목 硼 B(붕소), 酸不溶物(산불용분), 镍 Ni(탄산리튬) -> 판정 대상 아님 (REF)
  - 예외 표기: '未检出', '未检出(检出限0.0002)', '氧化钠 Na2O', '钾钠合量 Na+K', '重金属(以Pb计)'
  - 협력사 판정은 항상 合格 -> 사내 규격으로만 잡히는 숨은 불합격만 나옴
  - 빨간 질검 도장, 손서명

사용법 (옵션은 세 양식 모두 같음. 자세한 설명은 README.md)
    pip install reportlab pillow pypdfium2
    python gen_B.py                                # 탄산리튬 30장, 정상 60 %, 열화 4단계 -> output_B_li2co3/
    python gen_B.py --material lioh                # 수산화리튬 -> output_B_lioh/
    python gen_B.py --count 200 --normal-rate 0.7  # 정상 70 %
    python gen_B.py --reason-weights OUT_OF_SPEC=3,SUM_ONLY=2,DATE_CONFLICT=0
    python gen_B.py --degrade original             # 열화본 없이 원본만
    python gen_B.py --fail-rate 0.25               # v1 처럼 숨은 불합격만 25 %

결과물
    pdf/<dev|eval>/<original|lowres|skew|blur>/...   CoA PDF (원본 + 열화본, 개발용/평가용 폴더로 나뉨)
    ground_truth.json / ground_truth_docs.csv / ground_truth_items.csv   정답 라벨
    receipts.csv        가상 입고 정보        variants.csv   열화본 목록
"""

import sys

from coa_common import (CUSTOMER, MATERIAL, Seq, draw_text, factor, fmt_date, fmt_num, font, hexcolor, make_dates,
                        nice, round_seal, run, signature, wrap)

TEMPLATE = "B"
DATE_FMT = "{y}-{m:02d}-{d:02d}"
ALLOW_BOTH = False         # 单项判定 이 항상 合格 -> 숨은 불합격만
ISSUE_ANCHOR = "test"      # DATE_CONFLICT: 报告日期 < 检验日期

SUPPLIER = dict(name="Ruilan Lithium (Yichun) Co., Ltd.", impurity_level=1.05, shelf_life_months=12)

# 고정 정보 (모두 가상)
FIXED = dict(
    company_cn="瑞澜锂业（宜春）有限公司", company_en="RUILAN LITHIUM (YICHUN) CO., LTD.",
    doc_no="RL/QR-8.2-05", doc_rev="A/2", seal_top="瑞澜锂业（宜春）有限公司", seal_bottom="质检专用章",
    address_cn="地址 Add.：江西省宜春市袁州区锂电新材料产业园锂源大道88号",
    address_en="No.88 Liyuan Avenue, Lithium New Materials Industrial Park, Yuanzhou, Yichun, Jiangxi, China",
    tel="+86-795-555-0188", fax="+86-795-555-0189", email="qc@ruilan-li.example.cn",
)
# 원자재별로 달라지는 칸 (제품명, 검사 기준, 로트 머리글자, 결론 문구)
PRODUCT = {
    "lioh": dict(standard="GB/T 26008-2020 (D1)", product_cn="电池级单水氢氧化锂",
                 product_en="Battery Grade Lithium Hydroxide Monohydrate", grade="D1 微粉 Micronized", lot_prefix="LH",
                 conclusion_cn="该批产品经检验，所检项目均符合 GB/T 26008-2020 D1 级要求，判定为合格。",
                 conclusion_en="The batch complies with GB/T 26008-2020 (Grade D1). Conclusion: QUALIFIED."),
    "li2co3": dict(standard="YS/T 582-2023 (D1)", product_cn="电池级碳酸锂", product_en="Battery Grade Lithium Carbonate",
                   grade="D1 微粉 Micronized", lot_prefix="LC",
                   conclusion_cn="该批产品经检验，所检项目均符合 YS/T 582-2023 D1 级要求，判定为合格。",
                   conclusion_en="The batch complies with YS/T 582-2023 (Grade D1). Conclusion: QUALIFIED."),
}

# ── 시험 항목표 (원자재별) ───────────────────────────────────────────────────────
#   cn : 중국어 항목명   en : 영어 (작은 글씨, _{ } ^{ } 첨자)   plain : 정답 라벨에 쓰는 항목명
#   unit : 문서 단위   dec : 소수 자릿수   spec : 문서 규격 표기   lsl/usl : 규격 한계(표준 단위)
ITEMS_BY_MATERIAL = {
    "lioh": [
        dict(id="appearance", cn="外观", en="Appearance", plain="外观 Appearance", unit="—",
             spec="白色结晶粉末，无可见杂质"),
        dict(id="lioh", cn="氢氧化锂", en="LiOH", plain="氢氧化锂 LiOH", unit="%", dec=2, spec="56.5～57.5",
             lsl=56.5, usl=57.5),
        dict(id="co3", cn="碳酸根", en="CO_{3}^{2−}", plain="碳酸根 CO₃²⁻", unit="%", dec=2, spec="≤0.40", usl=0.40),
        dict(id="na", cn="钠", en="Na", plain="钠 Na", unit="%", dec=4, spec="≤0.0050", usl=50),
        dict(id="k", cn="钾", en="K", plain="钾 K", unit="%", dec=4, spec="≤0.0030", usl=30),
        dict(id="fe", cn="铁", en="Fe", plain="铁 Fe", unit="%", dec=5, spec="≤0.0007", usl=7),
        dict(id="ca", cn="钙", en="Ca", plain="钙 Ca", unit="%", dec=4, spec="≤0.0020", usl=20),
        dict(id="cu", cn="铜", en="Cu", plain="铜 Cu", unit="%", dec=5, spec="≤0.0001", usl=1),
        dict(id="mg", cn="镁", en="Mg", plain="镁 Mg", unit="%", dec=5, spec="≤0.0010", usl=10),
        dict(id="mn", cn="锰", en="Mn", plain="锰 Mn", unit="%", dec=5, spec="≤0.0010", usl=10),
        dict(id="si", cn="硅", en="Si", plain="硅 Si", unit="%", dec=4, spec="≤0.0050", usl=50),
        dict(id="cl", cn="氯离子", en="Cl^{−}", plain="氯离子 Cl⁻", unit="%", dec=4, spec="≤0.0020", usl=20),
        dict(id="so4", cn="硫酸根", en="SO_{4}^{2−}", plain="硫酸根 SO₄²⁻", unit="%", dec=4, spec="≤0.0080", usl=80),
        dict(id="boron", cn="硼", en="B", plain="硼 B", unit="%", dec=4, spec="≤0.0050", usl=50),
        dict(id="acid_insol", cn="酸不溶物", en="Acid Insoluble", plain="酸不溶物 Acid Insoluble", unit="%", dec=4,
             spec="≤0.0050", usl=50),
        dict(id="mag", cn="磁性物质", en="Magnetic Substance", plain="磁性物质 Magnetic Substance", unit="μg/kg",
             dec=0, spec="≤50", usl=50),
        dict(id="d50", cn="粒度 D50", en="Particle Size", plain="粒度 D50 Particle Size", unit="μm", dec=1,
             spec="3.0～20.0", lsl=3, usl=20),
    ],
    # 탄산리튬: YS/T 582-2023 D1 급 한도 (Nanotrun 시험성적서 표기와 같은 값). 불순물은 % 로 표기
    "li2co3": [
        dict(id="appearance", cn="外观", en="Appearance", plain="外观 Appearance", unit="—",
             spec="白色粉末，无可见杂质"),
        dict(id="li2co3", cn="碳酸锂", en="Li_{2}CO_{3}", plain="碳酸锂 Li₂CO₃", unit="%", dec=2, spec="≥99.5",
             lsl=99.5),
        dict(id="na", cn="钠", en="Na", plain="钠 Na", unit="%", dec=4, spec="≤0.025", usl=250),
        dict(id="k", cn="钾", en="K", plain="钾 K", unit="%", dec=5, spec="≤0.0050", usl=50),
        dict(id="ca", cn="钙", en="Ca", plain="钙 Ca", unit="%", dec=4, spec="≤0.0080", usl=80),
        dict(id="mg", cn="镁", en="Mg", plain="镁 Mg", unit="%", dec=4, spec="≤0.0080", usl=80),
        dict(id="fe", cn="铁", en="Fe", plain="铁 Fe", unit="%", dec=5, spec="≤0.0010", usl=10),
        dict(id="cu", cn="铜", en="Cu", plain="铜 Cu", unit="%", dec=5, spec="≤0.0003", usl=3),
        dict(id="mn", cn="锰", en="Mn", plain="锰 Mn", unit="%", dec=5, spec="≤0.0003", usl=3),
        dict(id="ni", cn="镍", en="Ni", plain="镍 Ni", unit="%", dec=5, spec="≤0.0010", usl=10),
        dict(id="si", cn="硅", en="Si", plain="硅 Si", unit="%", dec=4, spec="≤0.0030", usl=30),
        dict(id="boron", cn="硼", en="B", plain="硼 B", unit="%", dec=5, spec="≤0.0050", usl=50),
        dict(id="so4", cn="硫酸根", en="SO_{4}^{2−}", plain="硫酸根 SO₄²⁻", unit="%", dec=3, spec="≤0.080", usl=800),
        dict(id="cl", cn="氯离子", en="Cl^{−}", plain="氯离子 Cl⁻", unit="%", dec=4, spec="≤0.0050", usl=50),
        dict(id="h2o", cn="水分", en="H_{2}O", plain="水分 H₂O", unit="%", dec=2, spec="≤0.25", usl=0.25),
        dict(id="mag", cn="磁性物质", en="Magnetic Substance", plain="磁性物质 Magnetic Substance", unit="μg/kg",
             dec=0, spec="≤300", usl=300),
        dict(id="d50", cn="粒度 D50", en="Particle Size", plain="粒度 D50 Particle Size", unit="μm", dec=1,
             spec="3.0～8.0", lsl=3, usl=8),
    ],
}

WORDS = dict(appearance_pass=["符合"], appearance_fail="微黄，有结块", value="{t}", lod="<{t}",
             nd="未检出", nd_lod="未检出(检出限{t})")
JUDGE_WORD = {"PASS": "合格", "FAIL": "不合格", "REF": "合格"}
REMARKS = ["1. 磁性物质为 Fe+Cr+Ni+Zn 总量（ICP-OES 法）；Magnetic substance = sum of Fe, Cr, Ni, Zn.",
           "2. “<”表示低于方法检出限；\"<\" means below the method detection limit.",
           "3. 本报告仅对本批次产品负责，未经本公司书面批准不得部分复制。This report is valid for the stated batch only."]

FIELD_NAMES = [("report_no", "报告编号 Report No."), ("product", "产品名称 Product"), ("grade", "规格型号 Grade"),
               ("customer", "客户名称 Customer"), ("lot_no", "批号 Batch No."), ("lot_size", "批量 Lot Size"),
               ("mfg_date", "生产日期 Mfg. Date"), ("test_date", "检验日期 Test Date"),
               ("expiry_date", "保质期 Expiry Date"), ("packing", "包装规格 Packing"),
               ("issue_date", "报告日期 Date of Issue"), ("standard", "检验依据 Standard")]


# =============================================================================
# 예외를 넣을 때 쓰는 양식별 표기 (coa_common 의 예외 주입이 부름)
# =============================================================================

def relabel(it, kind, ox=None):
    """kind: oxide(산화물 기준) / combined(Na+K) / heavy(중금속)"""
    if kind == "oxide":
        return dict(it, cn=ox[2], en=ox[1], plain=f"{ox[2]} {ox[0]}")
    if kind == "combined":
        return dict(it, cn="钾钠合量", en="Na+K", plain="钾钠合量 Na+K")
    return dict(it, cn="重金属", en="(以Pb计) as Pb", plain="重金属(以Pb计) Heavy metals as Pb")


def make_spec(it, usl_std):
    return dict(spec=f"≤{fmt_num(nice(usl_std * factor(it), up=True))}", usl=usl_std)


def set_issue_date(d, new):
    d["fields"]["issue_date"] = fmt_date(new, DATE_FMT)


# =============================================================================
# 문서 머리글 만들기 (시험 결과표와 예외는 coa_common.run 이 만든다)
# =============================================================================

def make_docs(args):
    rng = args.rng
    pr = PRODUCT[MATERIAL["key"]]
    items = [dict(it, label=it["plain"]) for it in ITEMS_BY_MATERIAL[MATERIAL["key"]]]
    lots = sorted((make_dates(rng, args.start, args.end, SUPPLIER["shelf_life_months"]) for _ in range(args.count)),
                  key=lambda r: (r["issue"], r["mfg"]))
    seq = Seq(rng)
    docs = []
    for i, r in enumerate(lots, 1):
        mfg, iss = r["mfg"], r["issue"]
        f = {
            "report_no": f"JY{iss:%Y%m%d}-{seq.next(('rep', iss), (1, 4), (1, 3)):02d}",
            "product": f"{pr['product_cn']} {pr['product_en']}", "grade": pr["grade"], "customer": CUSTOMER,
            "lot_no": f"{pr['lot_prefix']}{mfg:%y%m%d}{seq.next(('lot', mfg), (1, 3), (1, 2)):02d}",
            "lot_size": f"{rng.choice([10000, 16000, 20000, 24000]):,} kg",
            "mfg_date": fmt_date(mfg, DATE_FMT), "test_date": fmt_date(r["test"], DATE_FMT),
            "expiry_date": fmt_date(r["expiry"], DATE_FMT),
            "packing": rng.choice(["500 kg/袋 吨袋 Jumbo Bag", "25 kg/袋 铝塑复合袋 Al-PE Bag"]),
            "issue_date": fmt_date(iss, DATE_FMT), "standard": pr["standard"],
        }
        doc_id = f"COA_{TEMPLATE}_{i:04d}"
        dates = {k: r[k] for k in ("mfg", "test", "issue", "printed", "expiry")}
        docs.append(dict(doc_id=doc_id, supplier=SUPPLIER["name"], fields=f, dates=dates, items=items,
                         level=SUPPLIER["impurity_level"] * rng.uniform(0.85, 1.15),
                         printed_conclusion="合格 / QUALIFIED", seal_code=f"{rng.randint(36000000, 36999999)}"))
    return docs


# =============================================================================
# PDF 그리기 (A4, 위에서부터 잰 pt 를 T() 로 바꿔 씀)
# =============================================================================
PAGE_W, PAGE_H = 595.0, 842.0
GREY = "#F1F1EC"
INK = "#111111"


def T(y_top):
    return PAGE_H - y_top


def two_line_label(c, x, top, bot, cn, en, align="left", cn_size=9.5, en_size=6.5, bold_cn=False):
    """칸 안에 중국어(위) + 영어(아래 작게) 두 줄"""
    mid = (top + bot) / 2
    fcn = font("cjk-b") if bold_cn else font("cjk")
    draw_text(c, x, T(mid - 0.5), cn, fcn, cn_size, align)
    draw_text(c, x, T(mid + en_size + 1.5), en, font("serif"), en_size, align)


def mid_text(c, x, top, bot, text, fname, size, align="left"):
    draw_text(c, x, T(bot) + (bot - top - size * 0.72) / 2, text, fname, size, align)


def logo(c, cx, cy, r):
    import math
    c.saveState()
    for rr, col, fill in ((r, "#1F6F78", 1), (r * 0.82, "#FFFFFF", 0)):
        p = c.beginPath()
        for k in range(6):
            a = math.radians(90 + 60 * k)
            x, y = cx + rr * math.cos(a), cy + rr * math.sin(a)
            p.moveTo(x, y) if k == 0 else p.lineTo(x, y)
        p.close()
        c.setFillColor(hexcolor(col))
        c.setStrokeColor(hexcolor(col))
        c.setLineWidth(0.8)
        c.drawPath(p, stroke=1 - fill, fill=fill)
    draw_text(c, cx, cy - r * 0.27, "RL", font("serif-b"), r * 0.8, "center", hexcolor("#FFFFFF"))
    c.restoreState()


def draw_doc(path, d, rng):
    pr = PRODUCT[MATERIAL["key"]]
    from reportlab.pdfgen import canvas
    cjk, cjkb, serif, serifb, sans = font("cjk"), font("cjk-b"), font("serif"), font("serif-b"), font("sans")
    f = d["fields"]
    ink = hexcolor(INK)
    c = canvas.Canvas(str(path), pagesize=(PAGE_W, PAGE_H))
    c.setTitle("产品检验报告单 / Certificate of Analysis")
    c.setAuthor(d["supplier"])

    # ── 머리: 로고, 회사명, 문서번호 ─────────────────────────────
    logo(c, 66.5, T(60.5), 21)
    draw_text(c, 101, T(62), FIXED["company_cn"], cjkb, 17.5, color=ink)
    draw_text(c, 101, T(77), FIXED["company_en"], serif, 9.2, char_space=0.6)
    c.setStrokeColor(ink)
    c.setLineWidth(0.6)
    c.line(422, T(43), 422, T(79))
    for k, line in enumerate([f"文件编号 Doc. No.：{FIXED['doc_no']}", f"版本/修改 Rev.：{FIXED['doc_rev']}",
                              "第 1 页 共 1 页 Page 1 of 1"]):
        draw_text(c, 430, T(51 + k * 11.5), line, cjk, 7.8)
    c.setLineWidth(2.2)
    c.line(43, T(93), 552, T(93))
    c.setLineWidth(0.6)
    c.line(43, T(96.5), 552, T(96.5))

    draw_text(c, 297.5, T(125), "产 品 检 验 报 告 单", cjkb, 19.5, "center")
    draw_text(c, 297.5, T(141), "CERTIFICATE OF ANALYSIS", serifb, 10.5, "center", char_space=2.6)
    draw_text(c, 43, T(165), "报告编号 Report No.：", cjk, 8.5)
    from reportlab.pdfbase.pdfmetrics import stringWidth
    draw_text(c, 43 + stringWidth("报告编号 Report No.：", cjk, 8.5), T(165), f["report_no"], serifb, 8.5)
    draw_text(c, 552, T(165), pr["standard"], serifb, 8.5, "right")
    draw_text(c, 552 - stringWidth(pr["standard"], serifb, 8.5), T(165), "检验依据 Standard：", cjk, 8.5, "right")

    # ── 제품 정보 표 ──────────────────────────────────────────
    cols = [43, 118, 296, 372, 552]
    top, rh = 172.0, 24.2
    rows = [(("产品名称", "Product"), f["product"], None, None),
            (("规格型号", "Grade"), f["grade"], ("客户名称", "Customer"), f["customer"]),
            (("批　　号", "Batch No."), f["lot_no"], ("批　　量", "Lot Size"), f["lot_size"]),
            (("生产日期", "Mfg. Date"), f["mfg_date"], ("检验日期", "Test Date"), f["test_date"]),
            (("保 质 期", "Expiry Date"), f["expiry_date"], ("包装规格", "Packing"), f["packing"])]
    for r, (l1, v1, l2, v2) in enumerate(rows):
        y0, y1 = top + r * rh, top + (r + 1) * rh
        c.setFillColor(hexcolor(GREY))
        c.rect(cols[0], T(y1), cols[1] - cols[0], rh, stroke=0, fill=1)
        if l2:
            c.rect(cols[2], T(y1), cols[3] - cols[2], rh, stroke=0, fill=1)
        c.setFillColor(ink)
        two_line_label(c, cols[0] + 5, y0, y1, *l1)
        vfont = serifb if l1[1] == "Batch No." else cjk
        mid_text(c, cols[1] + 6, y0, y1, v1, vfont, 9)
        if l2:
            two_line_label(c, cols[2] + 5, y0, y1, *l2)
            mid_text(c, cols[3] + 6, y0, y1, v2, cjk, 9)
    c.setStrokeColor(ink)
    c.setLineWidth(0.5)
    for r in range(6):
        c.line(cols[0], T(top + r * rh), cols[-1], T(top + r * rh))
    for x in (cols[0], cols[1], cols[-1]):
        c.line(x, T(top), x, T(top + 5 * rh))
    for x in (cols[2], cols[3]):
        c.line(x, T(top + rh), x, T(top + 5 * rh))
    c.setLineWidth(1.0)
    c.rect(cols[0], T(top + 5 * rh), cols[-1] - cols[0], 5 * rh, stroke=1, fill=0)

    # ── 시험 항목 표 ──────────────────────────────────────────
    cols = [43, 69, 216, 263, 359, 490, 552]
    top, hh, rh, rh1 = 300.5, 27.0, 16.1, 28.0
    c.setFillColor(hexcolor(GREY))
    c.rect(cols[0], T(top + hh), cols[-1] - cols[0], hh, stroke=0, fill=1)
    c.setFillColor(ink)
    for k, (cn, en) in enumerate([("序号", "No."), ("检验项目", "Test Item"), ("单位", "Unit"),
                                  ("标准要求", "Specification"), ("检验结果", "Result"), ("单项判定", "Judgement")]):
        two_line_label(c, (cols[k] + cols[k + 1]) / 2, top, top + hh, cn, en, "center", 8.5, 6.3, True)
    y = top + hh
    lines = [y]
    for r in d["rows"]:
        it = r["it"]
        h = rh1 if r["item_id"] == "appearance" else rh
        y0, y1 = y, y + h
        mid_text(c, (cols[0] + cols[1]) / 2, y0, y1, str(r["row"]), serif, 9, "center")
        w = draw_text(c, cols[1] + 5, T(y1) + (h - 9 * 0.72) / 2, it["cn"], cjk, 9.2)
        draw_text(c, cols[1] + 5 + w + 3, T(y1) + (h - 9 * 0.72) / 2, it["en"], serif, 6.5)
        mid_text(c, (cols[2] + cols[3]) / 2, y0, y1, r["unit"], cjk if r["unit"] == "—" else serif, 9, "center")
        if r["item_id"] == "appearance":
            sp = wrap(r["spec"], cjk, 9, cols[4] - cols[3] - 8)
            for k, line in enumerate(sp):
                draw_text(c, (cols[3] + cols[4]) / 2, T(y0 + 11 + k * 12.5), line, cjk, 9, "center")
        else:
            mid_text(c, (cols[3] + cols[4]) / 2, y0, y1, r["spec"], cjk, 9.5, "center")
        mid_text(c, (cols[4] + cols[5]) / 2, y0, y1, r["result"], cjk if not r["result"].isascii() else serif,
                 9, "center")
        mid_text(c, (cols[5] + cols[6]) / 2, y0, y1, JUDGE_WORD[r["supplier"]], cjk, 9, "center")
        y = y1
        lines.append(y)
    c.setLineWidth(0.5)
    for k, yy in enumerate([top] + lines):
        c.setLineWidth(0.9 if k in (0, 1, 4, 12) else 0.5)
        c.line(cols[0], T(yy), cols[-1], T(yy))
    c.setLineWidth(0.5)
    for x in cols[1:-1]:
        c.line(x, T(top), x, T(y))
    # 결론 칸
    cb = y + 41
    draw_text(c, cols[0] + 6, T(y + 17), "检验结论 Conclusion：", cjkb, 9.5)
    draw_text(c, cols[0] + 6 + stringWidth("检验结论 Conclusion：", cjkb, 9.5), T(y + 17), pr["conclusion_cn"], cjk, 9)
    draw_text(c, cols[0] + 6, T(y + 33), pr["conclusion_en"], serif, 9)
    c.setLineWidth(1.0)
    c.rect(cols[0], T(cb), cols[-1] - cols[0], cb - top, stroke=1, fill=0)

    # ── 비고 ──────────────────────────────────────────────────
    y = cb + 15
    draw_text(c, 43, T(y), "备注 Remarks：" + REMARKS[0], cjk, 7.8)
    for k, rem in enumerate(REMARKS[1:], 1):
        draw_text(c, 91, T(y + k * 12), rem, cjk, 7.8)

    # ── 서명 · 도장 ───────────────────────────────────────────
    y = cb + 66
    for x, cn, en in ((43, "检验员", "Inspector"), (213, "审　核", "Checked by"), (383, "批　准", "Approved by")):
        draw_text(c, x, T(y), cn, cjk, 9)
        draw_text(c, x, T(y + 9), en, serif, 6.5)
        signature(c, x + 34, T(y + 6), 46, 11, rng)
    draw_text(c, 396, T(y + 37), f"报告日期 Date of Issue：{f['issue_date']}", cjk, 9)
    round_seal(c, 481 + rng.uniform(-8, 8), T(y + 20) + rng.uniform(-6, 6), 45, FIXED["seal_top"],
               FIXED["seal_bottom"], d["seal_code"], rng)

    # ── 바닥글 ────────────────────────────────────────────────
    y = 787
    c.setStrokeColor(ink)
    c.setLineWidth(0.5)
    c.line(43, T(y), 552, T(y))
    c.setFillColor(ink)
    draw_text(c, 43, T(y + 10), FIXED["address_cn"], cjk, 7)
    draw_text(c, 43, T(y + 22), FIXED["address_en"], serif, 7)
    draw_text(c, 552, T(y + 10), f"Tel：{FIXED['tel']}", cjk, 7, "right")
    draw_text(c, 552, T(y + 22), f"Fax：{FIXED['fax']}　{FIXED['email']}", cjk, 7, "right")
    draw_text(c, 552, T(PAGE_H - 12), "SYNTHETIC TEST DOCUMENT · fictitious company · for AI training only",
              sans, 5, "right", hexcolor("#9a9a9a"))
    c.showPage()
    c.save()


def main():
    run(sys.modules[__name__], "양식 B (중국 정제사 检验报告单) 가상 CoA 생성기", "output_B")


if __name__ == "__main__":
    main()
