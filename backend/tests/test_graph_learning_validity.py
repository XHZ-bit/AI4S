"""Source validity and teaching recommendations must preserve graph semantics."""

import json
import sqlite3

import pytest

from app.knowledge import experience, extraction, learning, store


@pytest.fixture
def conn():
    connection = sqlite3.connect(':memory:')
    store.init(connection)
    yield connection
    connection.close()


def source(conn, sid, text, kind='paper'):
    value = {'id': sid, 'project_id': 'p', 'asset_id': sid + '-asset', 'version': sid + '-v1',
             'title': sid, 'filename': sid + '.md', 'kind': kind, 'removed': False}
    conn.execute('INSERT INTO kw_sources VALUES(?,?,?,?,?)', (sid, 'p', value['asset_id'], 0, store.encode(value)))
    store.put_parse(conn, value['asset_id'], {'blocks': [{'text': text, 'kind': 'text'}]})
    block = store.source_blocks(conn, value['asset_id'])[0]
    eid = store.add_evidence(conn, 'p', value, block)
    return value, block, eid


def node(conn, src, key, eid, *, label=None, meta=None):
    return store.put_record(conn, 'kw_nodes', extraction.node(src, key, 'method', label or key,
        'An explanation grounded in the provided source.', [eid], metadata=meta or {'semantic': True}))


def test_catalog_matches_are_optional_supplements_without_borrowed_paper_evidence(conn):
    src, _, eid = source(conn, 'gating', 'The model uses state gating for a bounded residual.')
    target = node(conn, src, 'method', eid, label='State gating with bounded residual')
    learning.add_prerequisites(conn, 'p', src['id'])
    detail = learning.detail(conn, 'p', target['id'])
    assert not detail['prerequisites']
    assert {n['metadata']['demo'] for n in detail['suggested_foundations']} >= {'activations', 'chain_rule'}
    assert all(not n['evidence_ids'] for n in detail['suggested_foundations'])
    assert all(e['kind'] == 'SUPPLEMENTS' and not e['evidence_ids'] for e in detail['edges'])
    assert not experience.paths(conn, 'p', target['id'], kind='prerequisites')['paths']
    foundation = detail['suggested_foundations'][0]
    assert learning.related_source_context(conn, 'p', foundation) == []
    basic = learning.basic(conn, 'p', foundation['id'])
    assert basic['origin'] == 'inference' and not basic['evidence']


def test_legacy_catalog_dependency_is_projected_without_mutating_history(conn):
    src, _, eid = source(conn, 'legacy', 'A paper that uses a gated model.')
    target = node(conn, src, 'target', eid)
    catalog = store.put_record(conn, 'kw_nodes', extraction.node(src, 'prerequisite:activations', 'concept',
        'sigmoid 与 tanh', 'Generic teaching content', [eid], origin='inference',
        metadata={'educational': True, 'demo': 'activations'}))
    edge = store.put_record(conn, 'kw_edges', extraction.edge(src, catalog['id'], target['id'],
        'PREREQUISITE_OF', '帮助理解', 'The previous catalog suggestion', [eid], origin='inference'))
    assert learning.prerequisites(conn, 'p', target['id']) == []
    assert learning.suggested_foundations(conn, 'p', target['id'])[0]['evidence_ids'] == []
    assert experience.graph_records(conn, 'p')[1][0]['kind'] == 'SUPPLEMENTS'
    assert store.record(conn, 'kw_edges', 'p', edge['id'])['kind'] == 'PREREQUISITE_OF'
    assert store.record(conn, 'kw_nodes', 'p', catalog['id'])['evidence_ids'] == [eid]


@pytest.mark.parametrize('damage', ['source_version', 'missing_block', 'changed_quote', 'missing_evidence'])
def test_partial_relation_evidence_never_justifies_a_prerequisite_or_question_context(conn, damage):
    own, _, e1 = source(conn, 'own', 'The target has its own grounded definition.')
    other, block, e2 = source(conn, 'other', 'Independent mathematical foundation.')
    target, foundation = node(conn, own, 'target', e1), node(conn, other, 'foundation', e2)
    # The edge remains owned by the current source, but needs BOTH citations.
    edge = store.put_record(conn, 'kw_edges', extraction.edge(own, foundation['id'], target['id'],
        'PREREQUISITE_OF', 'prerequisite', 'Both sources are necessary.', [e1, e2], origin='inference'))
    assert learning.prerequisites(conn, 'p', target['id'])
    if damage == 'source_version':
        changed = {**other, 'version': 'other-v2'}
        conn.execute('UPDATE kw_sources SET data=? WHERE id=?', (store.encode(changed), other['id']))
    elif damage == 'missing_block':
        conn.execute('DELETE FROM kw_blocks WHERE id=?', (block['id'],))
    elif damage == 'changed_quote':
        changed = {**block, 'text': 'This block now discusses something unrelated.'}
        conn.execute('UPDATE kw_blocks SET data=? WHERE id=?', (store.encode(changed), block['id']))
    else:
        conn.execute('DELETE FROM kw_evidence WHERE id=?', (e2,))
    _, edges, _ = experience.graph_records(conn, 'p')
    assert edge['id'] not in {e['id'] for e in edges}
    assert learning.prerequisites(conn, 'p', target['id']) == []
    assert learning._prerequisite_context(conn, 'p', target['id']) == {'nodes': [], 'edges': []}
    _, related, adjacent, citations = experience.question_context(conn, 'p', target['id'], 'Explain the foundation')
    assert not related and not adjacent and all(e['source_id'] == own['id'] for e in citations)
    assert store.record(conn, 'kw_edges', 'p', edge['id'])['id'] == edge['id']


def test_disputed_implementation_is_not_used_as_actual_supplied_code(conn):
    src, _, eid = source(conn, 'paper', 'A method for which the implementation is discussed.')
    code_src, _, code_eid = source(conn, 'code', 'def apply(x): return x', kind='code')
    target, code = node(conn, src, 'method', eid), node(conn, code_src, 'implementation', code_eid)
    relation = extraction.edge(src, target['id'], code['id'], 'IMPLEMENTED_BY', 'implementation',
        'An explicit implementation link.', [eid, code_eid], origin='inference')
    relation['quality_status'] = 'disputed'
    store.put_record(conn, 'kw_edges', relation)
    assert learning._linked_implementations(conn, 'p', target, store.evidence(conn, 'p', [code_eid])) == []
    assert not any(e['source_id'] == code_src['id'] for e in learning.related_source_context(conn, 'p', target))


def test_model_prerequisites_are_inferences_and_unknown_relationships_are_not_accepted(conn):
    src, block, _ = source(conn, 'paper', 'Differentiation and composition are explained in this passage.')
    result = {'nodes': [
        {'key': key, 'kind': 'concept', 'label': key, 'summary': 'A scoped mathematical concept',
         'evidence': [{'block_id': block['id'], 'quote': block['text']}]} for key in ['derivative', 'chain rule']],
        'edges': [
            {'source_key': 'derivative', 'target_key': 'chain rule', 'kind': 'PREREQUISITE_OF',
             'label': 'learn first', 'origin': 'source', 'evidence': [{'block_id': block['id'], 'quote': block['text']}]},
            {'source_key': 'chain rule', 'target_key': 'derivative', 'kind': 'PROVES_PHYSICAL_SAFETY', 'label': 'invented'}]}
    extraction.save_extraction(conn, src, result, [block])
    edges = [json.loads(row[0]) for row in conn.execute('SELECT data FROM kw_edges')]
    prerequisite = next(e for e in edges if e['kind'] == 'PREREQUISITE_OF')
    assert prerequisite['origin'] == 'inference'
    assert prerequisite['metadata']['prerequisite_basis'] == 'source_context_inference'
    assert not any(e['kind'] == 'PROVES_PHYSICAL_SAFETY' for e in edges)


def test_same_name_different_sources_remain_distinct_and_invalid_sources_do_not_link(conn):
    first, _, e1 = source(conn, 'a', 'A sigmoid network with its own conditions.')
    second, block, e2 = source(conn, 'b', 'Another sigmoid network with different conditions.')
    one, two = node(conn, first, 'method', e1, label='Shared Network'), node(conn, second, 'method', e2, label='Shared Network')
    extraction.connect_sources(conn, 'p', first['id'])
    assert one['id'] != two['id']
    edges = [json.loads(row[0]) for row in conn.execute('SELECT data FROM kw_edges')]
    assert len(edges) == 1 and edges[0]['kind'] == 'SHARED_TOPIC'
    conn.execute('DELETE FROM kw_blocks WHERE id=?', (block['id'],))
    current, others = extraction.connect_sources(conn, 'p', first['id'])
    assert len(current) == 1 and not others
