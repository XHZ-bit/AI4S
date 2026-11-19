import copy
import json

from app.api.knowledge_global import Quality, review, history
from app.db import projects
from app.db.sqlite import connect
from app.knowledge import extraction, sources, store, unified
from app.knowledge.parser import parse_source
from app.models.research import ResearchProjectCreate, ProjectConstraints
from app.tenancy import user_scope


def seed():
    with connect() as conn:
        project = projects.create_project(conn, ResearchProjectCreate(title='Evidence study', research_question='Understand a formula', domain='custom', constraints=ProjectConstraints(version=1, objective='Check evidence')))
    pid = project.id
    src = sources.ingest(pid, b'# Study\n\n## Method\nThe output is bounded by tanh.\n', 'study.md')
    with store.connection(pid) as conn:
        asset = conn.execute('SELECT path FROM kw_assets WHERE id=?', (src['asset_id'],)).fetchone()
        parsed = parse_source(asset[0], src['kind'], use_docling=False)
        store.put_parse(conn, src['asset_id'], parsed)
        blocks = store.source_blocks(conn, src['asset_id'])
        extraction.structural_graph(conn, src, blocks)
        node = json.loads(conn.execute('SELECT data FROM kw_nodes WHERE project_id=? LIMIT 1', (pid,)).fetchone()[0])
    return pid, src, node


def verify(pid, node):
    with store.connection(pid) as conn:
        return unified.review_record(conn, node['id'], 'verify', 'reader', 'Checked against the saved source', project_id=pid, expected_version=node['version'])['record']


def test_formula_edit_expires_review_and_keeps_history():
    pid, src, node = seed()
    with store.connection(pid) as conn:
        formula = {**node, 'id': 'formula', 'kind': 'formula', 'metadata': {**node['metadata'], 'latex': 'y=x'}}
        formula = store.put_record(conn, 'kw_nodes', formula)
    checked = verify(pid, formula)
    with store.connection(pid) as conn:
        changed = store.edit_record(conn, 'kw_nodes', pid, checked['id'], checked['version'], {'metadata': {**checked['metadata'], 'latex': 'y=x^2'}})
        assert changed['quality_status'] == 'candidate'
        assert store.record(conn, 'kw_nodes', pid, changed['id'])['quality_review_stale']
    snapshots = history(changed['id'], pid)['items']
    assert any(item['snapshot'].get('metadata', {}).get('latex') == 'y=x' for item in snapshots)


def test_regenerated_content_cannot_reuse_old_human_verdict():
    pid, src, node = seed()
    checked = verify(pid, node)
    with store.connection(pid) as conn:
        regenerated = copy.deepcopy(checked)
        regenerated.pop('quality_review_stale', None)
        regenerated.pop('source_missing', None)
        regenerated['summary'] = 'A different explanation needs a new review.'
        store.put_record(conn, 'kw_nodes', regenerated)
        current = store.record(conn, 'kw_nodes', pid, node['id'])
        assert current['quality_status'] == 'candidate'
        assert current['quality_review_stale']


def test_missing_source_block_cannot_be_verified():
    pid, src, node = seed()
    with store.connection(pid) as conn:
        conn.execute('DELETE FROM kw_blocks WHERE asset_id=?', (src['asset_id'],))
        evidence = store.evidence(conn, pid, node['evidence_ids'])
        assert evidence and evidence[0]['unresolved']
        import pytest
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as failure:
            unified.review_record(conn, node['id'], 'verify', 'reader', 'review', project_id=pid, expected_version=node['version'])
        assert failure.value.status_code == 422


def test_review_identity_comes_from_authenticated_account():
    with user_scope({'id': 'a'*32, 'username': 'alice'}):
        pid, src, node = seed()
        result = review(node['id'], Quality(action='verify', actor='someone else', reason='Checked source', expected_version=node['version'], project_id=pid))
        assert result['record']['metadata']['quality_decision']['actor'] == 'alice'


def test_comparison_explains_changed_knowledge_without_replacing_old_cells():
    from app.knowledge import comparison
    pid, src, node = seed()
    second = sources.ingest(pid, b'# Another study\n\n## Method\nA different controller.\n', 'second.md')
    with store.connection(pid) as conn:
        method = {**node, 'id': 'method', 'kind': 'method', 'parent_id': node['id'], 'metadata': {**node['metadata'], 'semantic': True}, 'summary': 'Original method explanation'}
        method = store.put_record(conn, 'kw_nodes', method)
    result = comparison.compare(pid, [src['id'], second['id']], basic_only=True)
    old_text = next(row for row in result['rows'] if row['dimension'] == '方法与模块划分')['values'][0]['text']
    with store.connection(pid) as conn:
        store.edit_record(conn, 'kw_nodes', pid, method['id'], method['version'], {'summary': 'Corrected explanation'})
    with store.connection(pid) as conn:
        saved = comparison.list_comparisons(conn, pid)[0]
    assert saved['stale']
    assert saved['stale_changes'][0]['reason'] == '相关知识已有修订'
    assert '方法与模块划分' in saved['stale_changes'][0]['dimensions']
    assert next(row for row in saved['rows'] if row['dimension'] == '方法与模块划分')['values'][0]['text'] == old_text
