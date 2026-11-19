"""Personal node attachments and authored nodes, separate from scientific claims.

Files are ingested through the existing immutable store. Saving an attachment
never schedules knowledge extraction, calls a model, or executes uploaded code.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from app.db import projects
from app.knowledge import extraction, sources, store
from app.knowledge.parser import parse_source
from app.tenancy import current_user

TEXT_SUFFIXES = {'.md', '.txt', '.py', '.js', '.ts', '.tsx', '.jsx', '.cpp', '.c',
                 '.h', '.yaml', '.yml', '.json', '.csv', '.html', '.ipynb'}
LOCAL_PARSE_BYTES = 2 * 1024 * 1024


def init(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS kw_node_materials('
                 'id TEXT PRIMARY KEY,project_id TEXT NOT NULL,node_id TEXT NOT NULL,'
                 'source_id TEXT NOT NULL,revision INTEGER NOT NULL,data TEXT NOT NULL,'
                 'UNIQUE(project_id,node_id,source_id))')
    conn.execute('CREATE INDEX IF NOT EXISTS kw_node_materials_scope ON kw_node_materials(project_id,node_id)')


def _actor():
    user = current_user.get()
    return (user.get('username') or user['id']) if user else '本机用户'


def _node(conn, pid, nid, *, writing=False):
    node = store.record(conn, 'kw_nodes', pid, nid)
    if writing and projects.get_project(conn, pid).status.value == 'archived':
        raise HTTPException(409, '请先恢复已归档空间')
    return node


def _snapshot(source):
    return {key: source.get(key) for key in ('id', 'title', 'version', 'filename', 'kind', 'media_type')}


def _original_available(conn, source):
    row = conn.execute('SELECT path FROM kw_assets WHERE id=?', (source['asset_id'],)).fetchone()
    return bool(row and Path(row[0]).is_file())


def _raw(conn, pid, nid, mid):
    row = conn.execute('SELECT data FROM kw_node_materials WHERE id=? AND project_id=? AND node_id=?',
                       (mid, pid, nid)).fetchone()
    if not row:
        raise HTTPException(404, '资料关联不在当前知识节点')
    return json.loads(row[0])


def _present(conn, pid, value):
    try:
        source = store.source(conn, pid, value['source_id'], include_removed=True)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        source = None
    missing = not source or source['removed'] or not _original_available(conn, source)
    return {**value, 'current_source': {**_snapshot(source), 'removed': source['removed']} if source else None,
            'source_changed': bool(source and source['version'] != value['source_snapshot']['version']),
            'source_missing': bool(missing),
            'original_url': None if missing else f'/api/projects/{pid}/sources/{value["source_id"]}/file'}


def collection(conn, pid, nid, *, include_removed=False):
    _node(conn, pid, nid)
    init(conn)
    values = [json.loads(row[0]) for row in conn.execute(
        'SELECT data FROM kw_node_materials WHERE project_id=? AND node_id=? ORDER BY rowid', (pid, nid))]
    return {'items': [_present(conn, pid, value) for value in values if include_removed or not value['removed']]}


def _persist(conn, pid, value, before, action):
    timestamp = store.now()
    result = {**value, 'revision': before['revision'] + 1 if before else 1,
              'created_at': before['created_at'] if before else timestamp,
              'updated_at': timestamp, 'reviewed_by': _actor(), 'action': action}
    conn.execute('INSERT INTO kw_node_materials VALUES(?,?,?,?,?,?) ON CONFLICT(id) '
                 'DO UPDATE SET revision=excluded.revision,data=excluded.data',
                 (result['id'], pid, result['node_id'], result['source_id'], result['revision'], store.encode(result)))
    conn.execute('INSERT INTO kw_history(project_id,record_id,kind,data,created_at) VALUES(?,?,?,?,?)',
                 (pid, result['id'], 'node_material', store.encode(result), timestamp))
    return {'item': _present(conn, pid, result)}


def bind(conn, pid, nid, sid, note=''):
    init(conn)
    conn.execute('BEGIN IMMEDIATE')
    _node(conn, pid, nid, writing=True)
    source = store.source(conn, pid, sid)
    if not _original_available(conn, source):
        raise HTTPException(409, '资料原件当前不可用，请重新导入后添加')
    mid = store.identity('node-material-v1', pid, nid, sid)
    row = conn.execute('SELECT data FROM kw_node_materials WHERE id=? AND project_id=?', (mid, pid)).fetchone()
    before = json.loads(row[0]) if row else None
    note = note.strip()
    if before and not before['removed']:
        if before['note'] != note:
            raise HTTPException(409, '这份资料已经添加到该节点，请编辑已有的资料备注')
        return {'item': _present(conn, pid, before)}
    value = {'id': mid, 'project_id': pid, 'node_id': nid, 'source_id': sid,
             'note': note, 'removed': False, 'origin': 'user', 'source_snapshot': _snapshot(source)}
    return _persist(conn, pid, value, before, 'restore' if before else 'attach')


def revise(conn, pid, nid, mid, values):
    init(conn)
    conn.execute('BEGIN IMMEDIATE')
    _node(conn, pid, nid, writing=True)
    before = _raw(conn, pid, nid, mid)
    if before['revision'] != values['expected_revision']:
        raise HTTPException(409, '资料关联已在其他位置更新，请重新读取后操作')
    changes = {key: values[key] for key in ('note', 'removed') if values.get(key) is not None}
    if not changes:
        raise HTTPException(422, '请提供要修改的备注或关联状态')
    if 'note' in changes:
        changes['note'] = changes['note'].strip()
    return _persist(conn, pid, {**before, **changes}, before, 'update')


def history(conn, pid, nid, mid):
    _node(conn, pid, nid)
    init(conn)
    _raw(conn, pid, nid, mid)
    return {'items': [json.loads(row[0]) for row in conn.execute(
        "SELECT data FROM kw_history WHERE project_id=? AND record_id=? AND kind='node_material' ORDER BY id DESC LIMIT 50",
        (pid, mid))]}


def _parse_text(pid, source, raw):
    """Only bounded native text parsing; PDF and complex document originals remain available."""
    if Path(source['filename']).suffix.lower() not in TEXT_SUFFIXES or len(raw) > LOCAL_PARSE_BYTES:
        return 'original_only'
    with store.connection(pid) as conn:
        existing = conn.execute('SELECT 1 FROM kw_parses WHERE asset_id=?', (source['asset_id'],)).fetchone()
        if existing:
            return 'ready'
        asset = conn.execute('SELECT path FROM kw_assets WHERE id=?', (source['asset_id'],)).fetchone()
    try:
        parsed = parse_source(Path(asset[0]), source['kind'], use_docling=False)
    except Exception:
        return 'original_only'
    if not parsed.get('blocks'):
        return 'original_only'
    with store.connection(pid) as conn:
        live = store.source(conn, pid, source['id'])
        # Never replace another completed parser's blocks or invalidate its evidence.
        if live['version'] == source['version'] and not conn.execute(
                'SELECT 1 FROM kw_parses WHERE asset_id=?', (source['asset_id'],)).fetchone():
            store.put_parse(conn, source['asset_id'], parsed)
            store.update_source(conn, pid, source['id'], {'parser': parsed.get('parser'), 'quality': parsed.get('quality', {})})
    return 'ready'


def upload(pid, nid, raw, filename, kind=None, note=''):
    with store.connection(pid) as conn:
        _node(conn, pid, nid, writing=True)
    source = sources.ingest(pid, raw, filename, kind)
    try:
        reading = _parse_text(pid, source, raw)
        with store.connection(pid) as conn:
            result = bind(conn, pid, nid, source['id'], note)
        return {**result, 'source': source, 'reading_status': reading}
    except HTTPException as exc:
        raise HTTPException(exc.status_code, {'message': '原文件已保存，节点关联未完成：' + str(exc.detail),
                                             'saved_source': _snapshot(source)}) from exc
    except Exception as exc:
        raise HTTPException(503, {'message': '原文件已保存，节点关联暂未完成。可从本课题资料中重新添加。',
                                  'saved_source': _snapshot(source)}) from exc


def create_node(pid, label, summary='', kind='concept'):
    label, summary = label.strip(), summary.strip()
    if not label:
        raise HTTPException(422, '请填写节点名称')
    uid = uuid4().hex
    body = f'# {label}\n\n个人知识节点，由用户撰写。\n\n{summary}\n\n<!-- PaperStride personal node {uid} -->\n'
    source = sources.ingest(pid, body.encode('utf-8'), f'{label[:100]}-个人节点.md', 'report')
    _parse_text(pid, source, body.encode('utf-8'))
    with store.connection(pid) as conn:
        conn.execute('BEGIN IMMEDIATE')
        blocks = store.source_blocks(conn, source['asset_id'])
        quote = summary[:1200] if summary else label
        # The native Markdown reader may split long text; quote only an actual block.
        block = next((block for block in blocks if quote in block['text']), blocks[0])
        if quote not in block['text']:
            quote = block['text'][:1200]
        evidence = store.add_evidence(conn, pid, source, block, quote=quote, origin='user')
        node = extraction.node(source, 'manual:' + uid, kind, label, summary, [evidence], origin='user',
                               metadata={'manual': True, 'user_authored': True, 'semantic': True,
                                         'created_by': _actor(), 'user_fields': ['label', 'summary']})
        return {'node': store.put_record(conn, 'kw_nodes', node)}
