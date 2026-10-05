from app.db.proposals import list_proposals
from app.db.sqlite import connect
from app.pipeline.extract import canonical_uid, extract_paper

LLM_JSON = """
{"entities": [
   {"type": "method", "name": "PPO", "confidence": 0.95, "evidence": "uses PPO"},
   {"type": "concept", "name": "clip objective", "confidence": 0.7, "evidence": "clip"}
 ],
 "relations": [
   {"rel_type": "USES", "src_name": "Diffusion Policy", "dst_name": "PPO", "confidence": 0.9, "evidence": "e1"},
   {"rel_type": "COMPARED_WITH", "src_name": "PPO", "dst_name": "SAC", "confidence": 0.3, "evidence": "e2"},
   {"rel_type": "PREREQUISITE_OF", "src_name": "TD", "dst_name": "Actor-Critic", "confidence": 0.2, "evidence": "e3"}
 ]}
"""


def test_extract_paper_saves_proposals_with_grading(monkeypatch):
    conn = connect(":memory:")
    monkeypatch.setattr("app.pipeline.extract.chat", lambda msgs, json_mode=False: LLM_JSON)
    monkeypatch.setattr("app.pipeline.extract.embed", lambda texts: [[0.1, 0.2] for _ in texts])

    result = extract_paper(conn, "2401.12345", "T", "abstract text")
    assert result["entities"] == 2
    assert result["relations"] == 2
    assert result["discarded"] == 1
    pending = list_proposals(conn)
    assert {p["kind"] for p in pending} == {"entity", "relation"}


def test_extract_paper_discards_low_confidence_entities(monkeypatch):
    conn = connect(":memory:")
    low = '{"entities": [{"type": "method", "name": "X", "confidence": 0.2, "evidence": "e"}], "relations": []}'
    monkeypatch.setattr("app.pipeline.extract.chat", lambda msgs, json_mode=False: low)
    monkeypatch.setattr("app.pipeline.extract.embed", lambda texts: [[0.0] for _ in texts])
    result = extract_paper(conn, "p2", "T", "a")
    assert result["entities"] == 0 and result["discarded"] == 1


def test_canonical_uid():
    assert canonical_uid("Method", "Proximal Policy Optimization") == "method:proximal-policy-optimization"
    assert canonical_uid("concept", "TD 学习") == "concept:td-学习"


def test_relation_payload_includes_src_dst_type(monkeypatch):
    conn = connect(":memory:")
    monkeypatch.setattr("app.pipeline.extract.chat", lambda msgs, json_mode=False: LLM_JSON)
    monkeypatch.setattr("app.pipeline.extract.embed", lambda texts: [[0.1] for _ in texts])
    extract_paper(conn, "p1", "T", "a")
    rels = [p for p in list_proposals(conn, kind="relation")]
    uses = next(r for r in rels if r["payload"]["rel_type"] == "USES")
    # PPO 在本批实体中是 method -> dst_type 应为 method
    assert uses["payload"]["dst_type"] == "method"
    # Diffusion Policy 不在本批实体 -> src_type 缺省 concept
    assert uses["payload"]["src_type"] == "concept"
