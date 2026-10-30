"""Parsed representations and immutable PDF byte versions must stay distinct."""

from contextlib import closing
import hashlib
import json

from fastapi.testclient import TestClient
import pymupdf
import pytest

from app.db.sqlite import connect
from app.db.reading_position import save_position
from app.knowledge import service, source_files, store
from app.main import app
from app.tenancy import data_dir, user_scope


def seed(*, uid="coordination-paper", pages=21, explicit=False):
    with pymupdf.open() as pdf:
        for page in range(1, pages + 1):
            pdf.new_page().insert_text((60, 60), f"Original page {page}; two coordinated residual heads")
        raw = pdf.tobytes()
    digest = hashlib.sha256(raw).hexdigest()
    folder = data_dir() / "knowledge/assets"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (digest + ".pdf")
    path.write_bytes(raw)
    (data_dir() / "pdfs").mkdir(exist_ok=True)
    (data_dir() / "pdfs" / (uid + ".pdf")).write_bytes(raw)
    src = {"id": "source-" + uid, "project_id": "space", "asset_id": "asset-" + uid, "version": "sha256:" + digest,
           "title": "Coordinated residual paper", "filename": uid + ".pdf", "kind": "paper", "media_type": "application/pdf", "paper_uid": uid}
    result = {"title": src["title"], "parser": "local-layout", "blocks": [{"heading": "Method", "text": "Shared representation and separate residual heads", "page": page, "kind": "text", "metadata": {"source_block_id": "block-" + str(page)}} for page in range(1, pages + 1)]}
    with closing(connect()) as conn:
        store.init(conn)
        conn.execute("INSERT INTO papers(uid,title) VALUES(?,?)", (uid, src["title"]))
        conn.execute("INSERT INTO kw_assets VALUES(?,?,?,?,?,?)", (src["asset_id"], digest, str(path), src["filename"], "application/pdf", "then"))
        conn.execute("INSERT INTO kw_sources VALUES(?,?,?,?,?)", (src["id"], src["project_id"], src["asset_id"], 0, store.encode(src)))
        store.put_parse(conn, src["asset_id"], result)
        blocks = store.source_blocks(conn, src["asset_id"])
        representation = source_files.bridge_digest(src, result, blocks)
        # Match the production legacy bridge's deterministic document identity.
        did = hashlib.sha256(f"{uid}:{representation}".encode()).hexdigest()[:32]
        conn.execute("INSERT INTO documents(id,paper_uid,content_hash,coverage) VALUES(?,?,?,'fulltext')", (did, uid, representation))
        for block in blocks:
            conn.execute("INSERT INTO passages(id,document_id,heading,text,page,ordinal,kind,metadata_json) VALUES(?,?,?,?,?,?,?,?)", (did + "-" + str(block["ordinal"]), did, block["heading"], block["text"], block["page"], block["ordinal"], block["kind"], json.dumps(block["metadata"])))
        if explicit:
            source_files.bind_document_file(conn, did, src, representation)
        conn.commit()
    return src, result, did, raw, digest


def test_legacy_bridge_pdf_resolves_without_mutating_any_records_and_page_14_is_valid():
    src, _, did, raw, digest = seed()
    with closing(connect()) as conn:
        before = list(conn.execute("SELECT name FROM sqlite_master ORDER BY name"))
        resolved, actual = source_files.read_document_file(conn, src["paper_uid"], did)
        assert resolved.sha256 == digest and resolved.representation_hash != digest and actual == raw
        assert list(conn.execute("SELECT name FROM sqlite_master ORDER BY name")) == before
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='document_source_files'").fetchone()
        position = save_position(conn, src["paper_uid"], did, 14)
        assert position["page"] == 14 and position["page_count"] == 21
        assert position["document_version"] == "sha256:" + resolved.representation_hash
    client = TestClient(app)
    resources = client.get("/api/resources", params={"scope": "paper", "id": src["paper_uid"]})
    assert resources.status_code == 200
    pdf = next(item for item in resources.json()["items"] if item["kind"] == "pdf")
    assert pdf["file_available"] and pdf["document_id"] == did
    assert pdf["source_file_sha256"] == digest and pdf["version"] != digest
    assert pdf["url"].endswith("?file_sha256=" + digest)
    response = client.get(pdf["url"])
    assert response.status_code == 200 and response.content == raw
    assert response.headers["x-source-file-sha256"] == digest
    assert response.headers["cache-control"] in {"private, no-cache", "no-store"}
    assert client.get(pdf["url"].replace(digest, "0" * 64)).status_code == 409


def test_unmatched_historical_representation_does_not_silently_use_current_pdf():
    src, _, _, raw, digest = seed()
    with closing(connect()) as conn:
        conn.execute("INSERT INTO documents(id,paper_uid,content_hash,coverage,created_at) VALUES(?,?,?,'fulltext','2099-01-01')", ("unmatched-old", src["paper_uid"], "unrelated-historical-content"))
        conn.commit()
    client = TestClient(app)
    response = client.get(f"/api/papers/{src['paper_uid']}/documents/unmatched-old/file")
    assert response.status_code == 409 and response.content != raw
    items = client.get("/api/resources", params={"scope": "paper", "id": src["paper_uid"]}).json()["items"]
    pdfs = [item for item in items if item["kind"] == "pdf"]
    assert pdfs[0]["file_available"]
    old = next(item for item in pdfs if item["document_id"] == "unmatched-old")
    assert old["file_available"] is False and old["source_file_sha256"] is None
    assert old["current_file_url"] == f"/api/papers/{src['paper_uid']}/file"
    assert client.get(old["current_file_url"]).content == raw
    assert digest not in old["url"]


def test_explicit_mapping_preserves_original_when_current_parse_blocks_change():
    src, result, did, raw, _ = seed(explicit=True)
    with closing(connect()) as conn:
        store.put_parse(conn, src["asset_id"], {**result, "parser": "next-parser", "blocks": [{"text": "Changed representation"}]})
        conn.commit()
        assert source_files.read_document_file(conn, src["paper_uid"], did)[1] == raw


def test_legacy_bridge_after_block_enrichment_requires_exact_restored_snapshot_digest():
    src, result, did, raw, _ = seed()
    result["blocks"][0]["text"] = "A later formula transcription"
    result["blocks"][0]["metadata"]["latex"] = "a+b"
    with closing(connect()) as conn:
        store.put_parse(conn, src["asset_id"], result)
        conn.commit()
        assert source_files.read_document_file(conn, src["paper_uid"], did)[1] == raw
        conn.execute("UPDATE passages SET text='not the published representation' WHERE document_id=? AND ordinal=0", (did,))
        conn.commit()
        with pytest.raises(source_files.DocumentFileError) as error:
            source_files.resolve_document_file(conn, src["paper_uid"], did)
        assert error.value.status_code == 409


def test_future_bridge_persists_raw_hash_separately_from_representation_hash():
    src, result, _, _, digest = seed()
    with closing(connect()) as conn:
        service._bridge_paper(conn, src, result, store.source_blocks(conn, src["asset_id"]))
        conn.commit()
        mapping = conn.execute("SELECT * FROM document_source_files").fetchone()
        assert mapping["source_file_sha256"] == digest
        assert mapping["representation_hash"] != digest
        assert mapping["asset_id"] == src["asset_id"]


def test_account_scope_cannot_resolve_another_accounts_document_or_asset():
    with user_scope({"id": "a" * 32}):
        src, _, did, _, _ = seed()
        other_asset = data_dir() / "knowledge/assets" / (hashlib.sha256(b"not the file").hexdigest() + ".pdf")
    with user_scope({"id": "b" * 32}):
        with closing(connect()) as conn:
            with pytest.raises(source_files.DocumentFileError) as error:
                source_files.resolve_document_file(conn, src["paper_uid"], did)
            assert error.value.status_code == 404
        second, _, second_did, _, _ = seed(uid="other-paper")
        with closing(connect()) as conn:
            conn.execute("UPDATE kw_assets SET path=? WHERE id=?", (str(other_asset), second["asset_id"]))
            conn.commit()
            (data_dir() / "pdfs" / (second["paper_uid"] + ".pdf")).unlink()
            with pytest.raises(source_files.DocumentFileError) as error:
                source_files.resolve_document_file(conn, second["paper_uid"], second_did)
            assert error.value.status_code == 404


def test_asset_bytes_are_verified_not_just_accepted_from_declared_hash():
    src, _, did, _, _ = seed()
    with closing(connect()) as conn:
        path = conn.execute("SELECT path FROM kw_assets WHERE id=?", (src["asset_id"],)).fetchone()[0]
        from pathlib import Path
        Path(path).write_bytes(b"changed bytes")
        with pytest.raises(source_files.DocumentFileError) as error:
            source_files.resolve_document_file(conn, src["paper_uid"], did)
        assert error.value.status_code == 409
