"""Prepare a learning-route fixture through real upload, parsing and extraction.

The entire document is authored teaching material. Fixed HTTP model responses
exercise extraction and citation validation; no semantic rows are seeded and no
real provider is called. A fresh directory inside this repository is required.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

DOCUMENT = '''# 自编教学资料：从点积到注意力权重

## 教学目标
这份资料用固定的教学输入说明缩放点积注意力，帮助读者核对分数、归一化和权重。

## 点积
向量点积把同长度实向量对应位置相乘后相加。本例点积分数为8、4、0，理解点积有助于读懂缩放点积注意力的输入。

## Softmax
Softmax把有限实数分数沿同一候选轴归一化，得到总和为1的正权重。理解Softmax有助于区分注意力分数和最终权重。

## 缩放点积注意力
缩放点积注意力先把点积除以键向量维度的平方根，再经过Softmax归一化。本例d_k=4，缩放分数为4、2、0，第一个权重约为0.8668。

## 研究记录
学习记录应分开写下原文事实、教学输入和个人判断。完成一个学习步骤并不等于已经掌握知识，也没有在此报告学习收益数据。
'''

DEFINITIONS = [
    ('dot', 'concept', '向量点积', '向量点积把同长度实向量对应位置相乘后相加。'),
    ('softmax', 'concept', 'Softmax归一化', 'Softmax把有限实数分数沿同一候选轴归一化，得到总和为1的正权重。'),
    ('goal', 'method', '缩放点积注意力', '缩放点积注意力先把点积除以键向量维度的平方根，再经过Softmax归一化。'),
    ('unrelated', 'concept', '研究记录边界', '学习记录应分开写下原文事实、教学输入和个人判断。'),
]
RELATIONS = [
    ('dot', 'goal', '本例点积分数为8、4、0，理解点积有助于读懂缩放点积注意力的输入。', '理解点积有助于辨认目标方法的输入。'),
    ('softmax', 'goal', '理解Softmax有助于区分注意力分数和最终权重。', '理解归一化有助于区分分数和最终权重。'),
]


def prepare(directory: Path, *, source_kind='report'):
    directory = directory.resolve()
    if directory == ROOT or not directory.is_relative_to(ROOT):
        raise ValueError('Choose an isolated directory inside this repository')
    if directory.exists() and any(directory.iterdir()):
        raise ValueError('Choose a fresh directory')
    directory.mkdir(parents=True, exist_ok=True)
    os.environ.update(DATA_DIR=str(directory / 'data'), ATLAS_ENV_FILE='', ACCESS_MODE='local',
                      REQUIRE_LOGIN='false', OFFLINE_MODE='true', KNOWLEDGE_USE_DOCLING='false',
                      RESEARCH_MODEL_ENABLED='false', KNOWLEDGE_MODEL_ENABLED='false',
                      DASHSCOPE_API_KEY='fixture-unused-key', LLM_API_BASE='https://fixture.invalid/v1')
    import httpx
    from fastapi.testclient import TestClient
    from app.main import app
    from app.knowledge import model, service, store
    from app.knowledge.parser import parse_source

    requests = []

    def transport(request):
        payload = json.loads(json.loads(request.content)['messages'][1]['content'])
        nodes, edges = [], []
        for key, kind, label, quote in DEFINITIONS:
            block = next((block for block in payload.get('blocks', []) if quote in block['text']), None)
            if block:
                nodes.append({'key':key, 'kind':kind, 'label':label, 'summary':quote,
                              'evidence':[{'block_id':block['block_id'], 'quote':quote}]})
        keys = {node['key'] for node in nodes}
        for source, target, quote, explanation in RELATIONS:
            block = next((block for block in payload.get('blocks', []) if quote in block['text']), None)
            if block and source in keys and target in keys:
                edges.append({'source_key':source, 'target_key':target, 'kind':'PREREQUISITE_OF',
                              'label':'理解目标所需的基础', 'explanation':explanation, 'origin':'inference',
                              'evidence':[{'block_id':block['block_id'], 'quote':quote}]})
        requests.append({'purpose':'decomposition', 'nodes':len(nodes), 'edges':len(edges)})
        result = {'nodes':nodes, 'edges':edges}
        return httpx.Response(200, json={'choices':[{'message':{'content':json.dumps(result, ensure_ascii=False)}}],
                                        'usage':{'prompt_tokens':1, 'completion_tokens':1, 'total_tokens':2}})

    real_client = httpx.Client

    def model_client(**kwargs):
        return real_client(transport=httpx.MockTransport(transport), **kwargs)

    def enqueue(pid, sid, retry=False):
        with store.connection(pid) as conn:
            run, fresh = store.create_run(conn, pid, sid)
        if fresh:
            service.analyze(pid, sid, run['id'], retry)
        with store.connection(pid) as conn:
            return store.run(conn, pid, run['id'])

    with TestClient(app) as client, patch.object(model, 'available', lambda:True), \
            patch.object(model.httpx, 'Client', model_client), \
            patch.object(service, 'parse_file', lambda path, kind, check:parse_source(path, kind, use_docling=False)), \
            patch.object(service, 'enqueue', enqueue):
        project = client.post('/api/projects', json={'title':'从目标继续学习的路线验收', 'domain':'custom',
            'research_question':'怎样区分点积、缩放分数和注意力权重？',
            'constraints':{'version':1, 'objective':'工程复验；自编教学材料；固定模型HTTP响应'}})
        project.raise_for_status()
        pid = project.json()['id']
        client.patch(f'/api/projects/{pid}/knowledge/preferences', json={'mode':'explore'}).raise_for_status()
        (directory / 'attention-route.md').write_text(DOCUMENT, encoding='utf-8')
        response = client.post(f'/api/projects/{pid}/sources', data={'kind':source_kind},
                               files={'file':('attention-route.md', DOCUMENT.encode('utf-8'), 'text/markdown')})
        response.raise_for_status()
        source = response.json()['source']
        assert source['analysis']['status'] in {'succeeded', 'partial'}, source['analysis']
        graph = client.get(f'/api/projects/{pid}/knowledge/graph', params={'limit':2000}).json()
        semantic = {node['label']:node for node in graph['nodes'] if node.get('metadata', {}).get('semantic')}
        node_ids = {key:semantic[label]['id'] for key, _, label, _ in DEFINITIONS}
        assert len([edge for edge in graph['edges'] if edge['kind']=='PREREQUISITE_OF']) == 2
        teaching = [node for node in graph['nodes'] if node.get('metadata', {}).get('educational')]
        assert teaching and any(edge['kind']=='SUPPLEMENTS' for edge in graph['edges'])
        report = {'project_id':pid, 'source_id':source['id'], 'source_title':source['title'],
                  'source_kind':'authored_teaching_material', 'model_stub':True, 'real_provider_calls':0,
                  'nodes':node_ids, 'teaching_node_ids':[node['id'] for node in teaching],
                  'prerequisite_count':2, 'model_requests':requests}
    (directory / 'fixture.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    report = prepare(parser.parse_args().directory)
    print(json.dumps({'project_id':report['project_id'], 'prerequisite_count':report['prerequisite_count'],
                      'model_stub':True, 'real_provider_calls':0}))
