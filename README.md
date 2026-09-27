### 가상 CoA 생성기 실행 방법

**1. 가상환경 생성 및 활성화**
```bash
cd coa-spec-checker
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
```

**2. 의존성 설치**
```bash
pip install --upgrade pip   # Windows : python -m pip install --upgrade pip
pip install python-docx
```

**2-1. PDF 변환 도구 설치 (PDF가 필요할 때만)**

`--pdf` 옵션을 쓰려면 아래 둘 중 하나가 필요합니다. LibreOffice가 설치돼 있으면 그것을 먼저 사용하고, 없으면 MS Word(docx2pdf)로 변환합니다.
* [libreoffice.org](https://www.libreoffice.org/download/download/) 에서 LibreOffice 설치
* 또는 MS Word가 설치된 PC에서 아래 명령 실행
```bash
pip install docx2pdf
```
둘 다 없으면 PDF 없이 docx와 정답 파일만 만들어집니다.

**3. 실행**
```bash
# 기본 (20장 생성)
python generate_coa.py

# 개수 지정 + PDF 생성
python generate_coa.py --count 100 --pdf

# Windows 배치 파일 사용 시 (python-docx 자동 설치, 개수와 PDF 여부를 물어봄)
run
```
`generate_coa.py`와 `CoA_Form.docx`는 반드시 같은 폴더에 있어야 합니다.

**3-1. 주요 옵션**

| 옵션 | 설명 | 기본값 |
|---|---|---|
| `--count N` | 만들 CoA 개수 | 20 |
| `--seed S` | 난수 시드 (같은 시드면 항상 같은 결과) | 42 |
| `--fail-rate R` | 규격 이탈 CoA 비율 0~1 (생략 시 공급사별 설정, 평균 약 20%) | 공급사별 |
| `--start` / `--end` | 제조일 범위 `YYYY-MM-DD` | 2025-09-01 ~ 2026-08-31 |
| `--template` | 양식 파일 경로 | `CoA_Form.docx` |
| `--out` | 결과 폴더 | `output` |
| `--pdf` | PDF도 생성 | 사용 안 함 |

**4. 결과 확인**
```
output/
├─ docx/COA_0001.docx ...    채워진 CoA
├─ pdf/COA_0001.pdf ...      (--pdf 사용 시)
├─ ground_truth.json         문서별 전체 정답 (필드 + 항목별 결과 + 합/불)
└─ ground_truth.csv          문서 x 시험항목 한 줄씩 (엑셀에서 바로 열림)
```
다시 실행하면 `output` 안의 기존 `COA_숫자` 파일은 지워지고 새로 만들어집니다.
