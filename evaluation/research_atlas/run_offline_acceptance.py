"""Reproducible software regressions; synthetic development fixtures, no AI calls."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["ATLAS_ENV_FILE"] = ""
os.environ["OFFLINE_MODE"] = "true"
os.environ["DASHSCOPE_API_KEY"] = ""

from app.db import projects as store  # noqa: E402
from app.models.research import FactRevisionRequest, StatusTransitionRequest  # noqa: E402
from app.research.comparison import compare_conditions  # noqa: E402
from tests.test_research_t1_storage import conn as database_fixture, link_paper, make_bundle, make_project, seed_snapshot  # noqa: E402
from tests.test_research_t3_comparison import CONSISTENT_DIMENSIONS, _change_second, dimension, image_bundle, request  # noqa: E402


def evaluate():
    conditions = []
    classes = ("compatible", "incompatible", "insufficient")
    matrix = {expected: {actual: 0 for actual in classes} for expected in classes}
    for name in CONSISTENT_DIMENSIONS:
        for expected in classes:
            bundle = image_bundle()
            if expected != "compatible":
                _change_second(bundle, name, missing=expected == "insufficient")
            result = dimension(compare_conditions(request(), bundle), name)
            actual = "compatible" if result.comparable else "insufficient" if "判断=信息不足" in result.reason else "incompatible"
            matrix[expected][actual] += 1
            conditions.append({"dimension": name, "expected": expected, "actual": actual, "detail": result.model_dump(mode="json")})

    impacts = []
    cases = [(kind, action) for kind in ("method", "setting", "measurement") for action in ("revision", "disputed", "withdrawn")]
    cases.append(("unrelated", "revision"))
    temporary = ROOT / ".tmp"
    temporary.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="submission-impact-", dir=temporary) as folder:
        for index, (kind, action) in enumerate(cases):
            case_dir = Path(folder) / str(index)
            case_dir.mkdir()
            fixture = database_fixture.__wrapped__(case_dir)
            conn = next(fixture)
            try:
                project = make_project(conn)
                link = link_paper(conn, project)
                snapshot, method = seed_snapshot(conn, project, link)
                ids = {"method": method.id, "setting": f"setting-{method.id}", "measurement": f"measurement-{method.id}"}
                if kind == "unrelated":
                    other = make_bundle(project.id, link.id, method_id="other-method")
                    store.save_candidate_bundle(conn, other)
                    ids[kind] = other.methods[0].id
                before = conn.execute("SELECT payload_json FROM research_snapshots WHERE snapshot_id=?", (snapshot.id,)).fetchone()[0]
                if action == "revision":
                    changes = {"dataset": "Changed synthetic dataset"} if kind == "setting" else {"value": None} if kind == "measurement" else {"name": "Changed synthetic method"}
                    store.revise_fact(conn, project.id, ids[kind], FactRevisionRequest(expected_version=1, changes=changes, actor="Synthetic regression", reason="Fault injection"))
                else:
                    store.transition_fact(conn, project.id, ids[kind], StatusTransitionRequest(expected_version=1, from_status="candidate", to_status=action, actor="Synthetic regression", reason="Fault injection"))
                after = store.get_snapshot(conn, project.id, snapshot.id)
                unchanged = conn.execute("SELECT payload_json FROM research_snapshots WHERE snapshot_id=?", (snapshot.id,)).fetchone()[0] == before
                impacts.append({"case": f"{kind}:{action}", "expected_affected": kind != "unrelated", "actual_affected": after.review_status.value == "needs_review", "frozen_payload_unchanged": unchanged})
            finally:
                conn.close()
                fixture.close()
    correct = sum(item["actual"] == item["expected"] for item in conditions)
    false_pass = sum(matrix[name]["compatible"] for name in ("incompatible", "insufficient"))
    tp = sum(item["expected_affected"] and item["actual_affected"] for item in impacts)
    fp = sum(not item["expected_affected"] and item["actual_affected"] for item in impacts)
    return {"fixture": "synthetic development regression", "independent_holdout": False, "human_effectiveness": False, "model_calls": 0,
            "condition_cases": conditions, "condition_metrics": {"correct": correct, "total": len(conditions), "accuracy": correct / len(conditions), "false_pass_count": false_pass, "non_comparable_count": 16, "false_pass_rate": false_pass / 16, "effective_judgment_coverage": (matrix["compatible"]["compatible"] + matrix["incompatible"]["incompatible"]) / 16, "confusion_matrix": matrix},
            "source_impact_cases": impacts, "source_impact_metrics": {"true_positive": tp, "false_positive": fp, "affected_cases": 9, "unrelated_cases": 1, "frozen_preserved": sum(item["frozen_payload_unchanged"] for item in impacts), "total": len(impacts)},
            "passed": correct == len(conditions) and tp == 9 and fp == 0 and all(item["frozen_payload_unchanged"] for item in impacts)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps({key: value for key, value in result.items() if not key.endswith("_cases")}, ensure_ascii=False))
    raise SystemExit(0 if result["passed"] else 1)
