"""Node practice remains grounded, versioned and entirely client-executed."""

import json

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.knowledge_practice import router
from app.db import projects
from app.db.sqlite import connect
from app.knowledge import extraction, model, practice, sources, store
from app.knowledge.parser import parse_source
from app.models.research import ResearchProjectCreate


def fixture_node(label="Scale function"):
    conn = connect()
    try:
        pid = projects.create_project(conn, ResearchProjectCreate(title="Isolated practice",
            research_question="Understand a scale function", domain="custom",
            constraints={"version": 1, "objective": "Check local numerical behavior"})).id
    finally:
        conn.close()
    text = f"# {label}\n\n## Formula\ny = 2*x. This is a teaching fixture, not a research result.\n"
    source = sources.ingest(pid, text.encode(), "synthetic.md", "report")
    with store.connection(pid) as conn:
        parsed = parse_source(__import__('pathlib').Path(conn.execute('SELECT path FROM kw_assets WHERE id=?', (source['asset_id'],)).fetchone()[0]), "report", use_docling=False)
        store.put_parse(conn, source['asset_id'], parsed)
        block = next(b for b in store.source_blocks(conn, source['asset_id']) if '2*x' in b['text'])
        eid = store.add_evidence(conn, pid, source, block)
        node = extraction.node(source, "fixture-scale", "formula", label, "The fixture defines y=2*x", [eid], metadata={"latex": "y=2x"})
        store.put_record(conn, "kw_nodes", node)
    return pid, node


def test_code_review_requires_model_and_never_executes_user_code(monkeypatch):
    pid, node = fixture_node()
    exercise = practice.get(pid, node["id"])
    monkeypatch.setattr(model, "available", lambda: False)
    with pytest.raises(HTTPException) as exc:
        practice.review_code(pid, exercise["id"], "print('hello')")
    assert exc.value.status_code == 503

    calls = []
    monkeypatch.setattr(model, "available", lambda: True)
    def structured(system, payload, budget, purpose, **kwargs):
        calls.append((payload, purpose))
        return {"feedback": "请检查张量的维度。"}
    monkeypatch.setattr(model, "structured", structured)
    code = "import torch\nraise RuntimeError('must not execute')"
    result = practice.review_code(pid, exercise["id"], code, "ModuleNotFoundError")
    assert result["feedback"] == "请检查张量的维度。"
    assert calls[0][0]["code"] == code
    assert calls[0][1] == "practice_code_review"


def test_user_saved_feedback_is_persistent_idempotent_and_scoped():
    from app.main import app as main_app

    project_id, node = fixture_node()
    other_id, other_node = fixture_node("Other project")
    artifact = practice.get(project_id, node["id"])
    path = f'/api/projects/{project_id}/knowledge/nodes/{node["id"]}/experiences'
    payload = {"practice_id": artifact["id"], "content": "检查维度，再结合运行结果核对。"}
    with TestClient(main_app) as client:
        first = client.post(path, json=payload)
        assert first.status_code == 201, first.text
        entry = first.json()
        assert entry["origin"] == "user_saved_ai_feedback"
        assert client.post(path, json=payload).json()["id"] == entry["id"]
        assert client.get(path).json()["items"] == [entry]
        summary = client.get(f'/api/projects/{project_id}/knowledge/progress/summary').json()
        assert summary["items"][0]["saved_experiences"][0]["id"] == entry["id"]
        assert summary["items"][0]["status"] == "not_started"
        other_path = f'/api/projects/{other_id}/knowledge/nodes/{other_node["id"]}/experiences'
        assert client.get(other_path).json()["items"] == []
        assert client.post(other_path, json=payload).status_code == 404


def test_generated_exercise_supports_standard_input(monkeypatch):
    pid, node = fixture_node()
    prompts = []
    monkeypatch.setattr(model, "available", lambda: True)

    def structured(system, payload, budget, purpose, **kwargs):
        prompts.append(system)
        if purpose == "practice_review":
            return {"accepted": True, "issues": [], "corrections": {}}
        return {
            "title": "两数相加", "prompt": "输入两行整数并输出它们的和。",
            "starter_code": "a = int(input())\nb = int(input())\nprint(a + b)",
            "test_code": "assert a + b == 5", "reference_code": "",
            "input_json": '{"stdin":["2","3"]}', "expected_behavior": "输出 5",
            "hints": [], "learning_objectives": [], "simplifications": [],
            "evidence_ids": [payload["sources"][0]["id"]],
        }

    monkeypatch.setattr(model, "structured", structured)
    exercise = practice.generate(pid, node["id"])
    assert exercise["status"] == "ready"
    assert json.loads(exercise["input_json"])["stdin"] == ["2", "3"]
    assert "可使用 input()" in prompts[0]
    assert "不要再次调用 input()" in prompts[0]


def test_generated_exercise_rejects_invalid_standard_input():
    value = {"title": "Input", "prompt": "Read input", "starter_code": "print(input())",
             "input_json": '{"stdin":42}', "hints": [], "learning_objectives": [], "simplifications": []}
    with pytest.raises(model.ModelUnavailable, match="程序输入"):
        practice.validate_exercise(value, [])


@pytest.fixture
def generated(monkeypatch):
    calls = []
    monkeypatch.setattr(model, 'available', lambda: True)
    def structured(system, payload, budget, purpose, **kwargs):
        calls.append((purpose, payload))
        budget.calls += 1
        budget.usage['calls'] += 1
        assert budget.limit == 4
        if purpose == 'practice_review':
            return {'accepted': True, 'issues': [], 'corrections': {}}
        return {'title': payload['goal'] + '/' + payload['difficulty'],
                'prompt': 'Use current fixture to compute y=2*x. ' + payload['adjustment'],
                'starter_code': "values = inputs['values']\nprint([2*x for x in values])\n",
                'test_code': 'assert 2*2 == 4', 'reference_code': '',
                'input_json': '{"values":[1,2,3]}', 'expected_behavior': 'A teaching result only.',
                'hints': ['Multiply each x by 2'], 'learning_objectives': [payload['goal']],
                'simplifications': ['A synthetic fixture, not a research experiment.'],
                'evidence_ids': [payload['sources'][0]['id']]}
    monkeypatch.setattr(model, 'structured', structured)
    return calls


def test_get_starter_and_changed_difficulty_never_calls_model(monkeypatch):
    pid, node = fixture_node()
    monkeypatch.setattr(model, 'structured', lambda *a, **k: pytest.fail('GET must not call a model'))
    basic = practice.get(pid, node['id'])
    deep = practice.get(pid, node['id'], 'Check an extreme input', 'advanced')
    assert basic['status'] == deep['status'] == 'starter'
    assert basic['id'] != deep['id']
    assert len(json.loads(basic['input_json'])['values']) == 3
    assert len(json.loads(deep['input_json'])['values']) == 11
    assert '不是模型生成的专属课程' in basic['simplifications'][0]
    assert practice.resume(pid, node['id'])['id'] == deep['id']
    assert practice.get(pid, node['id'])['id'] == basic['id']


def test_generation_uses_goal_difficulty_source_cache_and_preserves_draft(generated):
    pid, node = fixture_node()
    basic = practice.get(pid, node['id'], 'Check local slope')
    draft = practice.save_draft(pid, basic['id'], 1, "print('my unsaved idea')", '{}')
    first = practice.generate(pid, node['id'], 'Check local slope')
    assert first['status'] == 'ready' and len(generated) == 2
    assert generated[0][1]['node']['id'] == node['id']
    assert generated[0][1]['current_source']['id'] == node['source_id']
    assert generated[0][1]['current_source']['implementation_code_supplied'] is False
    assert practice.generate(pid, node['id'], 'Check local slope')['id'] == first['id']
    assert len(generated) == 2
    second = practice.generate(pid, node['id'], 'Find a counterexample', 'advanced', 'Add a zero input')
    assert second['id'] != first['id'] and second['title'] != first['title']
    assert generated[2][1]['adjustment'] == 'Add a zero input'
    with store.connection(pid) as conn:
        practice.init(conn)
        assert practice.record(conn, pid, basic['id'])['draft_code'] == draft['draft_code']
    assert len(second['versions']) >= 3


def test_adjustment_receives_actual_saved_draft_and_invalidates_cache_after_edit(generated):
    pid, node = fixture_node()
    old = practice.get(pid, node['id'], 'Original goal')
    saved = practice.save_draft(pid, old['id'], old['revision'], 'print("edited code", inputs["values"])', '{"values":[7],"scale":2}')
    adjusted = practice.generate(pid, node['id'], 'New goal', 'advanced', 'Keep my code and add a boundary case', previous_practice_id=saved['id'])
    previous = generated[0][1]['previous_exercise']
    assert previous['draft_code'] == saved['draft_code']
    assert previous['input_json'] == saved['input_json']
    assert previous['title'] == old['title'] and previous['prompt'] == old['prompt']
    assert previous['origin'] == 'user_teaching_draft' and previous['is_source_implementation'] is False
    cached = practice.generate(pid, node['id'], 'New goal', 'advanced', 'Keep my code and add a boundary case', previous_practice_id=saved['id'])
    assert cached['id'] == adjusted['id'] and len(generated) == 2
    revised = practice.save_draft(pid, old['id'], saved['revision'], 'print("new edit")', '{"values":[9]}')
    resumed = practice.resume(pid, node['id'])
    assert resumed['id'] == adjusted['id'] and resumed['status'] == 'ready'
    next_value = practice.generate(pid, node['id'], 'New goal', 'advanced', 'Keep my code and add a boundary case', previous_practice_id=revised['id'])
    assert next_value['fingerprint'] != adjusted['fingerprint']
    assert next_value['previous_context_hash'] != adjusted['previous_context_hash']
    assert generated[2][1]['previous_exercise']['draft_code'] == 'print("new edit")'
    assert len(generated) == 4
    assert practice.resume(pid, node['id'])['id'] == next_value['id']


def test_adjustment_rejects_previous_exercise_from_other_node_or_space(generated):
    pid, node = fixture_node()
    with store.connection(pid) as conn:
        source = store.source(conn, pid, node['source_id'])
        other_node = extraction.node(source, 'other-node', 'concept', 'Another node', 'Not this exercise target', node['evidence_ids'])
        store.put_record(conn, 'kw_nodes', other_node)
    wrong_node = practice.get(pid, other_node['id'])
    other_pid, foreign_node = fixture_node('Foreign space')
    wrong_space = practice.get(other_pid, foreign_node['id'])
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        path = f'/api/projects/{pid}/knowledge/nodes/{node["id"]}/practice'
        for previous_id in (wrong_node['id'], wrong_space['id'], 'unknown-practice'):
            response = client.post(path, json={'goal': 'Adjust my draft', 'previous_practice_id': previous_id})
            assert response.status_code == 404
    assert generated == []


def test_private_data_is_not_read_or_executed_and_browser_report_is_labelled(monkeypatch, generated, tmp_path):
    pid, node = fixture_node()
    original = model.structured
    marker = tmp_path / 'must-not-exist'
    def hostile(system, payload, budget, purpose, **kwargs):
        result = original(system, payload, budget, purpose, **kwargs)
        if purpose == 'node_practice':
            result['starter_code'] = f"open({str(marker)!r}, 'w').write('host execution is forbidden')"
        return result
    monkeypatch.setattr(model, 'structured', hostile)
    artifact = practice.generate(pid, node['id'])
    assert artifact['status'] == 'ready' and not marker.exists()
    assert artifact['quality']['execution'] == 'not_executed'
    run = practice.save_run(pid, artifact['id'], {'status': 'error', 'output': 'browser traceback', 'code': artifact['starter_code'], 'input_json': '{}', 'elapsed_ms': 10, 'checked': False, 'passed': None})
    assert run['origin'] == 'browser_teaching_run'
    assert run['verification'] == 'browser_reported_not_independently_verified'
    assert not marker.exists()


def test_rejected_generation_keeps_explicit_starter_and_old_versions(monkeypatch, generated):
    pid, node = fixture_node()
    original = model.structured
    def rejected(system, payload, budget, purpose, **kwargs):
        if purpose == 'practice_review':
            return {'accepted': False, 'issues': ['wrong source formula'], 'corrections': {}}
        return original(system, payload, budget, purpose, **kwargs)
    monkeypatch.setattr(model, 'structured', rejected)
    artifact = practice.generate(pid, node['id'])
    assert artifact['status'] == 'starter' and artifact['errors']
    assert artifact['origin'] == 'teaching_starter'
    assert len(artifact['versions']) == 2


def test_missing_model_does_not_claim_specialized_course(monkeypatch):
    pid, node = fixture_node()
    monkeypatch.setattr(model, 'available', lambda: False)
    value = practice.generate(pid, node['id'])
    assert value['status'] == 'starter'
    assert '尚未生成专属练习' in value['errors'][0]
    assert value['usage']['calls'] == 0


def test_unavailable_refresh_keeps_old_course_but_does_not_reuse_review_claim(monkeypatch, generated):
    pid, node = fixture_node()
    old = practice.generate(pid, node['id'])
    monkeypatch.setattr(model, 'available', lambda: False)
    new = practice.generate(pid, node['id'], refresh=True)
    assert new['status'] == 'starter' and new['id'] != old['id']
    assert new['quality']['review'] == 'not_generated'
    with store.connection(pid) as conn:
        practice.init(conn)
        assert practice.record(conn, pid, old['id'])['status'] == 'ready'


def test_versions_conflicts_changed_node_and_space_ownership(generated):
    pid, node = fixture_node()
    other, _ = fixture_node('Other space')
    value = practice.generate(pid, node['id'])
    practice.save_draft(pid, value['id'], 1, 'print(5)', '{}')
    with pytest.raises(HTTPException) as conflict:
        practice.save_draft(pid, value['id'], 1, 'print(6)', '{}')
    assert conflict.value.status_code == 409
    with store.connection(pid) as conn:
        changed = store.record(conn, 'kw_nodes', pid, node['id'])
        store.edit_record(conn, 'kw_nodes', pid, node['id'], changed['version'], {'summary': 'Updated fixture rule'})
    assert practice.get(pid, node['id'])['status'] == 'starter'
    with store.connection(other) as conn:
        practice.init(conn)
        with pytest.raises(HTTPException) as absent:
            practice.record(conn, other, value['id'])
        assert absent.value.status_code == 404


def test_http_validation_and_browser_result_do_not_trigger_generation(monkeypatch):
    pid, node = fixture_node()
    monkeypatch.setattr(model, 'structured', lambda *a, **k: pytest.fail('No generation requested'))
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        path = f'/api/projects/{pid}/knowledge/nodes/{node["id"]}/practice'
        value = client.get(path).json()
        assert client.post(path, json={'difficulty': 'expert'}).status_code == 422
        assert client.patch(f'/api/projects/{pid}/knowledge/practice/{value["id"]}', json={'expected_revision': 1, 'code': 'print(2)', 'input_json': 'invalid'}).status_code == 422
        result = client.post(f'/api/projects/{pid}/knowledge/practice/{value["id"]}/runs', json={'status': 'timeout', 'code': 'while True: pass', 'output': 'stopped', 'elapsed_ms': 5000})
        assert result.status_code == 201 and result.json()['status'] == 'timeout'
