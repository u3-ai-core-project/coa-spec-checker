"""[담당: 고도영] LLM 후보를 같은 문제로 돌린다 (llama-server, OpenAI 호환 API, 온도 0).

    python bench/llm/run.py qwen3.5-2b                       # llama-server 를 직접 띄움 (맥 Metal)
    python bench/llm/run.py qwen3.5-2b --base-url http://127.0.0.1:8090 --tag docker-cpu --limit 5
    python bench/llm/run.py baseline                         # 규칙 베이스라인 (사전·규칙, 서버 판정 규칙)
    python bench/llm/run.py product-rules                    # 제품 코드(coa_ai), LLM 없이
    python bench/llm/run.py product --base-url http://127.0.0.1:8090   # 제품 코드 + LLM 서버 (ai/docker-compose.llm.yml)
결과: data/generated/bench/llm/<모델>[__태그].jsonl  (이미 푼 문제는 건너뛴다)
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
import cases  # noqa: E402

MODELS_DIR = Path(os.environ.get("COA_BENCH_MODELS", Path.home() / ".cache" / "coa-bench" / "models"))
MODELS = {
    "qwen3.5-2b": "Qwen3.5-2B-Q4_K_M.gguf",
    "lfm2.5-2.6b": "LFM2.5-2.6B-Q4_K_M.gguf",
    "gemma4-e2b": "gemma-4-E2B_q4_0-it.gguf",
}
OUT = cases.BENCH / "llm"
PRODUCT = ("product", "product-rules")  # 제품 코드(coa_ai.normalize·meaning·inquiry)를 그대로 돌린다
MATERIAL_KO = {"LI2CO3": "탄산리튬", "LIOH": "수산화리튬"}

NORM_SYSTEM = """너는 2차전지 원료 시험성적서(CoA)의 시험 항목명을 사내 표준 항목명으로 맞추는 도우미다.
규칙:
- 후보 목록에서 같은 측정 대상을 뜻하는 이름 하나를 고른다. 확실하지 않거나 후보에 없으면 "없음"을 고른다.
- 총량을 Pb 기준으로 적은 중금속(예: heavy metals as Pb)은 Pb 가 아니라 중금속이다.
- 산화물은 Na2O, CaO, Fe2O3 만 각 원소(Na, Ca, Fe)로 본다. 다른 산화물은 "없음".
- 시험 항목이 아닌 것(로트 크기, 분자량, 날짜 등)은 "없음".
JSON 으로만 답한다."""

VALUE_SYSTEM = """너는 CoA 결과 칸의 원문이 어떤 종류인지 분류한다. 규격 충족 여부(합격·불합격)는 판단하지 않는다.
종류:
- number: 측정값 숫자 (예: "12 ppm", "99.6 %")
- bound: 측정 결과를 부등호나 '미만·이하'로 보고한 것 (예: "< 1"). 규격과 숫자가 다르거나 규격보다 엄격한 부등호
- nd: 검출 안 됨 (예: "ND", "not detected")
- spec_copy: 결과 칸에 규격 조건을 다시 적은 것. 규격과 같은 숫자에 같은 뜻의 부등호면 표기가 달라도 복사 (예: 결과 "≤ 0.5 %", 규격 "0.5 % max")
- pass_text: 합격·적합·규격 충족을 말하는 문구
- description: 색·형태 등 서술
JSON 으로만 답한다. reason 에는 판단 근거를 한 줄로 쓴다."""

DRAFT_SYSTEM = """너는 2차전지 원료 입고 QC 담당자를 대신해 공급사에 보낼 CoA 확인 요청 메일 초안을 쓴다.
규칙:
- 입력의 요청 항목을 빠짐없이 로트별로 쓴다. 여러 로트는 메일 1통에 묶는다.
- 숫자, 로트 번호, CoA 원문 값은 입력에 있는 것만 그대로 옮긴다. 입력에 없는 숫자·날짜·기한·판정을 지어내지 않는다.
- 항목마다 무엇이 문제인지(why)와 무엇을 보내 주면 해결되는지(condition)를 쓴다.
- 정중한 한국어 업무 메일로 쓰고, 서명은 "[담당자 이름]"으로 둔다. 표(|)는 쓰지 않고 번호 목록으로 쓴다.
형식: 첫 줄에 "제목: ...", 빈 줄 다음에 본문."""


CANON_SYSTEM = """너는 CoA 표의 칸 원문 하나를 정규형으로 바꾼다. 비교하거나 합격 여부를 판단하지 않는다.
kind: value(숫자 하나, 앞에 부등호가 있을 수 있음), range(두 숫자로 된 범위), nd(검출 안 됨), pass_text(합격·적합 문구), description(색·형태 등 서술)
op: 숫자 앞 조건. "=", "<", "<=", ">", ">=" 중 하나. 말로 쓴 조건(예: "max" 는 "<=", "이상" 은 ">=")도 기호로 바꾼다. value 가 아니면 "".
number: 원문에 적힌 숫자를 글자 그대로 옮긴다 (range 는 아래쪽 숫자). value·range 가 아니면 "".
unit: 원문의 단위 (%, ppm 등). 없으면 "". 괄호 속 부가 설명은 무시한다.
JSON 으로만 답한다."""


def canon_prompt(c: dict) -> tuple[str, dict]:
    schema = {"type": "object", "properties": {
        "kind": {"type": "string", "enum": ["value", "range", "nd", "pass_text", "description"]},
        "op": {"type": "string", "enum": ["=", "<", "<=", ">", ">=", ""]},
        "number": {"type": "string"}, "unit": {"type": "string"}}, "required": ["kind", "op", "number", "unit"]}
    return f"칸 원문: {c['text']}", schema


def norm_prompt(c: dict) -> tuple[str, dict]:
    names = cases.standard_names(c["material"])
    lines = "\n".join(f"- {n}: {cases.MEANING.get(n, '')}" for n in names)
    user = f"원자재: {MATERIAL_KO[c['material']]}\n후보:\n{lines}\n\n항목명: {c['raw_name']}"
    schema = {"type": "object", "properties": {"name": {"type": "string", "enum": [*names, cases.NONE]}},
              "required": ["name"]}
    return user, schema


def value_prompt(c: dict) -> tuple[str, dict]:
    user = f"항목명: {c['raw_name']}\n결과 칸: {c['raw_value']}\n규격 칸: {c['raw_spec'] or '(없음)'}"
    schema = {"type": "object", "properties": {"kind": {"type": "string", "enum": cases.VALUE_KINDS},
                                               "reason": {"type": "string"}}, "required": ["kind", "reason"]}
    return user, schema


def draft_prompt(c: dict) -> tuple[str, dict]:
    lots = [{"lot_no": lot["lot_no"], "material_name": lot["material_name"],
             "requests": [{k: line[k] for k in ("target", "label", "why", "condition", "raw_value")} for line in lot["lines"]]}
            for lot in c["lots"]]
    user = json.dumps({"supplier": c["supplier"], "lots": lots}, ensure_ascii=False, indent=1)
    return user, None  # 긴 글을 JSON 틀에 넣게 하면 표 칸 반복 같은 퇴행이 잦아 일반 글로 받는다


def parse_draft(raw: str) -> dict:
    lines = raw.strip().splitlines()
    if not lines or not lines[0].lstrip("# *").startswith("제목"):
        raise ValueError("첫 줄에 제목 없음")
    subject = lines[0].lstrip("# *").split(":", 1)[-1].strip().strip("*").strip()
    return {"subject": subject, "body": "\n".join(lines[1:]).strip()}


TASKS = {  # 과제 → (문제, 지시문, 프롬프트, 최대 토큰)
    "norm": (cases.norm_cases, NORM_SYSTEM, norm_prompt, 64),
    "value": (cases.value_cases, VALUE_SYSTEM, value_prompt, 160),
    "draft": (lambda: cases.DRAFT_CASES, DRAFT_SYSTEM, draft_prompt, 1200),
    "canon": (cases.canon_cases, CANON_SYSTEM, canon_prompt, 80),
    "holdout": (cases.holdout_cases, VALUE_SYSTEM, value_prompt, 160),  # 규칙을 만들 때 보지 않은 의미 분류 문제
}


class Server:
    """llama-server 를 띄운다. 포트에 다른 서버가 남아 있으면 그 서버에 붙지 않고 멈춘다."""

    def __init__(self, model: str, port: int = 8095):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError(f"포트 {port} 에 이미 다른 서버가 떠 있음")
        self.base = f"http://127.0.0.1:{port}"
        log = open(Path(os.environ.get("TMPDIR", "/tmp")) / f"llama-llm-{model}.log", "w")
        self.proc = subprocess.Popen(
            ["llama-server", "-m", str(MODELS_DIR / MODELS[model]), "--port", str(port), "-c", "8192",
             "-ngl", "99", "--temp", "0", "--no-webui",
             # 생각(reasoning) 없이 바로 답하게 한다. LFM2.5 는 enable_thinking=False 를 무시하고 생각부터 해서
             # 출력 한도를 다 쓰고 답이 비었다. 세 모델 모두 같은 조건으로 둔다
             "--reasoning-budget", "0"], stdout=subprocess.DEVNULL, stderr=log)
        end = time.time() + 300
        while time.time() < end:
            if self.proc.poll() is not None:
                raise RuntimeError(f"llama-server 종료됨 ({model})")
            try:
                if requests.get(f"{self.base}/health", timeout=2).status_code == 200:
                    return
            except requests.RequestException:
                pass
            time.sleep(1)
        raise TimeoutError(model)

    def close(self):
        self.proc.terminate()
        self.proc.wait(timeout=30)


def chat(base: str, system: str, user: str, schema: dict | None, max_tokens: int) -> tuple[str, float]:
    t0 = time.perf_counter()
    r = requests.post(f"{base}/v1/chat/completions", timeout=1800, json={
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0, "max_tokens": max_tokens,
        **({"response_format": {"type": "json_schema", "json_schema": {"name": "out", "schema": schema}}}
           if schema else {}),
        "chat_template_kwargs": {"enable_thinking": False},
    })
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"], round(time.perf_counter() - t0, 2)


def case_id(task: str, c: dict) -> str:
    return f"{task}:" + (c.get("id") or "|".join(str(c.get(k)) for k in ("material", "raw_name", "raw_value", "raw_spec")))


def baseline(task: str, c: dict) -> dict:
    """규칙 베이스라인: 정규화 = coa_ai 사전·규칙·유사도, 의미 분류 = 서버 규칙(PR #5 value_parser) + 합격 문구 사전."""
    if task == "norm":
        from coa_ai.normalize import Normalizer
        name = Normalizer(c["material"]).map(c["raw_name"]).name
        return {"name": name if name in cases.standard_names(c["material"]) else cases.NONE}
    import baseline_rules  # value, holdout
    return {"kind": baseline_rules.kind(c["raw_value"], c["raw_spec"])}


def product(task: str, c: dict, llm) -> dict | None:
    """제품 경로: 정규화 = Normalizer(llm=), 의미 분류 = classify(), 초안 = draft_inquiry() (검사 실패는 fallback)."""
    if task == "norm":
        from coa_ai.normalize import Normalizer
        name = Normalizer(c["material"], llm=llm).map(c["raw_name"]).name
        return {"name": name if name in cases.standard_names(c["material"]) else cases.NONE}
    if task in ("value", "holdout"):
        from coa_ai.meaning import classify
        m = classify(c["raw_value"], c["raw_spec"], llm, raw_name=c["raw_name"])
        return {"kind": m.kind, "reason": m.reason}
    if task == "draft":
        from coa_ai.inquiry import InquiryDraftError, draft_inquiry
        try:
            subject, body = draft_inquiry(c["supplier"], cases.inquiry_lots(c), llm)
        except InquiryDraftError as e:
            return {"fallback": str(e)}
        return {"subject": subject, "body": body}
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("model", choices=[*MODELS, "baseline", *PRODUCT])
    ap.add_argument("--tasks", default="norm,value,draft")
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--tag", default="")
    ap.add_argument("--limit", type=int, default=0, help="과제마다 앞에서 이만큼만 (시간 측정용)")
    args = ap.parse_args()
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_, s=sig: sys.exit(128 + s))

    OUT.mkdir(parents=True, exist_ok=True)
    out_file = OUT / f"{args.model}{'__' + args.tag if args.tag else ''}.jsonl"
    done = set()
    if out_file.exists():
        done = {json.loads(line)["id"] for line in out_file.read_text().splitlines() if line.strip()}

    server, llm = None, None
    if args.model == "product":
        if not args.base_url:
            ap.error("product 는 --base-url (LLM 서버 주소) 가 필요하다")
        from coa_ai.llm import LLMClient
        llm = LLMClient(args.base_url, timeout=600)
    elif args.model not in ("baseline", "product-rules"):
        server = None if args.base_url else Server(args.model)
    base = args.base_url or (server.base if server else None)
    try:
        with out_file.open("a") as fh:
            for task in args.tasks.split(","):
                load, system, prompt, max_tokens = TASKS[task]
                todo = [c for c in load() if case_id(task, c) not in done]
                if args.limit:
                    todo = todo[:args.limit]
                print(f"{args.model} {task}: {len(todo)} cases", flush=True)
                for c in todo:
                    rec = {"id": case_id(task, c), "task": task, "case": c, "raw": None, "pred": None,
                           "seconds": None, "error": None}
                    if args.model == "baseline" or args.model == "product-rules":
                        if task in ("draft", "canon"):
                            continue
                        rec["pred"] = baseline(task, c) if args.model == "baseline" else product(task, c, None)
                    elif args.model == "product":
                        if task == "canon":
                            continue
                        t0 = time.perf_counter()
                        rec["pred"] = product(task, c, llm)
                        rec["seconds"] = round(time.perf_counter() - t0, 2)
                    else:
                        try:
                            user, schema = prompt(c)
                            rec["raw"], rec["seconds"] = chat(base, system, user, schema, max_tokens)
                            rec["pred"] = parse_draft(rec["raw"]) if task == "draft" else json.loads(rec["raw"])
                        except Exception as e:  # noqa: BLE001 — 실패도 결과로 남긴다
                            rec["error"] = f"{type(e).__name__}: {e}"
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    fh.flush()
    finally:
        if server:
            server.close()


if __name__ == "__main__":
    main()
