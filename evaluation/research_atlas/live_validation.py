"""Opt-in real-service checks. Never run as part of the default mock suite."""

import argparse
import json
import os
from pathlib import Path
import sys
import time
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))


def configure(data_dir):
    from app import config
    settings = config.Settings(_env_file=None, data_dir=str(data_dir))
    config.get_settings = lambda: settings
    return settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["serve", "graph", "grobid", "offline"])
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.data_dir
    if args.mode in {"graph", "offline"}:
        from prepare_browser_fixture import prepare_fixture
        # Linux-native SQLite avoids Windows bind-mount WAL locking differences.
        args.data_dir = Path(tempfile.mkdtemp(prefix="atlas-live-"))
        manifest = prepare_fixture(args.data_dir)
    else:
        manifest = json.loads((args.data_dir / "browser-fixture.json").read_text(encoding="utf-8"))
    settings = configure(args.data_dir)
    if manifest.get("fixture_kind") != "synthetic_browser_validation":
        raise ValueError("Only explicitly synthetic validation data is permitted")
    from app.db import projects as store
    from app.db.sqlite import connect
    with connect() as conn:
        snapshot = store.get_snapshot(conn, manifest["project_id"], manifest["snapshot_id"])
    assert snapshot is not None
    report = {"mode": args.mode, "synthetic_input": True, "checks": {}}
    if args.mode == "serve":
        import uvicorn
        uvicorn.run("app.main:app", host="127.0.0.1", port=18000)
        return
    if args.mode == "graph":
        from app.db.neo4j_client import get_driver
        from app.research.graph_projection import build_graph_projection, project_graph
        from app.research.graph_queries import query_dependencies, query_impact, query_method_context, query_project_graph
        from app.models.research import GraphQuery
        driver = get_driver()
        for attempt in range(20):
            try:
                driver.verify_connectivity()
                break
            except Exception:
                if attempt == 19:
                    raise
                time.sleep(2)
        graph = build_graph_projection(snapshot)
        first = project_graph(graph)
        repeat = project_graph(graph)
        assert first == repeat
        for mode, result in (
            ("dependencies", query_dependencies(snapshot.project_id, snapshot.id, snapshot.plan.id)),
            ("method_context", query_method_context(snapshot.project_id, snapshot.id, snapshot.plan.selected_method_id)),
            ("impact", query_impact(snapshot.project_id, snapshot.id, manifest["evidence_id"])),
        ):
            assert result.edges, mode
            report["checks"][mode] = {"nodes": len(result.nodes), "edges": len(result.edges)}
        try:
            query_project_graph(GraphQuery(project_id="unrelated-project", snapshot_id=snapshot.id))
        except RuntimeError:
            report["checks"]["project_isolation"] = True
        else:
            raise AssertionError("Cross-project query unexpectedly succeeded")
        next_snapshot = snapshot.model_copy(update={"id": snapshot.id + "-v2", "snapshot_version": 2})
        project_graph(build_graph_projection(next_snapshot))
        old = query_dependencies(snapshot.project_id, snapshot.id, snapshot.plan.id)
        marker = next(n for n in old.nodes if n.kind == "projection_status")
        assert marker.properties["current"] is False
        report["checks"].update(authenticated_bolt=True, idempotent=True, old_snapshot_retained=True)
        driver.close()
    elif args.mode == "grobid":
        import fitz
        import httpx
        from app.parser.grobid import parse_with_grobid
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 65), "Synthetic Protocol for Research Atlas Validation", fontsize=16)
        paragraphs = [
            "Abstract", "This synthetic document validates PDF parsing. It contains no scientific results.",
            "1 Introduction", "Research Atlas links source passages to methods and experimental settings.",
            "2 Methods", "The Synthetic Probe method compares two separately named experimental settings.",
            "Setting Alpha uses synthetic images. Setting Beta uses synthetic time series.",
            "GPU memory and runtime were not reported. No experiment was executed.",
            "3 Limitations", "All content is synthetic. Successful parsing is not evidence of scientific validity.",
        ]
        page.insert_text((72, 110), "\n\n".join(paragraphs), fontsize=11)
        page = doc.new_page()
        page.insert_text((72, 70), "2 Methods", fontsize=18)
        body = ("The Synthetic Probe method compares two separately named experimental settings. "
                "Setting Alpha uses synthetic images. Setting Beta uses synthetic time series. "
                "GPU memory and runtime were not reported. No experiment was executed. "
                "The source is a generated validation document, and all statements are synthetic. ")
        page.insert_textbox(fitz.Rect(72, 110, 520, 700), "\n\n".join([body] * 6), fontsize=11)
        pdf = doc.tobytes()
        (args.data_dir / "synthetic-source.pdf").write_bytes(pdf)
        def capture_tei(response):
            response.read()
            (args.data_dir / "grobid-response.tei.xml").write_bytes(response.content)
        with httpx.Client(trust_env=False, event_hooks={"response": [capture_tei]}) as client:
            parsed = parse_with_grobid(client, settings.grobid_base_url, pdf, "synthetic-source.pdf")
        (args.data_dir / "grobid-parsed.json").write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
        assert parsed["sections"], "GROBID returned no body sections"
        text = " ".join(s["text"] for s in parsed["sections"])
        assert "Synthetic Probe" in text and "not reported" in text
        (args.data_dir / "grobid-parsed.json").write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
        report["checks"] = {"real_pdf_bytes": len(pdf), "sections": len(parsed["sections"]), "method_preserved": True, "unknown_preserved": True}
    else:
        import socket
        from fastapi.testclient import TestClient
        from app.main import app
        from app.research.graph_projection import build_graph_projection, project_graph
        assert os.environ.get("ATLAS_NETWORK_NONE") == "1", "Run inside docker --network none"
        try:
            socket.create_connection(("1.1.1.1", 443), timeout=2)
        except OSError:
            report["checks"]["external_network_unreachable"] = True
        else:
            raise AssertionError("External network remained reachable")
        # Use ASGI's real routes, schema and temporary SQLite, with no service mocks.
        with TestClient(app) as client:
            path = f"/api/projects/{snapshot.project_id}/snapshots/{snapshot.id}"
            assert client.get(path).json()["id"] == snapshot.id
            assert client.get(path + "/export?format=json").json()["plan"]["source_kind"] == "user_input"
            try:
                project_graph(build_graph_projection(snapshot))
            except RuntimeError:
                report["checks"]["graph_failure_explicit"] = True
            else:
                raise AssertionError("Graph unexpectedly succeeded offline")
            assert client.get(path).json()["frozen_facts"] == snapshot.model_dump(mode="json")["frozen_facts"]
            report["checks"].update(snapshot_preserved=True, json_export_offline=True)
    (output_dir / f"live-{args.mode}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
