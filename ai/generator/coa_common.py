# -*- coding: utf-8 -*-
"""
CoA 생성기 공통 모듈 v2 (gen_A.py / gen_B.py / gen_D.py 가 함께 씀)
===================================================================
원자재: 탄산리튬 Li2CO3 배터리급(기본) 또는 수산화리튬 일수화물 LiOH·H2O 배터리급(--material lioh).
회사·사람·주소는 모두 가상.

이 파일에 들어 있는 것
  1. 원자재별 사내 규격 DB (Sydco 수입검사 규격, 가상)   --material 로 고름
       - lioh   : coa3/coa_data.py, coa_generators/ (v1) 의 SPEC_DB 와 같은 값
       - li2co3 : YS/T 582-2023 · Chengxin · Nanotrun · Century Lithium · Thermo Fisher 값으로 잡은 범위 (sources.md)
  2. 값 만들기: 정상 / 한계 근접 / 사내만 불합격(숨은 불합격) / 협력사까지 불합격
  4. 예외 주입: 사유코드 12종 (BOUND_ABOVE_LIMIT, ND_NO_LOD, ... ) 을 문서 1장에 여러 개 섞을 수 있음, 로트 권고 판정
  5. PDF 그리기 도우미: 글꼴 찾기, 아래·위 첨자, 서명, 도장
  6. 입고 정보(receipts.csv), 개발용/평가용 분할, 정답 라벨 저장
  7. 실행 옵션과 전체 흐름 run()   (열화본은 coa_degrade.py)

각 양식 프로그램은 '양식별 항목표', '머리글 만들기', '그리는 함수'만 따로 가지고, 나머지는 여기서 가져다 쓴다.
"""

import calendar
import csv
import json
import math
import os
import random
import re
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

# =============================================================================
# 1. 원자재별 사내 규격 DB (표준 단위: 함량·탄산·수분 %, 불순물 ppm, 자성이물 ppb, 입도 μm)
#    typical = 정상 로트에서 흔히 나오는 값 (최소, 최대, 최빈)    lod = 검출한계(표준 단위)
#    src     = 값 범위 근거 (sources.md 의 번호)
# =============================================================================

# ── 수산화리튬 일수화물 (v1 과 같은 값) ─────────────────────────────────────────
SPEC_DB_LIOH = [
    dict(id="appearance", name="Appearance", unit="-", type="qualitative",
         spec="White crystalline powder, free of visible foreign matter"),
    dict(id="lioh", name="LiOH content", unit="%", lsl=56.5, usl=57.5, typical=(56.62, 57.32, 56.95), impurity=False),
    dict(id="co3", name="Carbonate (CO3)", unit="%", usl=0.35, typical=(0.08, 0.30, 0.17)),
    dict(id="na", name="Sodium (Na)", unit="ppm", usl=30, typical=(4, 24, 11)),
    dict(id="k", name="Potassium (K)", unit="ppm", usl=20, typical=(1.0, 12, 4)),
    dict(id="ca", name="Calcium (Ca)", unit="ppm", usl=15, typical=(2, 12, 6)),
    dict(id="mg", name="Magnesium (Mg)", unit="ppm", usl=10, typical=(0.3, 6, 1.8), lod=0.2),
    dict(id="fe", name="Iron (Fe)", unit="ppm", usl=5, typical=(0.3, 3.5, 1.4), lod=0.2),
    dict(id="cu", name="Copper (Cu)", unit="ppm", usl=1, typical=(0.03, 0.6, 0.15), lod=0.1),
    dict(id="mn", name="Manganese (Mn)", unit="ppm", usl=5, typical=(0.1, 3.0, 0.6), lod=0.2),
    dict(id="si", name="Silicon (Si)", unit="ppm", usl=30, typical=(5, 25, 12)),
    dict(id="cl", name="Chloride (Cl)", unit="ppm", usl=20, typical=(3, 15, 7)),
    dict(id="so4", name="Sulfate (SO4)", unit="ppm", usl=80, typical=(15, 62, 34)),
    dict(id="mag", name="Magnetic impurities", unit="ppb", usl=50, typical=(6, 36, 17), lod=5),
    dict(id="d50", name="Particle size D50", unit="μm", lsl=5.0, usl=15.0, typical=(7.0, 13.0, 9.8), impurity=False),
]
REF_LIOH = {
    "boron": dict(name="Boron (B)", unit="ppm", typical=(2, 18, 6)),
    "acid_insol": dict(name="Acid insoluble matter", unit="ppm", typical=(5, 30, 12)),
    "ni": dict(name="Nickel (Ni)", unit="ppm", typical=(0.2, 3.0, 0.8), lod=0.5),
    "cr": dict(name="Chromium (Cr)", unit="ppm", typical=(0.1, 1.5, 0.4), lod=0.2),
    "zn": dict(name="Zinc (Zn)", unit="ppm", typical=(0.3, 4.0, 1.2), lod=0.5),
    "d10": dict(name="Particle size D10", unit="μm", typical=(2.0, 4.2, 3.0), impurity=False),
    "d90": dict(name="Particle size D90", unit="μm", typical=(18, 30, 23), impurity=False),
}

# ── 탄산리튬 (배터리급, 미분형) ──────────────────────────────────────────────────
#   사내 한도: YS/T 582-2023 D1 급(협력사 규격 수준)보다 엄격하게, 공개 자료 중 엄격한 편인 Chengxin 규격 근처로 잡음
#   typical : Nanotrun 배터리급 시험값, Century Lithium 파일럿 결과, Thermo Fisher 앱노트 실측값을 보고 잡은 범위
SPEC_DB_LI2CO3 = [
    dict(id="appearance", name="Appearance", unit="-", type="qualitative",
         spec="White powder, free of visible foreign matter"),
    # 주성분: 하한만 있음. YS/T ≥99.5, Chengxin ≥99.60, Nanotrun 99.68, Century 99.875
    dict(id="li2co3", name="Li2CO3 content", unit="%", lsl=99.6, typical=(99.63, 99.93, 99.76), impurity=False,
         src="L1 L2 L3 L5"),
    # Na: YS/T 250 / Chengxin 200 ppm.  Nanotrun 62, Thermo(99 % 급) 132, Century 파일럿 470
    dict(id="na", name="Sodium (Na)", unit="ppm", usl=200, typical=(25, 170, 70), src="L1 L2 L3 L4 L5"),
    # K: YS/T 50(Nanotrun 표기) / Chengxin 5.  Nanotrun <1, Thermo 0.9
    dict(id="k", name="Potassium (K)", unit="ppm", usl=10, typical=(0.4, 8, 1.8), lod=0.5, src="L1 L2 L3 L4"),
    # Ca: YS/T 80 / Chengxin 40.  Nanotrun 16, Century 90, Thermo 115(99 % 급)
    dict(id="ca", name="Calcium (Ca)", unit="ppm", usl=50, typical=(5, 42, 16), src="L1 L2 L3 L4 L5"),
    # Mg: YS/T 80 / Chengxin 60.  Nanotrun 2, Thermo 6.6
    dict(id="mg", name="Magnesium (Mg)", unit="ppm", usl=60, typical=(0.8, 45, 7), lod=1, src="L1 L2 L3 L4"),
    # Fe: YS/T 10 / Chengxin 5.  Century 3, Thermo 1.4, Nanotrun <1
    dict(id="fe", name="Iron (Fe)", unit="ppm", usl=5, typical=(0.3, 4.0, 1.4), lod=0.5, src="L1 L2 L3 L4 L5"),
    dict(id="cu", name="Copper (Cu)", unit="ppm", usl=3, typical=(0.05, 2.0, 0.3), lod=0.3, src="L1 L2 L3"),
    dict(id="mn", name="Manganese (Mn)", unit="ppm", usl=3, typical=(0.05, 2.0, 0.3), lod=0.2, src="L1 L2 L3 L4"),
    # Si: YS/T 30 / Chengxin 20.  Nanotrun 2, Thermo 113(99 % 급)
    dict(id="si", name="Silicon (Si)", unit="ppm", usl=20, typical=(1, 17, 5), src="L1 L2 L3 L4"),
    # SO4: YS/T 800 / Chengxin 800.  Nanotrun 416
    dict(id="so4", name="Sulfate (SO4)", unit="ppm", usl=600, typical=(120, 520, 330), src="L1 L2 L3"),
    # Cl: YS/T 50(Nanotrun 표기) / Chengxin 20.  Nanotrun 15, Century 80
    dict(id="cl", name="Chloride (Cl)", unit="ppm", usl=30, typical=(4, 26, 13), src="L1 L2 L3 L5"),
    # 수분: YS/T 0.25 %.  Nanotrun 0.12, Century 0.03
    dict(id="h2o", name="Moisture (H2O)", unit="%", usl=0.20, typical=(0.03, 0.17, 0.09), impurity=False,
         src="L1 L2 L3 L5"),
    # 자성이물: YS/T 300 / Chengxin 150 ppb.  Nanotrun 31
    dict(id="mag", name="Magnetic impurities", unit="ppb", usl=150, typical=(8, 120, 35), lod=5, src="L1 L2 L3"),
    # D50: YS/T 5.5±2.5 (3–8) / Chengxin 5.0–8.0.  Nanotrun 6
    dict(id="d50", name="Particle size D50", unit="μm", lsl=4.0, usl=8.0, typical=(4.6, 7.4, 6.0), impurity=False,
         src="L1 L2 L3"),
]
REF_LI2CO3 = {
    "boron": dict(name="Boron (B)", unit="ppm", typical=(0.5, 15, 3), lod=1),
    "ni": dict(name="Nickel (Ni)", unit="ppm", typical=(0.1, 3.0, 0.6), lod=0.5),
    "cr": dict(name="Chromium (Cr)", unit="ppm", typical=(0.05, 0.8, 0.2), lod=0.2),
    "zn": dict(name="Zinc (Zn)", unit="ppm", typical=(0.1, 2.0, 0.5), lod=0.3),
    "al": dict(name="Aluminium (Al)", unit="ppm", typical=(0.5, 7.0, 2.0), lod=0.5),
    "d10": dict(name="Particle size D10", unit="μm", typical=(1.4, 3.0, 2.1), impurity=False),
    "d90": dict(name="Particle size D90", unit="μm", typical=(10, 15.5, 12.5), impurity=False),
}

MATERIALS = {
    "li2co3": dict(key="li2co3", name="Li2CO3 Battery Grade", name_kr="탄산리튬 (배터리급)", main="li2co3",
                   spec_id="SYD-QS-LC-BG v1", spec_db=SPEC_DB_LI2CO3, ref_items=REF_LI2CO3),
    "lioh": dict(key="lioh", name="LiOH·H2O Battery Grade", name_kr="수산화리튬 일수화물 (배터리급)", main="lioh",
                 spec_id="SYD-QS-LHM-BG v1", spec_db=SPEC_DB_LIOH, ref_items=REF_LIOH),
}

# 지금 고른 원자재의 규격. set_material() 이 '안의 내용만' 바꾸므로 from coa_common import SPEC 해 둔 이름도 같이 바뀐다
MATERIAL = dict(MATERIALS["li2co3"])
SPEC_DB = list(SPEC_DB_LI2CO3)
SPEC = {s["id"]: s for s in SPEC_DB}
REF_ITEMS = dict(REF_LI2CO3)


def set_material(key):
    m = MATERIALS[key]
    MATERIAL.clear()
    MATERIAL.update(m)
    SPEC_DB[:] = m["spec_db"]
    SPEC.clear()
    SPEC.update({s["id"]: s for s in SPEC_DB})
    REF_ITEMS.clear()
    REF_ITEMS.update(m["ref_items"])


# 문서 단위 -> 표준 단위 배율.  예) 0.0018 % x 10000 = 18 ppm
UNIT_TO_STD = {
    ("%", "%"): 1, ("% w/w", "%"): 1, ("%", "ppm"): 10000, ("ppm", "ppm"): 1, ("mg/kg", "ppm"): 1,
    ("ppb", "ppb"): 1, ("μg/kg", "ppb"): 1, ("μm", "μm"): 1, ("µm", "μm"): 1,
}

# 산화물 기준 표기 -> 원소 기준 환산 배율 (원소 = 산화물 x factor).  (평문, 첨자 표기, 중국어, 배율)
OXIDES = {
    "na": ("Na2O", "Na_{2}O", "氧化钠", 0.7419),
    "k": ("K2O", "K_{2}O", "氧化钾", 0.8301),
    "ca": ("CaO", "CaO", "氧化钙", 0.7147),
    "mg": ("MgO", "MgO", "氧化镁", 0.6031),
    "fe": ("Fe2O3", "Fe_{2}O_{3}", "氧化铁", 0.6994),
}

CUSTOMER = "Sydco Co., Ltd."     # 납품처 = 우리 회사
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

NEAR_LIMIT_RATE = 0.04               # 항목별로 '합격이지만 사내 한계에 바짝 붙은 값'이 나올 확률
FAIL_ITEM_COUNT_WEIGHTS = {1: 7, 2: 3}   # OUT_OF_SPEC 이 걸린 CoA 의 불합격 항목 수 비율 (1개 70 %, 2개 30 %)


# =============================================================================
# 2. 날짜 · 단위 도우미
# =============================================================================

def fmt_date(d, fmt):
    """fmt 예: '{d:02d}-{mon}-{y}' / '{y}-{m:02d}-{d:02d}' / '{m:02d}/{d:02d}/{y}'"""
    return fmt.format(d=d.day, m=d.month, y=d.year, mon=MONTHS[d.month - 1])


def add_months(d, months):
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def std_unit(item_id):
    if item_id == "appearance":
        return "-"
    if item_id in SPEC:
        return SPEC[item_id]["unit"]
    if item_id in REF_ITEMS:
        return REF_ITEMS[item_id]["unit"]
    return "ppm"


def factor(it):
    """표준 단위 값 x factor = 문서 단위 값"""
    return 1.0 / UNIT_TO_STD[(it["unit"], std_unit(it.get("std_of", it["id"])))]


def within(v, lsl, usl):
    return (lsl is None or v >= lsl - 1e-9) and (usl is None or v <= usl + 1e-9)


def fmt_num(x):
    """1.50 -> '1.5', 20.0 -> '20', 0.00340 -> '0.0034'"""
    return f"{x:.8f}".rstrip("0").rstrip(".")


def nice(x, up=False, sig=2):
    """유효숫자 sig 자리로 깔끔하게.  up=True 면 올림"""
    if x <= 0:
        return x
    p = 10 ** (math.floor(math.log10(x)) - sig + 1)
    return round((math.ceil(x / p - 1e-9) if up else round(x / p)) * p, 10)


def make_dates(rng, start, end, shelf_months):
    """제조일·시험일·발행일 등 한 로트의 날짜 묶음"""
    mfg = start + timedelta(days=rng.randint(0, (end - start).days))
    test = mfg + timedelta(days=rng.randint(1, 3))
    issue = test + timedelta(days=rng.randint(0, 2))
    return dict(mfg=mfg, test=test, issue=issue, printed=issue + timedelta(days=rng.randint(0, 3)),
                expiry=add_months(mfg, shelf_months))


class Seq:
    """문서 번호·로트 번호를 날짜순으로 조금씩 늘려 가는 카운터"""

    def __init__(self, rng):
        self.rng, self.c = rng, Counter()

    def next(self, k, first=(1, 9), step=(1, 3)):
        self.c[k] = self.c[k] + self.rng.randint(*step) if k in self.c else self.rng.randint(*first)
        return self.c[k]


# =============================================================================
# 3. 값 만들기 · 판정
#    case: normal(정상) / near_limit(한계 근접 합격) / fail_internal(사내만 불합격) / fail_both(협력사도 불합격)
# =============================================================================

def fail_mode(it, allow_both):
    """이 항목을 불합격으로 만들 수 있는 방법.  internal_only = 협력사 규격은 통과하고 사내 규격만 벗어남"""
    s = SPEC.get(it["id"])
    if not s:
        return None
    if s.get("type") == "qualitative":
        return "both" if allow_both else None
    hi_gap = s.get("usl") is not None and it.get("usl") is not None and it["usl"] > s["usl"] * 1.05
    lo_gap = s.get("lsl") is not None and it.get("lsl") is not None and it["lsl"] < s["lsl"] - 1e-9
    if hi_gap or lo_gap:
        return "internal_only"
    return "both" if allow_both else None


def spec_width(lsl, usl):
    """규격 폭.  상한만 있으면 0 ~ 상한, 하한만 있으면 하한의 1 % (순도 99.6 % 같은 하한 규격용)"""
    if lsl is not None and usl is not None:
        return usl - lsl
    return usl if usl is not None else lsl * 0.01


def gen_value(it, case, level, rng):
    """표준 단위 값 하나를 뽑는다"""
    s = SPEC.get(it["id"]) or REF_ITEMS[it["id"]]
    lo, hi, mode = s["typical"]
    lsl, usl = s.get("lsl"), s.get("usl")
    w = spec_width(lsl, usl) if (lsl is not None or usl is not None) else None
    if case == "normal":
        v = rng.triangular(lo, hi, mode)
        if s.get("impurity", True):
            v *= level
        if usl is not None:
            v = min(v, usl * 0.93 if lsl is None else usl - 0.05 * w)
        if lsl is not None:
            v = max(v, lsl + 0.05 * w)
        return v
    if case == "near_limit":
        if lsl is not None and (usl is None or rng.random() < 0.4):
            return lsl + w * rng.uniform(0.005, 0.04)
        return usl * rng.uniform(0.88, 0.985) if lsl is None else usl - w * rng.uniform(0.005, 0.04)
    sup_lsl, sup_usl = it.get("lsl"), it.get("usl")
    if case == "fail_internal":
        sides = []
        if usl is not None and sup_usl is not None and sup_usl > usl * 1.05:
            sides.append("hi")
        if lsl is not None and sup_lsl is not None and sup_lsl < lsl - 1e-9:
            sides.append("lo")
        if rng.choice(sides) == "hi":
            return usl + (sup_usl - usl) * rng.uniform(0.12, 0.92)
        return sup_lsl + (lsl - sup_lsl) * rng.uniform(0.08, 0.88)
    # fail_both
    if lsl is not None and (usl is None or rng.random() < 0.5):
        base = min(lsl, sup_lsl if sup_lsl is not None else lsl)
        return base - min(w, base) * rng.uniform(0.05, 0.35)
    base = max(usl, sup_usl if sup_usl is not None else usl)
    return base * rng.uniform(1.08, 1.6) if lsl is None else base + w * rng.uniform(0.05, 0.35)


def number_text(it, v_std):
    """표준 단위 값 -> (문서에 찍을 숫자 글자, 반올림된 표준 단위 값)"""
    f, dec = factor(it), it["dec"]
    disp = round(v_std * f, dec)
    return f"{disp:.{dec}f}", round(disp / f, 9)


def deviation(v, s):
    lsl, usl = s.get("lsl"), s.get("usl")
    dev, lim = (v - usl, usl) if usl is not None and v > usl else (lsl - v, lsl)
    return round(dev, 6), round(dev / lim * 100, 2)


def make_item(it, case, level, rng, words):
    """
    시험 항목 한 줄의 값과 정답을 만든다.
    words: 양식별 표기 -> dict(appearance_pass=[...], appearance_fail='...', value='{t} {u}', lod='< {t} {u}')
    """
    iid = it["id"]
    s = SPEC.get(iid)
    row = dict(item_id=iid, it=it, ref=s is None, printed_name=it.get("plain") or plain(it["label"]),
               method=it.get("method", ""), unit=it["unit"], spec=it["spec"], case=case, below_lod=False,
               value_std=None, unit_std=std_unit(iid), sup_lsl=it.get("lsl"), sup_usl=it.get("usl"),
               int_lsl=(s or {}).get("lsl"), int_usl=(s or {}).get("usl"), bound=None, note="")

    if iid == "appearance":
        bad = case.startswith("fail")
        row["number"] = None
        row["result"] = words["appearance_fail"] if bad else rng.choice(words["appearance_pass"])
        row["supplier"] = row["internal"] = "FAIL" if bad else "PASS"
        row.update(value_type="text", expected=row["internal"], reason="OUT_OF_SPEC" if bad else "OK")
        return row

    want = {"normal": (True, True), "near_limit": (True, True),
            "fail_internal": (True, False), "fail_both": (False, False)}[case]
    lod = (s or REF_ITEMS.get(iid, {})).get("lod")
    for _ in range(60):                  # 반올림 때문에 판정이 뒤집히면 다시 뽑는다
        v = max(gen_value(it, case, level, rng), 1e-6)
        if lod is not None and v < lod and case == "normal":
            text, _ = number_text(it, lod)
            row.update(below_lod=True, bound=lod, number=text, result=words["lod"].format(t=text, u=it["unit"]))
            sup_ok, int_ok = True, True
            break
        text, v_std = number_text(it, v)
        sup_ok = within(v_std, it.get("lsl"), it.get("usl"))
        int_ok = within(v_std, s.get("lsl"), s.get("usl")) if s else None
        if float(text) > 0 and (sup_ok, int_ok) == (want if s else (True, None)):
            row.update(value_std=v_std, number=text, result=words["value"].format(t=text, u=it["unit"]))
            break
    else:
        raise RuntimeError(f"값 생성 실패: {iid} {case}")

    no_spec = it.get("lsl") is None and it.get("usl") is None
    row["supplier"] = "REF" if no_spec else ("PASS" if sup_ok else "FAIL")
    row["internal"] = "REF" if s is None else ("PASS" if int_ok else "FAIL")
    row["value_type"] = "bound" if row["below_lod"] else "exact"
    row["expected"] = row["internal"]
    row["reason"] = {"FAIL": "OUT_OF_SPEC", "REF": "REF"}.get(row["internal"],
                                                             "BOUND_WITHIN_LIMIT" if row["below_lod"] else "OK")
    if row["internal"] == "FAIL":
        row["deviation_std"], row["deviation_pct"] = deviation(row["value_std"], s)
    elif row["internal"] == "PASS" and not row["below_lod"]:
        lsl, usl = s.get("lsl"), s.get("usl")
        gaps = [g for g in ((usl - row["value_std"]) if usl is not None else None,
                            (row["value_std"] - lsl) if lsl is not None else None) if g is not None]
        width = spec_width(lsl, usl)
        if min(gaps) / width < 0.05:
            row["note"] = f"사내 한계 근접 (여유 {min(gaps) / width * 100:.1f}%)"
    return row


def pick_fails(items, rng, allow_both):
    """OUT_OF_SPEC(숨은 불합격) 으로 만들 항목 1~2개 -> {item_id: case}"""
    fails = {}
    pool = [it for it in items if fail_mode(it, allow_both)]
    k = rng.choices(list(FAIL_ITEM_COUNT_WEIGHTS), weights=list(FAIL_ITEM_COUNT_WEIGHTS.values()))[0]
    weights = [0.3 if it["id"] == "appearance" else 1.0 for it in pool]
    while pool and len(fails) < min(k, len(pool)):
        it = rng.choices(pool, weights=weights)[0]
        mode = fail_mode(it, allow_both)
        if allow_both and mode == "internal_only" and rng.random() < 0.3:
            mode = "both"
        fails[it["id"]] = "fail_both" if mode == "both" else "fail_internal"
    return fails


def make_results(items, rng, fails, level, words):
    """CoA 한 장의 시험 결과 전체.  fails = {item_id: 'fail_internal' | 'fail_both'}"""
    rows = []
    for n, it in enumerate(items, 1):
        if it["id"] in fails:
            case = fails[it["id"]]
        elif it["id"] in SPEC and it["id"] != "appearance" and rng.random() < NEAR_LIMIT_RATE:
            case = "near_limit"
        else:
            case = "normal"
        r = make_item(it, case, level, rng, words)
        r["row"] = n
        rows.append(r)
    return rows


# =============================================================================
# 4. 예외 주입 (사유코드)
#    정상으로 만든 결과표에서 사유코드에 해당하는 칸만 바꾼다. 한 장에 여러 코드를 섞을 수 있다.
#    항목 판정 정답(expected): PASS 적합 · FAIL 부적합 · INDETERMINATE 판정 불가 · CHECK 확인 필요 · MISSING 누락 · REF 참고
# =============================================================================

REASONS = {
    # 기존 (v1) 숨은 불합격
    "OUT_OF_SPEC": "표준 단위 값이 사내 규격 밖 (숨은 불합격: 협력사 규격으로는 합격. A 양식은 협력사 규격까지 벗어나기도 함)",
    # 멘토 피드백 10.12 추가 요청
    "BOUND_ABOVE_LIMIT": "'< X' 결과인데 X 가 사내 상한보다 큼 (예: '<20', 사내 상한 5) -> 실제 값이 상한 초과인지 알 수 없음",
    "ND_NO_LOD": "'N.D.' 로만 적혀 있고 검출한계(LOD) 값이 없음 -> 사내 상한 이하인지 확인 필요",
    "ND_WITH_LOD": "'N.D. (LOD 2 ppm)' 처럼 검출한계가 적혀 있음 -> LOD ≤ 사내 상한이면 적합, 크면 판정 불가",
    "SPEC_COPIED": "결과 칸에 측정값 대신 규격 문구가 그대로 적혀 있음 (예: '≤ 50 ppm')",
    "MISSING_REQUIRED": "사내 규격 필수 항목(Mg, 자성이물 등) 줄이 CoA 에 없음",
    "CONVERTED_OOS": "산화물 기준 표기(예: Na₂O 0.04 %) -> 원소 기준으로 환산하면 사내 규격 초과",
    "SUM_ONLY": "Na+K 합산값만 있음 -> 개별 원소로 임의로 나누지 않음. 합이 원소 상한 이하인 원소만 적합 확정",
    "AMBIGUOUS_ANALYTE": "'Heavy metals (as Pb)' 처럼 대상 원소가 모호한 항목이 Cu 줄 대신 있음 -> Cu 판정 불가",
    "DATE_CONFLICT": "날짜 논리 충돌: 발행일이 시험일(A 양식은 제조일)보다 이름, 또는 입고일에 유효기한(재시험일)이 이미 지남",
    "LOT_MISMATCH": "CoA 로트 번호와 입고 등록 로트 번호가 다름 (receipts.csv)",
    "MATERIAL_MISMATCH": "입고 등록 원자재와 CoA 원자재가 다름 (예: 탄산리튬 입고에 수산화리튬 CoA)",
}
# 사유코드별 기본 생성 비율 (예외 문서 안에서의 상대 가중치).  --reason-weights 로 바꿀 수 있다
DEFAULT_REASON_WEIGHTS = {
    "OUT_OF_SPEC": 3, "BOUND_ABOVE_LIMIT": 1, "ND_NO_LOD": 1, "ND_WITH_LOD": 1, "SPEC_COPIED": 1,
    "MISSING_REQUIRED": 1, "CONVERTED_OOS": 1, "SUM_ONLY": 1, "AMBIGUOUS_ANALYTE": 1, "DATE_CONFLICT": 1,
    "LOT_MISMATCH": 0.5, "MATERIAL_MISMATCH": 0.5,
}
# 예외 문서 1장에 섞는 사유코드 수 비율 (1개 65 %, 2개 25 %, 3개 10 %).  --mix-weights 로 바꿀 수 있다
DEFAULT_MIX_WEIGHTS = {1: 65, 2: 25, 3: 10}
ITEM_STATUS = {"PASS": "적합", "FAIL": "부적합", "INDETERMINATE": "판정 불가", "CHECK": "확인 필요",
               "MISSING": "누락", "REF": "참고(사내 규격 없음)"}
LOT_REC = {"ACCEPT": "적합 권고", "REJECT": "부적합 권고", "HOLD": "보류 권고"}
LOT_RULE = ("FAIL 이 하나라도 있으면 부적합 권고 > 판정 불가·확인 필요·누락·문서/입고 정합성 오류가 있으면 보류 권고 > "
            "그 밖에는 적합 권고. 최종 처분은 담당자가 한다.")
QUIET_REASONS = {"OK", "REF", "BOUND_WITHIN_LIMIT"}

# 여기에 있는 항목은 결과 칸을 바꾸는 예외의 대상에서 뺀다 (주성분·외관·입도는 'ppm 불순물' 성격이 아님)
NOT_TRACE = {"appearance", "lioh", "li2co3", "co3", "h2o", "d50"}


def row_of(d, iid):
    return next((r for r in d["rows"] if r["item_id"] == iid), None)


def renumber(d):
    for n, r in enumerate(d["rows"], 1):
        r["row"] = n


def trace_rows(d, used, need_usl=True, need_lod=False):
    """결과 칸을 바꿀 수 있는 불순물 줄.  need_lod=True 면 검출한계가 있는 미량 항목만 ('N.D.', '<X' 가 자연스러운 항목)"""
    return [r for r in d["rows"] if r["item_id"] in SPEC and r["item_id"] not in NOT_TRACE
            and r["item_id"] not in used and (not need_usl or SPEC[r["item_id"]].get("usl") is not None)
            and (not need_lod or SPEC[r["item_id"]].get("lod") is not None)]


def choose(rng, rows, prefer=(), w_pref=3.0):
    if not rows:
        return None
    return rng.choices(rows, weights=[w_pref if r["item_id"] in prefer else 1.0 for r in rows])[0]


def set_special(r, result, value_type, expected, reason, note="", value_std=None, bound=None):
    r.update(result=result, value_type=value_type, expected=expected, reason=reason, note=note,
             value_std=value_std, bound=bound, below_lod=value_type in ("bound", "nd"), supplier="PASS",
             deviation_std=None, deviation_pct=None, internal=expected, case="exception")


def x_bound_above(d, mod, rng, used):
    r = choose(rng, trace_rows(d, used, need_lod=True), prefer={"fe", "cu"})
    if not r:
        return False
    s, it = SPEC[r["item_id"]], r["it"]
    f = factor(it)
    x_doc = nice(s["usl"] * rng.uniform(1.6, 4.0) * f, sig=1)
    x_std = round(x_doc / f, 9)
    set_special(r, mod.WORDS["lod"].format(t=fmt_num(x_doc), u=it["unit"]), "bound", "INDETERMINATE",
                "BOUND_ABOVE_LIMIT", f"보고한계 {fmt_num(x_std)} {s['unit']} > 사내 상한 {fmt_num(s['usl'])} {s['unit']}",
                bound=x_std)
    used.add(r["item_id"])
    return True


def x_nd_no_lod(d, mod, rng, used):
    r = choose(rng, trace_rows(d, used, need_lod=True), prefer={"fe", "cu"})
    if not r:
        return False
    set_special(r, mod.WORDS["nd"], "nd", "CHECK", "ND_NO_LOD",
                f"검출한계 값 없음 -> 사내 상한 {fmt_num(SPEC[r['item_id']]['usl'])} 이하인지 확인 불가")
    used.add(r["item_id"])
    return True


def x_nd_with_lod(d, mod, rng, used):
    r = choose(rng, trace_rows(d, used, need_lod=True), prefer={"fe", "cu"})
    if not r:
        return False
    s, it = SPEC[r["item_id"]], r["it"]
    f = factor(it)
    above = rng.random() < 0.3                     # 30 % 는 LOD 가 사내 상한보다 커서 판정 불가
    x_doc = nice(s["usl"] * (rng.uniform(1.5, 3.0) if above else rng.uniform(0.1, 0.6)) * f, sig=1)
    x_std = round(x_doc / f, 9)
    above = x_std > s["usl"] + 1e-9
    set_special(r, mod.WORDS["nd_lod"].format(t=fmt_num(x_doc), u=it["unit"]), "nd",
                "INDETERMINATE" if above else "PASS", "ND_WITH_LOD",
                f"LOD {fmt_num(x_std)} {s['unit']} {'>' if above else '≤'} 사내 상한 {fmt_num(s['usl'])} {s['unit']}",
                bound=x_std)
    used.add(r["item_id"])
    return True


def x_spec_copied(d, mod, rng, used):
    r = choose(rng, trace_rows(d, used), prefer={"na", "ca", "si", "so4", "cl"})
    if not r:
        return False
    sup = r["sup_usl"]
    s = SPEC[r["item_id"]]
    note = "결과 = 규격 문구. 실측값 아님"
    if sup is not None and sup > s["usl"]:
        note += f" (그 값 {fmt_num(sup)} 이면 사내 상한 {fmt_num(s['usl'])} 초과)"
    set_special(r, r["spec"], "spec_like", "CHECK", "SPEC_COPIED", note)
    used.add(r["item_id"])
    return True


def x_missing(d, mod, rng, used):
    rows = [r for r in d["rows"] if r["item_id"] in SPEC and r["item_id"] not in used
            and r["item_id"] not in ("appearance", MATERIAL["main"])]
    r = choose(rng, rows, prefer={"mg", "mag"}, w_pref=5.0)
    if not r:
        return False
    iid = r["item_id"]
    d["rows"].remove(r)
    renumber(d)
    d["extra"].append(dict(row=None, item_id=iid, printed_name="", method="", unit="", spec="", result="",
                           value_type="missing", value_std=None, unit_std=std_unit(iid), supplier="",
                           expected="MISSING", internal="MISSING", reason="MISSING_REQUIRED",
                           note=f"{SPEC[iid]['name']} 줄 없음", int_lsl=SPEC[iid].get("lsl"),
                           int_usl=SPEC[iid].get("usl"), case="exception"))
    used.add(iid)
    return True


def x_converted(d, mod, rng, used):
    rows = [r for r in d["rows"] if r["item_id"] in OXIDES and r["item_id"] not in used and r["value_type"] == "exact"]
    if not rows:
        return False
    gap = [r for r in rows if r["sup_usl"] is not None and r["sup_usl"] > SPEC[r["item_id"]]["usl"] * 1.1]
    r = rng.choice(gap or rows)
    iid, it, s = r["item_id"], r["it"], SPEC[r["item_id"]]
    ox, ox_rich, ox_cn, k = OXIDES[iid]
    usl = s["usl"]
    sup = r["sup_usl"] if r["sup_usl"] is not None else usl * 1.5
    for _ in range(60):
        v_el = usl + (sup - usl) * rng.uniform(0.2, 0.9) if sup > usl * 1.1 else usl * rng.uniform(1.15, 1.6)
        text, ox_std = number_text(it, v_el / k)          # 문서에는 산화물 값이 찍힌다
        v_el = round(ox_std * k, 4)
        if v_el > usl + 1e-9 and float(text) > 0:
            break
    new_it = mod.relabel(it, "oxide", (ox, ox_rich, ox_cn))
    new_it.update(mod.make_spec(new_it, nice(sup / k, up=True)))
    dev_std, dev_pct = deviation(v_el, s)
    r.update(it=new_it, printed_name=new_it.get("plain") or plain(new_it["label"]), spec=new_it["spec"],
             method=new_it.get("method", ""),
             result=mod.WORDS["value"].format(t=text, u=it["unit"]), number=text, value_type="exact",
             below_lod=False, value_std=v_el, basis=ox, value_doc_std=ox_std, expected="FAIL", internal="FAIL",
             supplier="PASS", reason="CONVERTED_OOS", deviation_std=dev_std, deviation_pct=dev_pct, case="exception",
             note=f"{ox} {fmt_num(ox_std)} {s['unit']} x {k} = {iid.capitalize()} {fmt_num(v_el)} {s['unit']} "
                  f"> 사내 상한 {fmt_num(usl)}")
    used.add(iid)
    return True


def x_sum_only(d, mod, rng, used):
    na, kk = row_of(d, "na"), row_of(d, "k")
    if not na or not kk or {"na", "k"} & used:
        return False
    usl_na, usl_k = SPEC["na"]["usl"], SPEC["k"]["usl"]
    vals = [r["value_std"] if r["value_std"] is not None else (r.get("bound") or 0) for r in (na, kk)]
    total = sum(vals)
    lo = min(usl_na, usl_k)
    sup_sum = (na["sup_usl"] or usl_na * 1.5) + (kk["sup_usl"] or usl_k * 1.5)
    if total <= lo:                       # 합이 너무 작으면 둘 다 확정 적합이라 예외가 안 됨 -> 한쪽 상한을 넘게
        total = lo * rng.uniform(1.15, 1.8)
    it = na["it"]
    for _ in range(60):
        text, t_std = number_text(it, min(total, sup_sum * 0.95))
        if t_std > lo:
            break
        total *= 1.1
    new_it = mod.relabel(it, "combined")
    new_it.update(mod.make_spec(new_it, sup_sum))
    comp = {i: ("PASS" if t_std <= SPEC[i]["usl"] + 1e-9 else "CHECK") for i in ("na", "k")}
    d["rows"].remove(kk)
    renumber(d)
    na.update(it=new_it, item_id="na_k", printed_name=new_it.get("plain") or plain(new_it["label"]),
              spec=new_it["spec"], result=mod.WORDS["value"].format(t=text, u=it["unit"]), number=text,
              value_type="combined", below_lod=False, value_std=t_std, expected="CHECK", internal="CHECK",
              supplier="PASS", reason="SUM_ONLY", deviation_std=None, deviation_pct=None, case="exception",
              int_lsl=None, int_usl=None, note=f"Na+K = {fmt_num(t_std)} ppm. 개별 값은 알 수 없음")
    for i in ("na", "k"):
        d["extra"].append(dict(row=None, item_id=i, printed_name="(Na+K 줄에서 유도)", method="", unit="", spec="",
                               result="", value_type="derived", value_std=None, unit_std="ppm", supplier="",
                               expected=comp[i], internal=comp[i], reason="SUM_ONLY",
                               note=f"Na+K {fmt_num(t_std)} {'≤' if comp[i] == 'PASS' else '>'} {i.upper() if i == 'k' else 'Na'} "
                                    f"사내 상한 {fmt_num(SPEC[i]['usl'])} -> {'적합 확정' if comp[i] == 'PASS' else '확인 필요'}",
                               int_lsl=None, int_usl=SPEC[i]["usl"], case="exception"))
    used.update({"na", "k"})
    return True


def x_ambiguous(d, mod, rng, used):
    cu = row_of(d, "cu")
    if not cu or "cu" in used:
        return False
    it, usl = cu["it"], SPEC["cu"]["usl"]
    spec_std = max(10.0, usl * 5)
    new_it = mod.relabel(it, "heavy")
    new_it.update(mod.make_spec(new_it, spec_std))
    text, v = number_text(new_it, rng.uniform(usl * 1.5, spec_std * 0.8))
    cu.update(it=new_it, item_id="heavy_metals", printed_name=new_it.get("plain") or plain(new_it["label"]),
              method=new_it.get("method", ""),
              spec=new_it["spec"], result=mod.WORDS["value"].format(t=text, u=it["unit"]), number=text,
              value_type="ambiguous", below_lod=False, value_std=v, expected="CHECK", internal="CHECK",
              supplier="PASS", reason="AMBIGUOUS_ANALYTE", deviation_std=None, deviation_pct=None, case="exception",
              int_lsl=None, int_usl=None, maps_to="cu",
              note=f"중금속(Pb 환산) {fmt_num(v)} ppm. Cu 줄은 없음 -> Cu 값 알 수 없음")
    d["extra"].append(dict(row=None, item_id="cu", printed_name="(Heavy metals 줄로 대체됨)", method="", unit="",
                           spec="", result="", value_type="derived", value_std=None, unit_std="ppm", supplier="",
                           expected="CHECK", internal="CHECK", reason="AMBIGUOUS_ANALYTE",
                           note="Cu 개별 결과 없음. 중금속 총량으로는 Cu 를 판정할 수 없음",
                           int_lsl=None, int_usl=usl, case="exception"))
    used.add("cu")
    return True


def x_date(d, mod, rng, used):
    dt = d["dates"]
    if rng.random() < 0.5:
        anchor_key = getattr(mod, "ISSUE_ANCHOR", "test")
        new = dt[anchor_key] - timedelta(days=rng.randint(1, 5))
        mod.set_issue_date(d, new)
        dt["issue"] = new
        d["doc_notes"].append(f"발행일 {new.isoformat()} < {'제조일' if anchor_key == 'mfg' else '시험일'} "
                              f"{dt[anchor_key].isoformat()}")
        d["date_conflict"] = "issue_before_" + anchor_key
    else:
        d["receipt_after"] = dt["expiry"] + timedelta(days=rng.randint(5, 60))
        d["doc_notes"].append(f"입고일 {d['receipt_after'].isoformat()} > 유효기한(재시험일) {dt['expiry'].isoformat()}")
        d["date_conflict"] = "expired_at_receipt"
    return True


def x_lot(d, mod, rng, used):
    d["receipt_lot"] = swap_lot(d["fields"]["lot_no"], rng)
    d["doc_notes"].append(f"CoA 로트 {d['fields']['lot_no']} ≠ 입고 로트 {d['receipt_lot']}")
    return True


def x_material(d, mod, rng, used):
    other = next(k for k in MATERIALS if k != MATERIAL["key"])
    d["receipt_material"] = MATERIALS[other]
    d["doc_notes"].append(f"입고 원자재 {MATERIALS[other]['name']} ≠ CoA 원자재 {MATERIAL['name']}")
    return True


def swap_lot(lot, rng):
    """로트 번호에서 이웃한 다른 숫자 두 개를 바꾼다 (사람이 옮겨 적다 틀리는 흔한 형태)"""
    pos = [i for i in range(len(lot) - 1) if lot[i].isdigit() and lot[i + 1].isdigit() and lot[i] != lot[i + 1]]
    if pos:
        i = rng.choice(pos)
        return lot[:i] + lot[i + 1] + lot[i] + lot[i + 2:]
    i = max(i for i, ch in enumerate(lot) if ch.isdigit())
    return lot[:i] + str((int(lot[i]) + 1) % 10) + lot[i + 1:]


INJECT = {
    "BOUND_ABOVE_LIMIT": x_bound_above, "ND_NO_LOD": x_nd_no_lod, "ND_WITH_LOD": x_nd_with_lod,
    "SPEC_COPIED": x_spec_copied, "MISSING_REQUIRED": x_missing, "CONVERTED_OOS": x_converted,
    "SUM_ONLY": x_sum_only, "AMBIGUOUS_ANALYTE": x_ambiguous, "DATE_CONFLICT": x_date,
    "LOT_MISMATCH": x_lot, "MATERIAL_MISMATCH": x_material,
}
DOC_LEVEL = {"DATE_CONFLICT", "LOT_MISMATCH", "MATERIAL_MISMATCH"}


def plan_codes(rng, normal_rate, reason_w, mix_w):
    """이 문서에 넣을 사유코드 목록.  빈 목록 = 정상 문서"""
    if rng.random() < normal_rate:
        return []
    n = rng.choices(list(mix_w), weights=list(mix_w.values()))[0]
    pool = {k: w for k, w in reason_w.items() if w > 0}
    codes = []
    while pool and len(codes) < n:
        c = rng.choices(list(pool), weights=list(pool.values()))[0]
        codes.append(c)
        del pool[c]
        if c == "LOT_MISMATCH":
            pool.pop("MATERIAL_MISMATCH", None)       # 입고 불일치는 한 장에 하나만
        if c == "MATERIAL_MISMATCH":
            pool.pop("LOT_MISMATCH", None)
    # 결과표를 먼저 만드는 OUT_OF_SPEC 을 맨 앞에, 줄을 지우는 MISSING 을 맨 뒤에
    order = ["OUT_OF_SPEC"] + [c for c in INJECT if c != "MISSING_REQUIRED"] + ["MISSING_REQUIRED"]
    return sorted(codes, key=order.index)


def build_rows(d, mod, rng, codes):
    """정상 결과표를 만들고 codes 의 예외를 넣는다.  실제로 들어간 코드 목록을 돌려준다"""
    d.update(extra=[], doc_notes=[], doc_reasons=[])
    fails = pick_fails(d["items"], rng, mod.ALLOW_BOTH) if "OUT_OF_SPEC" in codes else {}
    d["rows"] = make_results(d["items"], rng, fails, d["level"], mod.WORDS)
    used = set(fails)
    done = ["OUT_OF_SPEC"] if fails else []
    for c in codes:
        if c == "OUT_OF_SPEC":
            continue
        if INJECT[c](d, mod, rng, used):
            done.append(c)
            if c in DOC_LEVEL:
                d["doc_reasons"].append(c)
    return done


def lot_recommendation(d):
    exp = [r["expected"] for r in d["rows"] + d["extra"]]
    if "FAIL" in exp:
        return "REJECT"
    if d["doc_reasons"] or any(e in ("INDETERMINATE", "CHECK", "MISSING") for e in exp):
        return "HOLD"
    return "ACCEPT"


def judge_doc(d):
    rows = d["rows"] + d["extra"]
    failed = [r["item_id"] for r in rows if r["expected"] == "FAIL"]
    sup_failed = [r["item_id"] for r in d["rows"] if r.get("supplier") == "FAIL"]
    flagged = [r["item_id"] for r in rows if r["expected"] not in ("PASS", "REF")]
    reasons = list(d["doc_reasons"]) + sorted({r["reason"] for r in rows if r["reason"] not in QUIET_REASONS})
    return dict(lot_recommendation=lot_recommendation(d), reason_codes=reasons, flagged_items=flagged,
                supplier_judgement="FAIL" if sup_failed else "PASS", internal_failed_items=failed,
                hidden_fail=bool(failed) and not sup_failed)


# =============================================================================
# 5. PDF 그리기 도우미 (reportlab)
# =============================================================================

def need_reportlab():
    try:
        import reportlab  # noqa: F401
    except ImportError:
        print("reportlab 이 없습니다. 먼저 다음을 실행하세요:  pip install reportlab")
        sys.exit(1)


WIN_FONTS = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
FONT_DIRS = [WIN_FONTS, Path.home() / "AppData/Local/Microsoft/Windows/Fonts",
             Path("/usr/share/fonts/truetype/liberation"), Path("/usr/share/fonts/truetype/liberation2"),
             Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/share/fonts/truetype/wqy"),
             Path("/usr/share/fonts/truetype/arphic"), Path("/Library/Fonts"), Path("/System/Library/Fonts"),
             Path("/System/Library/Fonts/Supplemental")]

# 역할별 후보 글꼴 (앞에 있는 것부터 찾음).  (파일 이름, ttc 안 번호)
FONT_CANDIDATES = {
    "sans": [("arial.ttf", 0), ("LiberationSans-Regular.ttf", 0), ("Arial.ttf", 0), ("DejaVuSans.ttf", 0)],
    "sans-b": [("arialbd.ttf", 0), ("LiberationSans-Bold.ttf", 0), ("Arial Bold.ttf", 0), ("DejaVuSans-Bold.ttf", 0)],
    "sans-i": [("ariali.ttf", 0), ("LiberationSans-Italic.ttf", 0), ("Arial Italic.ttf", 0),
               ("DejaVuSans-Oblique.ttf", 0)],
    "serif": [("times.ttf", 0), ("LiberationSerif-Regular.ttf", 0), ("Times New Roman.ttf", 0),
              ("DejaVuSerif.ttf", 0)],
    "serif-b": [("timesbd.ttf", 0), ("LiberationSerif-Bold.ttf", 0), ("Times New Roman Bold.ttf", 0),
                ("DejaVuSerif-Bold.ttf", 0)],
    "mono": [("consola.ttf", 0), ("cour.ttf", 0), ("DejaVuSansMono.ttf", 0), ("LiberationMono-Regular.ttf", 0)],
    # 중국어: 宋体(본문) / 黑体·雅黑(제목).  Windows 기본 글꼴, 없으면 리눅스 문천역정흑
    "cjk": [("simsun.ttc", 0), ("simsun.ttf", 0), ("msyh.ttc", 0), ("simhei.ttf", 0), ("wqy-zenhei.ttc", 0),
            ("uming.ttc", 0), ("Songti.ttc", 0)],
    "cjk-b": [("simhei.ttf", 0), ("msyhbd.ttc", 0), ("msyh.ttc", 0), ("wqy-zenhei.ttc", 0), ("simsun.ttc", 0),
              ("STHeiti Medium.ttc", 0)],
}
BUILTIN = {"sans": "Helvetica", "sans-b": "Helvetica-Bold", "sans-i": "Helvetica-Oblique", "serif": "Times-Roman",
           "serif-b": "Times-Bold", "mono": "Courier", "cjk": "STSong-Light", "cjk-b": "STSong-Light"}
_FONTS = {}
_FONT_FILES = {}            # 역할 -> (글꼴 파일 경로, ttc 번호)  도장 그림(PIL)에 씀
_FAKE_BOLD = set()          # 굵은 글꼴 파일이 없어 보통 글꼴에 테두리를 둘러 굵게 보이게 할 글꼴


def font(role):
    """역할 이름('sans', 'cjk' ...) -> reportlab 글꼴 이름.  처음 부를 때 PC에서 글꼴 파일을 찾아 등록한다"""
    if role in _FONTS:
        return _FONTS[role]
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    for fname, idx in FONT_CANDIDATES[role]:
        for d in FONT_DIRS:
            p = d / fname
            if p.exists():
                try:
                    name = f"F_{role}"
                    pdfmetrics.registerFont(TTFont(name, str(p), subfontIndex=idx))
                    _FONTS[role] = name
                    _FONT_FILES[role] = (str(p), idx)
                    if role == "cjk-b" and fname not in ("simhei.ttf", "msyhbd.ttc", "STHeiti Medium.ttc"):
                        _FAKE_BOLD.add(name)
                    return name
                except Exception:
                    continue
    name = BUILTIN[role]
    if role.startswith("cjk"):
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        pdfmetrics.registerFont(UnicodeCIDFont(name))
        print("  (주의) 중국어 글꼴 파일을 못 찾아 PDF 뷰어 내장 글꼴(STSong)로 대체합니다.")
    _FONTS[role] = name
    return name


def hexcolor(h):
    from reportlab.lib.colors import HexColor
    return HexColor(h)


# ── 아래·위 첨자: "CO_{3}^{2-}" 처럼 쓰면 3 은 아래, 2- 는 위에 작게 찍힌다 ────────────────
_RICH = re.compile(r"(_\{[^}]*\}|\^\{[^}]*\})")


def _segments(text):
    out = []
    for part in _RICH.split(text):
        if not part:
            continue
        if part.startswith("_{"):
            out.append((part[2:-1], "sub"))
        elif part.startswith("^{"):
            out.append((part[2:-1], "sup"))
        else:
            out.append((part, None))
    return out


def plain(text):
    """첨자 표시를 뺀 글자 (정답 라벨용)"""
    return "".join(s for s, _ in _segments(text))


def rich_width(text, fname, size, char_space=0):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    w = 0
    for s, kind in _segments(text):
        sz = size * 0.65 if kind else size
        w += stringWidth(s, fname, sz) + char_space * len(s)
    return w


def draw_text(c, x, y, text, fname, size, align="left", color=None, char_space=0):
    """글자 하나 줄을 찍는다. align: left / center / right.  첨자 표기 지원"""
    w = rich_width(text, fname, size, char_space)
    if align == "center":
        x -= w / 2
    elif align == "right":
        x -= w
    from reportlab.pdfbase.pdfmetrics import stringWidth
    if color is not None:
        c.setFillColor(color)
    for s, kind in _segments(text):
        sz, dy = size, 0
        if kind == "sub":
            sz, dy = size * 0.65, -size * 0.18
        elif kind == "sup":
            sz, dy = size * 0.65, size * 0.38
        t = c.beginText(x, y + dy)
        t.setFont(fname, sz)
        t.setCharSpace(char_space)
        if fname in _FAKE_BOLD:
            c.saveState()
            c.setLineWidth(sz * 0.035)
            c.setStrokeColor(c._fillColorObj)
            t.setTextRenderMode(2)
            t.textOut(s)
            c.drawText(t)
            c.restoreState()
            x += stringWidth(s, fname, sz) + char_space * len(s)
            continue
        t.textOut(s)
        c.drawText(t)
        x += stringWidth(s, fname, sz) + char_space * len(s)
    return w


def wrap(text, fname, size, width):
    """단어 단위 줄바꿈 (공백 없는 중국어는 글자 단위)"""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    words = re.findall(r"\S+\s*", text) if " " in text else list(text)
    lines, cur = [], ""
    for w in words:
        if cur and stringWidth((cur + w).rstrip(), fname, size) > width:
            lines.append(cur.rstrip())
            cur = w
        else:
            cur += w
    if cur.strip():
        lines.append(cur.rstrip())
    return lines


def signature(c, x, y, w, h, rng, color="#1f2f6b", width=1.1):
    """손글씨 서명 흉내 (베지어 곡선 몇 개)"""
    c.saveState()
    c.setStrokeColor(hexcolor(color))
    c.setLineWidth(width)
    c.setLineCap(1)
    c.setLineJoin(1)
    p = c.beginPath()
    p.moveTo(x, y + h * rng.uniform(0.1, 0.4))
    n = rng.randint(3, 5)
    step = w / n
    for i in range(n):
        x0 = x + i * step
        p.curveTo(x0 + step * 0.2, y + h * rng.uniform(0.8, 1.15), x0 + step * 0.7, y + h * rng.uniform(0.8, 1.15),
                  x0 + step, y + h * rng.uniform(0.0, 0.3))
    c.drawPath(p, stroke=1, fill=0)
    p = c.beginPath()                               # 밑줄 획
    p.moveTo(x + w * rng.uniform(0.0, 0.15), y - h * 0.15)
    p.curveTo(x + w * 0.4, y - h * rng.uniform(0.3, 0.5), x + w * 0.7, y - h * 0.1, x + w * rng.uniform(0.9, 1.05),
              y + h * rng.uniform(0.0, 0.2))
    c.drawPath(p, stroke=1, fill=0)
    c.restoreState()


def star(c, cx, cy, r, color):
    p = c.beginPath()
    for i in range(10):
        a = math.radians(90 + i * 36)
        rr = r if i % 2 == 0 else r * 0.4
        x, y = cx + rr * math.cos(a), cy + rr * math.sin(a)
        p.moveTo(x, y) if i == 0 else p.lineTo(x, y)
    p.close()
    c.setFillColor(color)
    c.drawPath(p, stroke=0, fill=1)


def round_seal(c, cx, cy, r, top_text, bottom_text, code, rng, color=(216, 38, 43), alpha=0.8):
    """
    중국식 빨간 원형 도장 (회사명 원호 + 별 + 아래 글자 + 일련번호).  살짝 기울고 반투명.
    실제 도장은 찍힌 '그림'이라 PDF 글자로 읽히면 안 되므로 그림(PNG)으로 그려 붙인다 (pillow 필요).
    pillow 가 없으면 테두리와 별만 선으로 그린다.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        from reportlab.lib.utils import ImageReader
    except ImportError:
        c.saveState()
        c.setStrokeColorRGB(*[v / 255 for v in color])
        c.setLineWidth(r * 0.06)
        c.circle(cx, cy, r, stroke=1, fill=0)
        star(c, cx, cy, r * 0.26, hexcolor("#%02x%02x%02x" % color))
        c.restoreState()
        return
    font("cjk-b")
    path, idx = _FONT_FILES.get("cjk-b", (None, 0))
    S = 5                                            # 1 pt = 5 px 로 그림
    R = r * S
    size = int(2 * R + 8 * S)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    o = size / 2
    ink = color + (int(255 * alpha),)
    lw = int(r * 0.06 * S)
    dr.ellipse([o - R, o - R, o + R, o + R], outline=ink, width=lw)

    def ttf(px):
        try:
            return ImageFont.truetype(path, int(px), index=idx) if path else ImageFont.load_default()
        except Exception:
            return ImageFont.load_default()

    f_top = ttf(r * 0.22 * S)
    n = len(top_text)
    a0, a1 = 212, -32                                # 왼쪽 아래 -> 위 -> 오른쪽 아래
    for i, ch in enumerate(top_text):
        a = math.radians(a0 + (a1 - a0) * (i + 0.5) / n)
        g = Image.new("RGBA", (int(R * 0.6), int(R * 0.6)), (0, 0, 0, 0))
        ImageDraw.Draw(g).text((g.width / 2, g.height / 2), ch, font=f_top, fill=ink, anchor="mm")
        g = g.rotate(math.degrees(a) - 90, resample=Image.BICUBIC)
        px, py = o + R * 0.7 * math.cos(a), o - R * 0.7 * math.sin(a)
        img.alpha_composite(g, (int(px - g.width / 2), int(py - g.height / 2)))
    pts = []
    for k in range(10):
        a = math.radians(90 + k * 36)
        rr = R * 0.26 if k % 2 == 0 else R * 0.104
        pts.append((o + rr * math.cos(a), o - rr * math.sin(a)))
    dr.polygon(pts, fill=ink)
    dr.text((o, o + R * 0.5), bottom_text, font=ttf(r * 0.2 * S), fill=ink, anchor="mm")
    dr.text((o, o + R * 0.74), code, font=ttf(r * 0.1 * S), fill=ink, anchor="mm")
    # 도장 잉크가 고르게 묻지 않은 느낌 (군데군데 옅게)
    px = img.load()
    for _ in range(int(size * size * 0.02)):
        x, y = rng.randrange(size), rng.randrange(size)
        r_, g_, b_, a_ = px[x, y]
        if a_:
            px[x, y] = (r_, g_, b_, int(a_ * rng.uniform(0.2, 0.7)))
    img = img.rotate(rng.uniform(-18, 18), resample=Image.BICUBIC)
    w = size / S
    c.drawImage(ImageReader(img), cx - w / 2, cy - w / 2, w, w, mask="auto")




# =============================================================================
# 6. 입고 정보 · 개발용/평가용 분할 · 정답 라벨 저장
# =============================================================================

RECEIPT_COLS = ["receipt_id", "supplier", "material", "received_lot", "spec_id", "received_date"]


def make_receipts(docs, rng):
    """CoA 1장 = 입고 1건.  일부 행에는 로트·원자재 불일치나 유효기한 경과가 들어가 있다 (사유코드로 주입한 것만)"""
    recs = []
    for d in docs:
        mat = d.get("receipt_material", MATERIAL)
        when = d.get("receipt_after") or d["dates"]["issue"] + timedelta(days=rng.randint(3, 20))
        recs.append(dict(doc=d, supplier=d["supplier"], material=mat["name"],
                         received_lot=d.get("receipt_lot", d["fields"]["lot_no"]), spec_id=mat["spec_id"],
                         received_date=when))
    recs.sort(key=lambda r: (r["received_date"], r["doc"]["doc_id"]))
    out = []
    for n, r in enumerate(recs, 1):
        rid = f"RCV-{r['received_date']:%y%m}-{n:04d}"
        r["doc"]["receipt_id"] = rid
        out.append(dict(receipt_id=rid, supplier=r["supplier"], material=r["material"],
                        received_lot=r["received_lot"], spec_id=r["spec_id"],
                        received_date=r["received_date"].isoformat()))
    return out


def assign_split(docs, eval_rate, seed):
    """
    개발용(dev) / 평가용(eval) 나누기.  문서(원본) 단위로 나누므로 같은 원본에서 만든 열화본은 항상 같은 쪽에 간다.
    정상 문서와 예외 문서를 따로 섞어서 나누어 두 쪽의 정상 비율이 비슷하게 한다.
    """
    rng = random.Random(seed * 7919 + 1)
    for group in (True, False):
        ds = [d for d in docs if d["is_normal"] == group]
        rng.shuffle(ds)
        n_eval = round(len(ds) * eval_rate)
        for k, d in enumerate(ds):
            d["split"] = "eval" if k < n_eval else "dev"


ITEM_COLS = ["doc_id", "split", "row", "item_id", "printed_name", "method", "unit", "spec", "result", "value_type",
             "bound", "value_std", "unit_std", "basis", "value_doc_std", "supplier", "internal_lsl", "internal_usl",
             "expected", "expected_kr", "reason", "deviation_std", "deviation_pct", "case", "note"]


def item_record(d, r):
    rec = dict(r, doc_id=d["doc_id"], split=d["split"], internal_lsl=r.get("int_lsl"), internal_usl=r.get("int_usl"),
               expected_kr=ITEM_STATUS[r["expected"]])
    return {k: rec.get(k) for k in ITEM_COLS}


def save_labels(out_dir, mod, docs, receipts, variants, settings):
    """
    ground_truth.json        문서별 전체 정답 (머리글 + 항목 + 사유코드 + 입고 + 열화본) 과 규격 DB
    ground_truth_docs.csv    문서 1장 = 1줄: 머리글 필드, 정상 여부, 넣은 사유코드, 로트 권고(정답), 분할
    ground_truth_items.csv   시험 항목 1개 = 1줄 (+ 누락 줄, 합산·중금속 줄에서 유도한 원소 줄)
    receipts.csv             가상 입고 정보 (판독 프로그램 입력)
    variants.csv             열화본 목록: 파일, 원본 문서, 열화 종류, 분할
    """
    out_dir = Path(out_dir)
    field_names = mod.FIELD_NAMES
    judged = [(d, judge_doc(d)) for d in docs]
    data = dict(template=mod.TEMPLATE, material=MATERIAL["name"], material_key=MATERIAL["key"],
                spec_id=MATERIAL["spec_id"], customer=CUSTOMER, settings=settings, spec_db=SPEC_DB,
                ref_items={k: dict(name=v["name"], unit=v["unit"]) for k, v in REF_ITEMS.items()},
                unit_to_std=[dict(doc_unit=a, std_unit=b, factor=f) for (a, b), f in UNIT_TO_STD.items()],
                oxide_to_element={k: dict(oxide=v[0], factor=v[3]) for k, v in OXIDES.items()},
                reason_codes=REASONS, item_status=ITEM_STATUS, lot_recommendation=LOT_REC, lot_rule=LOT_RULE,
                receipts=receipts, documents=[])
    for d, j in judged:
        data["documents"].append(dict(
            doc_id=d["doc_id"], file=d["file"], split=d["split"], template=mod.TEMPLATE, supplier=d["supplier"],
            receipt_id=d["receipt_id"], fields=d["fields"], printed_conclusion=d.get("printed_conclusion"),
            is_normal=d["is_normal"], injected_codes=d["injected"], doc_notes=d["doc_notes"],
            date_conflict=d.get("date_conflict"), **j,
            variants=[v["file"] for v in variants if v["doc_id"] == d["doc_id"]],
            items=[item_record(d, r) for r in d["rows"] + d["extra"]]))
    with open(out_dir / "ground_truth.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, default=str)

    with open(out_dir / "ground_truth_docs.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["doc_id", "file", "split", "material", "supplier", "receipt_id"] + [k for k, _ in field_names]
                   + ["printed_conclusion", "is_normal", "injected_codes", "lot_recommendation",
                      "lot_recommendation_kr", "reason_codes", "flagged_items", "internal_failed_items",
                      "hidden_fail", "doc_notes"])
        for d, j in judged:
            w.writerow([d["doc_id"], d["file"], d["split"], MATERIAL["key"], d["supplier"], d["receipt_id"]]
                       + [d["fields"].get(k, "") for k, _ in field_names]
                       + [d.get("printed_conclusion") or "", d["is_normal"], ";".join(d["injected"]),
                          j["lot_recommendation"], LOT_REC[j["lot_recommendation"]], ";".join(j["reason_codes"]),
                          ";".join(j["flagged_items"]), ";".join(j["internal_failed_items"]), j["hidden_fail"],
                          " / ".join(d["doc_notes"])])

    with open(out_dir / "ground_truth_items.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(ITEM_COLS)
        for d in docs:
            for r in d["rows"] + d["extra"]:
                rec = item_record(d, r)
                w.writerow(["" if rec[c] is None else rec[c] for c in ITEM_COLS])

    with open(out_dir / "receipts.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(RECEIPT_COLS)
        for r in receipts:
            w.writerow([r[c] for c in RECEIPT_COLS])

    cols = ["file", "doc_id", "split", "degrade", "text_layer", "dpi", "angle", "blur_radius", "jpeg_quality"]
    with open(out_dir / "variants.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for v in variants:
            w.writerow(["" if v.get(c) is None else v.get(c) for c in cols])


def print_summary(mod, docs, variants, out_dir):
    js = [judge_doc(d) for d in docs]
    rec = Counter(j["lot_recommendation"] for j in js)
    n_norm = sum(d["is_normal"] for d in docs)
    codes = Counter(c for d in docs for c in d["injected"])
    split = Counter(d["split"] for d in docs)
    print(f"\n양식 {mod.TEMPLATE} · {MATERIAL['name_kr']}: {len(docs)}장 -> {Path(out_dir).resolve()}")
    print(f"  정상 문서 {n_norm}장 ({n_norm / max(len(docs), 1) * 100:.0f}%) / 예외 문서 {len(docs) - n_norm}장")
    print("  로트 권고 정답: " + ", ".join(f"{LOT_REC[k]} {rec.get(k, 0)}" for k in LOT_REC))
    if codes:
        print("  넣은 사유코드: " + ", ".join(f"{k} {v}" for k, v in codes.most_common()))
    print(f"  분할: 개발용 {split.get('dev', 0)}장 / 평가용 {split.get('eval', 0)}장 (원본 기준)")
    kinds = Counter(v["degrade"] for v in variants)
    print("  PDF: " + ", ".join(f"{k} {v}" for k, v in kinds.items()))


# =============================================================================
# 7. 실행 옵션과 전체 흐름
# =============================================================================

def parse_weights(text, base, key_type=str):
    w = dict(base)
    if not text:
        return w
    for part in text.split(","):
        if not part.strip():
            continue
        k, v = part.split("=")
        k = key_type(k.strip().upper() if key_type is str else k.strip())
        if key_type is str and k not in base:
            raise SystemExit(f"모르는 사유코드: {k}  (쓸 수 있는 코드: {', '.join(base)})")
        w[k] = float(v)
    return w


def parse_common_args(desc, default_count, default_out):
    import argparse
    ap = argparse.ArgumentParser(description=desc, formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="사유코드: " + ", ".join(REASONS))
    ap.add_argument("--material", choices=list(MATERIALS), default="li2co3",
                    help="원자재. li2co3 = 탄산리튬(기본), lioh = 수산화리튬 일수화물")
    ap.add_argument("--count", type=int, default=default_count, help=f"만들 CoA 장수 (기본 {default_count})")
    ap.add_argument("--seed", type=int, default=42, help="난수 시드. 같으면 항상 같은 결과 (기본 42)")
    ap.add_argument("--normal-rate", type=float, default=0.6,
                    help="정상 문서 비율 0~1 (기본 0.6). 정상 문서에는 예외를 하나도 넣지 않는다")
    ap.add_argument("--reason-weights", default="",
                    help="사유코드별 생성 비율. 예) OUT_OF_SPEC=3,SUM_ONLY=2,DATE_CONFLICT=0  (0 = 안 만듦)")
    ap.add_argument("--mix-weights", default="",
                    help="예외 문서 1장에 섞는 코드 수 비율. 예) 1=65,2=25,3=10 (기본)")
    ap.add_argument("--fail-rate", type=float, default=None,
                    help="(v1 호환) 숨은 불합격만 만들 때. --normal-rate 1-값, 사유코드 OUT_OF_SPEC 만")
    ap.add_argument("--eval-rate", type=float, default=0.3, help="평가용 비율 0~1 (기본 0.3). 원본 문서 단위로 나눔")
    ap.add_argument("--degrade", default="original,lowres,skew,blur",
                    help="만들 열화 단계 (기본 네 가지 모두). 예) original  또는  original,blur")
    ap.add_argument("--start", default="2025-10-01", help="제조일 범위 시작 (기본 2025-10-01)")
    ap.add_argument("--end", default="2026-09-30", help="제조일 범위 끝 (기본 2026-09-30)")
    ap.add_argument("--out", default=None, help=f"결과 폴더 (기본 {default_out}_<원자재>)")
    a = ap.parse_args()
    a.start, a.end = date.fromisoformat(a.start), date.fromisoformat(a.end)
    if a.end < a.start:
        ap.error("--end 가 --start 보다 빠릅니다")
    a.reason_w = parse_weights(a.reason_weights, DEFAULT_REASON_WEIGHTS)
    a.mix_w = {int(k): v for k, v in parse_weights(a.mix_weights, DEFAULT_MIX_WEIGHTS, key_type=int).items() if v > 0}
    if a.fail_rate is not None:
        a.normal_rate = 1 - a.fail_rate
        a.reason_w = {k: (1.0 if k == "OUT_OF_SPEC" else 0.0) for k in DEFAULT_REASON_WEIGHTS}
        a.mix_w = {1: 1}
    if not 0 <= a.normal_rate <= 1 or not 0 <= a.eval_rate <= 1:
        ap.error("--normal-rate, --eval-rate 는 0~1 사이 값이어야 합니다")
    a.degrade = [x.strip() for x in a.degrade.split(",") if x.strip()]
    bad = [x for x in a.degrade if x not in ("original", "lowres", "skew", "blur")]
    if bad:
        ap.error(f"모르는 열화 단계: {bad}  (original, lowres, skew, blur 중에서)")
    if "original" not in a.degrade:
        a.degrade.insert(0, "original")
    a.rng = random.Random(a.seed)
    out = Path(a.out or f"{default_out}_{a.material}")
    if not out.is_absolute():
        out = Path(__file__).resolve().parent / out
    out.mkdir(parents=True, exist_ok=True)
    a.out = out
    return a


def run(mod, desc, default_out):
    """양식 프로그램의 main: 머리글 -> 결과표 + 예외 -> 입고 정보 -> 분할 -> PDF·열화본 -> 정답"""
    need_reportlab()
    args = parse_common_args(desc, 30, default_out)
    set_material(args.material)
    rng = args.rng
    docs = mod.make_docs(args)
    for d in docs:
        d["planned"] = plan_codes(rng, args.normal_rate, args.reason_w, args.mix_w)
        d["injected"] = build_rows(d, mod, rng, d["planned"])
        d["is_normal"] = not d["injected"]
    receipts = make_receipts(docs, rng)
    assign_split(docs, args.eval_rate, args.seed)

    import coa_degrade
    deg_rng = random.Random(args.seed * 104729 + 3)
    variants = []
    for d in docs:
        d["file"] = f"pdf/{d['split']}/original/{d['doc_id']}.pdf"
        path = args.out / d["file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        mod.draw_doc(path, d, rng)
        variants += coa_degrade.make_variants(path, args.out, d, args.degrade, deg_rng)
    settings = dict(material=args.material, count=args.count, seed=args.seed, normal_rate=args.normal_rate,
                    reason_weights=args.reason_w, mix_weights=args.mix_w, eval_rate=args.eval_rate,
                    degrade=args.degrade, start=args.start.isoformat(), end=args.end.isoformat())
    save_labels(args.out, mod, docs, receipts, variants, settings)
    print_summary(mod, docs, variants, args.out)
