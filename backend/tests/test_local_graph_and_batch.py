import json
from contextlib import closing

from fastapi.testclient import TestClient
from neo4j.exceptions import ServiceUnavailable

from app.db.sqlite import connect
from app.db.proposals import save_proposal
from app.main import app


def test_offline_graph_browses_metadata_and_candidate_provenance(monkeypatch):
    def stopped():
        raise ServiceUnavailable("not running")
    monkeypatch.setattr("app.db.neo4j_client.get_driver", stopped)
    with closing(connect()) as conn:
        conn.execute("INSERT INTO papers(uid,title,categories_json) VALUES('p','Robotics study','[\"cs.RO\"]')")
        pid = save_proposal(conn, "p", "relation", {
            "src_name": "Robotics study", "src_uid": "p", "src_type": "paper",
            "dst_name": "Diffusion Policy", "dst_type": "method", "rel_type": "USES",
        }, .9)
        conn.execute("INSERT INTO knowledge(id,paper_uid,status,passage_id) VALUES(?, 'p','candidate','passage-one')", (pid,))
        from app.knowledge.unified import migrate
        migrate(conn)
        conn.commit()
    client = TestClient(app)
    result = client.get("/api/graph/overview").json()
    assert result["backend"] == "sqlite"
    assert {node["name"] for node in result["nodes"]} == {"Robotics study", "cs.RO", "Diffusion Policy"}
    assert any(link["quality_status"] == "metadata" for link in result["links"])
    candidate = next(link for link in result["links"] if link["rel_type"] == "USES")
    assert candidate["quality_status"] == "candidate" and candidate["passage_id"] == "passage-one"
    found = client.get("/api/graph/nodes", params={"q": "diffusion", "type": "method"}).json()["items"]
    assert len(found) == 1
    neighbors = client.get("/api/graph/neighbors/p").json()
    assert len(neighbors["nodes"]) == 3
    with closing(connect()) as conn:
        assert conn.execute("SELECT status FROM knowledge WHERE id=?", (pid,)).fetchone()[0] == "candidate"


def test_batch_verification_reduces_requests_without_cross_assigning_verdicts(monkeypatch):
    from app.pipeline.evidence import _verify_batch
    requests = []
    def model(messages, **_):
        requests.append(messages)
        return json.dumps({"verdicts": [{"id": 1, "supported": True}, {"id": 0, "supported": False}]})
    monkeypatch.setattr("app.pipeline.evidence.chat", model)
    verdicts = _verify_batch("Alpha and Beta are described.", [{"evidence": "Alpha"}, {"evidence": "Beta"}, {"evidence": "invented"}])
    assert len(requests) == 1
    assert verdicts[0]["supported"] is False and verdicts[1]["supported"] is True
    assert 2 not in verdicts


def test_collection_keeps_the_workers_connection_open(monkeypatch):
    from app.collector.service import run_collect
    monkeypatch.setattr("app.collector.service.fetch_topic", lambda *_: [])
    with closing(connect()) as conn:
        run_collect([], [], 2020, 5, connection=conn)
        assert conn.execute("SELECT 1").fetchone()[0] == 1


def test_full_extraction_batches_and_overlaps_only_network_work(monkeypatch):
    import threading
    import time
    from app.db.workspace import save_document
    from app.models.paper import ParsedPaper, Section
    from app.pipeline.evidence import extract_document

    calls, thread_ids = [], set()
    lock = threading.Lock()
    active, peak = 0, 0
    names = [f"Concept{index}" for index in range(8)]

    def model(messages, **_):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            calls.append(messages)
        time.sleep(.03)  # Simulated network latency, never a paid model request.
        with lock:
            active -= 1
        if "candidates" in messages[1]["content"]:
            return json.dumps({"verdicts": [{"id": i, "supported": True} for i in range(8)]})
        return json.dumps({"entities": [{"type": "concept", "name": name, "evidence": name, "confidence": .5} for name in names]})

    monkeypatch.setattr("app.pipeline.evidence.chat", model)
    with closing(connect()) as conn:
        conn.execute("INSERT INTO papers(uid,title) VALUES('batch','Batch test')")
        conn.commit()
        save_document(conn, "batch", ParsedPaper(uid="batch", title="Batch test", abstract="",
                      sections=[Section(heading=f"Section {i}", text=" ".join(names), page=i+1) for i in range(3)]))
        owner = threading.get_ident()
        conn.set_trace_callback(lambda _: thread_ids.add(threading.get_ident()))
        result = extract_document(conn, {"uid": "batch", "title": "Batch test"})
        assert result["entities"] == 24
        assert len(calls) == 6  # Three extraction + three verification calls; previously 27.
        assert 2 <= peak <= 3
        assert thread_ids == {owner}
        assert extract_document(conn, {"uid": "batch", "title": "Batch test"})["cached"] == 3
        assert len(calls) == 6


def test_reference_metadata_survives_an_unavailable_independent_graph(monkeypatch):
    from app.collector.citations import backfill_citations
    from app.graphsvc.local import view
    monkeypatch.setattr("app.collector.citations.fetch_citations", lambda *_: ["referenced"])
    def unavailable(*_):
        raise ServiceUnavailable("offline")
    monkeypatch.setattr("app.collector.citations.merge_cites_batch", unavailable)
    with closing(connect()) as conn:
        conn.execute("INSERT INTO papers(uid,title,arxiv_id) VALUES('source','Source paper','2401.12345')")
        conn.commit()
        assert backfill_citations(conn, ["source"]) == 1
    graph = view()
    citation = next(link for link in graph["links"] if link["rel_type"] == "CITES")
    source = next(node for node in graph['nodes'] if node['uid'] == citation['source'])
    referenced = next(node for node in graph['nodes'] if node['uid'] == citation['target'])
    assert source['paper_uid'] == 'source'
    assert referenced['metadata']['reference_uid'] == 'referenced'
    assert referenced['metadata']['available'] is False


def test_malformed_long_output_retries_smaller_source_without_accepting_partial_json(monkeypatch):
    from app.pipeline.evidence import _extract_text
    lengths = []
    def model(messages, **_):
        text = messages[1]["content"].split("当前章节原文：", 1)[1]
        lengths.append(len(text))
        return '{"entities":[' if len(text) > 1400 else '{"entities":[],"relations":[]}'
    monkeypatch.setattr("app.pipeline.evidence.chat", model)
    result = _extract_text("Long source", "An unchanged source sentence. " * 90)
    assert result.entities == [] and result.relations == []
    assert len(lengths) > 1 and min(lengths) < max(lengths)
