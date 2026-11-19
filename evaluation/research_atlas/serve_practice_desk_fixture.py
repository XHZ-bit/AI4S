"""Real isolated practice API, with deterministic model HTTP replies only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from threading import Lock

from serve_learning_entry_fixture import create_app as create_base_app

STARTER_CODE = '''import math

# TODO: change the JSON input, then compare the intermediate score.
scaled = float(inputs["dot"]) / math.sqrt(float(inputs["d_k"]))
offset = float(input())
result = scaled + offset
print(f"scaled={scaled:.1f}")
print(f"result={result:.1f}")
'''
INPUT_JSON = '{"dot":8,"d_k":4,"stdin":["2"]}'
FEEDBACK = '固定验收分析：代码先按键向量维度缩放点积分数，再读取一行教学偏移量。请分别核对scaled和result；这里仅做静态解释，运行是否成功以右侧实际输出和运行记录为准。'


def exercise(payload):
    return {'title': '教学练习：缩放分数与标准输入',
        'prompt': '先计算dot/sqrt(d_k)，再读取一行stdin作为教学偏移量，与缩放分数相加。JSON输入提供dot、d_k，程序输入每行供一次input()读取。默认输入8、4和偏移2，应分别看到4.0与6.0。',
        'starter_code': STARTER_CODE, 'input_json': INPUT_JSON,
        'test_code': 'assert abs(scaled - 4.0) < 1e-12\nassert abs(result - 6.0) < 1e-12',
        'reference_code': '', 'hints': ['先观察scaled，再改变stdin中的教学偏移量。'],
        'expected_behavior': '默认输入打印scaled=4.0与result=6.0。修改输入后使用运行代码观察实际结果。',
        'learning_objectives': ['区分JSON输入与input()标准输入', '保留中间量并核对实际输出'],
        'simplifications': ['偏移量是自编教学输入，不是论文公式的一部分。', '未提供真实方法源码，当前代码为教学实现，不代表完整Transformer或论文复现。'],
        'evidence_ids': [item['id'] for item in payload.get('sources', [])[:1]]}


def create_app(directory: Path):
    import httpx
    real_client = httpx.Client
    app = create_base_app(directory)
    from app.knowledge import model
    calls, lock = [], Lock()

    def transport(request):
        body = json.loads(request.content)
        payload = json.loads(body['messages'][1]['content'])
        system = body['messages'][0]['content']
        if 'feedback:string' in system:
            purpose = 'practice_code_review'
            result = {'feedback': FEEDBACK}
        elif 'exercise' in payload:
            purpose = 'practice_review'
            result = {'accepted': True, 'issues': [], 'corrections': {}}
        elif 'starter_code' in system:
            purpose = 'practice_generation'
            result = exercise(payload)
        else:
            raise AssertionError('Unexpected model purpose in practice-only acceptance')
        with lock:
            calls.append({'purpose': purpose, 'node_id': payload.get('node', {}).get('id'),
                          'code': payload.get('code'), 'output': payload.get('output')})
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(result, ensure_ascii=False)}}],
                                        'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}})

    model.httpx.Client = lambda **kwargs: real_client(transport=httpx.MockTransport(transport), **kwargs)

    @app.get('/api/__acceptance__/practice/stats')
    def stats():
        with lock:
            return {'calls': list(calls), 'real_provider_calls': 0}

    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--port', type=int, default=18139)
    arguments = parser.parse_args()
    import uvicorn
    uvicorn.run(create_app(arguments.directory), host='127.0.0.1', port=arguments.port)
