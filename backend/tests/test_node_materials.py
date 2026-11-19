"""Personal node materials preserve ownership, originals and user decisions."""

import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.knowledge import model, node_materials, service, sources, store
from app.tenancy import user_scope
from tests.test_knowledge_workspace import project


def node_root(pid, nid):
    return f'/api/projects/{pid}/knowledge/nodes/{nid}'


@pytest.fixture
def material_case(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Saving personal nodes or materials must not request models or schedule analysis')
    monkeypatch.setattr(model, 'structured', forbidden)
    monkeypatch.setattr(service, 'enqueue', forbidden)
    with TestClient(app) as client:
        pid, other = project(client), project(client)
        created = client.post(f'/api/projects/{pid}/knowledge/nodes', json={
            'label': 'My research question', 'summary': 'Record my interpretation of a method.', 'kind': 'concept'})
        assert created.status_code == 201, created.text
        node = created.json()['node']
        foreign = client.post(f'/api/projects/{other}/knowledge/nodes', json={'label': 'Other project only'}).json()['node']
        source = sources.ingest(pid, b'# Supporting document\n\nPersonal background material.', 'background.md')
        yield client, pid, other, node, foreign, source


def attach(client, pid, node, source, note='Read the implementation details'):
    result = client.post(node_root(pid, node['id']) + '/materials', json={'source_id': source['id'], 'note': note})
    assert result.status_code == 201, result.text
    return result.json()['item']


def test_manual_node_has_user_authored_original_and_survives_graph_reload_without_model(material_case):
    client, pid, _, node, _, _ = material_case
    assert node['origin'] == 'user' and node['metadata']['manual'] and node['metadata']['user_authored']
    graph = client.get(f'/api/projects/{pid}/knowledge/graph?overview=false').json()
    assert node['id'] in {item['id'] for item in graph['nodes']}
    assert graph['edges'] == []
    detail = client.get(node_root(pid, node['id'])).json()
    direct = next(item for item in detail['evidence'] if item['id'] in node['evidence_ids'])
    assert direct['origin'] == 'user' and direct['quote'] == node['summary']
    source = client.get(f'/api/projects/{pid}/sources/{node["source_id"]}').json()
    assert '个人节点' in source['title'] and source['blocks']
    raw = client.get(f'/api/projects/{pid}/sources/{source["id"]}/file')
    assert raw.status_code == 200 and '个人知识节点，由用户撰写' in raw.content.decode()
    with store.connection(pid) as conn:
        assert conn.execute('SELECT COUNT(*) FROM kw_runs WHERE project_id=?', (pid,)).fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM kw_learning WHERE project_id=?', (pid,)).fetchone()[0] == 0


def test_material_binding_preserves_source_version_personal_note_and_history(material_case):
    client, pid, _, node, _, source = material_case
    root = node_root(pid, node['id']) + '/materials'
    item = attach(client, pid, node, source)
    assert item['source_snapshot']['version'] == source['version'] and item['note'] == 'Read the implementation details'
    assert item['origin'] == 'user' and item['reviewed_by'] and item['revision'] == 1
    assert not item['source_missing'] and not item['source_changed']
    assert client.get(item['original_url']).content.startswith(b'# Supporting document')
    assert client.get(root).json()['items'][0]['id'] == item['id']
    history = client.get(root + '/' + item['id'] + '/history').json()['items']
    assert len(history) == 1 and history[0]['source_snapshot'] == item['source_snapshot']
    with store.connection(pid) as conn:
        assert conn.execute('SELECT COUNT(*) FROM kw_edges WHERE project_id=?', (pid,)).fetchone()[0] == 0


@pytest.mark.parametrize('filename,raw,kind', [
    ('notes.md', b'# Node notes\n\nThis is the locally parsed attachment.', 'report'),
    ('example.py', b"# Never execute uploaded code\nraise RuntimeError('must not execute')\n", 'code'),
])
def test_uploaded_text_and_code_are_immediately_readable_without_analysis(material_case, filename, raw, kind):
    client, pid, _, node, _, _ = material_case
    response = client.post(node_root(pid, node['id']) + '/materials/upload',
                           files={'file': (filename, raw)}, data={'kind': kind, 'note': 'For this node only'})
    assert response.status_code == 201, response.text
    result = response.json()
    assert result['reading_status'] == 'ready' and result['item']['note'] == 'For this node only'
    source = client.get(f'/api/projects/{pid}/sources/{result["source"]["id"]}').json()
    assert source['blocks'] and not source['analysis']
    assert client.get(result['item']['original_url']).content == raw
    with store.connection(pid) as conn:
        assert conn.execute('SELECT COUNT(*) FROM kw_nodes WHERE project_id=?', (pid,)).fetchone()[0] == 1
        assert conn.execute('SELECT COUNT(*) FROM kw_runs WHERE project_id=?', (pid,)).fetchone()[0] == 0


def test_node_and_source_bindings_reject_cross_project_ids_before_saving_files(material_case):
    client, pid, other, node, foreign, source = material_case
    foreign_source = sources.ingest(other, b'# Private to project B', 'private.md')
    assert client.post(node_root(pid, node['id']) + '/materials', json={'source_id': foreign_source['id']}).status_code == 404
    assert client.get(node_root(other, node['id']) + '/materials').status_code == 404
    with store.connection(pid) as conn:
        before = conn.execute('SELECT COUNT(*) FROM kw_sources WHERE project_id=?', (pid,)).fetchone()[0]
    result = client.post(node_root(pid, foreign['id']) + '/materials/upload', files={'file': ('wrong.md', b'Should not save')})
    assert result.status_code == 404
    with store.connection(pid) as conn:
        assert conn.execute('SELECT COUNT(*) FROM kw_sources WHERE project_id=?', (pid,)).fetchone()[0] == before
    with user_scope({'id': 'c' * 32, 'username': 'other-account'}):
        with pytest.raises(HTTPException) as error:
            with store.connection(pid):
                pass
        assert error.value.status_code == 404


def test_removed_and_changed_sources_keep_material_history_and_notes(material_case):
    client, pid, _, node, _, source = material_case
    item = attach(client, pid, node, source)
    root = node_root(pid, node['id']) + '/materials'
    with store.connection(pid) as conn:
        store.update_source(conn, pid, source['id'], {'version': 'sha256:new-version'})
    changed = client.get(root).json()['items'][0]
    assert changed['source_changed'] and not changed['source_missing']
    assert changed['source_snapshot']['version'] == source['version']
    assert changed['current_source']['version'] == 'sha256:new-version'
    assert client.patch(f'/api/projects/{pid}/sources/{source["id"]}', json={'removed': True}).status_code == 200
    removed = client.get(root).json()['items'][0]
    assert removed['id'] == item['id'] and removed['note'] == item['note']
    assert removed['source_missing'] and removed['original_url'] is None
    assert removed['current_source']['removed']
    assert client.get(root + '/' + item['id'] + '/history').json()['items'][0]['source_snapshot']['version'] == source['version']


def test_revision_conflicts_do_not_erase_notes_and_removing_attachment_preserves_original(material_case):
    client, pid, _, node, _, source = material_case
    item = attach(client, pid, node, source)
    root = node_root(pid, node['id']) + '/materials'
    endpoint = root + '/' + item['id']
    saved = client.patch(endpoint, json={'expected_revision': 1, 'note': 'My updated explanation'}).json()['item']
    assert saved['revision'] == 2
    assert client.patch(endpoint, json={'expected_revision': 1, 'removed': True}).status_code == 409
    assert client.get(root).json()['items'][0]['note'] == 'My updated explanation'
    response = client.patch(endpoint, json={'expected_revision': 2, 'removed': True})
    assert response.status_code == 200 and response.json()['item']['revision'] == 3
    assert client.get(root).json()['items'] == []
    historical = client.get(root + '?include_removed=true').json()['items'][0]
    assert historical['removed'] and historical['source_snapshot'] == item['source_snapshot']
    assert client.get(item['original_url']).status_code == 200
    history = client.get(endpoint + '/history').json()['items']
    assert [entry['revision'] for entry in history] == [3, 2, 1]
    restored = attach(client, pid, node, source, note='Deliberately restored')
    assert restored['revision'] == 4 and not restored['removed']


def test_duplicate_binding_is_idempotent_and_cannot_overwrite_a_newer_note(material_case):
    client, pid, _, node, _, source = material_case
    item = attach(client, pid, node, source)
    again = attach(client, pid, node, source)
    assert item['id'] == again['id'] and again['revision'] == 1
    root = node_root(pid, node['id']) + '/materials'
    response = client.post(root, json={'source_id': source['id'], 'note': 'Overwrite without revision'})
    assert response.status_code == 409
    assert client.get(root).json()['items'][0]['note'] == item['note']
    assert len(client.get(root + '/' + item['id'] + '/history').json()['items']) == 1


@pytest.mark.parametrize('failure', [HTTPException(409, 'Concurrent node change'), RuntimeError('Simulated store failure')])
def test_upload_failure_exposes_saved_original_for_recovery_without_losing_file(material_case, monkeypatch, failure):
    client, pid, _, node, _, _ = material_case
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(node_materials, 'bind', fail)
    raw = b'# Keep this original\n\nAlready accepted content.'
    response = client.post(node_root(pid, node['id']) + '/materials/upload', files={'file': ('recover.md', raw)})
    assert response.status_code == (failure.status_code if isinstance(failure, HTTPException) else 503)
    detail = response.json()['detail']
    assert '原文件已保存' in detail['message']
    sid = detail['saved_source']['id']
    assert client.get(f'/api/projects/{pid}/sources/{sid}/file').content == raw
    assert client.get(f'/api/projects/{pid}/sources/{sid}').json()['blocks']


def test_native_parse_does_not_replace_existing_blocks_or_evidence(material_case):
    client, pid, _, node, _, source = material_case
    with store.connection(pid) as conn:
        store.put_parse(conn, source['asset_id'], {'blocks': [{'text': 'Previous reviewed parse', 'kind': 'text'}]})
        original = store.source_blocks(conn, source['asset_id'])
    response = client.post(node_root(pid, node['id']) + '/materials/upload',
                           files={'file': ('background.md', b'# Supporting document\n\nPersonal background material.')})
    assert response.status_code == 201
    with store.connection(pid) as conn:
        assert store.source_blocks(conn, source['asset_id']) == original


def test_invalid_names_files_and_patch_fields_are_rejected(material_case):
    client, pid, _, node, _, source = material_case
    assert client.post(f'/api/projects/{pid}/knowledge/nodes', json={'label': '   '}).status_code == 422
    assert client.post(f'/api/projects/{pid}/knowledge/nodes', json={'label': 'Name', 'origin': 'source'}).status_code == 422
    response = client.post(node_root(pid, node['id']) + '/materials/upload', files={'file': ('script.exe', b'not valid')})
    assert response.status_code == 415
    item = attach(client, pid, node, source)
    endpoint = node_root(pid, node['id']) + '/materials/' + item['id']
    assert client.patch(endpoint, json={'expected_revision': 1}).status_code == 422
    assert client.patch(endpoint, json={'expected_revision': 1, 'source_id': 'other'}).status_code == 422
    with store.connection(pid) as conn:
        stored = json.loads(conn.execute('SELECT data FROM kw_node_materials WHERE id=?', (item['id'],)).fetchone()[0])
        assert stored['source_id'] == source['id']
