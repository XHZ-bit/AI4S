import json
import pytest
from fastapi.testclient import TestClient
from app.db.sqlite import connect, upsert_paper
from app.db.workspace import save_document, document_view, get_state, put_state
from app.models.paper import ParsedPaper, Section
from app.pipeline.evidence import extract_document, knowledge_list
from app.main import app


def seed(conn):
    paper = {
        "uid": "p1",
        "arxiv_id": None,
        "title": "Test Paper",
        "abstract": "We describe a method.",
        "authors": [],
        "year": 2024,
        "venue": None,
        "categories": [],
        "published": None,
        "pdf_url": None,
        "code_url": None,
        "source": "upload",
    }
    upsert_paper(conn, paper)
    return paper


def test_document_versions_exact_offsets_and_cache(monkeypatch):
    conn = connect(":memory:")
    paper = seed(conn)
    parsed = ParsedPaper(
        uid="p1",
        title="Test Paper",
        abstract="",
        sections=[
            Section(heading="Methods", text="We use PPO under condition X.", page=2)
        ],
    )
    did = save_document(conn, "p1", parsed)
    assert save_document(conn, "p1", parsed) == did
    assert len(document_view(conn, "p1")) == 1
    calls = []

    def model(messages, json_mode=False):
        calls.append(messages)
        if len(calls) == 1:
            return json.dumps(
                {
                    "entities": [
                        {
                            "type": "method",
                            "name": "PPO",
                            "confidence": 0.99,
                            "evidence": "PPO under condition X",
                        }
                    ],
                    "relations": [],
                }
            )
        return '{"supported":true,"reason":"direct quote","conditions":"condition X"}'

    monkeypatch.setattr("app.pipeline.evidence.chat", model)
    extract_document(conn, paper)
    item = knowledge_list(conn, "p1")[0]
    assert item["status"] == "auto_checked"
    assert item["proposal_status"] == "pending"
    passage = document_view(conn, "p1")[0]["passages"][0]
    assert passage["text"][item["start_offset"] : item["end_offset"]] == item["quote"]
    assert passage["page"] == 2
    assert extract_document(conn, paper)["cached"] == 1
    assert len(calls) == 2


def test_missing_quote_cannot_be_verified(monkeypatch):
    conn = connect()
    paper = seed(conn)
    monkeypatch.setattr(
        "app.pipeline.evidence.chat",
        lambda *a, **k: json.dumps(
            {
                "entities": [
                    {
                        "type": "concept",
                        "name": "invented",
                        "confidence": 1,
                        "evidence": "not in paper",
                    }
                ]
            }
        ),
    )
    extract_document(conn, paper)
    kid = knowledge_list(conn, "p1")[0]["id"]
    conn.close()
    client = TestClient(app)
    r = client.post(
        f"/api/learning/quality/{kid}",
        json={"action": "verify", "actor": "tester", "reason": "checked"},
    )
    assert r.status_code == 422


def test_workspace_optimistic_concurrency_and_reopen():
    conn = connect()
    seed(conn)
    state = get_state(conn, "p1")["state"]
    state["reading"]["one"] = True
    saved = put_state(conn, "p1", state, 0)
    assert saved["version"] == 1
    with pytest.raises(ValueError):
        put_state(conn, "p1", state, 0)
    conn.close()
    conn = connect()
    assert get_state(conn, "p1")["state"]["reading"]["one"] is True
    conn.close()


def test_workspace_feedback_and_pagination():
    conn = connect()
    paper = seed(conn)
    for i in range(44):
        upsert_paper(conn, {**paper, "uid": f"p{i + 2}"})
    conn.close()
    client = TestClient(app)
    a = client.get("/api/papers?limit=20&offset=0").json()
    b = client.get("/api/papers?limit=20&offset=20").json()
    c = client.get("/api/papers?limit=20&offset=40").json()
    assert a["total"] == 45 and len(c["items"]) == 5
    assert not ({p["uid"] for p in a["items"]} & {p["uid"] for p in b["items"]})
    r = client.post(
        "/api/learning/papers/p1/feedback",
        json={"kind": "not_understood", "detail": "need help"},
    )
    assert r.status_code == 201
    assert client.get("/api/learning/quality").json()["feedback"][0]["status"] == "open"
    assert (
        client.patch(
            "/api/learning/papers/p1", json={"version": 0, "state": {"answers": []}}
        ).status_code
        == 422
    )


def test_withdraw_marks_recommendation_stale_without_losing_done(monkeypatch):
    from app.db.proposals import save_proposal
    from app.db.roadmaps import save_roadmap, get_roadmap
    from app.models.roadmap import (
        LearnerProfile,
        RoadmapResult,
        RoadmapPhase,
        RoadmapItem,
    )

    conn = connect()
    seed(conn)
    kid = save_proposal(conn, "p1", "entity", {"name": "PPO", "type": "method"}, 1)
    conn.execute(
        "INSERT INTO knowledge(id,paper_uid,status) VALUES(?,'p1','human_verified')",
        (kid,),
    )
    conn.commit()
    rid = save_roadmap(
        conn,
        RoadmapResult(
            goal="g",
            knowledge_ids=[kid],
            phases=[
                RoadmapPhase(
                    phase=7,
                    title="p",
                    weeks="w",
                    items=[
                        RoadmapItem(
                            kind="paper", title="x", reason="r", evidence="e", done=True
                        )
                    ],
                )
            ],
        ),
        LearnerProfile(goal="g"),
    )
    conn.close()
    client = TestClient(app)
    assert (
        client.post(
            f"/api/learning/quality/{kid}",
            json={"action": "withdraw", "actor": "reviewer", "reason": "incorrect"},
        ).status_code
        == 200
    )
    conn = connect()
    result = get_roadmap(conn, rid)
    assert result.stale and result.phases[0].items[0].done
    assert conn.execute("SELECT count(*) FROM audit_events").fetchone()[0] == 1
    conn.close()


def test_progress_uses_task_id_and_version():
    from app.db.roadmaps import save_roadmap, get_roadmap, update_item_done
    from app.models.roadmap import (
        LearnerProfile,
        RoadmapResult,
        RoadmapPhase,
        RoadmapItem,
    )

    conn = connect(":memory:")
    rid = save_roadmap(
        conn,
        RoadmapResult(
            goal="g",
            phases=[
                RoadmapPhase(
                    phase=7,
                    title="p",
                    weeks="w",
                    items=[
                        RoadmapItem(kind="paper", title="x", reason="r", evidence="e")
                    ],
                )
            ],
        ),
        LearnerProfile(goal="g"),
    )
    result = get_roadmap(conn, rid)
    tid = result.phases[0].items[0].task_id
    changed = update_item_done(conn, rid, task_id=tid, version=1, done=True)
    assert changed.version == 2 and changed.phases[0].items[0].done
    with pytest.raises(ValueError):
        update_item_done(conn, rid, task_id=tid, version=1, done=False)


def test_invalid_generated_evidence_is_not_saved(monkeypatch):
    from app.guidance import generate_guide

    conn = connect(":memory:")
    seed(conn)
    save_document(conn, "p1", ParsedPaper(uid="p1", title="Test", abstract="text"))
    monkeypatch.setattr(
        "app.guidance.chat",
        lambda *a,
        **k: '{"explanations":[{"topic":"x","explanation":"y","passage_ids":["invented"]}]}',
    )
    with pytest.raises(ValueError):
        generate_guide(conn, "p1")
    assert not conn.execute("SELECT * FROM guides").fetchone()


def test_upload_file_survives_parser_failure(monkeypatch, tmp_path):
    from app.api.papers import process_saved_pdf, _store
    from starlette.datastructures import UploadFile
    import io

    uid = _store(UploadFile(filename="bad.pdf", file=io.BytesIO(b"%PDF-broken")))
    monkeypatch.setattr(
        "app.api.papers.parse_pdf",
        lambda *a, **k: (_ for _ in ()).throw(ValueError("bad file")),
    )
    conn = connect()
    with pytest.raises(ValueError):
        process_saved_pdf(conn, uid)
    assert (
        conn.execute(
            "SELECT status FROM pipeline_stages WHERE stage='parse'"
        ).fetchone()[0]
        == "failed"
    )
    from app.api.papers import _data_dir

    assert (_data_dir() / f"{uid}.pdf").exists()
    conn.close()
