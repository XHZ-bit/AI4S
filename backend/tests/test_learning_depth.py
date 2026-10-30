"""Research learning must be goal-scoped, substantive and source-preserving."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.knowledge import router
from app.db import projects
from app.db.sqlite import connect
from app.knowledge import extraction, learning, model, sources, store
from app.models.research import ResearchProjectCreate


def fixture_node():
    conn = connect()
    try:
        pid = projects.create_project(conn, ResearchProjectCreate(title="Learning depth fixture", domain="custom",
            research_question="Explain a source-backed scale function", constraints={"version": 1, "objective": "Understand calculation"})).id
    finally:
        conn.close()
    src = sources.ingest(pid, b"# Scale\n\ny = 2*x for scalar x.", "scale.md", "report")
    with store.connection(pid) as conn:
        store.put_parse(conn, src['asset_id'], {"blocks": [{"kind": "text", "text": "The fixture defines y = 2*x for scalar input x.", "metadata": {}}]})
        block = store.source_blocks(conn, src['asset_id'])[0]
        eid = store.add_evidence(conn, pid, src, block)
        node = extraction.node(src, "scale", "method", "Scale function", "Compute a scalar output from a scalar input.", [eid], metadata={"semantic": True})
        store.put_record(conn, 'kw_nodes', node)
    return pid, src, node


def complete_sections():
    return {
        'overview': '这是教学资料中的标量变换，输入x经过乘以常数2得到输出y。它说明信息如何从输入到输出，而不是实际论文实验。' * 3,
        'definition': 'x与y均为标量，系数2是来源明确给出的常数，既不是待训练参数也不是张量维度。原文没有规定物理单位，因此不推断单位。' * 3,
        'derivation': '步骤1：从定义 y=2x 开始。步骤2：代入教学输入x=3，计算y=2*3=6。步骤3：对于x=0得到y=0，对于负值x=-1得到y=-2。这个例子只说明线性映射，不构成真实研究实验或性能结果。' * 4,
        'prerequisites': '前置知识是标量乘法，乘数2作用于同一个输入；理解此规则即可复核中间计算。' * 3,
        'implementation': '当前方法源码未提供。以下只能讨论教学伪代码：输入标量x，返回2*x。用于说明计算对应关系，不能冒充真实仓库实现。' * 4,
        'limitations': '这一计算仅适用于资料明确给出的标量线性规则；不能直接将它解释为高维网络、控制器或随机策略。若输入不是数值标量，现有定义没有给出行为。' * 3,
    }


@pytest.fixture
def generated(monkeypatch):
    calls = []
    monkeypatch.setattr(model, 'available', lambda: True)
    monkeypatch.setattr(learning, 'discover_resources', lambda pid, node, initial: initial)
    monkeypatch.setattr(learning, 'fetch_resources', lambda pid, resources: resources)
    def structured(system, payload, budget, purpose, **kwargs):
        calls.append((purpose, payload))
        budget.calls += 1
        budget.usage['calls'] += 1
        assert budget.limit == 4 and budget.calls <= 4
        if purpose == 'learning_review':
            return {'accepted': True, 'issues': [], 'corrections': {}}
        return {'sections': complete_sections(), 'evidence_ids': [payload['sources'][0]['id']]}
    monkeypatch.setattr(model, 'structured', structured)
    return calls


def test_goal_depth_variants_are_independent_resumable_and_do_not_erase_manual_sections(generated):
    pid, src, node = fixture_node()
    first = learning.generate(pid, node['id'], goal='Understand scalar flow', depth='deep')
    assert first['status'] == 'ready' and first['coverage']['status'] == 'complete'
    learning.revise(pid, node['id'], first['revision'], {'derivation': 'User supplied derivation'}, goal=first['goal'], depth='deep')
    second = learning.generate(pid, node['id'], goal='Compare a boundary input', depth='standard')
    assert second['goal'] != first['goal'] and second['sections']['derivation'] != 'User supplied derivation'
    with store.connection(pid) as conn:
        assert learning.get_learning(conn, pid, node['id'])['goal'] == second['goal']
        restored = learning.get_learning(conn, pid, node['id'], first['goal'], 'deep')
        assert restored['sections']['derivation'] == 'User supplied derivation'
        assert len(restored['variants']) == 2
    assert generated[0][1]['goal'] == first['goal']


def test_shallow_or_empty_generated_sections_are_partial_even_when_source_review_accepts(generated, monkeypatch):
    pid, src, node = fixture_node()
    original = model.structured
    def shallow(system, payload, budget, purpose, **kwargs):
        value = original(system, payload, budget, purpose, **kwargs)
        if purpose != 'learning_review':
            value['sections'] = {key: 'Short definition' if key == 'overview' else '' for key in complete_sections()}
        return value
    monkeypatch.setattr(model, 'structured', shallow)
    result = learning.generate(pid, node['id'])
    assert result['status'] == 'partial'
    assert '逐步推导或机制解释' in result['coverage']['missing']
    assert result['usage']['calls'] <= 4


def test_failed_refresh_retains_prior_deep_content_and_records_failure(generated, monkeypatch):
    pid, src, node = fixture_node()
    first = learning.generate(pid, node['id'])
    monkeypatch.setattr(model, 'available', lambda: False)
    failed = learning.generate(pid, node['id'], refresh=True)
    assert failed['status'] == 'partial'
    assert failed['sections'] == first['sections']
    assert failed['retained_from']['id'] == first['id']
    assert failed['quality']['last_attempt'] == 'failed_previous_content_retained'
    with store.connection(pid) as conn:
        assert learning.get_learning(conn, pid, node['id'])['sections'] == first['sections']


def test_unrelated_source_and_node_do_not_invalidate_but_dependency_edit_does(generated):
    pid, src, node = fixture_node()
    learning.generate(pid, node['id'])
    other = sources.ingest(pid, b'Unrelated independent source', 'unrelated.txt', 'report')
    with store.connection(pid) as conn:
        independent = extraction.node(other, 'other', 'concept', 'Other knowledge', 'Not a dependency', [], metadata={'semantic': True})
        store.put_record(conn, 'kw_nodes', independent)
        assert not learning.get_learning(conn, pid, node['id'])['stale']
        prereq = extraction.node(src, 'pre', 'concept', 'Scalar multiply', 'How multiplication works', node['evidence_ids'], parent_id=node['id'])
        store.put_record(conn, 'kw_nodes', prereq)
        edge = extraction.edge(src, prereq['id'], node['id'], 'PREREQUISITE_OF', 'helps', 'Explicit teaching dependency', node['evidence_ids'])
        store.put_record(conn, 'kw_edges', edge)
        assert learning.get_learning(conn, pid, node['id'])['stale']


def test_explicit_linked_fetched_code_is_available_from_a_report_node(generated):
    pid, src, node = fixture_node()
    code = sources.ingest(pid, b'def scale(x):\n    return 2*x\n', 'policy.py', 'code')
    with store.connection(pid) as conn:
        store.put_parse(conn, code['asset_id'], {'blocks': [{'kind': 'code', 'text': 'def scale(x):\n    return 2*x', 'metadata': {'path': 'policy.py', 'start_line': 1, 'end_line': 2}}]})
        block = store.source_blocks(conn, code['asset_id'])[0]
        eid = store.add_evidence(conn, pid, code, block)
        implementation = extraction.node(code, 'fn', 'code', 'scale', 'Actual provided code', [eid])
        store.put_record(conn, 'kw_nodes', implementation)
        store.put_record(conn, 'kw_edges', extraction.edge(src, implementation['id'], node['id'], 'IMPLEMENTS', 'implements', 'Provided function implements fixture', [eid]))
    result = learning.generate(pid, node['id'])
    payload = generated[0][1]
    assert payload['current_source']['kind'] == 'report'
    assert payload['current_source']['implementation_code_supplied'] is True
    assert payload['linked_implementations'][0]['id'] == code['id']
    assert result['context_summary']['linked_code_sources'][0]['version'] == code['version']


def test_curated_content_is_retained_with_new_material_instead_of_overwriting_it():
    previous = {'sections': {'derivation': 'Source-checked derivation'}, 'curated_sections': ['derivation'], 'revision': 4}
    current = {'sections': {'derivation': 'New step-by-step numeric explanation'}}
    learning._preserve_learning_edits(current, previous)
    assert current['sections']['derivation'].startswith(previous['sections']['derivation'])
    assert 'New step-by-step' in current['sections']['derivation']


def test_http_goal_depth_validation_and_old_get_contract(generated):
    pid, src, node = fixture_node()
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        path = f'/api/projects/{pid}/knowledge/nodes/{node["id"]}/learning'
        assert client.get(path).json()['status'] == 'basic'
        assert client.post(path, json={'depth': 'unknown'}).status_code == 422
        result = client.post(path, json={'goal': 'Check an example', 'depth': 'deep'}).json()
        assert result['goal'] == 'Check an example' and result['status'] == 'ready'
        assert client.get(path).json()['goal'] == result['goal']
        assert client.get(path, params={'goal': 'Other question', 'depth': 'standard'}).json()['status'] == 'basic'


def test_model_context_budget_drops_peripheral_text_but_keeps_linked_code():
    from app.knowledge.learning_depth import bounded_payload
    payload = {'sources': [{'id': 'own', 'quote': 'Definition ' * 100}, {'id': 'code', 'quote': 'def scale(x): return 2*x'}]
               + [{'id': str(i), 'quote': 'Extra context ' * 500} for i in range(8)],
               'external_resources': [{'content': 'Peripheral resource ' * 500}],
               'linked_implementations': [{'evidence_ids': ['code']}],
               'prerequisite_graph': {'nodes': [{'summary': 'Prior explanation ' * 1000}]}}
    result = bounded_payload(payload, 'System instructions', maximum=14000)
    assert len(json.dumps(model.structured_request('System instructions', result), ensure_ascii=False)) <= 14000
    assert 'code' in {e['id'] for e in result['sources']} and result['context_truncated']


@pytest.mark.parametrize('purpose,max_tokens', [('node_learning', 10000), ('learning_review', 8000)])
def test_nested_request_budget_keeps_complete_initializer_and_review_sections(purpose, max_tokens, monkeypatch):
    from app.config import get_settings
    from app.knowledge.learning_depth import bounded_payload
    monkeypatch.setenv('LLM_MODEL', 'qwen3.8-flash')
    get_settings.cache_clear()
    code = 'def __init__(self):\n    self.log_std = Parameter(zeros(3))\n' + r'    path = "C:\\public\\code" # $\mu_{i}$' * 90
    peripheral = [{'id': f'extra-{i}', 'source_id': 'repo', 'quote': (r'辅助上下文 "quoted" \\beta' + '\n') * 120}
                  for i in range(12)]
    sources = [{'id': 'current', 'source_id': 'repo', 'quote': 'def update(self): return self.std'},
               {'id': 'init', 'source_id': 'repo', 'quote': code,
                'code_scope': {'symbol': 'Policy.__init__', 'complete': True}}, *peripheral]
    payload = {'sources': sources, 'external_resources': [{'content': '外部资料' * 500}],
               'linked_implementations': [{'id': 'repo', 'evidence_ids': [s['id'] for s in sources],
                                           'locations': [{'line': i} for i in range(len(sources))]}]}
    if purpose == 'learning_review':
        payload['sections'] = {key: (r'中文推导 $\beta(x)$ "quoted" ' + '\n') * 25 for key in complete_sections()}
    original = json.dumps(payload, ensure_ascii=False)
    system = '中文教学及数学转义：' + r'\pi(a\mid s)' * 30
    result = bounded_payload(payload, system, maximum=26000, max_tokens=max_tokens)
    request = model.structured_request(system, result, max_tokens=max_tokens)
    assert request['enable_thinking'] is False and request['max_tokens'] == max_tokens
    assert len(json.dumps(request, ensure_ascii=False)) <= 26000
    assert next(s for s in result['sources'] if s['id'] == 'init')['quote'] == code
    assert result['context_truncated']
    assert json.dumps(payload, ensure_ascii=False) == original
    assert result.get('sections') == payload.get('sections')
    retained = {s['id'] for s in result['sources']}
    assert set(result['linked_implementations'][0]['evidence_ids']) == retained


def test_request_budget_rejects_when_essential_code_alone_cannot_fit():
    from app.knowledge.learning_depth import bounded_payload
    payload = {'sources': [{'id': 'current', 'quote': 'Necessary complete source ' * 1000}]}
    with pytest.raises(model.ModelUnavailable, match='必要依据超过输入预算'):
        bounded_payload(payload, 'System', maximum=1000)


def test_related_function_keeps_initializer_tail_in_model_context_without_rewriting_quote():
    from app.knowledge.learning_depth import model_sources
    pid, src, node = fixture_node()
    code = sources.ingest(pid, b'class Policy: pass', 'policy.py', 'code')
    initializer = 'def __init__(self):\n' + '    # retained source detail\n' * 150 + '    self.std = Parameter(ones(3))\n'
    current = 'def update(self, observations):\n    self.distribution = Normal(self.actor(observations), self.std)\n'
    with store.connection(pid) as conn:
        store.put_parse(conn, code['asset_id'], {'blocks': [
            {'kind': 'code', 'text': initializer, 'metadata': {'symbol': 'Policy.__init__', 'symbol_kind': 'function', 'start_line': 1, 'end_line': 153, 'path': 'policy.py'}},
            {'kind': 'code', 'text': current, 'metadata': {'symbol': 'Policy.update', 'symbol_kind': 'function', 'start_line': 155, 'end_line': 157, 'path': 'policy.py'}}]})
        blocks = store.source_blocks(conn, code['asset_id'])
        eid = store.add_evidence(conn, pid, code, blocks[1])
        target = extraction.node(code, 'update', 'code', 'Policy.update', 'Build the distribution', [eid], metadata={'block_id': blocks[1]['id']})
        store.put_record(conn, 'kw_nodes', target)
        context = learning.related_source_context(conn, pid, target)
        init = next(item for item in context if item.get('code_context', {}).get('symbol') == 'Policy.__init__')
        assert 'self.std =' not in init['quote']
        model_init = next(item for item in model_sources(context) if item['id'] == init['id'])
        assert model_init['quote'] == initializer and model_init['code_scope']['complete']
        stored = json.loads(conn.execute('SELECT data FROM kw_evidence WHERE id=?', (init['id'],)).fetchone()[0])
        assert stored['quote'] == init['quote']  # citation/history still unchanged


@pytest.mark.parametrize('bad', ['\\beta'.replace('\\b', '\x08'), '$\\theta$'.replace('\\t', '\t'), '$x\ry$', '$x\ny$'])
def test_control_characters_cannot_pass_coverage_or_render_as_correct_math(bad):
    from app.knowledge.learning_depth import coverage, rendering_issues, safe_presentation
    sections = complete_sections()
    sections['prerequisites'] = bad
    original = dict(sections)
    assert rendering_issues(sections)
    result = coverage(sections, {'kind': 'method'}, prerequisites=[{'id': 'p'}])
    assert result['status'] == 'partial' and '公式与文本格式' in result['missing']
    projected = safe_presentation({'sections': sections, 'status': 'ready', 'coverage': result, 'errors': []})
    assert projected['status'] == 'partial' and projected['sections']['prerequisites'] == ''
    assert projected['sections']['derivation'] == original['derivation'] and sections == original


def test_escaped_latex_and_normal_code_indentation_are_not_misclassified():
    from app.knowledge.learning_depth import rendering_issues
    assert not rendering_issues({'derivation': r'$\beta(s)$ and $\pi(a\mid s)$', 'implementation': '```python\n\treturn x\n```'})
