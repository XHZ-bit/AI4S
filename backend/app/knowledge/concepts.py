"""Cross-source concept decisions grounded in two independently versioned sources."""

from __future__ import annotations

import json
import re
import unicodedata

from fastapi import HTTPException

from app.knowledge import extraction, store
from app.knowledge.graph_validity import active, current_records, teaching_node, valid_evidence
from app.tenancy import current_user

KINDS = {'concept', 'formula', 'method', 'module', 'algorithm', 'hypothesis'}
LINKED = {'comparable', 'conditions_differ'}
STOP_WORDS = {'the', 'and', 'that', 'this', 'for', 'with', 'from', 'which', 'using', 'used', 'are', 'was'}
ALIASES = (
    ('self attention', 'self-attention', '自注意力'),
    ('attention', '注意力'),
    ('softmax', '归一化指数', '归一化指数函数'),
    ('dot product', 'dot-product', '点积', '内积'),
    ('randomized controlled trial', '随机对照试验', '随机对照实验'),
    ('control group', '对照组'),
    ('sample size', '样本量'),
    ('working memory', '工作记忆'),
    ('retrieval practice', '回忆练习', '提取练习', '检索练习'),
)


def init(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS kw_concept_correspondences('
                 'id TEXT PRIMARY KEY,project_id TEXT NOT NULL,left_id TEXT NOT NULL,'
                 'right_id TEXT NOT NULL,revision INTEGER NOT NULL,data TEXT NOT NULL)')


def _normalize(text):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', text).casefold()).strip()


def _terms(text):
    normalized = _normalize(text)
    values = set(re.findall(r'[a-z][a-z0-9_]+', normalized)) - STOP_WORDS
    for phrase in re.findall(r'[\u3400-\u9fff]+', normalized):
        values.update(phrase[index:index + 2] for index in range(max(1, len(phrase) - 1)))
    for index, aliases in enumerate(ALIASES):
        if any(alias in normalized for alias in aliases):
            values.add('alias:' + str(index))
    return values


def _conditions(node):
    meta = node.get('metadata', {})
    return {key: meta[key] for key in ('conditions', 'assumptions', 'inputs', 'outputs', 'units')
            if meta.get(key)}


def _side(conn, pid, nid, *, require_evidence=False):
    node = store.record(conn, 'kw_nodes', pid, nid)
    source = store.source(conn, pid, node['source_id'], include_removed=True)
    evidence = [value for value in store.evidence(conn, pid, node.get('evidence_ids', []))
                if value['source_id'] == source['id'] and valid_evidence(value) and value.get('quote')]
    available = (active(node) and not source['removed'] and node['kind'] in KINDS and not teaching_node(node)
                 and node.get('metadata', {}).get('knowledge_role') != 'teaching_supplement')
    if require_evidence and (not available or not evidence):
        raise HTTPException(422, '两侧都需要当前可定位的原文依据，才能保存可对照或条件差异判断')
    return {'node': node, 'source_id': source['id'], 'source_title': source['title'],
            'source_version': source['version'], 'conditions': _conditions(node),
            'evidence': evidence[:6], 'evidence_fingerprint': store.identity(evidence[:6]), 'available': available}


def _valid_nodes(conn, pid):
    values = [json.loads(row[0]) for row in conn.execute(
        'SELECT data FROM kw_nodes WHERE project_id=? AND hidden=0', (pid,))]
    return [value for value in current_records(conn, pid, values)
            if value['kind'] in KINDS and not teaching_node(value)
            and value.get('metadata', {}).get('knowledge_role') != 'teaching_supplement']


def _reasons(conn, pid, side):
    try:
        live = _side(conn, pid, side['node']['id'])
    except HTTPException:
        return ['知识节点或资料已移除']
    reasons = []
    if not live['available']:
        reasons.append('知识节点或资料当前不可用')
    if side['node']['version'] != live['node']['version']:
        reasons.append('节点内容已有修订')
    if side['source_version'] != live['source_version']:
        reasons.append('原资料版本已有变化')
    current = {value['id']: value for value in live['evidence']}
    for captured in side['evidence']:
        found = current.get(captured['id'])
        if not found or any(found.get(key) != captured.get(key) for key in ('quote', 'block_id', 'source_version', 'locator')):
            reasons.append('保存的原文依据已变化或无法定位')
            break
    return reasons


def _present(conn, pid, value, nid):
    result = dict(value)
    if value['right']['node']['id'] == nid:
        result['left'], result['right'] = value['right'], value['left']
    result['stale_reasons'] = list(dict.fromkeys(_reasons(conn, pid, value['left']) + _reasons(conn, pid, value['right'])))
    result['stale'] = bool(result['stale_reasons'])
    for key in ('left', 'right'):
        try:
            result['current_' + key] = _side(conn, pid, result[key]['node']['id'])
        except HTTPException:
            result['current_' + key] = None
    return result


def collection(conn, pid, nid, q='', source_id=None):
    init(conn)
    left = _side(conn, pid, nid)
    items = [_present(conn, pid, json.loads(row[0]), nid) for row in conn.execute(
        'SELECT data FROM kw_concept_correspondences WHERE project_id=? AND (left_id=? OR right_id=?) ORDER BY rowid DESC',
        (pid, nid, nid))]
    saved = {item['right']['node']['id'] for item in items}
    label_terms = _terms(left['node']['label'])
    context_terms = _terms(left['node']['summary'] + ' ' + json.dumps(left['conditions'], ensure_ascii=False))
    query_terms = _terms(q)
    ranked = []
    for node in _valid_nodes(conn, pid):
        if node['source_id'] == left['source_id'] or source_id and node['source_id'] != source_id:
            continue
        title = _normalize(node['label'])
        text = title + ' ' + _normalize(node['summary'])
        terms = _terms(text)
        if q and not (_normalize(q) in text or query_terms & terms):
            continue
        same_name = _normalize(left['node']['label']) == title
        label_overlap = label_terms & _terms(node['label'])
        score = 20 * same_name + 5 * len(label_overlap) + len(context_terms & terms)
        ranked.append((score, same_name, bool(label_overlap), node))
    ranked.sort(key=lambda item: (-item[0], item[3]['label'], item[3]['id']))
    choices = []
    candidates = []
    for score, same_name, label_match, node in ranked:
        if len(choices) >= 40:
            break
        side = _side(conn, pid, node['id'])
        choices.append(side)
        if score and node['id'] not in saved and len(candidates) < 6:
            reason = '名称相同，定义与条件待核对' if same_name else '名称或双语术语有重合，定义待核对' if label_match else '说明中的词项有重合，含义待核对'
            candidates.append({'side': side, 'reason': reason})
    return {'node': left, 'items': items, 'candidates': candidates, 'choices': choices,
            'sources': [{'id': value['id'], 'title': value['title']} for value in store.sources(conn, pid)
                        if value['id'] != left['source_id']],
            'generation': 'local_rules', 'truncated': len(ranked) > 40}


def _check_versions(left, right, values, *, confirm=False):
    expected = (values.get('left_node_version'), values.get('right_node_version'),
                values.get('left_source_version'), values.get('right_source_version'))
    actual = (left['node']['version'], right['node']['version'], left['source_version'], right['source_version'])
    if expected != actual:
        raise HTTPException(409, '核对期间节点或资料已有变化，请重新读取双方依据')
    if confirm and (values.get('left_evidence_fingerprint') != left['evidence_fingerprint']
                    or values.get('right_evidence_fingerprint') != right['evidence_fingerprint']):
        raise HTTPException(409, '核对期间原文摘录或位置已有变化，请重新读取双方依据')


def _reviewer():
    user = current_user.get()
    return (user.get('username') or user['id']) if user else '本机用户'


def _project_edge(conn, pid, value):
    left, right = value['left'], value['right']
    evidence = [item['id'] for side in (left, right) for item in side['evidence']]
    source = store.source(conn, pid, left['source_id'], include_removed=True)
    label = '用户核对可对照' if value['status'] == 'comparable' else '用户核对条件有差异'
    relation = extraction.edge(source, left['node']['id'], right['node']['id'], 'RELATED_TO',
                               label, value['explanation'] or label, evidence, origin='user')
    # A private decision has a separate edge identity from extracted relationships.
    relation['id'] = store.identity(pid, 'concept-correspondence', value['id'])
    relation['hidden'] = value['status'] not in LINKED
    relation['metadata'] = {'concept_correspondence_id': value['id'], 'concept_correspondence_revision': value['revision'], 'knowledge_role': 'user_concept_comparison',
                            'concept_node_versions': {side['node']['id']: side['node']['version'] for side in (left, right)},
                            'concept_evidence_snapshot': [item for side in (left, right) for item in side['evidence']],
                            'comparison_decision': value['status'], 'reviewed_by': value['reviewed_by']}
    store.put_record(conn, 'kw_edges', relation, preserve_user=False)


def create(conn, pid, nid, values):
    init(conn)
    conn.execute('BEGIN IMMEDIATE')
    other = values['other_node_id']
    if other == nid:
        raise HTTPException(422, '请选择另一份资料中的知识节点')
    left = _side(conn, pid, nid, require_evidence=values['status'] in LINKED)
    right = _side(conn, pid, other, require_evidence=values['status'] in LINKED)
    if not left['available'] or not right['available']:
        raise HTTPException(422, '请选择两份有效资料中的知识节点，教学补充单独保留')
    if left['source_id'] == right['source_id']:
        raise HTTPException(422, '请选择不同资料中的知识节点')
    _check_versions(left, right, values, confirm=values['status'] in LINKED)
    identifier = store.identity(pid, 'concept-pair', sorted((nid, other)))
    if conn.execute('SELECT 1 FROM kw_concept_correspondences WHERE id=? AND project_id=?', (identifier, pid)).fetchone():
        raise HTTPException(409, '这对知识已有保存的判断，请打开原判断修订')
    result = {'id': identifier, 'left': left, 'right': right, 'status': values['status'],
              'explanation': values.get('explanation', '').strip(), 'revision': 1, 'origin': 'user',
              'reviewed_by': _reviewer(), 'reviewed_at': store.now()}
    conn.execute('INSERT INTO kw_concept_correspondences VALUES(?,?,?,?,?,?)',
                 (identifier, pid, nid, other, 1, store.encode(result)))
    _project_edge(conn, pid, result)
    return _present(conn, pid, result, nid)


def revise(conn, pid, nid, identifier, values):
    init(conn)
    conn.execute('BEGIN IMMEDIATE')
    row = conn.execute('SELECT data FROM kw_concept_correspondences WHERE id=? AND project_id=? AND (left_id=? OR right_id=?)',
                       (identifier, pid, nid, nid)).fetchone()
    if not row:
        raise HTTPException(404, '核对记录不属于当前知识节点')
    old = json.loads(row[0])
    if old['revision'] != values['expected_revision']:
        raise HTTPException(409, '判断已有新的修订，请重新读取')
    result = {**old, 'status': values['status'], 'explanation': values.get('explanation', '').strip(),
              'revision': old['revision'] + 1, 'reviewed_by': _reviewer(), 'reviewed_at': store.now()}
    if values['status'] in LINKED:
        view = _present(conn, pid, old, nid)
        left = _side(conn, pid, view['left']['node']['id'], require_evidence=True)
        right = _side(conn, pid, view['right']['node']['id'], require_evidence=True)
        _check_versions(left, right, values, confirm=True)
        result['left'], result['right'] = (left, right) if old['left']['node']['id'] == nid else (right, left)
    conn.execute('INSERT INTO kw_history(project_id,record_id,kind,data,created_at) VALUES(?,?,?,?,?)',
                 (pid, identifier, 'concept_correspondence', store.encode(old), store.now()))
    conn.execute('UPDATE kw_concept_correspondences SET revision=?,data=? WHERE id=? AND project_id=?',
                 (result['revision'], store.encode(result), identifier, pid))
    _project_edge(conn, pid, result)
    return _present(conn, pid, result, nid)
