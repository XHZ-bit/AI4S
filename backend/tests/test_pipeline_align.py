from app.db.proposals import get_proposal, save_entity_vector, save_proposal
from app.db.sqlite import connect
from app.pipeline.align import align_pending_entities, cosine, find_match


def test_cosine_parallel_and_orthogonal():
    assert abs(cosine([1, 0], [1, 0]) - 1.0) < 1e-9
    assert abs(cosine([1, 0], [0, 1])) < 1e-9


def test_find_match_levels():
    conn = connect(":memory:")
    save_entity_vector(conn, "method:ppo", "PPO", [1.0, 0.0])
    assert find_match(conn, "proximal policy optimization", [1.0, 0.0])["decision"] == "manual"
    assert find_match(conn, "PPO", [1.0, 0.0])["decision"] == "auto_merge"
    mid = find_match(conn, "somewhat related", [0.7, 0.7])
    assert mid["decision"] == "manual" and mid["match_uid"] == "method:ppo"
    assert find_match(conn, "totally different", [0.0, 1.0])["decision"] == "new"


def test_align_pending_entities():
    conn = connect(":memory:")
    save_entity_vector(conn, "method:ppo", "PPO", [1.0, 0.0])
    a = save_proposal(conn, "p1", "entity", {"type": "method", "name": "PPO", "evidence": "e"}, 0.9, [1.0, 0.0])
    b = save_proposal(conn, "p1", "entity", {"type": "method", "name": "PPO2", "evidence": "e"}, 0.8, [0.7, 0.7])
    c = save_proposal(conn, "p1", "entity", {"type": "method", "name": "SAC", "evidence": "e"}, 0.8, [0.0, 1.0])

    manual = align_pending_entities(conn)
    assert get_proposal(conn, a)["status"] == "auto_merged"
    assert get_proposal(conn, b)["status"] == "pending"
    assert get_proposal(conn, c)["status"] == "pending"
    assert {p["id"] for p in manual} == {b, c}
    assert get_proposal(conn, b)["payload"]["align"]["match_uid"] == "method:ppo"
    assert get_proposal(conn, c)["payload"]["align"]["decision"] == "new"
