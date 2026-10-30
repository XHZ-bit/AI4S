"""Offline regression gate for source impact and comparison readiness.

The fixture is synthetic and the checks establish software behavior only.
"""

import argparse
import json
import tempfile
from contextlib import closing
from pathlib import Path

from prepare_browser_fixture import REPOSITORY_ROOT, prepare_fixture

from app.db.sqlite import connect
from app.research.impact import project_impact
from app.research.readiness import comparison_readiness
from app.workflow import activities, recommendations


def evaluate():
    temporary = REPOSITORY_ROOT / ".tmp"
    temporary.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="next-phase-", dir=temporary) as folder:
        fixture = prepare_fixture(Path(folder) / "fixture")
        with closing(connect(fixture["database_path"])) as conn:
            pid = fixture["project_id"]
            before = project_impact(conn, pid)
            readiness = comparison_readiness(conn, pid)
            assert readiness["total_pairs"] >= 1
            conn.execute("UPDATE passages SET text=? WHERE document_id=?",
                         ("fault injected: quoted source removed", fixture["document_id"]))
            conn.commit()
            changed = project_impact(conn, pid)
            broken = [issue for issue in changed["issues"] if issue["code"] == "quote_mismatch"]
            assert broken and changed["input_fingerprint"] != before["input_fingerprint"]
            assert fixture["snapshot_id"] in {item["id"] for issue in broken
                                               for item in issue["affected"] if item["kind"] == "snapshot"}
            assert any(item["status"] == "needs_review" for item in
                       activities(conn, "project", project_id=pid))
            assert any(item["kind"] == "source_review" for item in recommendations(conn)["items"])
            assert conn.execute("SELECT review_status FROM research_snapshots WHERE snapshot_id=?",
                                (fixture["snapshot_id"],)).fetchone()[0] == "current"
            return {"contract_version": "next-phase-evaluation-v1", "fixture": "synthetic",
                    "scientific_result": False, "checks": {
                        "source_mutation_detected": True,
                        "downstream_snapshot_identified": True,
                        "workflow_review_prompted": True,
                        "saved_history_unchanged": True,
                        "comparison_pairs_examined": readiness["total_pairs"],
                    }, "notice": "故障注入只检验软件行为，不证明科学结论或学习效果。"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
