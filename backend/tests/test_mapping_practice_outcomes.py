"""Mapping-linked practice records retain their evidence and remain scoped."""

import pytest
from fastapi import HTTPException

from app.api.workbench import initialize
from app.knowledge import implementations, outcomes, practice, store
from tests.test_knowledge_practice import fixture_node


def test_mapping_run_and_export(monkeypatch):
    pid, node = fixture_node()
    artifact = practice.get(pid, node['id'])
    mapping = {'id': 'map-1', 'node_id': node['id'], 'revision': 2, 'stale': False,
               'status': 'confirmed', 'implementation_kind': 'source', 'paper_span': 'y = 2*x',
               'code_span': 'return 2*x', 'explanation': 'scale', 'paper_evidence': None,
               'code_evidence': {'source_title': 'code.py', 'locator': {
                   'path': 'code.py', 'start_line': 7,
                   'commit': '9a5dfe0f52efd2624507f8cc9ed117aef6ef7472',
                   'url': 'https://example.org/repo/blob/9a5dfe0f52efd2624507f8cc9ed117aef6ef7472/code.py',
               }, 'quote': 'return 2*x'}}
    monkeypatch.setattr(implementations, 'list_mappings', lambda conn, project, nid: [mapping] if project == pid and nid == node['id'] else [])
    payload = {'status': 'success', 'output': '4', 'code': 'print(4)', 'input_json': '{}', 'elapsed_ms': 10,
               'checked': False, 'passed': None, 'mapping_id': 'map-1', 'mapping_revision': 2,
               'prediction': '4', 'explanation': ''}
    run = practice.save_run(pid, artifact['id'], payload)
    practice.update_run_explanation(pid, artifact['id'], run['id'], 'x=2')
    with pytest.raises(HTTPException) as error:
        practice.save_run(pid, artifact['id'], {**payload, 'mapping_revision': 1})
    assert error.value.status_code == 409
    mapping['status'] = 'rejected'
    with pytest.raises(HTTPException) as error:
        practice.save_run(pid, artifact['id'], payload)
    assert error.value.status_code == 409
    mapping.update(status='confirmed', stale=True)
    with pytest.raises(HTTPException) as error:
        practice.save_run(pid, artifact['id'], payload)
    assert error.value.status_code == 409
    mapping['stale'] = False
    with pytest.raises(HTTPException) as error:
        practice.save_run(pid, artifact['id'], {**payload, 'mapping_id': 'other-node-mapping'})
    assert error.value.status_code == 404
    mapping.update(status='confirmed', revision=3, code_span='new implementation')
    practice.save_draft(pid, artifact['id'], artifact['revision'], 'print("new unsent draft")', '{"d_k":16}')
    # Older than the former 10-run limit still exports its immutable snapshot.
    for _ in range(11):
        practice.save_run(pid, artifact['id'], {**payload, 'mapping_id': None, 'mapping_revision': None})
    with store.connection(pid) as conn:
        initialize(conn)
        exported = outcomes.preview(conn, pid, node['id'], {'mappings': [{'id': 'map-1', 'revision': 3}]})['markdown']
        assert all(text in exported for text in ('code.py', '行 7', 'confirmed', '运行前预测：', '实际输出：', '用户解释：', '```text\nx=2\n```', '运行时映射快照', '修订：2', 'return 2*x', 'new implementation'))
        assert '```python\nprint(4)\n```' in exported and '```json\n{}\n```' in exported
        assert '耗时：10 ms' in exported and '运行所关联的练习修订：1' in exported
        assert 'new unsent draft' not in exported and '{"d_k":16}' not in exported
        captured = next(value for value in outcomes.catalog(conn, pid, node['id'])['practices'][0]['runs'] if value['id'] == run['id'])
        assert captured['code'] == payload['code'] and captured['input_json'] == payload['input_json']
        assert captured['practice_revision'] == artifact['revision']
        assert captured['mapping_revision'] == 2 and captured['mapping_snapshot']['code_span'] == 'return 2*x'
        assert exported.count('9a5dfe0f52efd2624507f8cc9ed117aef6ef7472') == 4
        assert exported.count('https://example.org/repo/blob/9a5dfe0f52efd2624507f8cc9ed117aef6ef7472/code.py') == 2
        with pytest.raises(HTTPException) as error:
            outcomes.preview(conn, pid, node['id'], {'mappings': [{'id': 'map-1', 'revision': 1}]})
        assert error.value.status_code == 409


def test_generation_is_bound_to_confirmed_mapping_and_retains_history(monkeypatch):
    from app.knowledge import model
    pid, node = fixture_node()
    with store.connection(pid) as conn:
        evidence = store.evidence(conn, pid, node['evidence_ids'])[0]
    mapping = {'id': 'chosen', 'node_id': node['id'], 'revision': 2, 'stale': False,
               'status': 'confirmed', 'implementation_kind': 'teaching',
               'paper_span': '2*x', 'code_span': 'return 2*x', 'paper_evidence': evidence,
               'code_evidence': {**evidence, 'id': 'code-evidence', 'quote': 'return 2*x'}}
    monkeypatch.setattr(implementations, 'list_mappings', lambda *args: [mapping])
    monkeypatch.setattr(model, 'available', lambda: True)
    prompts = []

    def generated(system, payload, budget, purpose, **kwargs):
        if purpose == 'practice_review':
            return {'accepted': True, 'issues': [], 'corrections': {}}
        prompts.append(payload)
        return {'title': 'Check a scale', 'prompt': 'Predict the scaled value.',
                'starter_code': 'print(2*2)', 'test_code': '', 'reference_code': '',
                'input_json': '{}', 'hints': [], 'learning_objectives': [], 'simplifications': [],
                'evidence_ids': ['code-evidence']}

    monkeypatch.setattr(model, 'structured', generated)
    artifact = practice.generate(pid, node['id'], mapping_id='chosen', mapping_revision=2)
    assert artifact['status'] == 'ready'
    assert prompts[0]['confirmed_correspondence']['code_span'] == 'return 2*x'
    assert prompts[0]['current_source']['implementation_code_supplied'] is False
    assert artifact['mapping_snapshot']['revision'] == 2
    assert practice.generate(pid, node['id'], mapping_id='chosen', mapping_revision=2)['id'] == artifact['id']
    assert len(prompts) == 1
    mapping.update(revision=3, code_span='return 3*x')
    with pytest.raises(HTTPException) as error:
        practice.generate(pid, node['id'], mapping_id='chosen', mapping_revision=2)
    assert error.value.status_code == 409
    with store.connection(pid) as conn:
        historical = practice.present(conn, pid, practice.record(conn, pid, artifact['id']))
    assert historical['mapping_stale'] is True
    assert historical['mapping_snapshot']['code_span'] == 'return 2*x'
    newer = practice.generate(pid, node['id'], mapping_id='chosen', mapping_revision=3)
    assert newer['id'] != artifact['id'] and len(prompts) == 2
    run = practice.save_run(pid, newer['id'], {'status': 'success', 'output': '6'})
    assert run['mapping_id'] == 'chosen' and run['mapping_revision'] == 3
    with pytest.raises(HTTPException) as error:
        practice.save_run(pid, newer['id'], {'mapping_id': 'another', 'mapping_revision': 3})
    assert error.value.status_code == 409
    with pytest.raises(HTTPException):
        practice.generate(pid, node['id'], mapping_revision=3)
    mapping['status'] = 'rejected'
    with pytest.raises(HTTPException):
        practice.generate(pid, node['id'], mapping_id='chosen', mapping_revision=3)
    reopened = practice.get_for_mapping(pid, node['id'], mapping_id='chosen', mapping_revision=3)
    assert reopened['id'] == newer['id'] and reopened['mapping_stale'] is True
    assert reopened['mapping_snapshot']['code_span'] == 'return 3*x'
