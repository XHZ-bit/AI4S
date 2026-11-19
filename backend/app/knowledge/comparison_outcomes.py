"""Immutable, source-located personal outcomes from any saved comparison."""

import json
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import HTTPException

from app.knowledge import comparison, store


def _location(locator):
    parts = []
    if locator.get('page') is not None:
        parts.append('第 ' + str(locator['page']) + ' 页')
    if locator.get('heading'):
        parts.append(str(locator['heading']))
    if locator.get('start_line') is not None:
        parts.append('行 ' + str(locator['start_line']) + '–' + str(locator.get('end_line', locator['start_line'])))
    if locator.get('path'):
        parts.append(str(locator['path']))
    return ' · '.join(parts) or '原文块定位'


def _markdown(pid, value):
    lines = ['# ' + value['title'], '', '研究问题', '', value['question'] or '尚未填写', '',
             '我的理解', '', value['interpretation'] or '尚未填写', '',
             '未解决的问题', '', value['unresolved'] or '尚未填写', '',
             '比较版本 ' + str(value['comparison_revision'])]
    if value['stale']:
        lines.extend(['', '保存时比较依据已变化，以下保留当时快照，需要复核。'])
    for cell in value['cells']:
        source = value['sources'].get(cell['source_id'], {})
        lines.extend(['', '## ' + cell['dimension'] + ' · ' + source.get('title', '历史资料'), '', cell['text'], '',
                      '内容性质为' + ('个人修订' if cell['origin'] == 'user' else '原文归纳' if cell['origin'] == 'source' else '推断，待结合原文核对')])
        if cell.get('reviewed'):
            lines.append('用户核对记录 ' + str(cell.get('reviewed_by', '未记录')) + ' · ' + str(cell.get('reviewed_at', '')))
        if cell.get('review_stale'):
            lines.extend(['', '此项保留历史核对，依据已变化，需要复核。'])
        if cell.get('compatibility'):
            lines.extend(['', cell['compatibility']])
        if not cell['evidence']:
            lines.extend(['', '此项缺少已保存的原文依据。'])
        for evidence in cell['evidence']:
            locator = evidence.get('locator', {})
            lines.extend(['', '### 原文依据', '', evidence.get('source_title', source.get('title', '资料')) + ' · ' + _location(locator), '',
                          evidence.get('quote', ''), '', '来源版本 ' + str(evidence.get('source_version', source.get('version', '未记录')))])
            for key, label in [('commit', '代码提交'), ('url', '固定来源地址')]:
                if locator.get(key):
                    lines.append(label + ' ' + str(locator[key]))
            params = {'view': 'reading', 'source': cell['source_id'], 'block': evidence.get('block_id', '')}
            if locator.get('page') is not None:
                params['page'] = locator['page']
            if locator.get('start_line') is not None:
                params['line'] = locator['start_line']
                params['endLine'] = locator.get('end_line', locator['start_line'])
            lines.extend(['', '平台定位 ' + '/research/' + pid + '?' + urlencode(params)])
    return '\n'.join(lines).strip() + '\n'


def create(pid, cid, expected_revision, selections, question='', interpretation='', unresolved='', *, save=False):
    with store.connection(pid) as conn:
        if save:
            conn.execute('BEGIN IMMEDIATE')
        current = comparison.get_comparison(conn, pid, cid)
        if current.get('revision', 1) != expected_revision:
            raise HTTPException(409, '比较已修订，请重新预览成果')
        cells = []
        seen = set()
        for selected in selections:
            key = (selected['dimension'], selected['source_id'])
            if key in seen:
                continue
            seen.add(key)
            row = next((r for r in current['rows'] if r['dimension'] == key[0]), None)
            entry = next((e for e in row['values'] if e['source_id'] == key[1]), None) if row else None
            if entry is None:
                raise HTTPException(422, '所选内容不属于当前比较')
            evidence = entry.get('evidence_snapshot')
            if evidence is None:
                evidence = [e for e in current.get('evidence', []) if e['id'] in entry.get('evidence_ids', []) and e['source_id'] == key[1]]
            cells.append({**entry, 'dimension': key[0], 'compatibility': row.get('compatibility', ''), 'evidence': evidence})
        if not cells:
            raise HTTPException(422, '请先选择至少一项比较内容')
        try:
            stale = current['fingerprint'] != comparison.fingerprint(conn, pid, current['source_ids'], current.get('focus_node_ids'), current.get('dimensions'), current.get('template'))
        except HTTPException:
            stale = True
        stale = stale or any(cell.get('review_stale') for cell in cells)
        value = {'id': str(uuid4()) if save else 'preview', 'comparison_id': cid,
                 'comparison_revision': expected_revision, 'title': current['title'] + ' · 我的比较成果',
                 'question': question.strip(), 'interpretation': interpretation.strip(), 'unresolved': unresolved.strip(),
                 'cells': cells, 'sources': current.get('input_versions', {}), 'stale': stale, 'created_at': store.now()}
        value['markdown'] = _markdown(pid, value)
        if save:
            conn.execute('INSERT INTO kw_history(project_id,record_id,kind,data,created_at) VALUES(?,?,?,?,?)',
                         (pid, cid, 'comparison_outcome', store.encode(value), value['created_at']))
        return value


def list_saved(pid, cid):
    with store.connection(pid) as conn:
        current = comparison.get_comparison(conn, pid, cid)
        result = []
        for row in conn.execute("SELECT data FROM kw_history WHERE project_id=? AND record_id=? AND kind='comparison_outcome' ORDER BY id DESC LIMIT 30", (pid, cid)):
            value = json.loads(row[0])
            value['comparison_changed'] = value['comparison_revision'] != current.get('revision', 1)
            value['source_changes'] = comparison.comparison_changes(conn, pid, {'source_ids': list(value['sources']), 'input_versions': value['sources'], 'rows': [], 'evidence': [e for cell in value['cells'] for e in cell['evidence']]})
            # comparison_changes gives a generic fallback for other context changes.
            value['source_changes'] = [c for c in value['source_changes'] if c['source_id']]
            result.append(value)
        return result
