"""Disposable projections invalidated transactionally with their source records."""

import json


def init_projections(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS activity_projection_meta (version TEXT PRIMARY KEY);
    CREATE TABLE IF NOT EXISTS projection_revisions (
      kind TEXT NOT NULL, source_id TEXT NOT NULL, token TEXT NOT NULL,
      PRIMARY KEY(kind,source_id));
    CREATE TABLE IF NOT EXISTS activity_projection (
      id TEXT PRIMARY KEY, source_kind TEXT NOT NULL, source_id TEXT NOT NULL,
      project_id TEXT, status_order INTEGER NOT NULL, title TEXT NOT NULL, payload_json TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS idx_activity_page ON activity_projection(status_order,source_kind,title,id);
    CREATE INDEX IF NOT EXISTS idx_activity_source ON activity_projection(source_kind,source_id);
    CREATE TABLE IF NOT EXISTS projection_consumed (
      kind TEXT NOT NULL, source_id TEXT NOT NULL, token TEXT NOT NULL, PRIMARY KEY(kind,source_id));
    CREATE TABLE IF NOT EXISTS project_audit_cache (
      project_id TEXT PRIMARY KEY, token TEXT NOT NULL, rule_version TEXT NOT NULL, payload_json TEXT NOT NULL);
    """)
    if not conn.execute("SELECT 1 FROM activity_projection_meta WHERE version='workflow-projection-1'").fetchone():
        conn.execute('DELETE FROM projection_consumed')
        conn.execute('DELETE FROM activity_projection_meta')
        conn.execute("INSERT INTO activity_projection_meta VALUES('workflow-projection-1')")
    mapping = {'papers': ('paper','uid'), 'documents': ('paper','paper_uid'),
               'workspaces': ('paper','paper_uid'), 'roadmaps': ('roadmap','id'),
               'case_sessions': ('case','*'), 'case_runs': ('case','*'),
               'workflow_roadmap_lineage': ('roadmap','*'), 'knowledge': ('roadmap','*'),
               'extraction_proposals': ('roadmap','*'), 'workflow_mastery': ('roadmap','*')}
    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'research_%'")]
    for table in tables:
        columns = {row['name'] for row in conn.execute(f'PRAGMA table_info({table})')}
        if 'project_id' in columns and table not in ('research_impact_checkpoints', 'research_async_tasks', 'research_projection_outbox'):
            mapping[table] = ('project', 'project_id')
    mapping['passages'] = ('paper', 'passage_document')
    mapping['workflow_step_records'] = ('project', 'snapshot_project')
    for table, (kind, column) in mapping.items():
        for event in ('INSERT','UPDATE','DELETE'):
            refs = ('NEW','OLD') if event == 'UPDATE' else ('OLD',) if event == 'DELETE' else ('NEW',)
            statements = []
            for ref in refs:
                if column == '*':
                    source = "'*'"
                elif column == 'passage_document':
                    source = f'(SELECT paper_uid FROM documents WHERE id={ref}.document_id)'
                elif column == 'snapshot_project':
                    source = f'(SELECT project_id FROM research_snapshots WHERE snapshot_id={ref}.snapshot_id)'
                else:
                    source = f'CAST({ref}.{column} AS TEXT)'
                statements.append(f"INSERT INTO projection_revisions VALUES('{kind}',coalesce({source},'*'),hex(randomblob(16))) "
                                  "ON CONFLICT(kind,source_id) DO UPDATE SET token=excluded.token;")
                if kind == 'paper':
                    # Paper links include frozen sources; dependency edges also locate historical targets.
                    statements.append("INSERT INTO projection_revisions SELECT 'project',project_id,hex(randomblob(16)) "
                                      f"FROM research_paper_link_versions WHERE paper_uid={source} GROUP BY project_id "
                                      "ON CONFLICT(kind,source_id) DO UPDATE SET token=excluded.token;")
                    statements.append("INSERT INTO projection_revisions SELECT 'project',project_id,hex(randomblob(16)) "
                                      f"FROM research_dependency_edges WHERE source_kind='paper' AND source_id={source} GROUP BY project_id "
                                      "ON CONFLICT(kind,source_id) DO UPDATE SET token=excluded.token;")
            conn.execute(f'CREATE TRIGGER IF NOT EXISTS projection_{table}_{event.lower()} AFTER {event} ON {table} BEGIN {" ".join(statements)} END')
    for kind in ('paper','roadmap','case','project'):
        conn.execute("INSERT OR IGNORE INTO projection_revisions VALUES(?, '*',hex(randomblob(16)))", (kind,))


def refresh_activities(conn):
    from app.workflow import _roadmap_activities, _paper_activities, _case_activities, _project_activities
    factories = {'roadmap': _roadmap_activities, 'paper': _paper_activities,
                 'case': _case_activities, 'project': _project_activities}
    dirty = conn.execute('SELECT r.* FROM projection_revisions r LEFT JOIN projection_consumed c '
                         'ON c.kind=r.kind AND c.source_id=r.source_id WHERE c.token IS NULL OR c.token!=r.token').fetchall()
    if not dirty:
        return
    prior_transaction = conn.in_transaction
    if not prior_transaction:
        conn.execute('BEGIN IMMEDIATE')
        # Re-read after acquiring the write lock.
        dirty = conn.execute('SELECT r.* FROM projection_revisions r LEFT JOIN projection_consumed c '
                             'ON c.kind=r.kind AND c.source_id=r.source_id WHERE c.token IS NULL OR c.token!=r.token').fetchall()
    try:
        full_kinds = {row['kind'] for row in dirty if row['source_id'] == '*'}
        order = {'needs_review': 0, 'in_progress': 1, 'pending': 2, 'completed': 3}
        for row in dirty:
            kind, source = row['kind'], row['source_id']
            if source != '*' and kind in full_kinds:
                continue
            if source == '*':
                conn.execute('DELETE FROM activity_projection WHERE source_kind=?', (kind,))
                items = factories[kind](conn)
            else:
                conn.execute('DELETE FROM activity_projection WHERE source_kind=? AND ' +
                             ('project_id=?' if kind == 'project' else 'source_id=?'), (kind, source))
                items = factories[kind](conn, source)
            for item in items:
                conn.execute('INSERT OR REPLACE INTO activity_projection VALUES(?,?,?,?,?,?,?)',
                             (item['id'], kind, item['source_id'], item['project_id'], order[item['status']],
                              item['title'], json.dumps(item, ensure_ascii=False)))
        for row in dirty:
            conn.execute('INSERT OR REPLACE INTO projection_consumed VALUES(?,?,?)', tuple(row))
        if not prior_transaction:
            conn.commit()
    except Exception:
        if not prior_transaction:
            conn.rollback()
        raise


def activity_page(conn, source_kind=None, source_id=None, project_id=None, offset=0, limit=100):
    refresh_activities(conn)
    where, params = [], []
    for column, value in [('source_kind', source_kind), ('source_id', source_id), ('project_id', project_id)]:
        if value is not None:
            where.append(f'{column}=?')
            params.append(str(value))
    clause = ' WHERE ' + ' AND '.join(where) if where else ''
    total = conn.execute('SELECT COUNT(*) FROM activity_projection' + clause, params).fetchone()[0]
    rows = conn.execute('SELECT payload_json FROM activity_projection' + clause +
                        ' ORDER BY status_order,source_kind,title,id LIMIT ? OFFSET ?', [*params, limit, offset]).fetchall()
    return {'items': [json.loads(row[0]) for row in rows], 'total': total, 'offset': offset, 'limit': limit}
