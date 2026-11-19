"""Current, source-grounded graph views used by learning and recommendations.

Records stay in storage for history. Filtering a teaching/model context never
withdraws a record or rewrites a user's interpretation.
"""

from __future__ import annotations

import json

from app.knowledge import store


def active(value):
    return not (value.get('hidden') or value.get('source_missing')
                or value.get('quality_status') in {'withdrawn', 'rejected', 'disputed'}
                or value.get('metadata', {}).get('source_withdrawn'))


def valid_evidence(value):
    return not any(value.get(key) for key in ('source_missing', 'source_changed', 'unresolved'))


def teaching_node(value):
    metadata = value.get('metadata', {})
    return bool(metadata.get('educational') and metadata.get('demo'))


def project_teaching_node(value):
    """Legacy catalog matches borrowed the paper's citations; do not repeat that claim."""
    if not teaching_node(value):
        return value
    return {**value, 'evidence_ids': [], 'metadata': {**value.get('metadata', {}),
            'knowledge_role': 'teaching_supplement'}}


def project_teaching_edge(value, nodes):
    source = nodes.get(value['source'])
    if (source and teaching_node(source) and value.get('origin') == 'inference'
            and value['kind'] == 'PREREQUISITE_OF' and not value.get('metadata', {}).get('user_fields')):
        return {**value, 'kind': 'SUPPLEMENTS', 'label': '补充学习', 'evidence_ids': [],
                'explanation': '按知识类型匹配的可选教学补充，不是论文声明的先修关系。',
                'metadata': {**value.get('metadata', {}), 'knowledge_role': 'teaching_supplement'}}
    return value


def current_records(conn, pid, records, *, source_map=None):
    """Return active records only when every cited fragment is still locatable.

    A partly stale cross-source relationship cannot be justified by its one
    remaining citation. Uncited legacy/user relationships retain their existing
    meaning; catalog suggestions are handled separately from prerequisites.
    """
    sources = source_map if source_map is not None else {
        row[0]: json.loads(row[1]) for row in conn.execute(
            'SELECT id,data FROM kw_sources WHERE project_id=? AND removed=0', (pid,))}
    records = [value for value in records if active(value) and value['source_id'] in sources]
    ids = list(dict.fromkeys(eid for value in records for eid in value.get('evidence_ids', [])))
    available = {value['id'] for value in store.evidence(conn, pid, ids) if valid_evidence(value)}
    records = [value for value in records if all(eid in available for eid in value.get('evidence_ids', []))]
    # User-confirmed implementation links depend on the version of the method,
    # not merely the two citations. A later node edit requires another review.
    def current_mapping(value):
        concept_versions = value.get('metadata', {}).get('concept_node_versions')
        if concept_versions:
            table = conn.execute("SELECT 1 FROM sqlite_master WHERE name='kw_concept_correspondences'").fetchone()
            if not table:
                return False
            decision = conn.execute('SELECT data FROM kw_concept_correspondences WHERE id=? AND project_id=?',
                                    (value['metadata'].get('concept_correspondence_id'), pid)).fetchone()
            if not decision:
                return False
            decision = json.loads(decision[0])
            if decision.get('status') not in {'comparable', 'conditions_differ'} or decision.get('revision') != value['metadata'].get('concept_correspondence_revision'):
                return False
            for nid, version in concept_versions.items():
                row = conn.execute('SELECT data FROM kw_nodes WHERE id=? AND project_id=?', (nid, pid)).fetchone()
                if not row or json.loads(row[0]).get('version') != version or not active(json.loads(row[0])):
                    return False
            captured = value['metadata'].get('concept_evidence_snapshot', [])
            live = {item['id']: item for item in store.evidence(conn, pid, [item['id'] for item in captured])}
            for item in captured:
                current = live.get(item['id'])
                if not current or not valid_evidence(current) or any(item.get(key) != current.get(key) for key in ('quote', 'block_id', 'source_version', 'locator')):
                    return False
        mid = value.get('metadata', {}).get('implementation_mapping_id')
        if not mid:
            return True
        table = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='kw_implementations'").fetchone()
        if not table:
            return False
        row = conn.execute('SELECT data FROM kw_implementations WHERE id=? AND project_id=?', (mid, pid)).fetchone()
        if not row:
            return False
        mapping = json.loads(row[0])
        node = conn.execute('SELECT data FROM kw_nodes WHERE id=? AND project_id=?', (mapping.get('node_id'), pid)).fetchone()
        if not (node and mapping.get('status') == 'confirmed' and mapping.get('implementation_kind') == 'source'
                and json.loads(node[0]).get('version') == mapping.get('node_version')):
            return False
        for prefix in ('paper', 'code'):
            evidence = mapping.get(prefix + '_evidence_snapshot')
            if not evidence:
                found = store.evidence(conn, pid, [mapping.get(prefix + '_evidence_id')])
                evidence = found[0] if found else None
            src = sources.get(evidence.get('source_id')) if evidence else None
            expected = mapping.get('source_versions', {}).get(prefix)
            if not src or not expected or src.get('version') != expected:
                return False
        return True
    return [value for value in records if current_mapping(value)]
