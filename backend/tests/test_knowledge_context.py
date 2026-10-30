"""Generic context must remain grounded, additive, scoped and model-free."""

import json
import sqlite3

import pytest

from app.knowledge import context, extraction, model, store


@pytest.fixture
def conn(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Context enrichment must not call a model")

    monkeypatch.setattr(model, "structured", forbidden)
    connection = sqlite3.connect(":memory:")
    store.init(connection)
    yield connection
    connection.close()


def source(conn, sid="report", pid="space", texts=None, *, filename="notes.docx", kind="report", url=None):
    src = {"id": sid, "project_id": pid, "asset_id": sid + "-asset", "version": "sha256:" + sid,
           "title": filename, "filename": filename, "kind": kind, "url": url, "removed": False}
    conn.execute("INSERT INTO kw_sources VALUES(?,?,?,?,?)", (sid, pid, src["asset_id"], 0, store.encode(src)))
    store.put_parse(conn, src["asset_id"], {"blocks": [item if isinstance(item, dict) else {"text": item} for item in texts or []]})
    return src, store.source_blocks(conn, src["asset_id"])


def node(conn, src, blocks, *, kind="method", meta=None, key="test", evidence_ordinals=None):
    eids = [store.add_evidence(conn, src["project_id"], src, blocks[i]) for i in evidence_ordinals or [0]]
    value = extraction.node(src, key, kind, "Actual method", "A grounded record", eids, metadata=meta)
    return store.put_record(conn, "kw_nodes", value)


def saved(conn, value):
    return json.loads(conn.execute("SELECT data FROM kw_nodes WHERE id=?", (value["id"],)).fetchone()[0])


def test_explicit_cutoff_wins_range_and_anchors_semantic_nodes_idempotently(conn):
    src, blocks = source(conn, texts=["研究记录 2026年10月5日至10月28日", "本总结数值汇总截至2026年10月28日11:35，运行状态核查于11:36，均为北京时间。"])
    value = node(conn, src, blocks)
    structural = node(conn, src, blocks, key="structure", meta={"structural": True})
    result = context.enrich_context(conn, "space", "report")
    assert result["reported_at"] == "2026-10-28T11:35:00+08:00"
    updated_source = store.source(conn, "space", "report")
    assert updated_source["reported_at_evidence"]["block_id"] == blocks[1]["id"]
    assert updated_source["reported_at_evidence"]["quote"] in blocks[1]["text"]
    current = saved(conn, value)
    assert current["metadata"]["reported_at"] == result["reported_at"]
    assert current["version"] == 2
    assert "reported_at" not in saved(conn, structural)["metadata"]
    history = conn.execute("SELECT data FROM kw_history WHERE record_id=?", (value["id"],)).fetchall()
    assert len(history) == 1 and json.loads(history[0][0]) == value
    assert context.enrich_context(conn, "space", "report")["nodes_updated"] == 0
    assert saved(conn, value) == current


@pytest.mark.parametrize("text", ["研究过程尚在继续", "日期2026年2月30日", "计划更新2026年11月2日", "记录2026年10月5日至10月28日", "The result mentions 2026-10-28 without an observation-date cue."])
def test_no_current_date_inference_or_invalid_or_future_date(conn, text):
    src, blocks = source(conn, texts=[text])
    value = node(conn, src, blocks)
    assert context.enrich_context(conn, "space", "report")["reported_at"] is None
    assert "reported_at" not in store.source(conn, "space", "report")
    assert saved(conn, value) == value


def test_unknown_timezone_is_not_assumed_and_papers_do_not_gain_report_dates(conn):
    src, blocks = source(conn, texts=["Updated 2026-10-28 11:35."])
    value = node(conn, src, blocks)
    context.enrich_context(conn, "space", "report")
    assert saved(conn, value)["metadata"]["reported_at"] == "2026-10-28T11:35:00"
    paper, paper_blocks = source(conn, sid="paper", kind="paper", filename="paper.pdf", texts=["Updated 2026-10-28 11:35."])
    paper_node = node(conn, paper, paper_blocks)
    context.enrich_context(conn, "space", "paper")
    assert "reported_at" not in saved(conn, paper_node)["metadata"]


def test_user_metadata_and_hidden_state_survive(conn):
    src, blocks = source(conn, texts=["截至2026年10月28日。记录文件 experiments/private_network.py"])
    values = [node(conn, src, blocks, key="one", kind="resource", meta={"user_fields": ["metadata"], "reported_at": "2026-10-20", "missing_source": False}),
              node(conn, src, blocks, key="two", meta={"user_fields": ["metadata.reported_at"], "reported_at": "2026-10-21"})]
    values[0]["hidden"] = True
    store.put_record(conn, "kw_nodes", values[0], preserve_user=False)
    before = [saved(conn, value) for value in values]
    context.enrich_context(conn, "space", "report")
    assert [saved(conn, value) for value in values] == before


def test_local_paths_and_adjacent_file_list_mark_missing_without_reading_files(conn, monkeypatch):
    src, blocks = source(conn, texts=[
        {"text": "[E5] Implementations in local study", "heading": "References"},
        {"text": r"experiments/study_v3/d2_network.py; D:\\private\\outputs\\metrics.csv", "heading": "References"},
        {"text": "[E6] Another resource other/unrelated.json", "heading": "References"},
    ])
    value = node(conn, src, blocks, kind="resource")
    from pathlib import Path
    monkeypatch.setattr(Path, "open", lambda *a, **k: pytest.fail("Never open a referenced private path"))
    context.enrich_context(conn, "space", "report")
    meta = saved(conn, value)["metadata"]
    assert meta["missing_source"]
    assert meta["missing_paths"] == ["experiments/study_v3/d2_network.py", r"D:\\private\\outputs\\metrics.csv"]
    assert "other/unrelated.json" not in meta["referenced_paths"]


def test_only_current_space_provided_file_can_resolve_and_removal_reflags(conn):
    src, blocks = source(conn, texts=["代码 experiments/private/network.py，结果 outputs/metrics.csv"])
    value = node(conn, src, blocks, kind="resource")
    source(conn, sid="outside", pid="other-space", kind="code", filename="network.py", texts=["print('private')"])
    source(conn, sid="public-repo", kind="code", filename="public.repo.json", url="https://github.com/example/public", texts=[{"text": "def network(): pass", "metadata": {"path": "src/network.py"}}])
    context.enrich_context(conn, "space", "report")
    assert len(saved(conn, value)["metadata"]["missing_paths"]) == 2
    source(conn, sid="provided-code", kind="code", filename="network.py", texts=["def user_supplied(): pass"])
    source(conn, sid="provided-result", kind="results", filename="metrics.csv", texts=["score,1"])
    context.enrich_context(conn, "space", "report")
    meta = saved(conn, value)["metadata"]
    assert meta["missing_source"] is False and meta["missing_paths"] == []
    conn.execute("UPDATE kw_sources SET removed=1 WHERE id='provided-code'")
    context.enrich_context(conn, "space", "report")
    assert saved(conn, value)["metadata"]["missing_paths"] == ["experiments/private/network.py"]


def test_actual_fetched_repo_path_matches_but_url_and_unfetched_path_do_not(conn):
    src, blocks = source(conn, texts=["实现 src/policy.py，另见未提供的 src/unfetched.py；公开链接 https://example.org/guide.py"])
    value = node(conn, src, blocks, kind="resource")
    source(conn, sid="public", filename="code.repo.json", kind="code", url="https://github.com/example/code", texts=[{"text": "def policy(): pass", "metadata": {"path": "src/policy.py"}}])
    context.enrich_context(conn, "space", "report")
    assert saved(conn, value)["metadata"]["missing_paths"] == ["src/unfetched.py"]


def test_cross_space_evidence_cannot_add_missing_paths(conn):
    src, blocks = source(conn, texts=["A resource entry without a path."])
    foreign, foreign_blocks = source(conn, sid="foreign", pid="elsewhere", texts=["secret.py"])
    value = node(conn, src, blocks, kind="resource")
    value["evidence_ids"].append(store.add_evidence(conn, "elsewhere", foreign, foreign_blocks[0]))
    store.put_record(conn, "kw_nodes", value)
    context.enrich_context(conn, "space", "report")
    assert "missing_source" not in saved(conn, value)["metadata"]
