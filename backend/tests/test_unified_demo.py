"""The portable demo exercises real canonical reads and executable examples."""
import contextlib
import importlib.util
import io
import json
import sqlite3
import sys
from pathlib import Path

import pytest

from app.db.sqlite import connect
from app.db import projects
from app.knowledge import demo as knowledge_demo, experience, learning, model, store, unified
from app.models.research import ResearchProjectPatch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_demo.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("unified_demo_preparation", SCRIPT)
preparation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preparation)


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    monkeypatch.setattr(preparation, "ROOT", tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError("Demo preparation must not connect to a model or network")
    monkeypatch.setattr(model.httpx, "Client", forbidden)
    target = tmp_path / "demo"
    marker = preparation.prepare(target, tmp_path / "missing", synthetic_only=True)
    return target, marker


def test_current_graph_paths_evidence_resources_and_artifacts_are_available(prepared):
    target, marker = prepared
    pid, demo = marker["project_id"], marker["unified_demo"]
    with contextlib.closing(connect(str(target / "atlas.db"))) as conn:
        project = projects.get_project(conn, pid)
        assert "梯度与有界残差" in project.title
        assert project.domain.value == "custom"
        graph = unified.graph(conn, project_id=pid)
        assert len(graph["nodes"]) >= 12
        assert graph["edges"]
        nid = demo["node_ids"]["bounded:method"]
        detail = learning.detail(conn, pid, nid)
        assert detail["prerequisites"]
        paths = experience.paths(conn, pid, nid, kind="prerequisites")
        assert paths["paths"] and not paths["cycle_detected"]
        gradient = demo["node_ids"]["foundations:gradient"]
        chain = demo["node_ids"]["foundations:chain"]
        assert {(gradient, nid), (gradient, chain, nid)} <= {
            tuple(path["node_ids"]) for path in paths["paths"]
        }
        assert chain in {node["id"] for node in paths["nodes"]}
        assert all(e["kind"] == "PREREQUISITE_OF" for e in paths["edges"])
        lesson = learning.get_learning(conn, pid, nid)
        assert lesson["cached"] and not lesson["stale"]
        assert "原创" in lesson["sections"]["overview"]
        assert lesson["demos"]
        for evidence in detail["evidence"]:
            block = json.loads(conn.execute("SELECT data FROM kw_blocks WHERE id=?", (evidence["block_id"],)).fetchone()[0])
            assert evidence["quote"] in block["text"]
            assert evidence["locator"]["start_line"] > 0
        resource = experience.resources(conn, pid, demo["node_ids"]["bounded:figure"])["items"]
        assert any(r["type"] == "image" and r["access_status"] == "local" for r in resource)
        videos = experience.resources(conn, pid, demo["node_ids"]["foundations:chain"])["items"]
        assert any(r["type"] == "video" and not r["fetched"] for r in videos)
        comparison = json.loads(conn.execute("SELECT data FROM kw_comparisons WHERE id=?", (demo["comparison_id"],)).fetchone()[0])
        assert len(comparison["focus_node_ids"]) == 2
        assert all("未知" in v["text"] for v in comparison["rows"][-1]["values"])
        assert conn.execute("SELECT COUNT(*) FROM kw_model_calls").fetchone()[0] == 0
        for sid in demo["source_ids"].values():
            path, digest = conn.execute("SELECT path,hash FROM kw_assets a JOIN kw_sources s ON s.asset_id=a.id WHERE s.id=?", (sid,)).fetchone()
            original = Path(path)
            assert original.is_file() and original.is_relative_to(target)
            assert ".prepare-" not in path
        assert preparation.inspect_existing(target)["schema_version"] == 2


def run_example(code, inputs):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exec(compile(code, "<original-teaching-example>", "exec"), {"inputs": inputs})
    return [json.loads(line.split(":", 1)[1]) for line in output.getvalue().splitlines() if line.startswith("PAPERSTRIDE_VISUAL:")]


def test_examples_really_compute_curves_tables_and_changed_parameters():
    zero = run_example(knowledge_demo.PRACTICE_CODE, {"alpha": 0})
    half = run_example(knowledge_demo.PRACTICE_CODE, {"alpha": 0.5})
    assert zero[0]["type"] == "line" and half[1]["type"] == "table"
    assert all(y == 0 for _, y in zero[0]["series"][0]["points"])
    assert half[0]["series"][0]["points"][-1] == [4, 2]
    assert abs(half[0]["series"][1]["points"][-1][1]) < 0.5
    # y_B(2), analytic derivative, numeric derivative from the actual Python run.
    assert half[1]["rows"][-1][2:] == [2.482014, 1.035325, 1.035325]
    gaussian = run_example(knowledge_demo.GAUSSIAN_CODE, {"mu": 0, "sigma": 1})
    shifted = run_example(knowledge_demo.GAUSSIAN_CODE, {"mu": 2, "sigma": 1})
    assert [v["type"] for v in gaussian] == ["scatter", "bar"]
    assert shifted[0]["series"][0]["points"][0][1] == pytest.approx(gaussian[0]["series"][0]["points"][0][1] + 2)
    with pytest.raises(ValueError):
        run_example(knowledge_demo.GAUSSIAN_CODE, {"sigma": -1})


def test_beginner_path_has_matching_lessons_and_runnable_practice(prepared):
    target, marker = prepared
    pid, fixture = marker["project_id"], marker["unified_demo"]
    with contextlib.closing(connect(str(target / "atlas.db"))) as conn:
        for key, expected in (("foundations:gradient", "解析导数"),
                              ("foundations:chain", "链式法则导数")):
            nid = fixture["node_ids"][key]
            lesson = learning.get_learning(conn, pid, nid)
            practice = json.loads(conn.execute(
                "SELECT data FROM kw_practice WHERE project_id=? AND node_id=?",
                (pid, nid)).fetchone()[0])
            assert "数值差分" in lesson["sections"]["implementation"]
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                namespace = {"inputs": json.loads(practice["input_json"])}
                exec(compile(practice["starter_code"], "<demo>", "exec"), namespace)
                exec(compile(practice["test_code"], "<demo-test>", "exec"), namespace)
            assert expected in output.getvalue()
            assert "数值差分" in output.getvalue()
            namespace["derivative"] = 999
            with pytest.raises(AssertionError):
                exec(compile(practice["test_code"], "<demo-test>", "exec"), namespace)


def test_existing_demo_upgrade_adds_exercise_only_when_original_is_untouched(prepared):
    target, marker = prepared
    pid, fixture = marker["project_id"], marker["unified_demo"]
    gradient = fixture["node_ids"]["foundations:gradient"]
    chain = fixture["node_ids"]["foundations:chain"]
    with contextlib.closing(connect(str(target / "atlas.db"))) as conn:
        for node_id in (gradient, chain):
            row = conn.execute("SELECT id,data FROM kw_practice WHERE project_id=? AND node_id=?",
                               (pid, node_id)).fetchone()
            original = json.loads(row["data"])
            original.update(starter_code=knowledge_demo.PRACTICE_CODE,
                            draft_code=knowledge_demo.PRACTICE_CODE,
                            reference_code=knowledge_demo.PRACTICE_CODE,
                            title="旧版残差演示",
                            test_code="",
                            input_json=json.dumps({"alpha": 0.5}))
            if node_id == chain:
                original.update(draft_code="print('user work')", revision=2)
            conn.execute("UPDATE kw_practice SET data=? WHERE id=?", (store.encode(original), row["id"]))
        migration = dict(fixture, version=3)
        conn.execute("UPDATE kw_migrations SET data=? WHERE name=?",
                     (store.encode(migration), "portable-knowledge-demo-v3:" + pid))
        conn.commit()
        upgraded = knowledge_demo.seed(conn, target, pid)
        assert upgraded["version"] == knowledge_demo.VERSION
        entries = [json.loads(row[0]) for row in conn.execute(
            "SELECT data FROM kw_practice WHERE project_id=? AND node_id=? ORDER BY rowid", (pid, gradient))]
        assert len(entries) == 2
        assert entries[0]["starter_code"] == knowledge_demo.PRACTICE_CODE
        assert entries[0]["title"] == "旧版残差演示"
        assert entries[1]["starter_code"] == knowledge_demo.GRADIENT_CODE
        assert "含检查" in entries[1]["title"]
        user_entries = [json.loads(row[0]) for row in conn.execute(
            "SELECT data FROM kw_practice WHERE project_id=? AND node_id=?", (pid, chain))]
        assert len(user_entries) == 1 and user_entries[0]["draft_code"] == "print('user work')"
        knowledge_demo.seed(conn, target, pid)
        assert conn.execute("SELECT COUNT(*) FROM kw_practice WHERE project_id=? AND node_id=?",
                            (pid, gradient)).fetchone()[0] == 2


def test_prepare_upgrades_old_marker_once_without_changing_runs(prepared):
    target, marker = prepared
    pid = marker["project_id"]
    nid = marker["unified_demo"]["node_ids"]["foundations:gradient"]
    marker["unified_demo"]["version"] = 3
    (target / preparation.MANIFEST).write_text(json.dumps(marker), encoding="utf-8")
    with contextlib.closing(connect(str(target / "atlas.db"))) as conn:
        row = conn.execute("SELECT id,data FROM kw_practice WHERE project_id=? AND node_id=?", (pid, nid)).fetchone()
        original = json.loads(row["data"])
        original.update(starter_code=knowledge_demo.PRACTICE_CODE, draft_code=knowledge_demo.PRACTICE_CODE,
                        test_code="", input_json=json.dumps({"alpha": 0.5}))
        conn.execute("UPDATE kw_practice SET data=? WHERE id=?", (store.encode(original), row["id"]))
        conn.execute("INSERT INTO kw_practice_runs VALUES(?,?,?,?)", ("run1", pid, row["id"], '{"id":"run1"}'))
        fixture = dict(marker["unified_demo"], version=3)
        conn.execute("UPDATE kw_migrations SET data=? WHERE name=?",
                     (store.encode(fixture), "portable-knowledge-demo-v3:" + pid))
        conn.commit()
    assert preparation.prepare(target, target / "missing", check=True)["unified_demo"]["version"] == 3
    upgraded = preparation.prepare(target, target / "missing", synthetic_only=True)
    assert upgraded["upgraded"] and upgraded["unified_demo"]["version"] == knowledge_demo.VERSION
    with contextlib.closing(connect(str(target / "atlas.db"))) as conn:
        assert conn.execute("SELECT COUNT(*) FROM kw_practice WHERE project_id=? AND node_id=?", (pid, nid)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM kw_practice_runs WHERE project_id=? AND practice_id=?", (pid, row["id"])).fetchone()[0] == 1
    assert preparation.prepare(target, target / "missing", synthetic_only=True).get("upgraded") is not True


def test_repeated_prepare_and_seed_preserve_revisions_progress_and_snapshots(prepared):
    target, marker = prepared
    pid, demo = marker["project_id"], marker["unified_demo"]
    nid = demo["node_ids"]["bounded:method"]
    with contextlib.closing(connect(str(target / "atlas.db"))) as conn:
        snapshot = list(conn.execute("SELECT payload_json FROM research_snapshots"))
        node = store.record(conn, "kw_nodes", pid, nid)
        node["summary"] = "用户保留的修订"
        node["metadata"]["user_fields"] = ["summary"]
        store.put_record(conn, "kw_nodes", node, preserve_user=False)
        conn.commit()
        experience.save_progress(conn, pid, nid, "review")
        conn.commit()
        counts = [conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("kw_nodes", "kw_edges", "kw_practice")]
        knowledge_demo.seed(conn, target, pid)
        assert store.record(conn, "kw_nodes", pid, nid)["summary"] == "用户保留的修订"
        assert experience.progress(conn, pid, nid)["status"] == "review"
        assert counts == [conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("kw_nodes", "kw_edges", "kw_practice")]
        assert [r[0] for r in snapshot] == [r[0] for r in conn.execute("SELECT payload_json FROM research_snapshots")]
    before = (target / "atlas.db").read_bytes()
    assert preparation.prepare(target, target / "missing", synthetic_only=True)["reused"]
    assert (target / "atlas.db").read_bytes() == before


def test_recognized_version_one_upgrades_additively_and_check_is_read_only(tmp_path, monkeypatch):
    monkeypatch.setattr(preparation, "ROOT", tmp_path)
    target = tmp_path / "previous"
    fixture = preparation.prepare_synthetic(target)
    marker = {"kind": preparation.KIND, "schema_version": 1, "fixture_kind": "portable_synthetic", "paper_uids": [],
        "project_id": fixture["project_id"], "snapshot_id": fixture["snapshot_id"], "synthetic_paper_uid": fixture["paper_uid"]}
    (target / preparation.MANIFEST).write_text(json.dumps(marker), encoding="utf-8")
    with sqlite3.connect(target / "atlas.db") as conn:
        conn.execute("UPDATE papers SET title='Preserved existing title'")
        snapshot = conn.execute("SELECT payload_json FROM research_snapshots").fetchone()[0]
    before = (target / "atlas.db").read_bytes()
    assert preparation.prepare(target, target / "missing", check=True)["schema_version"] == 1
    assert (target / "atlas.db").read_bytes() == before
    result = preparation.prepare(target, target / "missing", synthetic_only=True)
    assert result["upgraded"] and result["schema_version"] == 2
    with sqlite3.connect(target / "atlas.db") as conn:
        assert conn.execute("SELECT title FROM papers").fetchone()[0] == "Preserved existing title"
        assert conn.execute("SELECT payload_json FROM research_snapshots").fetchone()[0] == snapshot
        assert conn.execute("SELECT COUNT(*) FROM kw_nodes").fetchone()[0] > 0


def test_demo_upgrade_preserves_user_project_context(tmp_path, monkeypatch):
    monkeypatch.setattr(preparation, "ROOT", tmp_path)
    target = tmp_path / "previous-custom"
    fixture = preparation.prepare_synthetic(target)
    with contextlib.closing(connect(str(target / "atlas.db"))) as conn:
        current = projects.get_project(conn, fixture["project_id"])
        projects.update_project(conn, current.id, ResearchProjectPatch(expected_version=current.version, title="用户自己的研究问题"))
        knowledge_demo.seed(conn, target, current.id)
        assert projects.get_project(conn, current.id).title == "用户自己的研究问题"
