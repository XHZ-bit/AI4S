"""The offline fixture is a provenance regression, not a scientific benchmark."""

import importlib.util
from pathlib import Path

import pytest


def _runner():
    path = Path(__file__).absolute().parents[2] / "evaluation" / "retrieval" / "evaluate_retrieval.py"
    spec = importlib.util.spec_from_file_location("offline_retrieval_baseline", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("force_scan", [False, True])
def test_offline_retrieval_and_exact_evidence_baseline(force_scan):
    report = _runner().evaluate_fixture(force_scan=force_scan)
    assert report["partition"] == "synthetic"
    assert report["query_count"] >= 10 and report["positive_query_count"] >= 8
    assert report["expected_evidence_count"] >= 8
    assert report["passed"], report["metrics"]
    assert report["metrics"]["invalid_citations"] == 0
    assert report["returned_citation_count"] > 0


def test_evaluation_counts_missing_retrieval_and_wrong_passage_as_failures(monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner.service, "lexical_search", lambda *args, **kwargs: [])
    report = runner.evaluate_fixture(force_scan=True)
    assert not report["passed"]
    assert report["metrics"]["recall_at_3"] == 0
    assert report["metrics"]["expected_evidence_accuracy"] == 0
    assert report["metrics"]["citation_integrity"] is None


def test_evaluation_detects_fabricated_citations(monkeypatch):
    runner = _runner()
    actual = runner.service.lexical_search

    def fabricated(*args, **kwargs):
        items = actual(*args, **kwargs)
        for item in items:
            if "quote" in item:
                item["quote"] = "This quote does not exist in any source."
        return items

    monkeypatch.setattr(runner.service, "lexical_search", fabricated)
    report = runner.evaluate_fixture(force_scan=True)
    assert not report["passed"]
    assert report["metrics"]["citation_integrity"] == 0
    assert report["metrics"]["invalid_citations"] > 0
