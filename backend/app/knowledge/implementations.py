"""User-reviewed correspondences between knowledge and source-code fragments."""

import json
import math
import re
from itertools import islice
from uuid import uuid4

from fastapi import HTTPException

from app.knowledge import extraction, store
from app.knowledge.graph_validity import valid_evidence
from app.tenancy import current_user


def setup(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS kw_implementations (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, node_id TEXT NOT NULL, revision INTEGER NOT NULL, data TEXT NOT NULL)')
    conn.execute('CREATE INDEX IF NOT EXISTS kw_impl_node ON kw_implementations(project_id,node_id)')


def _inputs(conn, pid, nid):
    node = store.record(conn, 'kw_nodes', pid, nid)
    paper = [e for e in store.evidence(conn, pid, node.get('evidence_ids', [])) if e.get('source_id') == node['source_id']]
    code_sources = []
    for src in store.sources(conn, pid):
        if src.get('kind') != 'code':
            continue
        blocks = [b for b in store.source_blocks(conn, src['asset_id']) if b.get('kind') == 'code']
        code_sources.append({'id': src['id'], 'title': src['title'], 'version': src['version'], 'blocks': blocks})
    return node, paper, code_sources


def _render(conn, pid, item):
    value = dict(item)
    reasons = []
    for prefix in ('paper', 'code'):
        eid = item.get(prefix + '_evidence_id')
        matches = store.evidence(conn, pid, [eid]) if eid else []
        live = matches[0] if matches else None
        snapshot = item.get(prefix + '_evidence_snapshot')
        evidence = dict(snapshot) if snapshot else (dict(live) if live else None)
        if evidence:
            row = conn.execute('SELECT removed,data FROM kw_sources WHERE id=? AND project_id=?',
                               (evidence['source_id'], pid)).fetchone()
            src = json.loads(row[1]) if row else None
            expected = item.get('source_versions', {}).get(prefix)
            evidence['source_missing'] = not row or bool(row[0])
            evidence['source_changed'] = bool(src and expected and src.get('version') != expected)
            block = conn.execute('SELECT data FROM kw_blocks WHERE id=? AND asset_id=?',
                                 (evidence['block_id'], src['asset_id'])).fetchone() if src else None
            evidence['unresolved'] = (not live or not block or
                bool(evidence.get('quote') and evidence['quote'] not in json.loads(block[0]).get('text', '')))
        value[prefix + '_evidence'] = evidence
        if not evidence:
            reasons.append(prefix + '_evidence_missing')
        elif not valid_evidence(evidence):
            reasons.append(prefix + '_evidence_changed_or_missing')
    try:
        node = store.record(conn, 'kw_nodes', pid, item['node_id'])
        if node['version'] != item.get('node_version'):
            reasons.append('node_changed')
        if node.get('hidden') or node.get('source_missing'):
            reasons.append('node_unavailable')
    except HTTPException:
        reasons.append('node_missing')
    value['stale_reasons'] = reasons
    value['stale'] = bool(reasons)
    return value


def list_mappings(conn, pid, nid):
    setup(conn)
    store.record(conn, 'kw_nodes', pid, nid)
    return [_render(conn, pid, json.loads(row[0])) for row in conn.execute(
        'SELECT data FROM kw_implementations WHERE project_id=? AND node_id=? ORDER BY rowid DESC', (pid, nid))]


def collection(conn, pid, nid):
    node, paper, sources = _inputs(conn, pid, nid)
    return {'items': list_mappings(conn, pid, nid), 'code_sources': sources, 'paper_evidence': paper}


def _prepare(conn, pid, nid, data, *, mid=None, origin='user'):
    node, paper, sources = _inputs(conn, pid, nid)
    if node.get('hidden') or node.get('source_missing'):
        raise HTTPException(400, '当前知识节点已隐藏或来源不可用')
    src = next((s for s in sources if s['id'] == data.get('code_source_id')), None)
    block = next((b for b in src['blocks'] if b['id'] == data.get('code_block_id')), None) if src else None
    if not src or not block:
        raise HTTPException(400, '代码片段不在当前研究空间的有效代码资料中')
    paper_id = data.get('paper_evidence_id') or None
    paper_item = next((e for e in paper if e['id'] == paper_id), None) if paper_id else None
    if paper_id and (not paper_item or paper_item.get('source_id') != node['source_id']):
        raise HTTPException(400, '论文依据不属于当前节点')
    paper_span, code_span = data.get('paper_span', '').strip(), data.get('code_span', '').strip()
    if paper_span and (not paper_item or paper_span not in paper_item.get('quote', '')):
        raise HTTPException(400, '论文片段必须来自所选节点依据')
    if code_span and code_span not in block.get('text', ''):
        raise HTTPException(400, '代码片段必须来自所选代码块')
    start, end = data.get('start_line'), data.get('end_line')
    meta = block.get('metadata') or {}
    block_start, block_end = meta.get('start_line'), meta.get('end_line')
    if (start is None) != (end is None) or (start is not None and (start < 1 or end < start or not isinstance(block_start, int) or not isinstance(block_end, int) or start < block_start or end > block_end)):
        raise HTTPException(400, '行号超出所选代码块')
    actual_start = actual_end = None
    if code_span and isinstance(block_start, int):
        text = block.get('text', '')
        positions = [m.start() for m in re.finditer(re.escape(code_span), text)]
        for offset in positions:
            first = block_start + text[:offset].count('\n')
            last = first + code_span.count('\n')
            if start is None or start <= first <= last <= end:
                actual_start, actual_end = first, last
                break
        if actual_start is None:
            raise HTTPException(400, '代码片段不在所选行号范围内')
    source = store.source(conn, pid, src['id'])
    code_id = store.add_evidence(conn, pid, source, block, quote=code_span or None)
    evidence = store.evidence(conn, pid, [code_id])[0]
    if actual_start is not None:
        evidence['locator'] = {**evidence['locator'], 'start_line': actual_start, 'end_line': actual_end}
    code_id = store.identity(pid, src['id'], block['id'], code_span, actual_start, actual_end, src['version'])
    evidence['id'] = code_id
    conn.execute('INSERT OR REPLACE INTO kw_evidence VALUES(?,?,?,?)', (code_id, pid, src['id'], store.encode(evidence)))
    return {'id': mid or uuid4().hex, 'node_id': nid, 'paper_evidence_id': paper_id,
        'code_evidence_id': code_id, 'code_source_id': src['id'], 'code_block_id': block['id'],
        'paper_span': paper_span, 'code_span': code_span, 'explanation': data.get('explanation', ''),
        'paper_evidence_snapshot': paper_item, 'code_evidence_snapshot': evidence,
        'implementation_kind': data.get('implementation_kind', 'source'), 'status': 'proposed', 'revision': 1,
        'node_version': node['version'], 'source_versions': {'paper': paper_item.get('source_version') if paper_item else None, 'code': src['version']},
        'start_line': actual_start, 'end_line': actual_end, 'origin': origin, 'created_at': store.now(), 'practice_id': data.get('practice_id')}


def _write(conn, pid, item, previous=None):
    setup(conn)
    if previous is None:
        conn.execute('INSERT INTO kw_implementations VALUES(?,?,?,?,?)', (item['id'], pid, item['node_id'], item['revision'], store.encode(item)))
    else:
        changed = conn.execute('UPDATE kw_implementations SET revision=?,data=? WHERE id=? AND project_id=? AND revision=?',
            (item['revision'], store.encode(item), item['id'], pid, previous['revision'])).rowcount
        if not changed:
            raise HTTPException(409, '对应关系已被修改，请重新读取')
        conn.execute('INSERT INTO kw_history(project_id,record_id,kind,data,created_at) VALUES(?,?,?,?,?)',
            (pid, item['id'], 'implementation', store.encode(previous), store.now()))


def create(conn, pid, nid, data, *, mid=None, origin='user'):
    setup(conn)
    item = _prepare(conn, pid, nid, data, mid=mid, origin=origin)
    _write(conn, pid, item)
    return _render(conn, pid, item)


def _edge(conn, pid, item):
    node = store.record(conn, 'kw_nodes', pid, item['node_id'])
    src = store.source(conn, pid, item['code_source_id'])
    code = extraction.node(src, 'implementation:' + item['id'], 'algorithm', '代码片段', item['code_span'][:3500],
                           [item['code_evidence_id']], parent_id=store.identity(pid, src['id'], 'root'), origin='user')
    store.put_record(conn, 'kw_nodes', code)
    edge = extraction.edge(store.source(conn, pid, node['source_id']), node['id'], code['id'], 'IMPLEMENTED_BY',
                           '用户确认的代码对应', item['explanation'], [item['paper_evidence_id'], item['code_evidence_id']], origin='user')
    edge['metadata']['implementation_mapping_id'] = item['id']
    edge['hidden'] = item['status'] != 'confirmed' or item['implementation_kind'] != 'source'
    store.put_record(conn, 'kw_edges', edge, preserve_user=False)


def _hide_edge(conn, pid, item):
    code_id = store.identity(pid, item['code_source_id'], 'implementation:' + item['id'])
    edge_id = store.identity(pid, item['node_id'], code_id, 'IMPLEMENTED_BY')
    row = conn.execute('SELECT data FROM kw_edges WHERE id=? AND project_id=?', (edge_id, pid)).fetchone()
    if row:
        edge = json.loads(row[0])
        edge['hidden'] = True
        store.put_record(conn, 'kw_edges', edge, preserve_user=False)


def revise(conn, pid, nid, mid, data):
    setup(conn)
    row = conn.execute('SELECT data FROM kw_implementations WHERE id=? AND project_id=? AND node_id=?', (mid, pid, nid)).fetchone()
    if not row:
        raise HTTPException(404, '对应关系不在当前研究空间')
    old = json.loads(row[0])
    if old['revision'] != data['expected_revision']:
        raise HTTPException(409, '对应关系已被修改，请重新读取')
    if data.get('practice_id') is not None:
        from app.knowledge import practice
        table = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='kw_practice'").fetchone()
        if not table:
            raise HTTPException(404, '练习不在当前研究空间')
        exercise = practice.record(conn, pid, data['practice_id'])
        if exercise['node_id'] != nid:
            raise HTTPException(404, '练习不属于当前知识节点')
    clearable = {'paper_evidence_id', 'start_line', 'end_line', 'practice_id'}
    changes = {k: v for k, v in data.items() if k != 'expected_revision' and (v is not None or k in clearable)}
    if changes.get('paper_evidence_id', old.get('paper_evidence_id')) is None:
        changes.setdefault('paper_span', '')
    if {'code_source_id', 'code_block_id'} & changes.keys() and 'start_line' not in changes and 'end_line' not in changes:
        changes.update(start_line=None, end_line=None)
    content_keys = {'paper_evidence_id', 'code_source_id', 'code_block_id', 'paper_span', 'code_span', 'explanation', 'implementation_kind', 'start_line', 'end_line'}
    if content_keys & changes.keys():
        item = _prepare(conn, pid, nid, {**old, **changes}, mid=mid, origin=old['origin'])
        item['created_at'] = old['created_at']
        item['practice_id'] = changes.get('practice_id', old.get('practice_id'))
        item['status'] = changes.get('status', 'proposed')
    else:
        item = {**old, **changes}
    item['revision'] = old['revision'] + 1
    if item['status'] == 'confirmed':
        view = _render(conn, pid, item)
        if view['stale'] or not item['paper_span'] or not item['code_span']:
            raise HTTPException(400, '确认前需要有效的论文依据和代码精确片段')
        if old['status'] != 'confirmed' or 'status' in changes or content_keys & changes.keys():
            user = current_user.get()
            item['reviewed_by'] = (user.get('username') or user.get('id')) if user else '本机用户'
            item['reviewed_at'] = store.now()
    elif old['status'] == 'confirmed':
        item.pop('reviewed_by', None)
        item.pop('reviewed_at', None)
    if old['status'] == 'confirmed' and (item['status'] != 'confirmed' or content_keys & changes.keys()):
        _hide_edge(conn, pid, old)
    if item['status'] == 'confirmed':
        _edge(conn, pid, item)
    _write(conn, pid, item, old)
    return _render(conn, pid, item)


def candidates(node, paper, sources, result=None):
    """Use only exact substrings and allowlisted blocks. All output remains a proposal."""
    available = {(s['id'], b['id']): b for s in sources for b in s['blocks']}
    pmap = {e['id']: e for e in paper if valid_evidence(e) and e.get('source_id') == node['source_id']}
    proposals = []
    raw_items = (result or {}).get('items', [])
    if not isinstance(raw_items, list):
        raw_items = []
    for v in raw_items:
        if not isinstance(v, dict):
            continue
        block = available.get((v.get('code_source_id'), v.get('code_block_id')))
        ev = pmap.get(v.get('paper_evidence_id'))
        ps, cs = v.get('paper_span'), v.get('code_span')
        if block and ev and isinstance(ps, str) and ps.strip() and ps.strip() in ev.get('quote', '') and isinstance(cs, str) and cs.strip() and cs.strip() in block.get('text', ''):
            proposals.append({'code_source_id': v['code_source_id'], 'code_block_id': v['code_block_id'], 'paper_evidence_id': ev['id'],
                'paper_span': ps.strip(), 'code_span': cs.strip(), 'explanation': str(v.get('explanation', ''))[:3500], 'implementation_kind': 'source'})
    if proposals:
        return proposals[:12], 'model'
    terms = _terms(node)
    ranked = [(_block_score(b, terms, set()), s, b) for s in sources for b in s['blocks']]
    ranked = sorted(ranked, key=lambda x: x[0], reverse=True)
    ev = next(iter(pmap.values()), None)
    for score, src, block in ranked[:8]:
        if score[1] <= 0:
            continue
        proposals.append({'code_source_id': src['id'], 'code_block_id': block['id'], 'paper_evidence_id': ev['id'] if ev else None,
            'paper_span': ev.get('quote', '')[:250] if ev else '', 'code_span': snippet_window(node, block.get('text', ''), 250),
            'explanation': '名称匹配产生的待核对候选，不证明代码实现该方法。', 'implementation_kind': 'source'})
    return proposals, 'rule'


def _terms(node):
    text = (node.get('label', '') + ' ' + node.get('summary', '')).lower()
    terms = set(re.findall(r'[a-zA-Z_][a-zA-Z_0-9]{2,}', text))
    for word, synonyms in {'门控': ('gate', 'gating'), '残差': ('residual',), '裁剪': ('clip',),
                           '分布': ('distribution',), '策略': ('policy', 'actor'), '分支': ('branch',)}.items():
        if word in text:
            terms.update(synonyms)
    return terms


def _block_score(block, terms, linked_ids):
    meta = block.get('metadata') or {}
    title = (str(block.get('heading', '')) + ' ' + str(meta.get('symbol', ''))).lower()
    text = block.get('text', '').lower()
    title_score = sum(term in title for term in terms)
    text_score = sum(term in text for term in terms) / math.sqrt(max(1, len(text) / 2000))
    return (block['id'] in linked_ids, 3 * title_score + text_score, meta.get('symbol_kind') == 'function')


def rank_blocks(node, source, linked_ids):
    terms = _terms(node)
    return sorted(source['blocks'], key=lambda block: _block_score(block, terms, linked_ids), reverse=True)


def snippet_window(node, text, max_chars=2000):
    """Return one contiguous, bounded slice centred on the most relevant terms."""
    if len(text) <= max_chars:
        return text
    lowered = text.lower()
    terms = sorted(_terms(node), key=lambda value: (-len(value), value))[:40]
    positions = []
    for term in terms:
        positions.extend(m.start() for m in islice(re.finditer(re.escape(term), lowered), 5))
    if not positions:
        return text[:max_chars]
    def window(offset):
        start = min(max(0, offset - max_chars // 2), len(text) - max_chars)
        return start, text[start:start + max_chars]
    _, result = max((window(offset) for offset in positions),
                    key=lambda item: sum(term in item[1].lower() for term in terms))
    return result
