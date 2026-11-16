# AI 평가셋과 예측 결과

발표 자료와 노션 「[AI] 성능 검증 결과」에 쓴 가상 CoA 평가의 정답·예측·리포트 원본입니다. 측정일은 2026-11-07입니다.

## 2026-11-07_synth_seed7 (가상 CoA 240장)

- 평가셋: 생성기 v2로 만든 탄산리튬 가상 CoA 60건(양식 A·B·D 각 20건) × 4단계(원본 글자 PDF, 저해상도, 기울기, 흐림) = 240장
- 시드 7: 규칙을 만들 때 보지 않은 묶음입니다. 같은 양식의 다른 묶음은 규칙 보강에 썼으므로, 처음 보는 양식에 대한 성능은 아닙니다.

| 경로 | 내용 |
| --- | --- |
| `gt/` | 정답 라벨 240개. 생성기 정답을 `ai/tools/synth_gt.py`로 평가 스크립트 형식으로 바꾼 것 |
| `pred/` | AI 추출 결과 240개 (`ExtractionInput` 형식). `ai/bench/synth_eval.py`로 만듦 |
| `pred_judged/` | `pred/`에 서버 판정 엔진을 돌린 결과 240개. 규격 세트 `LI2CO3-GENV2-EVAL` |
| `timings.csv` | 문서별 추출 시간(초) |
| `failures.csv` | 추출 실패 목록 (0건) |
| `reports/extract_report.md` | `pred/` 채점 리포트: 항목 인식률, 수치 일치율, 머리글 일치율 |
| `reports/judged_report.md` | `pred_judged/` 채점 리포트: 판정 일치율, 로트 권고, 자동 처리율, 안전성 |

### 발표 자료 수치와 출처

| 발표 수치 | 값 | 리포트 |
| --- | --- | --- |
| 항목 인식률 / 수치 일치율 (240장 전체) | 97.9 % / 99.7 % | extract_report 1장 |
| 머리글 일치율 (240장 전체) | 92.3 % | extract_report 1장 |
| 스캔본 평균 항목 / 수치 / 머리글 | 97.1 / 99.6 / 89.8 % | extract_report 열화 단계별 (blur·lowres·skew 평균) |
| 글자 PDF 판정 일치 / 로트 권고 / 자동 처리 | 99.7 / 100 / 100 % | judged_report 열화 단계별 original |
| 스캔본 판정 일치 / 로트 권고 / 자동 처리 | 6.9~7.7 / 18.3 / 0 % | judged_report 열화 단계별 |
| 부적합 → 적합, 판정 불가·누락 → 적합 | 0건 | judged_report |

- 판정 리포트의 항목·수치 지표(99.3 %, 95.3 %)는 판정 출력 형식으로 다시 센 값이라 추출 리포트와 다릅니다. 발표의 추출 지표는 추출 리포트 값입니다.
- 스캔본 판정 일치율이 낮은 것은 설계입니다. OCR 항목은 신뢰도 0.75 이하로 나가 모두 "확인 필요"가 됩니다.

### 다시 계산하는 방법

```bash
cd backend
# 추출 지표
python -m evaluation.run --gt ../ai/eval/2026-11-07_synth_seed7/gt --pred ../ai/eval/2026-11-07_synth_seed7/pred
# 판정 지표 (저장된 판정 결과 그대로)
python -m evaluation.run --gt ../ai/eval/2026-11-07_synth_seed7/gt --pred ../ai/eval/2026-11-07_synth_seed7/pred_judged
# 판정 결과를 지금 서버 코드로 다시 만들기
PYTHONPATH=. python ../ai/eval/judge_synth.py ../ai/eval/2026-11-07_synth_seed7/pred /tmp/pred_judged LI2CO3-GENV2-EVAL
```

리포트 안의 경로(`../ai/data/generated/eval_1107_seed7`)는 측정 당시 로컬 경로이고, 내용은 이 폴더와 같습니다. 2026-11-16 develop(c28b8ac)에서 다시 판정해도 위 판정 수치가 그대로 나옵니다.

## 저장소에 넣지 않은 것

- 실물 CoA 정답 라벨(35건 385항목)과 실물 50건 처리 결과: 공개 CoA의 값이 들어 있어 라이선스 확인 전에는 저장소에 올리지 않는다는 팀 규칙을 따릅니다. 결과 요약은 노션 「[AI] 성능 검증 결과」에 있습니다.
- LLM 문제 세트(589문제): 문제의 대부분이 실물 CoA 항목명과 결과 칸에서 나와 같은 이유로 뺐습니다. 채점 코드는 `ai/bench/llm/`에 있습니다.
