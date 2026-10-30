"""Vision transcription is source-bound, bounded, optional, and user-revisable."""

import hashlib
import json

import pymupdf
from fastapi.testclient import TestClient

from app.main import app
from app.knowledge import extraction, formulas, model, sources, store


def source_pdf(tmp_path):
    path = tmp_path / 'equation.pdf'
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 80), 'r(x) = x + 1')
        pdf.save(path)
    return path


def result():
    return {'title': 'Equation', 'parser': 'docling', 'warnings': ['检测到 1 个公式区域，已转写 0 个'], 'quality': {'status': 'partial'},
            'blocks': [{'ordinal': 0, 'kind': 'formula', 'heading': 'Method', 'text': 'raw source text', 'page': 1, 'bbox': [65, 60, 220, 90], 'metadata': {'latex': '', 'original_text': 'raw source text'}}]}


def test_budgeted_image_transcription_keeps_original_file_and_region(tmp_path, monkeypatch):
    path = source_pdf(tmp_path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(model, 'available', lambda: True)
    calls = []
    def transcribe(system, payload, budget, purpose, **kwargs):
        calls.append(purpose)
        assert len(kwargs['images']) == 1 and kwargs['images'][0].startswith('data:image/png;base64,')
        budget.calls += 1
        return {'formulas': [{'index': payload['items'][0]['index'], 'readable': True, 'latex': 'r(x)=x+1'}]}
    monkeypatch.setattr(model, 'structured', transcribe)
    value = formulas.enrich_result(path, result(), model.Budget('project', 'run'))
    assert value['blocks'][0]['metadata']['original_text'] == 'raw source text'
    assert value['blocks'][0]['metadata']['recognition'] == 'platform_vision_unverified'
    assert value['blocks'][0]['bbox'] == [65, 60, 220, 90]
    assert value['quality']['formula_coverage']['recognized'] == 1
    assert value['quality']['status'] == 'complete'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert calls == ['formula_transcription']


def test_unreadable_or_foreign_formula_never_becomes_latex(tmp_path, monkeypatch):
    path = source_pdf(tmp_path)
    monkeypatch.setattr(model, 'available', lambda: True)
    monkeypatch.setattr(model, 'structured', lambda *a, **k: {'formulas': [{'index': 42, 'readable': True, 'latex': 'invented'}, {'index': 0, 'readable': False, 'latex': 'guessed'}, {'index': 0, 'readable': True, 'latex': 'x=\ufffd'}]})
    value = formulas.enrich_result(path, result(), model.Budget('project', 'run'))
    assert not value['blocks'][0]['metadata']['latex']
    assert value['quality']['formula_status'] == 'partial'
    assert value['quality']['formula_coverage']['recognized'] == 0


def test_single_region_provider_response_is_validated_by_its_source_index(tmp_path, monkeypatch):
    path = source_pdf(tmp_path)
    monkeypatch.setattr(model, 'available', lambda: True)
    monkeypatch.setattr(model, 'structured', lambda *a, **k: {'index': 0, 'readable': True, 'latex': 'x+1'})
    assert formulas.enrich_result(path, result(), model.Budget('project', 'run'))['blocks'][0]['metadata']['latex'] == 'x+1'


def test_formula_correction_is_space_local_and_not_overwritten(tmp_path, monkeypatch):
    path = source_pdf(tmp_path)
    monkeypatch.setattr(model, 'available', lambda: False)
    with TestClient(app) as client:
        pids = []
        for _ in range(2):
            pids.append(client.post('/api/projects', json={'title': 'Formula study', 'domain': 'custom', 'research_question': 'Understand the formula', 'constraints': {'version': 1, 'objective': 'Learn'}}).json()['id'])
        nodes = []
        for pid in pids:
            src = sources.ingest(pid, path.read_bytes(), 'equation.pdf')
            with store.connection(pid) as conn:
                store.put_parse(conn, src['asset_id'], result())
                blocks = store.source_blocks(conn, src['asset_id'])
                extraction.structural_graph(conn, src, blocks)
                node = next(n for n in store.graph(conn, pid)['nodes'] if n['kind'] == 'formula')
                nodes.append(node)
        n = nodes[0]
        updated = client.patch(f'/api/projects/{pids[0]}/knowledge/nodes/{n["id"]}', json={'expected_version': n['version'], 'latex': 'r(x)=x+2'}).json()
        assert updated['origin'] == 'user' and updated['metadata']['recognition'] == 'user_corrected'
        with store.connection(pids[1]) as conn:
            assert store.record(conn, 'kw_nodes', pids[1], nodes[1]['id'])['metadata']['latex'] == ''
        budget = model.Budget(pids[0], 'correction-check')
        assert not formulas.ensure_node(pids[0], n['id'], budget)
        assert budget.calls == 0


def test_block_identity_survives_formula_annotation(tmp_path):
    path = source_pdf(tmp_path)
    with TestClient(app) as client:
        pid = client.post('/api/projects', json={'title': 'Identity', 'domain': 'custom', 'research_question': 'Preserve formula location', 'constraints': {'version': 1, 'objective': 'Read'}}).json()['id']
        src = sources.ingest(pid, path.read_bytes(), 'equation.pdf')
        with store.connection(pid) as conn:
            original = result()
            store.put_parse(conn, src['asset_id'], original)
            before = store.source_blocks(conn, src['asset_id'])[0]['id']
            changed = json.loads(json.dumps(original))
            changed['blocks'][0]['text'] = 'r(x)=x+1'
            changed['blocks'][0]['metadata']['latex'] = 'r(x)=x+1'
            store.put_parse(conn, src['asset_id'], changed)
            assert store.source_blocks(conn, src['asset_id'])[0]['id'] == before
