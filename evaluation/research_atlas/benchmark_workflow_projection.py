"""Compare warm paginated activities with source aggregation using isolated facts."""

import argparse
import json
import tempfile
from contextlib import closing
from pathlib import Path

from benchmark_local_search import measured
from prepare_browser_fixture import REPOSITORY_ROOT

from app import workflow
from app.db.projections import activity_page
from app.db.sqlite import connect
from app.db.workspace import get_state, put_state


def benchmark():
    temporary = REPOSITORY_ROOT / '.tmp'
    temporary.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='workflow-benchmark-', dir=temporary) as directory:
        with closing(connect(str(Path(directory)/'atlas.db'))) as conn:
            conn.executemany('INSERT INTO papers(uid,title) VALUES(?,?)',
                             [(f'p{i:04d}', f'Synthetic paper {i:04d}') for i in range(1000)])
            conn.executemany('INSERT INTO documents(id,paper_uid,content_hash,coverage) VALUES(?,?,?,?)',
                             [(f'd{i}', f'p{i:04d}', f'h{i}', 'fulltext') for i in range(1000)])
            conn.executemany('INSERT INTO passages(id,document_id,heading,text,ordinal) VALUES(?,?,?,?,0)',
                             [(f's{i}', f'd{i}', 'Original', 'Synthetic original text. '*100) for i in range(1000)])
            conn.commit()
            original = workflow._paper_activities
            expected, scan_ms = measured(lambda: sorted(list(original(conn)), key=lambda item:
                (item['status'], item['source_kind'], item['title'], item['id']))[:50])
            cold, cold_ms = measured(lambda: activity_page(conn, limit=50))
            assert cold['items'] == expected and cold['total'] == 5000
            calls = []

            def counted(database, source=None):
                calls.append(source)
                return original(database, source)

            workflow._paper_activities = counted
            try:
                _, warm_ms = measured(lambda: activity_page(conn, limit=50))
                assert calls == []
                state = get_state(conn, 'p0000')['state']
                state['reading']['read:s0'] = True
                put_state(conn, 'p0000', state, 0)
                activity_page(conn, limit=50)
                assert calls == ['p0000']
            finally:
                workflow._paper_activities = original
            return {'fixture': 'synthetic', 'paper_count': 1000, 'activity_count': 5000,
                    'page_size': 50, 'result_sets_equal': True, 'warm_source_rebuilds': 0,
                    'changed_source_rebuilds': calls, 'source_scan_median_ms': scan_ms,
                    'projection_median_ms': cold_ms, 'warm_page_median_ms': warm_ms,
                    'notice': 'Timing is environment specific; CI gates equality and invalidation scope only. First access builds the disposable projection.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = benchmark()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
