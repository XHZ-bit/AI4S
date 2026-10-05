from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from app.db import projects as store
from app.db import sqlite


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPOSITORY_ROOT / "evaluation/research_atlas/prepare_browser_fixture.py"


def _load_fixture_module():
    spec = importlib.util.spec_from_file_location("prepare_browser_fixture", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_browser_fixture_builds_isolated_traceable_snapshot(tmp_path):
    module = _load_fixture_module()
    output_dir = tmp_path / "isolated-browser-data"

    manifest = module.prepare_fixture(output_dir)

    assert manifest["scientific_result"] is False
    assert manifest["external_calls_made"] is False
    assert manifest["plan_source_kind"] == "user_input"
    assert (output_dir / "atlas.db").is_file()
    persisted_manifest = json.loads(
        (output_dir / "browser-fixture.json").read_text(encoding="utf-8")
    )
    assert persisted_manifest == manifest

    conn = sqlite.connect(str(output_dir / "atlas.db"))
    try:
        project_id = str(manifest["project_id"])
        project = store.get_project(conn, project_id)
        assert project is not None
        assert project.title.startswith("[合成验收]")
        facts = store.list_facts(conn, project_id)
        assert len(facts) == 5
        assert {fact.status.value for fact in facts} == {"user_confirmed"}
        settings = [fact for fact in facts if hasattr(fact, "method_id")]
        assert {setting.id for setting in settings} == {
            "setting-synthetic-a",
            "setting-synthetic-b",
        }
        setting_b = next(item for item in settings if item.id == "setting-synthetic-b")
        assert setting_b.random_seed is None
        assert setting_b.resources == []

        decisions = store.list_decisions(conn, project_id)
        assert len(decisions) == 1
        assert decisions[0].source_kind.value == "user_input"
        assert decisions[0].considered_candidate_ids == [
            "setting-synthetic-a",
            "setting-synthetic-b",
        ]
        plans = store.list_plans(conn, project_id)
        assert len(plans) == 1
        assert plans[0].source_kind.value == "user_input"
        assert "真实科研指标未知" in plans[0].unknowns
        snapshots = store.list_snapshots(conn, project_id)
        assert len(snapshots) == 1
        assert snapshots[0].id == manifest["snapshot_id"]
        assert snapshots[0].plan.id == plans[0].id
        assert snapshots[0].plan.source_kind.value == "user_input"
        assert snapshots[0].review_status.value == "current"
    finally:
        conn.close()


def test_browser_fixture_refuses_nonempty_and_production_targets(tmp_path):
    module = _load_fixture_module()
    nonempty = tmp_path / "nonempty"
    nonempty.mkdir()
    marker = nonempty / "keep.txt"
    marker.write_text("do not overwrite", encoding="utf-8")

    with pytest.raises(ValueError, match="非空"):
        module.prepare_fixture(nonempty)
    assert marker.read_text(encoding="utf-8") == "do not overwrite"

    with pytest.raises(ValueError, match="生产数据"):
        module.validate_output_directory(module.PRODUCTION_DATA_DIR)
    with pytest.raises(ValueError, match="生产数据"):
        module.validate_output_directory(module.PRODUCTION_DATA_DIR / "nested")
