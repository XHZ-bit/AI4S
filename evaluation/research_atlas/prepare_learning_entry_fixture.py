"""Create the learning-entry acceptance through normal authored-source import."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import prepare_route_fixture as route


def prepare(directory: Path):
    route.DOCUMENT += '''

## 自注意力与多头组织
自注意力的查询、键和值来自同一序列，当前位置可参考掩码允许的其他位置。
多头注意力分别投影查询、键和值，在各头并行计算后拼接，再用输出投影组合信息。
'''
    route.DEFINITIONS = [*route.DEFINITIONS,
        ('self_attention', 'concept', 'Self-attention', '自注意力的查询、键和值来自同一序列'),
        ('multihead', 'method', 'Multi-Head Attention', '在各头并行计算后拼接，再用输出投影组合信息'),
    ]
    report = route.prepare(directory, source_kind='paper')
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        graph = client.get(f'/api/projects/{report["project_id"]}/knowledge/graph?limit=2000')
        graph.raise_for_status()
        root = next(node for node in graph.json()['nodes'] if node['kind'] == 'paper'
                    and node['source_id'] == report['source_id'])
        report['nodes']['root'] = root['id']
        report['labels'] = {key: label for key, _, label, _ in route.DEFINITIONS}
        report['labels']['root'] = root['label']
        report['purpose'] = 'learning_entry_and_recovery_acceptance'
    (directory / 'fixture.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    result = prepare(parser.parse_args().directory.resolve())
    print(json.dumps({'project_id': result['project_id'], 'nodes': result['nodes'],
                      'model_stub': True, 'real_provider_calls': 0}, ensure_ascii=False))
