### 가상 CoA 생성기 v2 실행 방법

양식 A·B·D 가상 CoA(PDF)와 정답 라벨, 입고 정보(receipts.csv)를 만듭니다. 양식 하나에 프로그램 하나(`gen_A.py`, `gen_B.py`, `gen_D.py`)이고, 공통 코드는 `coa_common.py`에 있습니다. 원자재는 탄산리튬(기본) 또는 수산화리튬입니다.

**1. 가상환경 생성 및 활성화**
```bash
cd coa-spec-checker/ai/generator
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
```

**2. 의존성 설치**
```bash
pip install --upgrade pip   # Windows : python -m pip install --upgrade pip
pip install reportlab pillow pypdfium2
```
`verify_labels.py`는 `pdftotext`(poppler)를 씁니다. 없으면 PDF 글자 대조 검사는 건너뜁니다.

**3. 생성 실행**

**방법 A. 명령어 사용**
```bash
python gen_A.py                                   # 탄산리튬 30장, 정상 60 %, 열화 4단계
python gen_B.py --material lioh --count 200       # 수산화리튬 200장
python gen_D.py --normal-rate 0.7                 # 정상 문서 70 %
```

**방법 B. bat 파일 사용 (Windows)**

`run_A.bat`, `run_B.bat`, `run_D.bat`을 더블클릭하고 원자재(1 = 탄산리튬, 2 = 수산화리튬), 장수, 정상 비율을 입력합니다. 처음 한 번은 필요한 패키지를 자동으로 설치합니다.

**4. 결과 폴더 지정**

기본 결과 폴더는 `output_A_li2co3/`처럼 현재 폴더에 만들어집니다. 저장소에 올라가지 않는 `ai/data/generated/`에 만들려면 `--out`을 씁니다.
```bash
python gen_A.py --out ../data/generated/synth_v2/A_li2co3
```
이 경로는 `ai/tools/synth_gt.py`가 읽는 경로와 같습니다.

**5. 옵션**

| 옵션 | 설명 | 기본값 |
| --- | --- | --- |
| `--material` | `li2co3` / `lioh` | `li2co3` |
| `--count` | 만들 CoA 장수 | 30 |
| `--seed` | 난수 시드. 같으면 항상 같은 결과 | 42 |
| `--normal-rate` | 정상 문서 비율 (정상 문서에는 예외를 넣지 않음) | 0.6 |
| `--reason-weights` | 사유코드별 생성 비율. 0이면 안 만듦 | 사유코드별 기본 비율 |
| `--mix-weights` | 예외 문서 1장에 섞는 코드 수 비율 | `1=65,2=25,3=10` |
| `--degrade` | 열화 단계. `original,lowres,skew,blur` 중 선택 | 네 가지 모두 |
| `--eval-rate` | 평가용 비율. 원본 문서 단위로 나눔 | 0.3 |
| `--start`, `--end` | 제조일 범위 | 2025-10-01 ~ 2026-09-30 |
| `--fail-rate` | v1 호환. 숨은 불합격(`OUT_OF_SPEC`)만 만듦 | 없음 |

```bash
python gen_A.py --reason-weights OUT_OF_SPEC=3,SUM_ONLY=2,DATE_CONFLICT=0
python gen_A.py --mix-weights 1=50,2=30,3=20
python gen_B.py --degrade original        # 열화본 없이 원본만 (빠름)
python gen_D.py --eval-rate 0.2
```

**6. 결과물 확인**
```
pdf/dev/original/COA_A_0001.pdf        원본 (글자 PDF)
pdf/dev/lowres/COA_A_0001_lowres.pdf   저해상도 72~90 dpi 회색조
pdf/dev/skew/COA_A_0001_skew.pdf       1.5~4° 기울기 + 옅은 잡음
pdf/dev/blur/COA_A_0001_blur.pdf       가우스 흐림 1.2~2.0 px
pdf/eval/...                           평가용 (같은 구조)
ground_truth.json                      정답 전체
ground_truth_docs.csv                  문서 1장 = 1줄
ground_truth_items.csv                 항목 1개 = 1줄
receipts.csv                           입고 정보 (판독 입력, 정답 칸 없음)
variants.csv                           PDF 목록 (file, doc_id, split, degrade, dpi, angle, blur_radius)
```
열화본에는 글자 레이어가 없어 OCR이 필요합니다. 정답은 원본과 같고 `doc_id`로 연결합니다. 같은 원본에서 만든 변형본은 개발용과 평가용에 나눠 넣지 않습니다.

**7. 결과 검증**
```bash
python verify_labels.py output_A_li2co3
```
정답 결과 문자열의 PDF 존재 여부, 판정 재계산, 로트 권고 규칙, 입고 불일치와 사유코드의 일치, 개발용/평가용 분리를 확인합니다. 탄산리튬·수산화리튬 × 양식 A·B·D 1,200장 검증에서 불일치는 0건이었습니다.

**8. 사유코드 12종**

`OUT_OF_SPEC`, `BOUND_ABOVE_LIMIT`, `ND_NO_LOD`, `ND_WITH_LOD`, `SPEC_COPIED`, `MISSING_REQUIRED`, `CONVERTED_OOS`, `SUM_ONLY`, `AMBIGUOUS_ANALYTE`, `DATE_CONFLICT`, `LOT_MISMATCH`, `MATERIAL_MISMATCH`

- 로트 권고는 부적합 항목이 있으면 부적합 권고, 판정 불가·확인 필요·누락 또는 문서/입고 사유가 있으면 보류 권고, 그 밖에는 적합 권고입니다.
- 정상 자동 처리율은 `is_normal=True` 문서 중 적합 권고가 나온 비율입니다.

**참고**
- 가상 규격(탄산리튬 `SYD-QS-LC-BG v1`, 수산화리튬 `SYD-QS-LHM-BG v1`)의 값 범위 근거는 `sources.md`에 있습니다. 정상 로트 범위(typical), 검출한계(LOD), D 양식 협력사 규격은 추정 또는 가상 값입니다.
- Windows에서는 아직 실행해 보지 않았습니다 (리눅스에서 확인).
- 이전 docx 기반 생성기는 `reference/coa-generator` 브랜치를 참고하세요.
