"""Synthetic graph fixtures test provenance and ordering, not scientific validity."""

import pytest
from app.db.sqlite import connect, upsert_paper
from app.db.workspace import save_document, document_view
from app.db.proposals import save_proposal
from app.models.paper import ParsedPaper
from app.models.roadmap import LearnerProfile
from app.roadmap.generate import generate_roadmap


def setup_trusted(monkeypatch):
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
                "src_name": uid,
                "src_type": "paper",
                "dst_name": concept,
                "dst_type": "concept",
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
        "INSERT INTO knowledge(id,paper_uid,status,layer) VALUES(?,'paper:0','human_verified','teaching')",
        (kid,),
    )
    conn.commit()
    monkeypatch.setattr(
        "app.roadmap.generate.resolve_target",
        lambda name: {"target": "method:target", "basics": "concept:basics"}.get(name),
    )
    monkeypatch.setattr(
        "app.roadmap.generate.get_prerequisite_edges",
        lambda: [("concept:basics", "method:target")],
    )
    monkeypatch.setattr(
        "app.roadmap.generate.get_papers_for_concept", lambda uid: papers.get(uid, [])
    )
    return conn


def test_generate_roadmap_basic(monkeypatch):
    conn = setup_trusted(monkeypatch)
    result = generate_roadmap(
        LearnerProfile(goal="target", target_uid="method:target"), conn
    )
    assert len(result.phases) == 2
    assert result.phases[0].title == "concept:basics"
    assert all(i.evidence_ids and i.task_id for ph in result.phases for i in ph.items)
    assert not result.innovations
    assert all(i.kind == "paper" for ph in result.phases for i in ph.items)


def test_generate_roadmap_prunes_known(monkeypatch):
    conn = setup_trusted(monkeypatch)
    result = generate_roadmap(
        LearnerProfile(
            goal="target", target_uid="method:target", known_concepts=["basics"]
        ),
        conn,
    )
    assert len(result.phases) == 1 and result.phases[0].title == "method:target"


def test_generate_roadmap_persists(monkeypatch):
    from app.db.roadmaps import get_roadmap

    conn = setup_trusted(monkeypatch)
    result = generate_roadmap(
        LearnerProfile(goal="target", target_uid="method:target"), conn
    )
    assert (
        get_roadmap(conn, result.id).phases[0].items[0].task_id
        == result.phases[0].items[0].task_id
    )


def test_unverified_graph_does_not_create_route(monkeypatch):
    conn = setup_trusted(monkeypatch)
    conn.execute("UPDATE knowledge SET status='withdrawn'")
    conn.commit()
    with pytest.raises(ValueError):
        generate_roadmap(
            LearnerProfile(goal="target", target_uid="method:target"), conn
        )


def test_ambiguous_known_concept_requires_confirmation(monkeypatch):
    conn = setup_trusted(monkeypatch)
    with pytest.raises(ValueError):
        generate_roadmap(
            LearnerProfile(
                goal="target", target_uid="method:target", known_concepts=["ambiguous"]
            ),
            conn,
        )
