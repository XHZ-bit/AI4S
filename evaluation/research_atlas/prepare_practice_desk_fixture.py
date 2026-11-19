"""Import authored teaching source and prepare exercises using the real API."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from prepare_learning_entry_fixture import prepare as prepare_entry
from serve_practice_desk_fixture import FEEDBACK, INPUT_JSON, STARTER_CODE, create_app


def prepare(directory: Path):
    directory = directory.resolve()
    report = prepare_entry(directory)
    from fastapi.testclient import TestClient

    app = create_app(directory)
    exercises = {}
    with TestClient(app) as client:
        for key in ('goal', 'multihead'):
            response = client.post(f'/api/projects/{report["project_id"]}/knowledge/nodes/{report["nodes"][key]}/practice',
                                   json={'goal': '核对缩放分数与一行教学输入', 'difficulty': 'foundation'})
            response.raise_for_status()
            artifact = response.json()
            assert artifact['status'] == 'ready', artifact.get('errors')
            assert artifact['draft_code'] == STARTER_CODE
            exercises[key] = artifact['id']
        calls = client.get('/api/__acceptance__/practice/stats').json()['calls']
    report.update(purpose='desktop_practice_workspace_acceptance', exercises=exercises,
                  starter_code=STARTER_CODE, input_json=INPUT_JSON, fixed_feedback=FEEDBACK,
                  preparation_model_calls=calls, real_provider_calls=0)
    (directory / 'fixture.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    result = prepare(parser.parse_args().directory)
    print(json.dumps({'project_id': result['project_id'], 'exercises': result['exercises'],
                      'real_provider_calls': 0}, ensure_ascii=False))
