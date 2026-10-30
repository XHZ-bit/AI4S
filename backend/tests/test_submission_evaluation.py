import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("submission_scorer", ROOT / "evaluation/research_atlas/evaluate.py")
scorer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scorer)


def record(checks):
    value = json.loads((ROOT / "evaluation/research_atlas/fixtures/synthetic_annotations.jsonl").read_text(encoding="utf-8").splitlines()[0])
    value = copy.deepcopy(value)
    value["condition_checks"] = checks
    return value


def test_abstention_does_not_inflate_effective_coverage():
    checks = [{"expected": expected, "actual": "insufficient"} for expected in ["compatible", "incompatible", "insufficient"]]
    result = scorer.evaluate([record(checks)])
    assert result["condition_check_accuracy"] == 0.333333
    assert result["condition_checks"]["effective_judgment_coverage"] == 0
    assert result["condition_checks"]["false_pass_rate"] == 0
    assert result["condition_checks"]["determinable_count"] == 2


def test_false_pass_counts_insufficient_and_conflicting_inputs():
    checks = [{"expected": expected, "actual": "compatible"} for expected in ["compatible", "incompatible", "insufficient"]]
    result = scorer.evaluate([record(checks)])["condition_checks"]
    assert result["false_pass_count"] == 2
    assert result["false_pass_rate"] == 1
    assert result["effective_judgment_coverage"] == 0.5
    assert result["confusion_matrix_expected_by_actual"]["insufficient"]["compatible"] == 1
    empty = scorer.evaluate([record([])])["condition_checks"]
    assert empty["false_pass_rate"] is None and empty["effective_judgment_coverage"] is None


def test_local_http_diagnostics_do_not_load_the_windows_tls_store(monkeypatch):
    from app.api import system

    def no_tls():
        raise AssertionError("HTTP probe must not load TLS roots")

    monkeypatch.setattr(system, "_tls_context", no_tls)
    assert system.parser_status()["status"] == "fallback"
