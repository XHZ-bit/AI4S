"""Comparison templates and personal outcomes use real stored source snapshots."""

import json

from fastapi.testclient import TestClient

from app.main import app
from app.knowledge import comparison, extraction, store
from tests.test_knowledge_workspace import project, upload

pytest_plugins = ['tests.test_knowledge_workspace']


def prepare(client):
    pid = project(client)
    sources = [upload(client, pid, filename=name) for name in ['first.md', 'second.md']]
    # Different imported assets may share text, while the source IDs stay scoped.
    if sources[0]['id'] == sources[1]['id']:
        sources[1] = upload(client, pid, filename='second.md', text=b'# Study B\n\n## Method\nState Gate also appears here.\n')
    root = f'/api/projects/{pid}/knowledge/comparisons'
    value = client.get(root + '/preview', params=[('source_ids', s['id']) for s in sources]).json()
    return pid, sources, root, value


def test_study_template_uses_findings_and_experimental_conditions(synchronous, fake_model):
    with TestClient(app) as client:
        pid, sources, root, _ = prepare(client)
        with store.connection(pid) as conn:
            for source in sources:
                source = store.source(conn, pid, source['id'])
                block = store.source_blocks(conn, source['asset_id'])[0]
                eid = store.add_evidence(conn, pid, source, block)
                for kind in ['experiment', 'finding']:
                    item = extraction.node(source, kind, kind, kind, 'Source-grounded ' + kind, [eid], metadata={'semantic': True})
                    store.put_record(conn, 'kw_nodes', item)
        params = [('source_ids', s['id']) for s in sources] + [('template', 'study')]
        response = client.get(root + '/preview', params=params)
        assert response.status_code == 200, response.text
        value = response.json()
        assert value['template'] == 'study'
        assert value['dimensions'] == comparison.STUDY_DIMENSIONS
        findings = next(r for r in value['rows'] if r['dimension'] == '主要发现')
        assert all('Source-grounded finding' in v['text'] and v['evidence_snapshot'] for v in findings['values'])
        assert 'method_comparison' not in fake_model


def test_cell_review_rejects_other_source_and_preserves_manual_decisions(synchronous, fake_model):
    with TestClient(app) as client:
        pid, sources, root, value = prepare(client)
        dimension = '方法与模块划分'
        own = next(e for e in value['evidence'] if e['source_id'] == sources[0]['id'])
        other = next(e for e in value['evidence'] if e['source_id'] == sources[1]['id'])
        body = {'source_ids': value['source_ids'], 'expected_revision': value['revision'], 'dimension': dimension,
                'source_id': sources[0]['id'], 'text': '我的判断', 'evidence_ids': [other['id']], 'reviewed': True}
        assert client.patch(root + '/' + value['id'], json=body).status_code == 422
        body['evidence_ids'] = [own['id']]
        response = client.patch(root + '/' + value['id'], json=body)
        assert response.status_code == 200, response.text
        edited = response.json()
        cell = next(r for r in edited['rows'] if r['dimension'] == dimension)['values'][0]
        assert cell['reviewed'] and cell['reviewed_by'] == '本机用户'
        assert cell['evidence_snapshot'][0]['quote'] == own['quote']
        assert client.patch(root + '/' + value['id'], json=body).status_code == 409
        response = client.post(root, json={'source_ids': value['source_ids'], 'refresh': True})
        assert response.status_code == 200, response.text
        refreshed = response.json()
        cell = next(r for r in refreshed['rows'] if r['dimension'] == dimension)['values'][0]
        assert cell['text'] == '我的判断' and cell['reviewed']
        assert refreshed['revision'] > edited['revision']
        evidence = client.get(root + '/' + refreshed['id'] + '/evidence', params={'source_id': sources[0]['id']}).json()
        assert all(e['source_id'] == sources[0]['id'] for e in evidence['items'])


def test_saved_outcome_keeps_original_evidence_and_has_independent_preview(synchronous, fake_model):
    with TestClient(app) as client:
        pid, sources, root, value = prepare(client)
        body = {'expected_revision': value['revision'], 'selections': [{'dimension': '方法与模块划分', 'source_id': sources[0]['id']}],
                'question': '这两篇怎样构造方法？', 'interpretation': '这是我的理解', 'unresolved': '条件是否一致？'}
        outcome_root = root + '/' + value['id'] + '/outcomes'
        preview = client.post(outcome_root + '/preview', json=body)
        assert preview.status_code == 200, preview.text
        assert client.get(outcome_root).json()['items'] == []
        saved = client.post(outcome_root, json=body).json()
        evidence = saved['cells'][0]['evidence'][0]
        assert '来源版本' in saved['markdown'] and 'block=' + evidence['block_id'] in saved['markdown']
        assert saved['question'] == body['question']
        with store.connection(pid) as conn:
            changed = {**evidence, 'quote': 'A rewritten evidence record.'}
            conn.execute('UPDATE kw_evidence SET data=? WHERE project_id=? AND id=?', (store.encode(changed), pid, evidence['id']))
            src = store.source(conn, pid, sources[0]['id'])
            src['version'] = 'replacement-version'
            conn.execute('UPDATE kw_sources SET data=? WHERE project_id=? AND id=?', (store.encode(src), pid, src['id']))
        reopened = client.get(outcome_root).json()['items'][0]
        assert reopened['markdown'] == saved['markdown']
        assert reopened['cells'][0]['evidence'][0]['quote'] == evidence['quote']
        assert reopened['source_changes'][0]['source_id'] == sources[0]['id']
        other_pid = project(client)
        assert client.get(f'/api/projects/{other_pid}/knowledge/comparisons/{value["id"]}/outcomes').status_code == 404
        body['expected_revision'] = 999
        assert client.post(outcome_root, json=body).status_code == 409


def test_generation_merges_review_saved_while_model_runs(synchronous, fake_model, monkeypatch):
    from app.knowledge import model

    with TestClient(app) as client:
        pid, sources, root, value = prepare(client)
        original = model.structured
        edited = False
        with store.connection(pid) as conn:
            row = conn.execute('SELECT data FROM kw_nodes WHERE project_id=? AND source_id=?', (pid, sources[0]['id'])).fetchone()
            node = json.loads(row[0])
            node['summary'] += ' Updated context.'
            store.put_record(conn, 'kw_nodes', node)

        def during_generation(system, payload, budget, purpose, **kwargs):
            nonlocal edited
            if purpose == 'method_comparison' and not edited:
                edited = True
                comparison.revise(pid, value['id'], value['revision'], '方法与模块划分', sources[0]['id'], '并发保存的判断', value['source_ids'])
            return original(system, payload, budget, purpose, **kwargs)

        monkeypatch.setattr(model, 'structured', during_generation)
        response = client.post(root, json={'source_ids': value['source_ids'], 'refresh': True})
        assert response.status_code == 200, response.text
        fresh = response.json()
        assert fresh['id'] != value['id']
        assert next(r for r in fresh['rows'] if r['dimension'] == '方法与模块划分')['values'][0]['text'] == '并发保存的判断'
        with store.connection(pid) as conn:
            stored = json.loads(conn.execute('SELECT data FROM kw_comparisons WHERE id=?', (fresh['id'],)).fetchone()[0])
        assert stored['manual_cells']['方法与模块划分\t' + sources[0]['id']]['text'] == '并发保存的判断'


def test_edit_reconstructs_missing_study_preview_with_its_template(synchronous, fake_model):
    with TestClient(app) as client:
        pid, sources, root, _ = prepare(client)
        dimensions = ['研究问题']
        value = comparison.compare(pid, [s['id'] for s in sources], dimensions=dimensions, template='study', basic_only=True)
        with store.connection(pid) as conn:
            conn.execute('DELETE FROM kw_comparisons WHERE id=? AND project_id=?', (value['id'], pid))
        response = client.patch(root + '/' + value['id'], json={
            'source_ids': value['source_ids'], 'dimensions': dimensions, 'template': 'study',
            'expected_revision': 1, 'dimension': dimensions[0], 'source_id': sources[0]['id'], 'text': '实证研究判断'})
        assert response.status_code == 200, response.text
        assert response.json()['template'] == 'study'
        assert response.json()['rows'][0]['values'][0]['text'] == '实证研究判断'


def test_uncited_basic_cells_are_not_explicit_source_statements(synchronous, fake_model):
    with TestClient(app) as client:
        pid, sources, root, _ = prepare(client)
        params = [('source_ids', source['id']) for source in sources] + [('dimensions', '未报告的硬件预算')]
        response = client.get(root + '/preview', params=params)
        assert response.status_code == 200, response.text
        value = response.json()
        assert all(not cell['evidence_ids'] and cell['origin'] == 'inference' for cell in value['rows'][0]['values'])
        with store.connection(pid) as conn:
            saved = json.loads(conn.execute('SELECT data FROM kw_comparisons WHERE id=?', (value['id'],)).fetchone()[0])
        assert all(cell['origin'] == 'inference' for cell in saved['rows'][0]['values'])
        assert 'method_comparison' not in fake_model


def test_legacy_uncited_labels_are_corrected_on_reads_without_rewriting_decisions(synchronous, fake_model):
    with TestClient(app) as client:
        pid, sources, root, value = prepare(client)
        missing, manual = value['rows'][0]['values']
        missing.update(text='旧比较未保存依据的内容', origin='source', evidence_ids=[], evidence_snapshot=[])
        manual.update(text='保留个人补充', origin='user', evidence_ids=[], evidence_snapshot=[], reviewed=False)
        cited, inferred = value['rows'][1]['values']
        for cell, source, origin in ((cited, sources[0], 'source'), (inferred, sources[1], 'inference')):
            evidence = next(e for e in value['evidence'] if e['source_id'] == source['id'])
            cell.update(origin=origin, evidence_ids=[evidence['id']], evidence_snapshot=[evidence])
        value['manual_cells'] = {value['rows'][0]['dimension'] + '\t' + sources[1]['id']: dict(manual)}
        value['status'] = 'ready'
        raw = store.encode(value)
        with store.connection(pid) as conn:
            conn.execute('UPDATE kw_comparisons SET data=? WHERE id=?', (raw, value['id']))

        listed = client.get(root).json()['items'][0]
        params = [('source_ids', source['id']) for source in sources]
        cached = client.get(root + '/preview', params=params).json()
        with store.connection(pid) as conn:
            opened = comparison.get_comparison(conn, pid, value['id'])
            assert conn.execute('SELECT data FROM kw_comparisons WHERE id=?', (value['id'],)).fetchone()[0] == raw
        for current in (listed, cached, opened):
            assert current['revision'] == value['revision']
            assert current['rows'][0]['values'][0]['text'] == missing['text']
            assert current['rows'][0]['values'][0]['origin'] == 'inference'
            assert current['rows'][0]['values'][1] == manual
            assert [cell['origin'] for cell in current['rows'][1]['values']] == ['source', 'inference']
        preview = client.post(root + '/' + value['id'] + '/outcomes/preview', json={
            'expected_revision': value['revision'],
            'selections': [{'dimension': value['rows'][0]['dimension'], 'source_id': sources[0]['id']}],
        })
        assert preview.status_code == 200, preview.text
        assert preview.json()['cells'][0]['origin'] == 'inference'
        assert '原文归纳' not in preview.json()['markdown']

        changed = client.patch(root + '/' + value['id'], json={
            'source_ids': value['source_ids'], 'expected_revision': value['revision'],
            'dimension': value['rows'][0]['dimension'], 'source_id': sources[0]['id'],
            'text': '用户修订后的内容', 'evidence_ids': [], 'reviewed': False,
        })
        assert changed.status_code == 200, changed.text
        assert changed.json()['rows'][0]['values'][0]['origin'] == 'user'
        assert changed.json()['rows'][0]['values'][1] == manual
        assert [cell['origin'] for cell in changed.json()['rows'][1]['values']] == ['source', 'inference']
