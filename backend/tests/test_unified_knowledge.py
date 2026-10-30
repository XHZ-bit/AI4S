"""A single graph ledger across migration, old APIs, review and native analysis."""

from contextlib import closing
import json

import pytest
from fastapi import HTTPException
from app.db.sqlite import connect, upsert_paper
from app.db.workspace import save_document
from app.db.proposals import save_proposal
from app.db import projects
from app.models.paper import PaperDoc, ParsedPaper, Section
from app.models.research import (
    ResearchProjectCreate,
    ProjectConstraints,
    PaperLinkCreate,
)
from app.knowledge import unified, store, extraction


def seed():
    with closing(connect()) as c:
        upsert_paper(c, PaperDoc(uid="paper", title="A source", year=2024).model_dump())
        did = save_document(
            c,
            "paper",
            ParsedPaper(
                uid="paper",
                title="A source",
                abstract="",
                sections=[
                    Section(heading="Method", text="Method A uses knowledge B.", page=1)
                ],
            ),
        )
        passage = c.execute(
            "SELECT id FROM passages WHERE document_id=?", (did,)
        ).fetchone()[0]
        kid = save_proposal(
            c,
            "paper",
            "relation",
            {
                "src_name": "Method A",
                "src_type": "method",
                "dst_name": "knowledge B",
                "dst_type": "concept",
                "rel_type": "USES",
                "passage_id": passage,
                "evidence": "Method A uses knowledge B.",
            },
            0.8,
        )
        c.execute(
            "INSERT INTO knowledge(id,paper_uid,document_id,passage_id,quote,status,checks_json) VALUES(?,?,?,?,?,'candidate',?)",
            (
                kid,
                "paper",
                did,
                passage,
                "Method A uses knowledge B.",
                json.dumps({"structure": True, "evidence_located": True}),
            ),
        )
        c.commit()
        project = projects.create_project(
            c,
            ResearchProjectCreate(
                title="Research",
                research_question="Understand A",
                domain="custom",
                constraints=ProjectConstraints(version=1, objective="Learn"),
            ),
        )
        projects.link_paper(
            c,
            project.id,
            project.version,
            PaperLinkCreate(
                expected_project_version=project.version,
                paper_uid="paper",
                role="primary",
            ),
        )
        unified.migrate(c)
        c.commit()
    return project.id, kid


def test_library_and_project_use_one_ledger_without_duplicate_reimport():
    pid, kid = seed()
    with store.connection() as c:
        before = c.execute("SELECT COUNT(*) FROM kw_nodes").fetchone()[0]
        unified.migrate(c)
        assert c.execute("SELECT COUNT(*) FROM kw_nodes").fetchone()[0] == before
        assert len(unified.graph(c, project_id=pid)["edges"]) >= 1
        assert len(unified.graph(c, project_id="library")["edges"]) >= 1
        assert (
            c.execute(
                "SELECT COUNT(*) FROM kw_legacy_map WHERE legacy_id=?", (str(kid),)
            ).fetchone()[0]
            == 2
        )
        assert c.execute("SELECT COUNT(*) FROM kw_model_calls").fetchone()[0] == 0


def test_project_revision_survives_library_update_and_withdrawal():
    pid, kid = seed()
    with store.connection(pid) as c:
        rid = c.execute(
            "SELECT record_id FROM kw_legacy_map WHERE scope_id=? AND legacy_id=?",
            (pid, str(kid)),
        ).fetchone()[0]
        value = store.record(c, "kw_edges", pid, rid)
        store.edit_record(
            c,
            "kw_edges",
            pid,
            rid,
            value["version"],
            {"explanation": "My independent explanation"},
        )
    with store.connection() as c:
        c.execute("UPDATE knowledge SET status='withdrawn' WHERE id=?", (kid,))
        unified.sync_legacy(c, kid=kid)
        value = store.record(c, "kw_edges", pid, rid)
        assert value["explanation"] == "My independent explanation"
        assert value["metadata"]["source_withdrawn"]
        assert not any(
            e["id"] == rid for e in unified.graph(c, project_id=pid)["edges"]
        )


def test_native_nodes_appear_in_legacy_reading_and_graph():
    pid, _ = seed()
    with store.connection(pid) as c:
        src = store.sources(c, pid)[0]
        n = extraction.node(
            src, "native", "formula", "A new formula", "Native knowledge", []
        )
        store.put_record(c, "kw_nodes", n)
    from app.graphsvc.local import snapshot

    graph = snapshot(pid)
    assert any(
        n["uid"] == n["node_id"] and n["name"] == "A new formula"
        for n in graph["nodes"]
    )
    with store.connection() as c:
        assert any(
            r["payload"].get("name") == "A new formula"
            for r in unified.ledger(c, "paper")
        )


def test_project_connection_cannot_impersonate_library():
    seed()
    with pytest.raises(HTTPException):
        with store.connection("library"):
            pass
    with store.connection("library", allow_library=True) as c:
        assert unified.graph(c, project_id="library")["nodes"]


def test_review_requires_located_evidence_and_does_not_use_neo4j(monkeypatch):
    pid, _ = seed()
    monkeypatch.setattr(
        "app.db.neo4j_client.get_driver",
        lambda: pytest.fail("Canonical review must not require Neo4j"),
    )
    with store.connection(pid) as c:
        edge = next(
            e for e in unified.graph(c, project_id=pid)["edges"] if e["kind"] == "USES"
        )
        assert (
            unified.review_record(
                c, edge["id"], "verify", "Reviewer", "Checked source"
            )["status"]
            == "human_verified"
        )
        unified.review_record(
            c, edge["id"], "withdraw", "Reviewer", "Source no longer supported"
        )
        assert not any(
            e["id"] == edge["id"] for e in unified.graph(c, project_id=pid)["edges"]
        )
        src = store.sources(c, pid)[0]
        n = extraction.node(src, "unlocated", "concept", "No evidence", "", [])
        store.put_record(c, "kw_nodes", n)
        with pytest.raises(HTTPException):
            unified.review_record(c, n["id"], "verify", "Reviewer", "Cannot verify")


def test_changed_source_version_cannot_reuse_old_evidence_as_current():
    pid, _ = seed()
    with store.connection(pid) as c:
        edge = next(
            e for e in unified.graph(c, project_id=pid)["edges"] if e["kind"] == "USES"
        )
        original = store.evidence(c, pid, edge["evidence_ids"])[0]
        assert not original.get("unresolved")
        store.update_source(
            c, pid, edge["source_id"], {"version": "sha256:changed-source"}
        )
        outdated = store.evidence(c, pid, edge["evidence_ids"])[0]
        assert outdated["source_changed"] and outdated["unresolved"]
        assert outdated["quote"] == original["quote"]
        with pytest.raises(HTTPException):
            unified.review_record(
                c, edge["id"], "verify", "Reviewer", "Requires checking updated source"
            )


def test_missing_original_and_unlocated_quote_are_not_forged():
    _, kid = seed()
    with store.connection() as c:
        c.execute("UPDATE knowledge SET quote='not in any source' WHERE id=?", (kid,))
        unified.sync_legacy(c, kid=kid)
        row = next(r for r in unified.ledger(c, project_id="library") if r["id"] == kid)
        assert not row["checks"]["evidence_located"]
        assert row["evidence"][0]["unresolved"]
        assert "page" not in row["evidence"][0]["locator"]


def test_native_quality_edit_checks_quote_scope_and_versions():
    from fastapi.testclient import TestClient
    from app.main import app

    pid, _ = seed()
    with store.connection(pid) as c:
        edge = next(
            e for e in unified.graph(c, project_id=pid)["edges"] if e["kind"] == "USES"
        )
    client = TestClient(app)
    body = {
        "actor": "Reviewer",
        "reason": "Clarify explanation",
        "expected_version": edge["version"],
        "payload": {
            "evidence": "Method A uses knowledge B.",
            "description": "Independently edited",
        },
    }
    response = client.patch("/api/learning/quality/" + edge["id"], json=body)
    assert response.status_code == 200, response.text
    assert response.json()["record"]["explanation"] == "Independently edited"
    assert (
        client.patch("/api/learning/quality/" + edge["id"], json=body).status_code
        == 409
    )
    assert (
        client.get(
            "/api/knowledge/edges/" + edge["id"], params={"project_id": "library"}
        ).status_code
        == 404
    )
    value = client.get("/api/knowledge/graph", params={"project_id": pid}).json()
    assert all(n["project_id"] == pid for n in value["nodes"])
    assert (
        client.get(
            "/api/knowledge/graph", params={"project_id": "not-a-project"}
        ).status_code
        == 404
    )


def test_metadata_collection_can_be_followed_by_saved_body_without_empty_parse():
    with store.connection() as c:
        upsert_paper(
            c, PaperDoc(uid="later", title="Metadata first", year=2024).model_dump()
        )
        unified.sync_metadata(c, uid="later")
        src = store.sources(c, "library")[0]
        assert not store.source_blocks(c, src["asset_id"])
    with store.connection() as c:
        save_document(
            c,
            "later",
            ParsedPaper(
                uid="later",
                title="Metadata first",
                abstract="",
                sections=[
                    Section(
                        heading="Body", text="The saved body arrived later.", page=1
                    )
                ],
            ),
        )
        unified.sync_metadata(c, uid="later")
        updated = store.sources(c, "library")[0]
        assert updated["id"] == src["id"]
        assert (
            store.source_blocks(c, updated["asset_id"])[0]["text"]
            == "The saved body arrived later."
        )


@pytest.mark.parametrize(
    "kind,payload",
    [
        ("entity", {"type": None, "name": None, "evidence": 3}),
        (
            "relation",
            {
                "src_type": None,
                "src_name": "A",
                "dst_type": None,
                "dst_name": ["bad name"],
                "rel_type": None,
            },
        ),
    ],
)
def test_malformed_legacy_fields_are_preserved_and_cannot_be_silently_verified(
    kind, payload
):
    with store.connection() as c:
        upsert_paper(
            c,
            PaperDoc(
                uid="old-fields", title="Historical source", year=2024
            ).model_dump(),
        )
        kid = save_proposal(c, "old-fields", kind, payload, 0.5)
        c.execute(
            "INSERT INTO knowledge(id,paper_uid,status) VALUES(?,'old-fields','human_verified')",
            (kid,),
        )
        unified.migrate(c)
        mapped = c.execute(
            "SELECT record_id,record_table FROM kw_legacy_map WHERE scope_id='library' AND legacy_table='knowledge' AND legacy_id=?",
            (str(kid),),
        ).fetchone()
        value = store.record(c, mapped[1], "library", mapped[0])
        assert value["quality_status"] == "human_verified"
        assert value["metadata"]["legacy_input_issues"]
        assert json.loads(value["metadata"]["legacy_payload_raw"]) == payload
        assert isinstance(value["kind"], str)
        unified.migrate(c)
        assert (
            store.record(c, mapped[1], "library", mapped[0])["version"]
            == value["version"]
        )
        with pytest.raises(HTTPException):
            unified.review_record(
                c, value["id"], "verify", "Reviewer", "Cannot accept missing structure"
            )
