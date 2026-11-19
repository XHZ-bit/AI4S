import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.knowledge import extraction, learning_routes, model, sources, store
from app.main import app
from app.tenancy import user_scope


@pytest.fixture
def route_case(monkeypatch):
    monkeypatch.setattr(model, 'structured', lambda *a, **kw: pytest.fail('Routes must not call models'))
    with TestClient(app) as client:
        body = {'title': '学习路线', 'domain': 'custom', 'research_question': '理解注意力分数',
                'constraints': {'version': 1, 'objective': '沿原文理解'}}
        pid = client.post('/api/projects', json=body).json()['id']
        other = client.post('/api/projects', json={**body, 'title': '其他空间'}).json()['id']
        src = sources.ingest(pid, b'# Authored teaching fixture\nA bounded graph for itinerary checks.', 'route.md')
        with store.connection(pid) as conn:
            labels = ['点积', '缩放', '归一化', '注意力目标', '无先修目标', '可选教学']
            store.put_parse(conn, src['asset_id'], {'blocks': [
                {'text': label + '的固定原文说明。', 'kind': 'text', 'page': index + 1}
                for index, label in enumerate(labels)]})
            nodes = []
            for index, block in enumerate(store.source_blocks(conn, src['asset_id'])):
                eid = store.add_evidence(conn, pid, src, block)
                nodes.append(store.put_record(conn, 'kw_nodes', extraction.node(src, str(index), 'concept',
                    labels[index], block['text'], [eid], metadata={'semantic': True,
                    **({'educational': True, 'demo': 'softmax'} if index == 5 else {})})))
            edges = []
            for before, after in [(0, 1), (0, 2), (1, 3), (2, 3)]:
                edges.append(store.put_record(conn, 'kw_edges', extraction.edge(src, nodes[before]['id'],
                    nodes[after]['id'], 'PREREQUISITE_OF', '先修', '固定材料中保存的前置关系',
                    nodes[before]['evidence_ids'] + nodes[after]['evidence_ids'])))
            store.put_record(conn, 'kw_edges', extraction.edge(src, nodes[5]['id'], nodes[3]['id'],
                'SUPPLEMENTS', '教学补充', '可选补充而非必修', [], origin='inference'))
        yield client, pid, other, src, nodes, edges


def endpoint(pid):
    return f'/api/projects/{pid}/knowledge/learning-route'


def preview(client, pid, target):
    response = client.post(endpoint(pid) + '/preview', json={'target_node_id': target['id']})
    assert response.status_code == 200, response.text
    return response.json()


def save(client, pid, target, revision=0):
    data = preview(client, pid, target)
    response = client.post(endpoint(pid), json={'target_node_id': target['id'], 'expected_revision': revision,
                                              'preview_fingerprint': data['preview_fingerprint']})
    assert response.status_code == 200, response.text
    return response.json()['route']


def patch(client, pid, route, **values):
    response = client.patch(endpoint(pid), json={'expected_revision': route['revision'], **values})
    assert response.status_code == 200, response.text
    return response.json()['route']


def test_branch_preview_deduplicates_real_prerequisites_without_writing(route_case):
    client, pid, _, _, nodes, edges = route_case
    data = preview(client, pid, nodes[3])
    ids = [step['node_id'] for step in data['steps']]
    assert len(ids) == len(set(ids)) == 4
    assert ids[0] == nodes[0]['id'] and ids[-1] == nodes[3]['id']
    assert nodes[5]['id'] not in ids
    assert {edge['id'] for edge in data['edges']} == {edge['id'] for edge in edges}
    assert data['research_question'] == '理解注意力分数'
    assert client.get(endpoint(pid)).json() == {'route': None}
    assert client.get(endpoint(pid) + '/history').json()['items'] == []


def test_isolated_target_and_uncited_legacy_node_stay_honest(route_case):
    client, pid, _, _, nodes, _ = route_case
    data = preview(client, pid, nodes[4])
    assert [step['node_id'] for step in data['steps']] == [nodes[4]['id']]
    assert data['edges'] == [] and any('没有已保存' in item for item in data['warnings'])
    with store.connection(pid) as conn:
        node = store.record(conn, 'kw_nodes', pid, nodes[4]['id'])
        node['evidence_ids'] = []
        store.put_record(conn, 'kw_nodes', node)
    data = preview(client, pid, nodes[4])
    assert data['steps'][0]['available'] and data['steps'][0]['warnings']
    assert any('尚无直接原文依据' in item for item in data['warnings'])


def test_done_skip_reorder_reload_and_undo_are_independent_of_mastery(route_case):
    client, pid, _, _, nodes, _ = route_case
    route = save(client, pid, nodes[3])
    route = patch(client, pid, route, step_node_id=nodes[0]['id'], state='done')
    route = patch(client, pid, route, step_node_id=nodes[1]['id'], state='skipped')
    ids = [step['node_id'] for step in route['steps']]
    ids[1], ids[2] = ids[2], ids[1]
    route = patch(client, pid, route, order=ids)
    loaded = client.get(endpoint(pid)).json()['route']
    assert [step['node_id'] for step in loaded['steps']] == ids
    assert next(step for step in loaded['steps'] if step['node_id'] == nodes[0]['id'])['state'] == 'done'
    assert loaded['next_node_id'] == nodes[2]['id']
    progress = client.get(f'/api/projects/{pid}/knowledge/nodes/{nodes[0]["id"]}/progress').json()
    assert progress['status'] == 'not_started'
    route = patch(client, pid, route, step_node_id=nodes[0]['id'], state='todo')
    assert route['next_node_id'] == nodes[0]['id']
    history = client.get(endpoint(pid) + '/history').json()['items']
    assert len(history) == 5 and history[-1]['revision'] == 1
    assert history[-1]['research_question'] == '理解注意力分数'
    assert history[-1]['steps'][0]['state'] == 'todo'


def test_save_rebuild_retains_decisions_order_and_inserts_real_new_prerequisite(route_case):
    client, pid, _, src, nodes, _ = route_case
    route = save(client, pid, nodes[3])
    route = patch(client, pid, route, step_node_id=nodes[0]['id'], state='done')
    route = patch(client, pid, route, step_node_id=nodes[1]['id'], state='skipped')
    order = [nodes[i]['id'] for i in [0, 2, 1, 3]]
    route = patch(client, pid, route, order=order)
    # A new prerequisite is real graph content. Existing independent decisions survive.
    with store.connection(pid) as conn:
        store.put_record(conn, 'kw_edges', extraction.edge(src, nodes[4]['id'], nodes[2]['id'],
            'PREREQUISITE_OF', '新增先修', '需要先理解这项', nodes[4]['evidence_ids']))
    route = save(client, pid, nodes[3], route['revision'])
    ids = [step['node_id'] for step in route['steps']]
    assert [nid for nid in ids if nid in order] == order
    assert ids.index(nodes[4]['id']) < ids.index(nodes[2]['id'])
    assert next(step for step in route['steps'] if step['node_id'] == nodes[0]['id'])['state'] == 'done'
    assert next(step for step in route['steps'] if step['node_id'] == nodes[1]['id'])['state'] == 'skipped'


def test_cycles_and_bounded_expansion_are_explicit(route_case, monkeypatch):
    client, pid, _, src, nodes, _ = route_case
    with store.connection(pid) as conn:
        store.put_record(conn, 'kw_edges', extraction.edge(src, nodes[3]['id'], nodes[0]['id'],
            'PREREQUISITE_OF', '循环待查', '固定错误关系供复核', nodes[3]['evidence_ids']))
    data = preview(client, pid, nodes[3])
    assert data['cycle_detected'] and any('循环' in item for item in data['warnings'])
    assert len({step['node_id'] for step in data['steps']}) == 4
    monkeypatch.setattr(learning_routes, 'MAX_STEPS', 2)
    data = preview(client, pid, nodes[3])
    assert data['truncated'] and len(data['steps']) == 2


def test_new_chain_is_inserted_before_previously_isolated_target(route_case):
    client, pid, _, src, nodes, _ = route_case
    route = save(client, pid, nodes[4])
    with store.connection(pid) as conn:
        store.put_record(conn, 'kw_edges', extraction.edge(src, nodes[3]['id'], nodes[4]['id'],
            'PREREQUISITE_OF', '补入先修链', '固定目标新增已保存先修', nodes[3]['evidence_ids']))
    updated = save(client, pid, nodes[4], route['revision'])
    ids = [step['node_id'] for step in updated['steps']]
    assert ids[0] == nodes[0]['id'] and ids[-1] == nodes[4]['id']
    assert ids.index(nodes[1]['id']) < ids.index(nodes[3]['id']) < ids.index(nodes[4]['id'])


def test_preview_fingerprint_rejects_same_id_evidence_changes(route_case):
    client, pid, _, _, nodes, _ = route_case
    planned = preview(client, pid, nodes[3])
    with store.connection(pid) as conn:
        evidence = store.evidence(conn, pid, nodes[0]['evidence_ids'])[0]
        evidence['quote'] = '固定原文说明'
        conn.execute('UPDATE kw_evidence SET data=? WHERE id=?', (store.encode(evidence), evidence['id']))
    response = client.post(endpoint(pid), json={'expected_revision': 0, 'target_node_id': nodes[3]['id'],
                                              'preview_fingerprint': planned['preview_fingerprint']})
    assert response.status_code == 409
    assert client.get(endpoint(pid)).json()['route'] is None


def test_stale_node_requires_explicit_current_context_recheck_and_keeps_history(route_case):
    client, pid, _, _, nodes, _ = route_case
    route = save(client, pid, nodes[3])
    route = patch(client, pid, route, step_node_id=nodes[0]['id'], state='done')
    previous = route['steps'][0]['current_context']
    with store.connection(pid) as conn:
        node = store.record(conn, 'kw_nodes', pid, nodes[0]['id'])
        node['summary'] = '修订后的点积解释'
        store.put_record(conn, 'kw_nodes', node)
    route = client.get(endpoint(pid)).json()['route']
    stale = next(step for step in route['steps'] if step['node_id'] == nodes[0]['id'])
    assert stale['stale'] and stale['snapshot']['node']['summary'] != stale['current_node']['summary']
    response = client.post(endpoint(pid) + '/recheck', json={'expected_revision': route['revision'],
        'step_node_id': nodes[0]['id'], 'expected_context': previous})
    assert response.status_code == 409
    response = client.post(endpoint(pid) + '/recheck', json={'expected_revision': route['revision'],
        'step_node_id': nodes[0]['id'], 'expected_context': stale['current_context']})
    assert response.status_code == 200, response.text
    updated = response.json()['route']
    assert updated['steps'][0]['state'] == 'done' and not updated['steps'][0]['stale']
    history = client.get(endpoint(pid) + '/history').json()['items']
    assert history[-1]['steps'][0]['snapshot']['node']['summary'] != '修订后的点积解释'


def test_removed_source_blocks_continue_and_cannot_be_rechecked(route_case):
    client, pid, _, src, nodes, _ = route_case
    route = save(client, pid, nodes[3])
    with store.connection(pid) as conn:
        store.update_source(conn, pid, src['id'], {'removed': True})
    route = client.get(endpoint(pid)).json()['route']
    assert route['next_node_id'] is None and route['graph']['nodes'] == []
    assert all(step['stale'] and not step['available'] for step in route['steps'])
    assert src['title'] in route['steps'][0]['stale_reasons'][0]
    response = client.post(endpoint(pid) + '/recheck', json={'expected_revision': route['revision'],
        'step_node_id': nodes[0]['id'], 'expected_context': route['steps'][0]['current_context']})
    assert response.status_code == 409
    assert route['steps'][0]['snapshot']['source']['removed'] is False


def test_relation_change_invalidates_dependent_step_and_exits_route_graph(route_case):
    client, pid, _, _, nodes, edges = route_case
    save(client, pid, nodes[3])
    with store.connection(pid) as conn:
        edge = store.record(conn, 'kw_edges', pid, edges[-1]['id'])
        edge['hidden'] = True
        store.put_record(conn, 'kw_edges', edge, preserve_user=False)
    route = client.get(endpoint(pid)).json()['route']
    target = next(step for step in route['steps'] if step['node_id'] == nodes[3]['id'])
    assert target['stale'] and any('前置关系' in reason for reason in target['stale_reasons'])
    assert edges[-1]['id'] not in {edge['id'] for edge in route['edges']}


def test_current_target_is_not_recommended_before_a_changed_upstream_step_is_reviewed(route_case):
    client, pid, _, _, nodes, _ = route_case
    route = save(client, pid, nodes[3])
    for node in nodes[:3]:
        route = patch(client, pid, route, step_node_id=node['id'], state='done')
    assert route['next_node_id'] == nodes[3]['id']
    with store.connection(pid) as conn:
        node = store.record(conn, 'kw_nodes', pid, nodes[0]['id'])
        node['summary'] = '点积说明发生变化'
        store.put_record(conn, 'kw_nodes', node)
    route = client.get(endpoint(pid)).json()['route']
    target = next(step for step in route['steps'] if step['node_id'] == nodes[3]['id'])
    assert not target['stale'] and target['blocked_by']
    assert route['next_node_id'] is None


def test_recheck_does_not_silently_omit_new_prerequisite_and_updates_goal_label(route_case):
    client, pid, _, src, nodes, _ = route_case
    route = save(client, pid, nodes[4])
    with store.connection(pid) as conn:
        store.put_record(conn, 'kw_edges', extraction.edge(src, nodes[0]['id'], nodes[4]['id'],
            'PREREQUISITE_OF', '新前置', '新增固定前置知识', nodes[0]['evidence_ids']))
        goal = store.record(conn, 'kw_nodes', pid, nodes[4]['id'])
        goal['label'] = '重新命名的目标'
        store.put_record(conn, 'kw_nodes', goal)
    route = client.get(endpoint(pid)).json()['route']
    target = route['steps'][0]
    response = client.post(endpoint(pid) + '/recheck', json={'expected_revision': route['revision'],
        'step_node_id': target['node_id'], 'expected_context': target['current_context']})
    assert response.status_code == 200, response.text
    route = response.json()['route']
    assert not route['steps'][0]['stale'] and route['needs_replan']
    assert route['target_label'] == '重新命名的目标'
    assert nodes[0]['id'] in route['steps'][0]['blocked_by']
    assert route['next_node_id'] is None
    assert any('尚未加入路线' in item for item in route['warnings'])
    rebuilt = save(client, pid, nodes[4], route['revision'])
    assert not rebuilt['needs_replan'] and rebuilt['next_node_id'] == nodes[0]['id']


def test_revision_conflicts_invalid_order_and_project_account_boundaries(route_case):
    client, pid, other, _, nodes, _ = route_case
    route = save(client, pid, nodes[3])
    response = client.patch(endpoint(pid), json={'expected_revision': 999, 'step_node_id': nodes[0]['id'], 'state': 'done'})
    assert response.status_code == 409
    response = client.patch(endpoint(pid), json={'expected_revision': route['revision'], 'order': [nodes[0]['id']]})
    assert response.status_code == 422
    assert client.get(endpoint(other)).json() == {'route': None}
    assert client.post(endpoint(other) + '/preview', json={'target_node_id': nodes[3]['id']}).status_code == 404
    assert client.get(endpoint('missing')).status_code == 404
    with user_scope({'id': 'b' * 32, 'username': 'other'}):
        with pytest.raises(HTTPException) as error:
            with store.connection(pid):
                pass
        assert error.value.status_code == 404


def test_source_version_and_question_changes_are_specific_and_preview_bound(route_case):
    client, pid, _, src, nodes, _ = route_case
    save(client, pid, nodes[3])
    with store.connection(pid) as conn:
        # Modify the stored project snapshot through its normal version table.
        row = conn.execute('SELECT version,payload_json FROM research_project_versions WHERE project_id=? '
                           'ORDER BY version DESC LIMIT 1', (pid,)).fetchone()
        payload = json.loads(row['payload_json'])
        payload['research_question'] = '比较不同归一化条件'
        conn.execute('UPDATE research_project_versions SET payload_json=? WHERE project_id=? AND version=?',
                     (store.encode(payload), pid, row['version']))
        store.update_source(conn, pid, src['id'], {'version': 'v2'})
    route = client.get(endpoint(pid)).json()['route']
    assert route['question_changed'] and any('研究问题已改变' in item for item in route['warnings'])
    assert route['research_question'] == '理解注意力分数'
    assert any('版本已有变化' in item for item in route['steps'][0]['stale_reasons'])
    assert route['next_node_id'] is None
