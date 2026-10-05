from app.db.proposals import (
    all_entity_vectors,
    get_proposal,
    list_proposals,
    save_entity_vector,
    save_proposal,
    update_status,
)
from app.db.sqlite import connect


def test_save_and_list_proposals():
    conn = connect(":memory:")
    pid = save_proposal(conn, "2401.12345", "entity",
                        {"type": "method", "name": "PPO", "evidence": "e"}, 0.9)
    save_proposal(conn, "2401.12345", "relation",
                  {"rel_type": "USES", "src_name": "a", "dst_name": "b", "evidence": "e"}, 0.6)
    pending = list_proposals(conn)
    assert len(pending) == 2
    rels = list_proposals(conn, kind="relation")
    assert len(rels) == 1
    row = get_proposal(conn, pid)
    assert row["payload"]["name"] == "PPO"


def test_update_status_and_edit():
    conn = connect(":memory:")
    pid = save_proposal(conn, "p1", "entity", {"type": "concept", "name": "TD", "evidence": "e"}, 0.7)
    update_status(conn, pid, "approved", edited_payload={"type": "concept", "name": "TD学习", "evidence": "e"})
    row = get_proposal(conn, pid)
    assert row["status"] == "approved"
    assert row["payload"]["name"] == "TD学习"


def test_entity_vector_roundtrip():
    conn = connect(":memory:")
    save_entity_vector(conn, "method:ppo", "PPO", [0.1, 0.2, 0.3])
    vecs = all_entity_vectors(conn)
    assert len(vecs) == 1
    assert vecs[0]["uid"] == "method:ppo"
    assert all(abs(a - b) < 1e-9 for a, b in zip(vecs[0]["embedding"], [0.1, 0.2, 0.3]))

def test_save_proposal_is_idempotent_for_same_payload():
    conn = connect(":memory:")
    payload = {"type": "method", "name": "PPO", "evidence": "e"}
    first = save_proposal(conn, "p1", "entity", payload, 0.9)
    second = save_proposal(conn, "p1", "entity", payload, 0.9)
    assert first == second
    assert len(list_proposals(conn)) == 1
