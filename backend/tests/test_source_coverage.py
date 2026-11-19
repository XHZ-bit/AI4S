"""Coverage describes evidence and supplements one category without replacing decisions."""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.knowledge import coverage, extraction, model, store
from tests.test_knowledge_workspace import project, upload

pytest_plugins = ['tests.test_knowledge_workspace']


def prepare(client):
    pid = project(client)
    source = upload(client, pid, text=b'# Research\n\n## Method\nWe propose a scaled dot product.\n\n## Results\nThe delayed test improved recall.\n')
    return pid, source, f'/api/projects/{pid}/sources/{source["id"]}/coverage'


def add_node(pid, sid, kind='method', label='Scaled score'):
    with store.connection(pid) as conn:
        source = store.source(conn, pid, sid)
        block = next(b for b in store.source_blocks(conn, source['asset_id']) if 'scaled' in b['text'])
        eid = store.add_evidence(conn, pid, source, block)
        item = extraction.node(source, kind, kind, label, 'A source-grounded definition', [eid], metadata={'semantic': True})
        store.put_record(conn, 'kw_nodes', item)
    return item


def supplement_result(payload, category='finding', quote='The delayed test improved recall.'):
    block = next(b for b in payload['blocks'] if quote in b['text'])
    return {'nodes': [{'key': 'result', 'kind': category, 'label': 'Delayed recall',
                       'summary': '教学检查中的原文结果', 'evidence': [{'block_id': block['block_id'], 'quote': quote}]}]}


def expected(value, category):
    return {'category': category, 'expected_source_version': value['source_version'], 'expected_revision': value['revision']}


def test_get_only_reports_current_grounded_semantics_and_never_calls_model(synchronous, monkeypatch):
    with TestClient(app) as client:
        pid, source, root = prepare(client)
        monkeypatch.setattr(model, 'structured', lambda *a, **kw: pytest.fail('GET called a model'))
        value = client.get(root).json()
        assert all(item['state'] == 'not_extracted' for item in value['items'])
        node = add_node(pid, source['id'])
        value = client.get(root).json()
        method = next(i for i in value['items'] if i['category'] == 'method')
        assert method['state'] == 'covered' and method['node_count'] == 1
        assert method['evidence'][0]['source_version'] == source['version']
        assert next(i for i in value['items'] if i['category'] == 'finding')['state'] == 'missing'
        with store.connection(pid) as conn:
            store.edit_record(conn, 'kw_nodes', pid, node['id'], 1, {'hidden': True})
        assert client.get(root).json()['semantic_node_count'] == 0


def test_user_missing_and_inapplicable_decisions_are_versioned_and_not_inferred(synchronous):
    with TestClient(app) as client:
        pid, source, root = prepare(client)
        value = client.get(root).json()
        body = {**expected(value, 'limitation'), 'status': 'not_reported', 'reason': '我检查了讨论部分，未找到这项内容。'}
        saved = client.patch(root, json=body)
        assert saved.status_code == 200, saved.text
        item = next(i for i in saved.json()['items'] if i['category'] == 'limitation')
        assert item['state'] == 'not_reported' and item['decision']['origin'] == 'user'
        assert client.patch(root, json=body).status_code == 409
        empty = {**expected(saved.json(), 'experiment'), 'status': 'not_applicable', 'reason': ' '}
        assert client.patch(root, json=empty).status_code == 422
        with store.connection(pid) as conn:
            store.update_source(conn, pid, source['id'], {'version': 'sha256:changed'})
        changed = client.get(root).json()
        item = next(i for i in changed['items'] if i['category'] == 'limitation')
        assert item['state'] == 'not_extracted' and item['decision_stale']
        assert item['decision']['reason'] == body['reason']
        reset = client.patch(root, json={**expected(changed, 'limitation'), 'status': 'reset'})
        assert reset.status_code == 200
        assert next(i for i in reset.json()['items'] if i['category'] == 'limitation')['decision'] is None


def test_explicit_supplement_is_bounded_grounded_and_keeps_other_knowledge(synchronous, monkeypatch):
    calls = []
    with TestClient(app) as client:
        pid, source, root = prepare(client)
        before = add_node(pid, source['id'])
        value = client.get(root).json()
        monkeypatch.setattr(model, 'available', lambda: True)

        def generate(system, payload, budget, purpose, **kwargs):
            calls.append(payload)
            assert budget.limit == 1 and purpose == 'source_coverage_supplement'
            assert payload['category'] == 'finding'
            assert len(payload['blocks']) <= 8 and sum(len(b['text']) for b in payload['blocks']) <= 10000
            return supplement_result(payload)

        monkeypatch.setattr(model, 'structured', generate)
        response = client.post(root + '/supplement', json=expected(value, 'finding'))
        assert response.status_code == 200, response.text
        result = response.json()
        assert len(calls) == 1 and result['supplement']['added_or_refreshed'] == 1
        assert next(i for i in result['items'] if i['category'] == 'finding')['state'] == 'covered'
        with store.connection(pid) as conn:
            assert store.record(conn, 'kw_nodes', pid, before['id'])['summary'] == before['summary']


def test_invalid_quotes_and_foreign_types_never_fill_a_gap(synchronous, monkeypatch):
    with TestClient(app) as client:
        _, _, root = prepare(client)
        value = client.get(root).json()
        monkeypatch.setattr(model, 'available', lambda: True)
        monkeypatch.setattr(model, 'structured', lambda *a, **kw: {'nodes': [
            {'key': 'bad', 'kind': 'finding', 'label': 'Made up', 'summary': 'invented',
             'evidence': [{'block_id': 'foreign-block', 'quote': 'not in source'}]},
            {'key': 'wrong-kind', 'kind': 'method', 'label': 'Method', 'evidence': []},
        ]})
        result = client.post(root + '/supplement', json=expected(value, 'finding'))
        assert result.status_code == 200, result.text
        assert result.json()['supplement']['added_or_refreshed'] == 0
        assert next(i for i in result.json()['items'] if i['category'] == 'finding')['state'] == 'not_extracted'


def test_model_failure_and_concurrent_source_change_preserve_existing_records(synchronous, monkeypatch):
    with TestClient(app) as client:
        pid, source, root = prepare(client)
        node = add_node(pid, source['id'])
        value = client.get(root).json()
        assert client.post(root + '/supplement', json=expected(value, 'finding')).status_code == 503
        monkeypatch.setattr(model, 'available', lambda: True)

        def generate(system, payload, budget, purpose, **kwargs):
            with store.connection(pid) as conn:
                store.update_source(conn, pid, source['id'], {'version': 'sha256:changed-during-call'})
            return supplement_result(payload)

        monkeypatch.setattr(model, 'structured', generate)
        response = client.post(root + '/supplement', json=expected(value, 'finding'))
        assert response.status_code == 409
        with store.connection(pid) as conn:
            assert store.record(conn, 'kw_nodes', pid, node['id'])['summary'] == node['summary']
            assert conn.execute("SELECT COUNT(*) FROM kw_nodes WHERE project_id=? AND json_extract(data, '$.kind')='finding'", (pid,)).fetchone()[0] == 0


def test_concurrent_manual_judgment_wins_and_cross_project_source_is_rejected(synchronous, monkeypatch):
    with TestClient(app) as client:
        pid, source, root = prepare(client)
        other = project(client)
        assert client.get(f'/api/projects/{other}/sources/{source["id"]}/coverage').status_code == 404
        value = client.get(root).json()
        monkeypatch.setattr(model, 'available', lambda: True)

        def generate(system, payload, budget, purpose, **kwargs):
            coverage.review(pid, source['id'], 'finding', 'not_applicable', '先保留我核对后的判断', source['version'], 0)
            return supplement_result(payload)

        monkeypatch.setattr(model, 'structured', generate)
        response = client.post(root + '/supplement', json=expected(value, 'finding'))
        assert response.status_code == 409
        result = client.get(root).json()
        finding = next(i for i in result['items'] if i['category'] == 'finding')
        assert finding['state'] == 'not_applicable'
        assert finding['decision']['reason'] == '先保留我核对后的判断'


def test_supplement_reuses_extraction_preservation_of_user_edits(synchronous, monkeypatch):
    with TestClient(app) as client:
        pid, source, root = prepare(client)
        with store.connection(pid) as conn:
            src = store.source(conn, pid, source['id'], blocks=True)
            block = next(b for b in src['blocks'] if 'The delayed' in b['text'])
            response = {'nodes': [{'key': 'result', 'kind': 'finding', 'label': 'Delayed recall',
                                  'summary': '初始摘要', 'evidence': [{'block_id': block['id'], 'quote': 'The delayed test improved recall.'}]}]}
            extraction.save_extraction(conn, src, response, src['blocks'])
            node = json.loads(conn.execute("SELECT data FROM kw_nodes WHERE project_id=? AND json_extract(data, '$.kind')='finding'", (pid,)).fetchone()[0])
        with store.connection(pid) as conn:
            store.edit_record(conn, 'kw_nodes', pid, node['id'], 1, {'summary': '我的人工修订'})
        value = client.get(root).json()
        monkeypatch.setattr(model, 'available', lambda: True)
        monkeypatch.setattr(model, 'structured', lambda system, payload, *a, **kw: supplement_result(payload))
        assert client.post(root + '/supplement', json=expected(value, 'finding')).status_code == 200
        with store.connection(pid) as conn:
            assert store.record(conn, 'kw_nodes', pid, node['id'])['summary'] == '我的人工修订'


def test_full_analysis_starting_during_supplement_cannot_overwrite_new_analysis(synchronous, monkeypatch):
    with TestClient(app) as client:
        pid, source, root = prepare(client)
        value = client.get(root).json()
        monkeypatch.setattr(model, 'available', lambda: True)

        def generate(system, payload, budget, purpose, **kwargs):
            with store.connection(pid) as conn:
                store.create_run(conn, pid, source['id'])
            return supplement_result(payload)

        monkeypatch.setattr(model, 'structured', generate)
        response = client.post(root + '/supplement', json=expected(value, 'finding'))
        assert response.status_code == 409
        current = client.get(root).json()
        assert current['analysis_running']
        assert next(i for i in current['items'] if i['category'] == 'finding')['node_count'] == 0
        assert client.post(root + '/supplement', json=expected(current, 'finding')).status_code == 409
