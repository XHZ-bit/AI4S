"""Isolated runtime, cancellation, immutable action plans and projection regressions."""

import json
import time
from contextlib import closing

import httpx
import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.db.sqlite import connect, reset_running_tasks
from app.db.workspace import get_state, put_state, save_document
from app.main import app
from app.models.paper import ParsedPaper
from app.task_control import TaskStopped, check_active, checkpoint, stop_task, task_scope
from tests.test_assistant import fixture_project as base_fixture

fixture_project = base_fixture


def seed(conn, uid='p1', text='Saved original passage. ' * 100):
    conn.execute('INSERT INTO papers(uid,title) VALUES(?,?)', (uid, f'Paper {uid}'))
    conn.commit()
    return save_document(conn, uid, ParsedPaper(uid=uid,title=uid,abstract='',sections=[{'heading':'Method','text':text}]))


def test_health_reports_database_failure_without_exposing_exception(monkeypatch):
    monkeypatch.setattr('app.api.system.connect', lambda: (_ for _ in ()).throw(RuntimeError('secret-value')))
    result = TestClient(app).get('/health')
    assert result.status_code == 503
    assert 'secret-value' not in result.text


def test_runtime_capabilities_distinguish_missing_dependencies(monkeypatch):
    monkeypatch.setattr('app.api.system.graph_status', lambda:{'status':'unavailable'})
    monkeypatch.setattr('app.api.system.parser_status', lambda:{'status':'fallback'})
    result = TestClient(app).get('/api/system/status').json()
    assert result['status'] == 'degraded'
    assert result['capabilities']['automatic_actions']
    assert not result['capabilities']['research_model']
    assert result['services']['model']['status'] == 'unconfigured'
    assert 'password' not in json.dumps(result)


def test_runtime_distinguishes_automatic_knowledge_model_from_legacy_research_model(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'unit-private-knowledge-key')
    monkeypatch.setenv('KNOWLEDGE_MODEL_ENABLED', 'true')
    monkeypatch.setenv('RESEARCH_MODEL_ENABLED', 'false')
    monkeypatch.setenv('OFFLINE_MODE', 'false')
    get_settings.cache_clear()
    monkeypatch.setattr('app.api.system.graph_status', lambda: {'status': 'available'})
    monkeypatch.setattr('app.api.system.parser_status', lambda: {'status': 'fallback'})
    result = TestClient(app).get('/api/system/status').json()
    assert result['capabilities']['knowledge_model'] is True
    assert result['capabilities']['research_model'] is False
    assert result['services']['model']['knowledge_enabled'] is True
    assert result['services']['parser']['knowledge_backend'] in {'Docling', 'PyMuPDF'}
    assert 'unit-private-knowledge-key' not in json.dumps(result)


def test_actions_follow_original_progress_preserve_versions_and_detect_changed_source():
    client = TestClient(app)
    with closing(connect()) as conn:
        did = seed(conn)
    inputs = {'paper_uids':['p1'], 'weekly_hours':1}
    preview = client.post('/api/actions/v1/preview',json=inputs).json()
    body = {**inputs,'title':'Read my paper','input_fingerprint':preview['input_fingerprint']}
    saved = client.post('/api/actions/v1',json=body)
    assert saved.status_code == 200, saved.text
    ident = saved.json()['id']
    assert client.post('/api/actions/v1',json=body).json()['id'] == ident
    with closing(connect()) as conn:
        state = get_state(conn,'p1')['state']
        state['reading'][f'read:{did}-0'] = True
        put_state(conn,'p1',state,0)
        assert conn.execute('SELECT COUNT(*) FROM workflow_mastery').fetchone()[0] == 0
    current = client.get(f'/api/actions/v1/{ident}').json()
    assert next(item for item in current['items'] if item['item_id'] == f'read:{did}-0')['status'] == 'completed'
    assert current['needs_adjustment'] and not current['needs_review']
    replan = client.post(f'/api/actions/v1/{ident}/replan-preview',json={'expected_version':1}).json()
    request = {'expected_version':1,'input_fingerprint':replan['input_fingerprint']}
    assert client.post(f'/api/actions/v1/{ident}/replan',json=request).json()['version'] == 2
    assert client.post(f'/api/actions/v1/{ident}/replan',json=request).status_code == 409
    assert client.get(f'/api/actions/v1/{ident}',params={'version':1}).json()['version'] == 1
    assert [item['version'] for item in client.get(f'/api/actions/v1/{ident}/history').json()['items']] == [2, 1]
    with closing(connect()) as conn:
        conn.execute('UPDATE passages SET text=? WHERE document_id=?',('changed original',did))
        conn.commit()
    assert client.get(f'/api/actions/v1/{ident}').json()['needs_review']
    assert client.post('/api/actions/v1',json=body).status_code == 409


def test_preview_commit_checks_progress_race_and_weekly_budget():
    client = TestClient(app)
    with closing(connect()) as conn:
        did = seed(conn,text='a'*12000)
    inputs = {'paper_uids':['p1'],'weekly_hours':1}
    preview = client.post('/api/actions/v1/preview',json=inputs).json()
    weeks = {}
    for item in preview['items']:
        if item['week']:
            weeks[item['week']] = weeks.get(item['week'],0)+item['estimated_minutes']
    assert all(minutes <= 60 for minutes in weeks.values())
    with closing(connect()) as conn:
        state = get_state(conn,'p1')['state']
        state['reading'][f'read:{did}-0'] = True
        put_state(conn,'p1',state,0)
    assert client.post('/api/actions/v1',json={**inputs,'title':'Race','input_fingerprint':preview['input_fingerprint']}).status_code == 409


def test_cancelled_queue_does_not_run_and_duplicate_works_at_capacity(monkeypatch):
    import app.jobs as jobs
    submitted=[]
    monkeypatch.setattr(jobs,'submit_task',lambda *args:submitted.append(args))
    ident = jobs.enqueue('parse',{'uid':'p1'})
    acquired=0
    try:
        while jobs._slots.acquire(blocking=False):
            acquired += 1
        assert jobs.enqueue('parse',{'uid':'p1'}) == ident
        with closing(connect()) as conn:
            stop_task(conn,f'legacy:{ident}')
        monkeypatch.setattr('app.api.papers.process_saved_pdf',lambda *_:pytest.fail('cancelled job ran'))
        jobs.run(ident)
        with closing(connect()) as conn:
            assert conn.execute('SELECT status FROM tasks WHERE id=?',(ident,)).fetchone()[0] == 'cancelled'
    finally:
        for _ in range(acquired):
            jobs._slots.release()


def test_cancel_during_model_call_prevents_publishing_guide(monkeypatch):
    import app.jobs as jobs
    monkeypatch.setattr(jobs,'submit_task',lambda *_:None)
    with closing(connect()) as conn:
        did=seed(conn)
    ident=jobs.enqueue('guide',{'uid':'p1'})
    def cancelled_call(*args,**kwargs):
        with closing(connect()) as conn:
            stop_task(conn,f'legacy:{ident}')
        return json.dumps({'explanations':[{'topic':'x','explanation':'x','passage_ids':[f'{did}-0']}],'questions':[]})
    monkeypatch.setattr('app.guidance.chat',cancelled_call)
    jobs.run(ident)
    with closing(connect()) as conn:
        assert conn.execute('SELECT COUNT(*) FROM guides').fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM guide_chunks').fetchone()[0] == 0


def test_deadline_is_enforced_at_saving_boundary():
    with closing(connect()) as conn, task_scope('legacy:1'):
        checkpoint(conn,'parse',0.3)
        conn.execute('UPDATE task_controls SET deadline_at=?',(time.time()-1,))
        conn.commit()
        with pytest.raises(TaskStopped,match='总时限'):
            check_active(conn)


def test_restart_recovers_only_local_untouched_parse_queue(monkeypatch):
    import app.jobs as jobs
    from app.tasks import submit_task
    submitted=[]
    monkeypatch.setattr(jobs,'submit_task',lambda *args:submitted.append(args))
    with closing(connect()) as conn:
        for kind,status in [('parse','queued'),('parse','running'),('guide','queued')]:
            conn.execute('INSERT INTO tasks(type,status) VALUES(?,?)',(kind,status))
        conn.commit()
        assert reset_running_tasks(conn) == 2
        jobs.recover_safe_queue(conn)
        assert len(submitted)==1
        jobs._slots.release()
        assert conn.execute("SELECT COUNT(*) FROM tasks WHERE status='queued'").fetchone()[0] == 1
    assert callable(submit_task)


def test_task_center_handles_malformed_records_and_cancellation():
    client=TestClient(app)
    with closing(connect()) as conn:
        conn.execute("INSERT INTO tasks(type,status,params_json,result_json) VALUES('parse','queued','[]','not json')")
        conn.commit()
    result=client.get('/api/system/tasks',params={'status':'queued','limit':1}).json()
    assert result['total']==1 and result['items'][0]['can_cancel']
    ident=result['items'][0]['id']
    assert client.post(f'/api/system/tasks/legacy/{ident}/cancel').status_code == 200
    assert client.get('/api/system/tasks',params={'status':'cancelled'}).json()['total']==1


def test_pdf_coverage_and_duplicate_upload_without_model(monkeypatch):
    from app.api.papers import _data_dir, process_saved_pdf
    monkeypatch.setattr('app.api.papers.merge_paper',lambda *_:None)
    monkeypatch.setattr('app.api.papers.index_paper',lambda *_:None)
    pdf=pymupdf.open()
    pdf.new_page().insert_text((72,72),'Research original text')
    pdf.new_page()
    raw=pdf.tobytes()
    pdf.close()
    with closing(connect()) as conn:
        conn.execute("INSERT INTO papers(uid,title) VALUES('pdf','Original')")
        conn.commit()
        (_data_dir()/'pdf.pdf').write_bytes(raw)
        result=process_saved_pdf(conn,'pdf')
        assert result['quality']['status']=='partial'
        assert result['quality']['text_page_count']==1
        assert process_saved_pdf(conn,'pdf')['reused']
        assert conn.execute("SELECT COUNT(*) FROM documents WHERE paper_uid='pdf'").fetchone()[0]==1
    uploaded=[]
    monkeypatch.setattr('app.jobs.enqueue',lambda kind,params:uploaded.append(kind) or 1)
    client=TestClient(app)
    first=client.post('/api/papers/upload-async',files={'file':('paper.pdf',raw,'application/pdf')}).json()
    again=client.post('/api/papers/upload-async',files={'file':('renamed.pdf',raw,'application/pdf')}).json()
    assert first['uid']==again['uid'] and uploaded==['parse','parse']


def test_projection_pagination_matches_full_projection_and_refreshes_only_changed_paper(monkeypatch):
    from app import workflow
    from app.db.projections import activity_page
    with closing(connect()) as conn:
        seed(conn)
        seed(conn,'p2')
        baseline=workflow.activities(conn)
        assert activity_page(conn,offset=2,limit=3)['items']==baseline[2:5]
        original=workflow._paper_activities
        called=[]
        def wrapped(conn,source=None):
            called.append(source)
            return original(conn,source)
        monkeypatch.setattr(workflow,'_paper_activities',wrapped)
        activity_page(conn,limit=1)
        assert not called
        state=get_state(conn,'p1')['state']
        state['answers']['problem']={'text':'Read','status':'answered'}
        put_state(conn,'p1',state,0)
        activity_page(conn,limit=1)
        assert called==['p1']


def test_project_audit_cache_invalidation_tracks_changed_passage(fixture_project,monkeypatch):
    from app.research import audit
    original=audit._project_audit
    calls=[]
    monkeypatch.setattr(audit,'_project_audit',lambda conn,pid:calls.append(pid) or original(conn,pid))
    with closing(connect()) as conn:
        before=audit.project_audit(conn,fixture_project['project_id'])
        assert audit.project_audit(conn,fixture_project['project_id'])==before
        assert len(calls)==1
        conn.execute('UPDATE passages SET text=? WHERE document_id=?',('modified',fixture_project['document_id']))
        conn.commit()
        after=audit.project_audit(conn,fixture_project['project_id'])
        assert after['input_fingerprint']!=before['input_fingerprint']
        assert len(calls)==2


def test_time_budget_excludes_unknown_durations_and_completed_work():
    client=TestClient(app)
    with closing(connect()) as conn:
        seed(conn)
    result=client.get('/api/workflow/v1/agenda',params={'minutes':5,'source_id':'p1'}).json()
    assert result['estimated_minutes']<=5
    assert result['unscheduled_count']==4
    assert all(item['estimated_minutes'] is not None for item in result['items'])


def test_error_classification_keeps_rate_limit_separate():
    from app.task_control import error_code
    response=httpx.Response(429,request=httpx.Request('GET','https://example.test'))
    assert error_code(httpx.HTTPStatusError('rate',request=response.request,response=response))=='rate_limited'
    assert error_code(httpx.ReadTimeout('read'))=='timeout'


def test_cancel_queued_future_releases_capacity_immediately(monkeypatch):
    from concurrent.futures import Future
    import app.jobs as jobs
    future = Future()
    monkeypatch.setattr(jobs, 'submit_task', lambda *_: future)
    ident = jobs.enqueue('parse', {'uid': 'capacity'})
    with closing(connect()) as conn:
        stop_task(conn, f'legacy:{ident}')
        stop_task(conn, f'legacy:{ident}')
    assert future.cancelled()
    acquired = 0
    try:
        while jobs._slots.acquire(blocking=False):
            acquired += 1
        assert acquired == 24
    finally:
        for _ in range(acquired):
            jobs._slots.release()


def test_restart_capacity_overflow_is_visible_and_retryable(monkeypatch):
    import app.jobs as jobs
    monkeypatch.setattr(jobs, 'submit_task', lambda *_: None)
    resumed = 0
    try:
        with closing(connect()) as conn:
            conn.executemany("INSERT INTO tasks(type,status) VALUES('parse','queued')", [()]*25)
            conn.commit()
            resumed = jobs.recover_safe_queue(conn)
            assert resumed == 24
            assert conn.execute("SELECT COUNT(*) FROM tasks WHERE status='failed'").fetchone()[0] == 1
            assert conn.execute("SELECT error_code FROM task_controls").fetchone()[0] == 'restart_capacity'
    finally:
        for _ in range(resumed):
            jobs._slots.release()


def test_parallel_recommendation_refresh_commits_projection(fixture_project):
    from concurrent.futures import ThreadPoolExecutor
    from app.api.workflow import get_recommendations
    with closing(connect()) as conn:
        seed(conn)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: get_recommendations(), range(12)))
    assert all(result['items'] for result in results)
    with closing(connect()) as conn:
        assert conn.execute('SELECT COUNT(*) FROM activity_projection').fetchone()[0] >= 5
        assert not conn.execute('SELECT 1 FROM projection_revisions r LEFT JOIN projection_consumed c '
                                'ON c.kind=r.kind AND c.source_id=r.source_id WHERE c.token IS NULL OR c.token!=r.token').fetchone()


def test_audit_endpoint_commits_cache_for_parallel_page_sections(fixture_project):
    from concurrent.futures import ThreadPoolExecutor
    from app.api.assistant import project_audit, project_impact, comparison_readiness
    pid = fixture_project['project_id']
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda call: call(pid), [project_audit, project_impact, comparison_readiness]))
    assert len(results) == 3
    with closing(connect()) as conn:
        assert conn.execute('SELECT COUNT(*) FROM project_audit_cache WHERE project_id=?', (pid,)).fetchone()[0] == 1


def test_machine_action_version_is_stable_and_withdrawal_requires_review():
    from app.knowledge.unified import migrate
    from tests.test_roadmap_generate import setup_trusted
    source = setup_trusted()
    try:
        for row in source.execute('SELECT k.id,p.document_id,p.text FROM knowledge k JOIN passages p ON p.id=k.passage_id').fetchall():
            source.execute("UPDATE knowledge SET status='auto_checked',document_id=?,quote=?,start_offset=0,end_offset=6 WHERE id=?",
                           (row['document_id'], row['text'][:6], row['id']))
        migrate(source)
        source.commit()
        with closing(connect()) as target:
            source.backup(target)
    finally:
        source.close()
    client = TestClient(app)
    inputs = {'paper_uids': [], 'weekly_hours': 4, 'profile': {'goal': 'target', 'target_uid': 'method:target', 'weekly_hours': 4}}
    first = client.post('/api/actions/v1/preview', json=inputs)
    assert first.status_code == 200, first.text
    again = client.post('/api/actions/v1/preview', json=inputs).json()
    assert again['input_fingerprint'] == first.json()['input_fingerprint']
    result = client.post('/api/actions/v1', json={**inputs, 'title': 'Machine proposal', 'input_fingerprint': again['input_fingerprint']})
    assert result.status_code == 200, result.text
    ident = result.json()['id']
    with closing(connect()) as conn:
        assert conn.execute('SELECT COUNT(*) FROM roadmaps').fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM workflow_mastery').fetchone()[0] == 0
        conn.execute("UPDATE knowledge SET status='withdrawn' WHERE id=(SELECT min(id) FROM knowledge)")
        migrate(conn)
        conn.commit()
    assert client.get(f'/api/actions/v1/{ident}').json()['needs_review']
    adjusted = client.post(f'/api/actions/v1/{ident}/replan-preview', json={'expected_version': 1})
    assert adjusted.status_code == 200, adjusted.text
    assert adjusted.json()['diff']['removed']
    with closing(connect()) as conn:
        conn.execute("UPDATE knowledge SET status='withdrawn'")
        migrate(conn)
        conn.commit()
    assert client.post(f'/api/actions/v1/{ident}/replan-preview', json={'expected_version': 1}).status_code == 422
