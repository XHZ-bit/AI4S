import json

import pytest
from fastapi.testclient import TestClient

from app.db import projects as store
from app.main import app
from app.models.research import FactRevisionRequest
from tests.test_research_t1_storage import conn as database_fixture, link_paper, make_bundle, make_project, seed_facts, seed_snapshot

conn = database_fixture


def revision(**changes):
    return FactRevisionRequest(expected_version=1, changes=changes, actor="Reviewer", reason="Checked against source")


def test_correction_preserves_versions_and_marks_frozen_snapshot(conn):
    project = make_project(conn)
    link = link_paper(conn, project)
    snapshot, method = seed_snapshot(conn, project, link)
    updated = store.revise_fact(conn, project.id, method.id, revision(name="Corrected method"))
    assert updated.version == 2
    assert updated.status.value == "candidate"
    assert updated.source_kind.value == "user_input"
    assert updated.field_evidence[0].source_kind.value == "user_input"
    assert updated.field_evidence[0].evidence_ids == []
    old = conn.execute("SELECT payload_json FROM research_fact_versions WHERE fact_id=? AND version=1", (method.id,)).fetchone()[0]
    assert json.loads(old)["name"] == "Method A"
    frozen = store.get_snapshot(conn, project.id, snapshot.id)
    assert frozen.plan == snapshot.plan
    assert frozen.frozen_facts == snapshot.frozen_facts
    assert frozen.review_status.value == "needs_review"
    assert store.fact_audit(conn, method.id)[0]["action"] == "content_revision"
    with pytest.raises(store.VersionConflictError):
        store.revise_fact(conn, project.id, method.id, revision(name="Late edit"))
    assert store.get_fact(conn, method.id).name == "Corrected method"


def test_graph_revision_updates_legacy_tools_and_preserves_frozen_plan(conn):
    from app.knowledge import store as kw, unified
    project = make_project(conn)
    snapshot, method = seed_snapshot(conn, project, link_paper(conn, project))
    rid = kw.identity(project.id, 'legacy-fact', method.id)
    original = kw.record(conn, 'kw_nodes', project.id, rid)
    updated = kw.edit_record(conn, 'kw_nodes', project.id, rid, original['version'],
                             {'label': 'Graph corrected name', 'summary': 'Graph checked description'})
    assert conn.in_transaction
    compatible = store.get_fact(conn, method.id)
    assert compatible.name == 'Graph corrected name' and compatible.summary == 'Graph checked description'
    assert compatible.version == 2 and compatible.status.value == 'candidate'
    assert updated['metadata']['legacy_fact_version'] == 2
    frozen = store.get_snapshot(conn, project.id, snapshot.id)
    assert frozen.frozen_facts == snapshot.frozen_facts and frozen.plan == snapshot.plan
    assert frozen.review_status.value == 'needs_review'
    conn.commit()
    unified.sync_research_facts(conn, project.id)
    conn.commit()
    assert store.get_fact(conn, method.id).version == 2
    assert kw.record(conn, 'kw_nodes', project.id, rid)['summary'] == 'Graph checked description'
    # A later explicit edit from the compatible tool wins for that exact field.
    store.revise_fact(conn, project.id, method.id,
        FactRevisionRequest(expected_version=2, changes={'name': 'Later explicit edit'}, actor='Reviewer', reason='Checked again'))
    node = kw.record(conn, 'kw_nodes', project.id, rid)
    assert node['label'] == 'Later explicit edit'
    assert node['summary'] == 'Graph checked description'


def test_graph_review_is_space_local_and_both_directions_withdraw(conn):
    from app.knowledge import store as kw, unified
    from app.models.research import StatusTransitionRequest
    first = make_project(conn, 'First')
    snapshot, method = seed_snapshot(conn, first, link_paper(conn, first))
    second = make_project(conn, 'Second')
    link = link_paper(conn, second)
    bundle = make_bundle(second.id, link.id, method_id='method-other')
    bundle.evidence[0].id = 'evidence-other'
    for fact in [*bundle.methods, *bundle.experiment_settings, *bundle.measurements]:
        for binding in fact.field_evidence:
            binding.evidence_ids = ['evidence-other']
    store.save_candidate_bundle(conn, bundle)
    rid = kw.identity(first.id, 'legacy-fact', method.id)
    unified.review_record(conn, rid, 'verify', 'Reviewer', 'Checked the original')
    conn.commit()
    assert store.get_fact(conn, method.id).status.value == 'user_confirmed'
    assert store.get_fact(conn, 'method-other').version == 1
    assert store.get_fact(conn, 'method-other').status.value == 'candidate'
    unified.review_record(conn, rid, 'withdraw', 'Reviewer', 'The support was withdrawn')
    conn.commit()
    current = store.get_fact(conn, method.id)
    assert current.status.value == 'withdrawn'
    assert not any(n['id'] == rid for n in kw.graph(conn, first.id)['nodes'])
    assert store.get_snapshot(conn, first.id, snapshot.id).frozen_facts == snapshot.frozen_facts
    restored = store.transition_fact(conn, first.id, method.id,
        StatusTransitionRequest(expected_version=current.version, from_status='withdrawn', to_status='candidate', actor='Reviewer', reason='Restore for review'))
    node = kw.record(conn, 'kw_nodes', first.id, rid)
    assert node['quality_status'] == 'candidate' and not node['hidden']
    assert not node['metadata']['source_withdrawn']
    assert node['metadata']['legacy_fact_version'] == restored.version


def test_graph_and_compatibility_versions_roll_back_together(conn):
    from app.knowledge import store as kw
    project = make_project(conn)
    method, _, _, _ = seed_facts(conn, project, link_paper(conn, project))
    rid = kw.identity(project.id, 'legacy-fact', method.id)
    original = kw.record(conn, 'kw_nodes', project.id, rid)
    kw.edit_record(conn, 'kw_nodes', project.id, rid, original['version'], {'label': 'Uncommitted change'})
    conn.rollback()
    assert store.get_fact(conn, method.id).version == 1
    assert kw.record(conn, 'kw_nodes', project.id, rid)['label'] == original['label']
    assert store.fact_audit(conn, method.id) == []


@pytest.mark.parametrize("changes", [{"project_id": "other"}, {"method_id": "other"}, {"status": "user_confirmed"}, {"name": " "}])
def test_invalid_corrections_roll_back(conn, changes):
    project = make_project(conn)
    method, _, _, _ = seed_facts(conn, project, link_paper(conn, project))
    with pytest.raises(store.ProjectStoreError):
        store.revise_fact(conn, project.id, method.id, revision(**changes))
    assert store.get_fact(conn, method.id).version == 1
    assert store.fact_audit(conn, method.id) == []
    assert not conn.in_transaction


def test_missing_measurement_stays_unknown_and_evidence_is_scoped(conn):
    project = make_project(conn)
    method, _, measurement, _ = seed_facts(conn, project, link_paper(conn, project))
    updated = store.revise_fact(conn, project.id, measurement.id, revision(value=None))
    assert updated.value is None
    assert updated.finding_status.value == "unknown"
    invalid = revision(name="Another")
    invalid.evidence_ids = ["foreign"]
    with pytest.raises(store.ValidationError):
        store.revise_fact(conn, project.id, method.id, invalid)
    other = make_project(conn, "Other")
    with pytest.raises(store.NotFoundError):
        store.revise_fact(conn, other.id, method.id, revision(name="Cross project"))
    same = store.revise_fact(conn, project.id, method.id, revision(name=method.name))
    assert same.version == 1 and not conn.in_transaction


def test_revision_http_endpoint_uses_versioned_store(conn, monkeypatch):
    from app.api import projects as routes
    project = make_project(conn)
    method, _, _, _ = seed_facts(conn, project, link_paper(conn, project))
    # Open a distinct connection, just as a real request does.
    import sqlite3
    database = conn.execute("PRAGMA database_list").fetchone()[2]

    def connect():
        value = sqlite3.connect(database)
        value.row_factory = sqlite3.Row
        return value

    monkeypatch.setattr(routes, "_connect", connect)
    client = TestClient(app)
    body = revision(summary="Rechecked description").model_dump()
    response = client.patch(f"/api/projects/{project.id}/facts/{method.id}", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["summary"] == "Rechecked description"
    assert client.patch(f"/api/projects/{project.id}/facts/{method.id}", json=body).status_code == 409


def test_cited_candidates_keep_source_and_revisions_replace_nested_bindings(conn):
    project = make_project(conn)
    link = link_paper(conn, project)
    bundle = make_bundle(project.id, link.id)
    for fact in [*bundle.methods, *bundle.experiment_settings]:
        fact.paper_link_id = None
    bundle.methods[0].field_evidence[0].field_path = "methods[0].name"
    bundle.methods[0].field_evidence[0].note = '{"claim_role":"cited_method"}'
    store.save_candidate_bundle(conn, bundle)
    assert len(store.list_facts(conn, project.id, paper_link_id=link.id)) == 3
    method = store.get_fact(conn, bundle.methods[0].id)
    assert method.paper_link_id is None
    changed = store.revise_fact(conn, project.id, method.id, revision(name="Corrected cited name"))
    assert [binding.field_path for binding in changed.field_evidence] == ["name"]
    # The original source is still available after all old bindings were replaced.
    request = FactRevisionRequest(expected_version=2, changes={"name": "Checked cited name"},
                                  evidence_ids=[bundle.evidence[0].id], actor="Reviewer", reason="Checked")
    assert store.revise_fact(conn, project.id, method.id, request).version == 3
    assert len(store.list_facts(conn, project.id, paper_link_id=link.id)) == 3


def test_same_paper_can_be_extracted_into_two_projects(conn, monkeypatch):
    from app.research import service
    from app.research_extraction import candidates

    raw = {"methods": [{"local_id": "m1", "claim_role": "current_paper_method",
                        "name": {"value": "Method A", "finding_status": "reported",
                                 "evidence": [{"passage_id": "passage-1", "quote": "Method A"}]}}]}
    monkeypatch.setattr(candidates, "chat", lambda *args, **kwargs: json.dumps(raw))
    projects = [make_project(conn, title) for title in ("First", "Second")]
    for project in projects:
        link = link_paper(conn, project)
        bundle = candidates.extract_candidates(service._document_input(conn, project.id, link.id, "doc-1"))
        store.save_candidate_bundle(conn, bundle)
        # Replaying an identical extraction remains idempotent.
        store.save_candidate_bundle(conn, bundle)
        assert len(store.list_facts(conn, project.id)) == 1
        assert len(store.list_evidence(conn, project.id)) == 1


def test_legacy_extraction_is_replayed_without_duplicate_facts(conn, monkeypatch):
    from app.research import service
    from app.research_extraction import candidates

    project = make_project(conn)
    link = link_paper(conn, project)
    raw = {"methods": [{"local_id": "m1", "claim_role": "current_paper_method",
                        "name": {"value": "Method A", "finding_status": "reported",
                                 "evidence": [{"passage_id": "passage-1", "quote": "Method A"}]}}]}
    monkeypatch.setattr(candidates, "chat", lambda *args, **kwargs: json.dumps(raw))
    value = service._document_input(conn, project.id, link.id, "doc-1")
    raw["methods"][0]["summary"] = {"value": "conflicted", "finding_status": "conflicting",
                                    "evidence": [{"passage_id": "passage-1", "quote": "Method A"}]}
    with monkeypatch.context() as legacy:
        legacy.setattr(candidates._Assembler, "scoped_id", lambda self, kind, *parts: candidates._stable_id(kind, *parts))
        previous = candidates.extract_candidates(value)
    store.save_candidate_bundle(conn, previous)
    task = store.create_task(conn, service.TaskKind.PROJECT_EXTRACTION, project.id,
        {"project_id": project.id, "link_id": link.id, "document_id": "doc-1"})
    finished = service.run_extraction_task(conn, task.id)
    assert finished.status.value == "succeeded", finished.error
    assert [fact.id for fact in store.list_facts(conn, project.id)] == [previous.methods[0].id]
    assert {ref.id for ref in store.list_evidence(conn, project.id)} == {ref.id for ref in previous.evidence}
