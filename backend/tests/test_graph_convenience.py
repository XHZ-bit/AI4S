from contextlib import closing
from fastapi.testclient import TestClient
from app.main import app
from app.db.sqlite import connect
from app.db.proposals import save_proposal
from app.graphsvc.resources import access_links
from app.knowledge.unified import migrate


def seed_sources(count=4):
    with closing(connect()) as db:
        for i in range(count):
            db.execute(
                "INSERT INTO papers(uid,title) VALUES(?,?)", (f"p{i}", f"Paper {i}")
            )
            db.commit()
            save_proposal(
                db,
                f"p{i}",
                "entity",
                {
                    "type": "dataset",
                    "name": ["H2O", "TACO", "GigaHands", "Unknown set"][i % 4],
                    "evidence": "Original description",
                    "passage_id": f"passage-{i}",
                },
                0.7,
            )
            save_proposal(
                db,
                f"p{i}",
                "relation",
                {
                    "src_name": f"Method {i}",
                    "src_type": "method",
                    "dst_name": ["H2O", "TACO", "GigaHands", "Unknown set"][i % 4],
                    "dst_type": "dataset",
                    "rel_type": "EVALUATES_ON",
                    "passage_id": f"passage-{i}",
                },
                0.6,
            )
        migrate(db)
        db.commit()


def test_filtered_graph_shows_multiple_datasets_and_source_context():
    seed_sources()
    with TestClient(app) as client:
        response = client.get("/api/graph/context", params={"type": "dataset"})
        assert response.status_code == 200, response.text
        graph = response.json()
        assert graph["matched_count"] == 4 and graph["shown_matches"] == 4
        assert len(graph["nodes"]) == 12 and len(graph["links"]) >= 8
        assert {n["name"] for n in graph["nodes"] if n["is_match"]} == {
            "H2O",
            "TACO",
            "GigaHands",
            "Unknown set",
        }
        assert graph["context_count"] == 8
        assert all(link["paper_uid"].startswith("p") for link in graph["links"])
        assert any(link["passage_id"] == "passage-0" for link in graph["links"])
        empty = client.get(
            "/api/graph/context", params={"q": "not present", "type": "dataset"}
        ).json()
        assert (
            empty["matched_count"] == 0
            and empty["nodes"] == []
            and empty["links"] == []
        )


def test_resource_access_uses_source_url_and_safe_labeled_fallback():
    links = access_links(
        "H2O",
        "dataset",
        {
            "url": "https://publisher.example/data",
            "evidence": "Other https://publisher.example/docs",
        },
    )
    assert (
        links[0]["origin"] == "source_record"
        and links[0]["url"] == "https://publisher.example/data"
    )
    assert any("h2odataset" in x["url"] and x["origin"] == "name_match" for x in links)
    assert all(
        x["url"].startswith(("https://", "http://"))
        for x in access_links(
            "Unknown <test>", "dataset", {"url": "javascript:alert(1)"}
        )
    )
    unknown = access_links("Unknown set", "dataset")
    assert len(unknown) == 1 and unknown[0]["origin"] == "web_search"
    assert access_links("Probability", "concept") == []


def test_context_is_bounded_and_does_not_change_candidate_status():
    seed_sources(28)
    with TestClient(app) as client:
        data = client.get(
            "/api/graph/context", params={"type": "method", "limit": 16}
        ).json()
        assert len(data["nodes"]) <= 16 and data["truncated"]
        assert data["matched_count"] == 28
        with closing(connect()) as db:
            assert not db.execute(
                "SELECT 1 FROM extraction_proposals WHERE status!='pending'"
            ).fetchone()


def test_project_context_keeps_sources_in_project():
    seed_sources()
    with TestClient(app) as client:
        r = client.post(
            "/api/projects",
            json={
                "title": "Scope",
                "research_question": "Open question",
                "domain": "robot_policy_learning",
                "constraints": {"version": 1, "objective": "Explore"},
            },
        )
        assert r.status_code == 201, r.text
        pid = r.json()["id"]
        assert (
            client.post(
                f"/api/workbench/projects/{pid}/papers", json={"paper_uid": "p0"}
            ).status_code
            == 200
        )
        data = client.get(
            "/api/graph/context", params={"project_id": pid, "type": "dataset"}
        ).json()
        assert data["matched_count"] == 1
        assert all(link["paper_uid"] == "p0" for link in data["links"])
        assert not any(n["uid"] == "p1" for n in data["nodes"])


def test_graph_sources_deduplicate_papers_and_include_titles():
    seed_sources(1)
    with closing(connect()) as db:
        save_proposal(
            db,
            "p0",
            "entity",
            {
                "type": "dataset",
                "name": "H2O",
                "evidence": "Another passage",
                "passage_id": "second-location",
            },
            0.7,
        )
        migrate(db)
        db.commit()
    with TestClient(app) as client:
        graph = client.get("/api/graph/context", params={"type": "dataset"}).json()
        dataset = next(n for n in graph["nodes"] if n["name"] == "H2O")
        assert len(dataset["sources"]) == 1
        assert dataset["sources"][0]["paper_title"] == "Paper 0"
        assert dataset["sources"][0]["passage_id"]


def test_paper_workspace_exposes_resource_access_without_graph_enabled():
    seed_sources(1)
    with closing(connect()) as db:
        identity = db.execute(
            "SELECT id FROM extraction_proposals WHERE paper_uid='p0' AND kind='entity'"
        ).fetchone()[0]
        db.execute(
            "INSERT INTO knowledge(id,paper_uid,status,quote) VALUES(?,'p0','candidate','H2O description')",
            (identity,),
        )
        db.commit()
    with TestClient(app) as client:
        prefs = client.get("/api/preferences").json()
        prefs["features"]["graph"] = False
        prefs = {
            k: v for k, v in prefs.items() if k not in ("avatar_url", "default_model")
        }
        prefs["provider"] = {
            k: v for k, v in prefs["provider"].items() if k != "has_key"
        }
        assert client.put("/api/preferences", json=prefs).status_code == 200
        data = client.get("/api/learning/papers/p0").json()
        item = next(x for x in data["knowledge"] if x["kind"] == "entity")
        assert any("h2odataset" in link["url"] for link in item["access_links"])
        assert client.get("/api/graph/context").status_code == 409
