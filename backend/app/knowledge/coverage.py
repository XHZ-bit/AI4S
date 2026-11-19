"""Read source-grounded content coverage and explicitly supplement one category."""

from __future__ import annotations

import json
import re
from uuid import uuid4

from fastapi import HTTPException

from app.db import projects
from app.knowledge import extraction, model, store
from app.knowledge.graph_validity import current_records, valid_evidence
from app.tenancy import current_user

CATEGORIES = {
    'problem': ('研究问题', r'problem|question|motivat|introduction|研究问题|问题|背景'),
    'method': ('核心方法', r'method|approach|model|algorithm|design|方法|模型|机制|研究设计'),
    'experiment': ('实验与条件', r'experiment|evaluat|participant|sample|procedure|实验|评估|样本|条件'),
    'finding': ('主要发现', r'result|finding|conclusion|performance|结果|发现|结论|效果'),
    'limitation': ('局限与范围', r'limitation|discussion|future|constraint|局限|讨论|范围|不足|限制'),
}


def _source_input(conn, pid, sid):
    source = store.source(conn, pid, sid, blocks=True)
    fingerprint = store.identity(source['version'], source['blocks'])
    return source, fingerprint


def _nodes(conn, pid, sid):
    values = [json.loads(row[0]) for row in conn.execute(
        'SELECT data FROM kw_nodes WHERE project_id=? AND source_id=? AND hidden=0', (pid, sid))]
    current = current_records(conn, pid, values)
    return [n for n in current if n['kind'] in extraction.NODE_KINDS and n.get('evidence_ids') and not n.get('metadata', {}).get('structural')
            and not n.get('metadata', {}).get('educational')]


def inspect(conn, pid, sid):
    source, fingerprint = _source_input(conn, pid, sid)
    nodes = _nodes(conn, pid, sid)
    decisions = source.get('coverage_decisions', {})
    items = []
    for key, (label, _) in CATEGORIES.items():
        matches = [n for n in nodes if n['kind'] == key]
        evidence_ids = list(dict.fromkeys(eid for n in matches for eid in n['evidence_ids']))
        evidence = [e for e in store.evidence(conn, pid, evidence_ids) if valid_evidence(e)]
        decision = decisions.get(key)
        decision_stale = bool(decision and (decision.get('input_fingerprint') != fingerprint or matches))
        state = 'covered' if matches else 'missing' if nodes else 'not_extracted'
        if decision and not decision_stale:
            state = decision['status']
        items.append({'category': key, 'label': label, 'state': state, 'node_count': len(matches),
                      'evidence_count': len(evidence),
                      'nodes': [{'id': n['id'], 'label': n['label'], 'version': n['version']} for n in matches[:5]],
                      'evidence': evidence[:6], 'decision': decision, 'decision_stale': decision_stale})
    return {'source_id': sid, 'source_title': source['title'], 'source_version': source['version'],
            'revision': source.get('coverage_revision', 0), 'items': items,
            'parsed': bool(source['blocks']), 'semantic_node_count': len(nodes),
            'analysis_running': (source.get('analysis') or {}).get('status') in {'queued', 'running'},
            'model_available': model.available(),
            'scope': '仅检查当前已保存且有可定位依据的知识覆盖。缺项需结合原文核对，覆盖不代表科学结论完整。'}


def _check_version(source, expected_source_version, expected_revision):
    if source['version'] != expected_source_version or source.get('coverage_revision', 0) != expected_revision:
        raise HTTPException(409, '资料或覆盖记录已有变化，请重新读取后操作')


def review(pid, sid, category, status, reason, expected_source_version, expected_revision):
    if category not in CATEGORIES or status not in {'not_reported', 'not_applicable', 'reset'}:
        raise HTTPException(422, '覆盖判断不在支持范围内')
    if status != 'reset' and not reason.strip():
        raise HTTPException(422, '请写下判断理由，便于以后复核')
    with store.connection(pid) as conn:
        conn.execute('BEGIN IMMEDIATE')
        source, fingerprint = _source_input(conn, pid, sid)
        _check_version(source, expected_source_version, expected_revision)
        if status != 'reset' and any(n['kind'] == category for n in _nodes(conn, pid, sid)):
            raise HTTPException(422, '这一项已有带依据的知识，请先核对这些节点')
        decisions = dict(source.get('coverage_decisions', {}))
        previous = decisions.get(category)
        if status == 'reset':
            decisions.pop(category, None)
        else:
            user = current_user.get()
            decisions[category] = {'status': status, 'reason': reason.strip(), 'origin': 'user',
                                   'source_version': source['version'], 'input_fingerprint': fingerprint,
                                   'reviewed_at': store.now(),
                                   'reviewed_by': (user.get('username') or user['id']) if user else '本机用户'}
        store.update_source(conn, pid, sid, {'coverage_decisions': decisions,
                                           'coverage_revision': expected_revision + 1})
        conn.execute('INSERT INTO kw_history(project_id,record_id,kind,data,created_at) VALUES(?,?,?,?,?)',
                     (pid, sid, 'source_coverage_review', store.encode({'category': category, 'previous': previous,
                      'decision': decisions.get(category), 'revision': expected_revision + 1}), store.now()))
        return inspect(conn, pid, sid)


def _select_blocks(blocks, category):
    pattern = CATEGORIES[category][1]
    candidates = [b for b in blocks if b.get('text', '').strip()
                  and not re.match(r'^\s*(references|bibliography|参考文献)\b', b.get('heading', ''), re.I)]
    candidates.sort(key=lambda b: (-int(bool(re.search(pattern, b.get('heading', ''), re.I))) * 2
                                  - int(bool(re.search(pattern, b.get('text', ''), re.I))), b['ordinal']))
    selected, length = [], 0
    for block in candidates:
        if len(selected) >= 8 or length >= 10000:
            break
        text = block['text'][:min(2200, 10000 - length)]
        selected.append({'block_id': block['id'], 'heading': block.get('heading', ''),
                         'page': block.get('page'), 'kind': block.get('kind', 'text'), 'text': text})
        length += len(text)
    return selected


def supplement(pid, sid, category, expected_source_version, expected_revision):
    if category not in CATEGORIES:
        raise HTTPException(422, '补充类型不在支持范围内')
    with model.operation(pid, 'coverage:' + sid + ':' + category):
        with store.connection(pid) as conn:
            source, fingerprint = _source_input(conn, pid, sid)
            _check_version(source, expected_source_version, expected_revision)
            if (source.get('analysis') or {}).get('status') in {'queued', 'running'}:
                raise HTTPException(409, '这份资料正在分析，完成后可针对缺项补充')
            project = projects.get_project(conn, pid)
            decision = source.get('coverage_decisions', {}).get(category)
            blocks = _select_blocks(source['blocks'], category)
        if not blocks:
            raise HTTPException(409, '资料尚无可用的解析片段，可先阅读原文或继续知识分析')
        if not model.available():
            raise HTTPException(503, '模型服务暂不可用，已有内容和人工覆盖判断仍可查看')
        budget = model.Budget(pid, uuid4().hex, limit=1)
        try:
            result = model.structured(extraction.SYSTEM + '\n本次只补充指定category类型。原文没有报告就返回空nodes，'
                                      '不可用背景、引用文献或教学猜测填补。最多4个节点。',
                                      {'source_title': source['title'], 'source_kind': source['kind'],
                                       'research_question': project.research_question,
                                       'category': category, 'blocks': blocks},
                                      budget, 'source_coverage_supplement', max_tokens=2600)
        except model.ModelUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        if not isinstance(result, dict) or not isinstance(result.get('nodes'), list):
            raise HTTPException(502, '补充分析未返回可用知识，原有内容已保留')
        selected = [node for node in result['nodes'] if isinstance(node, dict) and node.get('kind') == category][:4]
        with store.connection(pid) as conn:
            conn.execute('BEGIN IMMEDIATE')
            current, current_fingerprint = _source_input(conn, pid, sid)
            analysis = source.get('analysis') or {}
            current_analysis = current.get('analysis') or {}
            analysis_changed = any(analysis.get(key) != current_analysis.get(key) for key in ('id', 'status', 'updated_at'))
            if current_fingerprint != fingerprint or current.get('coverage_decisions', {}).get(category) != decision or analysis_changed:
                raise HTTPException(409, '补充期间资料或本项人工判断已有变化，请重新核对后操作')
            root = store.identity(pid, sid, 'root')
            if not conn.execute('SELECT 1 FROM kw_nodes WHERE project_id=? AND id=?', (pid, root)).fetchone():
                extraction.structural_graph(conn, current, current['blocks'])
            # Grounding is restricted to the excerpts actually supplied to the model.
            allowed = {block['block_id']: block for block in blocks}
            for node in selected:
                citations = node.get('evidence', [])
                if not isinstance(citations, list):
                    continue
                if any(not isinstance(c, dict) or c.get('block_id') not in allowed
                       or not isinstance(c.get('quote'), str)
                       or c['quote'] not in allowed[c['block_id']]['text'] for c in citations):
                    node['evidence'] = []
            count, warnings = extraction.save_extraction(conn, current, {'nodes': selected, 'edges': []}, current['blocks'],
                                                        generation='supplement:' + budget.run_id)
            revision = current.get('coverage_revision', 0) + 1
            store.update_source(conn, pid, sid, {'coverage_revision': revision})
            receipt = {'category': category, 'added_or_refreshed': count, 'warnings': warnings,
                       'source_version': current['version'], 'usage': budget.usage, 'created_at': store.now()}
            conn.execute('INSERT INTO kw_history(project_id,record_id,kind,data,created_at) VALUES(?,?,?,?,?)',
                         (pid, sid, 'source_coverage_supplement', store.encode(receipt), receipt['created_at']))
            return {**inspect(conn, pid, sid), 'supplement': receipt,
                    'notice': '已保存带原文依据的补充知识，请逐项核对。' if count else '本次未新增可定位知识，请核对原文是否报告了这一项。'}
