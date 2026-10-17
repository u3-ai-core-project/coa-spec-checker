#!/usr/bin/env bash
# [담당: 고도영] Docker CPU 에서 엔진별 처리 시간·최대 메모리를 잰다 (가상 CoA 원본만, CPU 는 느리므로).
#   bash bench/docker_cpu.sh <엔진>            # 가상 3장
#   DOCS=COA_A_0007 bash bench/docker_cpu.sh qwen3.5-2b   # 1장만 (장당 몇 분 걸리는 모델)
# 다른 측정과 겹치면 시간이 몇 배로 늘어나므로 컴퓨터가 한가할 때 돌린다.
# 결과: data/generated/bench/results/<엔진>__docker-cpu.jsonl, 최대 메모리(MB)는 <엔진>.mem
set -euo pipefail
cd "$(dirname "$0")/.."
ENGINE=$1
DOCS=${DOCS:-COA_}
MODELS=${COA_BENCH_MODELS:-$HOME/.cache/coa-bench/models}
LLAMA_IMAGE=ghcr.io/ggml-org/llama.cpp:server-b11669
RESULTS=data/generated/bench/results
NAME=coa-bench-$ENGINE
mkdir -p "$RESULTS"

watch_mem() {  # 컨테이너 메모리 사용량을 2초마다 기록
  while docker inspect "$NAME" >/dev/null 2>&1; do
    docker stats --no-stream --format '{{.MemUsage}}' "$NAME" 2>/dev/null | awk '{print $1}' >> "$RESULTS/$ENGINE.mem.raw"
    sleep 2
  done
}

rm -f "$RESULTS/$ENGINE.mem.raw"
case $ENGINE in
  rapidocr|paddleocr|easyocr|tesseract)
    # PaddlePaddle 은 리눅스 arm64 휠이 없어 Apple Silicon 에서는 x86 에뮬레이션으로 돈다 (시간은 비교 불가)
    PLATFORM=()
    [ "$ENGINE" = paddleocr ] && PLATFORM=(--platform linux/amd64)
    docker build -q ${PLATFORM[@]+"${PLATFORM[@]}"} -f bench/Dockerfile.ocr --build-arg ENGINE="$ENGINE" -t "coa-bench-$ENGINE" . >/dev/null
    docker run -d ${PLATFORM[@]+"${PLATFORM[@]}"} --name "$NAME" -v "$PWD/data/generated/bench:/ai/data/generated/bench" "coa-bench-$ENGINE" \
      python bench/run.py "$ENGINE" --docs "$DOCS" --levels original --tag docker-cpu >/dev/null
    watch_mem &
    docker wait "$NAME" >/dev/null
    docker logs "$NAME" 2>&1 | grep -E "^\[|peak" || true
    ;;
  *)
    EXTRA=()
    CLIENT=bench/.venv/bin/python
    case $ENGINE in
      glm-ocr) M=GLM-OCR-Q8_0.gguf; P=mmproj-GLM-OCR-Q8_0.gguf ;;
      qwen3.5-2b) M=Qwen3.5-2B-Q4_K_M.gguf; P=mmproj-F16.gguf ;;
      lfm2.5-vl-450m) M=LFM2.5-VL-450M-Q8_0.gguf; P=mmproj-LFM2.5-VL-450m-F16.gguf ;;
      gemma4-e2b) M=gemma-4-E2B_q4_0-it.gguf; P=gemma-4-E2B-it-mmproj.gguf ;;
      paddleocr-vl) M=PaddleOCR-VL-1.6-GGUF.gguf; P=PaddleOCR-VL-1.6-GGUF-mmproj.gguf ;;
      surya) M=surya-2.gguf; P=surya-2-mmproj.gguf; CLIENT=bench/.venv-surya/bin/python
             EXTRA=(--alias datalab-to/surya-ocr-2 --jinja) ;;  # Surya 클라이언트가 모델 이름을 확인한다
      *) echo "unknown engine $ENGINE" >&2; exit 1 ;;
    esac
    docker run -d --name "$NAME" -p 8090:8080 -v "$MODELS:/models:ro" "$LLAMA_IMAGE" \
      -m "/models/$M" --mmproj "/models/$P" -c 16384 --temp 0 --host 0.0.0.0 --port 8080 \
      -t "${THREADS:-4}" -np 1 ${EXTRA[@]+"${EXTRA[@]}"} >/dev/null
    watch_mem &
    $CLIENT bench/run.py "$ENGINE" --docs "$DOCS" --levels original --tag docker-cpu \
      --base-url http://127.0.0.1:8090 | grep -E "^\[|samples" || true
    docker stop "$NAME" >/dev/null
    ;;
esac
sleep 3
docker rm -f "$NAME" >/dev/null 2>&1 || true
wait
python3 - "$RESULTS/$ENGINE.mem.raw" > "$RESULTS/$ENGINE.mem" <<'EOF'
import re, sys
mb = []
for line in open(sys.argv[1]):
    m = re.match(r"([\d.]+)([KMG]i?B)", line.strip())
    if m:
        mb.append(float(m.group(1)) * {"K": 1 / 1024, "M": 1, "G": 1024}[m.group(2)[0]])
print(round(max(mb)) if mb else "")
EOF
echo "docker peak memory: $(cat "$RESULTS/$ENGINE.mem") MB"
