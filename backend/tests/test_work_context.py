"""Work continuity uses isolated source versions; no external model calls."""

import json
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from app.db.sqlite import connect, upsert_paper
from app.db.workspace import save_document
from app.main import app
from app.models.paper import PaperDoc, ParsedPaper


@pytest.fixture
def workspace(monkeypatch):
    calls = []

    def plan(question, source, profile, features, history):
        calls.append({'source': source, 'history': history, 'features': features})
        return {'title': 'Understanding a passage', 'goal': 'Explain one question',
                'steps': [{'question': 'Why?', 'explanation': 'An explanation', 'check': ''}],
                'quiz': [], 'terms': [], 'prerequisites': [], 'exercise': None}, 'test-fixture'

    monkeypatch.setattr('app.api.tutoring.make_plan', plan)
    with TestClient(app) as client:
        project = client.post('/api/projects', json={
            'title': 'A research space', 'domain': 'custom', 'stage': 'exploring', 'research_question': '',
            'constraints': {'version': 1, 'objective': ''},
        })
        assert project.status_code == 201, project.text
        pid = project.json()['id']
        documents = []
        with closing(connect()) as db:
            for uid in ['paper-one', 'paper-two']:
                upsert_paper(db, PaperDoc(uid=uid, title=uid, year=2025).model_dump())
                did = save_document(db, uid, ParsedPaper(uid=uid, title=uid, abstract='', sections=[
                    {'heading': 'Method', 'text': 'We model condi-\ntional distributions.\nThe loss measures error.', 'page': 2},
                    {'heading': 'Later', 'text': 'A second passage.', 'page': 3},
                ]))
                row = db.execute('SELECT content_hash FROM documents WHERE id=?', (did,)).fetchone()
                documents.append({'document_id': did, 'document_version': 'sha256:' + row[0]})
                db.execute('INSERT INTO paper_parse_quality VALUES(?,?,?)',
                           (did, uid, json.dumps({'page_count': 3})))
            db.commit()
        assert client.post(f'/api/workbench/projects/{pid}/papers', json={'paper_uid': 'paper-one'}).status_code == 200
        yield client, pid, documents, calls


def selection(doc, quote='We model conditional distributions.'):
    return {**doc, 'page': 2, 'quote': quote}


def test_selection_matches_layout_normalization_and_keeps_snapshot(workspace):
    client, pid, documents, calls = workspace
    response = client.post('/api/tutor/sessions', json={
        'project_id': pid, 'paper_uid': 'paper-one', 'question': 'Explain this sentence',
        'source_context': selection(documents[0]), 'phase': 'explain',
    })
    assert response.status_code == 201, response.text
    data = response.json()
    assert data['source']['selection_status'] == 'matched_passage'
    assert data['source']['passage_id'].startswith(documents[0]['document_id'])
    assert data['source']['passage']['page'] == 2
    assert data['source']['selection']['quote'] == 'We model conditional distributions.'
    assert calls[0]['features']['coding'] is False
    assert calls[0]['features']['quizzes'] is False
    second = client.post('/api/tutor/sessions', json={
        'project_id': pid, 'paper_uid': 'paper-one', 'session_id': data['id'],
        'question': 'Give me another example',
    })
    assert second.status_code == 201, second.text
    assert second.json()['source'] == data['source']
    assert len(calls[-1]['history']) == 1
    assert client.get('/api/tutor/sessions/' + second.json()['id']).json()['source'] == data['source']


def test_unmatched_selection_is_user_text_not_a_paper_quote(workspace):
    client, pid, documents, calls = workspace
    response = client.post('/api/tutor/sessions', json={
        'project_id': pid, 'paper_uid': 'paper-one', 'question': 'Explain this text',
        'source_context': selection(documents[0], 'A user supplied sentence not found in the paper.'),
    })
    assert response.status_code == 201, response.text
    source = response.json()['source']
    assert source['selection_status'] == 'user_selection'
    assert 'passage_id' not in source and 'passage' not in source
    assert calls[0]['source']['selection_status'] == 'user_selection'


@pytest.mark.parametrize('change,status', [
    ({'document_version': 'sha256:outdated'}, 409),
    ({'page': 4}, 422),
    ({'page': 0}, 422),
    ({'quote': ' '}, 422),
    ({'quote': 'x' * 8001}, 422),
])
def test_invalid_selection_does_not_call_model(workspace, change, status):
    client, pid, documents, calls = workspace
    response = client.post('/api/tutor/sessions', json={
        'project_id': pid, 'paper_uid': 'paper-one', 'question': 'Explain this text',
        'source_context': {**selection(documents[0]), **change},
    })
    assert response.status_code == status, response.text
    assert not calls


def test_cross_document_and_cross_account_selection_rejected(workspace):
    client, pid, documents, calls = workspace
    body = {'paper_uid': 'paper-one', 'question': 'Explain this text',
            'source_context': selection(documents[1])}
    assert client.post('/api/tutor/sessions', json=body).status_code == 404
    with TestClient(app) as other:
        signed = other.post('/api/auth/register', json={'username': 'context-reader', 'password': 'test-password-123!'})
        other.headers['X-Atlas-CSRF'] = signed.json()['csrf_token']
        assert other.post('/api/tutor/sessions', json={**body, 'source_context': selection(documents[0])}).status_code == 404
    assert not calls


def test_legacy_tutoring_request_still_works(workspace):
    client, _, _, calls = workspace
    response = client.post('/api/tutor/sessions', json={'question': 'What is expectation?'})
    assert response.status_code == 201, response.text
    assert response.json()['source'] is None
    assert len(calls) == 1


def test_tutor_timings_are_measured_and_saved_without_changing_legacy_plans(workspace):
    client, _, _, _ = workspace
    response = client.post('/api/tutor/sessions', json={'question': 'What is a conditional distribution?'})
    assert response.status_code == 201, response.text
    data = response.json()
    assert data['timings']['total_seconds'] >= data['timings']['model_seconds'] >= 0
    assert '_timings' not in data['plan']
    saved = client.get('/api/tutor/sessions/' + data['id']).json()
    assert saved['timings']['model_seconds'] == data['timings']['model_seconds']
    assert 'total_seconds' not in saved['timings'] and '_timings' not in saved['plan']
    with closing(connect()) as db:
        plan = json.loads(db.execute('SELECT plan_json FROM tutor_sessions WHERE id=?', (data['id'],)).fetchone()[0])
        plan.pop('_timings')
        db.execute('UPDATE tutor_sessions SET plan_json=? WHERE id=?', (json.dumps(plan), data['id']))
        db.commit()
    assert 'timings' not in client.get('/api/tutor/sessions/' + data['id']).json()


def test_scene_roundtrip_old_records_and_conflict(workspace):
    client, pid, documents, _ = workspace
    path = f'/api/workbench/projects/{pid}/scene'
    legacy = {'version': 0, 'view': 'reading', 'paper': 'paper-one', 'page': 2}
    assert client.post(path, json=legacy).status_code == 200
    body = {**legacy, 'version': 1, 'panel': 'tutor', 'ref': 'passage:selection',
            'focus': 'paragraph-2', 'session': 'session-id', 'lesson': 'probability',
            'step': 0, 'activity': 'reflect', 'unit': 'dp-1', 'returnTo': '/research/' + pid + '?tab=reading&paper=paper-one&page=2',
            **documents[0], 'selection': selection(documents[0])}
    saved = client.post(path, json=body)
    assert saved.status_code == 200, saved.text
    assert client.get(path).json() == saved.json()
    assert saved.json()['data']['step'] == 0
    assert saved.json()['data']['activity'] == 'reflect' and saved.json()['data']['unit'] == 'dp-1'
    assert saved.json()['data']['selection']['quote'] == selection(documents[0])['quote']
    assert client.post(path, json=body).status_code == 409
    assert client.get(path).json()['data']['paper'] == 'paper-one'


@pytest.mark.parametrize('target', ['https://example.com', '//example.com', '/%2fexample.com', '/\\example.com', '/api/auth/logout'])
def test_scene_rejects_unsafe_return_path(workspace, target):
    client, pid, _, _ = workspace
    response = client.post(f'/api/workbench/projects/{pid}/scene', json={'version': 0, 'returnTo': target})
    assert response.status_code == 422


def test_scene_checks_linked_paper_and_document(workspace):
    client, pid, documents, _ = workspace
    path = f'/api/workbench/projects/{pid}/scene'
    body = {'version': 0, 'view': 'reading', 'paper': 'paper-one', 'selection': selection(documents[1])}
    assert client.post(path, json=body).status_code == 404
    assert client.post(path, json={**body, 'paper': 'paper-two'}).status_code == 422
    assert client.post(path, json={'version': 0, 'returnTo': '/learn?question=hello%20world'}).status_code == 200


def test_note_preserves_source_when_older_editor_only_updates_body(workspace):
    client, pid, documents, _ = workspace
    with closing(connect()) as db:
        passage_id = db.execute('SELECT id FROM passages WHERE document_id=? AND page=2', (documents[0]['document_id'],)).fetchone()[0]
    body = {'id': 'selected-note', 'project_id': pid, 'paper_uid': 'paper-one',
            'title': 'My understanding', 'body': 'The distribution has several modes.',
            **selection(documents[0]), 'passage_id': passage_id}
    first = client.post('/api/workbench/records', json=body)
    assert first.status_code == 200, first.text
    source = json.loads(first.json()['source_json'])
    assert source['document_version'] == documents[0]['document_version']
    second = client.post('/api/workbench/records', json={
        'id': body['id'], 'version': 1, 'title': 'Edited understanding', 'body': 'Revised.',
    })
    assert second.status_code == 200, second.text
    assert second.json()['project_id'] == pid and second.json()['paper_uid'] == 'paper-one'
    assert json.loads(second.json()['source_json']) == source
    assert client.post('/api/workbench/records', json=body).status_code == 409


def test_note_cannot_attach_foreign_or_mismatched_document(workspace):
    client, pid, documents, _ = workspace
    body = {'title': 'Source note', 'paper_uid': 'paper-one', 'project_id': pid,
            **selection(documents[1])}
    assert client.post('/api/workbench/records', json=body).status_code == 404
    assert client.post('/api/workbench/records', json={**body, **selection(documents[0]), 'document_version': 'old'}).status_code == 409
    assert client.post('/api/workbench/records', json={**body, **selection(documents[0]), 'page': 99}).status_code == 422
