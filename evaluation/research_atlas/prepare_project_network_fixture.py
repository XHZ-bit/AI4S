"""Prepare two isolated research projects for the project-network acceptance.

The first source follows the normal upload/parser/extraction pipeline with a
fixed HTTP model transport, via the existing authored route fixture. Additional
nodes use the public manual-node API. No semantic records are inserted directly
and the user's normal database is never opened.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from prepare_route_fixture import prepare as prepare_route


def prepare(directory: Path):
    directory = directory.resolve()
    original = prepare_route(directory)

    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        pid = original['project_id']
        response = client.patch(f'/api/projects/{pid}', json={
            'expected_version': client.get(f'/api/projects/{pid}').json()['version'],
            'title': '课题A · 注意力机制学习', 'research_question': '怎样组织本课题的知识、资料和个人记录？',
            'status': None, 'constraints': None,
        })
        response.raise_for_status()
        other = client.post('/api/projects', json={
            'title': '课题B · 独立样本研究', 'domain': 'custom',
            'research_question': '怎样区分这个课题的个人知识？',
            'constraints': {'version': 1, 'objective': '隔离工程验收；全部材料自编'},
        })
        other.raise_for_status()
        other_pid = other.json()['id']
        manual = client.post(f'/api/projects/{other_pid}/knowledge/nodes', json={
            'label': '课题B专有节点', 'kind': 'concept', 'summary': '这条个人记录只属于课题B，用于核验项目隔离。',
        })
        manual.raise_for_status()
        other_node = manual.json()['node']
        a_graph = client.get(f'/api/projects/{pid}/knowledge/graph', params={'limit': 2000})
        a_graph.raise_for_status()
        assert other_node['id'] not in {node['id'] for node in a_graph.json()['nodes']}
        graph = a_graph.json()
        root = f'/api/projects/{pid}/knowledge/nodes/{original["nodes"]["goal"]}/materials'
        assert client.get(root).json()['items'] == [], 'Use a clean materials fixture'
        report = {
            **original,
            'project_title': '课题A · 注意力机制学习',
            'other_project_id': other_pid,
            'other_project_title': '课题B · 独立样本研究',
            'other_node': other_node,
            'initial_graph_node_ids': [node['id'] for node in graph['nodes']],
            'initial_graph_edges': [{key: edge[key] for key in ('id', 'source', 'target', 'kind')} for edge in graph['edges']],
            'attachment_filename': '节点补充资料.md',
            'attachment_title': '自编节点补充资料',
            'attachment_text': '# 自编节点补充资料\n\n这份附件说明记录如何与当前节点关联。\n\n用户可以保存个人解释，再次点击节点时继续查看。\n',
            'manual_node_label': '课题A手工知识节点',
            'manual_node_summary': '这是通过正常界面添加的个人知识，供后续整理与修订。',
        }
    (directory / report['attachment_filename']).write_text(report['attachment_text'], encoding='utf-8')
    (directory / 'fixture.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    result = prepare(parser.parse_args().directory)
    print(json.dumps({key: result[key] for key in ('project_id', 'other_project_id', 'model_stub', 'real_provider_calls')}, ensure_ascii=False))
