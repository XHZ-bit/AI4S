"""Offline synthetic retrieval/evidence regression; never opens user databases."""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import closing, nullcontext
from pathlib import Path
from unittest.mock import patch

REPOSITORY_ROOT = Path(__file__).absolute().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from app.db.search_index import available  # noqa: E402
from app.db.sqlite import connect  # noqa: E402
from app.search import service  # noqa: E402

DEFAULT_FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_corpus.json"


def seed(conn, fixture):
    for paper in fixture["papers"]:
        conn.execute("INSERT INTO papers(uid,title,abstract,source) VALUES(?,?,?,'synthetic-retrieval')",
                     (paper["uid"], paper["title"], paper["abstract"]))
        for document in paper["documents"]:
            conn.execute("INSERT INTO documents(id,paper_uid,content_hash,coverage,created_at) VALUES(?,?,?,'fulltext',?)",
                         (document["id"], paper["uid"], document["content_hash"], document.get("created_at", "2026-01-01")))
            for passage in document["passages"]:
                conn.execute("INSERT INTO passages(id,document_id,heading,text,page,ordinal) VALUES(?,?,?,?,?,?)",
                             (passage["id"], document["id"], passage["heading"], passage["text"], passage["page"], passage["ordinal"]))
    conn.commit()


def _source_is_exact(conn, item):
    row = conn.execute("SELECT p.text,p.page,p.document_id,d.content_hash,d.paper_uid "
                       "FROM passages p JOIN documents d ON d.id=p.document_id WHERE p.id=?",
                       (item.get("passage_id"),)).fetchone()
    return bool(row and item.get("quote") and item["quote"] in row["text"]
                and len(item["quote"]) <= 280 and item["document_id"] == row["document_id"]
                and item["document_version"] == f"sha256:{row['content_hash']}"
                and item["page"] == row["page"] and item["uid"] == row["paper_uid"])


def evaluate_fixture(path=DEFAULT_FIXTURE, *, force_scan=False, k=3):
    if k < 1:
        raise ValueError("k must be positive")
    fixture = json.loads(Path(path).read_text(encoding="utf-8"))
    if fixture.get("partition") != "synthetic":
        raise ValueError("This runner only accepts explicitly synthetic regression fixtures")
    results = []
    recalls, reciprocal_ranks, top1 = [], [], []
    evidence_checks, negative_checks, no_evidence_checks = [], [], []
    citations, valid_citations = 0, 0
    with closing(connect(":memory:")) as conn:
        seed(conn, fixture)
        fts_available = available(conn)
        scope = patch.object(service, "search_index_available", return_value=False) if force_scan else nullcontext()
        with scope:
            for query in fixture["queries"]:
                items = service.lexical_search(conn, query["query"], limit=k)
                by_uid = {item["uid"]: item for item in items}
                ranked = list(by_uid)
                relevant = set(query["relevant_uids"])
                if relevant:
                    recalls.append(len(relevant & set(ranked)) / len(relevant))
                    reciprocal_ranks.append(next((1 / rank for rank, uid in enumerate(ranked, 1) if uid in relevant), 0))
                    top1.append(bool(ranked and ranked[0] == query["expected_first"]))
                else:
                    negative_checks.append(not items)
                for item in items:
                    if any(field in item for field in ("quote", "passage_id", "document_id", "document_version", "page")):
                        citations += 1
                        valid_citations += int(_source_is_exact(conn, item))
                for expected in query.get("evidence", []):
                    item = by_uid.get(expected["uid"], {})
                    evidence_checks.append(bool(item.get("passage_id") == expected["passage_id"]
                                                and item.get("page") == expected["page"]
                                                and all(term in item.get("quote", "") for term in expected["contains"])
                                                and _source_is_exact(conn, item)))
                for uid in query.get("no_evidence", []):
                    item = by_uid.get(uid)
                    no_evidence_checks.append(bool(item and not any(
                        field in item for field in ("quote", "passage_id", "document_id", "document_version", "page"))))
                results.append({"id": query["id"], "query": query["query"], "retrieved_uids": ranked,
                                "sources": [{key: item[key] for key in ("uid", "passage_id", "document_id", "document_version", "page", "quote")
                                             if key in item} for item in items if "passage_id" in item]})
    def mean(values):
        return round(sum(values) / len(values), 6) if values else None

    metrics = {f"recall_at_{k}": mean(recalls), f"mrr_at_{k}": mean(reciprocal_ranks),
               "top1_accuracy": mean(top1), "expected_evidence_accuracy": mean(evidence_checks),
               "negative_query_accuracy": mean(negative_checks), "metadata_without_invented_evidence": mean(no_evidence_checks),
               "citation_integrity": round(valid_citations / citations, 6) if citations else None,
               "invalid_citations": citations - valid_citations}
    return {"contract_version": "offline-retrieval-baseline-v1", "partition": "synthetic",
            "backend": "scan" if force_scan or not fts_available else "fts5-bm25-with-short-query-scan",
            "fts_available": fts_available, "paper_count": len(fixture["papers"]), "query_count": len(results),
            "positive_query_count": len(recalls), "expected_evidence_count": len(evidence_checks),
            "returned_citation_count": citations, "metrics": metrics,
            "passed": all(value == 1.0 for key, value in metrics.items() if key != "invalid_citations")
                      and metrics["invalid_citations"] == 0,
            "notice": fixture["notice"], "queries": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--scan", action="store_true", help="Exercise the no-FTS fallback")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate_fixture(args.fixture, force_scan=args.scan, k=args.k)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
