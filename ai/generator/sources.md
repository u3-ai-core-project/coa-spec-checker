# 탄산리튬 값 범위 출처 (조사일 2026-10-18)

`coa_common.py` 의 `SPEC_DB_LI2CO3` 에 적힌 `src="L1 L2 ..."` 번호가 아래 번호입니다.
수산화리튬 쪽 출처(S1–S17)는 `labels_spec/sources.md` 를 그대로 따릅니다. 수치는 모두 표준 단위(%, ppm, ppb, µm)로 바꿔 적었습니다.

## 확인한 자료

| 번호 | 자료 | 확인한 값 | 어디에 썼나 | 링크 |
|---|---|---|---|---|
| L1 | YS/T 582-2023 전지급 탄산리튬 (중국 업계표준. 2023-12-20 발행, 2024-07-01 시행, 2013판 대체) | D1·D2·D3 등급, 자성물질 = Fe+Cr+Ni+Zn, 강열감량 ≤0.50 %, 붕소·D99 신설. **표 1 수치는 공개 요약에 없어서** L3 시험성적서에 적힌 'YS/T 582-2023' 한도로 간접 확인 | 협력사 규격(A·B 양식)의 기준선, B 양식 '检验依据' | [chinesestandard.net (2023판)](https://www.chinesestandard.net/PDF.aspx/YST582-2023) · [2013판](https://www.chinesestandard.net/PDF.aspx/YST582-2013) |
| L2 | Chengxin Lithium(成鑫锂业) 전지급 탄산리튬 검사 규격 | Li₂CO₃ ≥99.60 %, Na ≤200, Mg ≤60, Ca ≤40, Si ≤20, K ≤5, Fe ≤5, Cu·Zn·Mn·Pb ≤3, Cl ≤20 ppm, SO₄ ≤800 ppm, 수분 ≤0.25 %, 자성 ≤150 ppb, D50 5.0–8.0 µm | 사내 규격을 YS/T 보다 엄격하게 잡는 근거 (사내 한도는 L1 과 L2 사이) | [en.cxlithium.com](https://en.cxlithium.com/product/12.html) |
| L3 | Nanotrun 전지급 탄산리튬 시험성적서 (한 배치, 기준 YS/T 582-2023) | 규격: Li₂CO₃ ≥99.5, Na ≤0.025 %, K ≤0.005, Ca ≤0.008, Mg ≤0.008, Fe ≤0.001, Cu·Zn·Pb·Mn ≤0.0003, Si ≤0.003, SO₄ ≤0.08, Cl ≤0.005, 수분 ≤0.25 %, 자성 ≤300 ppb, D50 5.5±2.5 µm. 시험값: Li₂CO₃ 99.68 %, Na 62, Ca 16, Mg 2, Si 2, Cl 15, SO₄ 416 ppm, K·Fe·Cu <1 ppm, 수분 0.12 %, 자성 31 ppb, D50 6 µm | 협력사 규격 한도(A·B 양식에 그대로), 정상 로트 typical 의 중심값 | [nanotrun.com](https://www.nanotrun.com/battery-grade-lithium-carbonate-powder-p01604p1.html) |
| L4 | Thermo Fisher 앱노트 AN001168 (iCAP PRO XP ICP-OES, 탄산리튬 불순물) 표 4 | '99 %' 시료 평균: Na 131.6, Ca 114.6, Si 112.7, Mg 6.6, Fe 1.4, K 0.9, Mn 0.1 mg/kg. 99.998 % 시료는 거의 모두 검출한계 미만 | typical 범위의 위쪽(배터리급에 못 미치는 로트가 어디쯤인지), Fe·K·Mn 이 '<' 로 자주 나오는 근거 | [thermofisher PDF](https://documents.thermofisher.com/TFS-Assets/CMD/Application-Notes/an-001168-tea-icp-oes-icap-pro-xp-lithium-carbonate-an001168-na-en.pdf) |
| L5 | Century Lithium 보도자료 (2023-05-25, 파일럿 플랜트 탄산리튬) | Li₂CO₃ 99.875 wt %, Na 0.047 % (470 ppm), Ca 0.009 % (90 ppm), Cl 0.008 % (80 ppm), Fe 3 ppm, 수분 0.03 %, Al <2, Cu <4, Ni <5 ppm | 파일럿 단계 로트는 Na·Ca·Cl 이 사내 한도를 넘을 수 있다는 근거 (불합격 값 범위), 'Cu <4' 처럼 보고한계가 상한보다 큰 표기의 실제 예 | [channelchek 보도자료](https://dashboard.channelchek.com/release-century-lithium-reconfirms-production-of-battery-grade-purity-lithium-carbonate-and-provides-update-on-feasibility-study/) |
| L6 | Fisher Scientific 탄산리튬 CoA (시약급, 실제 발행본 2장) | Lot A0468916 (99+% ACS): 결과 칸이 규격과 똑같은 `=<50`, `=<20` 으로 적힘, `Heavy metals (ICP-OES) =<0.002 %`. Lot A0468768 (98+%): `Heavy metals (as Pb) 0.00068 %`, Na 0.0089 %, Fe 0.0002 %, 모든 값을 % 로 표기 | **값 범위가 아니라 표기 예**: SPEC_COPIED(결과 = 규격 문구), AMBIGUOUS_ANALYTE(Heavy metals as Pb) 가 실제 CoA 에 있다는 근거 | [Lot A0468916](https://assets.fishersci.com/api/ecertificate/95d0e6d1-4da2-418a-8da0-562ee839b203) · [Lot A0468768](https://assets.fishersci.com/api/ecertificate/24f9aff5-9ba1-4a51-b930-aec4ab5b4736) |

산화물 -> 원소 환산 배율(Na₂O 0.7419, K₂O 0.8301, CaO 0.7147, MgO 0.6031, Fe₂O₃ 0.6994)은 원자량으로 계산했습니다.

## 확인하지 못한 것, 추정한 것

- **'Fisher 27로트' 자료는 찾지 못했습니다.** 공개된 Fisher 전자 CoA 를 탄산리튬 2로트만 열어 봤고, 둘 다 시약급이라 배터리급 값 범위에는 쓰지 않았습니다. 27로트 모음 파일이 따로 있으면 typical 범위를 그 값으로 다시 맞추는 것이 좋습니다.
- **YS/T 582-2023 원문 표 1 은 열람하지 못했습니다** (유료). 협력사 규격 한도는 L3 성적서에 'YS/T 582-2023' 기준으로 적힌 값을 썼습니다.
- **사내 규격 한도(Sydco, 가상)는 우리가 정한 값입니다.** L1(느슨)과 L2(엄격) 사이에서 골랐습니다. 예: Na 200, Ca 50, Si 20 ppm.
- **typical(정상 로트 분포)은 추정입니다.** L3 한 배치, L4 측정값, L5 파일럿 결과처럼 몇 개 점만 있어서, 그 점들을 포함하고 사내 한도 안쪽에 오도록 범위를 잡았습니다.
- **검출한계(LOD) 값과 D 양식 협력사(Corvane)의 규격은 가상입니다.** D 양식 한도는 YS/T 수준에서 일부를 조금 엄격하게 바꾼 값입니다.
- 예외 값의 크기(예: '<20' 처럼 사내 상한의 1.6~4배인 보고한계, 산화물 환산 후 사내 상한을 넘는 정도)는 실제 분포가 아니라 판정 규칙을 시험하기 위한 설정입니다.
