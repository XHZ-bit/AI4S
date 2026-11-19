"""Prepare isolated correspondence acceptance data from cached public sources.

No model calls. PDF blocks use native text and original coordinates. The two
node explanations and tiny exercises are authored teaching material.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

ATTENTION_LATEX = r'\operatorname{Attention}(Q,K,V)=\operatorname{softmax}\left(\frac{QK^{\mathsf{T}}}{\sqrt{d_k}}\right)V'
TRANSCRIPTION_NOTICE = '预置教学示例，由开发助手整理，待用户最终核对。LaTeX 为单独转写，逐字摘录保留 PDF 原生文字。'


def complete_attention_formula(blocks):
    """Merge the two adjacent native PDF blocks, without rewriting their text."""
    index = next((i for i, b in enumerate(blocks) if b.get('page') == 4 and 'Attention(Q' in b.get('text', '')), None)
    if index is None or index + 1 >= len(blocks):
        raise ValueError('Attention equation (1) native blocks are missing')
    first, second = blocks[index:index + 2]
    if (second.get('page') != 4 or not first.get('bbox') or not second.get('bbox')
            or '\u221a' not in second.get('text', '') or 'dk' not in second['text'] or '(1)' not in second['text']):
        raise ValueError('Attention equation (1) denominator block is incomplete')
    a, b = first['bbox'], second['bbox']
    if not (a[1] <= b[1] <= a[3] and a[0] <= b[0] <= a[2]):
        raise ValueError('Attention native blocks do not form one formula region')
    return {'kind': 'formula', 'text': first['text'] + second['text'],
            'heading': '3.2.1 Scaled Dot-Product Attention · Equation (1)', 'page': 4,
            'bbox': [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])],
            'metadata': {'latex': ATTENTION_LATEX, 'recognition': 'manual_transcription',
                         'native_formula_region': True, 'transcription_origin': 'developer_assistant',
                         'transcription_notice': TRANSCRIPTION_NOTICE,
                         'native_parts': [{'text': part['text'], 'bbox': part['bbox']} for part in (first, second)]}}


def prepare(directory: Path):
    directory = directory.resolve()
    if not directory.is_relative_to(ROOT) or directory == ROOT:
        raise ValueError('Acceptance directory must be a new directory within the workspace')
    if directory.exists() and any(directory.iterdir()):
        raise ValueError('Choose a fresh acceptance directory')
    directory.mkdir(parents=True, exist_ok=True)
    os.environ.update(DATA_DIR=str(directory / 'data'), ATLAS_ENV_FILE='', OFFLINE_MODE='true',
                      ACCESS_MODE='local', REQUIRE_LOGIN='false', RESEARCH_MODEL_ENABLED='false',
                      DASHSCOPE_API_KEY='')
    import fitz
    from fastapi.testclient import TestClient
    from app.main import app
    from app.knowledge import extraction, practice, sources, store
    from app.knowledge.parser import parse_source

    client = TestClient(app)
    response = client.post('/api/projects', json={'title': '方法与实现对应验收', 'domain': 'custom',
        'research_question': '从原文和固定版本代码检查一个具体判断',
        'constraints': {'version': 1, 'objective': '工程验收，独立资料目录，无模型调用'}})
    response.raise_for_status()
    pid = response.json()['id']
    report = {'project_id': pid, 'model_calls': 0, 'cases': {}, 'sources': []}

    def pdf_source(path, title):
        raw = path.read_bytes()
        src = sources.ingest(pid, raw, title + '.pdf', 'paper')
        blocks = []
        with fitz.open(stream=raw, filetype='pdf') as doc:
            for index, page in enumerate(doc):
                for b in page.get_text('blocks'):
                    if b[4].strip():
                        blocks.append({'kind': 'text', 'text': b[4], 'heading': title,
                            'ordinal': len(blocks), 'page': index + 1, 'bbox': list(b[:4]), 'metadata': {}})
        if '1706.03762v7' in title:
            blocks.append(complete_attention_formula(blocks))
        with store.connection(pid) as conn:
            store.put_parse(conn, src['asset_id'], {'title': title, 'blocks': blocks, 'parser': 'native-pdf-acceptance'})
            blocks = store.source_blocks(conn, src['asset_id'])
        report['sources'].append({'title': title, 'sha256': hashlib.sha256(raw).hexdigest(), 'parser': 'native-pdf-acceptance'})
        return src, blocks

    def code_source(raw, name):
        src = sources.ingest(pid, raw, name, 'code')
        with store.connection(pid) as conn:
            asset = conn.execute('SELECT path FROM kw_assets WHERE id=?', (src['asset_id'],)).fetchone()[0]
            store.put_parse(conn, src['asset_id'], parse_source(Path(asset), 'code', use_docling=False))
            blocks = store.source_blocks(conn, src['asset_id'])
        return src, blocks

    def case(key, src, block, label, summary, code, expected):
        with store.connection(pid) as conn:
            eid = store.add_evidence(conn, pid, src, block)
            node = extraction.node(src, 'acceptance-' + key, 'method', label, summary, [eid],
                                   origin='inference', metadata={'semantic': True, 'acceptance_teaching': True})
            store.put_record(conn, 'kw_nodes', node)
        exercise = practice.get(pid, node['id'])
        with store.connection(pid) as conn:
            value = practice.record(conn, pid, exercise['id'])
            value.update(title=label + ' · 数值检验', prompt=summary,
                         starter_code=code, draft_code=code, input_json='{}',
                         expected_behavior=expected, status='ready', origin='authored_teaching')
            conn.execute('UPDATE kw_practice SET data=? WHERE id=?', (store.encode(value), value['id']))
        report['cases'][key] = {'node_id': node['id'], 'source_id': src['id'],
            'paper_evidence_id': eid, 'paper_span': block['text'], 'practice_id': exercise['id'],
            'teaching_code': code, 'expected_behavior': expected, 'teaching_prompt': summary}

    coordex, cb = pdf_source(ROOT / '.tmp/knowledge-acceptance/data/knowledge/assets/70519c81bfc797aaebf7f3d1cee7c68c.pdf', 'CoorDex')
    formula = next(b for b in cb if b['page'] == 5 and 'tanh' in b['text'])
    code_raw = (ROOT / '.tmp/knowledge-acceptance/data/knowledge/assets/aeea7543e39a2ab1616924e4f67fd88b.repo.json').read_bytes()
    cs, code_blocks = code_source(code_raw, 'coordex.repo.json')
    target = next(b for b in code_blocks if str(b['metadata'].get('symbol', '')).endswith('.update_distribution'))
    case('coordex', coordex, formula, 'CoorDex 有界残差与正态采样',
         '原文公式说明 tanh 残差。结合固定版本代码分别核对均值、分布构造和采样。'
         '教学算例检查后续裁剪或变换之前的标量采样，数值是教学输入。',
         'mu = 0.8\nsigma = 0.5\nepsilon = float(inputs.get("epsilon", 1))\nprint(round(mu + sigma * epsilon, 6))',
         '教学输入 mu=0.8, sigma=0.5, epsilon=1 时为 1.3；这里只检查后续裁剪或变换之前的标量采样。')
    report['cases']['coordex'].update(code_source_id=cs['id'], code_block_id=target['id'], code_span=target['text'])

    attention_path = ROOT / '.tmp/knowledge-holdout/data/knowledge/assets/c10cc9ca2bf3644a4ceaa6aaa87642fe.pdf'
    if hashlib.sha256(attention_path.read_bytes()).hexdigest() != 'bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697':
        raise ValueError('Attention cached version differs from the fixed acceptance source')
    attention, ab = pdf_source(attention_path, 'Attention Is All You Need · 1706.03762v7')
    formula = next(b for b in ab if b.get('metadata', {}).get('native_formula_region'))
    case('attention', attention, formula, 'Scaled dot-product attention',
         '核对缩放点积注意力中的 sqrt(d_k)。所配代码是自编教学实现，未声称为论文作者实现。',
         'import math\nq_dot_k = 8.0\nd_k = 4\nprint(q_dot_k / math.sqrt(d_k))',
         '教学输入 Q·K=8，d_k=4，缩放后的 logit 为 4.0；没有运行完整 Transformer。')
    good, gb = code_source(b'import math\n\ndef scaled_dot_product(q_dot_k, d_k):\n    return q_dot_k / math.sqrt(d_k)\n', 'attention-teaching.py')
    wrong, wb = code_source(b'def scaled_dot_product(q_dot_k, d_k):\n    return q_dot_k * d_k\n', 'attention-same-name-counterexample.py')
    report['cases']['attention'].update(code_source_id=good['id'], code_block_id=next(b['id'] for b in gb if b['metadata'].get('symbol') == 'scaled_dot_product'),
        wrong_source_id=wrong['id'], wrong_block_id=next(b['id'] for b in wb if b['metadata'].get('symbol') == 'scaled_dot_product'))
    (directory / 'fixture.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def bind_exercise(directory: Path, case_key: str, mapping_id: str):
    """Seed the authored exercise after the browser has confirmed a correspondence."""
    directory = directory.resolve()
    if not directory.is_relative_to(ROOT) or directory == ROOT:
        raise ValueError('Acceptance directory must be within the workspace')
    report = json.loads((directory / 'fixture.json').read_text(encoding='utf-8'))
    os.environ.update(DATA_DIR=str(directory / 'data'), ATLAS_ENV_FILE='', OFFLINE_MODE='true',
                      ACCESS_MODE='local', REQUIRE_LOGIN='false', RESEARCH_MODEL_ENABLED='false',
                      DASHSCOPE_API_KEY='')
    from app.knowledge import implementations, practice, store
    pid, case = report['project_id'], report['cases'][case_key]
    with store.connection(pid) as conn:
        mapping = next(item for item in implementations.list_mappings(conn, pid, case['node_id']) if item['id'] == mapping_id)
    artifact = practice.get(pid, case['node_id'], mapping_id=mapping_id, mapping_revision=mapping['revision'])
    with store.connection(pid) as conn:
        value = practice.record(conn, pid, artifact['id'])
        value.update(title=case_key + ' · 已核对教学算例', prompt=case['teaching_prompt'],
                     starter_code=case['teaching_code'], draft_code=case['teaching_code'], input_json='{}',
                     expected_behavior=case['expected_behavior'], status='ready', origin='authored_teaching')
        conn.execute('UPDATE kw_practice SET data=? WHERE id=? AND project_id=?', (store.encode(value), value['id'], pid))
    return {'practice_id': artifact['id'], 'mapping_id': mapping_id, 'mapping_revision': mapping['revision'], 'model_calls': 0}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('directory', type=Path)
    p.add_argument('--bind-case', choices=['coordex', 'attention'])
    p.add_argument('--mapping')
    args = p.parse_args()
    if args.bind_case:
        if not args.mapping:
            p.error('--mapping is required with --bind-case')
        print(json.dumps(bind_exercise(args.directory, args.bind_case, args.mapping)))
    else:
        result = prepare(args.directory)
        print(json.dumps({'project_id': result['project_id'], 'cases': list(result['cases'])}))
