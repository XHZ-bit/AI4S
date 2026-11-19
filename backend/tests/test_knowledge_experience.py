"""Graph learning must stay scoped, source-backed, bounded and user-controlled."""

import json

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.main import app
from app.knowledge import experience, extraction, model, sources, store


@pytest.fixture
def graph_fixture():
    with TestClient(app) as client:
        def project(title):
            response = client.post('/api/projects', json={'title': title, 'domain': 'custom', 'research_question': 'Understand gradients',
                                                        'constraints': {'version': 1, 'objective': 'Read evidence'}})
            assert response.status_code == 201, response.text
            return response.json()['id']
        pid, other = project('Graph learning'), project('Independent space')
        src = sources.ingest(pid, b'# Teaching\nThe chain rule links a composition of differentiable functions.', 'teaching.md')
        with store.connection(pid) as conn:
            store.put_parse(conn, src['asset_id'], {'blocks': [{'kind': 'text', 'text': 'The chain rule links a composition of differentiable functions.', 'page': None}]})
            block = store.source_blocks(conn, src['asset_id'])[0]
            evidence = store.add_evidence(conn, pid, src, block)
            nodes = [store.put_record(conn, 'kw_nodes', extraction.node(src, name, 'concept', name, 'A source-backed teaching concept', [evidence])) for name in ['Chain rule', 'Derivative', 'Function']]
            edges = [store.put_record(conn, 'kw_edges', extraction.edge(src, nodes[i + 1]['id'], nodes[i]['id'], 'PREREQUISITE_OF', 'helps understand', 'A teaching dependency', [evidence], origin='inference')) for i in range(2)]
        yield client, pid, other, src, nodes, edges


def test_bounded_paths_keep_direction_and_isolate_projects(graph_fixture):
    client, pid, other, _, nodes, edges = graph_fixture
    base = f'/api/projects/{pid}/knowledge/paths'
    response = client.get(base, params={'source': nodes[0]['id'], 'kind': 'prerequisites'})
    assert response.status_code == 200
    result = response.json()
    assert result['paths'][0]['node_ids'] == [n['id'] for n in reversed(nodes)]
    assert {e['id'] for e in result['edges']} == {e['id'] for e in edges}
    assert all(e['origin'] == 'inference' for e in result['edges'])
    one = client.get(base, params={'source': nodes[0]['id'], 'kind': 'prerequisites', 'max_depth': 1}).json()
    assert len(one['paths'][0]['node_ids']) == 2 and one['truncated']
    assert client.get(f'/api/projects/{other}/knowledge/paths', params={'source': nodes[0]['id']}).status_code == 404
    assert client.get(base, params={'source': nodes[0]['id'], 'max_depth': 99}).status_code == 422


@pytest.mark.parametrize('with_cycle', [False, True])
def test_prerequisite_paths_keep_converging_branches_without_repeating_cycles(graph_fixture, with_cycle):
    client, pid, _, src, nodes, _ = graph_fixture
    target, intermediate, foundation = [node['id'] for node in nodes]
    with store.connection(pid) as conn:
        store.put_record(conn, 'kw_edges', extraction.edge(src, foundation, target, 'PREREQUISITE_OF', 'direct prerequisite', 'A second saved learning route', []))
        if with_cycle:
            cyclic = store.put_record(conn, 'kw_nodes', extraction.node(src, 'cyclic', 'concept', 'Cyclic branch', 'A cyclic dependency branch', []))
            for source, destination in [(target, cyclic['id']), (cyclic['id'], target)]:
                store.put_record(conn, 'kw_edges', extraction.edge(src, source, destination, 'PREREQUISITE_OF', 'cycle', 'Synthetic test cycle', []))
    base = f'/api/projects/{pid}/knowledge/paths'
    response = client.get(base, params={'source': target, 'kind': 'prerequisites'})
    assert response.status_code == 200
    result = response.json()
    assert {tuple(path['node_ids']) for path in result['paths']} == {
        (foundation, target), (foundation, intermediate, target),
    }
    assert result['cycle_detected'] is with_cycle
    assert not result['truncated']
    assert all(len(path['node_ids']) == len(set(path['node_ids'])) for path in result['paths'])
    assert intermediate in {node['id'] for node in result['nodes']}
    connection = client.get(base, params={'source': target, 'target': foundation}).json()
    assert [path['node_ids'] for path in connection['paths']] == [[target, foundation]]


def test_cycles_and_withdrawn_nodes_do_not_create_false_paths(graph_fixture):
    client, pid, _, src, nodes, _ = graph_fixture
    with store.connection(pid) as conn:
        store.put_record(conn, 'kw_edges', extraction.edge(src, nodes[0]['id'], nodes[2]['id'], 'PREREQUISITE_OF', 'cycle', 'Synthetic test cycle', []))
    base = f'/api/projects/{pid}/knowledge/paths'
    response = client.get(base, params={'source': nodes[0]['id'], 'kind': 'prerequisites'}).json()
    assert response['cycle_detected'] and len(response['nodes']) == 3
    with store.connection(pid) as conn:
        value = store.record(conn, 'kw_nodes', pid, nodes[1]['id'])
        value['quality_status'] = 'withdrawn'
        store.put_record(conn, 'kw_nodes', value, preserve_user=False)
    response = client.get(base, params={'source': nodes[0]['id'], 'target': nodes[2]['id']}).json()
    assert all(n['id'] != nodes[1]['id'] for n in response['nodes'])


def test_path_omits_cross_source_relationship_when_its_source_is_removed(graph_fixture):
    client, pid, _, _, nodes, _ = graph_fixture
    relation_source = sources.ingest(pid, b'# Relation\nA separate source describes this relation.', 'relation.md')
    with store.connection(pid) as conn:
        edge = extraction.edge(relation_source, nodes[2]['id'], nodes[0]['id'], 'PREREQUISITE_OF',
                               'cross source', 'Relation from another source', [])
        store.put_record(conn, 'kw_edges', edge)
    url = f'/api/projects/{pid}/knowledge/paths'
    before = client.get(url, params={'source': nodes[0]['id'], 'kind': 'prerequisites'}).json()
    assert edge['id'] in {item['id'] for item in before['edges']}
    with store.connection(pid) as conn:
        conn.execute('UPDATE kw_sources SET removed=1 WHERE id=? AND project_id=?', (relation_source['id'], pid))
    after = client.get(url, params={'source': nodes[0]['id'], 'kind': 'prerequisites'}).json()
    assert edge['id'] not in {item['id'] for item in after['edges']}
    assert edge['id'] not in {item for path in after['paths'] for item in path['edge_ids']}


@pytest.mark.parametrize('change', ['removed', 'updated'])
def test_path_omits_relation_when_its_cross_source_evidence_is_unavailable(graph_fixture, change):
    client, pid, _, owner, nodes, _ = graph_fixture
    other = sources.ingest(pid, b'# Evidence\nIndependent relation evidence.', 'evidence.md')
    with store.connection(pid) as conn:
        store.put_parse(conn, other['asset_id'], {'blocks': [{'kind': 'text', 'text': 'Independent relation evidence.', 'page': None}]})
        evidence = store.add_evidence(conn, pid, other, store.source_blocks(conn, other['asset_id'])[0])
        edge = extraction.edge(owner, nodes[2]['id'], nodes[0]['id'], 'PREREQUISITE_OF',
                               'supported by another source', 'Cross-source prerequisite', [evidence], origin='inference')
        store.put_record(conn, 'kw_edges', edge)
    url = f'/api/projects/{pid}/knowledge/paths'
    before = client.get(url, params={'source': nodes[0]['id'], 'kind': 'prerequisites'}).json()
    assert edge['id'] in {item['id'] for item in before['edges']}
    with store.connection(pid) as conn:
        if change == 'removed':
            conn.execute('UPDATE kw_sources SET removed=1 WHERE id=? AND project_id=?', (other['id'], pid))
        else:
            row = conn.execute('SELECT data FROM kw_sources WHERE id=? AND project_id=?', (other['id'], pid)).fetchone()
            updated = json.loads(row[0])
            updated['version'] = 'changed-source-version'
            conn.execute('UPDATE kw_sources SET data=? WHERE id=? AND project_id=?', (store.encode(updated), other['id'], pid))
    after = client.get(url, params={'source': nodes[0]['id'], 'kind': 'prerequisites'}).json()
    assert edge['id'] not in {item['id'] for item in after['edges']}


def test_progress_is_versioned_manual_and_not_shared(graph_fixture):
    client, pid, other, _, nodes, _ = graph_fixture
    nid = nodes[0]['id']
    url = f'/api/projects/{pid}/knowledge/nodes/{nid}/progress'
    assert client.get(url).json()['status'] == 'not_started'
    saved = client.patch(url, json={'status': 'understood', 'expected_version': 0})
    assert saved.status_code == 200, saved.text
    assert saved.json()['origin'] == 'user'
    assert client.patch(url, json={'status': 'review', 'expected_version': 0}).status_code == 409
    assert client.get(f'/api/projects/{other}/knowledge/nodes/{nid}/progress').status_code == 404
    client.patch(f'/api/projects/{pid}/knowledge/nodes/{nid}', json={'expected_version': nodes[0]['version'], 'summary': 'Revised interpretation'})
    assert client.get(url).json()['stale']
    graph = client.get(f'/api/projects/{pid}/knowledge/graph').json()
    current = next(n for n in graph['nodes'] if n['id'] == nid)
    assert current['metadata']['learning_progress'] == 'understood'
    assert current['metadata']['learning_progress_stale']


def test_learning_summary_uses_saved_progress_and_is_scoped(graph_fixture):
    client, pid, other, _, nodes, _ = graph_fixture
    node_id = nodes[0]['id']
    url = f'/api/projects/{pid}/knowledge/nodes/{node_id}/summary'
    result = client.get(url)
    assert result.status_code == 200
    assert result.json()['run_count'] == 0
    assert result.json()['progress']['status'] == 'not_started'
    client.patch(f'/api/projects/{pid}/knowledge/nodes/{node_id}/progress',
                 json={'status': 'review', 'expected_version': 0})
    result = client.get(url).json()
    assert result['progress']['status'] == 'review'
    assert '复习' in result['recommendation']
    assert result['suggested_node']['id'] in {nodes[1]['id'], nodes[2]['id']}
    assert client.get(f'/api/projects/{other}/knowledge/nodes/{node_id}/summary').status_code == 404


def test_learning_summary_model_is_explicit_and_cached(graph_fixture, monkeypatch):
    client, pid, _, _, nodes, _ = graph_fixture
    calls = []
    monkeypatch.setattr(model, 'available', lambda: True)
    def generate(*args, **kwargs):
        calls.append(args)
        return {'explanation': '建议先阅读定义，再运行练习。'}
    monkeypatch.setattr(model, 'structured', generate)
    url = f'/api/projects/{pid}/knowledge/nodes/{nodes[0]["id"]}/summary'
    assert client.get(url).status_code == 200
    assert calls == []
    first = client.post(url).json()
    assert first['explanation'] == '建议先阅读定义，再运行练习。'
    assert first['cached'] is False
    assert client.post(url).json()['cached'] is True
    assert len(calls) == 1


def test_project_learning_summary_only_lists_its_own_records(graph_fixture):
    client, pid, other, _, nodes, _ = graph_fixture
    client.patch(f'/api/projects/{pid}/knowledge/nodes/{nodes[0]["id"]}/progress',
                 json={'status': 'review', 'expected_version': 0})
    response = client.get(f'/api/projects/{pid}/knowledge/progress/summary')
    assert response.status_code == 200
    item = response.json()['items'][0]
    assert item['node_id'] == nodes[0]['id']
    assert item['status'] == 'review'
    assert item['experience_entries'][0]['kind'] == 'self_review'
    assert item['suggested_node']['id'] in {nodes[1]['id'], nodes[2]['id']}
    assert client.get(f'/api/projects/{other}/knowledge/progress/summary').json()['items'] == []


def test_project_ai_summary_is_explicit_cached_and_scoped(graph_fixture, monkeypatch):
    client, pid, other, _, nodes, _ = graph_fixture
    calls = []
    monkeypatch.setattr(model, 'available', lambda: True)
    def generate(system, payload, budget, purpose, **kwargs):
        calls.append(payload)
        return {'explanation': '建议先回看已标记复习的节点。'}
    monkeypatch.setattr(model, 'structured', generate)
    url = f'/api/projects/{pid}/knowledge/progress/summary'
    assert client.get(url).json()['items'] == []
    assert calls == []
    client.patch(f'/api/projects/{pid}/knowledge/nodes/{nodes[0]["id"]}/progress',
                 json={'status': 'review', 'expected_version': 0})
    assert not client.post(url).json()['cached']
    assert client.post(url).json()['cached']
    assert len(calls) == 1
    assert calls[0]['items'][0]['node_id'] == nodes[0]['id']
    assert client.post(f'/api/projects/{other}/knowledge/progress/summary').json()['error']


def test_research_assistant_tracks_unified_graph_versions(graph_fixture):
    from app.assistant.engine import project_report
    _, pid, other, src, nodes, edges = graph_fixture
    with store.connection(pid) as conn:
        before = project_report(conn, pid)
        assert before.coverage['knowledge_nodes'] == 3
        assert any(a.target.view == 'graph' for a in before.actions)
        assert not any(a.id == 'add-paper' for a in before.actions)
        assert project_report(conn, other).coverage['knowledge_nodes'] == 0
        edge = edges[0].copy()
        edge['quality_status'] = 'withdrawn'
        store.put_record(conn, 'kw_edges', edge, preserve_user=False)
        after = project_report(conn, pid)
        assert before.input_fingerprint != after.input_fingerprint
        assert edge['id'] not in {e['id'] for e in after.knowledge_context['edges']}
        store.update_source(conn, pid, src['id'], {'removed': True})
        assert project_report(conn, pid).coverage['knowledge_nodes'] == 0


def test_learning_and_comparison_invalidate_when_a_relation_is_withdrawn(graph_fixture):
    from app.knowledge import comparison, learning, practice
    client, pid, _, src, nodes, edges = graph_fixture
    with store.connection(pid) as conn:
        before_learning = learning.learning_fingerprint(conn, pid, nodes[0]['id'])
        before_comparison = comparison.fingerprint(conn, pid, [src['id']])
        edge = edges[0].copy()
        edge['quality_status'] = 'withdrawn'
        store.put_record(conn, 'kw_edges', edge, preserve_user=False)
        assert learning.learning_fingerprint(conn, pid, nodes[0]['id']) != before_learning
        assert comparison.fingerprint(conn, pid, [src['id']]) != before_comparison
        assert not learning.prerequisites(conn, pid, nodes[0]['id'])
        node = store.record(conn, 'kw_nodes', pid, nodes[0]['id'])
        node.setdefault('metadata', {})['source_withdrawn'] = True
        store.put_record(conn, 'kw_nodes', node, preserve_user=False)
        with pytest.raises(HTTPException) as exc:
            practice.context(conn, pid, node['id'])
        assert exc.value.status_code == 409
    response = client.post(f'/api/projects/{pid}/knowledge/nodes/{nodes[0]["id"]}/learning', json={})
    assert response.status_code == 409


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'https://user:secret@example.com/', 'http://127.0.0.1/test', 'http://localhost/a', 'https://192.168.1.1/a', 'file:///a', 'https://example.com:9000/a'])
def test_resources_reject_unsafe_urls_without_fetch(graph_fixture, url):
    client, pid, _, _, nodes, _ = graph_fixture
    response = client.post(f'/api/projects/{pid}/knowledge/nodes/{nodes[0]["id"]}/resources', json={'title': 'Resource', 'url': url, 'type': 'tutorial'})
    assert response.status_code == 422


def test_resource_types_embeddings_and_search_are_truthful(graph_fixture):
    client, pid, _, _, nodes, _ = graph_fixture
    url = f'/api/projects/{pid}/knowledge/nodes/{nodes[0]["id"]}/resources'
    added = client.post(url, json={'title': 'Original lecture', 'url': 'https://www.youtube.com/watch?v=Ilg3gGewQ5U', 'type': 'video'})
    assert added.status_code == 201
    item = added.json()
    assert item['embed_url'].startswith('https://www.youtube-nocookie.com/embed/')
    assert not item['fetched'] and item['access_status'] == 'not_checked'
    response = client.get(url)
    assert response.status_code == 200
    assert any(r['type'] == 'search' and r['origin'] == 'search' for r in response.json()['items'])
    assert experience.embed_url('https://www.youtube.com.evil.example/watch?v=Ilg3gGewQ5U') is None
    assert experience.embed_url('https://www.bilibili.com/video/BV1234567890/') is not None


def test_resources_follow_explicit_figure_edges_and_keep_source_locator(graph_fixture):
    client, pid, _, src, nodes, _ = graph_fixture
    with store.connection(pid) as conn:
        blocks = store.source_blocks(conn, src['asset_id'])
        store.put_parse(conn, src['asset_id'], {'blocks': blocks + [{'kind': 'figure', 'text': 'Original teaching chart', 'heading': 'Figure 1', 'metadata': {'image_base64': 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9ioAAAAASUVORK5CYII='}}]})
        block = store.source_blocks(conn, src['asset_id'])[-1]
        ev = store.add_evidence(conn, pid, src, block)
        figure = store.put_record(conn, 'kw_nodes', extraction.node(src, 'figure', 'resource', 'Figure 1', 'Original teaching chart', [ev]))
        relation = store.put_record(conn, 'kw_edges', extraction.edge(src, nodes[0]['id'], figure['id'], 'ILLUSTRATED_BY', '图示', 'This method has an explicit source figure.', [ev]))
    url = f'/api/projects/{pid}/knowledge/nodes/{nodes[0]["id"]}/resources'
    image = next(r for r in client.get(url).json()['items'] if r['type'] == 'image')
    assert image['evidence']['block_id'] == block['id'] and image['source_id'] == src['id']
    assert client.get(image['url']).headers['content-type'] == 'image/png'
    with store.connection(pid) as conn:
        relation['quality_status'] = 'withdrawn'
        store.put_record(conn, 'kw_edges', relation, preserve_user=False)
    assert not any(r['type'] == 'image' for r in client.get(url).json()['items'])


def test_offline_question_returns_explicit_excerpts_without_model(graph_fixture, monkeypatch):
    client, pid, _, _, nodes, _ = graph_fixture
    monkeypatch.setattr(model, 'structured', lambda *a, **kw: pytest.fail('No model call on offline question'))
    response = client.post(f'/api/projects/{pid}/knowledge/nodes/{nodes[0]["id"]}/question', json={'question': 'How does it work?'})
    assert response.status_code == 200, response.text
    answer = response.json()
    assert not answer['model_used'] and answer['warnings'] and answer['citations']
    assert '原文摘录' in answer['warnings'][0]


def test_question_filters_fabricated_references_and_caches_by_graph_version(graph_fixture, monkeypatch):
    client, pid, _, _, nodes, _ = graph_fixture
    calls = []
    monkeypatch.setattr(model, 'available', lambda: True)
    def generate(system, payload, budget, purpose, **kwargs):
        calls.append(payload)
        return {'answer': 'The provided source describes the chain rule [1].',
                'evidence_ids': [payload['sources'][0]['id'], 'invented'], 'node_ids': ['invented'], 'edge_ids': ['invented']}
    monkeypatch.setattr(model, 'structured', generate)
    url = f'/api/projects/{pid}/knowledge/nodes/{nodes[0]["id"]}/question'
    first = client.post(url, json={'question': 'Explain the rule'}).json()
    assert first['model_used'] and len(first['citations']) == 1
    assert first['node_ids'] == [nodes[0]['id']] and first['edge_ids'] == []
    assert client.post(url, json={'question': 'Explain the rule'}).json()['cached']
    assert len(calls) == 1
    with store.connection(pid) as conn:
        before = conn.execute('SELECT data FROM kw_nodes WHERE id=?', (nodes[1]['id'],)).fetchone()[0]
        node = json.loads(before)
        store.edit_record(conn, 'kw_nodes', pid, node['id'], node['version'], {'summary': 'Different adjacent explanation'})
    assert not client.post(url, json={'question': 'Explain the rule'}).json()['cached']
    assert len(calls) == 2


def test_question_cache_tracks_selected_model(graph_fixture, monkeypatch):
    client, pid, _, _, nodes, _ = graph_fixture
    selected = ['first']
    calls = []
    monkeypatch.setattr(model, 'available', lambda: True)
    monkeypatch.setattr(model, 'identity', lambda: (selected[0], 'https://model.example'))
    def generate(system, payload, budget, purpose, **kwargs):
        calls.append(selected[0])
        return {'answer': 'The source explains the chain rule [1].',
                'evidence_ids': [payload['sources'][0]['id']], 'node_ids': [], 'edge_ids': []}
    monkeypatch.setattr(model, 'structured', generate)
    url = f'/api/projects/{pid}/knowledge/nodes/{nodes[0]["id"]}/question'
    assert not client.post(url, json={'question': 'Explain the rule'}).json()['cached']
    assert client.post(url, json={'question': 'Explain the rule'}).json()['cached']
    selected[0] = 'second'
    assert not client.post(url, json={'question': 'Explain the rule'}).json()['cached']
    assert calls == ['first', 'second']


def test_library_cannot_impersonate_project(graph_fixture):
    client, _, _, _, nodes, _ = graph_fixture
    assert client.get(f'/api/projects/library/knowledge/nodes/{nodes[0]["id"]}/progress').status_code == 404


@pytest.mark.parametrize('bad', [{'answer': 'Unsupported [2]', 'evidence_ids': None}, {'answer': 'Unsupported [2]', 'evidence_ids': ['fabricated']}, []])
def test_malformed_question_references_fall_back_to_saved_sources(graph_fixture, monkeypatch, bad):
    client, pid, _, _, nodes, _ = graph_fixture
    monkeypatch.setattr(model, 'available', lambda: True)
    monkeypatch.setattr(model, 'structured', lambda *args, **kwargs: bad)
    response = client.post(f'/api/projects/{pid}/knowledge/nodes/{nodes[0]["id"]}/question', json={'question': 'Explain the rule'})
    assert response.status_code == 200 and not response.json()['model_used']
    assert response.json()['warnings'] and response.json()['citations']
