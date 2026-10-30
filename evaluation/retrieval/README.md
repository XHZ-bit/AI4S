# Offline retrieval and evidence regression

Run from the repository root:

```powershell
python evaluation/retrieval/evaluate_retrieval.py --output .tmp/retrieval-indexed.json
python evaluation/retrieval/evaluate_retrieval.py --scan --output .tmp/retrieval-scan.json
```

Both commands seed a fresh in-memory SQLite database. They never open the user's database, contact a model, download a paper, or require paid services. Exit code 0 means all checks in this fixed synthetic regression corpus pass; exit code 1 means a regression or a fixture mismatch.

The corpus has fictional English and Chinese metadata and passages. It checks title hits with original evidence, passage-only retrieval, relevant passages preceding newer but weaker documents, two-character queries, case and hyphen handling, unknown pages, metadata without fabricated citations, heading-only matches, and absent queries.

`recall_at_k` and `mrr_at_k` score positive queries. `top1_accuracy` uses each query's annotated first paper. `expected_evidence_accuracy` includes every annotated source target, counting a missing paper or wrong passage as failure. `citation_integrity` independently checks every returned source against stored passage text, document ID, version, page and owning paper; an exact substring is required. Negative queries and metadata-only results have separate checks and denominators.

These are synthetic regression results, not a scientific retrieval benchmark, a human-reviewed evidence-quality score, or proof of generalization. FTS5 chooses source passages using SQLite BM25 in ascending order. The short-query/no-FTS scan uses query coverage and hit density instead; its numerical relevance is not BM25. RRF still combines paper-level lexical and optional semantic rankings in `/api/search/v2`; this runner isolates offline lexical/source retrieval so it does not depend on a model's changing output.

SQLite reference: [FTS5 BM25](https://www.sqlite.org/fts5.html#the_bm25_function). Lower values are better in SQLite's implementation. Existing metadata score priority remains: source evidence adds a locator without replacing a title hit's reason.

`/api/search/v2` keeps its existing fields and RRF weights. A matching source passage adds these optional fields; metadata-only and semantic-only hits omit them:

| Field | Meaning |
|---|---|
| `passage_id` | Stored passage ID; resolves through `/api/learning/evidence/{id}`. |
| `document_id` | The document that owns that passage. |
| `document_version` | `sha256:` followed by that document's stored `content_hash`, matching the existing project contract. |
| `page` | Parser-recorded one-based page number, or `null` if unknown. |
| `quote` | At most 280 original characters, forming one exact continuous substring of the stored passage text. |

When a source is attached, `snippet` is the same original excerpt as `quote`. A title match retains its title hit reason. Retrieval relevance does not certify the passage's claim or scientific reliability. No fields are added to the legacy `/api/search` interface.
