"""Immutable machine action plans referencing the original activity records."""

import hashlib
import json
from fastapi import HTTPException

RULE_VERSION = "automatic-actions-1"


def init_actions(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS automatic_action_versions (
      list_id TEXT NOT NULL, version INTEGER NOT NULL, title TEXT NOT NULL,
      input_json TEXT NOT NULL, payload_json TEXT NOT NULL, fingerprint TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT (datetime('now')), PRIMARY KEY(list_id,version));
    CREATE INDEX IF NOT EXISTS idx_automatic_actions_latest ON automatic_action_versions(list_id,version DESC);
    """)


def build_actions(conn, inputs):
    from app.workflow import activities
    from app.db.workspace import document_view
    from app.db.sqlite import get_paper

    paper_uids = list(dict.fromkeys(inputs['paper_uids']))
    machine_preview = None
    if inputs.get('profile'):
        from app.api.roadmap import auto_preview
        from app.models.roadmap import GenerateRequest
        machine_preview = auto_preview(GenerateRequest.model_validate({'profile': inputs['profile']}))
        paper_uids += [item['uid'] for phase in machine_preview['route']['phases']
                       for item in phase['items'] if item.get('uid') and get_paper(conn, item['uid'])]
        paper_uids = list(dict.fromkeys(paper_uids))
    if not paper_uids:
        raise ValueError("请先选择已解析论文或机器核查目标")
    tasks, sources = [], []
    for uid in paper_uids:
        if not get_paper(conn, uid):
            raise LookupError("论文不存在")
        docs = document_view(conn, uid)
        if not docs or not docs[0]['passages']:
            raise ValueError(f"论文 {uid} 没有可用原文，请查看解析情况")
        doc = docs[0]
        sources.append({'paper_uid': uid, 'version': doc['content_hash'], 'document_id': doc['id'],
                        'text_digest': hashlib.sha256(json.dumps(doc['passages'], sort_keys=True).encode()).hexdigest()})
        tasks += activities(conn, 'paper', uid)
    budget = inputs['weekly_hours'] * 60
    spent = 0
    week_number, week_used = 1, 0
    planned = []
    for item in tasks:
        minutes = item['estimated_minutes']
        week = None
        if minutes is not None and minutes <= budget and item['status'] != 'completed':
            if week_used + minutes > budget:
                week_number, week_used = week_number + 1, 0
            week, week_used = week_number, week_used + minutes
        planned.append({**item, 'week': week, 'duration_basis': '按原文字符数估算，非实测' if minutes is not None else '暂无可靠时长'})
        if week is not None:
            spent += minutes
    # Progress is projected live and is deliberately excluded from version identity.
    identity = {'sources': sources, 'inputs': inputs, 'rule_version': RULE_VERSION,
                'machine_preview': machine_preview}
    if machine_preview:
        identity['machine_preview'] = machine_preview
    source_fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    identity['progress'] = [(item['id'], item['status']) for item in tasks]
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {'rule_version': RULE_VERSION, 'evidence_level': 'machine_checked_actions',
            'sources': sources, 'items': planned, 'estimated_minutes': spent,
            'unscheduled_count': sum(item['week'] is None and item['status'] != 'completed' for item in planned),
            'input_fingerprint': fingerprint, 'source_fingerprint': source_fingerprint, 'machine_preview': machine_preview,
            'notice': '自动行动清单使用原活动记录；来源和结构检查不证明掌握、教学效果或科研结论。'}


def save_actions(conn, title, inputs, *, list_id=None, expected_version=0, fingerprint=None):
    conn.execute('BEGIN IMMEDIATE')
    try:
        ident = list_id or 'actions-' + hashlib.sha256(f'{title}:{fingerprint}'.encode()).hexdigest()[:32]
        current = conn.execute('SELECT MAX(version) FROM automatic_action_versions WHERE list_id=?', (ident,)).fetchone()[0] or 0
        payload = build_actions(conn, inputs)
        if fingerprint and payload['input_fingerprint'] != fingerprint:
            raise ValueError('清单来源已变化，请重新预览')
        if current and list_id is None:
            conn.rollback()
            return action_view(conn, ident)
        if current != expected_version:
            raise ValueError('清单版本已变化，请刷新后预览')
        conn.execute('INSERT INTO automatic_action_versions(list_id,version,title,input_json,payload_json,fingerprint) VALUES(?,?,?,?,?,?)',
                     (ident, current + 1, title, json.dumps(inputs), json.dumps(payload, ensure_ascii=False), payload['input_fingerprint']))
        conn.commit()
        return {'id': ident, 'version': current + 1, 'title': title, **payload}
    except Exception:
        conn.rollback()
        raise


def action_view(conn, ident, version=None):
    row = conn.execute('SELECT * FROM automatic_action_versions WHERE list_id=? AND (? IS NULL OR version=?) ORDER BY version DESC LIMIT 1',
                       (ident, version, version)).fetchone()
    if not row:
        raise LookupError('自动行动清单不存在')
    payload = json.loads(row['payload_json'])
    try:
        current = build_actions(conn, json.loads(row['input_json']))
        stale = current['source_fingerprint'] != payload['source_fingerprint']
        needs_adjustment = current['input_fingerprint'] != row['fingerprint']
        live = {item['id']: item for item in current['items']}
    except (ValueError, LookupError, HTTPException):
        stale, live, needs_adjustment = True, {}, True
    items = [{**item, 'status': 'needs_review' if stale else live.get(item['id'], item)['status'],
              'evidence_level': live.get(item['id'], item)['evidence_level']} for item in payload['items']]
    versions = [r[0] for r in conn.execute('SELECT version FROM automatic_action_versions WHERE list_id=? ORDER BY version DESC', (ident,))]
    return {**payload, 'id': ident, 'version': row['version'], 'title': row['title'],
            'needs_review': stale, 'needs_adjustment': needs_adjustment, 'items': items, 'versions': versions}


def replan_actions(conn, ident, expected_version):
    row = conn.execute('SELECT * FROM automatic_action_versions WHERE list_id=? ORDER BY version DESC LIMIT 1', (ident,)).fetchone()
    if not row:
        raise LookupError('自动行动清单不存在')
    if row['version'] != expected_version:
        raise ValueError('清单版本已变化，请刷新')
    inputs = json.loads(row['input_json'])
    preview = build_actions(conn, inputs)
    before = {item['id'] for item in json.loads(row['payload_json'])['items']}
    after = {item['id'] for item in preview['items']}
    return {**preview, 'diff': {'added': sorted(after-before), 'removed': sorted(before-after),
                              'retained': sorted(before & after)}, 'inputs': inputs, 'title': row['title']}
