"""Legacy import safety: offline, idempotent and scoped to real saved sources."""

from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3

import pymupdf
import pytest

from app.config import get_settings
from app.db import projects
from app.db.sqlite import connect, upsert_paper
from app.db.workspace import save_document
from app.knowledge import migration, model, sources, store
from app.models.paper import PaperDoc, ParsedPaper, Section
from app.models.research import (
    ExperimentSetting, FieldEvidence, Measurement, MethodCard, NumericValue,
    PaperLinkCreate, ProjectConstraints, ResearchProjectCreate,
)
from app.tenancy import data_dir, user_scope


@pytest.fixture(autouse=True)
def no_models(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("A legacy migration must never call a model")
    monkeypatch.setattr(model, "structured", forbidden)


def seed_scope(title="Legacy space", *, write_original=True, text="Method A uses a bounded message."):
    folder = data_dir() / "pdfs"
    folder.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((50, 60), text)
        raw = pdf.tobytes()
    if write_original:
        (folder / "paper-1.pdf").write_bytes(raw)
    with closing(connect()) as conn:
        upsert_paper(conn, PaperDoc(uid="paper-1", title="Existing research paper", year=2024).model_dump())
        did = save_document(conn, "paper-1", ParsedPaper(uid="paper-1", title="Existing research paper", abstract="",
                            sections=[Section(heading="Method", text=text, page=1)]), content_hash="frozen-document-v1", filename="original.pdf")
        project = projects.create_project(conn, ResearchProjectCreate(title=title, research_question="How does the method work?", domain="custom",
                                           constraints=ProjectConstraints(version=1, objective="Understand evidence")))
        link = projects.link_paper(conn, project.id, project.version, PaperLinkCreate(expected_project_version=project.version, paper_uid="paper-1", role="primary"))
        passage = conn.execute("SELECT id FROM passages WHERE document_id=? ORDER BY ordinal LIMIT 1", (did,)).fetchone()[0]
        eid = "evidence-" + project.id
        ref = {"id": eid, "source_kind": "literature_report", "finding_status": "reported", "kind": "text", "paper_uid": "paper-1",
               "document_id": did, "document_version": "sha256:frozen-document-v1", "passage_id": passage, "quote": "Method A"}
        conn.execute("INSERT INTO research_evidence VALUES(?,?,?,?,?)", (eid, project.id, link.id, json.dumps(ref), "2026-10-01"))
        field = FieldEvidence(field_path="name", source_kind="literature_report", finding_status="reported", evidence_ids=[eid])
        method = MethodCard(id="method-" + project.id, project_id=project.id, version=1, status="candidate", source_kind="literature_report",
                            finding_status="reported", field_evidence=[field], paper_link_id=link.id, name="Method A", summary=text)
        setting = ExperimentSetting(id="setting-" + project.id, project_id=project.id, version=1, status="candidate", source_kind="literature_report",
                                    finding_status="reported", field_evidence=[field], paper_link_id=link.id, method_id=method.id, name="Original setting", dataset="Task A")
        measurement = Measurement(id="measurement-" + project.id, project_id=project.id, version=1, status="candidate", source_kind="literature_report",
                                  finding_status="reported", field_evidence=[field], experiment_setting_id=setting.id, metric_name="successes per 1000 steps", value=NumericValue(value=7.0))
        for fact in (method, setting, measurement):
            projects._insert_fact(conn, fact)
        conn.execute("CREATE TABLE IF NOT EXISTS workspace_records(id TEXT PRIMARY KEY,title TEXT,body TEXT,version INTEGER)")
        conn.execute("INSERT OR REPLACE INTO workspace_records VALUES(?,?,?,?)", ("note-" + project.id, "Personal note", "Keep this exact text", 5))
        conn.execute("INSERT INTO research_snapshots VALUES(?,?,?,?,?,?,?)", ("snapshot-" + project.id, project.id, 1, '{"frozen":"do not rewrite"}', "current", "[]", "2026-10-01"))
        conn.commit()
    return project.id, method.id, setting.id, measurement.id, raw


def dump_tables(names):
    with closing(connect()) as conn:
        return {name: [tuple(row) for row in conn.execute(f"SELECT * FROM {name} ORDER BY rowid")] for name in names}


def knowledge_dump():
    with store.connection() as conn:
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'kw_%' ORDER BY name")]
    return dump_tables(names)


def test_migration_preserves_legacy_data_and_is_idempotent_without_model_calls():
    pid, mid, _, _, _ = seed_scope()
    protected = ["research_project_versions", "research_paper_link_versions", "research_fact_versions", "research_evidence", "research_snapshots", "workspace_records", "documents", "passages", "papers", "pipeline_stages"]
    before = dump_tables(protected)
    result = migration.migrate_workspace()
    assert result["sources_imported"] == 1 and result["facts_imported"] == 3
    assert result["model_calls"] == 0
    assert dump_tables(protected) == before
    with store.connection(pid) as conn:
        src = store.sources(conn, pid)[0]
        assert src["analysis"]["status"] == "partial"
        assert src["analysis"]["stages"]["extract"] == "skipped"
        node = store.record(conn, "kw_nodes", pid, store.identity(pid, "legacy-fact", mid))
        assert node["origin"] == "source" and node["metadata"]["legacy_unverified"]
        assert node["metadata"]["legacy_status"] == "candidate"
        evidence = store.evidence(conn, pid, node["evidence_ids"])[0]
        assert evidence["quote"] == "Method A" and evidence["locator"]["page"] == 1
        assert evidence["locator"]["legacy_document_version"] == "sha256:frozen-document-v1"
        assert conn.execute("SELECT COUNT(*) FROM kw_model_calls").fetchone()[0] == 0
    stable = knowledge_dump()
    second = migration.migrate_workspace()
    assert second["sources_imported"] == 0 and second["facts_imported"] == 0
    assert knowledge_dump() == stable
    assert dump_tables(protected) == before


def test_same_original_in_two_spaces_reuses_parse_but_preserves_independent_edits():
    first, mid, _, _, raw = seed_scope()
    with closing(connect()) as conn:
        other = projects.create_project(conn, ResearchProjectCreate(title="Other space", research_question="Another question", domain="custom", constraints=ProjectConstraints(version=1, objective="Read independently")))
        projects.link_paper(conn, other.id, other.version, PaperLinkCreate(expected_project_version=other.version, paper_uid="paper-1", role="background"))
    migration.migrate_workspace()
    with store.connection() as conn:
        a, b = store.sources(conn, first)[0], store.sources(conn, other.id)[0]
        assert a["asset_id"] == b["asset_id"] and a["id"] != b["id"]
        assert conn.execute("SELECT COUNT(*) FROM kw_parses").fetchone()[0] == 1
        nid = store.identity(first, "legacy-fact", mid)
        node = store.record(conn, "kw_nodes", first, nid)
    with store.connection(first) as conn:
        store.edit_record(conn, "kw_nodes", first, nid, node["version"], {"summary": "My independent correction"})
    migration.migrate_workspace()
    with store.connection(first) as conn:
        assert store.record(conn, "kw_nodes", first, nid)["summary"] == "My independent correction"
    with store.connection(other.id) as conn:
        assert all(n["project_id"] == other.id for n in store.graph(conn, other.id)["nodes"])
        with pytest.raises(Exception) as error:
            store.record(conn, "kw_nodes", other.id, nid)
        assert getattr(error.value, "status_code", None) == 404
    assert (data_dir() / "pdfs/paper-1.pdf").read_bytes() == raw


def test_existing_new_source_and_active_analysis_are_not_modified(monkeypatch):
    pid, _, _, _, raw = seed_scope()
    src = sources.ingest(pid, raw, "already-new.pdf", "paper", paper_uid="paper-1")
    with store.connection(pid) as conn:
        run, fresh = store.create_run(conn, pid, src["id"])
        assert fresh
    from app.knowledge import parser
    monkeypatch.setattr(parser, "parse_source", lambda *a, **k: pytest.fail("Must not parse an existing new source"))
    before = knowledge_dump()
    result = migration.migrate_workspace()
    assert result["sources_imported"] == 0 and result["sources_skipped"] == 1
    assert result["facts_imported"] == 0
    assert knowledge_dump() == before
    with store.connection(pid) as conn:
        assert store.run(conn, pid, run["id"])["status"] == "queued"


def test_missing_original_or_invalid_evidence_is_explicit_record_only():
    pid, mid, _, _, _ = seed_scope(write_original=False)
    result = migration.migrate_workspace()
    assert result["sources_imported"] == 0 and result["record_sources"] == 1
    assert result["warnings"]
    with store.connection(pid) as conn:
        node = store.record(conn, "kw_nodes", pid, store.identity(pid, "legacy-fact", mid))
        assert node["origin"] == "inference" and node["metadata"]["record_only"]
        assert node["metadata"]["legacy_unresolved_evidence"]
        src = store.source(conn, pid, node["source_id"])
        assert src["legacy_record_source"] and src["paper_uid"] is None
        ev = store.evidence(conn, pid, node["evidence_ids"])[0]
        assert ev["locator"]["page"] is None and ev["origin"] == "inference"
        asset = conn.execute("SELECT path FROM kw_assets WHERE id=?", (src["asset_id"],)).fetchone()[0]
        assert json.loads(Path(asset).read_text(encoding="utf-8"))["kind"] == "legacy_research_record_export"


def test_withdrawn_and_user_input_facts_keep_their_original_meaning():
    pid, mid, sid, _, _ = seed_scope()
    with closing(connect()) as conn:
        for fact_id, changes in [(mid, {"status": "withdrawn"}), (sid, {"source_kind": "user_input", "status": "user_confirmed", "field_evidence": []})]:
            row = conn.execute("SELECT * FROM research_fact_versions WHERE fact_id=?", (fact_id,)).fetchone()
            payload = {**json.loads(row["payload_json"]), **changes, "version": 2}
            conn.execute("INSERT INTO research_fact_versions VALUES(?,?,?,?,?,?,?)", (fact_id, pid, row["fact_kind"], 2, payload["status"], json.dumps(payload), "2026-10-02"))
        conn.commit()
    migration.migrate_workspace()
    with store.connection(pid) as conn:
        withdrawn = store.record(conn, "kw_nodes", pid, store.identity(pid, "legacy-fact", mid))
        user = store.record(conn, "kw_nodes", pid, store.identity(pid, "legacy-fact", sid))
        assert withdrawn["hidden"] and withdrawn["metadata"]["legacy_status"] == "withdrawn"
        assert user["origin"] == "user" and user["metadata"]["record_only"]
        assert not user["metadata"]["legacy_unverified"]
        visible = store.graph(conn, pid)["nodes"]
        assert all(n["id"] != withdrawn["id"] for n in visible)
        assert all(n.get("metadata", {}).get("legacy_status") != "withdrawn" for n in visible)


def test_cli_all_account_scopes_are_isolated_and_no_unknown_directories_are_scanned(tmp_path):
    root = Path(get_settings().data_dir)
    uid = "a" * 32
    with user_scope(None):
        root_pid, root_mid, _, _, _ = seed_scope("Root project")
    with user_scope({"id": uid}):
        user_pid, user_mid, _, _, _ = seed_scope("Private project")
    unrelated = root / "users" / "not-an-account"
    unrelated.mkdir(parents=True)
    (unrelated / "private-code.py").write_text("raise AssertionError('must not read or execute')")
    result = migration.migrate_site(root)
    assert {scope["scope"] for scope in result["scopes"]} == {"root", uid}
    assert result["model_calls"] == 0
    with user_scope(None), store.connection(root_pid) as conn:
        assert store.record(conn, "kw_nodes", root_pid, store.identity(root_pid, "legacy-fact", root_mid))
        assert not conn.execute("SELECT 1 FROM kw_sources WHERE project_id=?", (user_pid,)).fetchone()
    with user_scope({"id": uid}), store.connection(user_pid) as conn:
        assert store.record(conn, "kw_nodes", user_pid, store.identity(user_pid, "legacy-fact", user_mid))
        assert not conn.execute("SELECT 1 FROM kw_sources WHERE project_id=?", (root_pid,)).fetchone()


def test_project_filter_imports_only_the_requested_project():
    first, _, _, _, _ = seed_scope()
    with closing(connect()) as conn:
        second = projects.create_project(conn, ResearchProjectCreate(title="Not selected", research_question="", stage="exploring", domain="custom", constraints=ProjectConstraints(version=1, objective="")))
        projects.link_paper(conn, second.id, second.version, PaperLinkCreate(expected_project_version=second.version, paper_uid="paper-1", role="background"))
    result = migration.migrate_workspace(first)
    assert result["projects"] == 1
    with store.connection() as conn:
        assert store.sources(conn, first)
        assert not store.sources(conn, second.id)


def test_missing_saved_passages_uses_only_fast_parser_and_does_not_rewrite_documents(monkeypatch):
    pid, _, _, _, _ = seed_scope()
    with closing(connect()) as conn:
        conn.execute("DELETE FROM passages")
        conn.execute("DELETE FROM documents")
        conn.commit()
    from app.knowledge import parser
    actual = parser.parse_source
    calls = []
    def fast_only(path, kind, use_docling=True):
        assert use_docling is False
        calls.append(path)
        return actual(path, kind, use_docling=False)
    monkeypatch.setattr(parser, "parse_source", fast_only)
    result = migration.migrate_workspace()
    assert len(calls) == 1 and result["sources_imported"] == 1
    with store.connection(pid) as conn:
        original = next(s for s in store.sources(conn, pid) if s["kind"] == "paper")
        assert original["quality"]["status"] == "partial"
        assert store.source_blocks(conn, original["asset_id"])
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM passages").fetchone()[0] == 0


def test_evidence_from_a_different_frozen_version_is_not_promoted_to_original_evidence():
    pid, mid, _, _, _ = seed_scope()
    with closing(connect()) as conn:
        row = conn.execute("SELECT evidence_id,payload_json FROM research_evidence WHERE project_id=?", (pid,)).fetchone()
        ref = json.loads(row["payload_json"])
        ref["document_version"] = "sha256:a-different-document-version"
        conn.execute("UPDATE research_evidence SET payload_json=? WHERE evidence_id=?", (json.dumps(ref), row["evidence_id"]))
        conn.commit()
    migration.migrate_workspace()
    with store.connection(pid) as conn:
        node = store.record(conn, "kw_nodes", pid, store.identity(pid, "legacy-fact", mid))
        assert node["metadata"]["record_only"] and node["origin"] == "inference"
        assert node["metadata"]["legacy_unresolved_evidence"]
        assert all(e["source_id"] == node["source_id"] for e in store.evidence(conn, pid, node["evidence_ids"]))


def test_legacy_revision_preserves_manual_hidden_state_origin_and_monotonic_version():
    pid, mid, _, _, _ = seed_scope()
    migration.migrate_workspace()
    nid = store.identity(pid, "legacy-fact", mid)
    with store.connection(pid) as conn:
        old = store.record(conn, "kw_nodes", pid, nid)
    with store.connection(pid) as conn:
        edited = store.edit_record(conn, "kw_nodes", pid, nid, old["version"], {"summary": "My maintained explanation", "hidden": True})
    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM research_fact_versions WHERE fact_id=? ORDER BY version DESC LIMIT 1", (mid,)).fetchone()
        next_version = row['version'] + 1
        payload = {**json.loads(row["payload_json"]), "version": next_version, "summary": "A later legacy revision"}
        conn.execute("INSERT INTO research_fact_versions VALUES(?,?,?,?,?,?,?)", (mid, pid, row["fact_kind"], next_version, row["status"], json.dumps(payload), "2026-10-03"))
        conn.commit()
    migration.migrate_workspace()
    with store.connection(pid) as conn:
        final = store.record(conn, "kw_nodes", pid, nid)
        assert final["version"] > edited["version"]
        assert final["summary"] == "My maintained explanation" and final["hidden"]
        assert final["origin"] == "user"
        assert final["metadata"]["legacy_fact_version"] == next_version


def test_registered_account_allowlist_and_root_only_do_not_import_orphan_test_workspaces():
    root = Path(get_settings().data_dir)
    users = ["a" * 32, "b" * 32, "c" * 32]
    for uid in users:
        with user_scope({"id": uid}):
            seed_scope("Scope " + uid[0])
    with sqlite3.connect(root / "identity.db") as identity:
        identity.execute("CREATE TABLE users(id TEXT PRIMARY KEY)")
        identity.executemany("INSERT INTO users VALUES(?)", [(uid,) for uid in users[:2]])
    filtered = migration.migrate_site(root, account_ids={users[0]}, include_root=False)
    assert [scope["scope"] for scope in filtered["scopes"]] == [users[0]]
    assert {item["scope"]: item["reason"] for item in filtered["skipped_scopes"]} == {users[1]: "not_selected", users[2]: "not_registered"}
    root_only = migration.migrate_site(root, account_ids=set())
    assert not root_only["scopes"]  # this fixture has no root database
    for uid in users[1:]:
        with user_scope({"id": uid}), closing(connect()) as conn:
            assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='kw_sources'").fetchone() is None


def test_copied_root_database_rebases_only_verified_assets_and_preserves_source_identity(tmp_path):
    pid, mid, _, _, _ = seed_scope()
    migration.migrate_workspace()
    root = Path(get_settings().data_dir)
    with store.connection(pid) as conn:
        source = store.sources(conn, pid)[0]
        asset = conn.execute("SELECT path FROM kw_assets WHERE id=?", (source["asset_id"],)).fetchone()[0]
    old_root = tmp_path / "previous-data-root"
    old_asset = old_root / Path(asset).relative_to(root.resolve())
    old_asset.parent.mkdir(parents=True)
    shutil.copyfile(asset, old_asset)
    with store.connection(pid) as conn:
        conn.execute("UPDATE kw_assets SET path=? WHERE id=?", (str(old_asset), source["asset_id"]))
    migrated = migration.migrate_site(root, project_id=pid, account_ids=set(), relocate_from=old_root)
    assert migrated["scopes"][0]["asset_paths"] == {"verified": 1, "relocated": 1}
    with store.connection(pid) as conn:
        assert conn.execute("SELECT path FROM kw_assets WHERE id=?", (source["asset_id"],)).fetchone()[0] == str(Path(asset).resolve())
        assert store.source(conn, pid, source["id"])["version"] == source["version"]
        assert store.record(conn, "kw_nodes", pid, store.identity(pid, "legacy-fact", mid))


def test_relocation_hash_failure_is_atomic_and_cannot_reach_another_account(tmp_path):
    pid, _, _, _, _ = seed_scope()
    migration.migrate_workspace()
    root = data_dir().resolve()
    old_root = tmp_path / "old-root"
    with store.connection(pid) as conn:
        assets = conn.execute("SELECT * FROM kw_assets").fetchall()
        asset = assets[0]
        old = old_root / Path(asset["path"]).relative_to(root)
        conn.execute("UPDATE kw_assets SET path=? WHERE id=?", (str(old), asset["id"]))
    # The target exists but its content no longer matches the registered original.
    Path(asset["path"]).write_bytes(b"different original")
    with pytest.raises(ValueError, match="校验不一致"):
        migration.migrate_site(root, account_ids=set(), relocate_from=old_root)
    with store.connection(pid) as conn:
        assert conn.execute("SELECT path FROM kw_assets WHERE id=?", (asset["id"],)).fetchone()[0] == str(old)
        # A path belonging to another account is rejected even if its file exists.
        private = root / "users" / ("b" * 32) / "pdfs" / "private.pdf"
        private.parent.mkdir(parents=True)
        private.write_bytes(b"different original")
        conn.execute("UPDATE kw_assets SET path=? WHERE id=?", (str(private), asset["id"]))
    with pytest.raises(ValueError, match="不属于所选账号"):
        migration.migrate_site(root, account_ids=set(), relocate_from=old_root)
