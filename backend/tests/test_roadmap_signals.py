from app.roadmap.signals import (
    signal_a_sparse_comparisons, signal_b_improves_on_terminal,
    signal_c_benchmark_gap, collect_suggestions,
)


def test_signal_a_sparse_but_cited():
    methods = [
        {"uid": "method:x", "name": "X", "compared_with_count": 0, "citation_count": 30},
        {"uid": "method:y", "name": "Y", "compared_with_count": 5, "citation_count": 30},
        {"uid": "method:z", "name": "Z", "compared_with_count": 1, "citation_count": 5},
    ]
    out = signal_a_sparse_comparisons(methods)
    uids = [m["uid"] for m in out]
    assert "method:x" in uids
    assert "method:y" not in uids
    assert "method:z" not in uids


def test_signal_b_terminal_methods():
    methods = [
        {"uid": "method:old", "name": "Old", "improves_on_successors": 2},
        {"uid": "method:new", "name": "New", "improves_on_successors": 0},
    ]
    out = signal_b_improves_on_terminal(methods)
    assert [m["uid"] for m in out] == ["method:new"]


def test_signal_c_benchmark_gap():
    benchmarks = [
        {"uid": "benchmark:hard", "name": "HardBench", "method_count": 1},
        {"uid": "benchmark:easy", "name": "EasyBench", "method_count": 10},
    ]
    out = signal_c_benchmark_gap(benchmarks)
    assert [b["uid"] for b in out] == ["benchmark:hard"]


def test_collect_suggestions_has_evidence():
    methods = [{"uid": "method:new", "name": "New", "compared_with_count": 0, "citation_count": 20, "improves_on_successors": 0}]
    benchmarks = [{"uid": "benchmark:hard", "name": "HardBench", "method_count": 1}]
    suggestions = collect_suggestions(methods, benchmarks)
    assert len(suggestions) >= 2
    for s in suggestions:
        assert "title" in s and "rationale" in s and "evidence" in s
