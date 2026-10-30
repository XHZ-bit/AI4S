"""Demo initialization must preserve existing work and never fall back to network."""

import importlib.util
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest
import fitz

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_demo.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("demo_preparation", SCRIPT)
demo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(demo)


def test_production_and_existing_temporary_data_are_protected():
    for path in (demo.ROOT / "backend" / "data", demo.ROOT / ".tmp" / "second-demo-run-v4"):
        with pytest.raises(ValueError, match="protected"):
            demo.validate_target(path)


def test_portable_demo_requires_no_cache_and_preserves_edits(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "ROOT", tmp_path)
    target = tmp_path / "portable"
    created = demo.prepare(target, tmp_path / "absent", synthetic_only=True)
    assert created["real_paper_count"] == 0
    assert created["paper_uids"] == []
    assert created["external_calls_made"] is False
    with sqlite3.connect(target / "atlas.db") as conn:
        conn.execute("UPDATE papers SET title='Preserved edit'")
    before = (target / "atlas.db").read_bytes()
    assert demo.prepare(target, tmp_path / "absent", check=True)["reused"]
    assert (target / "atlas.db").read_bytes() == before


def test_existing_non_demo_directory_is_untouched(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "ROOT", tmp_path)
    target = tmp_path / "user-data"
    target.mkdir()
    sentinel = target / "atlas.db"
    sentinel.write_bytes(b"Existing user data")
    with pytest.raises(ValueError, match="no demo marker"):
        demo.prepare(target, tmp_path / "missing-cache")
    assert list(target.iterdir()) == [sentinel]
    assert sentinel.read_bytes() == b"Existing user data"


@pytest.fixture
def existing_demo(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "ROOT", tmp_path)
    target = tmp_path / "demo-data"
    synthetic = demo.prepare_synthetic(target)
    uid = "arxiv-0000.00000v1"
    path = target / "pdfs" / f"{uid}.pdf"
    with fitz.open() as pdf:
        pdf.new_page().insert_text((40, 40), "Tiny synthetic pinned source for initialization checks")
        pdf.save(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(demo, "SOURCES", [{"arxiv": "0000.00000v1", "sha256": digest}])
    database = target / "atlas.db"
    with sqlite3.connect(database) as conn:
        conn.execute("INSERT INTO papers(uid,title) VALUES(?,?)", (uid, "Synthetic pinned source"))
        conn.execute("INSERT INTO documents(id,paper_uid,content_hash,filename,coverage) VALUES(?,?,?,?,?)",
                     ("tiny-document", uid, digest, path.name, "fulltext"))
        conn.execute("INSERT INTO passages(id,document_id,heading,text,ordinal) VALUES(?,?,?,?,?)",
                     ("tiny-passage", "tiny-document", "Synthetic", "Synthetic source", 0))
    marker = target / demo.MANIFEST
    marker.write_text(json.dumps({"kind": demo.KIND, "schema_version": 1, "paper_uids": [uid],
        "project_id": synthetic["project_id"], "snapshot_id": synthetic["snapshot_id"],
        "synthetic_paper_uid": synthetic["paper_uid"]}), encoding="utf-8")
    return target


def test_prepare_reuses_marker_without_changing_user_records(existing_demo):
    target = existing_demo
    database, marker = target / "atlas.db", target / demo.MANIFEST
    with sqlite3.connect(database) as conn:
        conn.execute("UPDATE papers SET title='user-edited-record' WHERE uid='arxiv-0000.00000v1'")
        conn.execute("INSERT INTO papers(uid,title) VALUES('user-added-paper','Keep my own paper')")
    before = database.read_bytes(), marker.read_bytes()
    result = demo.prepare(target, target / "missing-cache")
    assert result["reused"] is True
    assert (database.read_bytes(), marker.read_bytes()) == before


def test_missing_pdf_is_reported_without_reseeding(existing_demo):
    target = existing_demo
    (target / "pdfs" / "arxiv-0000.00000v1.pdf").unlink()
    before = (target / "atlas.db").read_bytes()
    with pytest.raises(ValueError, match="PDF is missing"):
        demo.prepare(target, target / "missing-cache", check=True)
    assert (target / "atlas.db").read_bytes() == before


def test_replaced_pdf_is_reported_without_reseeding(existing_demo):
    target = existing_demo
    (target / "pdfs" / "arxiv-0000.00000v1.pdf").write_bytes(b"replaced file")
    with pytest.raises(ValueError, match="hash mismatch"):
        demo.prepare(target, target / "missing-cache", check=True)


def test_missing_snapshot_is_reported_without_reseeding(existing_demo):
    target = existing_demo
    with sqlite3.connect(target / "atlas.db") as conn:
        conn.execute("DELETE FROM research_snapshots")
    with pytest.raises(ValueError, match="project or snapshot is missing"):
        demo.prepare(target, target / "missing-cache", check=True)


def test_missing_pinned_document_is_reported(existing_demo):
    target = existing_demo
    with sqlite3.connect(target / "atlas.db") as conn:
        conn.execute("DELETE FROM documents WHERE id='tiny-document'")
    with pytest.raises(ValueError, match="document/passages are missing"):
        demo.prepare(target, target / "missing-cache", check=True)


def test_incomplete_marker_is_reported(existing_demo):
    target = existing_demo
    marker = target / demo.MANIFEST
    value = json.loads(marker.read_text(encoding="utf-8"))
    del value["snapshot_id"]
    marker.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="marker is incomplete"):
        demo.prepare(target, target / "missing-cache", check=True)


def test_missing_cache_creates_no_database_or_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "ROOT", tmp_path)
    target = tmp_path / "new-demo"
    with pytest.raises(ValueError, match="no download attempted"):
        demo.prepare(target, tmp_path / "missing-cache")
    assert not target.exists()


def test_unknown_marker_is_not_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "ROOT", tmp_path)
    target = tmp_path / "unknown-demo"
    target.mkdir()
    marker = target / demo.MANIFEST
    marker.write_text('{"kind":"another-application","schema_version":1}', encoding="utf-8")
    before = marker.read_bytes()
    with pytest.raises(ValueError, match="Unrecognized"):
        demo.prepare(target, tmp_path / "missing-cache")
    assert marker.read_bytes() == before


def test_check_does_not_initialize_empty_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "ROOT", tmp_path)
    target = tmp_path / "not-prepared"
    with pytest.raises(ValueError, match="not prepared"):
        demo.prepare(target, tmp_path / "missing-cache", check=True)
    assert not target.exists()
