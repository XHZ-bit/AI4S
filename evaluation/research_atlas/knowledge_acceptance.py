"""Isolated real-paper generalization and clearly synthetic graph load checks.

No model service is contacted unless the semantic command receives --allow-model.
Every database and output must remain in the repository's .tmp directory.
"""

from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import UTC, datetime
import hashlib
import io
import json
import os
from pathlib import Path
import statistics
import random
import sys
import time

ROOT = Path(__file__).absolute().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
HOLDOUT_URL = "https://arxiv.org/pdf/1706.03762v7"
TERMINAL = {"succeeded", "partial", "failed", "interrupted", "cancelled"}


def temp_path(value):
    path = Path(value).absolute().resolve()
    try:
        path.relative_to((ROOT / ".tmp").resolve())
    except ValueError:
        raise ValueError(
            "Acceptance data and outputs must stay inside repository .tmp"
        ) from None
    path.mkdir(parents=True, exist_ok=True)
    return path


def configure(folder, *, allow_models=False):
    folder = temp_path(folder)
    os.environ["DATA_DIR"] = str(folder)
    os.environ["ATLAS_ENV_FILE"] = (
        str(ROOT / ".env")
        if allow_models
        else str(ROOT / ".tmp/no-acceptance-secrets.env")
    )
    os.environ["ACCESS_MODE"] = "local"
    os.environ["OFFLINE_MODE"] = "false" if allow_models else "true"
    os.environ["KNOWLEDGE_MODEL_ENABLED"] = "true" if allow_models else "false"
    os.environ["KNOWLEDGE_USE_DOCLING"] = "true"
    os.environ["PAPERSTRIDE_FORMULA_BUDGET_SECONDS"] = "0"
    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    assert Path(settings.data_dir).resolve() == folder
    return settings


def save(folder, name, value):
    path = folder / name
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def project(title):
    from app.db import projects
    from app.knowledge import store
    from app.models.research import ResearchProjectCreate

    with store.connection() as conn:
        existing, _ = projects.list_projects(conn, limit=200)
        for item in existing:
            if item.title == title:
                return item.id
        value = projects.create_project(
            conn,
            ResearchProjectCreate(
                title=title,
                research_question="",
                domain="custom",
                stage="exploring",
                constraints={"version": 1, "objective": ""},
            ),
        )
        return value.id


def analyze(pid, sid, *, retry=False):
    from app.knowledge import service, store

    with store.connection(pid) as conn:
        run, _ = store.create_run(conn, pid, sid)
    started = time.perf_counter()
    service.analyze(pid, sid, run["id"], retry=retry)
    with store.connection(pid) as conn:
        state = store.run(conn, pid, run["id"])
    return state, time.perf_counter() - started


def holdout(folder, *, resume=False):
    from app.knowledge import sources, store

    pid = project("Holdout generalization — Attention Is All You Need")
    with store.connection(pid) as conn:
        prior = store.sources(conn, pid)
    started = time.perf_counter()
    source = (
        prior[0] if prior and resume else sources.ingest_link(pid, HOLDOUT_URL, "paper")
    )
    ingest_seconds = time.perf_counter() - started
    state, analysis_seconds = analyze(pid, source["id"], retry=resume)
    with store.connection(pid) as conn:
        src = store.source(conn, pid, source["id"], blocks=True)
        graph = store.graph(conn, pid, limit=2000)
        calls = conn.execute("SELECT COUNT(*) FROM kw_model_calls").fetchone()[0]
        evidences = [
            json.loads(row[0])
            for row in conn.execute(
                "SELECT data FROM kw_evidence WHERE project_id=?", (pid,)
            )
        ]
        asset = conn.execute(
            "SELECT path,hash FROM kw_assets WHERE id=?", (src["asset_id"],)
        ).fetchone()
        parse = json.loads(
            conn.execute(
                "SELECT data FROM kw_parses WHERE asset_id=?", (src["asset_id"],)
            ).fetchone()[0]
        )
    blocks = {block["id"]: block for block in src["blocks"]}
    mismatches = [
        ev["id"]
        for ev in evidences
        if ev["block_id"] not in blocks
        or ev["source_version"] != src["version"]
        or (ev["quote"] and ev["quote"] not in blocks[ev["block_id"]]["text"])
    ]
    checks = {
        "title": "attention is all you need" in src["title"].casefold(),
        "docling_actual_parser": parse["parser"] == "docling",
        "blocks_present": len(blocks) > 20,
        "formula_regions_present": sum(
            block["kind"] == "formula" for block in blocks.values()
        )
        > 0,
        "structure_graph_present": len(graph["nodes"]) > 10 and bool(graph["edges"]),
        "all_evidence_locates_current_source": not mismatches,
        "no_paid_model_calls": calls == 0,
        "source_bytes_match_hash": hashlib.sha256(
            Path(asset["path"]).read_bytes()
        ).hexdigest()
        == asset["hash"],
    }
    report = {
        "format": "paperstride-holdout-acceptance-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "kind": "real_public_paper_structural_generalization",
        "scope": "Structure and source fidelity only; semantic extraction deliberately disabled.",
        "source_url": HOLDOUT_URL,
        "source_sha256": asset["hash"],
        "project_id": pid,
        "source_id": source["id"],
        "data_dir": str(folder),
        "ingest_seconds": round(ingest_seconds, 3),
        "analysis_seconds": round(analysis_seconds, 3),
        "analysis": state,
        "quality": parse["quality"],
        "parser": parse["parser"],
        "block_kinds": dict(Counter(block["kind"] for block in blocks.values())),
        "graph": {
            "nodes": graph["total_nodes"],
            "edges": graph["total_edges"],
            "evidence": len(evidences),
        },
        "checks": checks,
        "passed": all(checks.values()),
        "semantic_validation": "not_run",
    }
    save(folder.parent, "holdout-structure.json", report)
    save(folder.parent, "holdout-parse.json", parse)
    save(folder.parent, "holdout-graph.json", graph)
    return report


def semantic(folder, *, allow_model):
    if not allow_model:
        raise ValueError(
            "Semantic acceptance requires explicit --allow-model and parent coordination"
        )
    import threading
    from app.knowledge import store, model

    model._slots = threading.BoundedSemaphore(1)

    record = folder.parent / "holdout-structure.json"
    if not record.is_file():
        raise ValueError("Run holdout structural acceptance first")
    previous = json.loads(record.read_text(encoding="utf-8"))
    pid, sid = previous["project_id"], previous["source_id"]
    with store.connection(pid) as conn:
        before = conn.execute("SELECT COUNT(*) FROM kw_model_calls").fetchone()[0]
    state, elapsed = analyze(pid, sid, retry=True)
    with store.connection(pid) as conn:
        graph = store.graph(conn, pid, limit=2000)
        rows = [
            json.loads(r[0])
            for r in conn.execute(
                "SELECT data FROM kw_model_calls WHERE project_id=?", (pid,)
            )
        ]
        facts = [
            node for node in graph["nodes"] if node.get("metadata", {}).get("semantic")
        ]
        source = store.source(conn, pid, sid, blocks=True)
        evidence = [
            json.loads(row[0])
            for row in conn.execute(
                "SELECT data FROM kw_evidence WHERE project_id=?", (pid,)
            )
        ]
    blocks = {block["id"]: block for block in source["blocks"]}
    invalid_evidence = [
        item["id"]
        for item in evidence
        if item["block_id"] not in blocks
        or item["source_version"] != source["version"]
        or (item["quote"] and item["quote"] not in blocks[item["block_id"]]["text"])
    ]
    formulas = [block for block in blocks.values() if block["kind"] == "formula"]
    recognized = [block for block in formulas if block.get("metadata", {}).get("latex")]
    result = {
        "format": "paperstride-holdout-semantic-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "project_id": pid,
        "source_id": sid,
        "data_dir": str(folder),
        "seconds": round(elapsed, 3),
        "analysis": state,
        "new_model_call_records": len(rows) - before,
        "semantic_node_count": len(facts),
        "source_sha256": previous["source_sha256"],
        "formula_regions": len(formulas),
        "recognized_formulas": len(recognized),
        "formula_samples": [
            {
                "heading": block["heading"],
                "page": block["page"],
                "latex": block["metadata"]["latex"],
            }
            for block in recognized
        ],
        "evidence_count": len(evidence),
        "invalid_evidence_ids": invalid_evidence,
        "checks": {
            "semantic_nodes_present": bool(facts),
            "formula_transcription_present": bool(recognized),
            "all_evidence_locates_current_source": not invalid_evidence,
        },
        "node_kinds": dict(Counter(node["kind"] for node in facts)),
        "sample_nodes": [
            {
                key: node[key]
                for key in ["id", "kind", "label", "summary", "evidence_ids"]
            }
            for node in facts[:30]
        ],
        "graph": {"nodes": graph["total_nodes"], "edges": graph["total_edges"]},
        "limitation": "One real holdout paper; schema and citation checks are not an independent scientific accuracy estimate.",
    }
    save(folder.parent, "holdout-semantic.json", result)
    save(folder.parent, "holdout-semantic-graph.json", graph)
    return result


def image_fixture(source_number):
    from PIL import Image

    image = Image.frombytes(
        "RGB", (160, 160), random.Random(source_number).randbytes(160 * 160 * 3)
    )
    output = io.BytesIO()
    image.save(output, format="PNG")
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    parts = [
        f"<html><body><h1>Performance fixture {source_number:02d}</h1>",
        "<p>Synthetic database performance material only. No research claims.</p>",
    ]
    for position in range(1, 101):
        parts.extend(
            [
                f"<h2>Fixture record {source_number:02d}-{position:03d}</h2>",
                f"<p>Performance fixture source {source_number}, record {position}. These are sequence positions, not experiment results.</p>",
            ]
        )
    parts.append(
        "<figure><figcaption>Deterministic noise image used only to measure metadata payload size.</figcaption>"
        f'<img src="data:image/png;base64,{encoded}" /></figure>'
    )
    parts.append(
        "<table><tr><th>Fixture row</th><th>Fixture column</th><th>Purpose</th></tr>"
    )
    for row in range(20):
        parts.append(
            f"<tr><td>{row}</td><td>{source_number}</td><td>Database payload fixture, not a measured result</td></tr>"
        )
    parts.append("</table></body></html>")
    return "\n".join(parts).encode("utf-8")


def build_performance_fixture(pid, *, image_payload=False):
    """Load honestly named benchmark data through the same source/block records."""
    from app.knowledge import extraction, sources, store
    from app.knowledge.parser import parse_source

    for source_number in range(1, 51):
        lines = [
            f"# Performance fixture {source_number:02d}",
            "Synthetic database performance material only. This document makes no research claims.",
        ]
        for position in range(1, 101):
            lines += [
                f"## Fixture record {source_number:02d}-{position:03d}",
                f"Performance fixture source {source_number}, record {position}. The number is a sequence position, not an experiment result.",
            ]
        raw = (
            image_fixture(source_number)
            if image_payload
            else ("\n\n".join(lines) + "\n").encode()
        )
        extension = "html" if image_payload else "md"
        source = sources.ingest(
            pid, raw, f"performance-fixture-{source_number:02d}.{extension}", "report"
        )
        with store.connection(pid) as conn:
            path = conn.execute(
                "SELECT path FROM kw_assets WHERE id=?", (source["asset_id"],)
            ).fetchone()[0]
        parsed = parse_source(Path(path), "report", False)
        with store.connection(pid) as conn:
            store.put_parse(conn, source["asset_id"], parsed)
            blocks = store.source_blocks(conn, source["asset_id"])
            extraction.structural_graph(conn, source, blocks)
            members = [
                json.loads(row[0])
                for row in conn.execute(
                    "SELECT data FROM kw_nodes WHERE project_id=? AND source_id=?",
                    (pid, source["id"]),
                )
            ]
            ordered = sorted(
                [node for node in members if node["parent_id"]],
                key=lambda node: node["label"],
            )
            for left, right in zip(ordered, ordered[1:]):
                edge = extraction.edge(
                    source,
                    left["id"],
                    right["id"],
                    "FIXTURE_SEQUENCE",
                    "夹具顺序",
                    "Synthetic performance fixture sequence only; not a scientific prerequisite or conclusion.",
                    left["evidence_ids"] + right["evidence_ids"],
                    origin="source",
                )
                edge["metadata"] = {"performance_fixture": True}
                store.put_record(conn, "kw_edges", edge)


def metrics(values):
    ordered = sorted(values)
    return {
        "samples": len(values),
        "median_ms": round(statistics.median(values), 3),
        "p95_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 3),
        "max_ms": round(max(values), 3),
        "min_ms": round(min(values), 3),
    }


def performance(folder, *, iterations=25, image_payload=False):
    from app.knowledge import store
    from app.main import app
    from fastapi.testclient import TestClient

    pid = project("Synthetic graph performance fixture — not research data")
    started = time.perf_counter()
    build_performance_fixture(pid, image_payload=image_payload)
    build_seconds = time.perf_counter() - started
    with store.connection(pid) as conn:
        counts = {
            name: conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE project_id=?", (pid,)
            ).fetchone()[0]
            for name, table in [
                ("sources", "kw_sources"),
                ("nodes", "kw_nodes"),
                ("edges", "kw_edges"),
                ("evidence", "kw_evidence"),
            ]
        }
        source = store.sources(conn, pid)[0]
        all_nodes = [
            json.loads(row[0])
            for row in conn.execute(
                "SELECT data FROM kw_nodes WHERE project_id=?", (pid,)
            )
        ]
        root = next(
            node
            for node in all_nodes
            if node["source_id"] == source["id"] and node["parent_id"] is None
        )
        leaf = next(
            node
            for node in all_nodes
            if node["source_id"] == source["id"] and node["parent_id"] is not None
        )
        pictures = [
            node
            for node in all_nodes
            if node.get("metadata", {}).get("image_url", "").startswith("data:image/")
        ]
        image_bytes = sum(
            len(node["metadata"]["image_url"].encode("utf-8")) for node in pictures
        )
    assert (
        counts["sources"] == 50
        and min(counts["nodes"], counts["edges"], counts["evidence"]) >= 5000
    )
    endpoints = {
        "overview_50_sources": f"/api/projects/{pid}/knowledge/graph?overview=true&limit=100",
        "default_graph_100_nodes": f"/api/projects/{pid}/knowledge/graph?limit=100",
        "source_subgraph": f"/api/projects/{pid}/knowledge/graph?source_id={source['id']}&limit=200",
        "root_detail_degree_101": f"/api/projects/{pid}/knowledge/nodes/{root['id']}",
        "leaf_detail": f"/api/projects/{pid}/knowledge/nodes/{leaf['id']}",
        "sources_list": f"/api/projects/{pid}/sources",
    }
    if pictures:
        endpoints["image_node_detail"] = (
            f"/api/projects/{pid}/knowledge/nodes/{pictures[0]['id']}"
        )
    results = {}
    # No lifespan means no recovery, graph server probing, or background jobs.
    client = TestClient(app, raise_server_exceptions=True)
    try:
        for name, endpoint in endpoints.items():
            for _ in range(3):
                response = client.get(endpoint)
                response.raise_for_status()
            samples = []
            sizes = []
            for _ in range(iterations):
                started = time.perf_counter()
                response = client.get(endpoint)
                response.raise_for_status()
                response.json()
                samples.append((time.perf_counter() - started) * 1000)
                sizes.append(len(response.content))
            results[name] = {
                **metrics(samples),
                "response_bytes": max(sizes),
                "endpoint": endpoint,
            }
    finally:
        client.close()
    report = {
        "format": "paperstride-knowledge-performance-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "fixture": "50 synthetic documents with explicitly non-scientific sequence records; no model outputs or research results.",
        "data_dir": str(folder),
        "project_id": pid,
        "counts": counts,
        "image_metadata_nodes": len(pictures),
        "image_metadata_bytes": image_bytes,
        "build_seconds": round(build_seconds, 3),
        "measurement": "Warm local FastAPI TestClient HTTP including account middleware, database access and JSON decoding; 3 warmups per endpoint.",
        "results": results,
        "p95_under_2_seconds": all(item["p95_ms"] < 2000 for item in results.values()),
        "limitations": [
            "Synthetic database load only; not 50 real PDF parsing or model-analysis throughput.",
            "Local in-process HTTP excludes network transport, browser rendering and graph layout costs.",
        ],
    }
    save(folder.parent, "performance.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["holdout", "semantic", "performance"])
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--allow-model", action="store_true")
    parser.add_argument("--iterations", type=int, default=25)
    parser.add_argument("--image-payload", action="store_true")
    args = parser.parse_args()
    if args.allow_model and args.mode != "semantic":
        raise ValueError("Only the semantic command can enable model services")
    folder = (
        args.data_dir
        or ROOT
        / ".tmp"
        / (
            (
                "knowledge-performance-images"
                if args.image_payload
                else "knowledge-performance"
            )
            if args.mode == "performance"
            else "knowledge-holdout"
        )
        / "data"
    )
    folder = temp_path(folder)
    configure(folder, allow_models=args.mode == "semantic" and args.allow_model)
    if args.mode == "holdout":
        result = holdout(folder, resume=args.resume)
    elif args.mode == "semantic":
        result = semantic(folder, allow_model=args.allow_model)
    else:
        if not 5 <= args.iterations <= 100:
            raise ValueError("Use 5–100 measurement iterations")
        result = performance(
            folder, iterations=args.iterations, image_payload=args.image_payload
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
