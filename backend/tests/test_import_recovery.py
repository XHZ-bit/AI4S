"""Import acceptance and analysis scheduling are separate durable outcomes."""

from concurrent.futures import Future
import threading

from fastapi.testclient import TestClient

from app.main import app
from app.knowledge import model, service, store
from app.knowledge.parser import parse_source


def make_project(client):
    response = client.post('/api/projects', json={
        'title': 'Import recovery', 'research_question': 'Understand a method',
        'domain': 'custom', 'constraints': {'version': 1, 'objective': 'Read a real source'},
    })
    assert response.status_code == 201, response.text
    return response.json()['id']


def test_saved_upload_survives_queue_saturation_and_resumes_once(monkeypatch):
    slots = threading.BoundedSemaphore(1)
    slots.acquire()
    monkeypatch.setattr(service, '_queue_slots', slots)
    submitted = []
    def submit(*args):
        future = Future()
        submitted.append(future)
        return future
    monkeypatch.setattr(service, 'submit_task', submit)
    with TestClient(app) as client:
        pid = make_project(client)
        response = client.post(f'/api/projects/{pid}/sources', files={'file': ('new.md', b'# New source\nA saved paper.')})
        assert response.status_code == 202, response.text
        result = response.json()
        assert result['scheduled'] is False
        assert result['analysis']['status'] == 'interrupted'
        sid = result['source']['id']
        assert result['source']['availability'] == {'original': True, 'parsed': False, 'blocks': 0, 'semantic_nodes': 0, 'parse_partial': False}
        assert client.get(f'/api/projects/{pid}/sources/{sid}/file').status_code == 200
        assert len(client.get(f'/api/projects/{pid}/sources').json()['items']) == 1

        slots.release()
        first = client.post(f'/api/projects/{pid}/analysis', json={'source_id': sid, 'retry': True})
        again = client.post(f'/api/projects/{pid}/analysis', json={'source_id': sid, 'retry': True})
        assert first.status_code == again.status_code == 202
        assert first.json()['id'] == again.json()['id']
        assert len(submitted) == 1
        submitted[0].set_result(None)


def test_executor_unavailable_preserves_source_but_unknown_failures_remain_errors(monkeypatch):
    def unavailable(*args):
        raise RuntimeError('executor is shutting down')
    monkeypatch.setattr(service, 'submit_task', unavailable)
    with TestClient(app, raise_server_exceptions=False) as client:
        pid = make_project(client)
        response = client.post(f'/api/projects/{pid}/sources', files={'file': ('first.md', b'# Original\nSaved before scheduling.')})
        assert response.status_code == 202, response.text
        assert response.json()['scheduled'] is False
        assert '暂不可用' in response.json()['notice']

        def unexpected(*args):
            raise ValueError('unexpected programmer error')
        monkeypatch.setattr(service, 'submit_task', unexpected)
        failed = client.post(f'/api/projects/{pid}/sources', files={'file': ('second.md', b'# Another source\nStill stored.')})
        assert failed.status_code == 500
        assert len(client.get(f'/api/projects/{pid}/sources').json()['items']) == 2
        invalid = client.post(f'/api/projects/{pid}/sources', files={'file': ('invalid.exe', b'Unsupported')})
        assert invalid.status_code == 415
        assert len(client.get(f'/api/projects/{pid}/sources').json()['items']) == 2


def test_offline_continue_reuses_parse_and_preserves_manual_node_revision(monkeypatch):
    monkeypatch.setattr(model, 'available', lambda: False)
    parses = []
    def parse(path, kind, check):
        parses.append(path)
        return parse_source(path, kind, use_docling=False)
    monkeypatch.setattr(service, 'parse_file', parse)
    pending = []
    def submit(*args):
        future = Future()
        pending.append((future, args))
        return future
    monkeypatch.setattr(service, 'submit_task', submit)
    with TestClient(app) as client:
        pid = make_project(client)
        response = client.post(f'/api/projects/{pid}/sources', files={'file': ('method.md', b'# Method\n\n## State Gate\nA gate scales a residual.')})
        source = response.json()['source']
        future, args = pending[-1]
        args[0](*args[1:])
        future.set_result(None)
        item = client.get(f'/api/projects/{pid}/sources').json()['items'][0]
        assert item['analysis']['status'] == 'partial'
        assert item['availability']['original'] and item['availability']['parsed']
        assert item['availability']['blocks'] > 0
        graph = client.get(f'/api/projects/{pid}/knowledge/graph', params={'source_id': source['id'], 'limit': 1000}).json()
        node = graph['nodes'][0]
        changed = client.patch(f'/api/projects/{pid}/knowledge/nodes/{node["id"]}', json={'expected_version': node['version'], 'summary': 'My checked explanation.'})
        assert changed.status_code == 200, changed.text
        continued = client.post(f'/api/projects/{pid}/analysis', json={'source_id': source['id'], 'retry': True})
        assert continued.status_code == 202
        future, args = pending[-1]
        args[0](*args[1:])
        future.set_result(None)
        assert len(parses) == 1
        with store.connection(pid) as conn:
            assert store.record(conn, 'kw_nodes', pid, node['id'])['summary'] == 'My checked explanation.'
