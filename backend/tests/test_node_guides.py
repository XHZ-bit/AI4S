"""Offline authored guides add understanding without changing source claims."""

import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.knowledge import extraction, learning, model, sources, store
from app.knowledge.node_guides import VERSION, get_guide


def node(label, summary='', kind='concept', **metadata):
    return {'kind': kind, 'label': label, 'summary': summary, 'metadata': metadata}


def test_self_attention_explains_source_roles_masks_and_a_hand_checkable_example():
    original = node('Self-attention', 'Self-attention relates positions of a single sequence.')
    before = deepcopy(original)
    guide = get_guide(original)
    assert guide['origin'] == 'authored_teaching' and guide['version'] == VERSION
    assert guide['topic'] == 'self_attention'
    assert '同一序列' in guide['overview'] and '只能看自己' in guide['overview']
    flow = '\n'.join(item['text'] for item in guide['flow'])
    assert '不同投影' in flow and '因果掩码' in flow and '多头' in flow
    assert '交叉注意力' in str(guide['common_confusions'])
    assert '0.75\\times2+0.25\\times6=3' in guide['example']['body']
    assert 0.75 * 2 + 0.25 * 6 == 3
    assert guide['demo_ids'] == []  # A general self-attention node does not assert a particular scoring rule.
    assert 'evidence' not in guide and 'source_id' not in guide
    assert original == before
    guide['flow'][0]['text'] = 'An edited frontend copy'
    assert get_guide(original)['flow'][0]['text'] != 'An edited frontend copy'


@pytest.mark.parametrize('value,topic', [
    (node('Self‑Attention'), 'self_attention'),
    (node('自注意力'), 'self_attention'),
    (node('Multi‑Head Attention', 'Used with self-attention and scaled dot-product scoring.'), 'multi_head_attention'),
    (node('多头注意力', kind='module'), 'multi_head_attention'),
    (node('Cross-attention', 'Unlike self-attention, Q comes from a different sequence.'), 'cross_attention'),
    (node('Encoder-decoder attention'), 'cross_attention'),
    (node('Scaled dot-product attention', 'Used in self-attention.'), 'scaled_attention'),
    (node('Softmax', 'Scaled dot-product attention uses this step.'), 'softmax'),
    (node('向量点积', 'Used before attention softmax.'), 'dot_product'),
    (node('概率与频率'), 'probability'),
    (node('实验设计', '比较反复阅读与回忆的延迟结果。', kind='experiment'), 'research_design'),
    (node('样本量与总体'), 'sampling'),
    (node('公式（1）', kind='formula', latex=r'\operatorname{softmax}(QK^T/\sqrt{d_k})V'), 'scaled_attention'),
    (node('实验一', 'Random assignment to a control group.', kind='experiment'), 'research_design'),
])
def test_specific_node_topics_take_precedence_over_mentions_in_context(value, topic):
    guide = get_guide(value)
    assert guide['topic'] == topic
    assert all(guide[key] for key in ('overview', 'why_it_matters', 'flow', 'example', 'key_points',
                                      'common_confusions', 'questions', 'boundary'))
    assert guide['origin'] == 'authored_teaching'


@pytest.mark.parametrize('value', [
    node('Sustained attention', 'Volunteers performed an attention task for twenty minutes.'),
    node('Self-focused attention', 'A psychological measure about personal thoughts.'),
    node('注意力', '参与者完成认知任务。'),
    node('Gaussian action sampling', 'Sample an action from a normal distribution.'),
    node('投影模块', 'Multiple projections are used in multi-head attention.'),
    node('查询模块', 'This module is contrasted with cross-attention.'),
    node('变量', 'Q和K是两个输入表示。'),
    node('随机实验记录', 'ordinary description', heading='self-attention'),
    node('Self-attention', structural=True),
])
def test_unrelated_or_ambiguous_labels_do_not_receive_a_neural_attention_lesson(value):
    assert get_guide(value) is None


def test_multihead_and_cross_attention_keep_distinct_shapes_and_checkable_examples():
    multihead = get_guide(node('Multi-Head Attention'))
    cross = get_guide(node('Cross-Attention'))
    assert multihead['demo_ids'] == cross['demo_ids'] == []
    assert '拼接' in multihead['overview'] and '输出投影' in str(multihead['flow'])
    assert '[3,10]' in multihead['example']['body']
    assert [3 * 1 + 5 * 0, 3 * 0 + 5 * 2] == [3, 10]
    assert '序列长度不必相同' in str(cross['flow'])
    assert '28' in cross['example']['body'] and .2 * 10 + .3 * 20 + .5 * 40 == 28
    assert '本页' in multihead['boundary'] and '教学输入' in cross['example']['body']
    assert 'evidence' not in multihead and 'source_id' not in cross


@pytest.mark.parametrize('title', ['My original paper', 'Attention paper',
                                  'Attention Is All You Need: A Survey', 'Notes on Attention Is All You Need'])
def test_paper_reading_outline_never_turns_a_title_or_summary_into_extracted_findings(title):
    value = node(title, '已保存的论文', kind='paper')
    before = deepcopy(value)
    guide = get_guide(value)
    assert guide['kind'] == 'reading_outline' and guide['topic'] == 'paper_reading'
    assert guide['origin'] == 'authored_teaching'
    assert '输入、关键操作和输出' in str(guide['flow'])
    assert '原文位置' in str(guide['key_points'])
    assert title not in guide['overview'] and '已保存的论文' not in str(guide)
    assert '当前论文结果的概括' in guide['example']['body']
    assert guide['references'] == [] and 'evidence' not in guide
    assert value == before


def test_canonical_transformer_outline_matches_only_its_exact_normalized_title():
    guide = get_guide(node(' Attention is All\n you Need ', '已保存的论文', kind='paper'))
    assert guide['topic'] == 'transformer_paper' and guide['kind'] == 'reading_outline'
    assert 'Figure 1' in str(guide['flow']) and '§3.2.2' in str(guide['flow'])
    assert '4.0' in guide['example']['body'] and 'softmax之前' in guide['example']['body']
    assert 8 / (4 ** .5) == 4
    assert guide['references'][0]['url'] == 'https://arxiv.org/abs/1706.03762v7'
    guide['flow'][0]['text'] = 'Changed copy'
    assert get_guide(node('Attention Is All You Need', kind='paper'))['flow'][0]['text'] != 'Changed copy'


@pytest.mark.parametrize('change', [{'hidden': True}, {'source_missing': True}, {'quality_status': 'disputed'},
                                   {'metadata': {'source_withdrawn': True}}])
def test_unavailable_paper_never_receives_a_current_reading_outline(change):
    assert get_guide({**node('Attention Is All You Need', kind='paper'), **change}) is None


@pytest.fixture
def guide_case(monkeypatch):
    monkeypatch.setattr(model, 'structured', lambda *a, **k: pytest.fail('Guide reads must not call a model'))
    monkeypatch.setattr(sources, 'download', lambda *a, **k: pytest.fail('Guide reads must not fetch external material'))
    with TestClient(app) as client:
        payload = {'title': 'Node content', 'domain': 'custom', 'research_question': '理解自注意力',
                   'constraints': {'version': 1, 'objective': '理解信息来源'}}
        pid = client.post('/api/projects', json=payload).json()['id']
        other = client.post('/api/projects', json={**payload, 'title': 'Other space'}).json()['id']
        text = 'Self-attention relates different positions of a single sequence to compute its representation.'
        source = sources.ingest(pid, ('# Self-attention\n' + text).encode(), 'attention.md')
        with store.connection(pid) as conn:
            store.put_parse(conn, source['asset_id'], {'blocks': [{'kind': 'text', 'text': text}]})
            block = store.source_blocks(conn, source['asset_id'])[0]
            eid = store.add_evidence(conn, pid, source, block)
            value = store.put_record(conn, 'kw_nodes', extraction.node(source, 'self-attention', 'concept',
                                     'Self-attention', text, [eid], metadata={'semantic': True}))
        yield client, pid, other, source, value, block


def test_detail_read_adds_an_optional_guide_without_creating_a_lecture_or_rewriting_source(guide_case):
    client, pid, other, _, value, _ = guide_case
    with store.connection(pid) as conn:
        before = conn.execute('SELECT data FROM kw_nodes WHERE id=?', (value['id'],)).fetchone()[0]
        evidence_before = conn.execute('SELECT data FROM kw_evidence').fetchall()
    response = client.get(f'/api/projects/{pid}/knowledge/nodes/{value["id"]}')
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail['study_guide']['topic'] == 'self_attention'
    assert detail['node']['summary'] == value['summary']
    assert detail['evidence'][0]['quote'] == value['summary']
    assert detail['prerequisites'] == [] and detail['edges'] == []
    with store.connection(pid) as conn:
        assert conn.execute('SELECT COUNT(*) FROM kw_learning').fetchone()[0] == 0
        assert conn.execute('SELECT data FROM kw_nodes WHERE id=?', (value['id'],)).fetchone()[0] == before
        assert conn.execute('SELECT data FROM kw_evidence').fetchall() == evidence_before
        assert conn.execute('SELECT COUNT(*) FROM kw_model_calls').fetchone()[0] == 0
    assert client.get(f'/api/projects/{other}/knowledge/nodes/{value["id"]}').status_code == 404


@pytest.mark.parametrize('label,kind,topic', [('Multi-Head Attention', 'module', 'multi_head_attention'),
                                           ('Attention Is All You Need', 'paper', 'transformer_paper'),
                                           ('My original paper', 'paper', 'paper_reading')])
def test_other_guides_are_read_only_and_do_not_mark_deep_learning_as_ready(guide_case, label, kind, topic):
    client, pid, _, _, value, _ = guide_case
    with store.connection(pid) as conn:
        current = store.record(conn, 'kw_nodes', pid, value['id'])
        current.update({'label': label, 'kind': kind, 'summary': '已保存的论文' if kind == 'paper' else 'Multiple projections.'})
        store.put_record(conn, 'kw_nodes', current, authoritative_fields=('label', 'kind', 'summary'))
        before = conn.execute('SELECT data FROM kw_nodes WHERE id=?', (value['id'],)).fetchone()[0]
    response = client.get(f'/api/projects/{pid}/knowledge/nodes/{value["id"]}')
    assert response.status_code == 200
    assert response.json()['study_guide']['topic'] == topic
    assert response.json()['node']['summary'] == current['summary']
    with store.connection(pid) as conn:
        assert conn.execute('SELECT COUNT(*) FROM kw_learning').fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM kw_model_calls').fetchone()[0] == 0
        assert conn.execute('SELECT data FROM kw_nodes WHERE id=?', (value['id'],)).fetchone()[0] == before


def test_ready_personal_explanation_and_user_revisions_remain_independent_from_the_guide(guide_case):
    client, pid, _, _, value, _ = guide_case
    with store.connection(pid) as conn:
        artifact = learning.basic(conn, pid, value['id'])
        artifact.update({'status': 'ready', 'revision': 3, 'user_edited_sections': ['overview'], 'origin': 'user'})
        artifact['sections']['overview'] = '我的解释：先确定查询与键值分别来自哪里，再查看掩码。'
        fingerprint = learning.learning_fingerprint(conn, pid, value['id'])
        encoded = store.encode(artifact)
        conn.execute('INSERT INTO kw_learning VALUES(?,?,?,?)', (pid, value['id'], fingerprint, encoded))
    detail = client.get(f'/api/projects/{pid}/knowledge/nodes/{value["id"]}').json()
    saved = client.get(f'/api/projects/{pid}/knowledge/nodes/{value["id"]}/learning').json()
    assert detail['study_guide']['origin'] == 'authored_teaching'
    assert saved['sections']['overview'] == artifact['sections']['overview']
    assert saved['user_edited_sections'] == ['overview'] and saved['revision'] == 3
    with store.connection(pid) as conn:
        assert conn.execute('SELECT data FROM kw_learning WHERE node_id=?', (value['id'],)).fetchone()[0] == encoded


@pytest.mark.parametrize('change', ['source_version', 'source_removed', 'unlocatable_quote', 'hidden', 'disputed'])
def test_unavailable_source_or_evidence_does_not_add_a_current_teaching_guide(guide_case, change):
    client, pid, _, source, value, block = guide_case
    with store.connection(pid) as conn:
        if change == 'source_version':
            store.update_source(conn, pid, source['id'], {'version': 'new-version'})
        elif change == 'source_removed':
            store.update_source(conn, pid, source['id'], {'removed': True})
        elif change == 'unlocatable_quote':
            conn.execute('UPDATE kw_blocks SET data=? WHERE id=?', (store.encode({**block, 'text': 'Different passage'}), block['id']))
        else:
            current = json.loads(conn.execute('SELECT data FROM kw_nodes WHERE id=?', (value['id'],)).fetchone()[0])
            current['hidden' if change == 'hidden' else 'quality_status'] = True if change == 'hidden' else 'disputed'
            store.put_record(conn, 'kw_nodes', current, authoritative_fields=('hidden', 'quality_status'))
    response = client.get(f'/api/projects/{pid}/knowledge/nodes/{value["id"]}')
    assert response.status_code == 200
    assert response.json()['study_guide'] is None
    assert response.json()['node']['summary'] == value['summary']
