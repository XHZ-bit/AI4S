"""Reproducible fault injection and structural baselines for the second demo.

The source corpus is pinned, but the expected teaching order is an authored
fixture, not an independent scientific or user-outcome gold standard.
"""

# ruff: noqa: E402 -- evaluation scripts add backend to sys.path before app imports.

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.db.proposals import save_proposal
from app.db.sqlite import connect
from app.main import app
from app.models.roadmap import LearnerProfile
from app.roadmap.auto_evaluate import evaluate_candidates
from app.roadmap.generate import generate_roadmap
from app.roadmap.trusted_queries import get_papers_for_concept
from fastapi.testclient import TestClient

TARGET = "method:diffusion-policy"
PROFILES = {
    "robotics": ["Imitation learning"],
    "generative_models": ["Diffusion models"],
}


def cloned(base_path, destination):
    with sqlite3.connect(base_path) as source, sqlite3.connect(destination) as target:
        source.backup(target)
    return connect(str(destination))


def routes(conn):
    output = {}
    for name, known in PROFILES.items():
        result = generate_roadmap(
            LearnerProfile(goal="Understand Diffusion Policy", target_uid=TARGET, known_concepts=known),
            conn, status="demo_curated", persist=False,
        )
        output[name] = {
            "phases": [phase.title for phase in result.phases],
            "papers": [item.uid for phase in result.phases for item in phase.items],
            "evidence_ids": [pid for phase in result.phases for item in phase.items for pid in item.evidence_ids],
        }
    return output


def inject_cycle(conn):
    dp_uid = "arxiv-2303.04137v4"
    passage = conn.execute(
        "SELECT k.document_id,k.passage_id,k.quote,k.start_offset,k.end_offset "
        "FROM knowledge k WHERE k.paper_uid=? AND k.layer='teaching' LIMIT 1", (dp_uid,)
    ).fetchone()
    nodes = [("concept:imitation-learning", "Imitation learning"),
             ("concept:diffusion-models", "Diffusion models")]
    for src, dst in ((nodes[0], nodes[1]), (nodes[1], nodes[0])):
        payload = {"rel_type": "PREREQUISITE_OF", "src_uid": src[0], "src_name": src[1],
                   "src_type": "concept", "dst_uid": dst[0], "dst_name": dst[1],
                   "dst_type": "concept", "passage_id": passage["passage_id"],
                   "evidence": passage["quote"]}
        kid = save_proposal(conn, dp_uid, "relation", payload, 0.0)
        conn.execute(
            "INSERT INTO knowledge(id,paper_uid,document_id,passage_id,quote,start_offset,end_offset,layer,status) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (kid, dp_uid, passage["document_id"], passage["passage_id"],
             passage["quote"], passage["start_offset"], passage["end_offset"],
             "teaching", "demo_curated"),
        )
    conn.commit()


def inject_semantic_swap(conn):
    row = conn.execute(
        "SELECT p.id,p.payload_json FROM extraction_proposals p JOIN knowledge k ON k.id=p.id "
        "WHERE k.layer='teaching' ORDER BY p.id LIMIT 1"
    ).fetchone()
    payload = json.loads(row["payload_json"])
    payload["src_uid"] = "concept:diffusion-models"
    payload["src_name"] = "Diffusion models"
    conn.execute("UPDATE extraction_proposals SET payload_json=? WHERE id=?",
                 (json.dumps(payload, ensure_ascii=False), row["id"]))
    conn.commit()


def preview_status(path, known):
    with patch("app.api.roadmap._connect", lambda: connect(str(path))):
        response = TestClient(app).post(
            "/api/roadmap/preview",
            json={"profile": {"goal": "Understand Diffusion Policy", "target_uid": TARGET,
                              "known_concepts": known}},
        )
    return response.status_code


def fault_trial(base_path, root, name, mutation):
    path = root / f"{name}.db"
    conn = cloned(base_path, path)
    try:
        mutation(conn)
        report = evaluate_candidates(conn, TARGET, PROFILES)
        try:
            after = routes(conn)
        except ValueError as exc:
            after = {"error": str(exc)}
        return {"gate_passed": report["passed"],
                "preview_http_status": preview_status(path, PROFILES["robotics"]),
                "failures": report["failures"],
                "ungated_planner_routes_diagnostic": after}
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf-dir", type=Path, help="optional offline cache; otherwise fetch pinned PDFs")
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    work = args.work_dir.resolve()
    if work.exists() and any(work.iterdir()):
        raise SystemExit("work directory must be new and empty")
    work.mkdir(parents=True, exist_ok=True)
    seed = work / "seed"
    prepare = [sys.executable, str(ROOT / "backend/scripts/prepare_second_demo.py"),
               "--data-dir", str(seed)]
    if args.pdf_dir:
        prepare += ["--pdf-dir", str(args.pdf_dir.resolve())]
    prepared = subprocess.run(prepare, cwd=ROOT, capture_output=True, text=True)
    if prepared.returncode:
        raise SystemExit("source preparation failed:\n" + prepared.stderr.strip())
    base_path = seed / "atlas.db"
    conn = connect(str(base_path))
    try:
        base_gate = evaluate_candidates(conn, TARGET, PROFILES)
        base_routes = routes(conn)
        paper_ids = [r["uid"] for r in conn.execute("SELECT uid FROM papers ORDER BY uid")]
        target_papers = [p["uid"] for p in get_papers_for_concept(conn, TARGET, "demo_curated")]
        evidence_ok = all(conn.execute("SELECT 1 FROM passages WHERE id=?", (pid,)).fetchone()
                          for route in base_routes.values() for pid in route["evidence_ids"])
    finally:
        conn.close()
    baseline_http = {name: preview_status(base_path, known) for name, known in PROFILES.items()}
    mutations = {
        "altered_quote": lambda c: (c.execute("UPDATE knowledge SET quote='fabricated' WHERE id=(SELECT min(id) FROM knowledge)"), c.commit()),
        "wrong_document": lambda c: (c.execute("UPDATE knowledge SET document_id=(SELECT id FROM documents WHERE paper_uid='arxiv-2006.11239v2' LIMIT 1) WHERE id=(SELECT min(id) FROM knowledge)"), c.commit()),
        "invalid_endpoint": lambda c: (c.execute("UPDATE extraction_proposals SET payload_json=json_set(payload_json,'$.src_type','method') WHERE id=(SELECT min(id) FROM knowledge)"), c.commit()),
        "missing_passage": lambda c: (c.execute("UPDATE knowledge SET passage_id='missing' WHERE id=(SELECT min(id) FROM knowledge)"), c.commit()),
        "prerequisite_cycle": inject_cycle,
        "withdrawn_prerequisite": lambda c: (c.execute("UPDATE knowledge SET status='withdrawn' WHERE id=(SELECT min(id) FROM knowledge WHERE layer='teaching')"), c.commit()),
        "semantic_swap": inject_semantic_swap,
    }
    trials = {name: fault_trial(base_path, work, name, mutation) for name, mutation in mutations.items()}
    rejection_names = ("altered_quote", "wrong_document", "invalid_endpoint", "missing_passage", "prerequisite_cycle")
    rejected = {name: not trials[name]["gate_passed"] and trials[name]["preview_http_status"] == 422
                for name in rejection_names}
    withdrawal = trials["withdrawn_prerequisite"]
    withdrawal_removed = all(
        len(withdrawal["ungated_planner_routes_diagnostic"][name]["phases"]) <= len(base_routes[name]["phases"])
        for name in PROFILES
    ) and withdrawal["ungated_planner_routes_diagnostic"] != base_routes and withdrawal["preview_http_status"] == 200
    static = {name: paper_ids for name in PROFILES}
    target_only = {name: target_papers for name in PROFILES}
    adaptive = {name: value["papers"] for name, value in base_routes.items()}
    result = {
        "scope": "structural and provenance checks; no independent teaching or learning-effect labels",
        "runtime": {"python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version},
        "code_sha256": {str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in [Path(__file__), ROOT / "backend/scripts/prepare_second_demo.py",
                                     ROOT / "backend/app/roadmap/auto_evaluate.py",
                                     ROOT / "backend/app/roadmap/generate.py",
                                     ROOT / "backend/app/api/roadmap.py",
                                     ROOT / "backend/app/roadmap/trusted_queries.py"]},
        "source_pdf_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted((seed / "pdfs").glob("*.pdf"))},
        "baseline_gate": base_gate,
        "baseline_preview_http_status": baseline_http,
        "baselines": {"static_all_papers": static, "target_only": target_only, "evidence_route": adaptive},
        "baseline_personalization": {
            "static_all_papers": len({tuple(v) for v in static.values()}) > 1,
            "target_only": len({tuple(v) for v in target_only.values()}) > 1,
            "evidence_route": len({tuple(v) for v in adaptive.values()}) > 1,
        },
        "recommended_passages_exist": evidence_ok,
        "faults": trials,
        "mechanical_faults_rejected": rejected,
        "withdrawal_changed_route_without_expanding_it": withdrawal_removed,
        "semantic_blind_spot_observed": (
            trials["semantic_swap"]["gate_passed"]
            and trials["semantic_swap"]["preview_http_status"] == 200
            and trials["semantic_swap"]["ungated_planner_routes_diagnostic"] != base_routes
        ),
    }
    result["passed"] = bool(base_gate["passed"] and all(code == 200 for code in baseline_http.values())
                             and evidence_ok and all(rejected.values()) and withdrawal_removed)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "mechanical_faults_rejected": rejected,
                      "withdrawal_changed_route": withdrawal_removed,
                      "semantic_blind_spot_observed": result["semantic_blind_spot_observed"],
                      "report": str(output)}, ensure_ascii=False))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
