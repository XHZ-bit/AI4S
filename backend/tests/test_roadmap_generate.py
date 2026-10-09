"""Synthetic graph fixtures test provenance and ordering, not scientific validity."""

import pytest
import sqlite3
from fastapi.testclient import TestClient
from app.main import app
from app.db.sqlite import connect, upsert_paper
from app.db.workspace import save_document, document_view
from app.db.proposals import save_proposal
from app.models.paper import ParsedPaper
from app.models.roadmap import LearnerProfile
from app.roadmap.generate import generate_roadmap


def setup_trusted():
    conn = connect(":memory:")
    papers = {}
    for idx, concept in enumerate(["concept:basics", "method:target"]):
        uid = f"paper:{idx}"
        upsert_paper(
            conn,
            dict(
                uid=uid,
                arxiv_id=None,
                title=uid,
                abstract="source text",
                authors=[],
                year=2024,
                venue=None,
                categories=[],
                published=None,
                pdf_url=None,
                code_url=None,
                source="test",
            ),
        )
        save_document(
            conn, uid, ParsedPaper(uid=uid, title=uid, abstract="source text")
        )
        passage = document_view(conn, uid)[0]["passages"][0]
        kid = save_proposal(
            conn,
            uid,
            "relation",
            {
                "rel_type": "USES",
                "src_uid": uid,
                "src_name": uid,
                "src_type": "paper",
                "dst_uid": concept,
                "dst_name": concept.split(":")[1],
                "dst_type": concept.split(":")[0],
            },
            1,
        )
        conn.execute(
            "INSERT INTO knowledge(id,paper_uid,status,passage_id) VALUES(?,?,'human_verified',?)",
            (kid, uid, passage["id"]),
        )
        papers[concept] = [
            dict(
                uid=uid,
                title=uid,
                year=2024,
                evidence_ids=[passage["id"]],
                knowledge_ids=[kid],
            )
        ]
    passage_id = document_view(conn, "paper:0")[0]["passages"][0]["id"]
    kid = save_proposal(
        conn,
        "paper:0",
        "relation",
        {
            "rel_type": "PREREQUISITE_OF",
            "src_uid": "concept:basics",
            "src_type": "concept",
            "src_name": "basics",
            "dst_uid": "method:target",
            "dst_type": "method",
            "dst_name": "target",
        },
        1,
    )
    conn.execute(
        "INSERT INTO knowledge(id,paper_uid,status,layer,passage_id) VALUES(?,'paper:0','human_verified','teaching',?)",
        (kid, passage_id),
    )
    conn.commit()
    return conn


def test_generate_roadmap_basic():
    conn = setup_trusted()
    result = generate_roadmap(
        LearnerProfile(goal="target", target_uid="method:target"), conn
    )
    assert len(result.phases) == 2
    assert result.phases[0].title == "concept:basics"
    assert all(i.evidence_ids and i.task_id for ph in result.phases for i in ph.items)
    assert not result.innovations
    assert all(i.kind == "paper" for ph in result.phases for i in ph.items)


def test_generate_roadmap_prunes_known():
    conn = setup_trusted()
    result = generate_roadmap(
        LearnerProfile(
            goal="target", target_uid="method:target", known_concepts=["basics"]
        ),
        conn,
    )
    assert len(result.phases) == 1 and result.phases[0].title == "method:target"


def test_generate_roadmap_persists():
    from app.db.roadmaps import get_roadmap

    conn = setup_trusted()
    result = generate_roadmap(
        LearnerProfile(goal="target", target_uid="method:target"), conn
    )
    assert (
        get_roadmap(conn, result.id).phases[0].items[0].task_id
        == result.phases[0].items[0].task_id
    )


def test_unverified_graph_does_not_create_route():
    conn = setup_trusted()
    conn.execute("UPDATE knowledge SET status='withdrawn'")
    conn.commit()
    with pytest.raises(ValueError):
        generate_roadmap(
            LearnerProfile(goal="target", target_uid="method:target"), conn
        )


def test_ambiguous_known_concept_requires_confirmation():
    conn = setup_trusted()
    with pytest.raises(ValueError):
        generate_roadmap(
            LearnerProfile(
                goal="target", target_uid="method:target", known_concepts=["ambiguous"]
            ),
            conn,
        )


def test_unpublished_preview_uses_same_planner_without_saving():
    conn = setup_trusted()
    conn.execute("UPDATE knowledge SET status='demo_curated'")
    conn.commit()
    profile = LearnerProfile(goal="target", target_uid="method:target", known_concepts=["basics"])
    preview = generate_roadmap(profile, conn, status="demo_curated", persist=False)
    assert [phase.title for phase in preview.phases] == ["method:target"]
    assert conn.execute("SELECT count(*) FROM roadmaps").fetchone()[0] == 0
    with pytest.raises(ValueError):
        generate_roadmap(profile, conn)


def test_automatic_gate_rejects_broken_source_quote():
    from app.roadmap.auto_evaluate import evaluate_candidates

    conn = setup_trusted()
    for row in conn.execute(
        "SELECT k.id,pa.document_id,pa.text FROM knowledge k "
        "JOIN passages pa ON pa.id=k.passage_id"
    ).fetchall():
        conn.execute(
            "UPDATE knowledge SET status='demo_curated',document_id=?,quote=?,start_offset=0,end_offset=6 WHERE id=?",
            (row["document_id"], row["text"][:6], row["id"]),
        )
    conn.commit()
    profiles = {"new": [], "prepared": ["basics"]}
    good = evaluate_candidates(conn, "method:target", profiles)
    assert good["passed"] and good["checked_relations"] == 3
    conn.execute("UPDATE knowledge SET quote='fabricated' WHERE id=1")
    conn.commit()
    bad = evaluate_candidates(conn, "method:target", profiles)
    assert not bad["passed"]
    assert any("evidence quote" in failure for failure in bad["failures"])


def test_auto_checked_preview_is_read_only_and_blocks_broken_quote(tmp_path, monkeypatch):
    conn = setup_trusted()
    for row in conn.execute(
        "SELECT k.id,pa.document_id,pa.text FROM knowledge k "
        "JOIN passages pa ON pa.id=k.passage_id"
    ).fetchall():
        conn.execute(
            "UPDATE knowledge SET status='auto_checked',document_id=?,quote=?,"
            "start_offset=0,end_offset=6 WHERE id=?",
            (row["document_id"], row["text"][:6], row["id"]),
        )
    conn.commit()
    path = tmp_path / "candidate-route.db"
    with sqlite3.connect(path) as target:
        conn.backup(target)
    conn.close()
    monkeypatch.setattr("app.api.roadmap._connect", lambda: connect(str(path)))
    client = TestClient(app)
    body = {"profile": {"goal": "target", "target_uid": "method:target", "weekly_hours": 4}}
    response = client.post("/api/roadmap/auto-preview", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["evidence_level"] == "machine_checked_preview"
    assert len(response.json()["route"]["phases"]) == 2
    with connect(str(path)) as stored:
        assert stored.execute("SELECT count(*) FROM roadmaps").fetchone()[0] == 0
        stored.execute("UPDATE knowledge SET quote='fabricated' WHERE id=(SELECT min(id) FROM knowledge)")
        stored.commit()
    rejected = client.post("/api/roadmap/auto-preview", json=body)
    assert rejected.status_code == 422
