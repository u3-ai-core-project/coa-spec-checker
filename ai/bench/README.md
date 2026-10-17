# 모델 테스트 (스캔본·이미지 CoA 추출 엔진 선정)

[담당: 고도영] 「AI 추출 파이프라인 개발계획」 참고 사항 2·3번의 후보 10개(OCR 5개, VLM 5개)를 같은 샘플로 비교한다.

## 샘플과 정답

- 문서 38건: 가상 CoA 3장(A·B·D, 수산화리튬) + 실물 CoA 35건(탄산리튬·수산화리튬, Fisher 양식 A~D, Alfa, Puratronic, 대정화금(한글), Piochem)
  - 실물 42건 중 CoA가 아닌 7건(규격서·공시·앱노트·Nanotrun 웹페이지)은 뺐다.
- 열화 4단계(임시값, 소성훈 님 열화 조건 표를 받으면 바꾼다): `samples.py` 의 `LEVELS`
  - 원본: 200 dpi
  - 저해상도: 100 dpi
  - 기울기: 200 dpi, 2° 회전
  - 흐림: 200 dpi, 가우시안 블러 반경 1.5
- 정답: 같은 PDF 를 텍스트 경로(`coa_ai.extract`)로 읽은 결과. 텍스트 PDF 라 글자가 정확하고, 가상 3장은 정답 라벨과 같음을 확인했다.
- 실물 CoA 와 거기서 만든 이미지·결과는 라이선스 문제로 저장소에 넣지 않는다 (`ai/data/generated/bench/`, gitignore 대상).

## 채점 (`score.py`, 홍채령 님 채점 스크립트를 받기 전 임시)

- 항목 인식률: 정답 항목 중 같은 표준 항목명으로 찾은 비율. 엔진 출력의 항목명은 텍스트 경로와 같은 `Normalizer` 로 정규화한다.
- 수치 일치율: 정답 항목 중 찾았고 결과 값도 같은 비율. 숫자 목록과 앞의 부등호(<, ≤, >, ≥)가 같으면 일치, 숫자가 없으면 글자만 비교한다.
- 머리글 일치율: 정답에 값이 있는 필드 중 맞힌 비율. `lot_no`·`test_date` 는 정확히 같아야 하고, `supplier`·`origin`·`applied_standard` 는 한쪽이 다른 쪽을 포함하면 맞은 것으로 본다.

## 엔진 구성

| 방식 | 엔진 | 실행 |
| --- | --- | --- |
| OCR + 규칙 | RapidOCR, PaddleOCR, EasyOCR, Tesseract, Surya | OCR 글줄·단어 좌표를 텍스트 PDF 와 같은 표 복원·머리글·정규화 규칙에 넣는다 |
| VLM 단독 | GLM-OCR, Qwen3.5-2B, LFM2.5-VL-450M, Gemma 4 E2B | llama-server + 이미지 + 지시문 → JSON (`engines.PROMPT`, JSON 스키마 제약) |
| VLM + 규칙 | PaddleOCR-VL-1.6 | 지시문을 받지 않고 작업 이름만 받으므로 출력 글·표를 규칙에 넣는다 |

모델별 조정
- GLM-OCR: 일반 지시문으로는 열을 한 칸씩 밀려 읽어서, 모델 카드의 정보 추출 형식(`请按下列JSON格式输出图中信息:` + JSON 틀)을 쓴다.
- VLM JSON 틀에는 `method`(시험법) 칸을 넣었다. 없으면 시험법 열을 결과로 읽는 일이 있었다. 채점에는 쓰지 않는다.
- RapidOCR·PaddleOCR: 검출 상자를 글줄 높이의 10% 줄이고 글줄 방향 분류를 끈다 (`engines.RapidOcrEngine` 설명). 이 두 값은 이번 샘플을 보고 정했으므로 기본 설정 결과도 같이 싣는다.
- RapidOCR 스레드는 4개로 둔다. 기본값(코어 수)은 M4·Docker 에서 2~3배 느렸다.
- RapidOCR 에 PaddleOCR 원본과 같은 모델(PP-OCRv6 medium 검출·인식의 ONNX 판, `--model medium`)과 같은 검출 설정(`--paddle-params`, `engines.RapidOcrEngine.PADDLE_PARAMS`)을 넣은 결과도 싣는다. 아래 'PaddleOCR 모델의 ONNX 판' 참고.

## 실행

```bash
cd ai
python -m venv bench/.venv && bench/.venv/bin/pip install -r bench/requirements.txt
brew install llama.cpp                       # VLM·Surya 용 llama-server
bench/.venv/bin/python bench/samples.py      # 이미지 152장 + 정답
bench/.venv/bin/python bench/run.py rapidocr # 엔진별 실행 (중간에 멈추면 이어서 돈다)
bench/.venv/bin/python bench/score.py        # 결과표
bash bench/docker_cpu.sh rapidocr            # Docker CPU 시간·메모리 (가상 3장 원본)
bench/.venv/bin/python bench/run.py rapidocr --model medium --paddle-params --tag medium-pdet   # PaddleOCR 모델의 ONNX 판
```

모델 파일은 `~/.cache/coa-bench/models` 에 둔다 (`COA_BENCH_MODELS` 로 바꿀 수 있음).

의존성이 서로 부딪혀 엔진별 가상환경을 따로 둔다: `bench/.venv-paddle`(`paddlepaddle`, `paddleocr`), `bench/.venv-easyocr`(`easyocr`), `bench/.venv-surya`(`surya-ocr`). Tesseract 는 `brew install tesseract tesseract-lang` + `pytesseract`.
`bench/rescore.py` 는 변환 코드를 고친 뒤 저장된 모델 원출력으로 다시 채점하고, `bench/report.py` 는 문서별 채점표, `bench/table.py` 는 위 결과표를 낸다.

## 결과 (1단계, 2026-10-17)

10개 후보가 모두 끝낸 47장 기준이다 (실물·가상 원본 38장 + 가상 3장의 열화 3단계 9장). 느린 모델의 나머지 열화 샘플(모델당 105장)은 2단계로 이어서 돌린다.

| 후보 | 항목 인식률 | 수치 일치율 | 머리글 일치율 | 처리 시간/장 (Docker CPU) | 최대 메모리 | Docker 실행 확인 |
| --- | --- | --- | --- | --- | --- | --- |
| RapidOCR (PP-OCR ONNX) | 91.2% | 90.6% | 99.5% | 3초 | 0.6GB | O |
| RapidOCR 기본 설정 | 79.6% | 77.7% | 99.5% | 3초 | 0.6GB | O |
| RapidOCR + PP-OCRv6 medium | 93.9% | 91.0% | 100.0% | 19초 | 1.2GB | O |
| RapidOCR + PP-OCRv6 medium + PaddleOCR 검출 설정 | 96.4% | 95.8% | 100.0% | 30초 | 1.8GB | O |
| PaddleOCR | 96.4% | 95.8% | 100.0% | 157초 (x86 에뮬레이션) | 3.1GB | △ arm64 휠 없음, x86 만 |
| EasyOCR | 57.8% | 39.5% | 69.1% | 33초 | 3.8GB | O |
| Tesseract | 68.3% | 65.0% | 90.7% | 2초 | 0.2GB | O |
| Surya 2 | 99.4% | 99.4% | 100.0% | 478초 | 2.2GB | O |
| GLM-OCR | 68.3% | 51.0% | 61.9% | 544초 | 4.1GB | O |
| Qwen3.5-2B | 93.3% | 79.2% | 79.4% | 654초 | 4.0GB | O |
| LFM2.5-VL-450M | 37.9% | 20.8% | 58.2% | 15초 | 1.1GB | O |
| Gemma 4 E2B | 89.4% | 56.7% | 52.1% | 825초 | 5.5GB | O |
| PaddleOCR-VL-1.6 | 87.7% | 78.7% | 80.4% | 1025초 | 2.3GB | O |

- 처리 시간: Docker(맥 M4, 리눅스 arm64, 스레드 4개)에서 가상 CoA 원본으로 잰 값. 장당 2분이 넘는 모델은 1장, 나머지는 3장의 중앙값이다. 다른 작업이 없을 때 쟀다.
- RapidOCR 기본 설정의 시간·메모리는 같은 엔진 값이다.

### PaddleOCR 모델의 ONNX 판

PaddleOCR 3.7 은 PP-OCRv6 medium 검출·인식 모델을 쓰고, RapidOCR 은 같은 모델의 ONNX 판을 내려받아 쓸 수 있다 (`multi_PP-OCRv6_{det,rec}_medium.onnx`).

- 모델만 바꾸면 93.9% 였다. 남은 차이는 가상 B 저해상도·흐림(1/17)과 가상 D 저해상도 값(5/20)이다. 글자는 바르게 읽었지만, 검출 상자가 PaddleOCR 보다 커서 '번호' 열의 `1` 과 항목명 `外观 Appearance` 가 한 구로 붙었다.
- 원인은 두 엔진의 검출 설정 차이다 (PaddleOCR: `paddlex/configs/pipelines/OCR.yaml`).

  | 설정 | PaddleOCR 3.7 | RapidOCR 3.10 기본 |
  | --- | --- | --- |
  | 이미지 긴 변 상한 | 4000 | 2000 |
  | 정규화 | ImageNet 평균·표준편차 | 0.5 / 0.5 |
  | 상자 팽창(dilation) | 끔 | 켬 |
  | box_thresh / unclip_ratio | 0.6 / 1.5 | 0.5 / 1.6 |
  | 인식 점수 하한 | 0.0 | 0.5 |

- 이 값을 PaddleOCR 과 같게 맞추면 47장 모두 문서별 점수가 PaddleOCR 원본과 하나도 다르지 않다 (96.4 / 95.8 / 100).
- Docker 에서는 PaddleOCR 원본보다 가볍다: 장당 30초, 1.8GB, `pip install rapidocr onnxruntime` 만으로 설치되고 arm64·x86 모두 그대로 돈다. PaddleOCR 원본은 리눅스 arm64 휠이 없어 이 맥에서는 x86 에뮬레이션(157초)으로만 돈다.
- small 모델(3초)보다 10배 느린 것은 모델 크기와 원본 해상도 처리 때문이다.
- 열화 샘플까지 152장 전체 (항목 / 값 / 머리글):

  | RapidOCR 구성 | 전체 | 원본 | 저해상도 | 기울기 | 흐림 |
  | --- | --- | --- | --- | --- | --- |
  | small | 90.8 / 90.1 / 99.8 | 92.0 / 91.2 | 90.6 / 89.8 | 91.4 / 90.8 | 89.3 / 88.5 |
  | medium | 95.1 / 93.6 / 100 | 98.2 / 97.5 | 93.4 / 89.6 | 95.5 / 94.7 | 93.4 / 92.6 |
  | medium + PaddleOCR 검출 설정 | 96.6 / 95.8 / 99.1 | 95.3 / 94.5 | 96.5 / 95.7 | 97.7 / 97.1 | 96.9 / 96.1 |

  - PaddleOCR 검출 설정은 열화 샘플(가상 B·D, Piochem)에서 낫고, 원본에서는 Puratronic S29G083 한 건에서 15항목을 더 놓친다. 이 문서는 PaddleOCR 원본도 35/55 다.
  - 그 원인은 OCR 이 아니라 규칙 쪽이다. 한 줄에 '원소 값' 쌍이 5개씩 있는 표에서 검출기가 `< 1` 상자 하나를 놓치자(box_thresh 0.6), 표 복원이 그 블록의 3행을 통째로 버렸다. 칸이 하나 빠져도 나머지 행은 살리도록 `coa_ai.table` 을 보강할 과제다.
  - Fisher 양식 D 저해상도 5장에서는 시험일을 놓치고 공급사를 'Thermo Fisher Scientific' 으로 읽어 머리글 일치율이 99.1% 로 내려갔다.

### 오류 유형

- Qwen3.5-2B: Fisher 양식 A 의 결과 칸 `=<20 ppm`(규격 문구를 복사한 결과)을 `<20 ppm` 으로 읽는다. '이하'가 '미만'으로 바뀌고, 규격 복사 탐지 목표와 정면으로 어긋난다.
- Gemma 4 E2B: 자릿수를 틀리거나(`0.00004` → `0.0004`) 결과 칸에 규격을 넣는다. 그럴듯한 틀린 값이라 신뢰도로 걸러지지 않는다.
- GLM-OCR·PaddleOCR-VL: 빈 칸(Min 없는 행)을 빼먹어 열이 밀린다 (가상 D). PaddleOCR-VL 은 'Table Recognition:' 이 표만 읽어 표 밖 머리글을 놓친다.
- LFM2.5-VL-450M: 머리글 표(Lot Size, Packing)를 시험 항목으로 읽는다. 모델 카드에도 세밀한 OCR 에는 맞지 않는다고 적혀 있다.
- EasyOCR·Tesseract: 중·영 혼합(가상 B)과 열화(저해상도·기울기·흐림)에서 크게 떨어진다.
- PaddleOCR·RapidOCR: 남은 오류는 대부분 한글 문서(대정화금)다. 기본 인식 모델에 한국어가 없어 '이하'를 '0|' 로 읽는다. 한국어 모델(korean PP-OCRv5)로 바꾸면 대정화금 4단계 모두 7/7 이었다.
- Surya: 원본 38장에서 값 오류 0건. 놓친 항목은 Alfa 13418 두 건(각 9개 중 1개)과 36225(11개 중 2개)뿐이다.

### 결론 (제안)

1. 스캔본 경로는 'OCR + 기존 표 복원 규칙'으로 간다. VLM 이 표를 직접 JSON 으로 내는 방식은 숫자·부등호를 바꾸는 오류가 있어 원문 그대로 전달 원칙과 맞지 않는다.
2. Docker CPU 기본 엔진은 RapidOCR + PP-OCRv6 medium(ONNX) + PaddleOCR 검출 설정. PaddleOCR 원본과 정확도가 같고(96.4%), 장당 30초·1.8GB 에 pip 만으로 설치된다. 처리 시간이 더 중요하면 RapidOCR small(3초, 91.2%)로 바꿀 수 있다.
3. 한글 문서는 한국어 인식 모델로 보내는 단계를 넣는다 (첫 OCR 결과의 한글 비율 등으로 판단).
4. GPU 가 있으면 Surya 2 가 가장 정확하다 (99.4%). CPU 에서는 장당 8분이라 데모 로트를 미리 처리해 두는 용도 정도다. 가중치는 수정 OpenRAIL-M (연구·개인·매출 500만 달러 미만 무료).

### 한계

- 실물 CoA 는 모두 텍스트 PDF 를 이미지로 바꾼 것이라 실제 스캔본보다 깨끗하다. 열화 값도 임시값이다.
- 정답은 사람이 만든 라벨이 아니라 텍스트 경로 추출 결과다 (가상 3장만 정답 라벨과 대조).
- RapidOCR·PaddleOCR 의 상자 축소(10%)·방향 분류 끄기, Tesseract 의 줄 높이 보정, Surya·PaddleOCR-VL 의 HTML/OTSL → Page 변환은 이번 샘플을 보며 맞췄다. Surya·PaddleOCR-VL 은 변환 코드를 고친 뒤 저장해 둔 모델 원출력으로 다시 채점했다 (`rescore.py`).
- VLM 지시문은 하나로 고정했다. 모델별로 지시문을 다듬으면 달라질 수 있다.
- Docker 시간은 맥 arm64 기준이다. 팀 PC(x86)에서는 다를 수 있고, PaddleOCR 은 이 맥에서 x86 에뮬레이션으로만 돈다.
- RapidOCR(ONNX)와 PaddleOCR 원본이 똑같다는 것은 47장(1단계)에서 확인했다. PaddleOCR 원본의 152장 결과는 2단계가 끝나면 비교한다.
