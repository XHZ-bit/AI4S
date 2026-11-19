"""Source-independent lessons remain useful offline without becoming paper evidence."""

import json
import sqlite3

import pytest

from app.knowledge import extraction, learning, store, teaching
from app.knowledge.foundations import FOUNDATIONS


def test_attention_formula_matches_math_foundations_without_robot_branch_lesson():
    value = {'kind': 'formula', 'label': 'Multi-head attention',
             'summary': 'Scaled dot-product attention uses query and key vectors.',
             'metadata': {'latex': r'\operatorname{softmax}(QK^T/\sqrt{d_k})V'}}
    topics = learning.demos_for(value)
    assert {'scaled_attention', 'softmax', 'dot_product', 'probability'} <= set(topics)
    assert 'branches' not in topics
    cognitive = {'kind': 'concept', 'label': 'Sustained attention',
                 'summary': 'Volunteers performed an attention task for twenty minutes.', 'metadata': {}}
    assert 'scaled_attention' not in learning.demos_for(cognitive)


@pytest.mark.parametrize('kind,label,summary,expected', [
    ('formula', '向量内积', '点积分数', {'dot_product'}),
    ('experiment', '学习方式的实验设计', '随机分配受试者进入对照组，延迟回忆。', {'research_design', 'sampling'}),
    ('finding', '样本比例', 'Participants were sampled from a volunteer population.', {'sampling'}),
])
def test_foundations_enter_existing_graph_and_have_offline_lessons(kind, label, summary, expected):
    conn = sqlite3.connect(':memory:')
    try:
        store.init(conn)
        source = {'id': 's', 'project_id': 'p', 'asset_id': 'asset', 'version': 'v1',
                  'title': 'Uploaded study', 'filename': 'study.md', 'kind': 'paper', 'removed': False}
        conn.execute('INSERT INTO kw_sources VALUES(?,?,?,?,?)', ('s', 'p', 'asset', 0, store.encode(source)))
        store.put_parse(conn, 'asset', {'blocks': [{'text': summary, 'kind': 'text'}]})
        block = store.source_blocks(conn, 'asset')[0]
        eid = store.add_evidence(conn, 'p', source, block)
        node = store.put_record(conn, 'kw_nodes', extraction.node(source, 'target', kind, label, summary,
                                 [eid], metadata={'semantic': True}))
        learning.add_prerequisites(conn, 'p', source['id'])
        detail = learning.detail(conn, 'p', node['id'])
        lessons = {item['metadata']['demo']: item for item in detail['suggested_foundations']}
        assert expected <= lessons.keys()
        assert not detail['prerequisites']
        for topic in expected:
            artifact = learning.basic(conn, 'p', lessons[topic]['id'])
            assert artifact['sections'] == FOUNDATIONS[topic]['sections']
            assert artifact['origin'] == 'inference' and artifact['evidence'] == []
            assert artifact['usage'] == {}
        edges = [json.loads(row[0]) for row in conn.execute('SELECT data FROM kw_edges')]
        assert all(item['kind'] == 'SUPPLEMENTS' and item['evidence_ids'] == [] for item in edges)
    finally:
        conn.close()


def test_trusted_teaching_references_keep_all_requested_foundations_and_legacy_gating():
    references = teaching.references(['softmax', 'research_design', 'gating', 'unknown'])
    assert set(references) == {'softmax', 'research_design', 'gating'}
    assert '0.8668' in references['softmax']
    assert '随机分配' in references['research_design']
    assert '∂δ_in/∂z' in references['gating']
