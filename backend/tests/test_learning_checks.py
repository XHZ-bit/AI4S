import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.knowledge import extraction, learning, model, sources, store
from app.knowledge.learning_checks import CHECKS


@pytest.fixture
def checks_fixture(monkeypatch):
    monkeypatch.setattr(model, 'structured', lambda *args, **kwargs: pytest.fail('Teaching checks must not call a model'))
    with TestClient(app) as client:
        payload = {'title': 'Attention learning', 'domain': 'custom', 'research_question': 'Understand attention',
                   'constraints': {'version': 1, 'objective': 'Understand scores'}}
        pid = client.post('/api/projects', json=payload).json()['id']
        other = client.post('/api/projects', json={**payload, 'title': 'Other space'}).json()['id']
        source = sources.ingest(pid, b'# Attention\nScaled dot-product attention divides the score by the square root of the key dimension.', 'attention.md')
        with store.connection(pid) as conn:
            store.put_parse(conn, source['asset_id'], {'blocks': [{'kind': 'text', 'text': 'Scaled dot-product attention divides the score by the square root of the key dimension.'}]})
            block = store.source_blocks(conn, source['asset_id'])[0]
            evidence = store.add_evidence(conn, pid, source, block)
            node = extraction.node(source, 'attention', 'formula', 'Scaled dot-product attention', '理解 attention softmax 缩放分数', [evidence],
                                   metadata={'semantic': True, 'latex': r'\operatorname{softmax}(QK^T/\sqrt{d_k})V'})
            node = store.put_record(conn, 'kw_nodes', node)
            learning.add_prerequisites(conn, pid, source['id'])
        yield client, pid, other, source, node


def answer(client, pid, node, value='probability'):
    root = f'/api/projects/{pid}/knowledge/nodes/{node["id"]}/checks'
    question = client.get(root)
    assert question.status_code == 200, question.text
    response = client.post(root + '/attention_score', json={
        'answer_id': value, 'expected_context': question.json()['context_fingerprint'], 'explanation': '我的预测与解释'})
    assert response.status_code == 201, response.text
    return root, response.json()


def test_optional_check_records_specific_feedback_without_certifying_progress(checks_fixture):
    client, pid, _, _, node = checks_fixture
    root = f'/api/projects/{pid}/knowledge/nodes/{node["id"]}/checks'
    before = client.get(root).json()
    assert before['history'] == []
    assert 'attention_score' in [item['id'] for item in before['questions']]
    root, result = answer(client, pid, node)
    assert result['correct'] is False
    assert result['answer_id'] == 'probability' and 'softmax' in result['feedback']
    assert result['explanation'] == '我的预测与解释'
    assert result['origin'] == 'authored_teaching_check'
    assert client.get(f'/api/projects/{pid}/knowledge/nodes/{node["id"]}/progress').json()['status'] == 'not_started'
    assert client.get(root).json()['history'][0]['answer_id'] == 'probability'
    recommendation = client.get(f'/api/projects/{pid}/knowledge/checks/recommendation').json()['recommendation']
    assert recommendation['attempt_id'] == result['id']
    with store.connection(pid) as conn:
        target = store.record(conn, 'kw_nodes', pid, recommendation['node_id'])
    assert target['metadata']['demo'] == 'softmax'


def test_corrected_answer_and_explicit_dismissal_change_next_step(checks_fixture):
    client, pid, _, _, node = checks_fixture
    root, result = answer(client, pid, node)
    endpoint = f'/api/projects/{pid}/knowledge/checks/recommendation'
    assert client.get(endpoint).json()['recommendation']
    assert client.post(root + '/' + result['id'] + '/dismiss').json()['dismissed']
    assert client.get(endpoint).json()['recommendation'] is None
    _, corrected = answer(client, pid, node, 'score')
    assert corrected['correct']
    assert client.get(endpoint).json()['recommendation'] is None
    assert len(client.get(root).json()['history']) == 2


def test_version_changes_preserve_old_answer_and_reject_stale_submission(checks_fixture):
    client, pid, _, source, node = checks_fixture
    root, result = answer(client, pid, node)
    with store.connection(pid) as conn:
        store.update_source(conn, pid, source['id'], {'version': 'updated-source'})
    history = client.get(root).json()['history']
    assert history[0]['stale'] and history[0]['source_version'] == source['version']
    assert client.get(f'/api/projects/{pid}/knowledge/checks/recommendation').json()['recommendation'] is None
    response = client.post(root + '/attention_score', json={'answer_id': 'score', 'expected_context': result['context_fingerprint']})
    assert response.status_code == 409


def test_checks_reject_foreign_nodes_and_unknown_choices(checks_fixture):
    client, pid, other, _, node = checks_fixture
    root = f'/api/projects/{pid}/knowledge/nodes/{node["id"]}/checks'
    fingerprint = client.get(root).json()['context_fingerprint']
    assert client.get(f'/api/projects/{other}/knowledge/nodes/{node["id"]}/checks').status_code == 404
    assert client.post(root + '/attention_score', json={'answer_id': 'invented', 'expected_context': fingerprint}).status_code == 422
    with store.connection(pid) as conn:
        count = conn.execute("SELECT COUNT(*) FROM kw_history WHERE project_id=? AND kind='learning_check'", (pid,)).fetchone()[0]
    assert count == 0


def test_node_change_and_removal_disable_current_recommendations(checks_fixture):
    client, pid, _, source, node = checks_fixture
    root, _ = answer(client, pid, node)
    with store.connection(pid) as conn:
        current = store.record(conn, 'kw_nodes', pid, node['id'])
        current['summary'] = 'New explanation of attention'
        store.put_record(conn, 'kw_nodes', current)
    assert client.get(root).json()['history'][0]['stale']
    assert client.get(f'/api/projects/{pid}/knowledge/checks/recommendation').json()['recommendation'] is None
    with store.connection(pid) as conn:
        store.update_source(conn, pid, source['id'], {'removed': True})
    assert client.get(root).json()['available'] is False


def test_unlocatable_evidence_blocks_a_fresh_answer_and_recommendation(checks_fixture):
    client, pid, _, source, node = checks_fixture
    root, _ = answer(client, pid, node)
    with store.connection(pid) as conn:
        block = store.source_blocks(conn, source['asset_id'])[0]
        block['text'] = 'The original passage is no longer present.'
        conn.execute('UPDATE kw_blocks SET data=? WHERE id=?', (store.encode(block), block['id']))
    latest = client.get(root).json()
    assert not latest['available'] and latest['history'][0]['stale']
    result = client.post(root + '/attention_score', json={'answer_id': 'score', 'expected_context': latest['context_fingerprint']})
    assert result.status_code == 409
    assert client.get(f'/api/projects/{pid}/knowledge/checks/recommendation').json()['recommendation'] is None


def test_updated_teaching_question_requires_a_new_context(checks_fixture, monkeypatch):
    client, pid, _, _, node = checks_fixture
    root, attempt = answer(client, pid, node)
    monkeypatch.setitem(CHECKS, 'attention_score', {**CHECKS['attention_score'], 'version': 2, 'question': '更新后的教学题'})
    assert client.get(root).json()['history'][0]['stale']
    result = client.post(root + '/attention_score', json={'answer_id': 'score', 'expected_context': attempt['context_fingerprint']})
    assert result.status_code == 409


def test_explicit_feedback_can_address_an_attempt_beyond_the_history_window(checks_fixture):
    client, pid, _, _, node = checks_fixture
    root, first = answer(client, pid, node)
    with store.connection(pid) as conn:
        for index in range(21):
            entry = {**first, 'id': 'later-' + str(index)}
            conn.execute('INSERT INTO kw_history(project_id,record_id,kind,data,created_at) VALUES(?,?,?,?,?)',
                         (pid, node['id'], 'learning_check', json.dumps(entry), entry['created_at']))
    assert first['id'] not in {item['id'] for item in client.get(root).json()['history']}
    assert client.post(root + '/' + first['id'] + '/dismiss').status_code == 200
