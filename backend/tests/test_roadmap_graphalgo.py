from app.roadmap.graphalgo import prerequisite_closure, topological_sort, prune_known

EDGES = [
    ("concept:td", "concept:actor-critic"),
    ("concept:actor-critic", "method:ppo"),
    ("concept:policy-gradient", "method:ppo"),
]


def test_prerequisite_closure():
    closure = prerequisite_closure(["method:ppo"], EDGES)
    assert closure == {"concept:td", "concept:actor-critic", "concept:policy-gradient", "method:ppo"}


def test_prerequisite_closure_multiple_targets():
    closure = prerequisite_closure(["concept:actor-critic", "method:ppo"], EDGES)
    assert "concept:td" in closure
    assert "concept:policy-gradient" in closure


def test_topological_sort_prerequisites_first():
    order = topological_sort(
        ["concept:td", "concept:actor-critic", "concept:policy-gradient", "method:ppo"], EDGES
    )
    assert order.index("concept:td") < order.index("concept:actor-critic")
    assert order.index("concept:actor-critic") < order.index("method:ppo")
    assert order.index("concept:policy-gradient") < order.index("method:ppo")


def test_topological_sort_cycle_returns_partial():
    cyclic = [("a", "b"), ("b", "a")]
    import pytest
    with pytest.raises(ValueError, match="cycle"):
        topological_sort(["a", "b"], cyclic)


def test_prune_known():
    order = ["concept:td", "concept:actor-critic", "method:ppo"]
    pruned = prune_known(order, {"concept:td"})
    assert pruned == ["concept:actor-critic", "method:ppo"]
