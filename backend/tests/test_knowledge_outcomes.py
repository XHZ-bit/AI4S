"""Real saved-node outcomes, without generation or model/network services."""

import json
import io
import re
from contextlib import redirect_stdout
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.knowledge import extraction, learning, model, sources, store
from app.knowledge.parser import parse_source


def create_project(client):
    response = client.post('/api/projects', json={"title": "Outcome study", "domain": "custom", "research_question": "Understand one concept", "constraints": {"version": 1, "objective": "Understand one concept"}})
    assert response.status_code == 201, response.text
    return response.json()['id']


def seed(pid, title='study.md'):
    src = sources.ingest(pid, ('# Method\nA gate scales a residual.\n'+title).encode(), title, 'paper')
    with store.connection(pid) as conn:
        asset = conn.execute('SELECT path FROM kw_assets WHERE id=?', (src['asset_id'],)).fetchone()[0]
        result = parse_source(Path(asset), 'paper', use_docling=False)
        store.put_parse(conn, src['asset_id'], result)
        blocks = store.source_blocks(conn, src['asset_id'])
        eid = store.add_evidence(conn, pid, src, blocks[0])
        node = extraction.node(src, 'gate', 'concept', 'Gate', 'A residual gate', [eid], parent_id='root')
        store.put_record(conn, 'kw_nodes', node)
    return src, node, blocks[0], eid


@pytest.fixture
def study():
    with TestClient(app) as client:
        pid = create_project(client)
        src, node, block, eid = seed(pid)
        yield client, pid, src, node, block, eid


def note(pid, node, **extra):
    return {'id': 'my-note', 'version': 0, 'title': 'My understanding', 'body': 'A gate controls the residual.', 'project_id': pid, 'knowledge_node_id': node['id'], 'unresolved_questions': 'What bounds the sample?', **extra}


def outcomes_root(pid, node):
    return f'/api/workbench/projects/{pid}/nodes/{node["id"]}/outcomes'


def test_note_context_conflicts_and_legacy_editor_preserves_provenance(study):
    client, pid, src, node, block, _ = study
    payload = note(pid, node, source_id=src['id'], block_id=block['id'], source_version=src['version'], node_version=node['version'])
    response = client.post('/api/workbench/records', json=payload)
    assert response.status_code == 200, response.text
    saved = response.json()
    context = json.loads(saved['source_json'])
    assert context['knowledge_node_id'] == node['id']
    assert context['source_version'] == src['version']
    assert client.post('/api/workbench/records', json=payload).status_code == 409
    response = client.post('/api/workbench/records', json={'id': saved['id'], 'version': saved['version'], 'title': 'Edited in old notebook', 'body': 'My own explanation'})
    assert response.status_code == 200, response.text
    assert json.loads(response.json()['source_json']) == context
    assert client.get('/api/workbench/records', params={'project_id': pid, 'knowledge_node_id': node['id']}).json()['items'][0]['body'] == 'My own explanation'
    with store.connection(pid) as conn:
        store.update_source(conn, pid, src['id'], {'removed': True})
    response = client.post('/api/workbench/records', json={**payload, 'version': 2, 'body': 'Historical note remains editable'})
    assert response.status_code == 200, response.text
    assert client.get(outcomes_root(pid, node)).json()['notes'][0]['stale'] is True


def test_note_rejects_cross_project_and_wrong_source_or_block(study):
    client, pid, src, node, block, _ = study
    other = create_project(client)
    second, _, _, _ = seed(pid, 'other.md')
    assert client.post('/api/workbench/records', json=note(other, node)).status_code == 404
    assert client.post('/api/workbench/records', json=note(pid, node, source_id=second['id'])).status_code == 422
    assert client.post('/api/workbench/records', json=note(pid, node, block_id='foreign-block')).status_code == 422
    assert client.get('/api/workbench/records', params={'knowledge_node_id': node['id']}).status_code == 422


def test_export_only_selected_saved_content_and_never_generates(study, monkeypatch):
    client, pid, src, node, _, eid = study
    monkeypatch.setattr(model, 'structured', lambda *a, **kw: pytest.fail('Outcome export must not call models'))
    assert client.post('/api/workbench/records', json=note(pid, node)).status_code == 200
    with store.connection(pid) as conn:
        artifact = {'id': 'lesson', 'node_id': node['id'], 'status': 'ready', 'revision': 2, 'goal': 'Gate example', 'depth': 'standard', 'sections': {'overview': 'SELECTED EXPLANATION', 'limitations': 'PRIVATE UNSELECTED LIMITATION'}, 'evidence': [], 'user_edited_sections': ['overview']}
        conn.execute('INSERT INTO kw_learning VALUES(?,?,?,?)', (pid, node['id'], learning.learning_fingerprint(conn, pid, node['id'], 'Gate example', 'standard'), store.encode(artifact)))
    catalog = client.get(outcomes_root(pid, node)).json()
    assert catalog['lessons'][0]['id'] == 'lesson'
    response = client.post(outcomes_root(pid, node) + '/preview', json={'note_ids': ['my-note'], 'evidence_ids': [eid], 'learning_sections': [{'artifact_id': 'lesson', 'revision': 2, 'section': 'overview'}]})
    assert response.status_code == 200, response.text
    markdown = response.json()['markdown']
    assert 'SELECTED EXPLANATION' in markdown and '人工修订' in markdown
    assert 'PRIVATE UNSELECTED LIMITATION' not in markdown
    assert 'What bounds the sample?' in markdown and 'A gate controls the residual.' in markdown
    assert 'study' in markdown and '原文依据' in markdown
    assert client.post(outcomes_root(pid, node) + '/preview', json={}).status_code == 422
    assert client.post(outcomes_root(pid, node) + '/preview', json={'note_ids': ['foreign-note']}).status_code == 422
    assert client.post(outcomes_root(pid, node) + '/preview', json={'learning_sections': [{'artifact_id': 'lesson', 'revision': 1, 'section': 'overview'}]}).status_code == 409


def test_outcomes_respects_account_database_boundary(study):
    from app.api.workbench import record
    from app.tenancy import user_scope
    from fastapi import HTTPException
    client, pid, _, node, _, _ = study
    assert client.post('/api/workbench/records', json=note(pid, node)).status_code == 200
    with user_scope({'id': 'a' * 32}):
        with pytest.raises(HTTPException) as error:
            record('my-note')
        assert error.value.status_code == 404


def test_export_practice_distinguishes_running_from_passing_and_comparison_has_conditions(study):
    from app.knowledge import practice
    client, pid, src, node, _, eid = study
    with store.connection(pid) as conn:
        practice.init(conn)
        exercise = {'id': 'practice', 'node_id': node['id'], 'title': 'Gate exercise', 'revision': 1, 'goal': 'Check a gate', 'node_version': node['version'], 'source_version': src['version']}
        conn.execute('INSERT INTO kw_practice VALUES(?,?,?,?,?)', ('practice', pid, node['id'], 'fingerprint', store.encode(exercise)))
        run = {'id': 'run', 'status': 'success', 'created_at': 'saved-time', 'checked': False, 'passed': None}
        conn.execute('INSERT INTO kw_practice_runs VALUES(?,?,?,?)', ('run', pid, 'practice', store.encode(run)))
        comparison = {'id': 'comparison', 'revision': 2, 'source_ids': [src['id']], 'focus_node_ids': [node['id']], 'fingerprint': 'older', 'rows': [
            {'dimension': 'mechanism', 'compatibility': 'Different experimental conditions', 'values': [{'source_id': src['id'], 'text': 'SELECTED COMPARISON', 'origin': 'user', 'node_ids': [node['id']], 'evidence_ids': [eid]}]},
            {'dimension': 'results', 'compatibility': 'Unknown', 'values': [{'source_id': src['id'], 'text': 'UNSELECTED RESULT', 'origin': 'inference', 'node_ids': [], 'evidence_ids': []}]}]}
        conn.execute('INSERT INTO kw_comparisons VALUES(?,?,?,?)', ('comparison', pid, 'older', store.encode(comparison)))
    response = client.post(outcomes_root(pid, node) + '/preview', json={'practice_ids': ['practice'], 'comparison_cells': [{'comparison_id': 'comparison', 'revision': 2, 'dimension': 'mechanism', 'source_id': src['id']}]})
    assert response.status_code == 200, response.text
    markdown = response.json()['markdown']
    assert '运行完成' in markdown and '未进行用例判定' in markdown and '用例通过' not in markdown
    assert 'SELECTED COMPARISON' in markdown and 'Different experimental conditions' in markdown
    assert 'UNSELECTED RESULT' not in markdown and '历史版本' in markdown


def test_selected_answer_references_are_captured_scoped_and_survive_source_changes(study):
    client, pid, src, node, _, eid = study
    other_pid = create_project(client)
    _, _, _, foreign_eid = seed(other_pid, 'foreign.md')
    response = client.post('/api/workbench/records', json=note(pid, node, evidence_references=[{'id': foreign_eid}]))
    assert response.status_code == 422
    response = client.post('/api/workbench/records', json=note(pid, node, evidence_references=[{'id': eid, 'source_version': src['version'], 'quote': 'FORGED'}]))
    assert response.status_code == 200, response.text
    saved = response.json()
    captured = json.loads(saved['source_json'])['evidence_references'][0]
    assert captured['quote'] != 'FORGED' and captured['block_id']
    with store.connection(pid) as conn:
        store.update_source(conn, pid, src['id'], {'version': 'source-v2'})
    listed = client.get('/api/workbench/records', params={'project_id': pid, 'knowledge_node_id': node['id']}).json()['items'][0]
    assert listed['context']['evidence_references'][0]['source_changed']
    response = client.post('/api/workbench/records', json=note(pid, node, version=1, evidence_references=[{**captured, 'quote': 'CHANGED IN CLIENT'}]))
    assert response.status_code == 200, response.text
    assert json.loads(response.json()['source_json'])['evidence_references'][0] == captured
    exported = client.post(outcomes_root(pid, node)+'/preview', json={'note_ids': ['my-note']}).json()['markdown']
    assert captured['quote'] in exported and captured['source_version'] in exported
    assert '平台定位：/research/' in exported and '历史版本' in exported
    assert 'CHANGED IN CLIENT' not in exported


def test_export_retains_executed_attention_code_input_and_versions_after_draft_edit(study, monkeypatch):
    from app.knowledge import practice
    client, pid, src, node, _, _ = study
    monkeypatch.setattr(model, 'structured', lambda *args, **kwargs: pytest.fail('Export must not generate'))
    exercise = practice.get(pid, node['id'])
    code = 'import math\nprint(inputs["dot"] / math.sqrt(inputs["d_k"]))\n'
    inputs = '{"dot":8,"d_k":16}'
    output = io.StringIO()
    with redirect_stdout(output):
        exec(code, {'inputs': json.loads(inputs)})
    assert output.getvalue() == '2.0\n'
    response = client.post(f'/api/projects/{pid}/knowledge/practice/{exercise["id"]}/runs', json={
        'status': 'success', 'output': output.getvalue(), 'code': code, 'input_json': inputs,
        'elapsed_ms': 37, 'prediction': '2.0', 'explanation': '增大缩放分母，固定点积得到2.0。',
        'checked': False, 'passed': None,
    })
    assert response.status_code == 201, response.text
    run = response.json()
    selection = {'practice_ids': [exercise['id']]}
    before = client.post(outcomes_root(pid, node) + '/preview', json=selection).json()['markdown']
    response = client.patch(f'/api/projects/{pid}/knowledge/practice/{exercise["id"]}', json={
        'expected_revision': exercise['revision'], 'code': 'print("CURRENT DRAFT MUST NOT EXPORT")',
        'input_json': '{"dot":8,"d_k":4}',
    })
    assert response.status_code == 200, response.text
    catalog = client.get(outcomes_root(pid, node)).json()
    saved = next(item for item in catalog['practices'] if item['id'] == exercise['id'])
    captured = saved['runs'][0]
    assert captured['code'] == code and captured['input_json'] == inputs
    assert captured['elapsed_ms'] == 37 and captured['status'] == 'success'
    assert captured['practice_id'] == exercise['id']
    assert captured['practice_revision'] == exercise['revision']
    assert captured['node_version'] == node['version']
    assert captured['source_version'] == src['version']
    assert captured['practice_fingerprint'] == exercise['fingerprint']
    assert saved['revision'] == exercise['revision'] + 1
    after = client.post(outcomes_root(pid, node) + '/preview', json=selection).json()['markdown']
    run_heading = '### 教学运行：' + run['id']
    assert after.split(run_heading, 1)[1] == before.split(run_heading, 1)[1]
    assert 'CURRENT DRAFT MUST NOT EXPORT' not in after
    assert inputs in after and code in after and '2.0' in after
    assert '耗时：37 ms' in after and '未进行用例判定' in after
    assert '运行所关联的练习修订：' + str(exercise['revision']) in after
    assert '浏览器报告的教学运行，未独立验证。' in after


def test_export_literal_run_payloads_use_fences_longer_than_saved_content(study):
    from app.knowledge import practice
    client, pid, _, node, _, _ = study
    exercise = practice.get(pid, node['id'])
    code = 'print("2.0")\n# ```python\n# ````\n# # Still code, not another Markdown heading\n'
    inputs = json.dumps({'dot': 8, 'd_k': 16, 'comment': '`````\n# Still JSON'}, ensure_ascii=False)
    output = '2.0\n```\n# Still output'
    response = client.post(f'/api/projects/{pid}/knowledge/practice/{exercise["id"]}/runs', json={
        'status': 'success', 'output': output, 'code': code, 'input_json': inputs, 'elapsed_ms': 0,
        'prediction': '```\nA prediction', 'explanation': '````\nA personal explanation',
    })
    assert response.status_code == 201, response.text
    markdown = client.post(outcomes_root(pid, node) + '/preview', json={'practice_ids': [exercise['id']]}).json()['markdown']
    for label, language, payload in [
        ('本次执行的 Python 代码', 'python', code), ('本次执行的 JSON 输入', 'json', inputs),
        ('实际输出', 'text', output), ('运行前预测', 'text', '```\nA prediction'),
        ('用户解释', 'text', '````\nA personal explanation'),
    ]:
        match = re.search(re.escape(label) + r'：\n\n(`{3,})' + language + r'\n(.*?)\n\1(?:\n|$)', markdown, re.S)
        assert match, label
        assert match[2] == payload
        assert len(match[1]) > max((len(part[0]) for part in re.finditer(r'`+', payload)), default=0)
    assert '耗时：0 ms' in markdown


def test_legacy_run_exports_available_fields_without_inventing_current_draft(study):
    from app.knowledge import practice
    client, pid, _, node, _, _ = study
    exercise = practice.get(pid, node['id'])
    with store.connection(pid) as conn:
        conn.execute('INSERT INTO kw_practice_runs VALUES(?,?,?,?)', (
            'legacy-run', pid, exercise['id'], store.encode({
                'id': 'legacy-run', 'status': 'error', 'created_at': 'legacy-time',
                'output': 'ValueError: old recorded error', 'explanation': '保留已有解释。',
            }),
        ))
    catalog = client.get(outcomes_root(pid, node)).json()
    run = catalog['practices'][0]['runs'][0]
    assert run['practice_id'] == exercise['id']
    for key in ('code', 'input_json', 'elapsed_ms', 'practice_revision', 'node_version', 'source_version', 'practice_fingerprint'):
        assert run[key] is None
    markdown = client.post(outcomes_root(pid, node) + '/preview', json={'practice_ids': [exercise['id']]}).json()['markdown']
    assert '运行出错' in markdown and 'legacy-time' in markdown
    assert 'ValueError: old recorded error' in markdown and '保留已有解释。' in markdown
    assert markdown.count('旧运行未保存此项，不使用当前编辑稿补写。') == 2
    assert '耗时：未记录' in markdown and '运行所关联的练习修订：未记录' in markdown
    assert exercise['draft_code'] not in markdown and exercise['input_json'] not in markdown
