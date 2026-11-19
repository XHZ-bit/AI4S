import json
import sqlite3

import pytest
from fastapi import HTTPException

from app.knowledge import concepts, extraction, learning, store, unified
from app.tenancy import user_scope


@pytest.fixture
def materials():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    store.init(conn)

    def add(sid, label, summary, *, metadata=None, evidence=True):
        source = {'id': sid, 'project_id': 'p', 'asset_id': sid, 'version': 'v1', 'kind': 'paper',
                  'title': sid + '论文', 'filename': sid + '.pdf', 'removed': False}
        conn.execute('INSERT INTO kw_sources VALUES(?,?,?,?,?)', (sid, 'p', sid, 0, store.encode(source)))
        store.put_parse(conn, sid, {'blocks': [{'text': summary, 'page': 4, 'heading': 'Definition'}]})
        block = store.source_blocks(conn, sid)[0]
        eid = store.add_evidence(conn, 'p', source, block)
        node = store.put_record(conn, 'kw_nodes', extraction.node(
            source, label, 'concept', label, summary, [eid] if evidence else [],
            metadata={'semantic': True, **(metadata or {})}))
        return node

    left = add('english', 'Softmax', 'Normalize attention scores into probabilities.', metadata={'conditions': 'a vector of scores'})
    right = add('chinese', '归一化指数函数', '将一组分数转成总和为1的概率。', metadata={'conditions': '一组分数'})
    missing = add('missing', 'Softmax', '尚待原文确认。', evidence=False)
    teaching = add('teaching', 'Softmax', '自编教学知识。', metadata={'educational': True, 'demo': 'softmax'})
    conn.commit()
    yield conn, left, right, missing, teaching
    conn.close()


def inputs(conn, left, right, status='comparable'):
    return {'other_node_id': right['id'], 'status': status, 'explanation': '核对两侧定义和向量归一化条件。',
            'left_node_version': left['version'], 'right_node_version': right['version'],
            'left_source_version': 'v1', 'right_source_version': 'v1',
            'left_evidence_fingerprint': concepts._side(conn, 'p', left['id'])['evidence_fingerprint'],
            'right_evidence_fingerprint': concepts._side(conn, 'p', right['id'])['evidence_fingerprint']}


def test_whole_space_alias_candidates_keep_evidence_and_teaching_separate(materials):
    conn, left, right, _, teaching = materials
    data = concepts.collection(conn, 'p', left['id'])
    match = next(candidate for candidate in data['candidates'] if candidate['side']['node']['id'] == right['id'])
    assert match['side']['evidence'][0]['locator']['page'] == 4
    assert '双语' in match['reason']
    assert all(item['side']['node']['id'] != teaching['id'] for item in data['candidates'])
    assert data['node']['conditions'] == {'conditions': 'a vector of scores'}
    search = concepts.collection(conn, 'p', left['id'], q='归一化', source_id='chinese')
    assert [value['node']['id'] for value in search['choices']] == [right['id']]


def test_decision_links_are_user_judgments_and_regeneration_preserves_rejection(materials):
    conn, left, right, _, _ = materials
    with user_scope({'id': 'a' * 32, 'username': 'researcher'}):
        item = concepts.create(conn, 'p', left['id'], inputs(conn, left, right, 'conditions_differ'))
    conn.commit()
    assert item['reviewed_by'] == 'researcher'
    link = next(edge for edge in learning.current_neighbors(conn, 'p', left['id'])[1]
                if edge['metadata'].get('concept_correspondence_id'))
    assert link['origin'] == 'user' and link['metadata']['comparison_decision'] == 'conditions_differ'
    rejected = concepts.revise(conn, 'p', left['id'], item['id'], {'expected_revision': 1, 'status': 'rejected', 'explanation': '本次不采用'})
    conn.commit()
    assert rejected['revision'] == 2
    assert not learning.current_neighbors(conn, 'p', left['id'])[1]
    for _ in range(2):
        refreshed = concepts.collection(conn, 'p', left['id'])
        assert refreshed['items'][0]['status'] == 'rejected'
        assert all(value['side']['node']['id'] != right['id'] for value in refreshed['candidates'])


def test_node_or_same_id_evidence_change_hides_old_link_but_keeps_snapshot(materials):
    conn, left, right, _, _ = materials
    item = concepts.create(conn, 'p', left['id'], inputs(conn, left, right))
    conn.commit()
    old_quote = item['right']['evidence'][0]['quote']
    right['summary'] = 'Updated definition'
    store.put_record(conn, 'kw_nodes', right)
    conn.commit()
    assert not learning.current_neighbors(conn, 'p', left['id'])[1]
    graph = store.graph(conn, 'p', limit=100)
    assert not any(edge.get('metadata', {}).get('concept_correspondence_id') for edge in graph['edges'])
    view = concepts.collection(conn, 'p', left['id'])['items'][0]
    assert view['stale'] and view['right']['evidence'][0]['quote'] == old_quote
    assert view['current_right']['node']['summary'] == 'Updated definition'


def test_confirmation_requires_versions_two_sources_and_evidence(materials):
    conn, left, right, missing, teaching = materials
    for data in [inputs(conn, left, missing), inputs(conn, left, teaching), {**inputs(conn, left, right), 'right_node_version': 2}]:
        with pytest.raises(HTTPException) as error:
            concepts.create(conn, 'p', left['id'], data)
        assert error.value.status_code in {409, 422}
        conn.rollback()
    with pytest.raises(HTTPException) as error:
        concepts.collection(conn, 'other', left['id'])
    assert error.value.status_code == 404
    item = concepts.create(conn, 'p', left['id'], inputs(conn, left, missing, 'uncertain'))
    conn.commit()
    assert item['status'] == 'uncertain' and not learning.current_neighbors(conn, 'p', left['id'])[1]


def test_reverse_view_revision_conflicts_and_missing_source_history(materials):
    conn, left, right, _, _ = materials
    item = concepts.create(conn, 'p', left['id'], inputs(conn, left, right))
    conn.commit()
    reverse = concepts.collection(conn, 'p', right['id'])['items'][0]
    assert reverse['left']['node']['id'] == right['id']
    with pytest.raises(HTTPException):
        concepts.create(conn, 'p', right['id'], inputs(conn, right, left))
    conn.rollback()
    item = concepts.revise(conn, 'p', right['id'], item['id'], {**inputs(conn, right, left, 'conditions_differ'), 'expected_revision': 1})
    conn.commit()
    assert item['left']['node']['id'] == right['id']
    with pytest.raises(HTTPException) as error:
        concepts.revise(conn, 'p', left['id'], item['id'], {'expected_revision': 1, 'status': 'rejected'})
    assert error.value.status_code == 409
    conn.rollback()
    source = store.source(conn, 'p', 'chinese')
    source['version'] = 'v2'
    conn.execute('UPDATE kw_sources SET data=?,removed=1 WHERE id=?', (json.dumps(source), 'chinese'))
    conn.commit()
    view = concepts.collection(conn, 'p', left['id'])['items'][0]
    assert view['stale'] and view['right']['source_version'] == 'v1'
    item = concepts.revise(conn, 'p', left['id'], item['id'], {'expected_revision': 2, 'status': 'rejected', 'explanation': '旧判断不再采用'})
    assert item['status'] == 'rejected'


def test_same_evidence_identifier_cannot_keep_an_old_decision_live_in_global_graph(materials, monkeypatch):
    conn, left, right, _, _ = materials
    monkeypatch.setattr(unified, 'scopes', lambda _: [{'id': 'p', 'title': '论文', 'kind': 'project', 'project_id': 'p'}])
    concepts.create(conn, 'p', left['id'], inputs(conn, left, right))
    conn.commit()
    assert unified.graph(conn, project_id='p')['edges']
    eid = right['evidence_ids'][0]
    value = store.evidence(conn, 'p', [eid])[0]
    value['quote'] = 'a different quote'
    conn.execute('UPDATE kw_evidence SET data=? WHERE id=?', (store.encode(value), eid))
    conn.commit()
    assert not unified.graph(conn, project_id='p')['edges']
    view = concepts.collection(conn, 'p', left['id'])['items'][0]
    assert view['stale'] and view['right']['evidence'][0]['quote'] != 'a different quote'


def test_confirm_cannot_silently_replace_the_excerpt_seen_by_the_user(materials):
    conn, left, right, _, _ = materials
    requested = inputs(conn, left, right)
    eid = right['evidence_ids'][0]
    evidence = store.evidence(conn, 'p', [eid])[0]
    # Keep source/node versions and evidence ID fixed, but point to a different valid quote.
    evidence['quote'] = evidence['quote'][:5]
    conn.execute('UPDATE kw_evidence SET data=? WHERE id=?', (store.encode(evidence), eid))
    conn.commit()
    with pytest.raises(HTTPException) as error:
        concepts.create(conn, 'p', left['id'], requested)
    assert error.value.status_code == 409
    conn.rollback()
    item = concepts.create(conn, 'p', left['id'], inputs(conn, left, right))
    conn.commit()
    stale_request = {**inputs(conn, left, right), 'expected_revision': 1}
    evidence['quote'] = evidence['quote'][:4]
    conn.execute('UPDATE kw_evidence SET data=? WHERE id=?', (store.encode(evidence), eid))
    conn.commit()
    with pytest.raises(HTTPException) as error:
        concepts.revise(conn, 'p', left['id'], item['id'], stale_request)
    assert error.value.status_code == 409


def test_api_versions_status_and_project_boundary():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.knowledge import sources

    client = TestClient(app)
    response = client.post('/api/projects', json={'title': '双侧概念核对', 'domain': 'custom',
        'research_question': '归一化定义是否可对照？', 'constraints': {'version': 1, 'objective': '固定资料核对'}})
    assert response.status_code == 201
    pid = response.json()['id']
    nodes = []
    for index, label in enumerate(('Softmax', '归一化指数函数')):
        src = sources.ingest(pid, b'# Definition\nNormalize a vector of scores.\n', f'source-{index}.md', 'paper')
        # Use two distinct authored files so the normal source deduplication keeps two sources.
        if index == 1:
            src = sources.ingest(pid, b'# Definition\nNormalize a vector of real scores.\n', 'source-1.md', 'paper')
        with store.connection(pid) as conn:
            store.put_parse(conn, src['asset_id'], {'blocks': [{'text': label + ' vector definition', 'kind': 'text', 'page': 1}]})
            block = store.source_blocks(conn, src['asset_id'])[0]
            eid = store.add_evidence(conn, pid, src, block)
            nodes.append(store.put_record(conn, 'kw_nodes', extraction.node(src, label, 'concept', label,
                'A vector definition', [eid], metadata={'semantic': True})))
    endpoint = f'/api/projects/{pid}/knowledge/nodes/{nodes[0]["id"]}/concept-correspondences'
    data = client.get(endpoint).json()
    assert data['generation'] == 'local_rules' and data['candidates']
    left, right = data['node'], data['candidates'][0]['side']
    body = {'other_node_id': right['node']['id'], 'status': 'comparable', 'explanation': '逐侧核对定义',
            'left_node_version': left['node']['version'], 'right_node_version': right['node']['version'],
            'left_source_version': left['source_version'], 'right_source_version': right['source_version'],
            'left_evidence_fingerprint': left['evidence_fingerprint'], 'right_evidence_fingerprint': right['evidence_fingerprint']}
    assert client.post(endpoint, json={**body, 'status': 'invented'}).status_code == 422
    assert client.post(endpoint, json={**body, 'right_node_version': 999}).status_code == 409
    saved = client.post(endpoint, json=body)
    assert saved.status_code == 200, saved.text
    assert client.get(endpoint.replace(pid, 'another-project')).status_code == 404
    assert client.patch(endpoint + '/' + saved.json()['id'], json={'status': 'rejected', 'expected_revision': 99}).status_code == 409
