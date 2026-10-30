"""Graph semantics and zero-model comparison reads on actual saved extraction."""
from fastapi.testclient import TestClient

from app.main import app
from tests import test_knowledge_workspace as workspace_fixtures
from tests.test_knowledge_workspace import project, semantic, upload

# Keep the shared pytest fixture objects discoverable in this test module.
fake_model = workspace_fixtures.fake_model
synchronous = workspace_fixtures.synchronous


def test_comparison_auto_fills_without_a_model_request_and_preserves_edits(synchronous, fake_model):
    with TestClient(app) as client:
        pid = project(client)
        a, b = upload(client, pid), upload(client, pid, 'b.md', b'# Method\nState Gate scales another bounded residual.\n')
        url = f'/api/projects/{pid}/knowledge/comparisons/preview'
        ids = [('source_ids', a['id']), ('source_ids', b['id'])]
        before = list(fake_model)
        value = client.get(url, params=ids).json()
        assert value['status'] == 'basic' and value['auto_filled']
        method = next(r for r in value['rows'] if r['dimension'] == '方法与模块划分')
        assert 'State Gate' in method['values'][0]['text'] and method['values'][0]['evidence_ids']
        assert fake_model == before
        patch = {'source_ids': [a['id'], b['id']], 'expected_revision': 1, 'dimension': '方法与模块划分', 'source_id': a['id'], 'text': 'My research annotation'}
        edit_url = f'/api/projects/{pid}/knowledge/comparisons/{value["id"]}'
        edited = client.patch(edit_url, json=patch)
        assert edited.status_code == 200, edited.text
        assert client.patch(edit_url, json=patch).status_code == 409
        read = client.get(url, params=ids).json()
        entry = next(r for r in read['rows'] if r['dimension'] == patch['dimension'])['values'][0]
        assert entry['text'] == patch['text'] and entry['origin'] == 'user'
        regenerated = client.post(f'/api/projects/{pid}/knowledge/comparisons', json={'source_ids': patch['source_ids'], 'refresh': True}).json()
        assert next(r for r in regenerated['rows'] if r['dimension'] == patch['dimension'])['values'][0]['text'] == patch['text']
        n = semantic(client, pid, a['id'])
        client.patch(f'/api/projects/{pid}/knowledge/nodes/{n["id"]}', json={'expected_version': n['version'], 'summary': 'Updated source organization'})
        changed = client.get(url, params=ids).json()
        assert changed['id'] != value['id']
        assert next(r for r in changed['rows'] if r['dimension'] == patch['dimension'])['values'][0]['text'] == patch['text']


def test_custom_comparison_dimensions_are_grounded_or_unknown(synchronous, fake_model):
    with TestClient(app) as client:
        pid = project(client)
        a, b = upload(client, pid), upload(client, pid, 'b.md', b'# Method\nState Gate scales another bounded residual.\n')
        before = len(fake_model)
        params = [('source_ids', a['id']), ('source_ids', b['id']), ('dimensions', '方法与模块划分'), ('dimensions', '未出现的物理约束')]
        result = client.get(f'/api/projects/{pid}/knowledge/comparisons/preview', params=params)
        assert result.status_code == 200, result.text
        value = result.json()
        assert [r['dimension'] for r in value['rows']] == ['方法与模块划分', '未出现的物理约束']
        assert all(not c['evidence_ids'] for c in value['rows'][1]['values'])
        assert len(fake_model) == before
