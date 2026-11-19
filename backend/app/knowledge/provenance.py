"""Content-bound review metadata; model checks are not human verification."""

import hashlib
import json


def content_fingerprint(value):
    fields = ('source_id', 'kind', 'label', 'summary', 'source', 'target', 'explanation', 'evidence_ids')
    body = {key: value.get(key) for key in fields}
    body['latex'] = value.get('metadata', {}).get('latex')
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def review_is_stale(value, evidence):
    decision = value.get('metadata', {}).get('quality_decision', {})
    if decision.get('action') != 'verify':
        return False
    signature = decision.get('content_fingerprint')
    if signature and signature != content_fingerprint(value):
        return True
    if not evidence or len(evidence) != len(set(value.get('evidence_ids', []))):
        return True
    return any(e.get('source_missing') or e.get('source_changed') or e.get('unresolved') for e in evidence)
