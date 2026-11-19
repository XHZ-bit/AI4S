"""A personal, persistent itinerary over real prerequisite relationships.

Itinerary completion is a task decision, never a certification of understanding.
Reads and previews do not invoke a model or alter the knowledge graph.
"""

from __future__ import annotations

from collections import defaultdict, deque
import json

from fastapi import HTTPException

from app.api.workbench import project_or_404
from app.knowledge import experience, store
from app.tenancy import current_user

MAX_STEPS = 40
MAX_DEPTH = 6
STATES = {'todo', 'done', 'skipped'}


def init(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS kw_learning_routes('
                 'project_id TEXT PRIMARY KEY,revision INTEGER NOT NULL,data TEXT NOT NULL)')


def _actor():
    user = current_user.get()
    return (user.get('username') or user['id']) if user else '本机用户'


def _question(conn, pid):
    project = project_or_404(conn, pid)
    if hasattr(project, 'model_dump'):
        project = project.model_dump()
    return project.get('research_question', '')


def _raw(conn, pid):
    row = conn.execute('SELECT data FROM kw_learning_routes WHERE project_id=?', (pid,)).fetchone()
    return json.loads(row[0]) if row else None


def _evidence(conn, pid, ids):
    keys = ('id', 'source_id', 'source_title', 'block_id', 'source_version', 'quote',
            'origin', 'locator', 'source_missing', 'source_changed', 'unresolved')
    return [{key: value[key] for key in keys if key in value}
            for value in store.evidence(conn, pid, ids)]


def _node(value):
    keys = ('id', 'project_id', 'source_id', 'kind', 'label', 'summary', 'version',
            'evidence_ids', 'origin', 'quality_status', 'hidden', 'metadata')
    return {key: value[key] for key in keys if key in value}


def _edge(conn, pid, value):
    return {**_node(value), **{key: value[key] for key in ('source', 'target', 'explanation')},
            'evidence': _evidence(conn, pid, value.get('evidence_ids', []))}


def _context(conn, pid, nid, nodes, edges):
    try:
        node = store.record(conn, 'kw_nodes', pid, nid)
        source = store.source(conn, pid, node['source_id'], include_removed=True)
    except HTTPException:
        return None
    snapshot = {
        'node': _node(node),
        'source': {key: source[key] for key in ('id', 'title', 'version', 'removed', 'asset_id')},
        'evidence': _evidence(conn, pid, node.get('evidence_ids', [])),
        'prerequisites': [_edge(conn, pid, value) for value in edges
                          if value['kind'] == 'PREREQUISITE_OF' and value['target'] == nid],
        'available': nid in nodes,
    }
    snapshot['fingerprint'] = store.identity('learning-route-context-v1', snapshot)
    return snapshot


def _step(context, target):
    node = context['node']
    return {'node_id': node['id'], 'label': node['label'],
            'role': 'target' if node['id'] == target else 'prerequisite',
            'state': 'todo', 'snapshot': context}


def _reasons(saved, current):
    if current is None:
        return ['知识节点或其来源已移除']
    reasons = []
    title = saved['source']['title']
    if current['source']['removed']:
        reasons.append(f'来源“{title}”已移除')
    elif saved['source']['version'] != current['source']['version']:
        reasons.append(f'来源“{title}”版本已有变化')
    if saved['node'] != current['node']:
        reasons.append('知识节点内容已有修订')
    if saved['evidence'] != current['evidence']:
        reasons.append(f'来源“{title}”的依据内容或位置已变化')
    if saved['prerequisites'] != current['prerequisites']:
        reasons.append('前置关系或其依据已有增删修订')
    if not current['available']:
        reasons.append('节点或原文依据当前不可用')
    return reasons


def _present_step(value, context):
    reasons = _reasons(value['snapshot'], context)
    evidence = context['evidence'] if context else []
    warnings = []
    if not evidence:
        warnings.append('此步骤尚无直接原文依据；学习安排不代表已核实知识。')
    if any(not edge.get('evidence') for edge in value['snapshot']['prerequisites']):
        warnings.append('部分前置关系未附原文依据，请核对关系说明。')
    return {**value, 'stale': bool(reasons), 'stale_reasons': reasons,
            'available': bool(context and context['available']), 'warnings': warnings,
            'current_context': context['fingerprint'] if context else None,
            'current_node': context['node'] if context else None,
            'current_source': context['source'] if context else None,
            'current_evidence': evidence}


def _present(conn, pid, value, graph=None):
    nodes, edges, _ = graph or experience.graph_records(conn, pid)
    steps = [_present_step(step, _context(conn, pid, step['node_id'], nodes, edges))
             for step in value['steps']]
    # A current descendant is not a safe next suggestion while an upstream
    # step needs review. Stored and current arrows are both relevant when a
    # changed relationship has disappeared from the live graph.
    blocked = {step['node_id'] for step in steps if step['stale'] or not step['available']}
    prerequisites = {step['node_id']: {edge['source'] for edge in step['snapshot']['prerequisites']}
                     for step in steps}
    route_node_ids = set(prerequisites)
    missing_prerequisites = set()
    for edge in edges:
        if edge['kind'] == 'PREREQUISITE_OF' and edge['target'] in prerequisites:
            prerequisites[edge['target']].add(edge['source'])
            if edge['source'] not in route_node_ids:
                missing_prerequisites.add(edge['source'])
    blocked |= missing_prerequisites
    for _ in steps:
        downstream = {nid for nid, before in prerequisites.items() if before & blocked}
        if downstream <= blocked:
            break
        blocked |= downstream
    for step in steps:
        step['blocked_by'] = sorted(prerequisites[step['node_id']] & blocked)
    included = {step['node_id'] for step in steps if step['available'] and not step['stale']}
    route_edges = [edge for edge in edges if edge['kind'] == 'PREREQUISITE_OF'
                   and edge['source'] in included and edge['target'] in included]
    changed = value['research_question'] != _question(conn, pid)
    warnings = list(value.get('warnings', []))
    if changed:
        warnings.append('当前研究问题已改变；路线仍保留保存时的问题，可预览并更新路线。')
    if any(step['stale'] for step in steps):
        warnings.append('部分步骤的知识、来源或前置关系已有变化，请逐项复核。')
    if missing_prerequisites:
        warnings.append('有前置知识尚未加入路线，请重新规划；逐项复核不会自动补入遗漏步骤。')
    next_step = next((step for step in steps if step['state'] == 'todo'
                      and step['available'] and not step['stale'] and not step['blocked_by']), None)
    return {**value, 'steps': steps, 'edges': route_edges, 'warnings': list(dict.fromkeys(warnings)),
            'stale': any(step['stale'] for step in steps), 'question_changed': changed,
            'needs_replan': bool(missing_prerequisites),
            'next_node_id': next_step['node_id'] if next_step else None,
            'graph': {'nodes': [nodes[step['node_id']] for step in steps if step['node_id'] in included],
                      'edges': route_edges}}


def get(conn, pid):
    init(conn)
    value = _raw(conn, pid)
    return {'route': _present(conn, pid, value) if value else None}


def preview(conn, pid, target_node_id):
    init(conn)
    question = _question(conn, pid)
    target = experience.active_node(conn, pid, target_node_id)
    graph = experience.graph_records(conn, pid)
    nodes, edges, truncated = graph
    # The bounded full-graph query may omit a valid target. Its own context can
    # still be previewed without inventing an unexplored prerequisite chain.
    if target_node_id not in nodes:
        nodes = {**nodes, target_node_id: target}
        graph = nodes, edges, True
        truncated = True
    incoming = defaultdict(list)
    for edge in edges:
        if edge['kind'] == 'PREREQUISITE_OF':
            incoming[edge['target']].append(edge)
    selected = {target_node_id}
    queue = deque([(target_node_id, 0)])
    while queue:
        nid, depth = queue.popleft()
        for edge in sorted(incoming[nid], key=lambda item: (nodes[item['source']]['label'], item['id'])):
            before = edge['source']
            if before in selected:
                continue
            if depth >= MAX_DEPTH or len(selected) >= MAX_STEPS:
                truncated = True
                continue
            selected.add(before)
            queue.append((before, depth + 1))
    selected_edges = [edge for edge in edges if edge['kind'] == 'PREREQUISITE_OF'
                      and edge['source'] in selected and edge['target'] in selected]
    indegree = {nid: 0 for nid in selected}
    outgoing = defaultdict(list)
    for edge in selected_edges:
        indegree[edge['target']] += 1
        outgoing[edge['source']].append(edge['target'])
    def key(nid):
        return nodes[nid]['label'], nid
    ready = sorted((nid for nid in selected if indegree[nid] == 0), key=key)
    order = []
    while ready:
        nid = ready.pop(0)
        order.append(nid)
        for after in outgoing[nid]:
            indegree[after] -= 1
            if indegree[after] == 0:
                ready.append(after)
                ready.sort(key=key)
    cycle = len(order) != len(selected)
    # Cyclic nodes are displayed explicitly. Their list position is only a
    # personal itinerary and never a valid topological proof.
    if cycle:
        order += sorted(selected - set(order) - {target_node_id}, key=key)
        if target_node_id not in order:
            order.append(target_node_id)
    steps = [_step(_context(conn, pid, nid, nodes, edges), target_node_id) for nid in order]
    warnings = []
    if cycle:
        warnings.append('前置关系存在循环，无法得出唯一先后顺序；请核对关系，也可自行选择目标。')
    if truncated:
        warnings.append(f'本次最多显示{MAX_STEPS}步、{MAX_DEPTH}层前置关系或有界图谱；仍有关系未展开。')
    if len(steps) == 1:
        warnings.append('当前没有已保存的有效前置关系，仅列出目标；不会补造学习路径。')
    if any(not step['snapshot']['evidence'] for step in steps):
        warnings.append('部分步骤尚无直接原文依据，可作为个人学习安排，内容仍需核对。')
    current = _raw(conn, pid)
    if current and current['target_node_id'] == target_node_id:
        old = {step['node_id']: step for step in current['steps']}
        for step in steps:
            previous = old.get(step['node_id'])
            if previous and not _reasons(previous['snapshot'], step['snapshot']):
                step['state'] = previous['state']
        steps = _merge_order(current['steps'], steps)
    data = {'project_id': pid, 'target_node_id': target_node_id, 'target_label': target['label'],
            'research_question': question, 'steps': steps, 'edges': selected_edges, 'warnings': warnings,
            'cycle_detected': cycle, 'truncated': bool(truncated)}
    data['preview_fingerprint'] = store.identity('learning-route-preview-v1', data)
    return _present(conn, pid, data, graph)


def _merge_order(old_steps, steps):
    """Preserve the chosen order, placing new prerequisites before their dependents."""
    by_id = {step['node_id']: step for step in steps}
    ordered = [step['node_id'] for step in old_steps if step['node_id'] in by_id]
    # Insert closest dependents first, so a newly discovered chain is placed
    # before the target in its actual prerequisite order.
    for step in reversed(steps):
        nid = step['node_id']
        if nid in ordered:
            continue
        dependents = {candidate['node_id'] for candidate in steps
                      if any(edge['source'] == nid for edge in candidate['snapshot']['prerequisites'])}
        positions = [ordered.index(other) for other in dependents if other in ordered]
        ordered.insert(min(positions) if positions else 0, nid)
    return [by_id[nid] for nid in ordered]


def _revision(conn, pid, expected):
    current = _raw(conn, pid)
    if (current['revision'] if current else 0) != expected:
        raise HTTPException(409, '学习路线已在其他位置更新，请重新读取后操作')
    return current


def _persist(conn, pid, value, before, action):
    timestamp = store.now()
    result = {**value, 'id': store.identity('learning-route-v1', pid),
              'revision': (before['revision'] if before else 0) + 1,
              'created_at': before['created_at'] if before else timestamp,
              'updated_at': timestamp, 'reviewed_by': _actor(), 'action': action}
    conn.execute('INSERT INTO kw_learning_routes VALUES(?,?,?) ON CONFLICT(project_id) '
                 'DO UPDATE SET revision=excluded.revision,data=excluded.data',
                 (pid, result['revision'], store.encode(result)))
    conn.execute('INSERT INTO kw_history(project_id,record_id,kind,data,created_at) VALUES(?,?,?,?,?)',
                 (pid, result['id'], 'learning_route', store.encode(result), timestamp))
    return {'route': _present(conn, pid, result)}


def save(conn, pid, target_node_id, expected_revision, preview_fingerprint):
    init(conn)
    conn.execute('BEGIN IMMEDIATE')
    before = _revision(conn, pid, expected_revision)
    planned = preview(conn, pid, target_node_id)
    if planned['preview_fingerprint'] != preview_fingerprint:
        raise HTTPException(409, '预览后问题、知识、依据或路线已有变化，请重新预览')
    fields = ('project_id', 'target_node_id', 'target_label', 'research_question', 'warnings',
              'cycle_detected', 'truncated', 'preview_fingerprint')
    data = {key: planned[key] for key in fields}
    data['steps'] = [{key: step[key] for key in ('node_id', 'label', 'role', 'state', 'snapshot')}
                     for step in planned['steps']]
    return _persist(conn, pid, data, before, 'save')


def update(conn, pid, values):
    init(conn)
    conn.execute('BEGIN IMMEDIATE')
    before = _revision(conn, pid, values['expected_revision'])
    if before is None:
        raise HTTPException(404, '还没有保存学习路线')
    value = json.loads(store.encode(before))
    step_id, state, order = values.get('step_node_id'), values.get('state'), values.get('order')
    if (step_id is None) != (state is None) or state is not None and state not in STATES:
        raise HTTPException(422, '更改步骤时需同时提供有效步骤和状态')
    if step_id is None and order is None:
        raise HTTPException(422, '请选择步骤状态或路线顺序')
    by_id = {step['node_id']: step for step in value['steps']}
    if step_id is not None:
        if step_id not in by_id:
            raise HTTPException(404, '步骤不在当前学习路线')
        if state == 'done':
            presented = _present(conn, pid, before)
            item = next(step for step in presented['steps'] if step['node_id'] == step_id)
            if item['stale'] or not item['available']:
                raise HTTPException(409, '这一步的依据已变化，请先复核再标记完成')
        by_id[step_id]['state'] = state
    if order is not None:
        if len(order) != len(by_id) or len(set(order)) != len(order) or set(order) != set(by_id):
            raise HTTPException(422, '顺序必须恰好包含当前路线的全部步骤，且不能重复')
        value['steps'] = [by_id[nid] for nid in order]
    return _persist(conn, pid, value, before, 'update')


def recheck(conn, pid, values):
    init(conn)
    conn.execute('BEGIN IMMEDIATE')
    before = _revision(conn, pid, values['expected_revision'])
    if before is None:
        raise HTTPException(404, '还没有保存学习路线')
    value = json.loads(store.encode(before))
    step = next((item for item in value['steps'] if item['node_id'] == values['step_node_id']), None)
    if step is None:
        raise HTTPException(404, '步骤不在当前学习路线')
    nodes, edges, _ = experience.graph_records(conn, pid)
    current = _context(conn, pid, step['node_id'], nodes, edges)
    if not current or not current['available']:
        raise HTTPException(409, '当前知识或依据不可用，无法重新确认；旧记录仍保留')
    if values['expected_context'] != current['fingerprint']:
        raise HTTPException(409, '核对期间节点、来源或关系又有变化，请重新读取')
    step['snapshot'] = current
    step['label'] = current['node']['label']
    if step['node_id'] == value['target_node_id']:
        value['target_label'] = step['label']
    return _persist(conn, pid, value, before, 'recheck')


def history(conn, pid):
    init(conn)
    return {'items': [json.loads(row[0]) for row in conn.execute(
        "SELECT data FROM kw_history WHERE project_id=? AND kind='learning_route' ORDER BY id DESC LIMIT 50", (pid,))]}
