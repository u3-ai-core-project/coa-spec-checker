"""[담당: 고도영] 추출값 자체 검증: 틀렸을 가능성이 높은 항목을 '확인 필요'로 돌리고 이유를 붙인다.

판정(합격·불합격)은 하지 않고 값도 고치지 않는다. 걸린 항목은 신뢰도를 SELF_CHECK_CAP 아래로 내려
서버가 확인 필요로 보내게 하고, check_reasons 에 이유를 남긴다 (검수 화면용, 팀 제안 칸).

  junk  값에 스캔 잡음으로 보이는 글자 ('40.0 ppm 0|': 한글 '이하'를 OCR 이 못 읽음)
  dup   같은 쪽에 같은 표준 항목이 두 번 나오고 숫자 값이 다름 (쪽이 다르면 로트별 쪽·이어지는 표일 수 있음)
  unit  결과와 규격의 단위 종류가 다름 (질량 분율 vs 길이) → 행이 어긋났을 수 있음
  swap  결과 칸에 범위, 규격 칸에 숫자 → 두 칸이 바뀌었을 수 있음
  huge  결과가 규격 상한의 50배 이상 → 소수점·단위 오류일 수 있음
  order 같은 쪽의 입도가 D10 ≤ D50 ≤ D90 이 아님 → 소수점을 놓쳤을 수 있음 (생성기 v2 저해상도 1.7 → 17)

모델 테스트(스캔본 152장)에서 틀린 값 15건을 모두 잡고 맞는 값은 하나도 잡지 않았다. 깨끗한 텍스트 PDF
39건에서는 0건이 걸린다. junk 외의 검사는 실제 데이터에서 걸린 적이 없고, 표 복원 오류를 대비한 것이다.
"""
from __future__ import annotations

import re
from collections import defaultdict

from coa_ai.meaning import Condition, parse_condition
from coa_ai.models import Item

SELF_CHECK_CAP = 0.75  # 서버 LOW_CONFIDENCE_THRESHOLD(0.8) 미만
HUGE_RATIO = 50  # 소수점이 빠지면(0.36 → 36) 상한의 수십~수백 배가 된다. 실제 불합격은 상한의 몇 배 수준
PARTICLE_SIZES = ("입도 D10", "입도 D50", "입도 D90")

# 스캔 잡음 글자. 기본 OCR 인식 모델은 한글이 없어 '이하'를 '0|'·'0l' 로 읽는다 (coa_ai.ocr 도 이 정규식을 쓴다)
OCR_JUNK = re.compile(r"[|σ¦]|(?<![A-Za-z0-9])\d[\d.,]*[lIOo](?![A-Za-z])")
_PARENS = re.compile(r"[(（][^)）]*[)）]")
_UNIT_KIND = {u: "질량 분율" for u in ("%", "wt%", "ppm", "ppb", "mg/kg", "ug/g", "ug/kg", "g/kg")}
_UNIT_KIND.update({u: "길이" for u in ("um", "nm", "mm")})


def check_items(items: list[Item]) -> None:
    """items 를 그 자리에서 고친다: 걸린 항목은 check_reasons 추가, 신뢰도 상한 SELF_CHECK_CAP."""
    found: dict[int, list[str]] = defaultdict(list)
    for k, it in enumerate(items):
        found[k] += _item_reasons(it)

    by_name: dict[tuple[int, str], list[int]] = defaultdict(list)
    for k, it in enumerate(items):
        if it.mapping_source == "dictionary" and it.raw_value and re.search(r"\d", it.raw_value):
            by_name[((it.bbox or {}).get("page", 0), it.normalized_name)].append(k)
    for (_, name), ks in by_name.items():
        if len({re.sub(r"\s+", "", items[k].raw_value) for k in ks}) > 1:
            for k in ks:
                found[k].append(f"같은 항목({name})이 두 번 나오고 값이 다름")

    for k in _particle_order_broken(items):
        found[k].append("입도 크기 순서가 맞지 않음 (D10 ≤ D50 ≤ D90). 소수점 확인")

    for k, why in found.items():
        if why:
            items[k].check_reasons.extend(why)
            items[k].confidence = min(items[k].confidence, SELF_CHECK_CAP)


def _item_reasons(it: Item) -> list[str]:
    value, spec = (it.raw_value or "").strip(), (it.raw_spec or "").strip()
    if not value:
        return []
    out = []
    outside = _PARENS.sub(" ", value)
    m = OCR_JUNK.search(outside)
    if m:
        token = re.search(r"\S*$", outside[:m.start()]).group(0) + re.match(r"\S*", outside[m.start():]).group(0)
        out.append(f"값에 스캔 잡음으로 보이는 글자가 있음('{token}')")
    pv = parse_condition(value)
    ps = parse_condition(spec) if spec else None
    if pv is None or ps is None:
        return out
    kv, ks = _UNIT_KIND.get(pv.unit or ""), _UNIT_KIND.get(ps.unit or "")
    if kv and ks and kv != ks:
        out.append(f"결과 단위({pv.unit})와 규격 단위({ps.unit})의 종류가 다름. 행이 어긋났을 수 있음")
    if pv.kind == "range" and ps.kind == "value" and ps.op == "=":
        out.append("결과 칸에 범위, 규격 칸에 숫자가 있음. 두 칸이 바뀌었을 수 있음")
    if _huge(pv, ps):
        out.append(f"결과가 규격 상한의 {HUGE_RATIO}배 이상. 소수점·단위 확인")
    return out


def _particle_order_broken(items: list[Item]) -> list[int]:
    """같은 쪽의 입도 D10·D50·D90 숫자가 커지는 순서가 아니면 그 항목들 번호 (어느 값이 틀렸는지는 모른다)."""
    by_page: dict[int, dict[str, int]] = defaultdict(dict)
    for k, it in enumerate(items):
        if it.normalized_name in PARTICLE_SIZES:
            by_page[(it.bbox or {}).get("page", 0)].setdefault(it.normalized_name, k)
    out = []
    for sizes in by_page.values():
        nums = []
        for name in PARTICLE_SIZES:
            c = parse_condition(items[sizes[name]].raw_value or "") if name in sizes else None
            if c and c.kind == "value" and c.op == "=" and c.num is not None:
                nums.append((c.num, sizes[name]))
        if any(a > b for (a, _), (b, _) in zip(nums, nums[1:])):
            out += [k for _, k in nums]
    return out


def _huge(pv: Condition, ps: Condition) -> bool:
    if pv.kind != "value" or ps.kind != "value" or ps.op not in ("<", "<=") or not ps.num or pv.num is None:
        return False
    if pv.unit and ps.unit and pv.unit != ps.unit:
        return False
    return pv.num >= HUGE_RATIO * ps.num
