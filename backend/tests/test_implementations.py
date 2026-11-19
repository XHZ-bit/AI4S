import json
import sqlite3

import pytest
from fastapi import HTTPException

from app.knowledge import extraction, implementations, learning, store
from app.tenancy import user_scope


@pytest.fixture
def setup_mapping():
    conn = sqlite3.connect(':memory:')
    store.init(conn)
    def make_source(sid, kind, text):
        src = {'id': sid, 'project_id': 'p', 'asset_id': sid + '-asset', 'version': 'v1',
               'title': sid, 'filename': sid, 'kind': kind, 'removed': False}
        conn.execute('INSERT INTO kw_sources VALUES(?,?,?,?,?)', (sid, 'p', src['asset_id'], 0, store.encode(src)))
        store.put_parse(conn, src['asset_id'], {'blocks': [{'text': text, 'kind': 'code' if kind == 'code' else 'text',
            'metadata': {'start_line': 1, 'end_line': 2} if kind == 'code' else {}}]})
        block = store.source_blocks(conn, src['asset_id'])[0]
        return src, block, store.add_evidence(conn, 'p', src, block)
    paper, pb, pe = make_source('paper', 'paper', 'The gate scales the residual.')
    code, cb, _ = make_source('code', 'code', 'def gate(x):\n    return x * 0.5')
    node = store.put_record(conn, 'kw_nodes', extraction.node(paper, 'gate', 'method', 'gate', 'gated residual', [pe]))
    data = {'paper_evidence_id': pe, 'paper_span': 'gate scales', 'code_source_id': code['id'],
            'code_block_id': cb['id'], 'code_span': 'return x * 0.5', 'explanation': '可能对应', 'implementation_kind': 'source'}
    yield conn, node, data
    conn.close()


def test_confirm_then_stale_node_removes_link_from_learning(setup_mapping):
    conn, node, data = setup_mapping
    mapping = implementations.create(conn, 'p', node['id'], data)
    assert mapping['status'] == 'proposed' and not mapping['stale']
    mapping = implementations.revise(conn, 'p', node['id'], mapping['id'], {'expected_revision': 1, 'status': 'confirmed'})
    assert mapping['status'] == 'confirmed' and mapping['revision'] == 2
    assert any(e['kind'] == 'IMPLEMENTED_BY' for e in learning.current_neighbors(conn, 'p', node['id'])[1])
    node['version'] += 1
    conn.execute('UPDATE kw_nodes SET data=? WHERE id=?', (store.encode(node), node['id']))
    assert implementations.list_mappings(conn, 'p', node['id'])[0]['stale']
    assert not any(e['kind'] == 'IMPLEMENTED_BY' for e in learning.current_neighbors(conn, 'p', node['id'])[1])
    with pytest.raises(HTTPException) as error:
        implementations.revise(conn, 'p', node['id'], mapping['id'], {'expected_revision': 1, 'status': 'rejected'})
    assert error.value.status_code == 409


def test_untrusted_spans_and_missing_evidence_cannot_be_confirmed(setup_mapping):
    conn, node, data = setup_mapping
    with pytest.raises(HTTPException):
        implementations.create(conn, 'p', node['id'], {**data, 'code_span': 'invented code'})
    item = implementations.create(conn, 'p', node['id'], {**data, 'paper_evidence_id': None, 'paper_span': ''})
    assert item['paper_evidence'] is None
    with pytest.raises(HTTPException):
        implementations.revise(conn, 'p', node['id'], item['id'], {'expected_revision': 1, 'status': 'confirmed'})
    with pytest.raises(HTTPException):
        implementations.list_mappings(conn, 'another-project', node['id'])


def test_teaching_never_becomes_implementation_edge_and_reject_survives_missing_source(setup_mapping):
    conn, node, data = setup_mapping
    item = implementations.create(conn, 'p', node['id'], {**data, 'implementation_kind': 'teaching'})
    item = implementations.revise(conn, 'p', node['id'], item['id'], {'expected_revision': 1, 'status': 'confirmed'})
    assert not any(e['kind'] == 'IMPLEMENTED_BY' for e in learning.current_neighbors(conn, 'p', node['id'])[1])
    conn.execute('UPDATE kw_sources SET removed=1 WHERE id=?', (data['code_source_id'],))
    item = implementations.revise(conn, 'p', node['id'], item['id'], {'expected_revision': 2, 'status': 'rejected'})
    assert item['status'] == 'rejected' and item['stale']


def test_model_cannot_invent_or_cross_scope_candidates(setup_mapping):
    conn, node, data = setup_mapping
    _, paper, sources = implementations._inputs(conn, 'p', node['id'])
    malicious = {'items': [{**data, 'code_span': 'made up'}]}
    items, origin = implementations.candidates(node, paper, sources, malicious)
    assert origin == 'rule'
    assert all(item['code_span'] != 'made up' for item in items)
    item = {**data}
    items, origin = implementations.candidates(node, paper, sources, {'items': [item]})
    assert origin == 'model' and items[0]['code_span'] == data['code_span']


def test_reviewer_identity_and_exact_line_locations(setup_mapping):
    conn, node, data = setup_mapping
    item = implementations.create(conn, 'p', node['id'], {**data, 'start_line': 2, 'end_line': 2})
    assert item['code_evidence']['locator']['start_line'] == 2
    assert item['code_evidence']['locator']['end_line'] == 2
    with user_scope({'id': 'a' * 32, 'username': 'researcher'}):
        item = implementations.revise(conn, 'p', node['id'], item['id'], {'expected_revision': 1, 'status': 'confirmed'})
    assert item['reviewed_by'] == 'researcher'
    with pytest.raises(HTTPException):
        implementations.create(conn, 'p', node['id'], {**data, 'start_line': 1, 'end_line': 1})


def test_edit_clears_paper_and_requires_review_again(setup_mapping):
    conn, node, data = setup_mapping
    item = implementations.create(conn, 'p', node['id'], data)
    item = implementations.revise(conn, 'p', node['id'], item['id'], {'expected_revision': 1, 'status': 'confirmed'})
    item = implementations.revise(conn, 'p', node['id'], item['id'], {'expected_revision': 2, 'paper_evidence_id': None})
    assert item['status'] == 'proposed' and item['paper_span'] == '' and item['paper_evidence'] is None
    assert not learning.current_neighbors(conn, 'p', node['id'])[1]


def test_hidden_node_cannot_create_mapping_and_rank_prefers_links(setup_mapping):
    conn, node, data = setup_mapping
    _, _, sources = implementations._inputs(conn, 'p', node['id'])
    blocks = implementations.rank_blocks(node, {**sources[0], 'blocks': [
        {'id': 'unrelated', 'text': 'gate gate', 'metadata': {}},
        {'id': 'linked', 'text': 'unrelated', 'metadata': {}},
    ]}, {'linked'})
    assert blocks[0]['id'] == 'linked'
    node['hidden'] = True
    conn.execute('UPDATE kw_nodes SET hidden=1,data=? WHERE id=?', (store.encode(node), node['id']))
    with pytest.raises(HTTPException):
        implementations.create(conn, 'p', node['id'], data)


def test_generation_refresh_preserves_confirmed_and_rejected(setup_mapping, monkeypatch):
    from contextlib import contextmanager
    from app.api import implementations as api
    conn, node, data = setup_mapping
    @contextmanager
    def connection(_):
        yield conn
    monkeypatch.setattr(store, 'connection', connection)
    monkeypatch.setattr(api.model, 'available', lambda: False)
    req = api.Generate(source_ids=[data['code_source_id']], refresh=True)
    result = api.generate('p', node['id'], req)
    candidate = result['items'][0]
    candidate = implementations.revise(conn, 'p', node['id'], candidate['id'], {'expected_revision': 1, 'status': 'confirmed'})
    new = api.generate('p', node['id'], req)['items']
    assert len(new) == 1 and new[0]['status'] == 'confirmed' and new[0]['revision'] == candidate['revision']
    candidate = implementations.revise(conn, 'p', node['id'], candidate['id'], {'expected_revision': 2, 'status': 'rejected'})
    new = api.generate('p', node['id'], req)['items']
    assert len(new) == 1 and new[0]['status'] == 'rejected' and new[0]['revision'] == candidate['revision']


def test_practice_link_must_belong_to_same_project_and_node(setup_mapping):
    conn, node, data = setup_mapping
    conn.execute('CREATE TABLE kw_practice(id TEXT PRIMARY KEY, project_id TEXT, node_id TEXT, fingerprint TEXT, data TEXT)')
    for identity, pid, nid in [('valid', 'p', node['id']), ('other-node', 'p', 'not-this-node'), ('other-project', 'elsewhere', node['id'])]:
        conn.execute('INSERT INTO kw_practice VALUES(?,?,?,?,?)', (identity, pid, nid, 'fp', store.encode({'id': identity, 'node_id': nid})))
    item = implementations.create(conn, 'p', node['id'], data)
    for identity in ['missing', 'other-node', 'other-project']:
        with pytest.raises(HTTPException):
            implementations.revise(conn, 'p', node['id'], item['id'], {'expected_revision': 1, 'practice_id': identity})
    item = implementations.revise(conn, 'p', node['id'], item['id'], {'expected_revision': 1, 'practice_id': 'valid'})
    assert item['practice_id'] == 'valid'
    item = implementations.revise(conn, 'p', node['id'], item['id'], {'expected_revision': 2, 'practice_id': None})
    assert item['practice_id'] is None


def test_multiple_distinct_fragments_in_one_function_are_preserved(setup_mapping, monkeypatch):
    from contextlib import contextmanager
    from app.api import implementations as api
    conn, node, data = setup_mapping
    @contextmanager
    def connection(_):
        yield conn
    @contextmanager
    def operation(*_):
        yield
    monkeypatch.setattr(store, 'connection', connection)
    monkeypatch.setattr(api.model, 'available', lambda: True)
    monkeypatch.setattr(api.model, 'operation', operation)
    monkeypatch.setattr(api.model, 'structured', lambda *a, **k: {'items': [data, {**data, 'paper_span': 'residual.', 'code_span': 'def gate(x):'}]})
    result = api.generate('p', node['id'], api.Generate(source_ids=[data['code_source_id']], refresh=True))
    assert len(result['items']) == 2
    assert len({item['id'] for item in result['items']}) == 2
    assert {item['paper_span'] for item in result['items']} == {'gate scales', 'residual.'}


def test_rewritten_evidence_cannot_refresh_old_confirmation(setup_mapping):
    conn, node, data = setup_mapping
    old = implementations.create(conn, 'p', node['id'], data)
    old = implementations.revise(conn, 'p', node['id'], old['id'], {'expected_revision': 1, 'status': 'confirmed'})
    for sid in ('paper', 'code'):
        src = store.source(conn, 'p', sid)
        src['version'] = 'v2'
        conn.execute('UPDATE kw_sources SET data=? WHERE id=?', (store.encode(src), sid))
        block = store.source_blocks(conn, src['asset_id'])[0]
        store.add_evidence(conn, 'p', src, block)
    # Simulate old IDs having been replaced by the generic evidence writer.
    for prefix in ('paper', 'code'):
        eid = old[prefix + '_evidence']['id']
        row = conn.execute('SELECT data FROM kw_evidence WHERE id=?', (eid,)).fetchone()
        value = json.loads(row[0])
        value['source_version'] = 'v2'
        conn.execute('UPDATE kw_evidence SET data=? WHERE id=?', (store.encode(value), eid))
    new = implementations.create(conn, 'p', node['id'], data)
    assert new['code_evidence']['source_version'] == 'v2'
    old_after = next(v for v in implementations.list_mappings(conn, 'p', node['id']) if v['id'] == old['id'])
    assert old_after['stale']
    assert old_after['paper_evidence']['source_version'] == 'v1'
    assert old_after['code_evidence']['source_version'] == 'v1'
    assert not any(e['kind'] == 'IMPLEMENTED_BY' for e in learning.current_neighbors(conn, 'p', node['id'])[1])


def test_long_function_sends_and_suggests_bounded_relevant_window(setup_mapping, monkeypatch):
    from contextlib import contextmanager
    from app.api import implementations as api
    conn, node, data = setup_mapping
    node['label'] = 'tanh'
    conn.execute('UPDATE kw_nodes SET data=? WHERE id=?', (store.encode(node), node['id']))
    row = conn.execute('SELECT data FROM kw_blocks WHERE id=?', (data['code_block_id'],)).fetchone()
    block = json.loads(row[0])
    block['text'] = 'def transform(x):\n' + ('    x = x + 1\n' * 300) + '    return tanh(x)\n'
    block['metadata'] = {'symbol_kind': 'function', 'symbol': 'transform', 'start_line': 1, 'end_line': 302}
    conn.execute('UPDATE kw_blocks SET data=? WHERE id=?', (store.encode(block), block['id']))
    @contextmanager
    def connection(_):
        yield conn
    @contextmanager
    def operation(*_):
        yield
    captured = {}
    def structured(_system, payload, *_args, **_kwargs):
        captured.update(payload)
        return {'items': []}
    monkeypatch.setattr(store, 'connection', connection)
    monkeypatch.setattr(api.model, 'available', lambda: True)
    monkeypatch.setattr(api.model, 'operation', operation)
    monkeypatch.setattr(api.model, 'structured', structured)
    result = api.generate('p', node['id'], api.Generate(source_ids=[data['code_source_id']], refresh=True))
    excerpt = captured['code_sources'][0]['blocks'][0]['text']
    assert 'return tanh(x)' in excerpt and len(excerpt) <= 2000 and excerpt in block['text']
    assert 'return tanh(x)' in result['items'][0]['code_span']
    assert result['items'][0]['code_evidence']['locator']['start_line'] > 1


def test_generation_respects_rejected_manual_full_and_contained_spans(setup_mapping, monkeypatch):
    from contextlib import contextmanager
    from app.api import implementations as api
    conn, node, data = setup_mapping
    item = implementations.create(conn, 'p', node['id'], {**data,
        'paper_span': 'The gate scales the residual.', 'code_span': 'def gate(x):\n    return x * 0.5'})
    item = implementations.revise(conn, 'p', node['id'], item['id'], {'expected_revision': 1, 'status': 'rejected'})
    @contextmanager
    def connection(_):
        yield conn
    @contextmanager
    def operation(*_):
        yield
    monkeypatch.setattr(store, 'connection', connection)
    monkeypatch.setattr(api.model, 'available', lambda: True)
    monkeypatch.setattr(api.model, 'operation', operation)
    monkeypatch.setattr(api.model, 'structured', lambda *a, **k: {'items': [data]})
    response = api.generate('p', node['id'], api.Generate(source_ids=[data['code_source_id']], refresh=True))
    assert len(response['items']) == 1 and response['items'][0]['id'] == item['id']
    assert response['items'][0]['status'] == 'rejected'


def test_reviewed_partial_span_does_not_block_distinct_span(setup_mapping, monkeypatch):
    from contextlib import contextmanager
    from app.api import implementations as api
    conn, node, data = setup_mapping
    item = implementations.create(conn, 'p', node['id'], {**data, 'code_span': 'def gate(x):'})
    implementations.revise(conn, 'p', node['id'], item['id'], {'expected_revision': 1, 'status': 'rejected'})
    @contextmanager
    def connection(_):
        yield conn
    @contextmanager
    def operation(*_):
        yield
    monkeypatch.setattr(store, 'connection', connection)
    monkeypatch.setattr(api.model, 'available', lambda: True)
    monkeypatch.setattr(api.model, 'operation', operation)
    monkeypatch.setattr(api.model, 'structured', lambda *a, **k: {'items': [data]})
    response = api.generate('p', node['id'], api.Generate(source_ids=[data['code_source_id']], refresh=True))
    assert {value['status'] for value in response['items']} == {'proposed', 'rejected'}
