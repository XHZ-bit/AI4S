from app.db import neo4j_client


def test_merge_paper_cypher_compiles():
    query, params = neo4j_client._paper_merge_query(
        {"uid": "2401.12345", "title": "T", "year": 2024, "source": "arxiv"}
    )
    assert "MERGE (p:Entity {uid: $uid})" in query
    assert "SET p:Paper" in query
    assert params["uid"] == "2401.12345"


def test_merge_cites_cypher():
    query, params = neo4j_client._cites_merge_query("a1", "b1")
    assert "MERGE" in query and "CITES" in query
    assert params == {"src": "a1", "dst": "b1"}
