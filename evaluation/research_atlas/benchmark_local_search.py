"""Reproducible local index/scan comparison; results are hardware specific."""

import argparse
import json
import statistics
import tempfile
import time
from contextlib import closing
from pathlib import Path

from prepare_browser_fixture import REPOSITORY_ROOT

from app.db.search_index import available
from app.db.sqlite import connect
from app.search import service


def measured(call):
    values = []
    for _ in range(5):
        start = time.perf_counter()
        result = call()
        values.append((time.perf_counter() - start) * 1000)
    return result, round(statistics.median(values), 3)


def benchmark():
    temporary = REPOSITORY_ROOT / ".tmp"
    temporary.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="search-benchmark-", dir=temporary) as folder:
        with closing(connect(str(Path(folder) / "atlas.db"))) as conn:
            conn.executemany("INSERT INTO papers(uid,title,abstract) VALUES(?,?,?)", (
                (f"synthetic-{index:05d}", f"Synthetic paper {index}",
                 "Distinctive atlasneedle condition" if index % 40 == 0 else
                 "Unrelated synthetic method and results") for index in range(2000)
            ))
            conn.commit()
            indexed_available = available(conn)
            indexed, indexed_ms = measured(lambda: service.lexical_search(conn, "atlasneedle"))
            original = service.search_index_available
            try:
                service.search_index_available = lambda _conn: False
                scanned, scan_ms = measured(lambda: service.lexical_search(conn, "atlasneedle"))
            finally:
                service.search_index_available = original
            assert indexed == scanned
            return {"contract_version": "local-search-benchmark-v1", "fixture": "synthetic",
                    "paper_count": 2000, "hit_count": len(indexed),
                    "trigram_index_available": indexed_available,
                    "indexed_median_ms": indexed_ms, "scan_median_ms": scan_ms,
                    "result_sets_equal": True,
                    "notice": "本机固定合成语料的五次中位数；仅用于同环境前后对照。"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = benchmark()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
