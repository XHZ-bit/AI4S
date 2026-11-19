"""Exercise explicit model generation and review via the real HTTP routes."""
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.knowledge import extraction, model, sources, store
from app.knowledge.parser import parse_source


def test_explicit_model_generation_keeps_reviews_and_reads_without_calls(monkeypatch):
    client = TestClient(app)
    response = client.post('/api/projects', json={'title': 'Implementation', 'domain': 'custom',
        'research_question': 'Explain scaled attention', 'constraints': {'version': 1, 'objective': 'Verify evidence'}})
    assert response.status_code == 201
    pid = response.json()['id']
    paper = sources.ingest(pid, b'# Attention\nDivide the dot product by the square root of d_k.', 'attention.md', 'paper')
    code = sources.ingest(pid, b'import math\ndef scale(x, d_k):\n    return x / math.sqrt(d_k)\n', 'attention.py', 'code')
    with store.connection(pid) as conn:
        for src in (paper, code):
            asset = conn.execute('SELECT path FROM kw_assets WHERE id=?', (src['asset_id'],)).fetchone()[0]
            store.put_parse(conn, src['asset_id'], parse_source(Path(asset), src['kind'], use_docling=False))
        pb = next(b for b in store.source_blocks(conn, paper['asset_id']) if 'Divide' in b['text'])
        cb = next(b for b in store.source_blocks(conn, code['asset_id']) if b['metadata'].get('symbol') == 'scale')
        eid = store.add_evidence(conn, pid, paper, pb)
        node = extraction.node(paper, 'scaled', 'method', 'Scaled attention', 'Divide by square root', [eid])
        store.put_record(conn, 'kw_nodes', node)
    calls = []

    def generate(system, payload, budget, purpose, **kwargs):
        calls.append(purpose)
        assert budget.limit == 1
        assert any(b['id'] == cb['id'] for src in payload['code_sources'] for b in src['blocks'])
        return {'items': [{'paper_evidence_id': eid, 'paper_span': 'square root of d_k',
            'code_source_id': code['id'], 'code_block_id': cb['id'], 'code_span': 'x / math.sqrt(d_k)',
            'explanation': 'The denominator computes the square root.'}]}

    monkeypatch.setattr(model, 'available', lambda: True)
    monkeypatch.setattr(model, 'structured', generate)
    route = f'/api/projects/{pid}/knowledge/nodes/{node["id"]}/implementations'
    assert client.get(route).json()['items'] == []
    assert calls == []
    generated = client.post(route + '/generate', json={'source_ids': [code['id']]})
    assert generated.status_code == 200, generated.text
    item = generated.json()['items'][0]
    assert generated.json()['generation'] == 'model' and item['status'] == 'proposed'
    reviewed = client.patch(route + '/' + item['id'], json={'expected_revision': 1, 'status': 'rejected'})
    assert reviewed.status_code == 200
    refreshed = client.post(route + '/generate', json={'source_ids': [code['id']], 'refresh': True})
    same = next(x for x in refreshed.json()['items'] if x['id'] == item['id'])
    assert same['status'] == 'rejected' and same['revision'] == 2
    assert len(calls) == 2
    client.get(route)
    assert len(calls) == 2
    # Concurrent offline generation serializes the final check-and-insert.
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setattr(model, 'available', lambda: False)
    with store.connection(pid) as conn:
        second = extraction.node(paper, 'another-method', 'method', 'scale', 'square root', [eid])
        store.put_record(conn, 'kw_nodes', second)
    second_route = f'/api/projects/{pid}/knowledge/nodes/{second["id"]}/implementations'
    with ThreadPoolExecutor(max_workers=2) as pool:
        requests = [pool.submit(client.post, second_route + '/generate',
            json={'source_ids': [code['id']], 'refresh': True}) for _ in range(2)]
        responses = [request.result() for request in requests]
    assert all(response.status_code == 200 for response in responses)
    saved = client.get(second_route).json()['items']
    assert saved and len(saved) == len({(x['code_block_id'], x['paper_span'], x['code_span']) for x in saved})
