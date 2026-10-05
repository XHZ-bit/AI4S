def signal_a_sparse_comparisons(methods: list[dict]) -> list[dict]:
    out = []
    for m in methods:
        if m.get("compared_with_count", 0) <= 1 and m.get("citation_count", 0) >= 10:
            out.append({**m, "signal_type": "a"})
    return out


def signal_b_improves_on_terminal(methods: list[dict]) -> list[dict]:
    out = []
    for m in methods:
        if m.get("improves_on_successors", 0) == 0:
            out.append({**m, "signal_type": "b"})
    return out


def signal_c_benchmark_gap(benchmarks: list[dict]) -> list[dict]:
    out = []
    for b in benchmarks:
        if b.get("method_count", 0) <= 2:
            out.append({**b, "signal_type": "c"})
    return out


def collect_suggestions(methods: list[dict], benchmarks: list[dict]) -> list[dict]:
    suggestions = []
    for m in signal_a_sparse_comparisons(methods):
        suggestions.append({
            "title": f"对{m['name']}的对比研究不足",
            "rationale": f"{m['name']}引用数{m.get('citation_count', 0)}但COMPARED_WITH边仅{m.get('compared_with_count', 0)}条",
            "evidence": "signal_a",
        })
    for m in signal_b_improves_on_terminal(methods):
        suggestions.append({
            "title": f"{m['name']}是改进链末端，可作新baseline",
            "rationale": f"{m['name']}无IMPROVES_ON后继，存在改进空间",
            "evidence": "signal_b",
        })
    for b in signal_c_benchmark_gap(benchmarks):
        suggestions.append({
            "title": f"benchmark {b['name']}上方法覆盖薄弱",
            "rationale": f"{b['name']}仅{b.get('method_count', 0)}个方法评测",
            "evidence": "signal_c",
        })
    return suggestions
