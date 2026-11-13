"""[담당: 장수민] 모델 갱신 평가 통과 점검 테스트 (운영 정책 7장). DB 필요 없음."""
import json
import shutil
from pathlib import Path

import pytest

from evaluation import gate
from evaluation.run import main as run_eval

EXAMPLES = Path(__file__).resolve().parents[2] / "evaluation" / "examples"
POLICY = {"LOW_CONFIDENCE_THRESHOLD": 0.8}


@pytest.fixture
def reports(tmp_path):
    """예시 정답·출력으로 만든 평가 리포트 두 개 (이번, 직전). 정답 폴더는 tmp 로 복사해 경로가 리포트에 남게 한다."""
    gt = tmp_path / "gt"
    shutil.copytree(EXAMPLES / "gt", gt)
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(POLICY), encoding="utf-8")

    def make(name):
        out = tmp_path / name
        run_eval(["--gt", str(gt), "--pred", str(EXAMPLES / "pred"), "--out", str(out), "--policy", str(policy)])
        return out
    return make("new"), make("previous"), gt


def edit(folder: Path, fn):
    path = folder / "report.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    fn(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def run_gate(new, previous, *extra):
    return gate.main(["--new", str(new), "--previous", str(previous), *extra])


def test_gate_passes_when_nothing_gets_worse(reports, tmp_path, capsys):
    new, previous, _ = reports
    tuning = tmp_path / "tuning"
    tuning.mkdir()
    (tuning / "OTHER_999.json").write_text("{}", encoding="utf-8")
    code = run_gate(new, previous, "--invented-numbers", "0", "--tuning-gt", str(tuning))
    out = capsys.readouterr().out
    assert code == 0 and "[실패]" not in out and "[확인 못 함]" not in out


def test_unchecked_items_do_not_pass(reports, capsys):
    new, previous, _ = reports
    assert run_gate(new, previous) == 1
    out = capsys.readouterr().out
    assert out.count("[확인 못 함]") == 2


def test_gate_fails_on_hidden_fail_and_false_approval(reports, tmp_path, capsys):
    new, previous, _ = reports
    tuning = tmp_path / "t"
    tuning.mkdir()

    def worse(d):
        d["system"]["overall"]["judgement"]["hidden_fail_missed"] = 2
        d["system"]["overall"]["lot"]["confusion"] = {"reject": {"approve": 1}, "approve": {"approve": 3}}
    edit(new, worse)
    assert run_gate(new, previous, "--invented-numbers", "0", "--tuning-gt", str(tuning)) == 1
    out = capsys.readouterr().out
    assert "[실패] 부적합 → 적합 0건: 2건" in out and "[실패] 잘못된 승인 권고 0건: 1건" in out


def test_gate_fails_on_invented_numbers(reports, tmp_path):
    new, previous, _ = reports
    tuning = tmp_path / "t"
    tuning.mkdir()
    assert run_gate(new, previous, "--invented-numbers", "1", "--tuning-gt", str(tuning)) == 1


def test_gate_allows_small_drop_but_not_more_than_one_point(reports, tmp_path, capsys):
    new, previous, _ = reports
    tuning = tmp_path / "t"
    tuning.mkdir()
    args = ("--invented-numbers", "0", "--tuning-gt", str(tuning))
    edit(previous, lambda d: d["system"]["overall"]["extraction"].update(item_recall=0.95, value_accuracy=0.95))
    edit(new, lambda d: d["system"]["overall"]["extraction"].update(item_recall=0.94, value_accuracy=0.95))
    assert run_gate(new, previous, *args) == 0                       # 정확히 1%p 하락은 허용
    edit(new, lambda d: d["system"]["overall"]["extraction"].update(item_recall=0.93))
    assert run_gate(new, previous, *args) == 1
    assert "[실패] 항목 인식률 하락 1%p 이내" in capsys.readouterr().out


def test_gate_fails_when_tuning_data_overlaps_evaluation_data(reports, capsys):
    new, previous, gt = reports
    assert run_gate(new, previous, "--invented-numbers", "0", "--tuning-gt", str(gt)) == 1   # 같은 폴더를 보강에도 씀
    assert "겹치는 문서" in capsys.readouterr().out
