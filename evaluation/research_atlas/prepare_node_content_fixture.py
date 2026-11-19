"""Export authored UI fixtures using the platform's actual teaching guide code.

No database, provider or network is used. Source passages, graph records and
saved lessons are synthetic test data, explicitly separate from user records.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / '.ui_validation' / 'node-content-20261117'


def main():
    sys.path.insert(0, str(ROOT / 'backend'))
    from app.knowledge.node_guides import get_guide

    pid = 'node-content-fixture'
    source_id = 'authored-source'

    def node(nid, label, summary, kind='concept'):
        return {
            'id': nid, 'project_id': pid, 'source_id': source_id,
            'label': label, 'summary': summary, 'kind': kind,
            'parent_id': None, 'origin': 'source', 'research_status': 'unspecified',
            'version': 1, 'hidden': False, 'source_missing': False,
            'evidence_ids': ['e-' + nid], 'metadata': {'semantic': True},
        }

    nodes = [
        node('self-attention', 'Self-attention',
             'Self-attention lets positions within one sequence use representations from other positions in that sequence.'),
        node('scaled-attention', '缩放点积注意力',
             '先计算query和key的点积，再除以键向量维度的平方根，经过softmax对value加权。', 'method'),
        node('dot-product', '向量点积', '同位置分量相乘求和，得到一个标量。'),
        node('research-design', '实验设计',
             '比较两种学习方式，需要记录学习时长、测试间隔和随机分配。', 'experiment'),
        node('unknown', 'Zeta桥', '自编未知主题：这个名称用于本次连通性记录。'),
        node('psychology', '选择性注意',
             '研究参与者对视觉目标的关注，记录反应时与正确率；这里的attention指心理过程。'),
    ]
    by_id = {item['id']: item for item in nodes}
    guides = {item['id']: get_guide(item) for item in nodes}
    assert guides['self-attention'] is not None
    assert guides['research-design'] is not None
    assert guides['unknown'] is None
    assert guides['psychology'] is None

    source = {
        'id': source_id, 'project_id': pid, 'asset_id': 'authored-asset',
        'version': 'authored-v1', 'title': '自编节点理解教学资料',
        'filename': 'node-learning.md', 'kind': 'report',
        'media_type': 'text/markdown', 'removed': False, 'created_at': '2026-11-17',
        'blocks': [
            {'id': 'b-' + item['id'], 'ordinal': index, 'kind': 'text',
             'heading': item['label'], 'text': item['summary'], 'page': None, 'metadata': {}}
            for index, item in enumerate(nodes)
        ],
        'knowledge_nodes': [
            {'id': item['id'], 'label': item['label'], 'kind': item['kind'],
             'block_ids': ['b-' + item['id']]}
            for item in nodes
        ],
    }
    evidence = {
        item['id']: {
            'id': 'e-' + item['id'], 'source_id': source_id,
            'source_title': source['title'], 'source_version': source['version'],
            'block_id': 'b-' + item['id'], 'quote': item['summary'], 'origin': 'source',
            'locator': {'heading': item['label'], 'ordinal': index},
        }
        for index, item in enumerate(nodes)
    }
    unrelated = {
        **evidence['self-attention'], 'id': 'e-foreign', 'source_id': 'foreign-source',
        'source_title': '另一份自编资料', 'block_id': 'b-foreign',
        'quote': '关联来源的条件不能充当当前概念的直接定义。',
    }
    edge_evidence = {
        **evidence['self-attention'], 'id': 'e-edge', 'block_id': 'b-edge',
        'quote': '自编关系摘录：该教学机制使用缩放点积评分。',
        'locator': {'heading': '关系说明', 'ordinal': len(nodes)},
    }
    source['blocks'].append({'id': 'b-edge', 'ordinal': len(nodes), 'kind': 'text',
                             'heading': '关系说明', 'text': edge_evidence['quote'],
                             'page': None, 'metadata': {}})

    def edge(eid, start, end, kind, label, explanation):
        return {'id': eid, 'project_id': pid, 'source_id': source_id,
                'source': start, 'target': end, 'kind': kind, 'label': label,
                'explanation': explanation, 'origin': 'source', 'version': 1,
                'hidden': False, 'source_missing': False, 'evidence_ids': ['e-edge'],
                'metadata': {}}

    edges = [
        edge('uses', 'self-attention', 'scaled-attention', 'USES', '使用',
             '在本教学图中，以缩放点积分数组织同一序列的信息汇聚。'),
        edge('prerequisite', 'dot-product', 'scaled-attention', 'PREREQUISITE_OF', '先修知识',
             '先理解点积分数，再看缩放和归一化。'),
        edge('related', 'unknown', 'self-attention', 'RELATED_TO', '相关',
             '仅用于验收未知主题的实际关系上下文。'),
    ]
    details = {}
    for item in nodes:
        adjacent = [value for value in edges if item['id'] in {value['source'], value['target']}]
        neighbor_ids = {endpoint for value in adjacent for endpoint in (value['source'], value['target'])} - {item['id']}
        details[item['id']] = {
            'node': item, 'neighbors': [by_id[nid] for nid in sorted(neighbor_ids)],
            'prerequisites': [by_id[value['source']] for value in adjacent
                              if value['kind'] == 'PREREQUISITE_OF' and value['target'] == item['id']],
            'suggested_foundations': [], 'edges': adjacent,
            'evidence': [evidence[item['id']]] + ([edge_evidence] if adjacent else [])
                        + ([unrelated] if item['id'] == 'self-attention' else []),
            'resources': [], 'demos': [], 'study_guide': guides[item['id']],
        }

    payload = {
        'source_kind': 'authored_teaching_material', 'api_stub': True,
        'guide_origin': 'actual app.knowledge.node_guides.get_guide',
        'model_stub': False, 'real_provider_calls': 0,
        'project': {'id': pid, 'version': 1, 'title': '节点内容验收（自编资料）',
                    'domain': 'custom', 'research_question': 'Self-attention怎样让序列中的位置交换信息？',
                    'status': 'active', 'constraints': {'version': 1, 'objective': '检查节点解释与原文上下文'},
                    'created_at': '2026-11-17', 'updated_at': '2026-11-17'},
        'source': source, 'nodes': by_id, 'details': details,
        'graph': {'nodes': nodes, 'edges': edges, 'total_nodes': len(nodes),
                  'total_edges': len(edges), 'truncated': False},
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / 'fixture.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'directory': str(OUTPUT), 'nodes': len(nodes),
                      'guided_topics': [key for key, value in guides.items() if value]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
