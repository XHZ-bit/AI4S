"""Prepare one real-paper demo through HTTP, with explicitly authored teaching.

Phases: import -> stop isolated server -> cache -> restart -> prepare.
After an engineering/browser review confirms the teaching mapping, bind-practice
adds the authored exercise at that exact mapping revision. No model is called.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time
from urllib.parse import urlparse

import fitz
import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_implementation_fixture import ATTENTION_LATEX, complete_attention_formula  # noqa: E402

SHA = 'bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697'
PDF = ROOT / '.tmp/knowledge-holdout/data/knowledge/assets/c10cc9ca2bf3644a4ceaa6aaa87642fe.pdf'
CACHE = ROOT / '.tmp/knowledge-holdout/data/atlas.db'
QUESTION = '翻译一个词时，模型怎样决定参考句中的哪些词'
NOTICE = '预置教学示例，由开发助手整理，待用户最终核对。'


def profile_path(directory):
    path = Path(directory).resolve()
    allowed = (ROOT / '.ui_validation').resolve()
    if (path == allowed or not path.is_relative_to(allowed) or (path / 'data').is_symlink()
            or not (path / 'data').resolve().is_relative_to(path)):
        raise ValueError('Choose an isolated profile below .ui_validation, never normal backend/data')
    return path


def read_manifest(directory):
    value = json.loads((directory / 'attention-demo.json').read_text(encoding='utf-8'))
    if value.get('kind') != 'attention-classic-offline-demo' or Path(value['profile']).resolve() != directory:
        raise ValueError('Unrecognized profile; existing data was kept')
    return value


def save(directory, value):
    value['notice'] = '经典论文为真实公开资料；补充解说、候选对应与练习为' + NOTICE
    (directory / 'attention-demo.json').write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def response(result):
    result.raise_for_status()
    return result.json()


def client_for(directory, api):
    parsed = urlparse(api)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.port in (None, 8000, 5173):
        raise ValueError('Use a dedicated loopback demo API, never normal 8000/5173')
    client = httpx.Client(base_url=api, timeout=60)
    response(client.get('/health'))
    status = response(client.get('/api/system/status'))
    if Path(status['data_dir']).resolve() != directory / 'data':
        client.close()
        raise ValueError('API data directory does not match the requested isolated profile')
    if status['capabilities']['knowledge_model'] or status['capabilities']['research_model']:
        client.close()
        raise ValueError('Disable model capabilities before preparing this offline demo')
    return closing(client)


def import_sources(directory, api):
    if hashlib.sha256(PDF.read_bytes()).hexdigest() != SHA:
        raise ValueError('Pinned Attention v7 PDF hash differs')
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / 'attention-demo.json').exists():
        report = read_manifest(directory)
        if all(key in report.get('imports', {}) for key in ('paper', 'teaching', 'counterexample')):
            return report
    else:
        database = directory / 'data/atlas.db'
        if database.exists():
            with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as conn:
                tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                for table in ('research_project_versions', 'kw_sources', 'papers'):
                    if table in tables and conn.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]:
                        raise ValueError('Existing populated profile has no Attention manifest; it was kept')
        with client_for(directory, api) as client:
            project = response(client.post('/api/projects', json={'title': 'Attention · 从问题到可核对实现',
                'domain': 'custom', 'research_question': QUESTION,
                'constraints': {'version': 1, 'objective': NOTICE + '核对缩放项与教学实现，运行一个数值例子。'}}))
        report = {'kind': 'attention-classic-offline-demo', 'schema_version': 1, 'profile': str(directory),
                  'api': api, 'project_id': project['id'], 'real_provider_calls': 0, 'imports': {}, 'stage': 'uploading'}
        save(directory, report)
    files = [('paper', PDF, 'Attention Is All You Need - 1706.03762v7.pdf', 'paper'),
             ('teaching', ROOT / 'evaluation/research_atlas/fixtures/attention_teaching.py', 'attention_teaching.py', 'code'),
             ('counterexample', ROOT / 'evaluation/research_atlas/fixtures/attention_counterexample.py', 'attention_counterexample.py', 'code')]
    with client_for(directory, api) as client:
        for key, path, name, kind in files:
            if key in report['imports']:
                continue
            raw = path.read_bytes()
            result = response(client.post(f'/api/projects/{report["project_id"]}/sources',
                files={'file': (name, raw)}, data={'kind': kind}))
            report['imports'][key] = {'source_id': result['source']['id'], 'source_version': result['source']['version'],
                'analysis_id': result['analysis']['id'], 'filename': name, 'sha256': hashlib.sha256(raw).hexdigest()}
            save(directory, report)
    report['stage'] = 'awaiting_normal_parse'
    save(directory, report)
    return report


def reuse_parse(directory):
    report = read_manifest(directory)
    if report.get('parse_reuse'):
        return report
    try:
        httpx.get(report['api'] + '/health', timeout=2).raise_for_status()
    except httpx.ConnectError:
        pass
    else:
        raise ValueError('Stop only the isolated demo API before cache reuse')
    with closing(sqlite3.connect(CACHE.resolve().as_uri() + '?mode=ro', uri=True)) as conn:
        source = next(json.loads(r[0]) for r in conn.execute('SELECT data FROM kw_sources')
                      if json.loads(r[0]).get('version') == 'sha256:' + SHA)
        parsed = json.loads(conn.execute('SELECT data FROM kw_parses WHERE asset_id=?', (source['asset_id'],)).fetchone()[0])
    if hashlib.sha256(PDF.read_bytes()).hexdigest() != SHA or len(parsed['blocks']) != 167:
        raise ValueError('Fixed source or reviewed parse cache differs')
    native = []
    with fitz.open(PDF) as document:
        for index, page in enumerate(document):
            native.extend({'page': index + 1, 'text': b[4], 'bbox': list(b[:4])} for b in page.get_text('blocks') if b[4].strip())
        formula = complete_attention_formula(native)
        document[3].get_pixmap(matrix=fitz.Matrix(4, 4), clip=fitz.Rect(formula['bbox'])).save(directory / 'attention-equation-1.png')
    parsed['blocks'].append(formula)
    from app.knowledge import store
    with closing(sqlite3.connect(directory / 'data/atlas.db')) as conn, conn:
        target = json.loads(conn.execute('SELECT data FROM kw_sources WHERE project_id=? AND id=?',
            (report['project_id'], report['imports']['paper']['source_id'])).fetchone()[0])
        if target['version'] != 'sha256:' + SHA:
            raise ValueError('Uploaded paper differs; no parse was replaced')
        store.put_parse(conn, target['asset_id'], parsed)
        block = store.source_blocks(conn, target['asset_id'])[-1]
    report['parse_reuse'] = {'notice': '固定版本解析缓存复用，非本轮新解析/AI抽取', 'cache': str(CACHE.relative_to(ROOT)),
        'source_version': 'sha256:' + SHA, 'copied_original_blocks': 167, 'cached_formula_count': 6, 'cached_latex_count': 4,
        'semantic_nodes_copied': 0, 'learning_or_notes_copied': 0, 'source_parse_status_not_rewritten': True}
    report['formula'] = {'block_id': block['id'], 'page': 4, 'bbox': formula['bbox'], 'native_text': formula['text'],
        'latex': ATTENTION_LATEX, 'transcription_origin': 'developer_assistant', 'review_notice': NOTICE, 'image': 'attention-equation-1.png'}
    report['stage'] = 'cached_parse_ready_for_normal_analysis'
    save(directory, report)
    (directory / 'attention-equation-1.md').write_text('# Attention v7 公式（1）原页核对\n\n来源 sha256:' + SHA +
        '\n\nPDF第4页，第3.2.1节。相邻原生两块真实拼接：\n\n```text\n' + formula['text'] +
        '```\n\n下列LaTeX单独转写，不混入逐字摘录。' + NOTICE + '\n\n$$\n' + ATTENTION_LATEX +
        '\n$$\n\n![原始公式区域](attention-equation-1.png)\n', encoding='utf-8')
    return report


def wait_for_sources(client, report):
    pid = report['project_id']
    for name, imported in report['imports'].items():
        path = f'/api/projects/{pid}/sources/{imported["source_id"]}'
        source = response(client.get(path))
        if source.get('analysis', {}).get('status') in ('interrupted', 'failed'):
            response(client.post(f'/api/projects/{pid}/analysis', json={'source_id': source['id'], 'retry': True}))
        deadline = time.monotonic() + 180
        while True:
            source = response(client.get(path))
            if source.get('analysis', {}).get('status') not in ('queued', 'running'):
                break
            if time.monotonic() > deadline:
                raise RuntimeError(f'{name} still parsing; source is saved. Resume later without reuploading.')
            time.sleep(1)
        if not source.get('blocks'):
            raise RuntimeError(f'{name} has no readable blocks; retain its real analysis status and retry explicitly')
        imported['analysis_status'] = source.get('analysis', {}).get('status')
        imported['latest_analysis_id'] = source.get('analysis', {}).get('id')
        imported['parser'] = source.get('parser')


def fill_exercise(directory, client, report, mapping=None):
    pid, nid = report['project_id'], report['node_id']
    params = {'goal': '', 'difficulty': 'foundation'}
    if mapping:
        params.update(mapping_id=mapping['id'], mapping_revision=mapping['revision'])
    artifact = response(client.get(f'/api/projects/{pid}/knowledge/nodes/{nid}/practice', params=params))
    if artifact.get('authored_by') == 'developer_assistant' or artifact.get('runs'):
        return artifact
    if artifact.get('revision', 1) != 1:
        raise ValueError('Existing exercise has edits; it was kept')
    code = (ROOT / 'evaluation/research_atlas/fixtures/attention_teaching.py').read_text(encoding='utf-8').replace('print(score)', 'print(f"scaled={score}")')
    artifact = response(client.patch(f'/api/projects/{pid}/knowledge/practice/{artifact["id"]}', json={
        'expected_revision': artifact['revision'], 'code': code, 'input_json': json.dumps({'dot': 8, 'd_k': 4})}))
    with closing(sqlite3.connect(directory / 'data/atlas.db')) as conn, conn:
        saved = json.loads(conn.execute('SELECT data FROM kw_practice WHERE project_id=? AND id=?', (pid, artifact['id'])).fetchone()[0])
        saved.update(status='starter', origin='developer_assistant_teaching_example', authored_by='developer_assistant',
            sample_pending_user_review=True, title='缩放分数 · 预置教学练习（待核对）', starter_code=code,
            prompt=NOTICE + '\n点积分数 dot=8、d_k=4。请先预测 softmax 之前的缩放分数，再运行；把 d_k 改为16后再预测。',
            test_code='expected = float(inputs.get("dot", 8)) / math.sqrt(float(inputs.get("d_k", 4)))\nassert math.isclose(score, expected, rel_tol=1e-9), "核对缩放分母"\n',
            expected_behavior='dot=8,d_k=4 输出 scaled=4.0；d_k=16 输出 scaled=2.0。这不是注意力权重。',
            hints=['函数来自自编教学实现；练习只为输出增加scaled标签。', '输入为教学数值，不是论文训练或真实模型输出。'],
            simplifications=[NOTICE, '仅检查单个缩放分数，不运行完整Transformer或softmax。'])
        conn.execute('UPDATE kw_practice SET data=? WHERE project_id=? AND id=?', (json.dumps(saved, ensure_ascii=False), pid, saved['id']))
    return response(client.get(f'/api/projects/{pid}/knowledge/practice/{artifact["id"]}'))


def prepare_teaching(directory, api, *, bind=False):
    report = read_manifest(directory)
    pid = report['project_id']
    with client_for(directory, api) as client:
        if not bind and report.get('stage') in ('prepared_examples_pending_user_review', 'confirmed_mapping_exercise_prepared_for_engineering_run'):
            return report
        if bind:
            items = response(client.get(f'/api/projects/{pid}/knowledge/nodes/{report["node_id"]}/implementations'))['items']
            mapping = next(m for m in items if m['id'] == report['mappings']['teaching']['id'])
            if mapping['status'] != 'confirmed' or mapping.get('stale'):
                raise ValueError('Review the teaching mapping first; preparation never confirms it for the user')
            artifact = fill_exercise(directory, client, report, mapping)
            for name, recorded in report['mappings'].items():
                actual = next((item for item in items if item['id'] == recorded['id']), recorded)
                report['mappings'][name] = {k: actual[k] for k in ('id', 'revision', 'status')}
            report['practice_id'], report['practice_revision'] = artifact['id'], artifact['revision']
            report['paths']['practice'] += '&mapping=' + mapping['id'] if '&mapping=' not in report['paths']['practice'] else ''
            report['stage'] = 'confirmed_mapping_exercise_prepared_for_engineering_run'
            save(directory, report)
            return report
        wait_for_sources(client, report)
        source = response(client.get(f'/api/projects/{pid}/sources/{report["imports"]["paper"]["source_id"]}'))
        graph = response(client.get(f'/api/projects/{pid}/knowledge/graph', params={'source_id': source['id'], 'limit': 2000}))
        node = next(n for n in graph['nodes'] if n.get('metadata', {}).get('block_id') == report['formula']['block_id'])
        if not report.get('node_id'):
            node = response(client.patch(f'/api/projects/{pid}/knowledge/nodes/{node["id"]}', json={
                'expected_version': node['version'], 'label': '缩放点积注意力 · 公式（1）',
                'summary': NOTICE + '论文第4页公式（1）先计算QKᵀ，再除以√d_k，之后对一组分数做softmax并作用于V。单个4.0只检验缩放项，不是概率。',
                'latex': ATTENTION_LATEX}))
        report['node_id'] = node['id']
        detail = response(client.get(f'/api/projects/{pid}/knowledge/nodes/{node["id"]}'))
        evidence = next(e for e in detail['evidence'] if e['block_id'] == report['formula']['block_id'])
        report['evidence_id'] = evidence['id']
        response(client.patch(f'/api/projects/{pid}/knowledge/preferences', json={'mode': 'explore', 'view': 'graph'}))
        learning_root = f'/api/projects/{pid}/knowledge/nodes/{node["id"]}/learning'
        lesson = response(client.get(learning_root))
        if not lesson.get('user_edited_sections'):
            sections = {'overview': NOTICE + '\n\n翻译时，query可理解为当前要找的信息，key用于和query比较，value提供被汇总的信息。具体模型背景仍需结合论文第3节。',
                'definition': NOTICE + '\n\n原文：PDF第4页3.2.1节公式（1）。Q、K、V分别表示查询、键和值；d_k是键向量维度。softmax作用于一组缩放后的分数。',
                'derivation': NOTICE + '\n\n教学输入dot=8、d_k=4，缩放分数为8/√4=4.0。把d_k改为16，得到2.0。两者都位于softmax之前；不能将4.0当作注意力权重。',
                'prerequisites': NOTICE + '\n\n先理解点积、平方根与softmax。平台的补基础入口是教学补充，不是论文宣称的实验结果。',
                'implementation': NOTICE + '\n\nattention_teaching.py第8–11行是自编教学函数，第11行做除法。attention_counterexample.py第7–8行故意乘以d_k，是待驳回候选。请对照双方原文后自行决定。',
                'limitations': NOTICE + '\n\n本例没有训练或复现Transformer，没有比较翻译质量、成本或学习收益。论文解析使用固定版本缓存复用；教学说明和练习没有冒认新AI生成。'}
            lesson = response(client.patch(learning_root, json={'expected_revision': lesson['revision'], 'goal': QUESTION, 'depth': 'standard', 'sections': sections}))
        report['lesson'] = {'id': lesson['id'], 'revision': lesson['revision'], 'status': lesson['status'], 'origin': lesson['origin'], 'goal': lesson['goal'], 'depth': lesson['depth']}
        mapping_root = f'/api/projects/{pid}/knowledge/nodes/{node["id"]}/implementations'
        report.setdefault('mappings', {})
        for key in ('teaching', 'counterexample'):
            if key in report['mappings']:
                continue
            code_source = response(client.get(f'/api/projects/{pid}/sources/{report["imports"][key]["source_id"]}'))
            block = next(b for b in code_source['blocks'] if b.get('metadata', {}).get('symbol') == 'scaled_dot_product')
            mapping = response(client.post(mapping_root, json={'paper_evidence_id': evidence['id'], 'paper_span': evidence['quote'],
                'code_source_id': code_source['id'], 'code_block_id': block['id'], 'code_span': block['text'], 'implementation_kind': 'teaching',
                'explanation': NOTICE + ('此候选的除以√d_k对应公式缩放项，尚待核对。' if key == 'teaching' else '故意设置的同名乘法反例，函数名称不能证明对应；待核对后驳回。')}))
            report['mappings'][key] = {k: mapping[k] for k in ('id', 'revision', 'status')}
            save(directory, report)
        if not report.get('note_id'):
            note = response(client.post('/api/workbench/records', json={'kind': 'note', 'title': '预置教学笔记 · 缩放分数与权重（待核对）',
                'body': NOTICE + '\n\n教学输入8/√4=4.0，只是softmax前的一个分数。请结合原页完整公式，核对何时才能称为注意力权重。',
                'project_id': pid, 'knowledge_node_id': node['id'], 'source_id': source['id'], 'block_id': evidence['block_id'],
                'source_version': source['version'], 'node_version': node['version'], 'evidence_references': [evidence], 'content_origin': 'user',
                'unresolved_questions': '待用户核对：softmax怎样将一组分数变成权重？维度缩放改变了什么？'}))
            report['note_id'] = note['id']
        artifact = fill_exercise(directory, client, report)
        report['practice_id'], report['practice_revision'] = artifact['id'], artifact['revision']
        base = f'/research/{pid}'
        report['paths'] = {'graph': base + '?view=graph&node=' + node['id'], 'learning': base + '?view=learning&node=' + node['id'],
            'practice': base + '?view=practice&node=' + node['id'], 'reading': base + '?view=reading&source=' + source['id'] + '&page=4&block=' + evidence['block_id']}
        report['stage'] = 'prepared_examples_pending_user_review'
        save(directory, report)
        with closing(sqlite3.connect(directory / 'data/atlas.db')) as conn:
            if conn.execute('SELECT COUNT(*) FROM kw_model_calls').fetchone()[0]:
                raise ValueError('Unexpected model calls: inspect isolated audit before presenting')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--api', default='http://127.0.0.1:18179')
    parser.add_argument('--phase', choices=['import', 'cache', 'prepare', 'bind-practice'], default='prepare')
    args = parser.parse_args()
    directory = profile_path(args.directory)
    result = (import_sources(directory, args.api) if args.phase == 'import' else reuse_parse(directory) if args.phase == 'cache'
              else prepare_teaching(directory, args.api, bind=args.phase == 'bind-practice'))
    print(json.dumps({'stage': result['stage'], 'project_id': result['project_id'], 'node_id': result.get('node_id'), 'manifest': str(directory / 'attention-demo.json')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
