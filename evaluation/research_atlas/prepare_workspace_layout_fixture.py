"""Prepare authored, isolated records for desktop workspace layout acceptance.

The local projects follow the normal import/parser/extraction path with a fixed
HTTP model response. Account projects use the public registration, project and
manual-node APIs. No normal user database is opened and no real provider runs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from prepare_project_network_fixture import prepare as prepare_network


def prepare(directory: Path):
    directory = directory.resolve()
    original = prepare_network(directory)
    from fastapi.testclient import TestClient
    from app.main import app

    identities = []
    for number in (1, 2):
        with TestClient(app) as client:
            username = f'layout-fixture-{number}'
            password = 'Authored-fixture-only-4917'
            response = client.post('/api/auth/register', json={'username': username, 'password': password})
            response.raise_for_status()
            session = response.json()
            client.headers['X-Atlas-CSRF'] = session['csrf_token']
            project = client.post('/api/projects', json={
                'title': f'布局验收账号{number}的独立课题', 'domain': 'custom',
                'research_question': '怎样调整节点阅读空间？',
                'constraints': {'version': 1, 'objective': '隔离桌面布局验收；全部记录自编'},
            })
            project.raise_for_status()
            pid = project.json()['id']
            client.patch(f'/api/projects/{pid}/knowledge/preferences', json={'mode': 'explore'}).raise_for_status()
            node = client.post(f'/api/projects/{pid}/knowledge/nodes', json={
                'label': f'账号{number}的个人阅读节点', 'kind': 'concept',
                'summary': '这条自编文字用于验证面板宽度与个人空间的隔离。',
            })
            node.raise_for_status()
            identities.append({'id': session['user']['id'], 'username': username, 'password': password,
                               'project_id': pid, 'node_id': node.json()['node']['id']})
    report = {**original, 'layout_accounts': identities, 'purpose': 'desktop_workspace_layout_acceptance'}
    (directory / 'fixture.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    report = prepare(parser.parse_args().directory)
    print(json.dumps({'project_id': report['project_id'], 'other_project_id': report['other_project_id'],
                      'account_count': len(report['layout_accounts']), 'real_provider_calls': 0}))
