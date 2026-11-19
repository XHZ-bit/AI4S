"""Isolated real API with a deterministic *HTTP model transport* for acceptance.

This is an evaluation entry point, never imported by the product. It patches no
business API. Only model availability, external resource retrieval and model HTTP
responses are controlled. Test controls exist only in this isolated process.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from threading import Event, Lock
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))


def sections(label, marker):
    return {
        'overview': f'{marker}：{label}。' + '理解当前节点时，先区分输入、打分、中间权重和最终输出。查询表示正在寻找的信息，键用于比较候选位置，值提供最后汇总的内容。把每个中间量放回原文的定义与适用条件中，可以避免将一个计算步骤误认为整个模型。这里的固定数值只用于自编教学演算，不代表论文实验。' * 2,
        'definition': '定义与维度：查询向量q和每个键向量k具有相同长度，维度d_k为正整数。点积得到标量分数，除以sqrt(d_k)后仍是标量。三个候选位置对应长度为3的分数向量，softmax沿这一个候选轴归一化。权重与值向量相乘并相加，才得到相应的输出表示。多头组织为各头分别做这一过程，随后组合。' * 2,
        'derivation': '步骤一：设定自编教学输入，三个点积分数为8、4、0，键向量维度d_k=4，因此sqrt(d_k)=2。步骤二：逐项相除，得到softmax之前的缩放分数4、2、0，其中第一个缩放分数为4.0。步骤三：计算三个指数exp(4)、exp(2)、exp(0)，再将每项除以这三个数的和，得到约0.8668、0.1173、0.0159。步骤四：检查权重均为正且总和约为1；完整注意力输出还须对提供的V加权求和。若V未提供，不能报告输出表示。这个例子展示的是计算顺序，改变d_k会改变分数的相对差异和归一化结果。' * 2,
        'prerequisites': '向量点积帮助理解候选位置如何获得分数，softmax帮助理解一组分数如何成为同一候选轴上的正权重。先核对输入向量长度，再核对归一化发生的轴，可以把当前节点与前置知识连接起来。前置解释属于教学组织，仍应返回提供的来源检查原文如何使用这些量。' * 2,
        'implementation': '本夹具没有提供真实仓库源码，因而不能把某个教学步骤指认成实际文件或函数。若后续导入源码，应分别定位点积、维度缩放、softmax及对V的加权求和，记录代码版本与行段。只有算法名称相同不足以确认实现对应关系。' * 2,
        'limitations': '适用条件与反例：d_k必须是正的键向量维度，归一化必须沿同一个候选轴进行。分数可以大于1，概率权重才满足和为1的约束。若输入包含非有限数值，或所有位置被掩码排除，需检查实现的额外处理规则。这些教学输入不能当作真实论文实验结果，也不能证明模型性能或用户学习收益。' * 2,
    }


def create_app(directory: Path):
    directory = directory.resolve()
    if not directory.is_relative_to(ROOT / '.ui_validation') or not (directory / 'fixture.json').is_file():
        raise ValueError('Use a prepared isolated fixture below .ui_validation')
    os.environ.update(DATA_DIR=str(directory / 'data'), ATLAS_ENV_FILE=str(directory / 'missing.env'),
        ACCESS_MODE='local', REQUIRE_LOGIN='false', OFFLINE_MODE='true',
        KNOWLEDGE_USE_DOCLING='false', RESEARCH_MODEL_ENABLED='false', KNOWLEDGE_MODEL_ENABLED='false',
        DASHSCOPE_API_KEY='fixed-fixture-key', LLM_API_BASE='https://fixture.invalid/v1')
    import httpx
    from fastapi import Body
    from app.main import app
    from app.knowledge import learning, model
    from app.knowledge.learning_depth import REVIEW_PROMPT

    lock = Lock()
    state = {'configured': True, 'enabled': True, 'nodes': {}, 'calls': [], 'sequence': 0}
    gates = {}
    real_client = httpx.Client

    def transport(request):
        body = json.loads(request.content)
        content = body['messages'][1]['content']
        if isinstance(content, list):
            content = next(part['text'] for part in content if part.get('type') == 'text')
        payload = json.loads(content)
        node = payload.get('node', {})
        nid = node.get('id', '')
        is_review = body['messages'][0]['content'] == REVIEW_PROMPT
        with lock:
            config = dict(state['nodes'].get(nid, {}))
            state['sequence'] += 1
            sequence = state['sequence']
            call = {'id': sequence, 'node_id': nid, 'label': node.get('label'), 'goal': payload.get('goal'),
                    'depth': payload.get('depth'), 'purpose': 'learning_review' if is_review else 'learning_generation',
                    'review_rejected': bool(config.get('reject')), 'started': time.time(), 'finished': None}
            state['calls'].append(call)
            gate = gates.get(nid) if config.get('hold') and not is_review else None
        if gate is not None:
            gate.wait(timeout=20)
        if is_review:
            value = {'accepted': not config.get('reject'),
                     'issues': config.get('review_issues', ['隔离验收：候选计算未通过校核']) if config.get('reject') else [],
                     'corrections': {}}
        else:
            marker = '未审核候选内容' if config.get('reject') else '已核对教学详解'
            value = {'sections': sections(node.get('label', '当前节点'), marker),
                     'evidence_ids': [item['id'] for item in payload.get('sources', [])[:2]]}
        with lock:
            call['finished'] = time.time()
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(value, ensure_ascii=False)}}],
                                        'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}})

    def client(**kwargs):
        return real_client(transport=httpx.MockTransport(transport), **kwargs)

    model.httpx.Client = client
    model.configured = lambda: state['configured']
    model.available = lambda: state['configured'] and state['enabled']
    learning.discover_resources = lambda pid, node, initial: initial
    learning.fetch_resources = lambda pid, resources: resources

    @app.get('/api/__acceptance__/learning/stats')
    def stats():
        with lock:
            return {'configured': state['configured'], 'enabled': state['enabled'],
                    'calls': [dict(call) for call in state['calls']], 'real_provider_calls': 0}

    @app.post('/api/__acceptance__/learning/control')
    def control(body: dict = Body(...)):
        with lock:
            for key in ('configured', 'enabled'):
                if key in body:
                    state[key] = bool(body[key])
            if body.get('node_id'):
                nid = body['node_id']
                state['nodes'][nid] = dict(body.get('scenario', {}))
                if state['nodes'][nid].get('hold'):
                    gates[nid] = Event()
                elif nid in gates:
                    gates[nid].set()
            for nid in body.get('release', []):
                if nid in gates:
                    gates[nid].set()
        return {'ok': True, 'real_provider_calls': 0}

    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--port', type=int, default=18119)
    arguments = parser.parse_args()
    import uvicorn
    uvicorn.run(create_app(arguments.directory), host='127.0.0.1', port=arguments.port)
