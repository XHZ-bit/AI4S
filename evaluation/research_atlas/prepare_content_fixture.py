"""Create isolated content-learning fixtures through the normal upload pipeline.

All source documents are authored teaching material. The parser and source
validation are real, while model HTTP responses are fixed engineering stubs.
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

DOCUMENTS = {
    'attention': '''# 自编教学资料A：缩放点积与softmax

## 研究问题
这份自编资料说明怎样把查询与键的点积分数转成一组权重，数值为教学输入。

## 方法与公式
查询向量q与键向量k长度相同，键向量维度为d_k。先计算q与k的点积，再除以sqrt(d_k)。三个点积分数为8、4、0，d_k=4时缩放分数为4、2、0。

Softmax将一组有限实数分数转为总和为1的正权重，计算为p_i=exp(s_i)/sum_j exp(s_j)，本例约为0.8668、0.1173、0.0159。这里沿三个候选位置归一化，温度为1。

## 教学条件
q和k为同长度实向量，d_k为正整数。分数s_i没有单位，p_i为归一化权重。4.0是softmax之前的一个缩放分数。

## 练习
改变d_k，观察缩放分数和权重怎样变化。完整注意力输出还需要对V加权求和。
''',
    'temperature': '''# 自编教学资料B：归一化指数的温度条件

## 方法与公式
归一化指数函数把一组分数转为和为1的权重。此教学实现先把分数除以温度tau=2，再计算p_i=exp(s_i/tau)/sum_j exp(s_j/tau)。

## 条件
三个候选位置沿同一轴归一化。分数为4、2、0，温度tau固定为2。改变温度会改变相对权重；这些输入只用于教学。
''',
    'study': '''# 自编教学资料C：学习方式的研究设计

## 研究问题
怎样比较重复阅读和主动回忆在延迟测试中的表现？这份资料用于练习辨认研究条件。

## 研究设计
实验设计比较两种学习方式，测量随后回忆出的项目数。两组使用同一材料、相同学习时长，并在同一测试间隔接受测验，参与者随机分配到各组。

## 样本
教学设定的总体为1000名学生，实际样本量为100名志愿参加者，其中30人支持某方案。样本比例是30%，总体其余人的选择没有在此给出。

## 条件核对
随机分配描述进入各组的方式，抽样描述谁进入研究。比较时还需核对学习时长、测试间隔和测量办法。此材料没有报告实际学习收益数据。
''',
}

NODES = {
    'attention': [
        ('problem', '怎样把点积分数转成权重', '怎样把查询与键的点积分数转成一组权重', {}),
        ('method', '缩放点积注意力', '三个点积分数为8、4、0，d_k=4时缩放分数为4、2、0', {'conditions':'沿三个候选位置计算，键向量维度d_k=4。'}),
        ('formula', 'Softmax', 'Softmax将一组有限实数分数转为总和为1的正权重', {
            'latex': r'p_i=\frac{\exp(s_i)}{\sum_j\exp(s_j)}',
            'symbols': {'s_i': {'meaning':'候选位置的缩放分数', 'unit':'无单位'}, 'p_i':'归一化权重', 'd_k': {'meaning':'键向量维度', 'unit':'正整数'}},
            'conditions': '沿三个候选位置归一化，温度为1。', 'inputs':['4','2','0'], 'outputs':'一组三项总和为1的权重',
        }),
    ],
    'temperature': [
        ('concept', '归一化指数', '归一化指数函数把一组分数转为和为1的权重', {
            'latex': r'p_i=\frac{\exp(s_i/\tau)}{\sum_j\exp(s_j/\tau)}',
            'conditions':'沿三个候选位置归一化，温度tau=2。', 'inputs':['4','2','0'],
        }),
    ],
    'study': [
        ('problem', '怎样比较学习方式', '怎样比较重复阅读和主动回忆在延迟测试中的表现', {}),
        ('experiment', '研究设计与对照', '两组使用同一材料、相同学习时长，并在同一测试间隔接受测验，参与者随机分配到各组', {'conditions':'同材料、同学习时长、同测试间隔，随机分配。'}),
        ('concept', '样本与总体', '总体为1000名学生，实际样本量为100名志愿参加者，其中30人支持某方案', {'conditions':'来自志愿者，样本100人。'}),
    ],
}


def prepare(directory: Path):
    directory = directory.resolve()
    if directory == ROOT or not directory.is_relative_to(ROOT):
        raise ValueError('Choose an isolated directory within this workspace')
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

    model_requests = []

    def transport(request):
        body = json.loads(request.content)
        payload = json.loads(body['messages'][1]['content'])
        if 'blocks' in payload:
            title = payload.get('source_title', '')
            case_key = next(key for key, text in DOCUMENTS.items() if text.splitlines()[0][2:] in title)
            nodes = []
            for kind, label, quote, metadata in NODES[case_key]:
                block = next((item for item in payload['blocks'] if quote in item['text']), None)
                if not block:
                    continue
                nodes.append({'key':label, 'kind':kind, 'label':label, 'summary':quote,
                              'metadata':metadata, 'evidence':[{'block_id':block['block_id'], 'quote':quote}]})
            result = {'nodes':nodes, 'edges':[]}
            model_requests.append({'purpose':'decomposition', 'source_title':title, 'node_count':len(nodes)})
        else:
            result = {'edges':[]}
            model_requests.append({'purpose':'cross_source_links', 'node_count':0})
        return httpx.Response(200, json={'choices':[{'message':{'content':json.dumps(result, ensure_ascii=False)}}],
                                        'usage':{'prompt_tokens':1, 'completion_tokens':1, 'total_tokens':2}})

    real_client = httpx.Client
    def local_model_client(**kwargs):
        return real_client(transport=httpx.MockTransport(transport), **kwargs)

    def enqueue(pid, sid, retry=False):
        with store.connection(pid) as conn:
            run, fresh = store.create_run(conn, pid, sid)
        if fresh:
            service.analyze(pid, sid, run['id'], retry)
        with store.connection(pid) as conn:
            return store.run(conn, pid, run['id'])

    report = {'source_kind':'authored_teaching_material', 'model_stub':True,
              'real_provider_calls':0, 'sources':{}, 'nodes':{}, 'model_requests':model_requests}
    with TestClient(app) as client, patch.object(model, 'available', lambda:True), \
            patch.object(model.httpx, 'Client', local_model_client), \
            patch.object(service, 'parse_file', lambda path, kind, check:parse_source(path, kind, use_docling=False)), \
            patch.object(service, 'enqueue', enqueue):
        response = client.post('/api/projects', json={'title':'自编资料的内容学习验收', 'domain':'custom',
            'research_question':'注意力分数怎样成为权重，怎样检查研究条件？',
            'constraints':{'version':1, 'objective':'工程验收，全部文档自编，模型传输为固定响应'}})
        response.raise_for_status()
        pid = report['project_id'] = response.json()['id']
        client.patch(f'/api/projects/{pid}/knowledge/preferences', json={'mode':'explore'}).raise_for_status()
        for key, text in DOCUMENTS.items():
            path = directory / (key + '.md')
            path.write_text(text, encoding='utf-8')
            response = client.post(f'/api/projects/{pid}/sources', data={'kind':'report'},
                                   files={'file':(key+'.md', text.encode('utf-8'), 'text/markdown')})
            response.raise_for_status()
            source = response.json()['source']
            report['sources'][key] = {'id':source['id'], 'title':source['title'], 'analysis':source['analysis']}
            if source['analysis']['status'] not in {'succeeded', 'partial'}:
                raise RuntimeError(source['analysis'])
            graph = client.get(f'/api/projects/{pid}/knowledge/graph', params={'source_id':source['id'], 'limit':2000}).json()
            report['nodes'][key] = {node['label']:node['id'] for node in graph['nodes'] if node.get('metadata', {}).get('semantic')}
            for _, label, _, _ in NODES[key]:
                if label not in report['nodes'][key]:
                    raise AssertionError('Missing extracted node '+label)
    (directory / 'fixture.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    result = prepare(parser.parse_args().directory)
    print(json.dumps({'project_id':result['project_id'], 'source_count':len(result['sources']),
                      'model_stub':result['model_stub'], 'real_provider_calls':0}))
