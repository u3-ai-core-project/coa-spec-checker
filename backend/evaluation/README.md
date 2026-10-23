# 평가 스크립트 (evaluation/)

정답 라벨과 시스템 출력을 비교해 추출·판정 정확도를 계산합니다. 서버를 띄우지 않고 파일만 읽어 실행합니다.
지표는 「백엔드 업무 분담」의 평가 항목과 v1.4(안) 추가 요청([홍채령 · P0])을 따릅니다.

## 실행

```bash
cd backend
python -m evaluation.run --gt <정답 라벨 폴더> --pred <시스템 출력 폴더> [--baseline <베이스라인 출력 폴더>]
```

- 리포트는 `evaluation/reports/<시각>/report.md`, `report.json` 에 저장됩니다 (`--out` 으로 변경, 이 폴더는 git 에 올라가지 않음).
- `--threshold`: 신뢰도 기준값. 기본은 서버 설정 `LOW_CONFIDENCE_THRESHOLD`
- `--policy`: 시스템 출력을 만든 서버의 판정 정책 JSON. 기본은 이 컴퓨터 `.env` 의 값 (`REASON_JUDGEMENT`, `ND_LIMIT_INCLUSIVE`, `UNMAPPED_AI_ITEM`, `CROSS_RULES`). 리포트에 기록해 정책별 결과를 비교할 수 있게 합니다.
- 예시 실행: `python -m evaluation.run --gt evaluation/examples/gt --pred evaluation/examples/pred --baseline evaluation/examples/baseline`
  (`examples/` 는 형식 예시용 가상 값입니다)

파일 이름(확장자 제외)이나 `document_id` 로 정답과 출력을 짝짓습니다. 문서 1건 = JSON 1개.

## 정답 라벨 형식 (제안, 참고용 초안)

소성훈 님 정답 라벨 구조(머리글 필드, 시험 항목 행, 문서 판정)에 판정 5종·사유코드·로트 권고를 더한 형식입니다.
사유코드 형식은 아직 확정 전입니다.

```json
{
  "document_id": "COA_A_0007",
  "material_code": "LI2CO3",
  "source": "synthetic",
  "form": "A",
  "degradation": "original",
  "header": {"supplier": "…", "lot_no": "…", "test_date": "2026-09-28"},
  "items": [
    {"normalized_name": "K", "raw_value": "< 100 ppm", "unit": "ppm", "converted_value": 100,
     "judgement": "undetermined", "reason_code": "BOUND_ABOVE_LIMIT"},
    {"normalized_name": "황산염", "judgement": "missing", "reason_code": "MISSING_REQUIRED"}
  ],
  "lot_recommendation": "hold",
  "document_issues": []
}
```

| 필드 | 설명 |
| --- | --- |
| `material_code`, `source`(`real`/`synthetic`), `form`, `degradation` | 분리 보고 기준. 없으면 그 그룹에서 빠짐 |
| `header` | 비교할 머리글 필드. 시스템 출력의 같은 이름 필드와 비교 (값이 null 이면 채점 안 함) |
| `items[].normalized_name` | 사내 규격 `item_name` 과 같은 이름. 이 이름으로 출력 항목과 짝지음 |
| `items[].raw_value`, `converted_value` | CoA 원문, 사내 단위 환산값 |
| `items[].judgement` | 판정 5종 (API 명세 2.3). 누락 항목은 `missing` |
| `items[].reason_code` | 사유코드 (v1.4안). 적합이면 `null` |
| `lot_recommendation`, `document_issues` | 로트 권고, 문서 정합성 코드 목록 |

**키를 안 적으면 채점하지 않습니다.** `"reason_code": null` 은 "사유코드 없음이 정답", 키 자체가 없으면 "아직 라벨링 안 함"입니다. 라벨을 단계적으로 채워도 채울 수 있는 지표부터 계산됩니다.

## 시스템 출력 형식

- 서버 `GET /documents/{id}/extraction` 응답(`ExtractionResult`)을 그대로 저장하면 됩니다. `{"success", "data"}` 로 감싼 채여도 됩니다.
- AI 추출 결과(`ExtractionInput`)도 됩니다. 이 경우 판정·사유코드 필드가 없으므로 추출 지표만 계산됩니다 (AI 모델 비교용).
- 규칙 베이스라인(소성훈 님 검증 프로그램 등) 출력도 같은 형식으로 변환해 `--baseline` 으로 넘깁니다.

## 지표 정의

분모가 0 이면 `-` (값 없음)로 표시합니다.

**추출 (업무 분담 '평가')**

| 지표 | 정의 |
| --- | --- |
| 항목 인식률 | 출력에서 찾은 정답 항목 수 ÷ CoA 에 있는 정답 항목 수 (누락 항목 제외). 출력 파일이 없는 문서는 0개 인식 |
| 수치 일치율 | 값이 일치한 항목 ÷ 인식한 항목 중 정답 값이 있는 항목. 환산값이 둘 다 숫자면 숫자로, 아니면 원문을 공백·부등호 표기만 정리해 비교. `"< 20"` 과 `"20"` 처럼 부등호·검출 안 됨 표기가 다르면 불일치 |
| 머리글 일치율 | 일치한 머리글 필드 ÷ 정답에 값이 있는 머리글 필드 |
| 오류 유형 | 항목 미인식, 부등호·ND 표기 차이(`qualifier`), 10의 거듭제곱 배 차이(`unit`), 숫자 오독(`number`), 값 없음 |
| 신뢰도 검증 | 신뢰도 기준값 미만 항목의 실제 오류 비율, 실제 오류 중 기준값 미만으로 잡힌 비율 |

**판정 (업무 분담 '평가')**

| 지표 | 정의 |
| --- | --- |
| 판정 일치율 (5종) | 판정이 같은 항목 ÷ 판정 라벨이 있는 항목. 출력에 항목이 없으면 `absent` 로 불일치 |
| 판정 불가·누락 → 적합 | 정답이 판정 불가·누락인데 출력이 적합이거나 항목이 없음 (가장 위험한 오류, 항목 단위) |
| 부적합 → 적합 | 정답이 부적합인데 출력이 적합이거나 항목이 없음 (숨은 불합격 미탐, 항목 단위) |

**v1.4(안) 추가 지표 (업무 분담 [홍채령 · P0])**

| 지표 | 정의 |
| --- | --- |
| 정상 자동 처리율 | 정답이 승인 권고인 문서(정상 문서) 중 시스템도 승인 권고한 비율 |
| 과잉 보류율 | 정상 문서 중 시스템이 보류 권고한 비율 (참고: 불합격 권고한 비율도 함께 계산) |
| 사유코드 정밀도·재현율 | 항목별로 정답·출력 사유코드를 비교. 같으면 TP, 출력에만 있으면 FP, 정답에만 있으면 FN. 코드별·전체(micro). `LOW_CONFIDENCE` 는 실행마다 달라 라벨에 적을 수 없으므로 채점에서 빼고 개수만 따로 보고 |
| 규칙 베이스라인 비교 | 같은 정답으로 시스템·베이스라인 지표를 나란히 계산하고 차이를 표시 |
| 분리 보고 | 원자재별, 실물/합성별 (업무 분담 '평가'의 양식별, 열화 단계별도 함께) |

`document_issues` 코드도 사유코드와 같은 방식으로 정밀도·재현율을 계산해 상세에 보여 줍니다.

**넣지 않은 것 (2026-10-18)**: 「기획안 v2」 11장에만 있는 지표는 기획안과 API 명세가 아직 맞춰지지 않아 넣지 않았습니다. 로트 단위 위험 오류(문제 로트를 승인 권고), 사유코드 정확 일치율, 값 유형 분류·규격 복사 탐지율, 항목명 매핑 정확도, 평가셋별(같은/처음 보는 양식) 보고, 문서 유형 분류, 사람 검토 감소율, 목표값. 확정되면 추가합니다.
