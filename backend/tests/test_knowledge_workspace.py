"""Critical workspace invariants; all models and network calls are isolated."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.knowledge import extraction, learning, model, service, sources, store
from app.knowledge.parser import parse_source

TEXT = b"# Study\n\n## Method\nWe propose State Gate. The gate scales a bounded residual.\n\n## Evaluation\nWe evaluate on Task A using five training seeds.\n"


def project(client, headers=None):
    r = client.post('/api/projects', headers=headers or {}, json={"title": "Real research", "research_question": "How does state gating work?", "domain": "custom", "constraints": {"version": 1, "objective": "Compare grounded methods"}})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture
def synchronous(monkeypatch):
    monkeypatch.setattr(service, 'parse_file', lambda path, kind, check: parse_source(path, kind, use_docling=False))
    def enqueue(pid, sid, retry=False):
        with store.connection(pid) as conn:
            value, fresh = store.create_run(conn, pid, sid)
        if fresh:
            service.analyze(pid, sid, value['id'], retry)
        with store.connection(pid) as conn:
            return store.run(conn, pid, value['id'])
    monkeypatch.setattr(service, 'enqueue', enqueue)


def teaching_sections():
    explanation = "教学解释先说明输入、输出与计算条件，当前来源未给出的张量维度或源码保持未知。步骤1识别来源中明确给出的信息。步骤2逐项检查信息路径及必要条件。步骤3使用教学数值例子x=2与x=0说明输入改变，不能把示例当作论文实验或真实性能保证。边界条件与反例需要结合原文核对。"
    return {key: explanation * 4 for key in ('overview', 'definition', 'derivation', 'prerequisites', 'implementation', 'limitations')}


@pytest.fixture
def fake_model(monkeypatch):
    calls = []
    monkeypatch.setattr(model, 'available', lambda: True)
    monkeypatch.setattr(learning, 'fetch_resources', lambda pid, resources: resources)
    def structured(system, payload, budget, purpose, **kwargs):
        calls.append(purpose)
        budget.calls += 1
        budget.usage['calls'] += 1
        if purpose == 'decomposition':
            block = next((b for b in payload['blocks'] if 'State Gate' in b['text']), payload['blocks'][0])
            quote = 'State Gate' if 'State Gate' in block['text'] else block['text'][:30]
            return {'nodes': [
                {'key': 'gate', 'kind': 'method', 'label': 'State Gate', 'summary': 'A state-dependent gate scales a bounded residual.', 'research_status': 'proposed', 'evidence': [{'block_id': block['block_id'], 'quote': quote}]},
                {'key': 'residual', 'kind': 'module', 'label': 'Bounded residual', 'summary': 'The residual modifies the base output.', 'parent_key': 'gate', 'evidence': [{'block_id': block['block_id'], 'quote': quote}]}],
                'edges': [{'source_key': 'gate', 'target_key': 'residual', 'kind': 'USES', 'label': 'uses', 'origin': 'source', 'evidence': [{'block_id': block['block_id'], 'quote': quote}]}]}
        if purpose == 'cross_source_links':
            return {'edges': []}
        if purpose == 'node_learning':
            return {'sections': teaching_sections(), 'evidence_ids': [payload['sources'][0]['id']]}
        if purpose == 'learning_review':
            return {'accepted': True, 'issues': [], 'corrections': {}}
        if purpose == 'comparison_review':
            return {'rows': payload['rows']}
        if purpose == 'method_comparison':
            return {'rows': [{'dimension': d, 'compatibility': 'Conditions not confirmed; qualitative comparison only.', 'values': [
                {'source_id': s['source_id'], 'text': 'The source describes a state gate.', 'node_ids': [s['nodes'][0]['id']], 'evidence_ids': [s['evidence'][0]['id']], 'origin': 'inference'} for s in payload['sources']]} for d in payload['dimensions']]}
        raise AssertionError(purpose)
    monkeypatch.setattr(model, 'structured', structured)
    return calls


def upload(client, pid, filename='study.md', text=TEXT, headers=None):
    r = client.post(f'/api/projects/{pid}/sources', files={'file': (filename, text)}, headers=headers or {})
    assert r.status_code == 202, r.text
    return r.json()['source']


def semantic(client, pid, sid):
    graph = client.get(f'/api/projects/{pid}/knowledge/graph', params={'source_id': sid, 'limit': 1000}).json()
    return next(n for n in graph['nodes'] if n['metadata'].get('semantic') and n['kind'] == 'method')


def test_upload_automatically_decomposes_and_locates_sources(synchronous, fake_model):
    with TestClient(app) as client:
        pid = project(client)
        source = upload(client, pid)
        assert source['analysis']['status'] == 'succeeded', source['analysis']
        assert source['analysis']['stages'] == {'save': 'done', 'parse': 'done', 'extract': 'done', 'graph': 'done'}
        node = semantic(client, pid, source['id'])
        detail = client.get(f'/api/projects/{pid}/knowledge/nodes/{node["id"]}').json()
        assert detail['evidence'][0]['quote'] == 'State Gate'
        assert detail['evidence'][0]['source_version'].startswith('sha256:')
        assert detail['prerequisites']
        assert all(e['locator']['page'] is None for e in detail['evidence'])
        assert fake_model.count('decomposition') == 1


def test_same_file_has_reusable_parse_and_independent_space_revisions(synchronous, fake_model):
    with TestClient(app) as client:
        a, b = project(client), project(client)
        sa, sb = upload(client, a), upload(client, b)
        assert sa['asset_id'] == sb['asset_id'] and sa['id'] != sb['id']
        na, nb = semantic(client, a, sa['id']), semantic(client, b, sb['id'])
        r = client.patch(f'/api/projects/{a}/knowledge/nodes/{na["id"]}', json={'expected_version': na['version'], 'summary': 'My own correction'})
        assert r.status_code == 200 and r.json()['origin'] == 'user'
        assert client.patch(f'/api/projects/{a}/knowledge/nodes/{na["id"]}', json={'expected_version': na['version'], 'summary': 'stale'}).status_code == 409
        assert client.get(f'/api/projects/{b}/knowledge/nodes/{na["id"]}').status_code == 404
        assert client.get(f'/api/projects/{b}/knowledge/nodes/{nb["id"]}').json()['node']['summary'] != 'My own correction'
        client.post(f'/api/projects/{a}/analysis', json={'source_id': sa['id'], 'retry': True})
        assert client.get(f'/api/projects/{a}/knowledge/nodes/{na["id"]}').json()['node']['summary'] == 'My own correction'


def test_missing_source_and_restore_preserve_knowledge(synchronous, fake_model):
    with TestClient(app) as client:
        pid = project(client)
        src = upload(client, pid)
        n = semantic(client, pid, src['id'])
        path = f'/api/projects/{pid}/sources/{src["id"]}'
        assert client.patch(path, json={'removed': True}).status_code == 200
        assert client.get(f'/api/projects/{pid}/sources').json()['items'] == []
        assert client.get(f'/api/projects/{pid}/sources?include_removed=true').json()['items'][0]['removed']
        assert client.get(f'/api/projects/{pid}/knowledge/nodes/{n["id"]}').json()['node']['source_missing']
        assert client.get(path + '/file').content == TEXT
        client.patch(path, json={'removed': False})
        assert not client.get(f'/api/projects/{pid}/knowledge/nodes/{n["id"]}').json()['node']['source_missing']


def test_learning_cache_invalidates_on_dependency_edit_and_relevant_source_addition(synchronous, fake_model):
    with TestClient(app) as client:
        pid = project(client)
        src = upload(client, pid)
        n = semantic(client, pid, src['id'])
        url = f'/api/projects/{pid}/knowledge/nodes/{n["id"]}/learning'
        assert client.get(url).json()['status'] == 'basic'
        assert 'node_learning' not in fake_model
        assert client.post(url, json={}).json()['status'] == 'ready'
        assert client.post(url, json={}).json()['cached']
        assert fake_model.count('node_learning') == 1
        client.patch(f'/api/projects/{pid}/knowledge/preferences', json={'view': 'reading'})
        assert not client.get(url).json()['stale']
        detail = client.get(f'/api/projects/{pid}/knowledge/nodes/{n["id"]}').json()
        edge = next(e for e in detail['edges'] if e['kind'] == 'PREREQUISITE_OF')
        assert client.patch(f'/api/projects/{pid}/knowledge/edges/{edge["id"]}', json={'expected_version': edge['version'], 'hidden': True}).status_code == 200
        assert client.get(url).json()['stale']
        assert client.post(url, json={}).json()['status'] == 'ready'
        upload(client, pid, 'other.md', TEXT + b'Extra source.')
        assert client.get(url).json()['stale']


def test_comparison_grounding_cache_and_overview_projection(synchronous, fake_model):
    with TestClient(app) as client:
        pid = project(client)
        a, b = upload(client, pid), upload(client, pid, 'other.md', TEXT + b'Other conditions.')
        path = f'/api/projects/{pid}/knowledge/comparisons'
        r = client.post(path, json={'source_ids': [a['id'], b['id']]})
        assert r.status_code == 200, r.text
        value = r.json()
        assert value['status'] == 'ready' and len(value['rows']) == 8
        assert client.post(path, json={'source_ids': [a['id'], b['id']]}).json()['cached']
        assert fake_model.count('method_comparison') == 1
        overview = client.get(f'/api/projects/{pid}/knowledge/graph?overview=true').json()
        assert len([n for n in overview['nodes'] if n['parent_id'] is None]) == 2
        assert any(n['kind'] == 'method' for n in overview['nodes'])
        assert any(n['kind'] == 'module' for n in overview['nodes'])
        assert overview['edges']
        assert all(e['source'] in {n['id'] for n in overview['nodes']} and e['target'] in {n['id'] for n in overview['nodes']} for e in overview['edges'])
        focus = semantic(client, pid, a['id'])
        focused = client.post(path, json={'source_ids': [a['id'], b['id']], 'focus_node_ids': [focus['id']]}).json()
        assert focused['status'] == 'ready' and focused['id'] != value['id']
        assert focused['focus_node_ids'] == [focus['id']]
        assert focused['focus_nodes'][0]['label'] == focus['label']
        assert client.post(path, json={'source_ids': [a['id'], b['id']], 'focus_node_ids': [focus['id']]}).json()['cached']
        other = upload(client, pid, 'unselected.md', TEXT + b'Unselected context.')
        unrelated = semantic(client, pid, other['id'])
        assert client.post(path, json={'source_ids': [a['id'], b['id']], 'focus_node_ids': [unrelated['id']]}).status_code == 422


def test_learning_revisions_survive_regeneration_and_stale_context(synchronous, fake_model):
    with TestClient(app) as client:
        pid = project(client)
        source = upload(client, pid)
        n = semantic(client, pid, source['id'])
        path = f'/api/projects/{pid}/knowledge/nodes/{n["id"]}/learning'
        generated = client.post(path, json={}).json()
        edited = client.patch(path, json={'expected_revision': generated['revision'], 'sections': {'derivation': 'My corrected derivation'}, 'hidden_sections': ['implementation']}).json()
        assert edited['origin'] == 'user' and edited['user_edited_sections'] == ['derivation']
        assert client.patch(path, json={'expected_revision': generated['revision'], 'sections': {'derivation': 'Lost update'}}).status_code == 409
        refreshed = client.post(path, json={'refresh': True}).json()
        assert refreshed['sections']['derivation'] == 'My corrected derivation'
        assert refreshed['hidden_sections'] == ['implementation']
        upload(client, pid, 'additional.md', TEXT + b'New source context')
        assert client.get(path).json()['stale']
        target = client.get(f'/api/projects/{pid}/knowledge/nodes/{n["id"]}').json()['node']
        client.patch(f'/api/projects/{pid}/knowledge/nodes/{n["id"]}', json={'expected_version': target['version'], 'summary': 'A revised current method context'})
        stale = client.get(path).json()
        assert stale['stale']
        revised = client.patch(path, json={'expected_revision': stale['revision'], 'sections': {'overview': 'My intuition'}}).json()
        assert revised['stale']
        final = client.post(path, json={}).json()
        assert final['sections']['overview'] == 'My intuition' and final['sections']['derivation'] == 'My corrected derivation'
        assert final['hidden_sections'] == ['implementation'] and not final['stale']


def test_learning_review_rejects_unsupported_explanation_and_keeps_basics(synchronous, fake_model, monkeypatch):
    original = model.structured
    def checked(*args, **kwargs):
        if args[3] == 'learning_review':
            return {'accepted': False, 'issues': ['Unsupported mathematical simplification'], 'corrections': {}}
        return original(*args, **kwargs)
    monkeypatch.setattr(model, 'structured', checked)
    with TestClient(app) as client:
        pid = project(client)
        src = upload(client, pid)
        n = semantic(client, pid, src['id'])
        value = client.post(f'/api/projects/{pid}/knowledge/nodes/{n["id"]}/learning', json={}).json()
        assert value['status'] == 'partial'
        assert value['sections']['overview'] == n['summary']
        assert '一致性检查' in value['errors'][0]


def test_learning_applies_review_correction_and_rechecks_within_budget(synchronous, fake_model, monkeypatch):
    original, reviews = model.structured, []
    def checked(*args, **kwargs):
        if args[3] == 'learning_review':
            reviews.append(True)
            args[2].calls += 1
            args[2].usage['calls'] += 1
            return {'accepted': len(reviews) > 1, 'issues': ['Clarify calculation'] if len(reviews) == 1 else [], 'corrections': {'derivation': 'Verified corrected mathematics. ' + teaching_sections()['derivation']} if len(reviews) == 1 else {}}
        return original(*args, **kwargs)
    monkeypatch.setattr(model, 'structured', checked)
    with TestClient(app) as client:
        pid = project(client)
        src = upload(client, pid)
        n = semantic(client, pid, src['id'])
        value = client.post(f'/api/projects/{pid}/knowledge/nodes/{n["id"]}/learning', json={}).json()
        assert value['status'] == 'ready' and value['sections']['derivation'].startswith('Verified corrected mathematics')
        assert len(reviews) == 2 and value['usage']['calls'] == 3


def test_learning_context_keeps_neighbor_equations_without_label_keywords(synchronous):
    with TestClient(app) as client:
        pid = project(client)
        src = sources.ingest(pid, b'Local method', 'method.txt')
        with store.connection(pid) as conn:
            store.put_parse(conn, src['asset_id'], {'title': 'Method', 'blocks': [
                {'kind': 'text', 'heading': 'Gate', 'text': 'The gate chooses the residual amplitude.'},
                {'kind': 'formula', 'heading': 'Gate', 'text': 'c*s*tanh(2*m/c)', 'metadata': {'latex': 'cs\\tanh(2m/c)'}}]})
            blocks = store.source_blocks(conn, src['asset_id'])
            eid = store.add_evidence(conn, pid, src, blocks[0])
            n = extraction.node(src, 'gate', 'module', 'State gate', 'Selects amplitude', [eid])
            context = learning.related_source_context(conn, pid, n)
            assert any(e['block_id'] == blocks[1]['id'] and '2*m/c' in e['quote'] for e in context)


def test_pinned_public_code_file_is_frozen_without_repository_api_quota(monkeypatch):
    fetched = []
    def download(url, **kwargs):
        fetched.append(url)
        return b'def policy(x):\n    return x\n', 'text/plain', url
    monkeypatch.setattr(sources, 'download', download)
    commit = 'a' * 40
    raw, filename = sources.repository(f'https://github.com/example/research/blob/{commit}/src/actor_critic.py')
    snapshot = json.loads(raw)
    assert filename.endswith('.repo.json') and snapshot['commit'] == commit
    assert snapshot['files'][0]['path'] == 'src/actor_critic.py'
    assert snapshot['coverage']['selection'] == 'explicit_file'
    assert fetched == [f'https://raw.githubusercontent.com/example/research/{commit}/src/actor_critic.py']


def test_merge_split_preserves_post_merge_edits_and_monotonic_versions(synchronous, fake_model):
    with TestClient(app) as client:
        pid = project(client)
        upload(client, pid)
        graph = client.get(f'/api/projects/{pid}/knowledge/graph').json()
        nodes = [n for n in graph['nodes'] if n['metadata'].get('semantic')]
        merged = client.post(f'/api/projects/{pid}/knowledge/nodes/merge', json={'node_ids': [n['id'] for n in nodes]}).json()
        assert merged['metadata']['merged_members']
        hidden = client.get(f'/api/projects/{pid}/knowledge/graph?include_hidden=true').json()
        assert any(n['hidden'] for n in hidden['nodes'])
        saved_edges = merged['metadata']['merged_edges']
        original_edge = saved_edges[0]
        with store.connection(pid) as conn:
            current = store.record(conn, 'kw_edges', pid, original_edge['id'])
        changed = client.patch(f'/api/projects/{pid}/knowledge/edges/{current["id"]}', json={'expected_version': current['version'], 'explanation': 'Correction after merge'}).json()
        revised = client.patch(f'/api/projects/{pid}/knowledge/nodes/{merged["id"]}', json={'expected_version': merged['version'], 'summary': 'New note after merge'}).json()
        assert client.post(f'/api/projects/{pid}/knowledge/nodes/{merged["id"]}/split', json={}).status_code == 200
        with store.connection(pid) as conn:
            final = store.record(conn, 'kw_edges', pid, original_edge['id'])
        assert final['version'] > changed['version']
        assert final['explanation'] == 'Correction after merge'
        result = client.get(f'/api/projects/{pid}/knowledge/nodes/{merged["id"]}').json()['node']
        assert result['version'] > revised['version'] and result['summary'] == 'New note after merge'


def test_no_model_is_partial_not_fake_semantic_success(synchronous):
    with TestClient(app) as client:
        pid = project(client)
        src = upload(client, pid)
        assert src['analysis']['status'] == 'partial'
        assert src['analysis']['stages']['extract'] == 'partial'
        graph = client.get(f'/api/projects/{pid}/knowledge/graph').json()
        assert graph['nodes'] and not any(n['metadata'].get('semantic') for n in graph['nodes'])


def test_html_original_is_not_active_app_content(synchronous):
    with TestClient(app) as client:
        pid = project(client)
        src = upload(client, pid, 'note.html', b'<h1>Research</h1><script>alert(1)</script><p>Useful content</p>')
        r = client.get(f'/api/projects/{pid}/sources/{src["id"]}/file')
        assert r.headers['content-type'].startswith('text/plain')
        assert r.headers['content-disposition'].startswith('attachment')
        assert 'sandbox' in r.headers['content-security-policy']


def test_new_pdf_larger_than_one_mb_is_uploaded_and_linked(synchronous):
    import pymupdf
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), 'Real source PDF')
        raw = doc.tobytes() + b'\n%' + b'x' * (1024 * 1024 + 32)
    with TestClient(app) as client:
        pid = project(client)
        src = upload(client, pid, 'paper.pdf', raw)
        assert src['paper_uid']
        linked = client.get(f'/api/projects/{pid}/papers').json()
        assert src['paper_uid'] in json.dumps(linked)


def test_active_analysis_claim_is_atomic():
    with TestClient(app) as client:
        pid = project(client)
        src = sources.ingest(pid, TEXT, 'study.md')
        barrier = threading.Barrier(2)
        def claim():
            barrier.wait()
            with store.connection(pid) as conn:
                return store.create_run(conn, pid, src['id'])
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: claim(), range(2)))
        assert sum(int(fresh) for _, fresh in results) == 1
        assert results[0][0]['id'] == results[1][0]['id']


def test_generation_claim_rejects_duplicate_and_is_recoverable():
    with TestClient(app) as client:
        pid = project(client)
        with model.operation(pid, 'same-content'):
            with pytest.raises(HTTPException) as exc:
                with model.operation(pid, 'same-content'):
                    pass
            assert exc.value.status_code == 409
        with model.operation(pid, 'same-content'):
            pass


def test_extraction_rejects_unknown_or_invented_evidence():
    with TestClient(app) as client:
        pid = project(client)
        src = sources.ingest(pid, TEXT, 'study.md')
        with store.connection(pid) as conn:
            store.put_parse(conn, src['asset_id'], parse_source(__import__('pathlib').Path(conn.execute('SELECT path FROM kw_assets WHERE id=?', (src['asset_id'],)).fetchone()[0]), 'report', False))
            blocks = store.source_blocks(conn, src['asset_id'])
            result = {'nodes': [{'key': 'bad', 'kind': 'method', 'label': 'Fabrication', 'summary': 'Unsupported claim', 'evidence': [{'block_id': blocks[0]['id'], 'quote': 'not actually present'}]}]}
            count, warnings = extraction.save_extraction(conn, src, result, blocks)
            assert count == 0 and warnings


def test_omission_expansion_preserves_actual_source_and_rejects_ambiguous_quote():
    text = 'State-dependent gating uses the full context and keeps a bounded residual.'
    assert extraction.resolve_quote(text, 'State-dependent gating...keeps a bounded residual.') == text
    assert extraction.resolve_quote(text, 'State-dependent gating uses...') == 'State-dependent gating uses'
    assert extraction.resolve_quote('repeated quoted phrase and repeated quoted phrase', 'repeated quoted phrase...') is None
    assert extraction.resolve_quote(text, 'invented content that was never reported') is None


def test_successful_reanalysis_retires_old_generated_nodes_but_keeps_user_edits(synchronous, fake_model):
    with TestClient(app) as client:
        pid = project(client)
        src = upload(client, pid)
        n = semantic(client, pid, src['id'])
        with store.connection(pid) as conn:
            extraction.retire_previous(conn, pid, src['id'], 'replacement-generation')
            assert store.record(conn, 'kw_nodes', pid, n['id'])['hidden']
            old = store.record(conn, 'kw_nodes', pid, n['id'])
            old['metadata']['analysis_run'] = 'replacement-generation'
            old['hidden'] = False
            store.put_record(conn, 'kw_nodes', old)
        detail = client.get(f'/api/projects/{pid}/knowledge/nodes/{n["id"]}').json()['node']
        edited = client.patch(f'/api/projects/{pid}/knowledge/nodes/{n["id"]}', json={'expected_version': detail['version'], 'summary': 'Preserve my interpretation'}).json()
        with store.connection(pid) as conn:
            extraction.retire_previous(conn, pid, src['id'], 'yet-another-generation')
            final = store.record(conn, 'kw_nodes', pid, n['id'])
        assert final['summary'] == edited['summary'] and not final['hidden']


def test_model_transport_limits_calls_records_usage_and_does_not_retry(monkeypatch, isolated_services):
    from app.config import get_settings
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'unit-test-key')
    get_settings.cache_clear()
    with TestClient(app) as client:
        pid = project(client)
        settings = get_settings()
        route = isolated_services.post(settings.llm_api_base.rstrip('/') + '/chat/completions').mock(return_value=httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': '{"ok":true}'}}], 'usage': {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30}}))
        budget = model.Budget(pid, 'unit-run', 1)
        assert model.structured('Test', {'x': 1}, budget, 'test') == {'ok': True}
        assert budget.usage['total_tokens'] == 30
        assert model.usage_for(pid, 'unit-run') == {'calls': 1, 'input_tokens': 10, 'output_tokens': 20, 'total_tokens': 30}
        with pytest.raises(model.ModelUnavailable):
            model.structured('Test', {'x': 1}, budget, 'test')
        assert route.call_count == 1
        route.mock(return_value=httpx.Response(429))
        with pytest.raises(model.ModelUnavailable):
            model.structured('Test', {}, model.Budget(pid, 'unit-fail'), 'test')
        assert route.call_count == 2
        with store.connection(pid) as conn:
            assert conn.execute("SELECT COUNT(*) FROM kw_model_calls WHERE status='failed'").fetchone()[0] == 1
            failed = json.loads(conn.execute("SELECT data FROM kw_model_calls WHERE status='failed'").fetchone()[0])
            assert 'HTTP 429' in failed['error']
        route.mock(return_value=httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': '[{"index":2,"readable":true,"latex":"x+1"}]'}}]}))
        assert model.structured('Test', {}, model.Budget(pid, 'formula-shape'), 'formula_transcription')['formulas'][0]['index'] == 2
        with pytest.raises(model.ModelUnavailable):
            model.structured('Test', {}, model.Budget(pid, 'invalid-generic-shape'), 'test')


def test_cancelled_work_never_dispatches_model_after_wait(monkeypatch):
    called = []
    monkeypatch.setattr(model, '_structured', lambda *a, **k: called.append(True))
    def cancelled():
        raise service.Cancelled()
    budget = model.Budget('project', 'run', check_active=cancelled)
    with pytest.raises(service.Cancelled):
        model.structured('x', {}, budget, 'test')
    assert not called and budget.calls == 0


def test_cross_account_cannot_read_or_upload_to_other_space(synchronous):
    with TestClient(app) as a, TestClient(app) as b:
        ra = a.post('/api/auth/register', json={'username': 'knowledge-owner', 'password': 'test-password-123!'})
        rb = b.post('/api/auth/register', json={'username': 'knowledge-other', 'password': 'test-password-123!'})
        ha, hb = {'X-Atlas-CSRF': ra.json()['csrf_token']}, {'X-Atlas-CSRF': rb.json()['csrf_token']}
        pid = project(a, ha)
        src = upload(a, pid, headers=ha)
        assert b.get(f'/api/projects/{pid}/sources').status_code == 404
        assert b.get(f'/api/projects/{pid}/sources/{src["id"]}/file').status_code == 404
        assert b.post(f'/api/projects/{pid}/sources', files={'file': ('other.md', TEXT)}, headers=hb).status_code == 404
