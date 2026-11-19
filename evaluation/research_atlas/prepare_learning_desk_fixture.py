"""Normal-import long evidence and API-authored math for learning-desk checks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from prepare_learning_entry_fixture import prepare as prepare_entry
from serve_learning_entry_fixture import create_app

ALIGNED = r'''\begin{aligned}
\mathrm{head}_i &= \mathrm{Attention}(QW_i^Q,KW_i^K,VW_i^V) \\
\mathrm{MultiHead}(Q,K,V) &= \mathrm{Concat}(\mathrm{head}_1,\dots,\mathrm{head}_h)W^O
\end{aligned}'''
NESTED = r'''\begin{aligned}
A &= \begin{bmatrix}1&2\\3&4\end{bmatrix} \\
z &= Aq
\end{aligned}'''
INVALID = r'\begin{aligned}x &= \unsupportedTeachingMacro{y}\end{aligned}'
DOCUMENT = '# 自编长证据教学资料：注意力核对\n\n'
for number in range(1, 17):
    DOCUMENT += f'## 教学依据 {number}\n\n本节教学片段{number}：' + (
        '缩放点积注意力先比较查询与键，再按键向量维度缩放分数，沿候选轴归一化，最后对值向量加权求和。'
        '本节只用固定教学输入解释中间计算；原文位置、输入条件和个人判断需要分别保存。'
        '若只有归一化权重而没有V，不能直接报告最终注意力输出。' * 6) + '\n\n'
DOCUMENT += '\n## 公式原文回看\n\n以下为教学公式，供浏览器检查显示与回到原文。\n\n' + ALIGNED + '\n\n'
DOCUMENT += '以下表达故意使用不存在的宏，只用于测试无法渲染时能否保留原样回看，不是正确公式：\n\n' + INVALID + '\n'


def prepare(directory: Path):
    directory = directory.resolve()
    original = prepare_entry(directory)
    import httpx
    from fastapi.testclient import TestClient
    from app.main import app
    from app.knowledge import model, service, store
    from app.knowledge.parser import parse_source

    model_calls = []
    real_client = httpx.Client

    def transport(request):
        payload = json.loads(json.loads(request.content)['messages'][1]['content'])
        matches = [block for block in payload.get('blocks', []) if '本节教学片段' in block['text']][:6]
        nodes = [{'key': 'long-evidence', 'kind': 'method', 'label': '缩放点积注意力：长证据核对',
                  'summary': '先按键向量维度缩放点积分数，再沿候选轴归一化；将多处教学依据与个人判断分别核对。',
                  'evidence': [{'block_id': block['block_id'], 'quote': block['text'][:1800]} for block in matches]}] if matches else []
        model_calls.append({'purpose': 'long_evidence_extraction', 'citations': len(matches)})
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps({'nodes': nodes, 'edges': []}, ensure_ascii=False)}}],
                                        'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}})

    def enqueue(pid, sid, retry=False):
        with store.connection(pid) as conn:
            run, fresh = store.create_run(conn, pid, sid)
        if fresh:
            service.analyze(pid, sid, run['id'], retry)
        with store.connection(pid) as conn:
            return store.run(conn, pid, run['id'])

    with TestClient(app) as client, patch.object(model, 'available', lambda: True), \
            patch.object(model.httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(transport), **kwargs)), \
            patch.object(service, 'parse_file', lambda file, kind, check: parse_source(file, kind, use_docling=False)), \
            patch.object(service, 'enqueue', enqueue):
        filename = 'authored-long-evidence.md'
        (directory / filename).write_text(DOCUMENT, encoding='utf-8')
        response = client.post(f'/api/projects/{original["project_id"]}/sources', data={'kind': 'paper'},
                               files={'file': (filename, DOCUMENT.encode(), 'text/markdown')})
        response.raise_for_status()
        source = response.json()['source']
        graph = client.get(f'/api/projects/{original["project_id"]}/knowledge/graph?source_id={source["id"]}&limit=2000').json()
        nodes = [node for node in graph['nodes'] if node.get('metadata', {}).get('semantic')]
        selected = max(nodes, key=lambda node: len(node['evidence_ids']))
        assert len(selected['evidence_ids']) >= 4

    fixed_app = create_app(directory)
    with TestClient(fixed_app) as client:
        project = client.get('/api/projects/' + original['project_id']).json()
        path = f'/api/projects/{original["project_id"]}/knowledge/nodes/{selected["id"]}/learning'
        saved = client.post(path, json={'goal': project['research_question'], 'depth': 'standard'}).json()
        assert saved['status'] == 'ready', saved.get('errors')
        derivation = ('以下为人工核对的教学公式，分别检查各头、拼接与输出投影。\n\n' + ALIGNED
                      + '\n\n嵌套矩阵的教学例：\n\n' + NESTED
                      + '\n\n以下测试表达无法按正确公式使用，需查看保存的原样文本与原文：\n\n' + INVALID)
        revised = client.patch(path, json={'expected_revision': saved['revision'], 'goal': saved['goal'],
                                          'depth': saved['depth'], 'sections': {'derivation': derivation}})
        revised.raise_for_status()
        secondary = client.post(f'/api/projects/{original["project_id"]}/knowledge/nodes/{original["nodes"]["multihead"]}/learning',
                                json={'goal': project['research_question'], 'depth': 'standard'})
        secondary.raise_for_status()
        assert secondary.json()['status'] == 'ready'
        report = {**original, 'purpose': 'desktop_learning_desk_acceptance',
                  'original_goal': original['nodes']['goal'], 'long_source_id': source['id'],
                  'long_source_title': source['title'], 'long_evidence_ids': selected['evidence_ids'],
                  'learning_evidence_count': len(saved['evidence']),
                  'nodes': {**original['nodes'], 'goal': selected['id']},
                  'labels': {**original['labels'], 'goal': selected['label']},
                  'aligned': ALIGNED, 'nested': NESTED, 'invalid': INVALID,
                  'manual_derivation': derivation, 'preparation_model_calls': model_calls,
                  'math_content_origin': 'user_authored_api_revision', 'real_provider_calls': 0}
    (directory / 'fixture.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    result = prepare(parser.parse_args().directory)
    print(json.dumps({'project_id': result['project_id'], 'evidence': result['learning_evidence_count'],
                      'real_provider_calls': 0}, ensure_ascii=False))
